#!/usr/bin/env python3
"""Audit a same-window SparseDrive lead-vehicle counterfactual response."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from analyze_sparsedrive_real_sim_factual import array_max_abs, front_image_path
from render_hugsim_exact_source_pose import select_camera_records, sha256_file
from run_sparsedrive_real_source import project_xy, source_intrinsic


REPORT_NAME = "sparsedrive_real_source_qualification.json"
FULLY_WARMED_DEPTH = 4
EGO_LENGTH_M = 3.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-report", type=Path, required=True)
    parser.add_argument("--factual-report", type=Path, required=True)
    parser.add_argument("--weak-report", type=Path, required=True)
    parser.add_argument("--strong-report", type=Path, required=True)
    parser.add_argument("--factual-audit", type=Path, required=True)
    parser.add_argument("--counterfactual-manifest", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def plan(frame: dict[str, Any]) -> np.ndarray:
    result = np.asarray(
        frame["native"]["final_planning_values"],
        dtype=np.float64,
    )
    if result.shape != (6, 2) or not np.isfinite(result).all():
        raise ValueError("each final native plan must be one finite 6x2 array")
    return result


def validate_reports(
    reports: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    factual = reports["factual"]
    for label, report in reports.items():
        for key in ("checkpoint_sha256", "config_sha256"):
            if report["model"][key] != factual["model"][key]:
                raise ValueError(f"{label} model {key} differs")
        if report["adapter"]["sha256"] != factual["adapter"]["sha256"]:
            raise ValueError(f"{label} receiver adapter differs")

    frames = {
        label: report["baseline"]["frames"]
        for label, report in reports.items()
    }
    lengths = {len(value) for value in frames.values()}
    if len(lengths) != 1 or next(iter(lengths)) < FULLY_WARMED_DEPTH:
        raise ValueError("reports must have one common window of at least four frames")

    rows = []
    labels = tuple(reports)
    for index, group in enumerate(zip(*(frames[label] for label in labels), strict=True)):
        by_label = dict(zip(labels, group, strict=True))
        reference = by_label["factual"]
        frame_index = int(reference["source_frame_index"])
        timestamp = float(reference["timestamp_s"])
        held_fixed = {}
        for label, frame in by_label.items():
            if int(frame["source_frame_index"]) != frame_index:
                raise ValueError(f"{label}: source-frame identity differs")
            if float(frame["timestamp_s"]) != timestamp:
                raise ValueError(f"{label}: timestamp differs")
            held_fixed[label] = {
                "ego_status": array_max_abs(
                    frame["input_contract"]["ego_status_10d"],
                    reference["input_contract"]["ego_status_10d"],
                ),
                "command": array_max_abs(
                    frame["input_contract"][
                        "command_one_hot_right_left_straight"
                    ],
                    reference["input_contract"][
                        "command_one_hot_right_left_straight"
                    ],
                ),
                "front_calibration": array_max_abs(
                    frame["input_contract"]["front_model_to_camera"],
                    reference["input_contract"]["front_model_to_camera"],
                ),
                "future_reference": array_max_abs(
                    frame["recorded_camera_rig_future_xy_m"],
                    reference["recorded_camera_rig_future_xy_m"],
                ),
            }
            if max(held_fixed[label].values()) > 1e-8:
                raise ValueError(f"{label}: held-fixed receiver state differs")

        plans = {label: plan(frame) for label, frame in by_label.items()}
        factual_plan = plans["factual"]
        row = {
            "source_frame_index": frame_index,
            "timestamp_s": timestamp,
            "history_depth_in_this_reset": index + 1,
            "fully_warmed_four_frame_history": index + 1 >= FULLY_WARMED_DEPTH,
            "held_fixed_max_abs_differences": held_fixed,
            "final_forward_m": {
                label: float(value[-1, 1]) for label, value in plans.items()
            },
            "final_right_m": {
                label: float(value[-1, 0]) for label, value in plans.items()
            },
            "selected_mode": {
                label: int(by_label[label]["planning_selection"]["selected_mode_index"])
                for label in labels
            },
            "D_domain_forward_sim_minus_real_m": float(
                plans["factual"][-1, 1] - plans["real"][-1, 1]
            ),
            "E_CF_forward_counterfactual_minus_factual_m": {
                label: float(plans[label][-1, 1] - factual_plan[-1, 1])
                for label in ("weak", "strong")
            },
            "strong_minus_weak_final_forward_m": float(
                plans["strong"][-1, 1] - plans["weak"][-1, 1]
            ),
            "plan_effect_vs_factual": {},
            "front_images": {
                label: str(front_image_path(by_label[label]))
                for label in labels
            },
            "plans_xy_m": {
                label: value.astype(float).tolist()
                for label, value in plans.items()
            },
        }
        for label in ("weak", "strong"):
            delta = plans[label] - factual_plan
            distance = np.linalg.norm(delta, axis=1)
            row["plan_effect_vs_factual"][label] = {
                "ade_m": float(np.mean(distance)),
                "fde_m": float(distance[-1]),
            }
        rows.append(row)
    return rows


def repeat_forward_envelope(
    reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    by_condition = {}
    for label, report in reports.items():
        baseline = report["baseline"]["frames"]
        repeated = report["baseline_repeat"]["frames"]
        differences = []
        for depth, (first, second) in enumerate(
            zip(baseline, repeated, strict=True),
            start=1,
        ):
            if depth < FULLY_WARMED_DEPTH:
                continue
            differences.append(abs(float(plan(first)[-1, 1] - plan(second)[-1, 1])))
        by_condition[label] = max(differences)
    return {
        "by_condition_m": by_condition,
        "maximum_m": max(by_condition.values()),
    }


def validate_counterfactual_geometry(
    manifest: dict[str, Any],
    warmed_indices: list[int],
) -> dict[str, Any]:
    conditions = manifest["conditions"]
    weak_gap = float(conditions["weak"]["declared_forward_path_gap_m"])
    strong_gap = float(conditions["strong"]["declared_forward_path_gap_m"])
    actor_length = float(manifest["actor"]["dimensions_wlh_m"][1])
    minimum_nonoverlap_center_gap = 0.5 * (EGO_LENGTH_M + actor_length)
    if not 0 < strong_gap < weak_gap:
        raise ValueError("counterfactual gap order is invalid")
    if strong_gap <= minimum_nonoverlap_center_gap:
        raise ValueError("strong actor gap overlaps declared vehicle lengths")

    geometry = {
        label: {
            int(item["source_frame_index"]): item
            for item in conditions[label]["actor_relative_geometry"]
        }
        for label in ("weak", "strong")
    }
    for frame_index in warmed_indices:
        weak = geometry["weak"][frame_index]
        strong = geometry["strong"][frame_index]
        if min(float(weak["forward_m"]), float(strong["forward_m"])) <= 0:
            raise ValueError("lead actor is not forward at every warmed timestamp")
        if float(strong["planar_distance_m"]) >= float(weak["planar_distance_m"]):
            raise ValueError("strong actor is not closer than weak")
    return {
        "declared_path_gap_m": {"weak": weak_gap, "strong": strong_gap},
        "minimum_nonoverlap_center_gap_m": minimum_nonoverlap_center_gap,
        "warmed_geometry": {
            label: {
                str(index): geometry[label][index]
                for index in warmed_indices
            }
            for label in ("weak", "strong")
        },
        "all_setup_geometry_gates_pass": True,
    }


def raw_front_projection(
    report: dict[str, Any],
    frame: dict[str, Any],
) -> np.ndarray:
    metadata = load_json(Path(report["source"]["metadata"]))
    record = select_camera_records(
        metadata,
        int(frame["source_frame_index"]),
    )["CAM_FRONT"]
    return (
        source_intrinsic(record)
        @ np.asarray(
            frame["input_contract"]["front_model_to_camera"],
            dtype=np.float64,
        )
    )


def draw_plan(
    image: Image.Image,
    plan_xy: np.ndarray,
    projection: np.ndarray,
    color: tuple[int, int, int],
) -> None:
    pixels, in_front = project_xy(plan_xy, projection)
    width, height = image.size
    visible = (
        in_front
        & np.isfinite(pixels).all(axis=1)
        & (pixels[:, 0] >= 0)
        & (pixels[:, 0] < width)
        & (pixels[:, 1] >= 0)
        & (pixels[:, 1] < height)
    )
    points = [
        (int(round(x)), int(round(y)))
        for x, y in pixels[visible]
    ]
    if not points:
        return
    draw = ImageDraw.Draw(image)
    if len(points) > 1:
        draw.line(points, fill=color, width=5)
    for x, y in points:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color)


def annotated_front(
    report: dict[str, Any],
    frame: dict[str, Any],
    label: str,
    color: tuple[int, int, int],
    history_depth: int,
) -> Image.Image:
    image = Image.open(front_image_path(frame)).convert("RGB")
    draw_plan(image, plan(frame), raw_front_projection(report, frame), color)
    draw = ImageDraw.Draw(image)
    band_height = 34
    draw.rectangle((0, 0, image.width, band_height), fill=(0, 0, 0))
    state = "WARM" if history_depth >= FULLY_WARMED_DEPTH else f"warm-up {history_depth}/4"
    text = (
        f"{label} | frame {frame['source_frame_index']} | {state} | "
        f"3 s forward {plan(frame)[-1, 1]:.2f} m"
    )
    draw.text((10, 10), text, fill=(255, 255, 255))
    return image


def save_contact_sheet(
    reports: dict[str, dict[str, Any]],
    warmed_rows: list[dict[str, Any]],
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    labels = ("real", "factual", "weak", "strong")
    colors = {
        "real": (255, 127, 14),
        "factual": (31, 119, 180),
        "weak": (44, 160, 44),
        "strong": (214, 39, 40),
    }
    figure, axes = plt.subplots(
        len(warmed_rows),
        len(labels),
        figsize=(18, 3.15 * len(warmed_rows)),
        constrained_layout=True,
    )
    frame_lookup = {
        label: {
            int(frame["source_frame_index"]): frame
            for frame in reports[label]["baseline"]["frames"]
        }
        for label in labels
    }
    for row_index, row in enumerate(warmed_rows):
        frame_index = int(row["source_frame_index"])
        for column, label in enumerate(labels):
            frame = frame_lookup[label][frame_index]
            image = annotated_front(
                reports[label],
                frame,
                label.upper(),
                colors[label],
                int(row["history_depth_in_this_reset"]),
            )
            axes[row_index, column].imshow(image)
            axes[row_index, column].axis("off")
    figure.suptitle(
        "Same SparseDrive receiver: REAL / factual HUGSIM / 10 m lead / 5 m lead\n"
        "colored dots are each condition's native 3 s plan projected into CAM_FRONT",
        fontsize=16,
    )
    path = output / "sparsedrive_same_window_counterfactual_contact_sheet.png"
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def save_effect_plot(
    warmed_rows: list[dict[str, Any]],
    repeat_envelope: float,
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    frames = [row["source_frame_index"] for row in warmed_rows]
    figure, axes = plt.subplots(1, 3, figsize=(17, 5.2), constrained_layout=True)
    colors = {
        "real": "#ff7f0e",
        "factual": "#1f77b4",
        "weak": "#2ca02c",
        "strong": "#d62728",
    }
    for label in ("real", "factual", "weak", "strong"):
        axes[0].plot(
            frames,
            [row["final_forward_m"][label] for row in warmed_rows],
            marker="o",
            linewidth=2.3,
            color=colors[label],
            label=label,
        )
    axes[0].set(
        title="Native 3 s forward endpoint",
        xlabel="source frame",
        ylabel="metres",
    )
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    series = {
        "D_domain factual-real": [
            row["D_domain_forward_sim_minus_real_m"] for row in warmed_rows
        ],
        "E_CF weak-factual": [
            row["E_CF_forward_counterfactual_minus_factual_m"]["weak"]
            for row in warmed_rows
        ],
        "E_CF strong-factual": [
            row["E_CF_forward_counterfactual_minus_factual_m"]["strong"]
            for row in warmed_rows
        ],
        "strong-weak": [
            row["strong_minus_weak_final_forward_m"] for row in warmed_rows
        ],
    }
    for label, values in series.items():
        axes[1].plot(frames, values, marker="o", linewidth=2, label=label)
    axes[1].axhspan(
        -repeat_envelope,
        repeat_envelope,
        color="#7f7f7f",
        alpha=0.35,
        label="repeat envelope",
    )
    axes[1].axhline(0, color="black", linewidth=1)
    axes[1].set(
        title="Signed response differences",
        xlabel="source frame",
        ylabel="metres (negative = less forward)",
    )
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)

    final = warmed_rows[-1]
    for label in ("real", "factual", "weak", "strong"):
        points = np.asarray(final["plans_xy_m"][label])
        points = np.vstack((np.zeros((1, 2)), points))
        axes[2].plot(
            points[:, 0],
            points[:, 1],
            marker="o",
            linewidth=2.3,
            color=colors[label],
            label=label,
        )
    axes[2].set(
        title=f"Final warmed frame {final['source_frame_index']} plans",
        xlabel="right (+) / left (-), metres",
        ylabel="forward, metres",
    )
    axes[2].legend()
    axes[2].grid(alpha=0.3)
    path = output / "sparsedrive_same_window_counterfactual_effects.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def save_video(
    reports: dict[str, dict[str, Any]],
    output: Path,
) -> Path:
    labels = ("real", "factual", "weak", "strong")
    colors = {
        "real": (255, 127, 14),
        "factual": (31, 119, 180),
        "weak": (44, 160, 44),
        "strong": (214, 39, 40),
    }
    sequences = {
        label: reports[label]["baseline"]["frames"]
        for label in labels
    }
    path = output / "sparsedrive_same_window_counterfactual_front_h264.mp4"
    with tempfile.TemporaryDirectory(prefix="sparsedrive-cf-video-") as temporary:
        temporary_path = Path(temporary)
        for history_depth, group in enumerate(
            zip(*(sequences[label] for label in labels), strict=True),
            start=1,
        ):
            panels = []
            for label, frame in zip(labels, group, strict=True):
                panel = annotated_front(
                    reports[label],
                    frame,
                    label.upper(),
                    colors[label],
                    history_depth,
                )
                panel.thumbnail((640, 360), Image.Resampling.LANCZOS)
                panels.append(panel)
            canvas = Image.new(
                "RGB",
                (
                    sum(panel.width for panel in panels),
                    max(panel.height for panel in panels),
                ),
                (0, 0, 0),
            )
            x = 0
            for panel in panels:
                canvas.paste(panel, (x, 0))
                x += panel.width
            canvas.save(temporary_path / f"frame_{history_depth:03d}.png")
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            "2",
            "-i",
            str(temporary_path / "frame_%03d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            str(path),
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")
    return path


def main() -> int:
    args = parse_args()
    paths = {
        "real": args.real_report.expanduser().resolve(),
        "factual": args.factual_report.expanduser().resolve(),
        "weak": args.weak_report.expanduser().resolve(),
        "strong": args.strong_report.expanduser().resolve(),
    }
    factual_audit_path = args.factual_audit.expanduser().resolve()
    manifest_path = args.counterfactual_manifest.expanduser().resolve()
    preregistration_path = args.preregistration.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (
        *paths.values(),
        factual_audit_path,
        manifest_path,
        preregistration_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    output.mkdir(parents=True)

    reports = {label: load_json(path) for label, path in paths.items()}
    rows = validate_reports(reports)
    warmed = [row for row in rows if row["fully_warmed_four_frame_history"]]
    warmed_indices = [int(row["source_frame_index"]) for row in warmed]
    repeat = repeat_forward_envelope(reports)
    geometry = validate_counterfactual_geometry(
        load_json(manifest_path),
        warmed_indices,
    )
    preregistration = load_json(preregistration_path)
    expected_warmed = preregistration["window"]["fully_warmed_evaluation_frames"]
    if warmed_indices != expected_warmed:
        raise ValueError("fully warmed frames differ from preregistration")

    strong_less_weak = [
        row["strong_minus_weak_final_forward_m"] < 0 for row in warmed
    ]
    signed_strong_minus_weak = [
        row["strong_minus_weak_final_forward_m"] for row in warmed
    ]
    median_strong_minus_weak = float(np.median(signed_strong_minus_weak))
    direction_accepted = (
        sum(strong_less_weak) >= 4
        and median_strong_minus_weak < -float(repeat["maximum_m"])
    )
    direction_decision = "accepted" if direction_accepted else "rejected"

    abs_domain = [
        abs(row["D_domain_forward_sim_minus_real_m"]) for row in warmed
    ]
    abs_strong_effect = [
        abs(row["E_CF_forward_counterfactual_minus_factual_m"]["strong"])
        for row in warmed
    ]
    ratios = [
        effect / domain if domain > 1e-12 else None
        for effect, domain in zip(abs_strong_effect, abs_domain, strict=True)
    ]
    finite_ratios = [value for value in ratios if value is not None]

    contact_sheet = save_contact_sheet(reports, warmed, output)
    effect_plot = save_effect_plot(warmed, float(repeat["maximum_m"]), output)
    video = save_video(reports, output)
    factual_audit = load_json(factual_audit_path)
    result = {
        "audit_id": "sparsedrive_same_window_counterfactual_001",
        "date": date.today().isoformat(),
        "inputs": {
            label: {
                "path": str(path),
                "sha256": sha256_file(path),
            }
            for label, path in paths.items()
        },
        "preregistration": {
            "path": str(preregistration_path),
            "sha256": sha256_file(preregistration_path),
        },
        "counterfactual_manifest": {
            "path": str(manifest_path),
            "sha256": sha256_file(manifest_path),
        },
        "factual_audit": {
            "path": str(factual_audit_path),
            "sha256": sha256_file(factual_audit_path),
            "warmed_summary": factual_audit["summary"],
        },
        "held_fixed_gate": {
            "checkpoint_config_adapter_equal": True,
            "ego_status_command_calibration_and_future_reference_equal": True,
        },
        "counterfactual_geometry_gate": geometry,
        "repeat_final_forward_envelope": repeat,
        "fully_warmed_rows": warmed,
        "decision": {
            "response_direction": direction_decision,
            "strong_less_forward_than_weak_count": sum(strong_less_weak),
            "fully_warmed_count": len(warmed),
            "median_strong_minus_weak_final_forward_m": median_strong_minus_weak,
            "median_effect_exceeds_repeat_in_expected_direction": (
                median_strong_minus_weak < -float(repeat["maximum_m"])
            ),
        },
        "domain_scale_diagnostic": {
            "per_frame_abs_strong_E_CF_over_abs_D_domain": {
                str(row["source_frame_index"]): ratio
                for row, ratio in zip(warmed, ratios, strict=True)
            },
            "median_abs_D_domain_forward_m": float(np.median(abs_domain)),
            "median_abs_strong_E_CF_forward_m": float(
                np.median(abs_strong_effect)
            ),
            "median_abs_effect_ratio": (
                float(np.median(finite_ratios)) if finite_ratios else None
            ),
            "strong_effect_exceeds_domain_count": sum(
                effect > domain
                for effect, domain in zip(
                    abs_strong_effect,
                    abs_domain,
                    strict=True,
                )
            ),
            "boundary": (
                "This compares observed scales in one window. It does not "
                "subtract domain error, define an equivalence threshold or "
                "supply real counterfactual truth."
            ),
        },
        "evidence_decision": {
            "overall": "down-weighted",
            "accepted": (
                "the preregistered strong-versus-weak SparseDrive response "
                "direction in this window"
                if direction_accepted
                else "the held-fixed setup and measured receiver response"
            ),
            "down-weighted": (
                "the result is one target AD, one reconstructed scene and a "
                "scripted non-interactive actor with no matched real counterpart"
            ),
            "rejected": [
                (
                    "the preregistered strong-versus-weak response direction"
                    if not direction_accepted
                    else "the response magnitude is thereby real-world-valid"
                ),
                "the result establishes realistic traffic interaction, collision validity or AD safety",
                "HUGSIM or SparseDrive can serve as its own external truth",
            ],
        },
        "artifacts": {
            "contact_sheet": str(contact_sheet),
            "contact_sheet_sha256": sha256_file(contact_sheet),
            "effect_plot": str(effect_plot),
            "effect_plot_sha256": sha256_file(effect_plot),
            "front_video": str(video),
            "front_video_sha256": sha256_file(video),
        },
    }
    result_path = output / "sparsedrive_same_window_counterfactual_audit.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
