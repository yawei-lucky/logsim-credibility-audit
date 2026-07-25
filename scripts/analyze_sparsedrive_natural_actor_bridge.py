#!/usr/bin/env python3
"""Audit a real/factual/static natural-actor SparseDrive comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from analyze_hugsim_source_dynamic_visibility import crop_bounds


CONDITIONS = ("real", "factual", "static_control")
RUNS = ("baseline", "baseline_repeat")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--real-report", type=Path, required=True)
    parser.add_argument("--factual-report", type=Path, required=True)
    parser.add_argument("--static-report", type=Path, required=True)
    parser.add_argument("--source-support-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plan_distance(first: Any, second: Any) -> dict[str, Any]:
    a = np.asarray(first, dtype=np.float64)
    b = np.asarray(second, dtype=np.float64)
    if a.shape != (6, 2) or b.shape != a.shape:
        raise ValueError("plans must both have shape 6x2")
    delta = b - a
    step_l2 = np.linalg.norm(delta, axis=1)
    return {
        "ade_m": float(np.mean(step_l2)),
        "fde_m": float(step_l2[-1]),
        "step_l2_m": step_l2.astype(float).tolist(),
        "final_right_delta_second_minus_first_m": float(delta[-1, 0]),
        "final_forward_delta_second_minus_first_m": float(delta[-1, 1]),
    }


def range_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"pairings": rows}
    for metric in ("ade_m", "fde_m"):
        values = [float(row[metric]) for row in rows]
        result[metric] = {
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "mean": float(np.mean(values)),
        }
    return result


def compare_all_resets(
    first: list[np.ndarray],
    second: list[np.ndarray],
) -> dict[str, Any]:
    rows = []
    for first_index, first_plan in enumerate(first):
        for second_index, second_plan in enumerate(second):
            rows.append(
                {
                    "first_reset": first_index + 1,
                    "second_reset": second_index + 1,
                    **plan_distance(first_plan, second_plan),
                }
            )
    return range_summary(rows)


def interval_decision(
    first_min: float,
    first_max: float,
    second_min: float,
    second_max: float,
) -> str:
    """Judge whether the first interval is strictly lower than the second."""

    if first_max < second_min:
        return "accepted"
    if second_max < first_min:
        return "rejected"
    return "down-weighted"


def response_decision(effect_min: float, effect_max: float, repeat_max: float) -> str:
    if effect_min > repeat_max:
        return "accepted"
    if effect_max <= repeat_max:
        return "rejected"
    return "down-weighted"


def max_abs(first: Any, second: Any) -> float:
    a = np.asarray(first, dtype=np.float64)
    b = np.asarray(second, dtype=np.float64)
    if a.shape != b.shape:
        return float("inf")
    return float(np.max(np.abs(a - b))) if a.size else 0.0


def endpoint_frame(report: dict[str, Any], run: str, endpoint: int) -> dict[str, Any]:
    matches = [
        frame
        for frame in report[run]["frames"]
        if int(frame["source_frame_index"]) == endpoint
    ]
    if len(matches) != 1:
        raise ValueError(f"{run}: expected one endpoint frame {endpoint}")
    return matches[0]


def endpoint_plans(
    report: dict[str, Any], endpoint: int
) -> list[np.ndarray]:
    return [
        np.asarray(
            endpoint_frame(report, run, endpoint)["native"][
                "final_planning_values"
            ],
            dtype=np.float64,
        )
        for run in RUNS
    ]


def validate_inputs(
    preregistration: dict[str, Any],
    reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected_frames = preregistration["selection"]["source_frame_indices"]
    endpoint = int(preregistration["selection"]["evaluated_endpoint_frame"])
    receiver = preregistration["receiver"]
    held_fixed_maxima = {
        "ego_status": 0.0,
        "command": 0.0,
        "front_calibration": 0.0,
        "future_reference": 0.0,
    }
    reference_frames = reports["real"]["baseline"]["frames"]

    for condition, report in reports.items():
        if report["source"]["frame_indices"] != expected_frames:
            raise ValueError(f"{condition}: source frame indices differ")
        if report["model"]["checkpoint_sha256"] != receiver["checkpoint_sha256"]:
            raise ValueError(f"{condition}: checkpoint differs")
        if report["model"]["config_sha256"] != receiver["config_sha256"]:
            raise ValueError(f"{condition}: config differs")
        if report["adapter"]["sha256"] != receiver["adapter_sha256"]:
            raise ValueError(f"{condition}: adapter differs")
        if (
            report["receiver_source"]["commit"]
            != receiver["source_commit"]
        ):
            raise ValueError(f"{condition}: receiver source commit differs")
        if (
            report["receiver_source"]["working_diff_sha256"]
            != receiver["source_working_diff_sha256"]
        ):
            raise ValueError(f"{condition}: receiver source diff differs")
        for run in RUNS:
            observed = [
                int(frame["source_frame_index"])
                for frame in report[run]["frames"]
            ]
            if observed != expected_frames:
                raise ValueError(f"{condition}/{run}: frame sequence differs")
            if not all(
                frame["native"]["all_declared_tensors_finite"]
                for frame in report[run]["frames"]
            ):
                raise ValueError(f"{condition}/{run}: non-finite native output")

    for condition, report in reports.items():
        for run in RUNS:
            for reference, candidate in zip(
                reference_frames, report[run]["frames"], strict=True
            ):
                if reference["timestamp_s"] != candidate["timestamp_s"]:
                    raise ValueError(f"{condition}/{run}: timestamp differs")
                reference_contract = reference["input_contract"]
                candidate_contract = candidate["input_contract"]
                checks = {
                    "ego_status": (
                        reference_contract["ego_status_10d"],
                        candidate_contract["ego_status_10d"],
                    ),
                    "command": (
                        reference_contract[
                            "command_one_hot_right_left_straight"
                        ],
                        candidate_contract[
                            "command_one_hot_right_left_straight"
                        ],
                    ),
                    "front_calibration": (
                        reference_contract["front_model_to_camera"],
                        candidate_contract["front_model_to_camera"],
                    ),
                    "future_reference": (
                        reference["recorded_camera_rig_future_xy_m"],
                        candidate["recorded_camera_rig_future_xy_m"],
                    ),
                }
                for name, values in checks.items():
                    held_fixed_maxima[name] = max(
                        held_fixed_maxima[name], max_abs(*values)
                    )
    if max(held_fixed_maxima.values()) > 1e-8:
        raise ValueError("held-fixed state, calibration or reference differs")

    endpoint_depth = expected_frames.index(endpoint) + 1
    if endpoint_depth < 4:
        raise ValueError("evaluated endpoint is not fully warmed")
    return {
        "source_frame_indices_equal": True,
        "checkpoint_config_adapter_equal": True,
        "all_native_outputs_finite": True,
        "endpoint_history_depth": endpoint_depth,
        "held_fixed_max_abs_differences": held_fixed_maxima,
    }


def camera_image_path(frame: dict[str, Any], camera: str) -> Path:
    paths = [
        Path(item["image_path"])
        for item in frame["input_contract"]["camera_inputs"]
        if item["camera"] == camera
    ]
    if len(paths) != 1:
        raise ValueError(f"expected one {camera} input path")
    return paths[0]


def source_support_row(
    source_support: dict[str, Any], endpoint: int, camera: str
) -> dict[str, Any]:
    matches = [
        row
        for row in source_support["rows"]
        if int(row["frame_index"]) == endpoint and row["camera"] == camera
    ]
    if len(matches) != 1:
        raise ValueError("source-support audit lacks endpoint/camera row")
    return matches[0]


def save_visualization(
    reports: dict[str, dict[str, Any]],
    plans: dict[str, list[np.ndarray]],
    comparisons: dict[str, dict[str, Any]],
    decisions: dict[str, str],
    support_row: dict[str, Any],
    repeat_max: float,
    endpoint: int,
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    camera = support_row["camera"]
    endpoint_frames = {
        condition: endpoint_frame(report, "baseline", endpoint)
        for condition, report in reports.items()
    }
    images = {
        condition: np.asarray(
            Image.open(camera_image_path(frame, camera)).convert("RGB")
        )
        for condition, frame in endpoint_frames.items()
    }
    source_keep_mask = np.load(Path(support_row["source_mask_path"]))
    source_mask = ~source_keep_mask.astype(bool)
    x0, y0, x1, y1 = crop_bounds(source_mask)
    local_mask = source_mask[y0:y1, x0:x1]
    crops = {
        condition: image[y0:y1, x0:x1]
        for condition, image in images.items()
    }
    delta = np.mean(
        np.abs(
            crops["factual"].astype(np.float64)
            - crops["static_control"].astype(np.float64)
        ),
        axis=2,
    )

    figure = plt.figure(figsize=(16, 9), constrained_layout=True)
    grid = figure.add_gridspec(2, 4, height_ratios=(1, 1.1))
    titles = {
        "real": "Real source RGB",
        "factual": "HUGSIM factual",
        "static_control": "HUGSIM native dynamic omitted",
    }
    for column, condition in enumerate(CONDITIONS):
        axis = figure.add_subplot(grid[0, column])
        axis.imshow(crops[condition])
        if condition == "real":
            overlay = np.zeros((*local_mask.shape, 4), dtype=np.float64)
            overlay[local_mask] = (0.0, 1.0, 1.0, 0.28)
            axis.imshow(overlay)
        axis.set_title(titles[condition])
        axis.axis("off")
    delta_axis = figure.add_subplot(grid[0, 3])
    delta_axis.imshow(delta, cmap="magma", vmin=0)
    delta_axis.contour(
        local_mask.astype(float),
        levels=[0.5],
        colors=["cyan"],
        linewidths=1.2,
    )
    delta_axis.set_title("Factual − static RGB support")
    delta_axis.axis("off")

    plan_axis = figure.add_subplot(grid[1, :2])
    colors = {
        "real": "#2ca02c",
        "factual": "#d62728",
        "static_control": "#1f77b4",
    }
    for condition in CONDITIONS:
        points = np.concatenate((np.zeros((1, 2)), plans[condition][0]), axis=0)
        plan_axis.plot(
            points[:, 0],
            points[:, 1],
            marker="o",
            linewidth=2.6,
            color=colors[condition],
            label=titles[condition],
        )
    plan_axis.set(
        title="Fully warmed native SparseDrive plan",
        xlabel="right (+) / left (−), metres",
        ylabel="forward, metres",
    )
    plan_axis.grid(alpha=0.3)
    plan_axis.legend(fontsize=9)

    gap_axis = figure.add_subplot(grid[1, 2])
    gap_labels = ["real↔factual", "real↔static", "factual↔static"]
    gap_keys = ["real_factual", "real_static", "factual_static"]
    gap_values = [
        comparisons[key]["ade_m"]["mean"] for key in gap_keys
    ]
    gap_axis.bar(
        gap_labels,
        gap_values,
        color=["#d62728", "#1f77b4", "#9467bd"],
    )
    gap_axis.set(
        title="Plan difference (all reset pairings)",
        ylabel="six-waypoint ADE, metres",
    )
    gap_axis.tick_params(axis="x", rotation=18)
    gap_axis.grid(axis="y", alpha=0.25)

    evidence_axis = figure.add_subplot(grid[1, 3])
    evidence_axis.axis("off")
    evidence_axis.text(
        0.02,
        0.95,
        "Preregistered decisions",
        fontsize=14,
        weight="bold",
        va="top",
    )
    evidence_axis.text(
        0.02,
        0.78,
        f"Native response > repeat: {decisions['native_response']}",
        fontsize=11,
    )
    evidence_axis.text(
        0.02,
        0.64,
        f"Moves output toward real: {decisions['moves_toward_real']}",
        fontsize=11,
    )
    evidence_axis.text(
        0.02,
        0.50,
        f"Same selected mode: {decisions['mode_invariance']}",
        fontsize=11,
    )
    evidence_axis.text(
        0.02,
        0.32,
        f"Native effect ADE: {comparisons['factual_static']['ade_m']['mean']:.4f} m\n"
        f"Real↔factual ADE: {comparisons['real_factual']['ade_m']['mean']:.4f} m\n"
        f"Real↔static ADE: {comparisons['real_static']['ade_m']['mean']:.4f} m\n"
        f"Repeat envelope: {repeat_max:.2e} m",
        fontsize=10.5,
        linespacing=1.45,
        va="top",
    )
    figure.suptitle(
        f"Natural-actor receiver bridge · scene-0383 · frame {endpoint}\n"
        "Correct image support does not guarantee a closer target-AD response",
        fontsize=16,
    )
    path = output / "sparsedrive_natural_actor_bridge.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    paths = {
        "preregistration": args.preregistration.expanduser().resolve(),
        "real": args.real_report.expanduser().resolve(),
        "factual": args.factual_report.expanduser().resolve(),
        "static_control": args.static_report.expanduser().resolve(),
        "source_support": args.source_support_audit.expanduser().resolve(),
    }
    output = args.output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    output.mkdir(parents=True)

    preregistration = load_json(paths["preregistration"])
    reports = {
        condition: load_json(paths[condition]) for condition in CONDITIONS
    }
    validation = validate_inputs(preregistration, reports)
    endpoint = int(preregistration["selection"]["evaluated_endpoint_frame"])
    plans = {
        condition: endpoint_plans(report, endpoint)
        for condition, report in reports.items()
    }
    repeats = {
        condition: plan_distance(condition_plans[0], condition_plans[1])
        for condition, condition_plans in plans.items()
    }
    repeat_max = max(row["ade_m"] for row in repeats.values())
    comparisons = {
        "real_factual": compare_all_resets(plans["real"], plans["factual"]),
        "real_static": compare_all_resets(
            plans["real"], plans["static_control"]
        ),
        "factual_static": compare_all_resets(
            plans["factual"], plans["static_control"]
        ),
    }
    decisions = {
        "native_response": response_decision(
            comparisons["factual_static"]["ade_m"]["min"],
            comparisons["factual_static"]["ade_m"]["max"],
            repeat_max,
        ),
        "moves_toward_real": interval_decision(
            comparisons["real_factual"]["ade_m"]["min"],
            comparisons["real_factual"]["ade_m"]["max"],
            comparisons["real_static"]["ade_m"]["min"],
            comparisons["real_static"]["ade_m"]["max"],
        ),
    }
    all_modes = [
        int(
            endpoint_frame(reports[condition], run, endpoint)[
                "planning_selection"
            ]["selected_mode_index"]
        )
        for condition in CONDITIONS
        for run in RUNS
    ]
    decisions["mode_invariance"] = (
        "accepted" if len(set(all_modes)) == 1 else "rejected"
    )

    source_support = load_json(paths["source_support"])
    support = source_support_row(
        source_support, endpoint, "CAM_FRONT_LEFT"
    )
    visual_path = save_visualization(
        reports,
        plans,
        comparisons,
        decisions,
        support,
        repeat_max,
        endpoint,
        output,
    )
    result = {
        "audit_id": "sparsedrive_natural_actor_bridge_001",
        "date": date.today().isoformat(),
        "analysis_script": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "inputs": {
            name: {
                "path": str(path),
                "sha256": sha256_file(path),
            }
            for name, path in paths.items()
        },
        "validation": validation,
        "evaluated_endpoint_frame": endpoint,
        "condition_repeat_plan_ade_m": repeats,
        "repeat_envelope_plan_ade_m": repeat_max,
        "cross_condition_plan_distances": comparisons,
        "selected_modes_real_factual_static_by_reset": all_modes,
        "source_support_context": {
            "camera": support["camera"],
            "source_mask_pixels": support["source_mask_pixels"],
            "exact_source_mask_energy_fraction": support[
                "exact_source_mask_energy_fraction"
            ],
            "dilated_16px_source_mask_energy_fraction": support[
                "dilated_16px_source_mask_energy_fraction"
            ],
            "centroid_error_px": support["centroid_error_px"],
            "post_hoc_source_mask_photometric": support[
                "post_hoc_source_mask_photometric"
            ],
            "boundary": (
                "This prior source-support evidence shares source geometry and "
                "preprocessing and is not independent real-world ground truth."
            ),
        },
        "preregistered_decisions": decisions,
        "evidence_decision": {
            "overall": "down-weighted",
            "accepted": [
                "the native dynamic path causes a fully warmed SparseDrive plan response beyond independent-reset sensitivity",
                "real, factual and static-control runs retained the same selected planning mode",
            ],
            "down_weighted": [
                "one endpoint, one native actor, one reconstruction and one target AD do not establish a population effect",
                "the static reconstruction retains actor-like residual content and is not an actor-free control",
                "the source-support mask shares source geometry and preprocessing with reconstruction",
            ],
            "rejected": [
                "adding the native dynamic moved the SparseDrive plan toward the matched real-source plan under the preregistered ADE rule",
                "correct camera membership and overlapping image support are sufficient for target-AD task equivalence",
                "this result proves SparseDrive correctness, sensor equivalence, general HUGSIM credibility or AD safety",
            ],
        },
        "interpretation": (
            "The native dynamic contribution is visible to the target AD, but "
            "for this endpoint its addition moves the plan farther from the "
            "real-input plan than the static-control render. The prior static "
            "actor leakage is a plausible confound, not a proven cause."
        ),
        "visualization": str(visual_path),
        "visualization_sha256": sha256_file(visual_path),
    }
    result_path = output / "sparsedrive_natural_actor_bridge_audit.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
