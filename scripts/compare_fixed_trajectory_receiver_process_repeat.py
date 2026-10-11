#!/usr/bin/env python3
"""Compare two fresh-process SparseDrive runs on the same frozen RGB inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch

from compare_fixed_trajectory_receiver_regression import (
    check_hash,
    compare_native_nodes,
    compare_report_sequences,
    git,
    git_diff_sha256,
    load_json,
    recompute_reset_repeat,
    report_native_plan_difference,
    resolve,
    sha256,
)
from diagnose_fixed_trajectory_receiver_regression import (
    id_aligned_detection_diagnostic,
    top_detection_diagnostic,
)


ROOT = Path(__file__).resolve().parents[1]
IDENTITY_SECTIONS = (
    "source",
    "model",
    "receiver_source",
    "adapter",
    "calibration",
    "ego_and_reference",
)


def directory_tree_sha256(root):
    root = Path(root).resolve()
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256(path)))
    return {"file_count": len(files), "sha256": digest.hexdigest()}


def build_receiver_command(primary_config, window):
    primary_window = next(
        item for item in primary_config["windows"] if item["id"] == window["id"]
    )
    input_root = resolve(primary_window["current_input_root"])
    command = [
        str(resolve(primary_config["runtime_python"])),
        str(resolve(primary_config["receiver_adapter"])),
        "--sparsedrive-root",
        str(resolve(primary_config["sparsedrive_root"])),
        "--checkpoint",
        str(resolve(primary_config["checkpoint"])),
        "--runtime-deps",
        str(resolve(primary_config["runtime_deps"])),
        "--anchor-dir",
        str(resolve(primary_config["anchor_dir"])),
        "--source-root",
        str(input_root),
        "--metadata",
        str(input_root / "metadata_exact_pose_window.json"),
        "--source-archive-manifest",
        str(input_root / "assembled_render_manifest.json"),
        "--metadata-archive-manifest",
        str(resolve(primary_config["metadata_archive_manifest"])),
        "--calibration-reference-run",
        str(resolve(primary_config["calibration_reference_run"])),
    ]
    for frame in window["frames"]:
        command.extend(("--frame-index", str(frame)))
    command.extend(
        ("--baseline-only", "--output", str(resolve(window["right_receiver_root"])))
    )
    return command


def native_result(primary_config, left, right):
    stats = compare_native_nodes(left, right)
    stats["within_float_tolerance"] = (
        stats["max_abs_float_difference"]
        <= float(primary_config["native_float_max_abs_tolerance"])
    )
    stats["all_integer_outputs_exact"] = stats["integer_mismatch_count"] == 0
    stats["all_other_scalars_exact"] = (
        stats["other_scalar_mismatch_count"] == 0
    )
    stats["passed"] = all(
        (
            stats["structure_equal"],
            stats["float_all_finite"],
            stats["within_float_tolerance"],
            stats["all_integer_outputs_exact"],
            stats["all_other_scalars_exact"],
        )
    )
    return stats


def verify_live_primary_assets(primary_config):
    for path_key, hash_key in (
        ("comparison_script", "comparison_script_sha256"),
        ("source_metadata", "source_metadata_sha256"),
        ("metadata_archive_manifest", "metadata_archive_manifest_sha256"),
        ("assembly_script", "assembly_script_sha256"),
        ("receiver_adapter", "receiver_adapter_sha256"),
        ("checkpoint", "checkpoint_sha256"),
        ("model_config", "model_config_sha256"),
    ):
        check_hash(
            resolve(primary_config[path_key]),
            primary_config[hash_key],
            f"primary {path_key}",
        )
    for helper in primary_config["transitive_helper_sha256"]:
        check_hash(
            resolve(helper["path"]),
            helper["sha256"],
            f"primary helper {helper['path']}",
        )
    anchor_root = resolve(primary_config["anchor_dir"])
    for name, expected in primary_config["anchor_sha256"].items():
        check_hash(anchor_root / name, expected, f"primary anchor {name}")
    calibration = resolve(primary_config["calibration_reference_run"]) / "infos.pkl"
    check_hash(
        calibration,
        primary_config["calibration_infos_sha256"],
        "primary calibration infos",
    )
    sparsedrive_root = resolve(primary_config["sparsedrive_root"])
    if git(sparsedrive_root, "rev-parse", "HEAD") != primary_config[
        "sparsedrive_commit"
    ]:
        raise ValueError("SparseDrive commit drift")
    if git_diff_sha256(sparsedrive_root) != primary_config[
        "sparsedrive_working_diff_sha256"
    ]:
        raise ValueError("SparseDrive working diff drift")
    if git(sparsedrive_root, "status", "--short").splitlines() != primary_config[
        "sparsedrive_status"
    ]:
        raise ValueError("SparseDrive status drift")


def verify_frozen_input(primary_result, window, report):
    result_windows = {
        item["window"]: item for item in primary_result["windows"]
    }
    if window["id"] not in result_windows:
        raise ValueError(f"{window['id']}: primary result window missing")
    result = result_windows[window["id"]]
    if result["current_receiver_report_sha256"] != window[
        "left_receiver_report_sha256"
    ]:
        raise ValueError(f"{window['id']}: primary receiver report binding drift")
    source = report["source"]
    if sha256(source["archive_manifest"]) != source["archive_manifest_sha256"]:
        raise ValueError(f"{window['id']}: live input manifest hash drift")
    if sha256(source["metadata"]) != source["metadata_sha256"]:
        raise ValueError(f"{window['id']}: live input metadata hash drift")
    if result["input_identity"]["manifest_sha256"] != source[
        "archive_manifest_sha256"
    ]:
        raise ValueError(f"{window['id']}: primary input manifest binding drift")
    rows = {
        (int(row["frame_index"]), row["camera"]): row
        for row in result["input_identity"]["rows"]
    }
    paths = {}
    for frame in report["baseline"]["frames"]:
        frame_index = int(frame["source_frame_index"])
        for camera in frame["input_contract"]["camera_inputs"]:
            paths[(frame_index, camera["camera"])] = Path(camera["image_path"])
    if set(rows) != set(paths) or len(rows) != 48:
        raise ValueError(f"{window['id']}: frozen input image key set drift")
    for key, path in paths.items():
        if sha256(path) != rows[key]["destination_sha256"]:
            raise ValueError(f"{window['id']}: frozen input image hash drift {key}")


def verify_execution_manifest(config, config_path, primary_config):
    manifest_path = resolve(config["execution_manifest"])
    manifest = load_json(manifest_path)
    if manifest["experiment_id"] != config["experiment_id"]:
        raise ValueError("execution manifest experiment drift")
    if manifest["status"] != "complete" or manifest["audit_status"]:
        raise ValueError("process-repeat execution did not complete cleanly")
    if manifest["config_sha256"] != sha256(config_path):
        raise ValueError("execution manifest config hash drift")
    if manifest["runner_script_sha256"] != config["runner_script_sha256"]:
        raise ValueError("execution manifest runner hash drift")
    for key in (
        "comparison_script_sha256",
        "diagnostic_helper_sha256",
        "primary_regression_sha256",
        "primary_native_diagnostic_sha256",
    ):
        if manifest[key] != config[key]:
            raise ValueError(f"execution manifest {key} drift")
    if manifest["gpu_driver_and_name"] != config["gpu_driver_and_name"]:
        raise ValueError("execution GPU/driver drift")
    if manifest["initial_assets"]["runtime_deps_tree"] != config[
        "runtime_deps_tree"
    ]:
        raise ValueError("execution initial runtime dependency tree drift")
    rows = {row["window"]: row for row in manifest["windows"]}
    if set(rows) != {window["id"] for window in config["windows"]}:
        raise ValueError("execution manifest window set drift")
    for window in config["windows"]:
        row = rows[window["id"]]
        if row["returncode"] != 0 or not row["input_unchanged"]:
            raise ValueError(f"{window['id']}: execution health/input gate failed")
        if row["command"] != build_receiver_command(primary_config, window):
            raise ValueError(f"{window['id']}: execution command drift")
        expected_environment = {
            "PYTHONPATH": str(resolve(primary_config["runtime_deps"])),
            "MPLCONFIGDIR": "/tmp/mpl-sparsedrive-receiver-process-repeat",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if row["environment"] != expected_environment:
            raise ValueError(f"{window['id']}: execution environment drift")
        expected_log = resolve(config["log_root"]) / f"{window['id']}.log"
        if Path(row["log"]).resolve() != expected_log:
            raise ValueError(f"{window['id']}: execution log path drift")
        if row["log_sha256"] != sha256(expected_log):
            raise ValueError(f"{window['id']}: execution log hash drift")
        if not (
            row["input_pre"]["all_images_exact"]
            and row["input_post"]["all_images_exact"]
            and row["input_pre"]["image_count"] == 48
            and row["input_post"]["image_count"] == 48
        ):
            raise ValueError(f"{window['id']}: execution image snapshot failed")
        if not (
            row["assets_pre"]["contract_passed"]
            and row["assets_post"]["contract_passed"]
            and row["assets_pre"] == row["assets_post"]
            and row["assets_pre"]["runtime_deps_tree"]
            == config["runtime_deps_tree"]
        ):
            raise ValueError(f"{window['id']}: execution asset snapshot failed")
        output_root = resolve(window["right_receiver_root"])
        report_path = output_root / "sparsedrive_real_source_qualification.json"
        native_path = output_root / "native_outputs.pt"
        if Path(row["receiver_report"]).resolve() != report_path:
            raise ValueError(f"{window['id']}: execution report path drift")
        if Path(row["native_outputs"]).resolve() != native_path:
            raise ValueError(f"{window['id']}: execution native path drift")
        if row["receiver_report_sha256"] != sha256(report_path):
            raise ValueError(f"{window['id']}: execution report hash drift")
        if row["native_outputs_sha256"] != sha256(native_path):
            raise ValueError(f"{window['id']}: execution native hash drift")
    return manifest_path, manifest


def compare_window(config, primary_config, primary_result, window):
    left_root = resolve(window["left_receiver_root"])
    right_root = resolve(window["right_receiver_root"])
    left_report_path = left_root / "sparsedrive_real_source_qualification.json"
    right_report_path = right_root / "sparsedrive_real_source_qualification.json"
    left_native_path = left_root / "native_outputs.pt"
    right_native_path = right_root / "native_outputs.pt"
    if sha256(left_report_path) != window["left_receiver_report_sha256"]:
        raise ValueError(f"{window['id']}: left receiver report hash drift")
    if sha256(left_native_path) != window["left_native_outputs_sha256"]:
        raise ValueError(f"{window['id']}: left native output hash drift")
    left_report = load_json(left_report_path)
    right_report = load_json(right_report_path)
    verify_frozen_input(primary_result, window, left_report)
    for section in IDENTITY_SECTIONS:
        if left_report[section] != right_report[section]:
            raise ValueError(f"{window['id']}: receiver {section} drift")
    if right_report["source"]["frame_indices"] != window["frames"]:
        raise ValueError(f"{window['id']}: right frame list drift")
    if not (
        right_report["qualification"]["all_native_outputs_finite"]
        and right_report["qualification"]["baseline_plans_non_degenerate"]
        and right_report["adapter"]["baseline_only"]
    ):
        raise ValueError(f"{window['id']}: right receiver health gate failed")
    if sha256(right_native_path) != right_report["artifacts"][
        "native_outputs_sha256"
    ]:
        raise ValueError(f"{window['id']}: right native output hash drift")
    for report, native_path, label in (
        (left_report, left_native_path, "left"),
        (right_report, right_native_path, "right"),
    ):
        if Path(report["artifacts"]["native_outputs"]).resolve() != native_path:
            raise ValueError(f"{window['id']}: {label} native output path drift")
        if sha256(native_path) != report["artifacts"]["native_outputs_sha256"]:
            raise ValueError(f"{window['id']}: {label} native output hash drift")
    report_comparison = compare_report_sequences(
        primary_config, window, left_report, right_report
    )
    left_native = torch.load(left_native_path, map_location="cpu")
    right_native = torch.load(right_native_path, map_location="cpu")
    native = native_result(primary_config, left_native, right_native)
    left_reset = recompute_reset_repeat(left_native)
    right_reset = recompute_reset_repeat(right_native)
    left_report_native = report_native_plan_difference(left_report, left_native)
    right_report_native = report_native_plan_difference(
        right_report, right_native
    )
    left_report_reset = abs(
        left_reset
        - float(
            left_report["qualification"][
                "baseline_repeat_max_abs_plan_difference_m"
            ]
        )
    )
    right_report_reset = abs(
        right_reset
        - float(
            right_report["qualification"][
                "baseline_repeat_max_abs_plan_difference_m"
            ]
        )
    )
    diagnostic_error = None
    try:
        id_aligned = id_aligned_detection_diagnostic(
            left_native, right_native, window["frames"]
        )
        top_detections = top_detection_diagnostic(left_report, right_report)
    except Exception as error:  # diagnostic must not suppress a primary failure result
        diagnostic_error = f"{type(error).__name__}: {error}"
        id_aligned = None
        top_detections = None
    plan_tolerance = float(primary_config["plan_max_abs_tolerance_m"])
    passed = all(
        (
            report_comparison["all_receiver_input_images_byte_exact"],
            report_comparison["all_input_contracts_equal_except_path"],
            report_comparison["all_selected_modes_and_commands_equal"],
            report_comparison["all_final_plans_within_tolerance"],
            native["passed"],
            left_reset <= plan_tolerance,
            right_reset <= plan_tolerance,
            left_report_native <= 1e-12,
            right_report_native <= 1e-12,
            left_report_reset <= 1e-12,
            right_report_reset <= 1e-12,
        )
    )
    return {
        "window": window["id"],
        "left_receiver_report": str(left_report_path),
        "left_receiver_report_sha256": sha256(left_report_path),
        "right_receiver_report": str(right_report_path),
        "right_receiver_report_sha256": sha256(right_report_path),
        "left_native_outputs": str(left_native_path),
        "left_native_outputs_sha256": sha256(left_native_path),
        "right_native_outputs": str(right_native_path),
        "right_native_outputs_sha256": sha256(right_native_path),
        "report_comparison": report_comparison,
        "native_direct_comparison": native,
        "id_aligned_detection": id_aligned,
        "top_detection_rank_comparison": top_detections,
        "diagnostic_error": diagnostic_error,
        "left_reset_max_abs_final_plan_difference_m": left_reset,
        "right_reset_max_abs_final_plan_difference_m": right_reset,
        "left_report_native_max_abs_plan_difference_m": left_report_native,
        "right_report_native_max_abs_plan_difference_m": right_report_native,
        "left_report_reset_metric_abs_difference_m": left_report_reset,
        "right_report_reset_metric_abs_difference_m": right_report_reset,
        "all_window_checks_passed": passed,
    }


def compare(config_path):
    config = load_json(config_path)
    if Path(sys.executable).resolve() != resolve(config["runtime_python"]):
        raise ValueError("wrong Python runtime")
    if resolve(config["comparison_script"]) != Path(__file__).resolve():
        raise ValueError("comparison script path drift")
    if sha256(Path(__file__).resolve()) != config["comparison_script_sha256"]:
        raise ValueError("comparison script hash drift")
    if sha256(resolve(config["primary_config"])) != config[
        "primary_config_sha256"
    ]:
        raise ValueError("primary config hash drift")
    if sha256(resolve(config["diagnostic_helper"])) != config[
        "diagnostic_helper_sha256"
    ]:
        raise ValueError("diagnostic helper hash drift")
    if sha256(resolve(config["primary_regression"])) != config[
        "primary_regression_sha256"
    ]:
        raise ValueError("primary regression hash drift")
    if sha256(resolve(config["primary_native_diagnostic"])) != config[
        "primary_native_diagnostic_sha256"
    ]:
        raise ValueError("primary native diagnostic hash drift")
    primary_result = load_json(resolve(config["primary_regression"]))
    primary_native_diagnostic = load_json(
        resolve(config["primary_native_diagnostic"])
    )
    if (
        primary_result["experiment_id"]
        != "fixed_trajectory_receiver_regression_001"
        or primary_result["summary"]["all_checks_passed"]
    ):
        raise ValueError("unexpected primary regression trigger state")
    if (
        not primary_native_diagnostic["outcome_informed"]
        or primary_native_diagnostic["primary_regression_sha256"]
        != config["primary_regression_sha256"]
    ):
        raise ValueError("primary native diagnostic binding drift")
    primary_config = load_json(resolve(config["primary_config"]))
    verify_live_primary_assets(primary_config)
    runtime_tree = directory_tree_sha256(resolve(primary_config["runtime_deps"]))
    if runtime_tree != config["runtime_deps_tree"]:
        raise ValueError("runtime dependency tree drift")
    execution_manifest_path, execution_manifest = verify_execution_manifest(
        config, config_path, primary_config
    )
    audit_status = git(ROOT, "status", "--short")
    if audit_status:
        raise ValueError(f"audit repository is not clean: {audit_status}")
    if execution_manifest["audit_commit"] != git(ROOT, "rev-parse", "HEAD"):
        raise ValueError("execution commit drift")
    windows = [
        compare_window(config, primary_config, primary_result, window)
        for window in config["windows"]
    ]
    summary = {
        "window_count": len(windows),
        "sequence_frame_comparison_count": sum(
            window["report_comparison"]["sequence_comparisons"]
            for window in windows
        ),
        "selected_mode_equal_count": sum(
            window["report_comparison"]["selected_mode_equal_count"]
            for window in windows
        ),
        "max_abs_final_plan_difference_m": max(
            window["report_comparison"]["max_abs_final_plan_difference_m"]
            for window in windows
        ),
        "max_abs_native_float_difference": max(
            window["native_direct_comparison"]["max_abs_float_difference"]
            for window in windows
        ),
        "native_integer_mismatch_count": sum(
            window["native_direct_comparison"]["integer_mismatch_count"]
            for window in windows
        ),
        "instance_id_rank_mismatch_count": (
            sum(
                window["id_aligned_detection"]["integer_rank_mismatch_count"]
                for window in windows
            )
            if all(window["id_aligned_detection"] is not None for window in windows)
            else None
        ),
        "max_right_reset_plan_difference_m": max(
            window["right_reset_max_abs_final_plan_difference_m"]
            for window in windows
        ),
        "all_checks_passed": all(
            window["all_window_checks_passed"] for window in windows
        ),
    }
    return {
        "experiment_id": config["experiment_id"],
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "outcome_informed": True,
        "config": str(Path(config_path).resolve()),
        "config_sha256": sha256(config_path),
        "comparison_script_sha256": sha256(Path(__file__).resolve()),
        "audit_commit": git(ROOT, "rev-parse", "HEAD"),
        "audit_status": audit_status,
        "execution_manifest": str(execution_manifest_path),
        "execution_manifest_sha256": sha256(execution_manifest_path),
        "gpu_driver_and_name": execution_manifest["gpu_driver_and_name"],
        "runtime_deps_tree": runtime_tree,
        "windows": windows,
        "summary": summary,
        "boundary": (
            "This current-to-current fresh-process diagnostic cannot change "
            "the rejected historical-to-current full-native claim or identify "
            "the component causing non-exact internal outputs."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    result = compare(args.config.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"summary": result["summary"]}, indent=2))
    return 0 if result["summary"]["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
