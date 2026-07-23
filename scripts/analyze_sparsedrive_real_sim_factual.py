#!/usr/bin/env python3
"""Compare matched real/source and factual HUGSIM SparseDrive responses."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from run_sparse4d_hugsim_receiver import sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-report", type=Path, required=True)
    parser.add_argument("--sim-report", type=Path, required=True)
    parser.add_argument("--cf-r-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def front_image_path(frame: dict[str, Any]) -> Path:
    matches = [
        Path(item["image_path"])
        for item in frame["input_contract"]["camera_inputs"]
        if item["camera"] == "CAM_FRONT"
    ]
    if len(matches) != 1:
        raise ValueError("each frame must declare one CAM_FRONT image")
    return matches[0]


def array_max_abs(first: Any, second: Any) -> float:
    a = np.asarray(first, dtype=np.float64)
    b = np.asarray(second, dtype=np.float64)
    if a.shape != b.shape:
        return float("inf")
    return float(np.max(np.abs(a - b))) if a.size else 0.0


def validate_pair(real: dict[str, Any], sim: dict[str, Any]) -> dict[str, Any]:
    if real["model"]["checkpoint_sha256"] != sim["model"]["checkpoint_sha256"]:
        raise ValueError("real and simulation checkpoints differ")
    if real["model"]["config_sha256"] != sim["model"]["config_sha256"]:
        raise ValueError("real and simulation model configs differ")
    if real["adapter"]["sha256"] != sim["adapter"]["sha256"]:
        raise ValueError("real and simulation receiver adapters differ")
    real_frames = real["baseline"]["frames"]
    sim_frames = sim["baseline"]["frames"]
    if len(real_frames) != len(sim_frames):
        raise ValueError("real and simulation frame counts differ")

    rows = []
    for real_frame, sim_frame in zip(real_frames, sim_frames, strict=True):
        if real_frame["source_frame_index"] != sim_frame["source_frame_index"]:
            raise ValueError("real and simulation source-frame identities differ")
        if real_frame["timestamp_s"] != sim_frame["timestamp_s"]:
            raise ValueError("real and simulation timestamps differ")
        real_contract = real_frame["input_contract"]
        sim_contract = sim_frame["input_contract"]
        status_difference = array_max_abs(
            real_contract["ego_status_10d"],
            sim_contract["ego_status_10d"],
        )
        command_difference = array_max_abs(
            real_contract["command_one_hot_right_left_straight"],
            sim_contract["command_one_hot_right_left_straight"],
        )
        calibration_difference = array_max_abs(
            real_contract["front_model_to_camera"],
            sim_contract["front_model_to_camera"],
        )
        reference_difference = array_max_abs(
            real_frame["recorded_camera_rig_future_xy_m"],
            sim_frame["recorded_camera_rig_future_xy_m"],
        )
        if max(
            status_difference,
            command_difference,
            calibration_difference,
            reference_difference,
        ) > 1e-8:
            raise ValueError(
                "held-fixed real/simulation input state or calibration differs"
            )

        real_plan = np.asarray(
            real_frame["native"]["final_planning_values"], dtype=np.float64
        )
        sim_plan = np.asarray(
            sim_frame["native"]["final_planning_values"], dtype=np.float64
        )
        delta = sim_plan - real_plan
        distance = np.linalg.norm(delta, axis=1)
        real_score = np.asarray(
            real_frame["native"]["planning_score_values"], dtype=np.float64
        )
        sim_score = np.asarray(
            sim_frame["native"]["planning_score_values"], dtype=np.float64
        )
        rows.append(
            {
                "source_frame_index": real_frame["source_frame_index"],
                "timestamp_s": real_frame["timestamp_s"],
                "history_depth_in_this_reset": len(rows) + 1,
                "fully_warmed_four_frame_history": len(rows) == 3,
                "held_fixed_max_abs_differences": {
                    "ego_status": status_difference,
                    "command": command_difference,
                    "front_calibration": calibration_difference,
                    "future_reference": reference_difference,
                },
                "real_final_plan_xy_m": real_plan.astype(float).tolist(),
                "sim_final_plan_xy_m": sim_plan.astype(float).tolist(),
                "plan_domain_step_l2_m": distance.astype(float).tolist(),
                "plan_domain_ade_m": float(np.mean(distance)),
                "plan_domain_fde_m": float(distance[-1]),
                "final_right_delta_sim_minus_real_m": float(delta[-1, 0]),
                "final_forward_delta_sim_minus_real_m": float(delta[-1, 1]),
                "planning_score_max_abs_difference": array_max_abs(
                    real_score, sim_score
                ),
                "real_selected_mode": real_frame["planning_selection"][
                    "selected_mode_index"
                ],
                "sim_selected_mode": sim_frame["planning_selection"][
                    "selected_mode_index"
                ],
                "mode_equal": (
                    real_frame["planning_selection"]["selected_mode_index"]
                    == sim_frame["planning_selection"]["selected_mode_index"]
                ),
                "recorded_camera_rig_future_xy_m": real_frame[
                    "recorded_camera_rig_future_xy_m"
                ],
                "real_reference_error": real_frame["plan_reference_error"],
                "sim_reference_error": sim_frame["plan_reference_error"],
                "real_front_image": str(front_image_path(real_frame)),
                "sim_front_image": str(front_image_path(sim_frame)),
            }
        )
    return {"rows": rows}


def load_pixel_metrics(sim_report: dict[str, Any]) -> dict[int, dict[str, float]]:
    manifest_path = Path(sim_report["source"]["archive_manifest"])
    manifest = load_json(manifest_path)
    report_paths = sorted(
        {Path(item["render_report"]) for item in manifest["images"]}
    )
    metrics = {}
    for report_path in report_paths:
        report = load_json(report_path)
        variant = manifest["variant"]
        metrics[int(report["frame_index"])] = report["variants"][variant][
            "mean_metrics"
        ]
    return metrics


def cf_r_scale(cf_r_audit: dict[str, Any]) -> dict[str, Any]:
    medians = cf_r_audit["planning"]["median_final_forward_m"]
    pair_results = cf_r_audit["planning"]["pair_results"]
    minimum_pair_margin = min(
        float(item["minimum_margin_m"]) for item in pair_results.values()
    )
    strong_to_weak = float(medians["fast"] - medians["slow"])
    return {
        "construct": "native 3 s final forward endpoint",
        "median_final_forward_m": medians,
        "minimum_adjacent_or_pairwise_margin_m": minimum_pair_margin,
        "strong_to_weak_median_effect_m": strong_to_weak,
        "comparison_boundary": (
            "Scale diagnostic only: CF-R uses a different simulated timeline "
            "and actor intervention. It cannot upgrade that result without a "
            "matched factual/counterfactual baseline in this same window."
        ),
    }


def save_visualization(
    rows: list[dict[str, Any]],
    pixel_metrics: dict[int, dict[str, float]],
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(
        3,
        len(rows),
        figsize=(4.5 * len(rows), 10.5),
        constrained_layout=True,
        gridspec_kw={"height_ratios": [1, 1, 1.15]},
    )
    for column, row in enumerate(rows):
        frame_index = int(row["source_frame_index"])
        real_image = np.asarray(Image.open(row["real_front_image"]).convert("RGB"))
        sim_image = np.asarray(Image.open(row["sim_front_image"]).convert("RGB"))
        axes[0, column].imshow(real_image)
        axes[0, column].set_title(
            f"REAL frame {frame_index}\nt={row['timestamp_s']:.2f}s"
        )
        axes[0, column].axis("off")
        metrics = pixel_metrics[frame_index]
        axes[1, column].imshow(sim_image)
        axes[1, column].set_title(
            f"HUGSIM same source pose\n"
            f"SSIM {metrics['ssim']:.3f}, PSNR {metrics['psnr_db']:.1f} dB"
        )
        axes[1, column].axis("off")

        axis = axes[2, column]
        real_plan = np.asarray(row["real_final_plan_xy_m"])
        sim_plan = np.asarray(row["sim_final_plan_xy_m"])
        reference = np.asarray(row["recorded_camera_rig_future_xy_m"])
        for points, color, label in (
            (reference, "#2ca02c", "recorded motion"),
            (real_plan, "#ff7f0e", "real → SparseDrive"),
            (sim_plan, "#1f77b4", "HUGSIM → SparseDrive"),
        ):
            points = np.concatenate((np.zeros((1, 2)), points), axis=0)
            axis.plot(
                points[:, 0],
                points[:, 1],
                marker="o",
                linewidth=2.2,
                color=color,
                label=label,
            )
        warm = "fully warmed" if row["fully_warmed_four_frame_history"] else (
            f"history {row['history_depth_in_this_reset']}/4"
        )
        axis.set_title(
            f"{warm}: D_domain ADE {row['plan_domain_ade_m']:.3f} m\n"
            f"endpoint {row['plan_domain_fde_m']:.3f} m"
        )
        axis.set_xlabel("right (+) / left (-), metres")
        if column == 0:
            axis.set_ylabel("forward, metres")
            axis.legend(fontsize=8)
        axis.grid(alpha=0.3)
    figure.suptitle(
        "Matched factual REAL ↔ HUGSIM response of the same frozen SparseDrive",
        fontsize=16,
    )
    path = output / "sparsedrive_real_sim_factual_comparison.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    real_path = args.real_report.expanduser().resolve()
    sim_path = args.sim_report.expanduser().resolve()
    cf_r_path = args.cf_r_audit.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (real_path, sim_path, cf_r_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    output.mkdir(parents=True)

    real = load_json(real_path)
    sim = load_json(sim_path)
    comparison = validate_pair(real, sim)
    rows = comparison["rows"]
    pixels = load_pixel_metrics(sim)
    missing_pixels = sorted(
        {int(row["source_frame_index"]) for row in rows} - set(pixels)
    )
    if missing_pixels:
        raise ValueError(f"missing pixel metrics for frames: {missing_pixels}")
    repeat_envelope = max(
        float(
            real["qualification"][
                "baseline_repeat_max_abs_plan_difference_m"
            ]
        ),
        float(
            sim["qualification"][
                "baseline_repeat_max_abs_plan_difference_m"
            ]
        ),
    )
    warmed = [row for row in rows if row["fully_warmed_four_frame_history"]]
    if len(warmed) != 1:
        raise ValueError("expected exactly one fully warmed receiver frame")
    warmed_row = warmed[0]
    visual_path = save_visualization(rows, pixels, output)
    cf_scale = cf_r_scale(load_json(cf_r_path))
    result = {
        "audit_id": "sparsedrive_real_sim_factual_001",
        "date": date.today().isoformat(),
        "inputs": {
            "real_report": str(real_path),
            "real_report_sha256": sha256_file(real_path),
            "sim_report": str(sim_path),
            "sim_report_sha256": sha256_file(sim_path),
            "cf_r_audit": str(cf_r_path),
            "cf_r_audit_sha256": sha256_file(cf_r_path),
        },
        "held_fixed_gate": {
            "checkpoint_equal": True,
            "config_equal": True,
            "adapter_equal": True,
            "ego_status_command_calibration_and_future_reference_equal": True,
        },
        "pixel_metrics_by_frame": {
            str(index): metrics for index, metrics in sorted(pixels.items())
        },
        "plan_domain_rows": rows,
        "summary": {
            "repeat_envelope_m": repeat_envelope,
            "all_frame_domain_ade_m": float(
                np.mean([row["plan_domain_ade_m"] for row in rows])
            ),
            "all_frame_domain_fde_m": float(
                np.mean([row["plan_domain_fde_m"] for row in rows])
            ),
            "fully_warmed_source_frame": warmed_row["source_frame_index"],
            "fully_warmed_domain_ade_m": warmed_row["plan_domain_ade_m"],
            "fully_warmed_domain_fde_m": warmed_row["plan_domain_fde_m"],
            "fully_warmed_final_forward_delta_sim_minus_real_m": warmed_row[
                "final_forward_delta_sim_minus_real_m"
            ],
            "fully_warmed_final_right_delta_sim_minus_real_m": warmed_row[
                "final_right_delta_sim_minus_real_m"
            ],
            "fully_warmed_mode_equal": warmed_row["mode_equal"],
            "fully_warmed_domain_effect_exceeds_repeat": (
                warmed_row["plan_domain_fde_m"] > repeat_envelope
            ),
        },
        "cf_r_cross_experiment_scale_diagnostic": cf_scale,
        "evidence_decision": {
            "overall": "down-weighted",
            "accepted": (
                "the same frozen SparseDrive input contract produces a measured "
                "nonzero factual response difference between official-source "
                "real RGB and HUGSIM RGB at the same declared source poses"
            ),
            "down-weighted": (
                "one fully warmed frame and a provisional absolute "
                "model-LiDAR/CAM_FRONT anchor do not define an externally "
                "qualified equivalence threshold"
            ),
            "rejected": [
                "pixel similarity alone establishes AD-task equivalence",
                "this factual slice upgrades the earlier CF-R response to a "
                "real-world-valid magnitude",
                "this result proves SparseDrive, HUGSIM or an AD system safe",
            ],
        },
        "visualization": str(visual_path),
        "visualization_sha256": sha256_file(visual_path),
    }
    result_path = output / "sparsedrive_real_sim_factual_audit.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
