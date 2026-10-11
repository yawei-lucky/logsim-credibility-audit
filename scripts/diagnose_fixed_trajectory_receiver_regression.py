#!/usr/bin/env python3
"""Localize a failed full-native receiver regression without changing its gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from compare_fixed_trajectory_receiver_regression import (
    RUN_VARIANTS,
    compare_native_nodes,
    recompute_reset_repeat,
    resolve,
)


DETECTION_FIELDS = (
    "boxes_3d",
    "scores_3d",
    "labels_3d",
    "cls_scores",
    "instance_ids",
    "trajs_3d",
    "trajs_score",
    "anchor_queue",
    "period",
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text())


def numpy_value(value):
    if torch.is_tensor(value):
        return value.detach().cpu().numpy()
    if isinstance(value, np.ndarray):
        return value
    raise TypeError(type(value))


def compact_stats(stats):
    return {
        key: stats[key]
        for key in (
            "structure_equal",
            "structure_errors",
            "float_element_count",
            "float_exact_count",
            "float_changed_count",
            "float_all_finite",
            "max_abs_float_difference",
            "worst_float_path",
            "integer_element_count",
            "integer_mismatch_count",
            "other_scalar_count",
            "other_scalar_mismatch_count",
        )
    }


def direct_field_stats(historical, current):
    fields = historical["baseline"][0].keys()
    result = {}
    for field in fields:
        old = {
            variant: [frame[field] for frame in historical[variant]]
            for variant in RUN_VARIANTS
        }
        new = {
            variant: [frame[field] for frame in current[variant]]
            for variant in RUN_VARIANTS
        }
        result[field] = compact_stats(
            compare_native_nodes(old, new, path=field)
        )
    return result


def empty_aligned_stats():
    return {
        "element_count": 0,
        "changed_or_mismatch_count": 0,
        "max_abs_float_difference": 0.0,
        "sum_abs_float_difference": 0.0,
        "dtype": None,
        "all_finite": True,
    }


def update_aligned_stats(stats, historical, current):
    if historical.shape != current.shape or historical.dtype != current.dtype:
        raise ValueError("ID-aligned detection shape or dtype drift")
    stats["element_count"] += int(historical.size)
    stats["dtype"] = str(historical.dtype)
    if np.issubdtype(historical.dtype, np.floating):
        finite = bool(np.isfinite(historical).all() and np.isfinite(current).all())
        stats["all_finite"] = stats["all_finite"] and finite
        if not finite:
            raise ValueError("non-finite ID-aligned detection output")
        difference = np.abs(
            historical.astype(np.float64) - current.astype(np.float64)
        )
        stats["changed_or_mismatch_count"] += int(np.count_nonzero(difference))
        stats["sum_abs_float_difference"] += float(difference.sum())
        stats["max_abs_float_difference"] = max(
            stats["max_abs_float_difference"],
            float(difference.max()) if difference.size else 0.0,
        )
    else:
        stats["changed_or_mismatch_count"] += int(
            np.count_nonzero(historical != current)
        )


def id_aligned_detection_diagnostic(historical, current, frames):
    field_stats = {field: empty_aligned_stats() for field in DETECTION_FIELDS}
    mismatches = []
    identity_rows = []
    for variant in RUN_VARIANTS:
        for frame_index, old, new in zip(
            frames,
            historical[variant],
            current[variant],
            strict=True,
        ):
            old_ids = numpy_value(old["instance_ids"])
            new_ids = numpy_value(new["instance_ids"])
            old_unique = len(np.unique(old_ids)) == len(old_ids)
            new_unique = len(np.unique(new_ids)) == len(new_ids)
            same_set = set(old_ids.tolist()) == set(new_ids.tolist())
            differing_ranks = np.flatnonzero(old_ids != new_ids)
            identity_rows.append(
                {
                    "variant": variant,
                    "frame_index": frame_index,
                    "old_ids_unique": old_unique,
                    "new_ids_unique": new_unique,
                    "same_id_set": same_set,
                    "differing_rank_count": int(differing_ranks.size),
                }
            )
            for rank in differing_ranks:
                mismatches.append(
                    {
                        "variant": variant,
                        "frame_index": frame_index,
                        "rank": int(rank),
                        "historical_instance_id": int(old_ids[rank]),
                        "current_instance_id": int(new_ids[rank]),
                        "historical_label": int(
                            numpy_value(old["labels_3d"])[rank]
                        ),
                        "current_label": int(
                            numpy_value(new["labels_3d"])[rank]
                        ),
                        "historical_score": float(
                            numpy_value(old["scores_3d"])[rank]
                        ),
                        "current_score": float(
                            numpy_value(new["scores_3d"])[rank]
                        ),
                    }
                )
            if not (old_unique and new_unique and same_set):
                continue
            new_index = {int(value): index for index, value in enumerate(new_ids)}
            order = np.asarray([new_index[int(value)] for value in old_ids])
            for field in DETECTION_FIELDS:
                old_value = numpy_value(old[field])
                new_value = numpy_value(new[field])[order]
                update_aligned_stats(field_stats[field], old_value, new_value)
    for stats in field_stats.values():
        if stats["element_count"]:
            stats["mean_abs_float_difference"] = (
                stats.pop("sum_abs_float_difference") / stats["element_count"]
            )
        else:
            stats["mean_abs_float_difference"] = 0.0
            stats.pop("sum_abs_float_difference")
    mismatch_scores = [
        max(row["historical_score"], row["current_score"])
        for row in mismatches
    ]
    return {
        "frame_variant_count": len(identity_rows),
        "all_instance_id_vectors_unique": all(
            row["old_ids_unique"] and row["new_ids_unique"]
            for row in identity_rows
        ),
        "all_historical_current_id_sets_equal": all(
            row["same_id_set"] for row in identity_rows
        ),
        "integer_rank_mismatch_count": len(mismatches),
        "minimum_mismatch_rank": min(
            (row["rank"] for row in mismatches), default=None
        ),
        "maximum_score_at_mismatched_rank": max(mismatch_scores, default=None),
        "identity_rows": identity_rows,
        "integer_rank_mismatches": mismatches,
        "id_aligned_field_stats": field_stats,
    }


def top_detection_diagnostic(historical_report, current_report):
    rows = []
    for variant in RUN_VARIANTS:
        for old_frame, new_frame in zip(
            historical_report[variant]["frames"],
            current_report[variant]["frames"],
            strict=True,
        ):
            old_top = old_frame["native"]["top_detections"]
            new_top = new_frame["native"]["top_detections"]
            if len(old_top) != len(new_top):
                raise ValueError("top-detection count drift")
            for old, new in zip(old_top, new_top, strict=True):
                box_difference = np.abs(
                    np.asarray(old["box"], dtype=np.float64)
                    - np.asarray(new["box"], dtype=np.float64)
                )
                rows.append(
                    {
                        "variant": variant,
                        "frame_index": int(old_frame["source_frame_index"]),
                        "rank": int(old["rank"]),
                        "rank_equal": int(old["rank"]) == int(new["rank"]),
                        "label_equal": int(old["label_id"]) == int(new["label_id"]),
                        "score_abs_difference": abs(
                            float(old["score"]) - float(new["score"])
                        ),
                        "box_max_abs_difference": float(box_difference.max()),
                    }
                )
    return {
        "comparison_count": len(rows),
        "label_equal_count": sum(row["label_equal"] for row in rows),
        "rank_equal_count": sum(row["rank_equal"] for row in rows),
        "all_ranks_equal": all(row["rank_equal"] for row in rows),
        "all_labels_equal": all(row["label_equal"] for row in rows),
        "max_abs_score_difference": max(
            row["score_abs_difference"] for row in rows
        ),
        "max_abs_box_difference": max(
            row["box_max_abs_difference"] for row in rows
        ),
        "rows": rows,
    }


def reset_diagnostic(native):
    stats = compact_stats(
        compare_native_nodes(
            native["baseline"], native["baseline_repeat"], path="reset"
        )
    )
    stats["max_abs_final_plan_difference_m"] = recompute_reset_repeat(native)
    return stats


def diagnose(config_path, regression_path):
    config = load_json(config_path)
    regression = load_json(regression_path)
    if regression["summary"]["all_checks_passed"]:
        raise ValueError("native diagnostic is intended for a retained failed result")
    windows = []
    regression_windows = {
        window["window"]: window for window in regression["windows"]
    }
    for window in config["windows"]:
        historical_native_path = resolve(window["historical_native_outputs"])
        current_native_path = (
            resolve(window["current_receiver_root"]) / "native_outputs.pt"
        )
        current_report_path = (
            resolve(window["current_receiver_root"])
            / "sparsedrive_real_source_qualification.json"
        )
        historical_report_path = resolve(window["historical_receiver_report"])
        if sha256(historical_native_path) != window[
            "historical_native_outputs_sha256"
        ]:
            raise ValueError(f"{window['id']}: historical native hash drift")
        if window["id"] not in regression_windows:
            raise ValueError(f"{window['id']}: primary regression row missing")
        if sha256(current_native_path) != regression_windows[window["id"]][
            "current_native_outputs_sha256"
        ]:
            raise ValueError(f"{window['id']}: current native hash drift")
        historical = torch.load(historical_native_path, map_location="cpu")
        current = torch.load(current_native_path, map_location="cpu")
        historical_report = load_json(historical_report_path)
        current_report = load_json(current_report_path)
        windows.append(
            {
                "window": window["id"],
                "historical_native": str(historical_native_path),
                "historical_native_sha256": sha256(historical_native_path),
                "current_native": str(current_native_path),
                "current_native_sha256": sha256(current_native_path),
                "direct_field_stats": direct_field_stats(historical, current),
                "id_aligned_detection": id_aligned_detection_diagnostic(
                    historical, current, window["frames"]
                ),
                "top_detection_rank_comparison": top_detection_diagnostic(
                    historical_report, current_report
                ),
                "historical_reset_variation": reset_diagnostic(historical),
                "current_reset_variation": reset_diagnostic(current),
            }
        )
    return {
        "experiment_id": "fixed_trajectory_receiver_regression_001",
        "diagnostic": "outcome_informed_native_difference_localization",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "outcome_informed": True,
        "diagnostic_script": str(Path(__file__).resolve()),
        "diagnostic_script_sha256": sha256(Path(__file__).resolve()),
        "config": str(Path(config_path).resolve()),
        "config_sha256": sha256(config_path),
        "primary_regression": str(Path(regression_path).resolve()),
        "primary_regression_sha256": sha256(regression_path),
        "windows": windows,
        "boundary": (
            "This diagnostic localizes a retained failed full-native claim. "
            "Exact instance-ID alignment is descriptive and cannot replace the "
            "preregistered direct comparison or change its thresholds."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--regression", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    result = diagnose(args.config.resolve(), args.regression.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
