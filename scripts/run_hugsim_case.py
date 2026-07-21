#!/usr/bin/env python3
"""Run one bounded HUGSIM case with the deterministic plan writer.

This is a small orchestration wrapper around the existing audit runner. It
keeps the simulator/receiver FIFO boundary intact while removing the manual
"start one shell, then start another shell" step from reproducible experiments.
"""

from __future__ import annotations

import argparse
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


def run_and_log(
    command: list[str],
    env: dict[str, str],
    log_path: Path,
) -> int:
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        return process.wait()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    scenario = args.scenario.expanduser().resolve()
    output = args.output.expanduser().resolve()
    python = Path(args.python).expanduser().resolve()

    if args.max_steps < 1:
        raise ValueError("--max-steps must be at least 1")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output}")
    if not scenario.is_file():
        raise FileNotFoundError(f"Missing scenario file: {scenario}")
    if not python.is_file():
        raise FileNotFoundError(f"Missing HUGSIM Python interpreter: {python}")

    env = runtime_env()
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
        "--output",
        str(output),
    ]
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
        str(args.max_steps),
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
        writer_code = run_and_log(writer_cmd, env, writer_log)
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
