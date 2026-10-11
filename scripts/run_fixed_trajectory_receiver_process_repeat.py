#!/usr/bin/env python3
"""Run fresh SparseDrive process repeats with frozen input snapshots."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from compare_fixed_trajectory_receiver_regression import (
    git,
    load_json,
    resolve,
    sha256,
)
from compare_fixed_trajectory_receiver_process_repeat import (
    build_receiver_command,
    directory_tree_sha256,
    verify_live_primary_assets,
)


ROOT = Path(__file__).resolve().parents[1]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def expected_image_rows(primary_result, window_id):
    result = next(
        item for item in primary_result["windows"] if item["window"] == window_id
    )
    return {
        (int(row["frame_index"]), row["camera"]): row["destination_sha256"]
        for row in result["input_identity"]["rows"]
    }


def input_snapshot(primary_config, primary_result, window):
    primary_window = next(
        item for item in primary_config["windows"] if item["id"] == window["id"]
    )
    input_root = resolve(primary_window["current_input_root"])
    manifest_path = input_root / "assembled_render_manifest.json"
    metadata_path = input_root / "metadata_exact_pose_window.json"
    manifest = load_json(manifest_path)
    expected = expected_image_rows(primary_result, window["id"])
    rows = []
    for item in manifest["images"]:
        key = (int(item["frame_index"]), item["camera"])
        if key not in expected:
            raise ValueError(f"{window['id']}: unexpected input image {key}")
        path = Path(item["destination"]).resolve()
        actual = sha256(path)
        rows.append(
            {
                "frame_index": key[0],
                "camera": key[1],
                "path": str(path),
                "sha256": actual,
                "expected_sha256": expected[key],
                "exact": actual == expected[key],
            }
        )
    if len(rows) != 48 or {(
        row["frame_index"], row["camera"]
    ) for row in rows} != set(expected):
        raise ValueError(f"{window['id']}: input image key set drift")
    snapshot = {
        "captured_utc": utc_now(),
        "input_root": str(input_root),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "metadata": str(metadata_path),
        "metadata_sha256": sha256(metadata_path),
        "image_count": len(rows),
        "exact_image_count": sum(row["exact"] for row in rows),
        "all_images_exact": all(row["exact"] for row in rows),
        "rows": rows,
    }
    if not snapshot["all_images_exact"]:
        raise ValueError(f"{window['id']}: input image hash drift")
    return snapshot


def asset_snapshot(primary_config):
    verify_live_primary_assets(primary_config)
    return {
        "contract_passed": True,
        "runtime_deps_tree": directory_tree_sha256(
            resolve(primary_config["runtime_deps"])
        ),
        "primary_comparison_script_sha256": sha256(
            resolve(primary_config["comparison_script"])
        ),
        "receiver_adapter_sha256": sha256(
            resolve(primary_config["receiver_adapter"])
        ),
        "sparsedrive_commit": git(
            resolve(primary_config["sparsedrive_root"]), "rev-parse", "HEAD"
        ),
        "sparsedrive_status": git(
            resolve(primary_config["sparsedrive_root"]), "status", "--short"
        ).splitlines(),
    }


def stable_input_snapshot(snapshot):
    return {key: value for key, value in snapshot.items() if key != "captured_utc"}


def run(config_path, manifest_path):
    config = load_json(config_path)
    primary_config = load_json(resolve(config["primary_config"]))
    primary_result = load_json(resolve(config["primary_regression"]))
    if sha256(Path(__file__).resolve()) != config["runner_script_sha256"]:
        raise ValueError("runner script hash drift")
    if sha256(resolve(config["primary_config"])) != config[
        "primary_config_sha256"
    ]:
        raise ValueError("primary config hash drift")
    if sha256(resolve(config["primary_regression"])) != config[
        "primary_regression_sha256"
    ]:
        raise ValueError("primary regression hash drift")
    if resolve(config["comparison_script"]) != (
        ROOT / "scripts/compare_fixed_trajectory_receiver_process_repeat.py"
    ).resolve():
        raise ValueError("process-repeat comparison script path drift")
    if sha256(resolve(config["comparison_script"])) != config[
        "comparison_script_sha256"
    ]:
        raise ValueError("process-repeat comparison script hash drift")
    if sha256(resolve(config["diagnostic_helper"])) != config[
        "diagnostic_helper_sha256"
    ]:
        raise ValueError("diagnostic helper hash drift")
    if sha256(resolve(config["primary_native_diagnostic"])) != config[
        "primary_native_diagnostic_sha256"
    ]:
        raise ValueError("primary native diagnostic hash drift")
    if primary_result["summary"]["all_checks_passed"]:
        raise ValueError("primary regression did not retain the expected failure")
    initial_assets = asset_snapshot(primary_config)
    if initial_assets["runtime_deps_tree"] != config["runtime_deps_tree"]:
        raise ValueError("runtime dependency tree drift")
    gpu_driver_and_name = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=driver_version,name",
            "--format=csv,noheader",
        ],
        text=True,
    ).strip()
    if gpu_driver_and_name != config["gpu_driver_and_name"]:
        raise ValueError("GPU/driver drift")
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite {manifest_path}")
    log_root = resolve(config["log_root"])
    if log_root.exists():
        raise FileExistsError(f"refusing to overwrite {log_root}")
    for window in config["windows"]:
        if resolve(window["right_receiver_root"]).exists():
            raise FileExistsError(
                f"refusing to overwrite {resolve(window['right_receiver_root'])}"
            )
    audit_status = git(ROOT, "status", "--short")
    if audit_status:
        raise ValueError(f"audit repository is not clean: {audit_status}")
    log_root.mkdir(parents=True)
    result = {
        "experiment_id": config["experiment_id"],
        "started_utc": utc_now(),
        "finished_utc": None,
        "status": "running",
        "host": platform.node(),
        "config": str(Path(config_path).resolve()),
        "config_sha256": sha256(config_path),
        "runner_script_sha256": sha256(Path(__file__).resolve()),
        "comparison_script_sha256": sha256(
            resolve(config["comparison_script"])
        ),
        "diagnostic_helper_sha256": sha256(
            resolve(config["diagnostic_helper"])
        ),
        "primary_regression_sha256": sha256(
            resolve(config["primary_regression"])
        ),
        "primary_native_diagnostic_sha256": sha256(
            resolve(config["primary_native_diagnostic"])
        ),
        "audit_commit": git(ROOT, "rev-parse", "HEAD"),
        "audit_status": audit_status,
        "gpu_driver_and_name": gpu_driver_and_name,
        "initial_assets": initial_assets,
        "windows": [],
    }
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(resolve(primary_config["runtime_deps"]))
    environment["MPLCONFIGDIR"] = "/tmp/mpl-sparsedrive-receiver-process-repeat"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    exit_code = 0
    for window in config["windows"]:
        assets_pre = asset_snapshot(primary_config)
        pre = input_snapshot(primary_config, primary_result, window)
        command = build_receiver_command(primary_config, window)
        log_path = log_root / f"{window['id']}.log"
        started = utc_now()
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        log_path.write_text(completed.stdout + completed.stderr)
        post = input_snapshot(primary_config, primary_result, window)
        assets_post = asset_snapshot(primary_config)
        output_root = resolve(window["right_receiver_root"])
        report_path = output_root / "sparsedrive_real_source_qualification.json"
        native_path = output_root / "native_outputs.pt"
        row = {
            "window": window["id"],
            "started_utc": started,
            "finished_utc": utc_now(),
            "command": command,
            "environment": {
                "PYTHONPATH": environment["PYTHONPATH"],
                "MPLCONFIGDIR": environment["MPLCONFIGDIR"],
                "PYTHONDONTWRITEBYTECODE": environment[
                    "PYTHONDONTWRITEBYTECODE"
                ],
            },
            "returncode": completed.returncode,
            "log": str(log_path),
            "log_sha256": sha256(log_path),
            "input_pre": pre,
            "input_post": post,
            "input_unchanged": stable_input_snapshot(pre)
            == stable_input_snapshot(post),
            "assets_pre": assets_pre,
            "assets_post": assets_post,
            "receiver_report": str(report_path),
            "receiver_report_sha256": (
                sha256(report_path) if report_path.is_file() else None
            ),
            "native_outputs": str(native_path),
            "native_outputs_sha256": (
                sha256(native_path) if native_path.is_file() else None
            ),
        }
        result["windows"].append(row)
        if (
            completed.returncode != 0
            or not row["input_unchanged"]
            or assets_pre != assets_post
            or not report_path.is_file()
            or not native_path.is_file()
        ):
            exit_code = 1
            break
    result["finished_utc"] = utc_now()
    result["status"] = "complete" if exit_code == 0 else "failed"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(manifest_path)
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    return run(args.config.resolve(), args.manifest.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
