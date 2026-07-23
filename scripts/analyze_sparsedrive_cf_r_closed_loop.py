#!/usr/bin/env python3
"""Audit a replicated strong/weak SparseDrive↔HUGSIM CF-R closed loop."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import subprocess
from pathlib import Path
from typing import Any

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analyze_hugsim_horizon_factorial import rectangle


CONDITIONS = ("slow", "fast")
CONSTRUCTS = (
    "final_ego_progress_m",
    "final_ego_speed_mps",
    "final_ego_actor_clearance_m",
)
DISPLAY = {
    "slow": "Strong conflict · actor 0.5 m/s",
    "fast": "Weak conflict · actor 1.5 m/s",
}
COLORS = {"slow": "#d62728", "fast": "#2ca02c"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_pickle(path: Path) -> Any:
    with path.open("rb") as stream:
        return pickle.load(stream)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob(repo: Path, commit: str, relative_path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def verify_preregistration(
    repo: Path,
    preregistration_path: Path,
    preregistration: dict[str, Any],
    commit: str,
) -> str:
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relative = str(preregistration_path.relative_to(repo))
    if git_blob(repo, resolved, relative) != preregistration_path.read_bytes():
        raise ValueError("preregistration differs from the committed version")
    script_relative = "scripts/analyze_sparsedrive_cf_r_closed_loop.py"
    script_hash = hashlib.sha256(
        git_blob(repo, resolved, script_relative)
    ).hexdigest()
    if script_hash != preregistration["analysis_script_sha256"]:
        raise ValueError("analysis script hash differs from preregistration")
    return resolved


def longitudinal_progress(
    boundary_box: list[float],
    current_box: list[float],
) -> float:
    boundary = np.asarray(boundary_box, dtype=np.float64)
    current = np.asarray(current_box, dtype=np.float64)
    forward = np.asarray(
        [np.cos(boundary[6]), np.sin(boundary[6])],
        dtype=np.float64,
    )
    return float(np.dot(current[:2] - boundary[:2], forward))


def outcome_rows(audit: dict[str, Any]) -> list[dict[str, float | bool]]:
    steps = audit["steps"]
    infos = [steps[0]["info_before"]]
    infos.extend(step["info_after"] for step in steps)
    boundary = infos[0]["ego_box"]
    rows = []
    for info in infos:
        if len(info["obj_boxes"]) != 1:
            raise ValueError("CF-R closed loop requires exactly one actor")
        rows.append(
            {
                "timestamp_s": float(info["timestamp"]),
                "elapsed_s": float(
                    info["timestamp"] - infos[0]["timestamp"]
                ),
                "ego_progress_m": longitudinal_progress(
                    boundary,
                    info["ego_box"],
                ),
                "ego_speed_mps": float(info["ego_velo"]),
                "ego_actor_clearance_m": float(
                    rectangle(info["ego_box"]).distance(
                        rectangle(info["obj_boxes"][0])
                    )
                ),
                "collision": bool(info["collision"]),
            }
        )
    return rows


def final_outcomes(rows: list[dict[str, float | bool]]) -> dict[str, float]:
    final = rows[-1]
    return {
        "final_ego_progress_m": float(final["ego_progress_m"]),
        "final_ego_speed_mps": float(final["ego_speed_mps"]),
        "final_ego_actor_clearance_m": float(
            final["ego_actor_clearance_m"]
        ),
        "minimum_ego_actor_clearance_m": min(
            float(row["ego_actor_clearance_m"]) for row in rows
        ),
    }


def robust_expected_order(
    strong_values: list[float],
    weak_values: list[float],
) -> dict[str, Any]:
    if len(strong_values) != len(weak_values) or len(strong_values) < 2:
        raise ValueError("paired analysis requires equal replicated conditions")
    paired_margins = [
        weak - strong
        for strong, weak in zip(strong_values, weak_values, strict=True)
    ]
    within_variation = max(
        float(np.ptp(strong_values)),
        float(np.ptp(weak_values)),
    )
    minimum_effect = min(paired_margins)
    direction_passed = all(margin > 0.0 for margin in paired_margins)
    separation_passed = (
        direction_passed and minimum_effect > within_variation
    )
    if separation_passed:
        decision = "accepted"
    elif direction_passed:
        decision = "down-weighted"
    else:
        decision = "rejected"
    return {
        "expected": "strong conflict < weak conflict",
        "strong_values": strong_values,
        "weak_values": weak_values,
        "paired_margins_weak_minus_strong": paired_margins,
        "minimum_between_condition_effect": minimum_effect,
        "maximum_within_condition_repeat_variation": within_variation,
        "direction_passed": direction_passed,
        "effect_exceeds_repeat_variation": separation_passed,
        "decision": decision,
    }


def validate_run(
    run_path: Path,
    spec: dict[str, Any],
    preregistration: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    audit = load_json(run_path / "audit_summary.json")
    writer = load_json(run_path / "sparsedrive_live_summary.json")
    expected_source = spec["source_input_sha256"]
    failures = []
    if audit["run_status"] != "complete":
        failures.append("runner incomplete")
    if audit["requested_steps"] != preregistration["live_loop"]["environment_steps"]:
        failures.append("wrong environment step count")
    if audit["control_hold_steps"] != preregistration["live_loop"]["control_hold_steps"]:
        failures.append("wrong control hold")
    if not audit["strict_action_bounds"] or not audit["evaluation_skipped"]:
        failures.append("action/scoring contract failed")
    warm = audit["warm_start"]
    if (
        not warm["enabled"]
        or warm["step_count"] != preregistration["warm_start"]["environment_steps"]
        or warm["maximum_state_residual"]
        > preregistration["warm_start"]["state_atol"]
        or warm["maximum_rgb_difference"] != 0
    ):
        failures.append("source warm-start gate failed")
    for name, expected_hash in expected_source.items():
        observed = warm["source_input_sha256"].get(name)
        if observed != expected_hash:
            failures.append(f"warm-start source hash differs: {name}")
    if audit["source_assets"]["scenario_yaml_sha256"] != spec["config_sha256"]:
        failures.append("scenario config hash differs")
    if (
        writer["status"] != "complete"
        or not writer["source_warm_started"]
        or writer["plans_sent"] != preregistration["live_loop"]["plan_updates"]
        or writer["padding_or_repetition_used"]
        or writer["first_live_boundary_state_max_abs_residual"] != 0.0
        or writer["first_live_boundary_rgb_max_abs_difference"] != 0
        or writer["first_plan_reference_max_abs_difference"]
        > writer["reset_numerical_envelope"]
    ):
        failures.append("SparseDrive live boundary or output gate failed")
    if sha256_file(
        Path(writer["first_plan_reference_native"])
    ) != spec["reference_native_sha256"]:
        failures.append("reference native output hash differs")
    if failures:
        raise ValueError(f"{run_path}: " + "; ".join(failures))
    return audit, writer


def analyze(
    runs: dict[str, list[dict[str, Any]]],
    writers: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    del writers
    rows = {
        condition: [outcome_rows(run) for run in condition_runs]
        for condition, condition_runs in runs.items()
    }
    timestamps = [
        [float(row["timestamp_s"]) for row in trace]
        for condition in CONDITIONS
        for trace in rows[condition]
    ]
    aligned = all(values == timestamps[0] for values in timestamps[1:])
    finals = {
        condition: [final_outcomes(trace) for trace in rows[condition]]
        for condition in CONDITIONS
    }
    decisions = {
        construct: robust_expected_order(
            [item[construct] for item in finals["slow"]],
            [item[construct] for item in finals["fast"]],
        )
        for construct in CONSTRUCTS
    }
    task_reversals = []
    for replicate in range(len(rows["slow"])):
        strong_adverse = any(
            bool(row["collision"]) for row in rows["slow"][replicate]
        )
        weak_adverse = any(
            bool(row["collision"]) for row in rows["fast"][replicate]
        )
        if weak_adverse and not strong_adverse:
            task_reversals.append(replicate + 1)
    input_gate = aligned
    all_directional = all(
        item["direction_passed"] for item in decisions.values()
    )
    all_robust = all(
        item["effect_exceeds_repeat_variation"]
        for item in decisions.values()
    )
    if input_gate and all_robust and not task_reversals:
        overall = "accepted"
    elif input_gate and all_directional and not task_reversals:
        overall = "down-weighted"
    else:
        overall = "rejected"
    return {
        "audit_id": "hugsim_cf_r_closed_loop_001",
        "scope": (
            "replicated simulator-internal strong/weak lead-actor "
            "closed-loop response"
        ),
        "timestamps_aligned": aligned,
        "final_outcomes": finals,
        "construct_decisions": decisions,
        "weak_only_adverse_event_replicates": task_reversals,
        "overall_internal_causal_response": {
            "decision": overall,
            "reason": (
                "all preregistered direct outcomes must preserve direction "
                "and exceed same-condition repeat variation"
            ),
        },
        "real_world_closed_loop_credibility": {
            "decision": "rejected",
            "reason": (
                "no matched real outcome or externally qualified behavior "
                "magnitude is available"
            ),
        },
        "rows": rows,
    }


def save_summary_plot(analysis: dict[str, Any], output: Path) -> Path:
    figure, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    fields = (
        ("ego_progress_m", "Ego longitudinal progress", "m"),
        ("ego_speed_mps", "Ego speed", "m/s"),
        ("ego_actor_clearance_m", "Oriented-box clearance", "m"),
    )
    for axis, (field, title, unit) in zip(axes.ravel()[:3], fields, strict=True):
        for condition in CONDITIONS:
            for replicate, trace in enumerate(
                analysis["rows"][condition],
                start=1,
            ):
                axis.plot(
                    [row["elapsed_s"] for row in trace],
                    [row[field] for row in trace],
                    color=COLORS[condition],
                    alpha=0.65,
                    marker="o",
                    markersize=2,
                    label=(
                        f"{DISPLAY[condition]} · reset {replicate}"
                        if replicate == 1
                        else None
                    ),
                )
        axis.set(title=title, xlabel="live-loop time, s", ylabel=unit)
        axis.grid(alpha=0.3)
        axis.legend(fontsize=8)

    labels = ["progress", "speed", "clearance"]
    ratios = []
    for construct in CONSTRUCTS:
        item = analysis["construct_decisions"][construct]
        within = item["maximum_within_condition_repeat_variation"]
        ratios.append(
            np.inf
            if within == 0.0 and item["minimum_between_condition_effect"] > 0
            else (
                item["minimum_between_condition_effect"] / within
                if within > 0.0
                else 0.0
            )
        )
    finite_ratios = [10.0 if np.isinf(value) else value for value in ratios]
    colors = ["#2ca02c" if value > 1.0 else "#ff7f0e" for value in ratios]
    axes[1, 1].bar(labels, finite_ratios, color=colors)
    axes[1, 1].axhline(1.0, color="black", linestyle="--")
    axes[1, 1].set(
        title="Effect / within-condition repeat variation",
        ylabel="ratio (>1 required)",
    )
    axes[1, 1].grid(axis="y", alpha=0.3)
    figure.suptitle("CF-R closed loop: strong vs weak lead-actor conflict")
    path = output / "cf_r_closed_loop_summary.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def crop_front(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    return frame[: height // 2, width // 3 : 2 * width // 3]


def labeled_pair(
    strong: np.ndarray,
    weak: np.ndarray,
    strong_row: dict[str, Any],
    weak_row: dict[str, Any],
) -> np.ndarray:
    panels = []
    for condition, frame, row in (
        ("slow", strong, strong_row),
        ("fast", weak, weak_row),
    ):
        panel = crop_front(frame)
        band = np.zeros((68, panel.shape[1], 3), dtype=np.uint8)
        cv2.putText(
            band,
            DISPLAY[condition],
            (16, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            band,
            (
                f"v={row['ego_speed_mps']:.2f} m/s  "
                f"clearance={row['ego_actor_clearance_m']:.2f} m"
            ),
            (16, 54),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            1,
        )
        panels.append(np.vstack([band, panel]))
    combined = np.hstack(panels)
    cv2.putText(
        combined,
        f"live t={strong_row['elapsed_s']:.2f} s",
        (combined.shape[1] // 2 - 90, combined.shape[0] - 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 255),
        2,
    )
    return combined


def save_comparison_media(
    slow_run: Path,
    fast_run: Path,
    analysis: dict[str, Any],
    output: Path,
) -> tuple[Path, Path]:
    captures = {
        "slow": cv2.VideoCapture(str(slow_run / "video.mp4")),
        "fast": cv2.VideoCapture(str(fast_run / "video.mp4")),
    }
    frames: dict[str, list[np.ndarray]] = {"slow": [], "fast": []}
    for condition in CONDITIONS:
        while True:
            ok, frame = captures[condition].read()
            if not ok:
                break
            frames[condition].append(frame)
        captures[condition].release()
    expected = len(analysis["rows"]["slow"][0])
    if len(frames["slow"]) != expected or len(frames["fast"]) != expected:
        raise ValueError("video frame count does not match outcome trace")

    paired_frames = [
        labeled_pair(
            frames["slow"][index],
            frames["fast"][index],
            analysis["rows"]["slow"][0][index],
            analysis["rows"]["fast"][0][index],
        )
        for index in range(expected)
    ]
    height, width = paired_frames[0].shape[:2]
    video_path = output / "cf_r_closed_loop_front_comparison.mp4"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        4.0,
        (width, height),
    )
    for frame in paired_frames:
        writer.write(frame)
    writer.release()

    indices = (0, expected // 2, expected - 1)
    contact = np.vstack([paired_frames[index] for index in indices])
    contact_path = output / "cf_r_closed_loop_front_contact_sheet.png"
    cv2.imwrite(str(contact_path), contact)
    return video_path, contact_path


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.expanduser().resolve()
    preregistration = load_json(preregistration_path)
    preregistration_commit = verify_preregistration(
        repo,
        preregistration_path,
        preregistration,
        args.preregistration_commit,
    )
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)

    paths: dict[str, list[Path]] = {}
    runs: dict[str, list[dict[str, Any]]] = {}
    writers: dict[str, list[dict[str, Any]]] = {}
    for condition in CONDITIONS:
        spec = preregistration["conditions"][condition]
        paths[condition] = [
            (repo / path).resolve() for path in spec["outputs"]
        ]
        validated = [
            validate_run(path, spec, preregistration)
            for path in paths[condition]
        ]
        runs[condition] = [item[0] for item in validated]
        writers[condition] = [item[1] for item in validated]

    analysis = analyze(runs, writers)
    analysis["preregistration_commit"] = preregistration_commit
    analysis["runs"] = {
        condition: [str(path) for path in paths[condition]]
        for condition in CONDITIONS
    }
    plot = save_summary_plot(analysis, output)
    video, contact = save_comparison_media(
        paths["slow"][0],
        paths["fast"][0],
        analysis,
        output,
    )
    analysis["visualization"] = str(plot)
    analysis["comparison_video"] = str(video)
    analysis["contact_sheet"] = str(contact)
    report = output / "cf_r_closed_loop_audit.json"
    report.write_text(json.dumps(analysis, indent=2) + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
