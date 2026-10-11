#!/usr/bin/env python3
"""Compare fresh SparseDrive outputs with frozen historical receiver outputs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CAMERAS = (
    "CAM_BACK",
    "CAM_BACK_LEFT",
    "CAM_BACK_RIGHT",
    "CAM_FRONT",
    "CAM_FRONT_LEFT",
    "CAM_FRONT_RIGHT",
)
RUN_VARIANTS = ("baseline", "baseline_repeat")


def resolve(path):
    path = Path(path).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text())


def check_hash(path, expected, label):
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"{label} hash mismatch: {actual} != {expected}")
    return actual


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True
    ).rstrip("\n")


def git_diff_sha256(repo):
    result = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "HEAD", "--binary"]
    )
    return hashlib.sha256(result).hexdigest()


def new_native_stats():
    return {
        "structure_equal": True,
        "structure_errors": [],
        "float_element_count": 0,
        "float_exact_count": 0,
        "float_changed_count": 0,
        "float_all_finite": True,
        "max_abs_float_difference": 0.0,
        "worst_float_path": None,
        "integer_element_count": 0,
        "integer_mismatch_count": 0,
        "other_scalar_count": 0,
        "other_scalar_mismatch_count": 0,
    }


def structure_error(stats, message):
    stats["structure_equal"] = False
    if len(stats["structure_errors"]) < 20:
        stats["structure_errors"].append(message)


def compare_arrays(first, second, path, stats):
    if first.shape != second.shape:
        structure_error(stats, f"{path}: shape {first.shape} != {second.shape}")
        return
    if first.dtype != second.dtype:
        structure_error(stats, f"{path}: dtype {first.dtype} != {second.dtype}")
        return
    if np.issubdtype(first.dtype, np.floating):
        stats["float_element_count"] += int(first.size)
        finite = bool(np.isfinite(first).all() and np.isfinite(second).all())
        stats["float_all_finite"] = stats["float_all_finite"] and finite
        if not finite:
            structure_error(stats, f"{path}: non-finite float value")
            return
        difference = np.abs(first.astype(np.float64) - second.astype(np.float64))
        changed = int(np.count_nonzero(difference))
        stats["float_changed_count"] += changed
        stats["float_exact_count"] += int(first.size) - changed
        maximum = float(difference.max()) if difference.size else 0.0
        if maximum > stats["max_abs_float_difference"]:
            stats["max_abs_float_difference"] = maximum
            stats["worst_float_path"] = path
    elif np.issubdtype(first.dtype, np.integer) or np.issubdtype(
        first.dtype, np.bool_
    ):
        stats["integer_element_count"] += int(first.size)
        stats["integer_mismatch_count"] += int(np.count_nonzero(first != second))
    else:
        if not np.array_equal(first, second):
            structure_error(stats, f"{path}: unsupported array values differ")


def compare_native_nodes(first, second, path="root", stats=None):
    if stats is None:
        stats = new_native_stats()
    try:
        import torch
    except ImportError:
        torch = None
    first_tensor = torch is not None and torch.is_tensor(first)
    second_tensor = torch is not None and torch.is_tensor(second)
    if first_tensor or second_tensor:
        if not (first_tensor and second_tensor):
            structure_error(stats, f"{path}: tensor/container type differs")
            return stats
        if type(first) is not type(second):
            structure_error(stats, f"{path}: tensor type differs")
            return stats
        compare_arrays(first.detach().cpu().numpy(), second.detach().cpu().numpy(), path, stats)
        return stats
    if isinstance(first, np.ndarray) or isinstance(second, np.ndarray):
        if not (isinstance(first, np.ndarray) and isinstance(second, np.ndarray)):
            structure_error(stats, f"{path}: ndarray/container type differs")
            return stats
        compare_arrays(first, second, path, stats)
        return stats
    if isinstance(first, dict) or isinstance(second, dict):
        if not (isinstance(first, dict) and isinstance(second, dict)):
            structure_error(stats, f"{path}: mapping/container type differs")
            return stats
        if type(first) is not type(second):
            structure_error(stats, f"{path}: mapping type differs")
            return stats
        if set(first) != set(second):
            structure_error(stats, f"{path}: mapping keys differ")
            return stats
        for key in sorted(first):
            compare_native_nodes(first[key], second[key], f"{path}.{key}", stats)
        return stats
    if isinstance(first, (list, tuple)) or isinstance(second, (list, tuple)):
        if type(first) is not type(second):
            structure_error(stats, f"{path}: sequence type differs")
            return stats
        if len(first) != len(second):
            structure_error(stats, f"{path}: sequence length differs")
            return stats
        for index, (left, right) in enumerate(zip(first, second, strict=True)):
            compare_native_nodes(left, right, f"{path}[{index}]", stats)
        return stats
    if isinstance(first, (float, np.floating)) or isinstance(
        second, (float, np.floating)
    ):
        if not (
            isinstance(first, (float, np.floating))
            and isinstance(second, (float, np.floating))
        ):
            structure_error(stats, f"{path}: float/scalar type differs")
            return stats
        if type(first) is not type(second):
            structure_error(stats, f"{path}: float scalar dtype differs")
            return stats
        stats["float_element_count"] += 1
        finite = math.isfinite(float(first)) and math.isfinite(float(second))
        stats["float_all_finite"] = stats["float_all_finite"] and finite
        if not finite:
            structure_error(stats, f"{path}: non-finite scalar")
            return stats
        difference = abs(float(first) - float(second))
        stats["float_exact_count"] += difference == 0
        stats["float_changed_count"] += difference != 0
        if difference > stats["max_abs_float_difference"]:
            stats["max_abs_float_difference"] = difference
            stats["worst_float_path"] = path
        return stats
    if isinstance(first, (int, bool, np.integer, np.bool_)) or isinstance(
        second, (int, bool, np.integer, np.bool_)
    ):
        first_is_bool = isinstance(first, (bool, np.bool_))
        second_is_bool = isinstance(second, (bool, np.bool_))
        first_is_integer = isinstance(first, (int, np.integer)) and not first_is_bool
        second_is_integer = isinstance(second, (int, np.integer)) and not second_is_bool
        if not (
            (first_is_bool and second_is_bool)
            or (first_is_integer and second_is_integer)
        ):
            structure_error(stats, f"{path}: integer/scalar type differs")
            return stats
        if type(first) is not type(second):
            structure_error(stats, f"{path}: integer scalar dtype differs")
            return stats
        stats["integer_element_count"] += 1
        stats["integer_mismatch_count"] += int(first != second)
        return stats
    if type(first) is not type(second):
        structure_error(stats, f"{path}: scalar type differs")
        return stats
    stats["other_scalar_count"] += 1
    stats["other_scalar_mismatch_count"] += int(first != second)
    return stats


def image_keyed_paths(report):
    indexed = {}
    for variant in RUN_VARIANTS:
        for frame in report[variant]["frames"]:
            frame_index = int(frame["source_frame_index"])
            for camera in frame["input_contract"]["camera_inputs"]:
                key = (variant, frame_index, camera["camera"])
                if key in indexed:
                    raise ValueError(f"duplicate receiver image key: {key}")
                indexed[key] = Path(camera["image_path"])
    return indexed


def normalized_input_contract(contract):
    normalized = copy.deepcopy(contract)
    for camera in normalized["camera_inputs"]:
        camera["image_path"] = f"<IMAGE>/{camera['camera']}"
    return normalized


def verify_report_identity(cfg, report, label):
    if report["model"]["checkpoint_sha256"] != cfg["checkpoint_sha256"]:
        raise ValueError(f"{label}: checkpoint drift")
    if report["model"]["config_sha256"] != cfg["model_config_sha256"]:
        raise ValueError(f"{label}: model config drift")
    if report["adapter"]["sha256"] != cfg["receiver_adapter_sha256"]:
        raise ValueError(f"{label}: receiver adapter drift")
    if report["receiver_source"]["commit"] != cfg["sparsedrive_commit"]:
        raise ValueError(f"{label}: SparseDrive commit drift")
    if (
        report["receiver_source"]["working_diff_sha256"]
        != cfg["sparsedrive_working_diff_sha256"]
    ):
        raise ValueError(f"{label}: SparseDrive working diff drift")
    if not report["qualification"]["all_native_outputs_finite"]:
        raise ValueError(f"{label}: non-finite native output")
    if not report["qualification"]["baseline_plans_non_degenerate"]:
        raise ValueError(f"{label}: degenerate baseline plan")


def verify_current_report_source(cfg, window, report, input_root):
    manifest_path = input_root / "assembled_render_manifest.json"
    metadata_path = input_root / "metadata_exact_pose_window.json"
    source = report["source"]
    expected_paths = {
        "root": input_root,
        "metadata": metadata_path,
        "archive_manifest": manifest_path,
        "metadata_archive_manifest": resolve(cfg["metadata_archive_manifest"]),
    }
    for key, expected in expected_paths.items():
        if Path(source[key]).resolve() != expected:
            raise ValueError(
                f"{window['id']}: current receiver used the wrong source {key}"
            )
    expected_hashes = {
        "metadata_sha256": sha256(metadata_path),
        "archive_manifest_sha256": sha256(manifest_path),
        "metadata_archive_manifest_sha256": cfg[
            "metadata_archive_manifest_sha256"
        ],
    }
    for key, expected in expected_hashes.items():
        if source[key] != expected:
            raise ValueError(f"{window['id']}: current receiver {key} drift")
    if source["frame_indices"] != window["frames"]:
        raise ValueError(f"{window['id']}: current receiver frame list drift")
    if not report["adapter"]["baseline_only"]:
        raise ValueError(f"{window['id']}: current receiver was not baseline-only")


def verify_historical_audit_inputs(window, historical_audit):
    inputs = historical_audit["inputs"]
    expected = {
        "real_report_sha256": window["real_receiver_report_sha256"],
        "sim_report_sha256": window["historical_receiver_report_sha256"],
    }
    for key, value in expected.items():
        if inputs[key] != value:
            raise ValueError(f"{window['id']}: historical audit {key} drift")
    if not all(historical_audit["held_fixed_gate"].values()):
        raise ValueError(f"{window['id']}: historical held-fixed gate did not pass")


def verify_assembled_input(cfg, window, upstream_rows):
    current_root = resolve(window["current_input_root"])
    current_render_root = resolve(window["current_render_root"])
    historical_root = resolve(window["historical_input_root"])
    manifest_path = current_root / "assembled_render_manifest.json"
    metadata_path = current_root / "metadata_exact_pose_window.json"
    manifest = load_json(manifest_path)
    if manifest["frame_indices"] != window["frames"]:
        raise ValueError(f"{window['id']}: assembled frame list drift")
    if manifest["camera_order"] != list(CAMERAS):
        raise ValueError(f"{window['id']}: assembled camera order drift")
    if manifest["copied_image_count"] != 48 or manifest["variant"] != "factual":
        raise ValueError(f"{window['id']}: assembled image contract incomplete")
    if manifest["metadata_source_sha256"] != cfg["source_metadata_sha256"]:
        raise ValueError(f"{window['id']}: assembled metadata source drift")
    if Path(manifest["metadata_source"]).resolve() != resolve(cfg["source_metadata"]):
        raise ValueError(f"{window['id']}: assembled metadata source path drift")
    if Path(manifest["output_metadata"]).resolve() != metadata_path.resolve():
        raise ValueError(f"{window['id']}: assembled output metadata path drift")
    if manifest["output_metadata_sha256"] != sha256(metadata_path):
        raise ValueError(f"{window['id']}: assembled output metadata hash drift")
    historical_manifest = historical_root / "assembled_render_manifest.json"
    check_hash(
        historical_manifest,
        window["historical_input_manifest_sha256"],
        f"{window['id']} historical input manifest",
    )
    if sha256(metadata_path) != sha256(
        historical_root / "metadata_exact_pose_window.json"
    ):
        raise ValueError(f"{window['id']}: assembled metadata differs from historical")
    rows = []
    for item in manifest["images"]:
        frame = int(item["frame_index"])
        camera = item["camera"]
        key = (window["id"], frame, camera)
        if key not in upstream_rows:
            raise ValueError(f"{window['id']}: missing upstream row {key}")
        upstream = upstream_rows[key]
        expected_source = (
            current_render_root
            / f"frame_{frame:05d}"
            / "factual"
            / f"{camera}.png"
        ).resolve()
        expected_destination = (
            current_root / "images" / camera / f"{frame:05d}.png"
        ).resolve()
        source = Path(item["source"]).resolve()
        destination = Path(item["destination"]).resolve()
        historical = historical_root / "images" / camera / f"{frame:05d}.png"
        if source != expected_source or Path(upstream["left_path"]).resolve() != source:
            raise ValueError(f"{window['id']}: assembled source path drift for {key}")
        if destination != expected_destination:
            raise ValueError(f"{window['id']}: assembled destination path drift for {key}")
        if Path(upstream["golden_path"]).resolve() != historical.resolve():
            raise ValueError(f"{window['id']}: upstream golden path drift for {key}")
        source_hash = check_hash(source, item["source_sha256"], "current render")
        destination_hash = check_hash(
            destination, item["destination_sha256"], "assembled current render"
        )
        historical_hash = sha256(historical)
        if source_hash != upstream["left_sha256"]:
            raise ValueError(f"{window['id']}: upstream source hash drift for {key}")
        if historical_hash != upstream["golden_sha256"]:
            raise ValueError(f"{window['id']}: upstream golden hash drift for {key}")
        if not (
            upstream["run_to_run"]["png_byte_exact"]
            and upstream["left_to_golden"]["png_byte_exact"]
        ):
            raise ValueError(f"{window['id']}: upstream exactness gate failed for {key}")
        rows.append(
            {
                "frame_index": frame,
                "camera": camera,
                "source_sha256": source_hash,
                "destination_sha256": destination_hash,
                "historical_sha256": historical_hash,
                "source_copy_exact": source_hash == destination_hash,
                "historical_byte_exact": destination_hash == historical_hash,
            }
        )
    if len(rows) != 48 or len({(row["frame_index"], row["camera"]) for row in rows}) != 48:
        raise ValueError(f"{window['id']}: assembled image key set incomplete")
    return {
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "metadata_sha256": sha256(metadata_path),
        "image_count": len(rows),
        "source_copy_exact_count": sum(row["source_copy_exact"] for row in rows),
        "historical_byte_exact_count": sum(
            row["historical_byte_exact"] for row in rows
        ),
        "all_source_copies_exact": all(row["source_copy_exact"] for row in rows),
        "all_historical_images_byte_exact": all(
            row["historical_byte_exact"] for row in rows
        ),
        "rows": rows,
    }


def native_final_plan(native_frame):
    value = native_frame["final_planning"]
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    value = np.asarray(value, dtype=np.float64)
    if value.shape != (6, 2) or not np.isfinite(value).all():
        raise ValueError(f"invalid native final plan: shape={value.shape}")
    return value


def recompute_reset_repeat(native_outputs):
    baseline = native_outputs.get("baseline")
    repeated = native_outputs.get("baseline_repeat")
    if not isinstance(baseline, list) or not isinstance(repeated, list):
        raise ValueError("native outputs lack baseline/reset lists")
    if len(baseline) != 8 or len(repeated) != 8:
        raise ValueError("native baseline/reset frame count drift")
    return max(
        float(
            np.max(
                np.abs(native_final_plan(left) - native_final_plan(right))
            )
        )
        for left, right in zip(baseline, repeated, strict=True)
    )


def report_native_plan_difference(report, native_outputs):
    maximum = 0.0
    for variant in RUN_VARIANTS:
        report_frames = report[variant]["frames"]
        native_frames = native_outputs[variant]
        if len(report_frames) != len(native_frames):
            raise ValueError(f"{variant}: report/native frame count drift")
        for report_frame, native_frame in zip(
            report_frames, native_frames, strict=True
        ):
            report_plan = np.asarray(
                report_frame["native"]["final_planning_values"],
                dtype=np.float64,
            )
            difference = np.max(
                np.abs(report_plan - native_final_plan(native_frame))
            )
            maximum = max(maximum, float(difference))
    return maximum


def compare_report_sequences(cfg, window, historical, current):
    tolerance = float(cfg["plan_max_abs_tolerance_m"])
    historical_images = image_keyed_paths(historical)
    current_images = image_keyed_paths(current)
    if set(historical_images) != set(current_images):
        raise ValueError(f"{window['id']}: receiver image key sets differ")
    image_rows = []
    for key in sorted(historical_images):
        old_hash = sha256(historical_images[key])
        new_hash = sha256(current_images[key])
        image_rows.append(
            {
                "variant": key[0],
                "frame_index": key[1],
                "camera": key[2],
                "historical_sha256": old_hash,
                "current_sha256": new_hash,
                "byte_exact": old_hash == new_hash,
            }
        )
    rows = []
    for variant in RUN_VARIANTS:
        old_frames = historical[variant]["frames"]
        new_frames = current[variant]["frames"]
        if len(old_frames) != len(window["frames"]) or len(new_frames) != len(
            window["frames"]
        ):
            raise ValueError(f"{window['id']}/{variant}: frame count drift")
        for expected_frame, old, new in zip(
            window["frames"], old_frames, new_frames, strict=True
        ):
            if int(old["source_frame_index"]) != expected_frame or int(
                new["source_frame_index"]
            ) != expected_frame:
                raise ValueError(f"{window['id']}/{variant}: frame identity drift")
            if float(old["timestamp_s"]) != float(new["timestamp_s"]):
                raise ValueError(f"{window['id']}/{variant}/{expected_frame}: timestamp drift")
            input_contract_equal = normalized_input_contract(
                old["input_contract"]
            ) == normalized_input_contract(new["input_contract"])
            old_plan = np.asarray(
                old["native"]["final_planning_values"], dtype=np.float64
            )
            new_plan = np.asarray(
                new["native"]["final_planning_values"], dtype=np.float64
            )
            if old_plan.shape != (6, 2) or new_plan.shape != (6, 2):
                raise ValueError(
                    f"{window['id']}/{variant}/{expected_frame}: final plan shape drift"
                )
            difference = np.abs(old_plan - new_plan)
            mode_equal = old["planning_selection"] == new["planning_selection"]
            rows.append(
                {
                    "variant": variant,
                    "frame_index": expected_frame,
                    "input_contract_equal_except_image_path": input_contract_equal,
                    "selected_mode_and_command_equal": mode_equal,
                    "final_plan_max_abs_m": float(difference.max()),
                    "final_plan_ade_m": float(
                        np.mean(np.linalg.norm(old_plan - new_plan, axis=1))
                    ),
                    "within_plan_tolerance": float(difference.max()) <= tolerance,
                }
            )
    return {
        "image_comparisons": len(image_rows),
        "image_byte_exact_count": sum(row["byte_exact"] for row in image_rows),
        "all_receiver_input_images_byte_exact": all(
            row["byte_exact"] for row in image_rows
        ),
        "sequence_comparisons": len(rows),
        "input_contract_equal_count": sum(
            row["input_contract_equal_except_image_path"] for row in rows
        ),
        "selected_mode_equal_count": sum(
            row["selected_mode_and_command_equal"] for row in rows
        ),
        "max_abs_final_plan_difference_m": max(
            row["final_plan_max_abs_m"] for row in rows
        ),
        "max_plan_ade_m": max(row["final_plan_ade_m"] for row in rows),
        "all_final_plans_within_tolerance": all(
            row["within_plan_tolerance"] for row in rows
        ),
        "all_input_contracts_equal_except_path": all(
            row["input_contract_equal_except_image_path"] for row in rows
        ),
        "all_selected_modes_and_commands_equal": all(
            row["selected_mode_and_command_equal"] for row in rows
        ),
        "rows": rows,
    }


def domain_row(real_frame, sim_frame, history_depth):
    real_plan = np.asarray(
        real_frame["native"]["final_planning_values"], dtype=np.float64
    )
    sim_plan = np.asarray(
        sim_frame["native"]["final_planning_values"], dtype=np.float64
    )
    delta = sim_plan - real_plan
    distance = np.linalg.norm(delta, axis=1)
    return {
        "source_frame_index": int(real_frame["source_frame_index"]),
        "history_depth_in_this_reset": history_depth,
        "fully_warmed_four_frame_history": history_depth >= 4,
        "plan_domain_ade_m": float(np.mean(distance)),
        "plan_domain_fde_m": float(distance[-1]),
        "final_right_delta_sim_minus_real_m": float(delta[-1, 0]),
        "final_forward_delta_sim_minus_real_m": float(delta[-1, 1]),
        "real_selected_mode": int(
            real_frame["planning_selection"]["selected_mode_index"]
        ),
        "sim_selected_mode": int(
            sim_frame["planning_selection"]["selected_mode_index"]
        ),
    }


def compare_domain_audit(cfg, window, real, current, historical_audit):
    tolerance = float(cfg["domain_metric_max_abs_tolerance_m"])
    historical_rows = {
        int(row["source_frame_index"]): row
        for row in historical_audit["plan_domain_rows"]
    }
    if set(historical_rows) != set(window["frames"]):
        raise ValueError(f"{window['id']}: historical domain row set drift")
    rows = []
    for index, (real_frame, sim_frame) in enumerate(
        zip(real["baseline"]["frames"], current["baseline"]["frames"], strict=True),
        start=1,
    ):
        expected_frame = window["frames"][index - 1]
        if int(real_frame["source_frame_index"]) != expected_frame or int(
            sim_frame["source_frame_index"]
        ) != expected_frame:
            raise ValueError(f"{window['id']}: real/sim frame identity drift")
        if float(real_frame["timestamp_s"]) != float(sim_frame["timestamp_s"]):
            raise ValueError(f"{window['id']}/{expected_frame}: real/sim time drift")
        if normalized_input_contract(
            real_frame["input_contract"]
        ) != normalized_input_contract(sim_frame["input_contract"]):
            raise ValueError(
                f"{window['id']}/{expected_frame}: held-fixed real/sim contract drift"
            )
        row = domain_row(real_frame, sim_frame, index)
        expected = historical_rows[row["source_frame_index"]]
        fields = (
            "plan_domain_ade_m",
            "plan_domain_fde_m",
            "final_right_delta_sim_minus_real_m",
            "final_forward_delta_sim_minus_real_m",
        )
        differences = {
            field: abs(float(row[field]) - float(expected[field])) for field in fields
        }
        row["historical_metric_abs_differences"] = differences
        row["historical_modes_equal"] = (
            row["real_selected_mode"] == int(expected["real_selected_mode"])
            and row["sim_selected_mode"] == int(expected["sim_selected_mode"])
        )
        row["within_domain_metric_tolerance"] = max(differences.values()) <= tolerance
        rows.append(row)
    warmed = [row for row in rows if row["fully_warmed_four_frame_history"]]
    return {
        "row_count": len(rows),
        "warmed_row_count": len(warmed),
        "max_abs_domain_metric_difference_m": max(
            value
            for row in rows
            for value in row["historical_metric_abs_differences"].values()
        ),
        "all_modes_equal_to_historical_audit": all(
            row["historical_modes_equal"] for row in rows
        ),
        "all_domain_metrics_within_tolerance": all(
            row["within_domain_metric_tolerance"] for row in rows
        ),
        "rows": rows,
    }


def compare_window(cfg, window, upstream_rows):
    input_identity = verify_assembled_input(cfg, window, upstream_rows)
    historical_report_path = resolve(window["historical_receiver_report"])
    historical_native_path = resolve(window["historical_native_outputs"])
    real_report_path = resolve(window["real_receiver_report"])
    historical_audit_path = resolve(window["historical_real_sim_audit"])
    check_hash(
        historical_report_path,
        window["historical_receiver_report_sha256"],
        f"{window['id']} historical receiver report",
    )
    check_hash(
        historical_native_path,
        window["historical_native_outputs_sha256"],
        f"{window['id']} historical native output",
    )
    check_hash(
        real_report_path,
        window["real_receiver_report_sha256"],
        f"{window['id']} real receiver report",
    )
    check_hash(
        historical_audit_path,
        window["historical_real_sim_audit_sha256"],
        f"{window['id']} historical real-sim audit",
    )
    current_root = resolve(window["current_receiver_root"])
    current_report_path = current_root / "sparsedrive_real_source_qualification.json"
    current_native_path = current_root / "native_outputs.pt"
    historical = load_json(historical_report_path)
    current = load_json(current_report_path)
    real = load_json(real_report_path)
    historical_audit = load_json(historical_audit_path)
    verify_report_identity(cfg, historical, f"{window['id']} historical")
    verify_report_identity(cfg, current, f"{window['id']} current")
    verify_report_identity(cfg, real, f"{window['id']} real")
    for section in (
        "model",
        "receiver_source",
        "adapter",
        "calibration",
        "ego_and_reference",
    ):
        if current[section] != historical[section]:
            raise ValueError(
                f"{window['id']}: current/historical receiver {section} drift"
            )
    current_input_root = resolve(window["current_input_root"])
    verify_current_report_source(cfg, window, current, current_input_root)
    verify_historical_audit_inputs(window, historical_audit)
    if sha256(current_native_path) != current["artifacts"]["native_outputs_sha256"]:
        raise ValueError(f"{window['id']}: current native output hash drift")
    if sha256(historical_native_path) != historical["artifacts"][
        "native_outputs_sha256"
    ]:
        raise ValueError(f"{window['id']}: historical native output hash drift")
    report_comparison = compare_report_sequences(
        cfg, window, historical, current
    )
    import torch

    historical_native = torch.load(historical_native_path, map_location="cpu")
    current_native = torch.load(current_native_path, map_location="cpu")
    native_stats = compare_native_nodes(historical_native, current_native)
    native_stats["within_float_tolerance"] = (
        native_stats["max_abs_float_difference"]
        <= float(cfg["native_float_max_abs_tolerance"])
    )
    native_stats["all_integer_outputs_exact"] = (
        native_stats["integer_mismatch_count"] == 0
    )
    native_stats["all_other_scalars_exact"] = (
        native_stats["other_scalar_mismatch_count"] == 0
    )
    native_stats["passed"] = all(
        (
            native_stats["structure_equal"],
            native_stats["float_all_finite"],
            native_stats["within_float_tolerance"],
            native_stats["all_integer_outputs_exact"],
            native_stats["all_other_scalars_exact"],
        )
    )
    domain = compare_domain_audit(
        cfg, window, real, current, historical_audit
    )
    reported_fresh_repeat = float(
        current["qualification"]["baseline_repeat_max_abs_plan_difference_m"]
    )
    fresh_repeat = recompute_reset_repeat(current_native)
    repeat_report_abs_difference = abs(fresh_repeat - reported_fresh_repeat)
    report_native_max_abs_plan_difference = report_native_plan_difference(
        current, current_native
    )
    passed = all(
        (
            input_identity["all_source_copies_exact"],
            input_identity["all_historical_images_byte_exact"],
            report_comparison["all_receiver_input_images_byte_exact"],
            report_comparison["all_input_contracts_equal_except_path"],
            report_comparison["all_selected_modes_and_commands_equal"],
            report_comparison["all_final_plans_within_tolerance"],
            native_stats["passed"],
            fresh_repeat <= float(cfg["plan_max_abs_tolerance_m"]),
            repeat_report_abs_difference <= 1e-12,
            report_native_max_abs_plan_difference <= 1e-12,
            domain["all_modes_equal_to_historical_audit"],
            domain["all_domain_metrics_within_tolerance"],
        )
    )
    return {
        "window": window["id"],
        "input_identity": input_identity,
        "current_receiver_report": str(current_report_path),
        "current_receiver_report_sha256": sha256(current_report_path),
        "current_native_outputs": str(current_native_path),
        "current_native_outputs_sha256": sha256(current_native_path),
        "reported_fresh_reset_repeat_max_abs_plan_difference_m": reported_fresh_repeat,
        "fresh_reset_repeat_max_abs_plan_difference_m": fresh_repeat,
        "fresh_reset_repeat_report_abs_difference_m": repeat_report_abs_difference,
        "report_native_max_abs_plan_difference_m": report_native_max_abs_plan_difference,
        "fresh_reset_repeat_within_tolerance": fresh_repeat
        <= float(cfg["plan_max_abs_tolerance_m"]),
        "historical_to_current_report": report_comparison,
        "historical_to_current_native": native_stats,
        "real_sim_domain_regression": domain,
        "all_window_checks_passed": passed,
    }


def run(config_path):
    cfg = load_json(config_path)
    if Path(sys.executable).resolve() != resolve(cfg["runtime_python"]):
        raise ValueError(
            f"wrong Python runtime: {Path(sys.executable).resolve()} != "
            f"{resolve(cfg['runtime_python'])}"
        )
    check_hash(
        resolve(cfg["comparison_script"]),
        cfg["comparison_script_sha256"],
        "comparison script",
    )
    check_hash(
        resolve(cfg["current_render_comparison"]),
        cfg["current_render_comparison_sha256"],
        "current render comparison",
    )
    render_comparison = load_json(resolve(cfg["current_render_comparison"]))
    if not (
        render_comparison["all_current_repeat_checks_passed"]
        and render_comparison["all_golden_regression_checks_passed"]
    ):
        raise ValueError("upstream RGB regression did not pass")
    upstream_rows = {}
    for row in render_comparison["rows"]:
        key = (row["window"], int(row["frame_index"]), row["camera"])
        if key in upstream_rows:
            raise ValueError(f"duplicate upstream RGB row: {key}")
        upstream_rows[key] = row
    expected_upstream_keys = {
        (window["id"], frame, camera)
        for window in cfg["windows"]
        for frame in window["frames"]
        for camera in CAMERAS
    }
    if set(upstream_rows) != expected_upstream_keys:
        raise ValueError("upstream RGB comparison key set drift")
    for path_key, hash_key in (
        ("source_metadata", "source_metadata_sha256"),
        ("metadata_archive_manifest", "metadata_archive_manifest_sha256"),
        ("assembly_script", "assembly_script_sha256"),
        ("receiver_adapter", "receiver_adapter_sha256"),
        ("checkpoint", "checkpoint_sha256"),
        ("model_config", "model_config_sha256"),
    ):
        check_hash(resolve(cfg[path_key]), cfg[hash_key], path_key)
    for helper in cfg["transitive_helper_sha256"]:
        check_hash(
            resolve(helper["path"]), helper["sha256"], f"helper {helper['path']}"
        )
    anchor_root = resolve(cfg["anchor_dir"])
    for name, expected in cfg["anchor_sha256"].items():
        check_hash(anchor_root / name, expected, f"anchor {name}")
    calibration = resolve(cfg["calibration_reference_run"]) / "infos.pkl"
    check_hash(calibration, cfg["calibration_infos_sha256"], "calibration infos")
    sparsedrive_root = resolve(cfg["sparsedrive_root"])
    if git(sparsedrive_root, "rev-parse", "HEAD") != cfg["sparsedrive_commit"]:
        raise ValueError("SparseDrive commit drift")
    if git_diff_sha256(sparsedrive_root) != cfg["sparsedrive_working_diff_sha256"]:
        raise ValueError("SparseDrive working diff drift")
    if git(sparsedrive_root, "status", "--short").splitlines() != cfg[
        "sparsedrive_status"
    ]:
        raise ValueError("SparseDrive status drift")
    audit_status = git(ROOT, "status", "--short")
    if audit_status:
        raise ValueError(f"audit repository is not clean: {audit_status}")
    windows = [
        compare_window(cfg, window, upstream_rows) for window in cfg["windows"]
    ]
    summary = {
        "window_count": len(windows),
        "frame_count": sum(len(window["frames"]) for window in cfg["windows"]),
        "unique_rgb_count": sum(
            window["input_identity"]["image_count"] for window in windows
        ),
        "unique_rgb_byte_exact_count": sum(
            window["input_identity"]["historical_byte_exact_count"]
            for window in windows
        ),
        "receiver_sequence_comparison_count": sum(
            window["historical_to_current_report"]["sequence_comparisons"]
            for window in windows
        ),
        "selected_mode_equal_count": sum(
            window["historical_to_current_report"]["selected_mode_equal_count"]
            for window in windows
        ),
        "max_abs_final_plan_difference_m": max(
            window["historical_to_current_report"][
                "max_abs_final_plan_difference_m"
            ]
            for window in windows
        ),
        "max_abs_native_float_difference": max(
            window["historical_to_current_native"][
                "max_abs_float_difference"
            ]
            for window in windows
        ),
        "native_integer_mismatch_count": sum(
            window["historical_to_current_native"]["integer_mismatch_count"]
            for window in windows
        ),
        "max_fresh_reset_repeat_difference_m": max(
            window["fresh_reset_repeat_max_abs_plan_difference_m"]
            for window in windows
        ),
        "domain_row_count": sum(
            window["real_sim_domain_regression"]["row_count"]
            for window in windows
        ),
        "warmed_domain_row_count": sum(
            window["real_sim_domain_regression"]["warmed_row_count"]
            for window in windows
        ),
        "max_abs_domain_metric_difference_m": max(
            window["real_sim_domain_regression"][
                "max_abs_domain_metric_difference_m"
            ]
            for window in windows
        ),
        "all_checks_passed": all(
            window["all_window_checks_passed"] for window in windows
        ),
    }
    return {
        "experiment_id": cfg["experiment_id"],
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(Path(config_path).resolve()),
        "config_sha256": sha256(config_path),
        "comparison_script_sha256": sha256(Path(__file__).resolve()),
        "python": sys.executable,
        "audit_commit": git(ROOT, "rev-parse", "HEAD"),
        "audit_status": audit_status,
        "sparsedrive_commit": cfg["sparsedrive_commit"],
        "sparsedrive_working_diff_sha256": cfg["sparsedrive_working_diff_sha256"],
        "tolerances": {
            key: cfg[key]
            for key in (
                "plan_max_abs_tolerance_m",
                "native_float_max_abs_tolerance",
                "domain_metric_max_abs_tolerance_m",
            )
        },
        "windows": windows,
        "summary": summary,
        "claim_boundary": (
            "This release regression tests numeric reproducibility of one frozen "
            "SparseDrive receiver on byte-identical simulated RGB in two windows. "
            "It does not add real-sim equivalence or AD-correctness evidence."
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
    result = run(args.config.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"summary": result["summary"]}, indent=2))
    return 0 if result["summary"]["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
