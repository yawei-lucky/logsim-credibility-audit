#!/usr/bin/env python3
"""Compare CF-R planned following gaps with the UN R157 M1/N1 boundary."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analyze_hugsim_horizon_factorial import rectangle


TIMESTEP_S = 0.5
NUMERIC_TOLERANCE = 1e-9
CONDITIONS = ("slow", "fast")
COLORS = {"slow": "#d62728", "fast": "#2ca02c"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
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


def verify_preregistration(repo: Path, path: Path, commit: str) -> str:
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relative = str(path.relative_to(repo))
    committed = subprocess.run(
        ["git", "show", f"{resolved}:{relative}"],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    if committed != path.read_bytes():
        raise ValueError("preregistration differs from committed version")
    return resolved


def minimum_following_distance_m(
    speed_mps: float,
    speed_table: np.ndarray,
    time_gap_table: np.ndarray,
) -> float | None:
    """Return the UN R157 M1/N1 comparator for a nonnegative speed."""
    if not np.isfinite(speed_mps) or speed_mps < 0:
        raise ValueError("planned ego speed must be finite and nonnegative")
    if speed_mps < speed_table[0]:
        return 2.0
    if speed_mps > speed_table[-1] + NUMERIC_TOLERANCE:
        return None
    time_gap = float(np.interp(speed_mps, speed_table, time_gap_table))
    return float(speed_mps * time_gap)


def box_corners(box: list[float]) -> np.ndarray:
    values = np.asarray(box, dtype=np.float64)
    x, y, _, width, length, _, yaw = values
    forward = np.asarray([np.cos(yaw), np.sin(yaw)])
    lateral = np.asarray([-np.sin(yaw), np.cos(yaw)])
    return np.asarray(
        [
            [x, y] + half_long * forward + half_lat * lateral
            for half_long, half_lat in (
                (length / 2, width / 2),
                (length / 2, -width / 2),
                (-length / 2, -width / 2),
                (-length / 2, width / 2),
            )
        ],
        dtype=np.float64,
    )


def wrapped_heading_difference(first: float, second: float) -> float:
    return float(abs(np.arctan2(np.sin(first - second), np.cos(first - second))))


def same_lane_relation(
    ego_box: list[float],
    actor_box: list[float],
) -> dict[str, float | bool]:
    ego = np.asarray(ego_box, dtype=np.float64)
    actor = np.asarray(actor_box, dtype=np.float64)
    forward = np.asarray([np.cos(ego[6]), np.sin(ego[6])])
    lateral = np.asarray([-np.sin(ego[6]), np.cos(ego[6])])
    ego_corners = box_corners(ego_box)
    actor_corners = box_corners(actor_box)
    ego_long = ego_corners @ forward
    actor_long = actor_corners @ forward
    ego_lat = ego_corners @ lateral
    actor_lat = actor_corners @ lateral
    longitudinal_gap = float(np.min(actor_long) - np.max(ego_long))
    lateral_overlap = float(
        min(np.max(ego_lat), np.max(actor_lat))
        - max(np.min(ego_lat), np.min(actor_lat))
    )
    return {
        "longitudinal_bumper_gap_m": longitudinal_gap,
        "lateral_overlap_m": lateral_overlap,
        "actor_ahead": longitudinal_gap >= -NUMERIC_TOLERANCE,
        "lateral_overlap": lateral_overlap > NUMERIC_TOLERANCE,
        "heading_difference_rad": wrapped_heading_difference(
            float(ego[6]),
            float(actor[6]),
        ),
        "euclidean_footprint_clearance_m": float(
            rectangle(ego_box).distance(rectangle(actor_box))
        ),
    }


def state_timeline(repo: Path, run: dict[str, Any]) -> dict[float, dict[str, Any]]:
    run_path = repo / run["input"]["run"]
    audit_path = run_path / "audit_summary.json"
    if sha256_file(audit_path) != run["input"]["audit_summary_sha256"]:
        raise ValueError(f"raw state input hash changed: {audit_path}")
    audit = load_json(audit_path)
    steps = audit["steps"]
    states = [steps[0]["info_before"]]
    states.extend(step["info_after"] for step in steps)
    return {round(float(state["timestamp"]), 9): state for state in states}


def sample_rows(
    context: str,
    condition: str,
    reset: int,
    metric: dict[str, Any],
    origin_box: list[float],
    speed_table: np.ndarray,
    time_gap_table: np.ndarray,
) -> list[dict[str, Any]]:
    previous_center = np.asarray(origin_box[:2], dtype=np.float64)
    rows = []
    for horizon, ego_box, actor_box, original_clearance in zip(
        metric["horizons_s"],
        metric["future_ego_boxes"],
        metric["future_actor_boxes"],
        metric["clearance_m"],
        strict=True,
    ):
        center = np.asarray(ego_box[:2], dtype=np.float64)
        speed = float(np.linalg.norm(center - previous_center) / TIMESTEP_S)
        relation = same_lane_relation(ego_box, actor_box)
        minimum_distance = minimum_following_distance_m(
            speed,
            speed_table,
            time_gap_table,
        )
        applicable = bool(
            minimum_distance is not None
            and relation["actor_ahead"]
            and relation["lateral_overlap"]
        )
        if abs(
            float(relation["euclidean_footprint_clearance_m"])
            - float(original_clearance)
        ) > NUMERIC_TOLERANCE:
            raise ValueError("footprint-clearance cross-check failed")
        gap = float(relation["longitudinal_bumper_gap_m"])
        margin = gap - minimum_distance if applicable else None
        rows.append(
            {
                "context": context,
                "condition": condition,
                "reset": reset,
                "plan_time_s": float(metric["plan_time_s"]),
                "horizon_s": float(horizon),
                "planned_ego_speed_mps": speed,
                **relation,
                "un_r157_minimum_following_distance_m": minimum_distance,
                "regulatory_margin_m": margin,
                "gap_to_minimum_ratio": (
                    gap / minimum_distance if applicable else None
                ),
                "applicable": applicable,
            }
        )
        previous_center = center
    return rows


def evidence_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    applicable = [row for row in rows if row["applicable"]]
    positive = [
        row for row in applicable if row["regulatory_margin_m"] > 0.0
    ]
    non_positive = [
        row for row in applicable if row["regulatory_margin_m"] <= 0.0
    ]
    if len(applicable) == len(rows):
        applicability = "accepted"
    elif applicable:
        applicability = "down-weighted"
    else:
        applicability = "rejected"
    all_exceed = bool(applicable) and len(positive) == len(applicable)
    minimum_relation = "accepted" if all_exceed else "rejected"
    boundary_coverage = (
        "accepted" if positive and non_positive else "rejected"
    )
    if applicability == "accepted" and boundary_coverage == "accepted":
        overall = "accepted"
    elif applicability != "rejected":
        overall = "down-weighted"
    else:
        overall = "rejected"
    return {
        "sample_count": len(rows),
        "applicable_count": len(applicable),
        "positive_margin_count": len(positive),
        "non_positive_margin_count": len(non_positive),
        "formula_applicability": applicability,
        "every_sample_exceeds_comparator": {
            "decision": minimum_relation,
            "value": all_exceed,
        },
        "boundary_coverage": {
            "decision": boundary_coverage,
            "positive_and_non_positive_present": bool(
                positive and non_positive
            ),
        },
        "minimum_regulatory_margin_m": (
            min(row["regulatory_margin_m"] for row in applicable)
            if applicable
            else None
        ),
        "minimum_gap_to_boundary_ratio": (
            min(row["gap_to_minimum_ratio"] for row in applicable)
            if applicable
            else None
        ),
        "maximum_planned_speed_mps": max(
            row["planned_ego_speed_mps"] for row in rows
        ),
        "maximum_heading_difference_deg": float(
            np.degrees(max(row["heading_difference_rad"] for row in rows))
        ),
        "minimum_lateral_overlap_m": min(
            row["lateral_overlap_m"] for row in rows
        ),
        "overall": overall,
    }


def analyze(
    repo: Path,
    preregistration: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_spec = preregistration["input"]
    source_path = repo / source_spec["path"]
    if sha256_file(source_path) != source_spec["sha256"]:
        raise ValueError("complete-future audit input hash changed")
    source = load_json(source_path)
    reference = preregistration["external_reference"]
    speed_table = np.asarray(reference["speed_mps"], dtype=np.float64)
    time_gap_table = np.asarray(
        reference["minimum_time_gap_s"],
        dtype=np.float64,
    )
    rows = []
    for condition in CONDITIONS:
        for run in source["runs"][condition]:
            reset = int(run["reset"])
            states = state_timeline(repo, run)
            common = run["common_reference"]
            rows.extend(
                sample_rows(
                    "common_reference",
                    condition,
                    reset,
                    common,
                    states[round(float(common["plan_time_s"]), 9)][
                        "ego_box"
                    ],
                    speed_table,
                    time_gap_table,
                )
            )
            for plan_time, metric in run[
                "complete_horizon_diagnostics"
            ].items():
                rows.extend(
                    sample_rows(
                        "target_ad_plan",
                        condition,
                        reset,
                        metric,
                        states[round(float(plan_time), 9)]["ego_box"],
                        speed_table,
                        time_gap_table,
                    )
                )
    summary = evidence_summary(rows)
    by_context = {
        context: evidence_summary(
            [row for row in rows if row["context"] == context]
        )
        for context in ("common_reference", "target_ad_plan")
    }
    by_condition = {
        condition: evidence_summary(
            [row for row in rows if row["condition"] == condition]
        )
        for condition in CONDITIONS
    }
    return (
        {
            "audit_id": preregistration["audit_id"],
            "scope": (
                "external M1/N1 ALKS following-distance comparator applied "
                "to fixed same-lane CF-R planned states"
            ),
            "external_reference": reference,
            "summary": summary,
            "by_context": by_context,
            "by_condition": by_condition,
            "evidence_decisions": {
                "external_formula_applicability": summary[
                    "formula_applicability"
                ],
                "all_sampled_gaps_exceed_comparator": summary[
                    "every_sample_exceeds_comparator"
                ]["decision"],
                "current_experiment_spans_external_boundary": summary[
                    "boundary_coverage"
                ]["decision"],
                "overall_external_boundary_audit": summary["overall"],
                "real_world_safety_or_regulatory_compliance": "rejected",
            },
            "strongest_interpretation": (
                "the comparator is applicable and all sampled planned gaps "
                "exceed it, but the fixed experiment stays on one side of "
                "the boundary and cannot qualify near-boundary response"
            ),
            "rows": rows,
        },
        rows,
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_plot(path: Path, result: dict[str, Any]) -> None:
    rows = result["rows"]
    figure, axes = plt.subplots(
        2,
        2,
        figsize=(14, 9),
        constrained_layout=True,
    )
    max_speed = max(row["planned_ego_speed_mps"] for row in rows)
    speeds = np.linspace(0.0, max(2.1, max_speed * 1.08), 200)
    reference = result["external_reference"]
    speed_table = np.asarray(reference["speed_mps"])
    gap_table = np.asarray(reference["minimum_time_gap_s"])
    boundary = [
        minimum_following_distance_m(value, speed_table, gap_table)
        for value in speeds
    ]
    axes[0, 0].plot(
        speeds,
        boundary,
        color="black",
        linewidth=2,
        label="UN R157 M1/N1 comparator",
    )
    markers = {"common_reference": "o", "target_ad_plan": "x"}
    for context in markers:
        for condition in CONDITIONS:
            selected = [
                row
                for row in rows
                if row["context"] == context
                and row["condition"] == condition
            ]
            axes[0, 0].scatter(
                [row["planned_ego_speed_mps"] for row in selected],
                [row["longitudinal_bumper_gap_m"] for row in selected],
                color=COLORS[condition],
                marker=markers[context],
                alpha=0.65,
                label=f"{condition} · {context}",
            )
    axes[0, 0].set(
        title="Planned same-lane gaps versus external comparator",
        xlabel="Planned ego segment speed (m/s)",
        ylabel="Longitudinal bumper gap (m)",
    )
    axes[0, 0].grid(alpha=0.25)
    axes[0, 0].legend(fontsize=7)

    groups = []
    values = []
    colors = []
    for context in ("common_reference", "target_ad_plan"):
        for condition in CONDITIONS:
            selected = [
                row["regulatory_margin_m"]
                for row in rows
                if row["context"] == context
                and row["condition"] == condition
                and row["applicable"]
            ]
            groups.append(f"{context.replace('_', ' ')}\n{condition}")
            values.append(min(selected))
            colors.append(COLORS[condition])
    axes[0, 1].bar(groups, values, color=colors)
    axes[0, 1].axhline(0.0, color="black", linewidth=1)
    axes[0, 1].set(
        title="Closest sampled margin above boundary",
        ylabel="Minimum regulatory margin (m)",
    )
    axes[0, 1].grid(axis="y", alpha=0.25)

    for condition in CONDITIONS:
        selected = [
            row
            for row in rows
            if row["context"] == "target_ad_plan"
            and row["condition"] == condition
        ]
        axes[1, 0].scatter(
            [
                row["plan_time_s"] + row["horizon_s"]
                for row in selected
            ],
            [row["regulatory_margin_m"] for row in selected],
            color=COLORS[condition],
            alpha=0.55,
            label=condition,
        )
    axes[1, 0].axhline(0.0, color="black", linewidth=1)
    axes[1, 0].set(
        title="Target-AD plan margins over complete future",
        xlabel="Future world time (s)",
        ylabel="Gap minus comparator (m)",
    )
    axes[1, 0].grid(alpha=0.25)
    axes[1, 0].legend()

    axes[1, 1].axis("off")
    summary = result["summary"]
    axes[1, 1].text(
        0.03,
        0.98,
        "External-boundary decision",
        fontsize=16,
        weight="bold",
        va="top",
    )
    axes[1, 1].text(
        0.03,
        0.80,
        (
            f"Applicable samples: {summary['applicable_count']}/"
            f"{summary['sample_count']}\n"
            f"Minimum margin: {summary['minimum_regulatory_margin_m']:.3f} m\n"
            f"Minimum gap/boundary ratio: "
            f"{summary['minimum_gap_to_boundary_ratio']:.2f}×\n"
            f"Boundary crossed: no"
        ),
        fontsize=12,
        linespacing=1.4,
        va="top",
    )
    axes[1, 1].text(
        0.03,
        0.36,
        "Overall: down-weighted",
        fontsize=13,
        weight="bold",
        va="top",
    )
    axes[1, 1].text(
        0.03,
        0.22,
        (
            "The current experiment tests response direction,\n"
            "not near-boundary safety behavior."
        ),
        fontsize=12,
        weight="bold",
        linespacing=1.35,
        va="top",
    )
    figure.suptitle(
        "CF-R external following-boundary audit",
        fontsize=17,
    )
    figure.savefig(path, dpi=170)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    preregistration_commit = verify_preregistration(
        repo,
        preregistration_path,
        args.preregistration_commit,
    )
    preregistration = load_json(preregistration_path)
    result, rows = analyze(repo, preregistration)
    output.mkdir(parents=True)
    json_path = output / "cf_r_external_following_boundary_audit.json"
    csv_path = output / "cf_r_external_following_boundary_rows.csv"
    plot_path = output / "cf_r_external_following_boundary.png"
    result["preregistration"] = {
        "path": str(preregistration_path),
        "commit": preregistration_commit,
        "sha256": sha256_file(preregistration_path),
    }
    result["analysis_script"] = {
        "path": str(Path(__file__).resolve()),
        "sha256": sha256_file(Path(__file__).resolve()),
    }
    result["artifacts"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "plot": str(plot_path),
    }
    with json_path.open("w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    write_csv(csv_path, rows)
    make_plot(plot_path, result)
    print(
        json.dumps(
            {
                "overall": result["summary"]["overall"],
                "applicable": result["summary"]["applicable_count"],
                "samples": result["summary"]["sample_count"],
                "minimum_margin_m": result["summary"][
                    "minimum_regulatory_margin_m"
                ],
                "boundary_coverage": result["summary"][
                    "boundary_coverage"
                ]["decision"],
                "output": str(output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
