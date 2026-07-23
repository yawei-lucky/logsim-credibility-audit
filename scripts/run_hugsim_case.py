#!/usr/bin/env python3
"""Run one bounded HUGSIM case with the deterministic plan writer.

This is a small orchestration wrapper around the existing audit runner. It
keeps the simulator/receiver FIFO boundary intact while removing the manual
"start one shell, then start another shell" step from reproducible experiments.
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one bounded HUGSIM case.")
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-steps", type=int, default=36)
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--step-m", type=float, default=1.0)
    parser.add_argument("--timeout-s", type=float, default=900.0)
    parser.add_argument("--control-hold-steps", type=int, default=1)
    writer_group = parser.add_mutually_exclusive_group()
    writer_group.add_argument(
        "--sparsedrive-native-output",
        type=Path,
        help="Replay frozen native SparseDrive plans for interface qualification.",
    )
    writer_group.add_argument(
        "--sparsedrive-live-source-run",
        type=Path,
        help="Run SparseDrive live after exact recorded-history pre-warm.",
    )
    parser.add_argument(
        "--warm-start-source-run",
        type=Path,
        help=(
            "Replay the source run inside HUGSIM through the SparseDrive "
            "handoff boundary before opening the live loop."
        ),
    )
    parser.add_argument("--warm-start-steps", type=int, default=6)
    parser.add_argument("--sparsedrive-start-index", type=int, default=0)
    parser.add_argument(
        "--sparsedrive-reference-native-output",
        type=Path,
        help="Qualified offline native output used to check the first live plan.",
    )
    parser.add_argument(
        "--writer-python",
        default="/home/yawei/miniforge3/envs/sparse4d-audit/bin/python",
    )
    parser.add_argument("--sparsedrive-root", default="/home/yawei/SparseDrive")
    parser.add_argument(
        "--sparsedrive-checkpoint",
        default=(
            "/home/yawei/logsim-credibility-audit/artifacts/"
            "sparsedrive_receiver/official-v1.0/sparsedrive_stage2.pth"
        ),
    )
    parser.add_argument(
        "--sparsedrive-runtime-deps",
        default=(
            "/home/yawei/logsim-credibility-audit/artifacts/"
            "sparsedrive_receiver/runtime-deps-v1"
        ),
    )
    parser.add_argument(
        "--sparsedrive-anchor-dir",
        default=(
            "/home/yawei/logsim-credibility-audit/artifacts/"
            "sparsedrive_receiver/official-v1.0/anchors"
        ),
    )
    parser.add_argument(
        "--python",
        default="/home/yawei/HUGSIM/.pixi/envs/default/bin/python",
        help="Python interpreter inside the HUGSIM runtime environment.",
    )
    return parser.parse_args()


def runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    cuda_bin = "/usr/local/cuda-12.1/bin"
    current_path = env.get("PATH", "")
    if cuda_bin not in current_path.split(":"):
        env["PATH"] = f"{cuda_bin}:{current_path}"
    env["CUDA_HOME"] = "/usr/local/cuda-12.1"
    env["TORCH_CUDA_ARCH_LIST"] = "8.9"
    return env


def wait_for_pipes(
    output: Path,
    runner: subprocess.Popen[str],
    timeout_s: float,
) -> None:
    deadline = time.monotonic() + timeout_s
    obs_pipe = output / "obs_pipe"
    plan_pipe = output / "plan_pipe"
    while time.monotonic() < deadline:
        if runner.poll() is not None:
            raise RuntimeError(f"HUGSIM runner exited early with code {runner.returncode}")
        if obs_pipe.exists() and plan_pipe.exists():
            return
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for FIFOs in {output}")


def run_writer_with_runner_monitor(
    command: list[str],
    env: dict[str, str],
    log_path: Path,
    runner: subprocess.Popen[str],
    *,
    runner_exit_grace_s: float = 10.0,
) -> int:
    with log_path.open("w", encoding="utf-8") as log:
        writer = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        runner_exit_seen_at: float | None = None
        while True:
            writer_code = writer.poll()
            if writer_code is not None:
                return writer_code
            runner_code = runner.poll()
            if runner_code is None:
                runner_exit_seen_at = None
            elif runner_exit_seen_at is None:
                runner_exit_seen_at = time.monotonic()
            elif (
                time.monotonic() - runner_exit_seen_at
                >= runner_exit_grace_s
            ):
                writer.terminate()
                try:
                    writer.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    writer.kill()
                    writer.wait()
                raise RuntimeError(
                    "HUGSIM runner exited while the receiver was still "
                    f"waiting; runner code={runner_code}"
                )
            time.sleep(0.25)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    scenario = args.scenario.expanduser().resolve()
    output = args.output.expanduser().resolve()
    python = Path(args.python).expanduser().resolve()
    writer_python = Path(args.writer_python).expanduser().resolve()

    if args.max_steps < 1:
        raise ValueError("--max-steps must be at least 1")
    if args.control_hold_steps < 1:
        raise ValueError("--control-hold-steps must be at least 1")
    if args.warm_start_steps < 1:
        raise ValueError("--warm-start-steps must be at least 1")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not scenario.is_file():
        raise FileNotFoundError(f"Missing scenario file: {scenario}")
    if not python.is_file():
        raise FileNotFoundError(f"Missing HUGSIM Python interpreter: {python}")

    env = runtime_env()
    writer_env = env.copy()
    runner_log = output.with_name(output.name + ".runner.log")
    writer_log = output.with_name(output.name + ".writer.log")
    runner_cmd = [
        str(python),
        str(repo_root / "scripts" / "run_hugsim_debug_smoke.py"),
        "--scenario",
        str(scenario),
        "--max-steps",
        str(args.max_steps),
        "--control-convention",
        "corrected",
        "--control-hold-steps",
        str(args.control_hold_steps),
        "--output",
        str(output),
    ]
    requested_plans = math.ceil(args.max_steps / args.control_hold_steps)
    if args.sparsedrive_native_output is not None:
        native_output = args.sparsedrive_native_output.expanduser().resolve()
        if not native_output.is_file():
            raise FileNotFoundError(
                f"Missing SparseDrive native output: {native_output}"
            )
        runner_cmd.extend(("--strict-action-bounds", "--skip-evaluation"))
        writer_cmd = [
            str(python),
            str(
                repo_root
                / "scripts"
                / "hugsim_sparsedrive_plan_replay_writer.py"
            ),
            "--output",
            str(output),
            "--native-output",
            str(native_output),
            "--start-index",
            str(args.sparsedrive_start_index),
            "--max-plans",
            str(requested_plans),
        ]
    elif args.sparsedrive_live_source_run is not None:
        source_run = args.sparsedrive_live_source_run.expanduser().resolve()
        warm_start_source_run = (
            args.warm_start_source_run.expanduser().resolve()
            if args.warm_start_source_run is not None
            else None
        )
        reference_native = (
            args.sparsedrive_reference_native_output.expanduser().resolve()
            if args.sparsedrive_reference_native_output is not None
            else None
        )
        if not source_run.is_dir():
            raise FileNotFoundError(f"Missing live source run: {source_run}")
        if (
            warm_start_source_run is not None
            and warm_start_source_run != source_run
        ):
            raise ValueError(
                "The HUGSIM warm start and SparseDrive source run must match"
            )
        if reference_native is None or not reference_native.is_file():
            raise FileNotFoundError(
                "A valid --sparsedrive-reference-native-output is required"
            )
        if not writer_python.is_file():
            raise FileNotFoundError(f"Missing writer Python: {writer_python}")
        runner_cmd.extend(("--strict-action-bounds", "--skip-evaluation"))
        if warm_start_source_run is not None:
            runner_cmd.extend(
                (
                    "--warm-start-source-run",
                    str(warm_start_source_run),
                    "--warm-start-steps",
                    str(args.warm_start_steps),
                )
            )
        sparse_root = str(Path(args.sparsedrive_root).expanduser().resolve())
        writer_env["PYTHONPATH"] = (
            f"{sparse_root}:{repo_root / 'scripts'}:"
            f"{writer_env.get('PYTHONPATH', '')}"
        )
        writer_cmd = [
            str(writer_python),
            str(repo_root / "scripts" / "hugsim_sparsedrive_live_writer.py"),
            "--output",
            str(output),
            "--source-run",
            str(source_run),
            "--reference-native-output",
            str(reference_native),
            "--max-plans",
            str(requested_plans),
            "--sparsedrive-root",
            sparse_root,
            "--checkpoint",
            str(Path(args.sparsedrive_checkpoint).expanduser().resolve()),
            "--runtime-deps",
            str(Path(args.sparsedrive_runtime_deps).expanduser().resolve()),
            "--anchor-dir",
            str(Path(args.sparsedrive_anchor_dir).expanduser().resolve()),
        ]
        if warm_start_source_run is not None:
            writer_cmd.append("--source-warm-started")
    else:
        writer_cmd = [
            str(python),
            str(repo_root / "scripts" / "hugsim_plan_pipe_writer.py"),
            "--output",
            str(output),
            "--horizon",
            str(args.horizon),
            "--step-m",
            str(args.step_m),
            "--max-steps",
            str(requested_plans),
        ]

    with runner_log.open("w", encoding="utf-8") as runner_stream:
        runner = subprocess.Popen(
            runner_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        assert runner.stdout is not None
        start = time.monotonic()
        while time.monotonic() - start < args.timeout_s:
            line = runner.stdout.readline()
            if line:
                print(line, end="", flush=True)
                runner_stream.write(line)
                runner_stream.flush()
                if "[debug-smoke] ready output=" in line:
                    break
            elif runner.poll() is not None:
                raise RuntimeError(
                    f"HUGSIM runner exited early with code {runner.returncode}"
                )
            else:
                time.sleep(0.2)
        else:
            runner.terminate()
            raise TimeoutError("Timed out waiting for HUGSIM runner readiness")

        wait_for_pipes(output, runner, args.timeout_s)
        writer_code = run_writer_with_runner_monitor(
            writer_cmd,
            writer_env,
            writer_log,
            runner,
        )
        if writer_code != 0:
            runner.terminate()
            runner.wait(timeout=10)
            return writer_code

        for line in runner.stdout:
            print(line, end="", flush=True)
            runner_stream.write(line)
            runner_stream.flush()
        runner_code = runner.wait()
        if runner_code != 0:
            return runner_code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
