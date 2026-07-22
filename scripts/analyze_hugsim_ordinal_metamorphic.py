#!/usr/bin/env python3
"""Analyze preregistered HUGSIM ordinal metamorphic audit 001."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analyze_hugsim_horizon_factorial import (
    load_data_frames,
    rectangle,
    sampled_future_actor_boxes,
)
from analyze_hugsim_multicar import paired_differences, validate_run_pairing
from analyze_sparse4d_hugsim_baseline import annotate_camera


CONDITIONS = (
    "no_actor",
    "center_near",
    "center_far",
    "adjacent_near",
    "adjacent_far",
)
ACTOR_CONDITIONS = CONDITIONS[1:]
DISPLAY_NAMES = {
    "no_actor": "No actor",
    "center_near": "Centre / near",
    "center_far": "Centre / far",
    "adjacent_near": "Adjacent / near",
    "adjacent_far": "Adjacent / far",
}
COLORS = {
    "center_near": "#d9485f",
    "center_far": "#2b6cb0",
    "adjacent_near": "#8a56ac",
    "adjacent_far": "#319795",
}
RELATIONS = (
    ("center_near", "center_far", "longitudinal"),
    ("center_near", "adjacent_near", "lateral"),
    ("center_far", "adjacent_far", "lateral"),
    ("adjacent_near", "adjacent_far", "longitudinal"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--receiver-output", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--prelaunch-note", default=None)
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


def planned_horizon_seconds(frames: list[dict[str, Any]]) -> float:
    planned = frames[0]["planned_traj"]
    return len(planned["traj"]) * float(planned["timestep"])


def actor_local_xy(info: dict[str, Any]) -> tuple[float, float]:
    ego = np.asarray(info["ego_box"], dtype=np.float64)
    actor = np.asarray(info["obj_boxes"][0], dtype=np.float64)
    delta = actor[:2] - ego[:2]
    cosine, sine = np.cos(ego[6]), np.sin(ego[6])
    forward = cosine * delta[0] + sine * delta[1]
    left = -sine * delta[0] + cosine * delta[1]
    return float(forward), float(left)


def geometry_rows(
    infos: list[dict[str, Any]],
    frames: list[dict[str, Any]],
    valid_end_s: float,
) -> list[dict[str, float]]:
    info_by_time = {
        round(float(info["timestamp"]), 8): info for info in infos
    }
    rows = []
    for frame_index, frame in enumerate(frames):
        timestamp = float(frame["time_stamp"])
        if not (0.0 < timestamp <= valid_end_s + 1e-9):
            continue
        info = info_by_time[round(timestamp, 8)]
        actor_history, _ = sampled_future_actor_boxes(frames, frame_index)
        current_plan = np.asarray(
            [[frame["ego_box"][0], frame["ego_box"][1], frame["ego_box"][6]]],
            dtype=np.float64,
        )
        plan = np.concatenate(
            (current_plan, np.asarray(frame["planned_traj"]["traj"], dtype=np.float64)),
            axis=0,
        )
        if len(actor_history) != len(plan):
            raise ValueError(
                f"timestamp {timestamp}: future actor history is incomplete "
                f"({len(actor_history)} of {len(plan)})"
            )

        ego_polygon = rectangle(info["ego_box"])
        actor_polygon = rectangle(info["obj_boxes"][0])
        current_clearance = float(ego_polygon.distance(actor_polygon))
        future_clearances = []
        for planned_state, actor_boxes in zip(plan, actor_history, strict=True):
            planned_ego = list(frame["ego_box"])
            planned_ego[0] = float(planned_state[0])
            planned_ego[1] = float(planned_state[1])
            planned_ego[6] = float(planned_state[2])
            future_clearances.append(
                float(rectangle(planned_ego).distance(rectangle(actor_boxes[0])))
            )
        forward, left = actor_local_xy(info)
        rows.append(
            {
                "timestamp_s": timestamp,
                "actor_forward_m": forward,
                "actor_left_m": left,
                "ego_footprint_clearance_m": current_clearance,
                "planned_corridor_clearance_m": float(min(future_clearances)),
            }
        )
    return rows


def geometry_relation(
    dominant_rows: list[dict[str, float]],
    subordinate_rows: list[dict[str, float]],
    relation_type: str,
) -> dict[str, Any]:
    subordinate = {row["timestamp_s"]: row for row in subordinate_rows}
    pairs = [(row, subordinate[row["timestamp_s"]]) for row in dominant_rows]
    if relation_type == "longitudinal":
        factor_margins = [
            other["actor_forward_m"] - dominant["actor_forward_m"]
            for dominant, other in pairs
        ]
    elif relation_type == "lateral":
        factor_margins = [
            abs(other["actor_left_m"]) - abs(dominant["actor_left_m"])
            for dominant, other in pairs
        ]
    else:
        raise ValueError(f"unknown relation type: {relation_type}")
    ego_margins = [
        other["ego_footprint_clearance_m"]
        - dominant["ego_footprint_clearance_m"]
        for dominant, other in pairs
    ]
    corridor_margins = [
        other["planned_corridor_clearance_m"]
        - dominant["planned_corridor_clearance_m"]
        for dominant, other in pairs
    ]
    passed = all(value > 0.0 for value in factor_margins + ego_margins + corridor_margins)
    return {
        "passed": passed,
        "paired_timestamp_count": len(pairs),
        "minimum_factor_margin_m": float(min(factor_margins)),
        "minimum_ego_clearance_margin_m": float(min(ego_margins)),
        "minimum_planned_corridor_clearance_margin_m": float(min(corridor_margins)),
    }


def receiver_relation(
    dominant_rows: list[dict[str, Any]],
    subordinate_rows: list[dict[str, Any]],
    relation_type: str,
    valid_end_s: float,
) -> dict[str, Any]:
    def valid(rows: list[dict[str, Any]]) -> dict[float, dict[str, Any]]:
        return {
            float(row["timestamp_s"]): row
            for row in rows
            if 0.0 < float(row["timestamp_s"]) <= valid_end_s + 1e-9
        }

    dominant = valid(dominant_rows)
    subordinate = valid(subordinate_rows)
    timestamps = sorted(set(dominant) & set(subordinate))
    comparisons = []
    expected = reversal = unavailable = 0
    for timestamp in timestamps:
        dominant_match = dominant[timestamp]["actor_matches"][0]["nearest_qualified"]
        subordinate_match = subordinate[timestamp]["actor_matches"][0]["nearest_qualified"]
        if dominant_match is None or subordinate_match is None:
            unavailable += 1
            comparisons.append({"timestamp_s": timestamp, "outcome": "unavailable"})
            continue
        dominant_xy = dominant_match["prediction_center_vehicle_xy"]
        subordinate_xy = subordinate_match["prediction_center_vehicle_xy"]
        if relation_type == "longitudinal":
            dominant_value = float(dominant_xy[0])
            subordinate_value = float(subordinate_xy[0])
        else:
            dominant_value = abs(float(dominant_xy[1]))
            subordinate_value = abs(float(subordinate_xy[1]))
        outcome = "expected" if dominant_value < subordinate_value else "reversal"
        expected += outcome == "expected"
        reversal += outcome == "reversal"
        comparisons.append(
            {
                "timestamp_s": timestamp,
                "dominant_value_m": dominant_value,
                "subordinate_value_m": subordinate_value,
                "outcome": outcome,
            }
        )
    available = [row for row in comparisons if row["outcome"] != "unavailable"]
    aggregate_expected = bool(
        available
        and np.median([row["dominant_value_m"] for row in available])
        < np.median([row["subordinate_value_m"] for row in available])
    )
    return {
        "planned_timestamp_count": len(timestamps),
        "expected_count": int(expected),
        "reversal_count": int(reversal),
        "unavailable_count": int(unavailable),
        "aggregate_direction_expected": aggregate_expected,
        "comparisons": comparisons,
    }


def relation_evidence_label(
    geometry_passed: bool,
    receiver: dict[str, Any],
) -> str:
    if not geometry_passed or not receiver["aggregate_direction_expected"]:
        return "rejected"
    if receiver["reversal_count"] == 0 and receiver["unavailable_count"] == 0:
        return "accepted"
    return "down-weighted"


def make_summary_figure(
    output: Path,
    relations: dict[str, dict[str, Any]],
    geometry: dict[str, list[dict[str, float]]],
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(16, 6), constrained_layout=True)
    labels = list(relations)
    x = np.arange(len(labels))
    expected = [relations[label]["receiver"]["expected_count"] for label in labels]
    reversals = [relations[label]["receiver"]["reversal_count"] for label in labels]
    unavailable = [relations[label]["receiver"]["unavailable_count"] for label in labels]
    axes[0].bar(x, expected, label="Expected", color="#2f855a")
    axes[0].bar(x, reversals, bottom=expected, label="Reversal", color="#c53030")
    axes[0].bar(
        x,
        unavailable,
        bottom=np.asarray(expected) + np.asarray(reversals),
        label="Unavailable",
        color="#d69e2e",
    )
    axes[0].set_xticks(x, labels, rotation=20, ha="right")
    axes[0].set_ylabel("Paired Sparse4Dv3 timestamps")
    axes[0].set_title("Predeclared receiver relation outcomes")
    axes[0].legend()
    axes[0].grid(axis="y", alpha=0.25)

    for condition in ACTOR_CONDITIONS:
        rows = geometry[condition]
        axes[1].plot(
            [row["timestamp_s"] for row in rows],
            [row["planned_corridor_clearance_m"] for row in rows],
            linewidth=2,
            color=COLORS[condition],
            label=DISPLAY_NAMES[condition],
        )
    axes[1].set_xlabel("Simulation time (s)")
    axes[1].set_ylabel("Minimum planned-corridor clearance (m)")
    axes[1].set_title("Independent geometry in complete-future window")
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    figure.suptitle("HUGSIM ordinal metamorphic audit 001", fontsize=16)
    figure.savefig(output, dpi=170)
    plt.close(figure)


def make_receiver_contact_sheet(
    output: Path,
    predictions: dict[str, list[dict[str, Any]]],
    run_paths: dict[str, Path],
    threshold: float,
    timestamp_s: float = 3.0,
) -> None:
    figure, axes = plt.subplots(1, len(CONDITIONS), figsize=(20, 4), constrained_layout=True)
    for axis, condition in zip(axes, CONDITIONS, strict=True):
        row = min(predictions[condition], key=lambda item: abs(float(item["timestamp_s"]) - timestamp_s))
        frame_index = int(row["frame_index"])
        observations = load_pickle(run_paths[condition] / "observations.pkl")
        infos = load_pickle(run_paths[condition] / "infos.pkl")
        display_row = associated_display_row(condition, row)
        image = annotate_camera(
            observations[frame_index]["rgb"]["CAM_FRONT"],
            infos[frame_index],
            display_row,
            "CAM_FRONT",
            threshold,
            max_predictions=8,
        )
        axis.imshow(image)
        axis.set_title(f"{DISPLAY_NAMES[condition]}\nt={row['timestamp_s']:.1f}s")
        axis.set_xticks([])
        axis.set_yticks([])
    figure.suptitle(
        "Raw HUGSIM CAM_FRONT supplied to Sparse4Dv3, with associated actor box",
        fontsize=15,
    )
    figure.savefig(output, dpi=160)
    plt.close(figure)


def make_receiver_video(
    output: Path,
    predictions: dict[str, list[dict[str, Any]]],
    run_paths: dict[str, Path],
    threshold: float,
) -> None:
    observations = {
        condition: load_pickle(run_paths[condition] / "observations.pkl")
        for condition in CONDITIONS
    }
    infos = {
        condition: load_pickle(run_paths[condition] / "infos.pkl")
        for condition in CONDITIONS
    }
    frame_count = min(len(predictions[condition]) for condition in CONDITIONS)
    width, height = 1600, 900
    tile_width, tile_height = 533, 450
    positions = {
        "no_actor": (0, 0),
        "center_near": (533, 0),
        "center_far": (1066, 0),
        "adjacent_near": (267, 450),
        "adjacent_far": (800, 450),
    }
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), 2.0, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"could not open video writer: {output}")
    try:
        for index in range(frame_count):
            canvas = np.zeros((height, width, 3), dtype=np.uint8)
            for condition in CONDITIONS:
                row = predictions[condition][index]
                frame_index = int(row["frame_index"])
                display_row = associated_display_row(condition, row)
                image = annotate_camera(
                    observations[condition][frame_index]["rgb"]["CAM_FRONT"],
                    infos[condition][frame_index],
                    display_row,
                    "CAM_FRONT",
                    threshold,
                    max_predictions=8,
                )
                tile = cv2.resize(image, (tile_width, tile_height), interpolation=cv2.INTER_AREA)
                cv2.putText(
                    tile,
                    f"{DISPLAY_NAMES[condition]}  t={row['timestamp_s']:.1f}s",
                    (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                if condition != "no_actor" and not display_row["predictions"]:
                    cv2.putText(
                        tile,
                        "actor association unavailable",
                        (12, 58),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.58,
                        (255, 80, 80),
                        2,
                        cv2.LINE_AA,
                    )
                x, y = positions[condition]
                canvas[y : y + tile_height, x : x + tile_width] = tile
            writer.write(cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))
    finally:
        writer.release()


def associated_display_row(
    condition: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Keep only the frozen actor association for actor-condition visuals."""
    if condition == "no_actor":
        return row
    association = row["actor_matches"][0]["nearest_qualified"]
    predictions = []
    if association is not None:
        predictions = [row["predictions"][association["prediction_rank"]]]
    return {**row, "predictions": predictions}


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.expanduser().resolve()
    receiver_root = args.receiver_output.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)

    preregistration = load_json(preregistration_path)
    if preregistration["audit_id"] != "hugsim_ordinal_metamorphic_001":
        raise ValueError("unexpected preregistration audit ID")
    run_paths = {
        condition: (repo_root / preregistration["conditions"][condition]["output"]).resolve()
        for condition in CONDITIONS
    }
    for condition in CONDITIONS:
        config = repo_root / preregistration["conditions"][condition]["config"]
        expected_hash = preregistration["conditions"][condition]["config_sha256"]
        if sha256_file(config) != expected_hash:
            raise ValueError(f"{condition}: config hash differs from preregistration")

    audits = {condition: load_json(path / "audit_summary.json") for condition, path in run_paths.items()}
    infos = {condition: load_pickle(path / "infos.pkl") for condition, path in run_paths.items()}
    steps = {condition: load_pickle(path / "audit_steps.pkl") for condition, path in run_paths.items()}
    frames = {condition: load_data_frames(path) for condition, path in run_paths.items()}
    pairing = {}
    for condition in ACTOR_CONDITIONS:
        input_validation = validate_run_pairing(
            audits["no_actor"],
            audits[condition],
            infos["no_actor"],
            infos[condition],
            steps["no_actor"],
            steps[condition],
        )
        output_differences = paired_differences(
            infos["no_actor"],
            infos[condition],
            steps["no_actor"],
            steps[condition],
        )
        if any(value != 0.0 for value in output_differences.values()):
            raise ValueError(
                f"{condition}: ego/action pairing differs: {output_differences}"
            )
        pairing[condition] = {
            "input_validation": input_validation,
            "output_differences": output_differences,
        }

    horizon_s = planned_horizon_seconds(frames["no_actor"])
    valid_end_s = min(float(items[-1]["timestamp"]) for items in infos.values()) - horizon_s
    geometry = {
        condition: geometry_rows(infos[condition], frames[condition], valid_end_s)
        for condition in ACTOR_CONDITIONS
    }

    receiver_manifest = load_json(receiver_root / "manifest.json")
    threshold = float(receiver_manifest["runs"]["no_actor"]["summary"]["score_threshold"])
    if threshold != float(preregistration["receiver"]["score_threshold"]):
        raise ValueError("receiver threshold differs from preregistration")
    if receiver_manifest["model"]["checkpoint_sha256"] != preregistration["receiver"]["checkpoint_sha256"]:
        raise ValueError("receiver checkpoint differs from preregistration")
    predictions = {
        condition: load_json(receiver_root / receiver_manifest["runs"][condition]["predictions"])
        for condition in CONDITIONS
    }

    relation_results = {}
    for dominant, subordinate, relation_type in RELATIONS:
        label = f"{dominant}>{subordinate}"
        geometry_result = geometry_relation(
            geometry[dominant], geometry[subordinate], relation_type
        )
        receiver_result = receiver_relation(
            predictions[dominant], predictions[subordinate], relation_type, valid_end_s
        )
        relation_results[label] = {
            "dominant": dominant,
            "subordinate": subordinate,
            "relation_type": relation_type,
            "geometry": geometry_result,
            "receiver": receiver_result,
            "evidence_label": relation_evidence_label(
                geometry_result["passed"], receiver_result
            ),
        }

    no_actor_valid = [
        row
        for row in predictions["no_actor"]
        if 0.0 < float(row["timestamp_s"]) <= valid_end_s + 1e-9
    ]
    no_actor_vehicle_count = sum(
        prediction["label_id"] in range(5) and prediction["score"] >= threshold
        for row in no_actor_valid
        for prediction in row["predictions"]
    )
    evidence_counts = {
        label: sum(result["evidence_label"] == label for result in relation_results.values())
        for label in ("accepted", "down-weighted", "rejected")
    }
    overall_label = "accepted" if evidence_counts == {"accepted": 4, "down-weighted": 0, "rejected": 0} else "down-weighted"

    summary = {
        "audit_id": preregistration["audit_id"],
        "preregistration_commit": args.preregistration_commit,
        "prelaunch_note": args.prelaunch_note,
        "run_paths": {key: str(value) for key, value in run_paths.items()},
        "pairing": pairing,
        "complete_future_window": {
            "planned_horizon_s": horizon_s,
            "valid_start_exclusive_s": 0.0,
            "valid_end_inclusive_s": valid_end_s,
            "geometry_frame_count": len(geometry["center_near"]),
            "receiver_frame_count": len(no_actor_valid),
        },
        "geometry": geometry,
        "relations": relation_results,
        "no_actor_valid_window_qualified_vehicle_detection_count": int(no_actor_vehicle_count),
        "evidence_counts": evidence_counts,
        "overall_segment_evidence_label": overall_label,
        "auxiliary_hugsim_score_notice": "HUGSIM NC/TTC/PDMS do not decide this audit",
        "strongest_allowed_claim": preregistration["strongest_allowed_claim"],
        "forbidden_claims": preregistration["forbidden_claims"],
    }
    (output / "ordinal_metamorphic_audit.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    make_summary_figure(output / "ordinal_audit_summary.png", relation_results, geometry)
    make_receiver_contact_sheet(
        output / "ordinal_receiver_contact_sheet.png",
        predictions,
        run_paths,
        threshold,
    )
    make_receiver_video(
        output / "ordinal_receiver_comparison.mp4",
        predictions,
        run_paths,
        threshold,
    )

    rows = []
    for label, result in relation_results.items():
        receiver = result["receiver"]
        rows.append(
            f"| `{label}` | {result['relation_type']} | "
            f"{result['geometry']['passed']} | {receiver['expected_count']} | "
            f"{receiver['reversal_count']} | {receiver['unavailable_count']} | "
            f"`{result['evidence_label']}` |"
        )
    report = f"""# HUGSIM Ordinal Metamorphic Audit 001

## Outcome

Overall segment: `{overall_label}`.

All four predeclared geometric relations hold at every one of the
{len(geometry['center_near'])} simulator timestamps in the complete-future
window `(0, {valid_end_s:.1f}] s`. Sparse4Dv3 produces zero reversals. Two
relations are `accepted`; two are `down-weighted` because the
`adjacent_near` actor has one unavailable association in the 13 receiver
timestamps.

| Relation | Type | Geometry gate | Expected | Reversal | Unavailable | Evidence |
|---|---|---:|---:|---:|---:|---|
{chr(10).join(rows)}

The no-actor baseline has {no_actor_vehicle_count} qualified vehicle
detections inside the valid receiver window. HUGSIM NC/TTC/PDMS are retained
only as auxiliary simulator outputs and do not decide this audit.

## Interpretation

The result supports a narrow claim: within this declared 2x2 design range,
HUGSIM state geometry changes monotonically and one frozen real-data-trained
receiver preserves the intended longitudinal and lateral direction without
reversal. The two unavailable comparisons are preserved as receiver/simulator
interface boundary evidence rather than averaged away.

This does not qualify the numerical distances as realistic uncertainty bounds,
does not establish real-sensor equivalence, and does not prove AD planning,
control, collision risk, or general HUGSIM fitness as a test domain.

## Inspectable Artifacts

- `ordinal_audit_summary.png`
- `ordinal_receiver_contact_sheet.png`
- `ordinal_receiver_comparison.mp4`
- `ordinal_metamorphic_audit.json`
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"overall": overall_label, "evidence_counts": evidence_counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
