#!/usr/bin/env python3
"""Analyze the preregistered CF-R motion-to-receiver causality audit."""

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
from analyze_hugsim_ordinal_metamorphic import actor_local_xy
from analyze_sparse4d_hugsim_baseline import annotate_camera


CONDITIONS = ("slow", "nominal", "fast")
DISPLAY = {
    "slow": "High closure / actor 0.5 m/s",
    "nominal": "Medium closure / actor 1.0 m/s",
    "fast": "Low closure / actor 1.5 m/s",
}
COLORS = {"slow": "#d9485f", "nominal": "#2b6cb0", "fast": "#2f855a"}
RELATIONS = (("slow", "nominal"), ("nominal", "fast"), ("slow", "fast"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--receiver-output", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preregistration-commit", required=True)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_pickle(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob(repo: Path, commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def verify_preregistration(
    repo: Path, commit: str, path: Path, preregistration: dict[str, Any]
) -> str:
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relative = str(path.relative_to(repo))
    if git_blob(repo, resolved, relative) != path.read_bytes():
        raise ValueError("preregistration differs from the committed version")
    script = "scripts/analyze_hugsim_cf_risk_causality.py"
    committed_script = git_blob(repo, resolved, script)
    if committed_script != (repo / script).read_bytes():
        raise ValueError("local analysis script differs from preregistration commit")
    if hashlib.sha256(committed_script).hexdigest() != preregistration[
        "analysis_script_sha256"
    ]:
        raise ValueError("analysis script hash differs from preregistration")
    return resolved


def state_rows(infos: list[dict[str, Any]], valid_end_s: float) -> list[dict[str, float]]:
    rows = []
    for info in infos:
        timestamp = float(info["timestamp"])
        if not (0.0 < timestamp <= valid_end_s + 1e-9):
            continue
        if len(info["obj_boxes"]) != 1:
            raise ValueError(f"t={timestamp}: expected exactly one actor")
        forward, left = actor_local_xy(info)
        rows.append(
            {
                "timestamp_s": timestamp,
                "actor_forward_m": forward,
                "actor_left_m": left,
                "ego_clearance_m": float(
                    rectangle(info["ego_box"]).distance(rectangle(info["obj_boxes"][0]))
                ),
            }
        )
    return rows


def strict_state_order(
    rows: dict[str, list[dict[str, float]]], field: str
) -> dict[str, Any]:
    indexed = {
        condition: {row["timestamp_s"]: row for row in values}
        for condition, values in rows.items()
    }
    timestamps = sorted(set.intersection(*(set(values) for values in indexed.values())))
    outcomes = []
    margins = []
    for timestamp in timestamps:
        values = {
            condition: float(indexed[condition][timestamp][field])
            for condition in CONDITIONS
        }
        first = values["nominal"] - values["slow"]
        second = values["fast"] - values["nominal"]
        margins.extend((first, second))
        outcomes.append(
            {
                "timestamp_s": timestamp,
                "values": values,
                "outcome": "expected" if first > 0.0 and second > 0.0 else "reversal_or_tie",
            }
        )
    reversals = sum(row["outcome"] != "expected" for row in outcomes)
    return {
        "field": field,
        "timestamp_count": len(timestamps),
        "expected_count": len(outcomes) - reversals,
        "reversal_or_tie_count": reversals,
        "minimum_adjacent_margin_m": float(min(margins)),
        "passed": reversals == 0,
        "outcomes": outcomes,
    }


def associated_xy(row: dict[str, Any]) -> tuple[float, float] | None:
    matches = row.get("actor_matches", [])
    if len(matches) != 1 or matches[0]["nearest_qualified"] is None:
        return None
    xy = matches[0]["nearest_qualified"]["prediction_center_vehicle_xy"]
    return float(xy[0]), float(xy[1])


def valid_receiver_rows(
    rows: list[dict[str, Any]], valid_end_s: float
) -> dict[float, dict[str, Any]]:
    return {
        float(row["timestamp_s"]): row
        for row in rows
        if 0.0 < float(row["timestamp_s"]) <= valid_end_s + 1e-9
    }


def expected_receiver_timestamps(valid_end_s: float, rate_hz: float) -> list[float]:
    step = 1.0 / rate_hz
    return [
        round(step * index, 8)
        for index in range(1, int(round(valid_end_s / step)) + 1)
    ]


def receiver_relation(
    riskier: list[dict[str, Any]], safer: list[dict[str, Any]], valid_end_s: float
) -> dict[str, Any]:
    left = valid_receiver_rows(riskier, valid_end_s)
    right = valid_receiver_rows(safer, valid_end_s)
    timestamps = sorted(set(left) & set(right))
    comparisons = []
    for timestamp in timestamps:
        left_xy, right_xy = associated_xy(left[timestamp]), associated_xy(right[timestamp])
        if left_xy is None or right_xy is None:
            comparisons.append({"timestamp_s": timestamp, "outcome": "unavailable"})
            continue
        comparisons.append(
            {
                "timestamp_s": timestamp,
                "riskier_x_m": left_xy[0],
                "safer_x_m": right_xy[0],
                "margin_m": right_xy[0] - left_xy[0],
                "outcome": "expected" if left_xy[0] < right_xy[0] else "reversal_or_tie",
            }
        )
    available = [row for row in comparisons if row["outcome"] != "unavailable"]
    expected = sum(row["outcome"] == "expected" for row in comparisons)
    reversals = sum(row["outcome"] == "reversal_or_tie" for row in comparisons)
    unavailable = sum(row["outcome"] == "unavailable" for row in comparisons)
    aggregate_expected = bool(
        available and np.median([row["margin_m"] for row in available]) > 0.0
    )
    return {
        "planned_timestamp_count": len(timestamps),
        "expected_count": expected,
        "reversal_or_tie_count": reversals,
        "unavailable_count": unavailable,
        "aggregate_direction_expected": aggregate_expected,
        "minimum_available_margin_m": (
            float(min(row["margin_m"] for row in available)) if available else None
        ),
        "comparisons": comparisons,
    }


def receiver_motion(
    rows: list[dict[str, Any]], valid_end_s: float
) -> dict[str, Any]:
    series = []
    instance_ids = []
    for timestamp, row in sorted(valid_receiver_rows(rows, valid_end_s).items()):
        xy = associated_xy(row)
        if xy is None:
            continue
        match = row["actor_matches"][0]["nearest_qualified"]
        prediction = row["predictions"][match["prediction_rank"]]
        series.append({"timestamp_s": timestamp, "receiver_x_m": xy[0]})
        if "instance_id" in prediction:
            instance_ids.append(int(prediction["instance_id"]))
    if len(series) < 2:
        return {
            "available_count": len(series),
            "slope_mps": None,
            "closing_step_count": 0,
            "nonclosing_step_count": 0,
            "dominant_instance_fraction": None,
            "series": series,
        }
    times = np.asarray([row["timestamp_s"] for row in series])
    xs = np.asarray([row["receiver_x_m"] for row in series])
    differences = np.diff(xs)
    dominant_fraction = None
    if instance_ids:
        dominant_fraction = max(instance_ids.count(value) for value in set(instance_ids)) / len(
            instance_ids
        )
    return {
        "available_count": len(series),
        "slope_mps": float(np.polyfit(times, xs, 1)[0]),
        "closing_step_count": int(np.count_nonzero(differences < 0.0)),
        "nonclosing_step_count": int(np.count_nonzero(differences >= 0.0)),
        "dominant_instance_fraction": dominant_fraction,
        "series": series,
    }


def evidence_label(state_passed: bool, receiver: dict[str, Any]) -> str:
    if not state_passed or not receiver["aggregate_direction_expected"]:
        return "rejected"
    if receiver["reversal_or_tie_count"] == 0 and receiver["unavailable_count"] == 0:
        return "accepted"
    return "down-weighted"


def make_summary(
    output: Path,
    states: dict[str, list[dict[str, float]]],
    motions: dict[str, dict[str, Any]],
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)
    for condition in CONDITIONS:
        axes[0].plot(
            [row["timestamp_s"] for row in states[condition]],
            [row["ego_clearance_m"] for row in states[condition]],
            color=COLORS[condition],
            label=DISPLAY[condition],
            linewidth=2,
        )
        series = motions[condition]["series"]
        axes[1].plot(
            [row["timestamp_s"] for row in series],
            [row["receiver_x_m"] for row in series],
            color=COLORS[condition],
            label=DISPLAY[condition],
            marker="o",
            linewidth=2,
        )
    axes[0].set(title="State: ego–actor footprint clearance", xlabel="Time (s)", ylabel="Clearance (m)")
    axes[1].set(title="Sparse4Dv3: associated longitudinal centre", xlabel="Time (s)", ylabel="Receiver x forward (m)")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    figure.suptitle("CF-R: dynamic conflict information through a frozen receiver", fontsize=15)
    figure.savefig(output, dpi=170)
    plt.close(figure)


def display_row(row: dict[str, Any]) -> dict[str, Any]:
    xy = associated_xy(row)
    if xy is None:
        return {**row, "predictions": []}
    rank = row["actor_matches"][0]["nearest_qualified"]["prediction_rank"]
    return {**row, "predictions": [row["predictions"][rank]]}


def make_contact_sheet(
    output: Path,
    predictions: dict[str, list[dict[str, Any]]],
    run_paths: dict[str, Path],
    threshold: float,
    target_s: float = 4.0,
) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(16, 4.2), constrained_layout=True)
    for axis, condition in zip(axes, CONDITIONS, strict=True):
        row = min(predictions[condition], key=lambda item: abs(float(item["timestamp_s"]) - target_s))
        frame = int(row["frame_index"])
        observations = load_pickle(run_paths[condition] / "observations.pkl")
        infos = load_pickle(run_paths[condition] / "infos.pkl")
        image = annotate_camera(
            observations[frame]["rgb"]["CAM_FRONT"],
            infos[frame],
            display_row(row),
            "CAM_FRONT",
            threshold,
            max_predictions=1,
        )
        axis.imshow(image)
        axis.set_title(f"{DISPLAY[condition]}\nt={row['timestamp_s']:.1f}s")
        axis.set_axis_off()
    figure.suptitle("Raw HUGSIM CAM_FRONT supplied to Sparse4Dv3; orange = associated receiver box")
    figure.savefig(output, dpi=160)
    plt.close(figure)


def make_video(
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
    tile_w, tile_h = 640, 360
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"mp4v"), 2.0, (tile_w * 3, tile_h)
    )
    if not writer.isOpened():
        raise RuntimeError(f"could not open video writer: {output}")
    try:
        for index in range(frame_count):
            tiles = []
            for condition in CONDITIONS:
                row = predictions[condition][index]
                frame = int(row["frame_index"])
                image = annotate_camera(
                    observations[condition][frame]["rgb"]["CAM_FRONT"],
                    infos[condition][frame],
                    display_row(row),
                    "CAM_FRONT",
                    threshold,
                    max_predictions=1,
                )
                tile = cv2.resize(image, (tile_w, tile_h), interpolation=cv2.INTER_AREA)
                cv2.putText(tile, DISPLAY[condition], (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
                tiles.append(tile)
            writer.write(cv2.cvtColor(np.concatenate(tiles, axis=1), cv2.COLOR_RGB2BGR))
    finally:
        writer.release()


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.resolve()
    preregistration = load_json(preregistration_path)
    verify_preregistration(
        repo, args.preregistration_commit, preregistration_path, preregistration
    )
    if preregistration["audit_id"] != "hugsim_cf_risk_causality_001":
        raise ValueError("unexpected audit ID")

    run_paths = {
        condition: (repo / preregistration["conditions"][condition]["output"]).resolve()
        for condition in CONDITIONS
    }
    for condition, path in run_paths.items():
        spec = preregistration["conditions"][condition]
        for filename, expected in spec["input_sha256"].items():
            if sha256_file(path / filename) != expected:
                raise ValueError(f"{condition}: {filename} hash differs")
        if hashlib.sha256(
            git_blob(repo, args.preregistration_commit, spec["config"])
        ).hexdigest() != spec["config_sha256"]:
            raise ValueError(f"{condition}: committed config hash differs")

    valid_end_s = float(preregistration["complete_future_window"]["valid_end_inclusive_s"])
    states = {
        condition: state_rows(load_pickle(path / "infos.pkl"), valid_end_s)
        for condition, path in run_paths.items()
    }
    state_forward = strict_state_order(states, "actor_forward_m")
    state_clearance = strict_state_order(states, "ego_clearance_m")
    state_passed = state_forward["passed"] and state_clearance["passed"]

    receiver_root = args.receiver_output.resolve()
    receiver_manifest = load_json(receiver_root / "manifest.json")
    receiver_contract = preregistration["receiver"]
    model = receiver_manifest["model"]
    if model["source_git_commit"] != receiver_contract["source_commit"]:
        raise ValueError("Sparse4D source commit differs")
    if model["checkpoint_sha256"] != receiver_contract["checkpoint_sha256"]:
        raise ValueError("Sparse4D checkpoint differs")
    if model["config_sha256"] != receiver_contract["config_sha256"]:
        raise ValueError("Sparse4D config differs")
    if model.get("runner_sha256") != receiver_contract["runner_sha256"]:
        raise ValueError("receiver runner hash differs")
    if int(receiver_manifest["receiver_input"]["frame_stride"]) != int(
        receiver_contract["frame_stride"]
    ):
        raise ValueError("receiver frame stride differs")
    receiver_input = receiver_manifest["receiver_input"]
    if receiver_input["camera_order"] != receiver_contract["camera_order"]:
        raise ValueError("receiver camera order differs")
    if receiver_input["modalities"] != receiver_contract["modalities"]:
        raise ValueError("receiver modalities differ")
    if receiver_input["explicitly_excluded"] != receiver_contract[
        "excluded_modalities"
    ]:
        raise ValueError("receiver excluded modalities differ")

    predictions = {
        condition: load_json(
            receiver_root / receiver_manifest["runs"][condition]["predictions"]
        )
        for condition in CONDITIONS
    }
    expected_timestamps = expected_receiver_timestamps(
        valid_end_s, float(receiver_input["receiver_rate_hz"])
    )
    for condition in CONDITIONS:
        run_manifest = receiver_manifest["runs"][condition]
        if Path(run_manifest["source"]).resolve() != run_paths[condition]:
            raise ValueError(f"{condition}: receiver source path differs")
        if float(run_manifest["summary"]["score_threshold"]) != float(
            receiver_contract["score_threshold"]
        ):
            raise ValueError(f"{condition}: receiver threshold differs")
        actual_timestamps = sorted(
            valid_receiver_rows(predictions[condition], valid_end_s)
        )
        if actual_timestamps != expected_timestamps:
            raise ValueError(
                f"{condition}: receiver timestamp set differs from the complete expected set"
            )
    relations = {}
    for riskier, safer in RELATIONS:
        receiver = receiver_relation(predictions[riskier], predictions[safer], valid_end_s)
        relations[f"{riskier}>{safer}"] = {
            "riskier": riskier,
            "safer": safer,
            "receiver": receiver,
            "evidence_label": evidence_label(state_passed, receiver),
        }
    motions = {
        condition: receiver_motion(predictions[condition], valid_end_s)
        for condition in CONDITIONS
    }
    slopes = {condition: motions[condition]["slope_mps"] for condition in CONDITIONS}
    slope_order_passed = bool(
        all(value is not None for value in slopes.values())
        and slopes["slow"] < slopes["nominal"] < slopes["fast"]
    )
    labels = [result["evidence_label"] for result in relations.values()]
    overall = "accepted" if all(label == "accepted" for label in labels) and slope_order_passed else "down-weighted"
    if any(label == "rejected" for label in labels) or not state_passed:
        overall = "rejected"

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    summary = {
        "audit_id": preregistration["audit_id"],
        "preregistration_commit": args.preregistration_commit,
        "complete_future_window": preregistration["complete_future_window"],
        "state_forward_order": state_forward,
        "state_clearance_order": state_clearance,
        "relations": relations,
        "receiver_motion": motions,
        "receiver_closure_slope_order": {
            "expected": "slow < nominal < fast (more negative means stronger closure)",
            "slopes_mps": slopes,
            "passed": slope_order_passed,
            "evidence_boundary": "directional diagnostic; Sparse4Dv3 metric velocity/distance is not calibrated HUGSIM truth",
        },
        "overall_segment_evidence_label": overall,
        "strongest_allowed_claim": preregistration["strongest_allowed_claim"],
        "forbidden_claims": preregistration["forbidden_claims"],
    }
    (output / "cf_risk_causality_audit.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    threshold = float(receiver_contract["score_threshold"])
    make_summary(output / "cf_risk_causality_summary.png", states, motions)
    make_contact_sheet(output / "cf_risk_receiver_contact_sheet.png", predictions, run_paths, threshold)
    make_video(output / "cf_risk_receiver_comparison.mp4", predictions, run_paths, threshold)
    print(json.dumps({"overall": overall, "relations": labels, "slopes_mps": slopes}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
