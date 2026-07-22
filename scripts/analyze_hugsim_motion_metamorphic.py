#!/usr/bin/env python3
"""Analyze the CF-M 001 HUGSIM constant-speed metamorphic experiment."""

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
from analyze_hugsim_multicar import paired_differences, validate_run_pairing
from analyze_hugsim_ordinal_metamorphic import actor_local_xy


CONDITIONS = ("slow", "nominal", "fast")
DISPLAY_NAMES = {"slow": "Slow 0.5 m/s", "nominal": "Nominal 1.0 m/s", "fast": "Fast 1.5 m/s"}
COLORS = {"slow": "#d9485f", "nominal": "#2b6cb0", "fast": "#2f855a"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preregistration-commit", required=True)
    return parser.parse_args()


def load_pickle(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git_blob(repo_root: Path, commit: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def verify_preregistration_commit(
    repo_root: Path,
    commit: str,
    preregistration_path: Path,
    preregistration: dict[str, Any],
) -> str:
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relative_preregistration = str(preregistration_path.relative_to(repo_root))
    if (
        git_blob(repo_root, resolved, relative_preregistration)
        != preregistration_path.read_bytes()
    ):
        raise ValueError("preregistration file differs from preregistration commit")

    script_relative = "scripts/analyze_hugsim_motion_metamorphic.py"
    if (
        sha256_bytes(git_blob(repo_root, resolved, script_relative))
        != preregistration["analysis_script_sha256"]
    ):
        raise ValueError("analysis script in preregistration commit has wrong hash")
    for condition in CONDITIONS:
        spec = preregistration["conditions"][condition]
        if sha256_bytes(git_blob(repo_root, resolved, spec["config"])) != spec[
            "config_sha256"
        ]:
            raise ValueError(
                f"{condition}: config in preregistration commit has wrong hash"
            )
    return resolved


def angular_difference(left: float, right: float) -> float:
    return float(abs((right - left + np.pi) % (2 * np.pi) - np.pi))


def actor_state_rows(infos: list[dict[str, Any]]) -> list[dict[str, float]]:
    rows = []
    for info in infos:
        if len(info["obj_boxes"]) != 1:
            raise ValueError(
                f"timestamp {info['timestamp']}: expected exactly one actor, "
                f"got {len(info['obj_boxes'])}"
            )
        actor = np.asarray(info["obj_boxes"][0], dtype=np.float64)
        forward, left = actor_local_xy(info)
        rows.append(
            {
                "timestamp_s": float(info["timestamp"]),
                "actor_x_m": float(actor[0]),
                "actor_y_m": float(actor[1]),
                "actor_yaw_rad": float(actor[6]),
                "actor_forward_m": forward,
                "actor_left_m": left,
                "ego_clearance_m": float(
                    rectangle(info["ego_box"]).distance(rectangle(actor))
                ),
            }
        )
    return rows


def motion_metrics(
    rows: list[dict[str, float]],
    configured_speed_mps: float,
    tolerances: dict[str, float],
) -> dict[str, Any]:
    transitions = []
    observed_speeds = []
    for previous, current in zip(rows[:-1], rows[1:], strict=True):
        dt = current["timestamp_s"] - previous["timestamp_s"]
        if dt <= 0:
            raise ValueError("timestamps must be strictly increasing")
        delta = np.asarray(
            [
                current["actor_x_m"] - previous["actor_x_m"],
                current["actor_y_m"] - previous["actor_y_m"],
            ],
            dtype=np.float64,
        )
        displacement = float(np.linalg.norm(delta))
        observed_speed = displacement / dt
        expected_delta = configured_speed_mps * dt * np.asarray(
            [
                np.cos(previous["actor_yaw_rad"]),
                np.sin(previous["actor_yaw_rad"]),
            ],
            dtype=np.float64,
        )
        observed_speeds.append(observed_speed)
        transitions.append(
            {
                "timestamp_s": current["timestamp_s"],
                "dt_s": dt,
                "displacement_m": displacement,
                "observed_speed_mps": observed_speed,
                "integration_residual_m": float(
                    np.linalg.norm(delta - expected_delta)
                ),
                "speed_error_mps": abs(observed_speed - configured_speed_mps),
                "heading_change_rad": angular_difference(
                    previous["actor_yaw_rad"], current["actor_yaw_rad"]
                ),
            }
        )

    acceleration_residuals = []
    for index in range(1, len(transitions)):
        dt = transitions[index]["timestamp_s"] - transitions[index - 1]["timestamp_s"]
        acceleration_residuals.append(
            abs(observed_speeds[index] - observed_speeds[index - 1]) / dt
        )

    maxima = {
        "integration_residual_m": max(
            row["integration_residual_m"] for row in transitions
        ),
        "speed_error_mps": max(row["speed_error_mps"] for row in transitions),
        "heading_change_rad": max(
            row["heading_change_rad"] for row in transitions
        ),
        "acceleration_residual_mps2": max(acceleration_residuals, default=0.0),
    }
    passed = all(
        maxima[name] <= tolerances[name]
        for name in (
            "integration_residual_m",
            "speed_error_mps",
            "heading_change_rad",
            "acceleration_residual_mps2",
        )
    )
    return {
        "configured_speed_mps": configured_speed_mps,
        "transition_count": len(transitions),
        "maxima": maxima,
        "passed": passed,
        "transitions": transitions,
    }


def strict_order_result(
    state_rows: dict[str, list[dict[str, float]]],
    field: str,
    skip_initial: bool = False,
) -> dict[str, Any]:
    by_condition = {
        condition: {row["timestamp_s"]: row for row in state_rows[condition]}
        for condition in CONDITIONS
    }
    timestamps = sorted(set.intersection(*(set(rows) for rows in by_condition.values())))
    if skip_initial:
        timestamps = timestamps[1:]
    outcomes = []
    margins = []
    for timestamp in timestamps:
        values = {
            condition: float(by_condition[condition][timestamp][field])
            for condition in CONDITIONS
        }
        lower_margin = values["nominal"] - values["slow"]
        upper_margin = values["fast"] - values["nominal"]
        expected = lower_margin > 0.0 and upper_margin > 0.0
        margins.extend((lower_margin, upper_margin))
        outcomes.append(
            {
                "timestamp_s": timestamp,
                "values": values,
                "outcome": "expected" if expected else "reversal_or_tie",
            }
        )
    reversal_count = sum(row["outcome"] != "expected" for row in outcomes)
    return {
        "field": field,
        "comparison_count": len(outcomes),
        "expected_count": len(outcomes) - reversal_count,
        "reversal_or_tie_count": reversal_count,
        "minimum_adjacent_margin": min(margins),
        "passed": reversal_count == 0,
        "outcomes": outcomes,
    }


def add_travel_distance(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    origin = np.asarray([rows[0]["actor_x_m"], rows[0]["actor_y_m"]])
    enriched = []
    for row in rows:
        position = np.asarray([row["actor_x_m"], row["actor_y_m"]])
        enriched.append(
            {**row, "travel_from_first_observation_m": float(np.linalg.norm(position - origin))}
        )
    return enriched


def make_summary_figure(
    output: Path,
    states: dict[str, list[dict[str, float]]],
    metrics: dict[str, dict[str, Any]],
    tolerances: dict[str, float],
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)
    for condition in CONDITIONS:
        rows = states[condition]
        transitions = metrics[condition]["transitions"]
        axes[0, 0].plot(
            [row["timestamp_s"] for row in rows],
            [row["travel_from_first_observation_m"] for row in rows],
            label=DISPLAY_NAMES[condition],
            color=COLORS[condition],
            linewidth=2,
        )
        axes[0, 1].plot(
            [row["timestamp_s"] for row in transitions],
            [row["observed_speed_mps"] for row in transitions],
            label=DISPLAY_NAMES[condition],
            color=COLORS[condition],
            linewidth=2,
        )
        axes[1, 0].plot(
            [row["timestamp_s"] for row in rows],
            [row["actor_forward_m"] for row in rows],
            label=DISPLAY_NAMES[condition],
            color=COLORS[condition],
            linewidth=2,
        )
        axes[1, 1].plot(
            [row["timestamp_s"] for row in transitions],
            [max(row["integration_residual_m"], 1e-12) for row in transitions],
            label=DISPLAY_NAMES[condition],
            color=COLORS[condition],
            linewidth=2,
        )

    axes[0, 0].set_title("Actor travel from first recorded state")
    axes[0, 0].set_ylabel("Travel (m)")
    axes[0, 1].set_title("Finite-difference actor speed")
    axes[0, 1].set_ylabel("Speed (m/s)")
    axes[1, 0].set_title("Actor forward gap in ego frame")
    axes[1, 0].set_ylabel("Forward gap (m)")
    axes[1, 1].set_title("Per-step constant-speed integration residual")
    axes[1, 1].set_ylabel("Residual (m, log scale)")
    axes[1, 1].set_yscale("log")
    axes[1, 1].axhline(
        tolerances["integration_residual_m"],
        color="black",
        linestyle="--",
        linewidth=1,
        label="Preregistered tolerance",
    )
    for axis in axes.flat:
        axis.set_xlabel("Simulation time (s)")
        axis.grid(alpha=0.25)
        axis.legend()
    figure.suptitle("HUGSIM CF-M 001: constant-speed motion invariants", fontsize=16)
    figure.savefig(output, dpi=170)
    plt.close(figure)


def make_contact_sheet(
    output: Path,
    observations: dict[str, list[dict[str, Any]]],
    infos: dict[str, list[dict[str, Any]]],
) -> None:
    indices = (0, len(infos["nominal"]) // 2, len(infos["nominal"]) - 1)
    figure, axes = plt.subplots(3, 3, figsize=(16, 9), constrained_layout=True)
    for row_index, condition in enumerate(CONDITIONS):
        for column_index, frame_index in enumerate(indices):
            axes[row_index, column_index].imshow(
                observations[condition][frame_index]["rgb"]["CAM_FRONT"]
            )
            timestamp = float(infos[condition][frame_index]["timestamp"])
            axes[row_index, column_index].set_title(
                f"{DISPLAY_NAMES[condition]}  t={timestamp:.2f}s"
            )
            axes[row_index, column_index].set_xticks([])
            axes[row_index, column_index].set_yticks([])
    figure.suptitle("Raw HUGSIM CAM_FRONT inputs for CF-M 001", fontsize=16)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def make_comparison_video(
    output: Path,
    observations: dict[str, list[dict[str, Any]]],
    states: dict[str, list[dict[str, float]]],
) -> None:
    tile_width, tile_height = 640, 360
    frame_count = min(len(observations[condition]) for condition in CONDITIONS)
    writer = cv2.VideoWriter(
        str(output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        4.0,
        (tile_width * len(CONDITIONS), tile_height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"could not open video writer: {output}")
    try:
        for index in range(frame_count):
            canvas = np.zeros(
                (tile_height, tile_width * len(CONDITIONS), 3), dtype=np.uint8
            )
            for column, condition in enumerate(CONDITIONS):
                image = observations[condition][index]["rgb"]["CAM_FRONT"]
                tile = cv2.resize(
                    image, (tile_width, tile_height), interpolation=cv2.INTER_AREA
                )
                label = (
                    f"{DISPLAY_NAMES[condition]}  "
                    f"t={states[condition][index]['timestamp_s']:.2f}s  "
                    f"gap={states[condition][index]['actor_forward_m']:.1f}m"
                )
                cv2.putText(
                    tile,
                    label,
                    (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.58,
                    (0, 0, 0),
                    4,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    tile,
                    label,
                    (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.58,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                start = column * tile_width
                canvas[:, start : start + tile_width] = tile
            writer.write(cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))
    finally:
        writer.release()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)

    preregistration = load_json(preregistration_path)
    if preregistration["audit_id"] != "hugsim_motion_metamorphic_001":
        raise ValueError("unexpected preregistration audit ID")
    if sha256_file(Path(__file__).resolve()) != preregistration[
        "analysis_script_sha256"
    ]:
        raise ValueError("current analysis script differs from preregistration")
    preregistration_commit = verify_preregistration_commit(
        repo_root,
        args.preregistration_commit,
        preregistration_path,
        preregistration,
    )

    controller_source = Path(preregistration["controller_source"]["path"])
    if sha256_file(controller_source) != preregistration["controller_source"]["sha256"]:
        raise ValueError("ConstantPlanner source hash differs from preregistration")

    run_paths = {}
    for condition in CONDITIONS:
        condition_spec = preregistration["conditions"][condition]
        config = (repo_root / condition_spec["config"]).resolve()
        if sha256_file(config) != condition_spec["config_sha256"]:
            raise ValueError(f"{condition}: config hash differs from preregistration")
        run_paths[condition] = (repo_root / condition_spec["output"]).resolve()

    audits = {
        condition: load_json(path / "audit_summary.json")
        for condition, path in run_paths.items()
    }
    writer_summaries = {
        condition: load_json(path / "plan_writer_summary.json")
        for condition, path in run_paths.items()
    }
    infos = {
        condition: load_pickle(path / "infos.pkl")
        for condition, path in run_paths.items()
    }
    steps = {
        condition: load_pickle(path / "audit_steps.pkl")
        for condition, path in run_paths.items()
    }
    observations = {
        condition: load_pickle(path / "observations.pkl")
        for condition, path in run_paths.items()
    }

    fixed = preregistration["fixed_design"]
    for condition in CONDITIONS:
        spec = preregistration["conditions"][condition]
        audit = audits[condition]
        source_assets = audit["source_assets"]
        if source_assets["scenario_yaml_sha256"] != spec["config_sha256"]:
            raise ValueError(f"{condition}: run used a non-preregistered scenario")
        expected_config = (repo_root / spec["config"]).resolve()
        if Path(source_assets["scenario_yaml"]).resolve() != expected_config:
            raise ValueError(f"{condition}: run scenario path differs")
        if audit["requested_steps"] != fixed["max_steps"]:
            raise ValueError(f"{condition}: requested step count differs")
        if audit["completed_steps"] != fixed["max_steps"]:
            raise ValueError(f"{condition}: run did not complete all steps")
        if audit["audit_repo"]["commit"] != preregistration_commit:
            raise ValueError(f"{condition}: run audit commit differs")
        if audit["audit_repo"]["worktree_status"]:
            raise ValueError(f"{condition}: run started from a dirty audit worktree")

        writer = writer_summaries[condition]
        writer_checks = {
            "status": writer["status"] == "complete",
            "horizon": writer["horizon"] == fixed["plan_writer_horizon"],
            "step_m": writer["step_m"] == fixed["plan_writer_step_m"],
            "max_steps": writer["max_steps"] == fixed["max_steps"],
            "responses_sent": writer["responses_sent"] == fixed["max_steps"],
            "done_received": writer["done_received"] is True,
            "audit_repo_commit": writer["audit_repo_commit"]
            == preregistration_commit,
        }
        failed_writer_checks = [
            name for name, passed in writer_checks.items() if not passed
        ]
        if failed_writer_checks:
            raise ValueError(
                f"{condition}: plan writer contract differs: "
                + ", ".join(failed_writer_checks)
            )

    pairing = {}
    for condition in ("slow", "fast"):
        pairing[condition] = {
            "input_validation": validate_run_pairing(
                audits["nominal"],
                audits[condition],
                infos["nominal"],
                infos[condition],
                steps["nominal"],
                steps[condition],
            ),
            "ego_action_differences": paired_differences(
                infos["nominal"],
                infos[condition],
                steps["nominal"],
                steps[condition],
            ),
        }
        if any(pairing[condition]["ego_action_differences"].values()):
            raise ValueError(f"{condition}: ego/action trajectory differs")

    tolerances = preregistration["numeric_tolerances"]
    states = {
        condition: add_travel_distance(actor_state_rows(infos[condition]))
        for condition in CONDITIONS
    }
    metrics = {
        condition: motion_metrics(
            states[condition],
            float(preregistration["conditions"][condition]["speed_mps"]),
            tolerances,
        )
        for condition in CONDITIONS
    }
    orders = {
        "travel_fast_gt_nominal_gt_slow": strict_order_result(
            states, "travel_from_first_observation_m", skip_initial=True
        ),
        "forward_gap_fast_gt_nominal_gt_slow": strict_order_result(
            states, "actor_forward_m"
        ),
        "clearance_fast_gt_nominal_gt_slow": strict_order_result(
            states, "ego_clearance_m"
        ),
    }

    hard_passed = all(result["passed"] for result in metrics.values())
    order_passed = all(result["passed"] for result in orders.values())
    claims = {
        "constant_speed_state_evolution": (
            "accepted" if hard_passed else "rejected"
        ),
        "controlled_relative_motion_order": (
            "accepted" if order_passed else "rejected"
        ),
    }
    overall_label = (
        "down-weighted"
        if all(label == "accepted" for label in claims.values())
        else "rejected"
    )

    summary = {
        "audit_id": preregistration["audit_id"],
        "preregistration_commit": preregistration_commit,
        "run_paths": {condition: str(path) for condition, path in run_paths.items()},
        "scope": preregistration["scope"],
        "pairing": pairing,
        "numeric_tolerances": tolerances,
        "motion_metrics": metrics,
        "monotonic_orders": orders,
        "claims": claims,
        "overall_segment_evidence_label": overall_label,
        "independence_notice": preregistration["independence_notice"],
        "strongest_allowed_claim": preregistration["strongest_allowed_claim"],
        "forbidden_claims": preregistration["forbidden_claims"],
    }
    (output / "motion_metamorphic_audit.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    make_summary_figure(
        output / "motion_indicator_summary.png", states, metrics, tolerances
    )
    make_contact_sheet(
        output / "motion_cam_front_contact_sheet.png", observations, infos
    )
    make_comparison_video(
        output / "motion_cam_front_comparison.mp4", observations, states
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
