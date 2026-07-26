#!/usr/bin/env python3
"""Audit the preregistered CF-R external-boundary response pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
import subprocess
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

from analyze_hugsim_cf_r_future_conflict import world_boxes_from_plan
from audit_cf_r_external_following_boundary import same_lane_relation


CONDITIONS = ("above", "near", "below")
COLORS = {"above": "#2ca02c", "near": "#ff7f0e", "below": "#d62728"}
HORIZONS_S = np.arange(1, 7, dtype=np.float64) * 0.5
BOUNDARY_M = 2.0
TOLERANCE = 1e-9
ACTION_PATTERN = re.compile(
    r"steer_rate=(?P<value>[-+0-9.eE]+) is outside HUGSIM action bounds "
    r"\[(?P<lower>[-+0-9.eE]+), (?P<upper>[-+0-9.eE]+)\]"
)
STEP_PATTERN = re.compile(r"\[debug-smoke\] step=(?P<step>\d+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--receiver", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def load_pickle(path: Path) -> Any:
    with path.open("rb") as stream:
        return pickle.load(stream)


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


def state_timeline(audit: dict[str, Any]) -> dict[float, dict[str, Any]]:
    steps = audit["steps"]
    states = [steps[0]["info_before"]]
    states.extend(step["info_after"] for step in steps)
    timeline = {round(float(state["timestamp"]), 9): state for state in states}
    expected = np.arange(0.0, 4.5 + 0.125, 0.25)
    if not np.allclose(sorted(timeline), expected, atol=TOLERANCE):
        raise ValueError("future state timeline is incomplete")
    return timeline


def rgb_digest(observation: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for camera in sorted(observation["rgb"]):
        digest.update(camera.encode())
        digest.update(np.ascontiguousarray(observation["rgb"][camera]).tobytes())
    return digest.hexdigest()


def state_residual(first: dict[str, Any], second: dict[str, Any]) -> float:
    fields = ("ego_box", "ego_pos", "ego_rot", "ego_velo", "ego_steer")
    values = [
        np.max(
            np.abs(
                np.asarray(first[field], dtype=np.float64)
                - np.asarray(second[field], dtype=np.float64)
            )
        )
        for field in fields
    ]
    values.append(
        np.max(
            np.abs(
                np.asarray(first["obj_boxes"], dtype=np.float64)
                - np.asarray(second["obj_boxes"], dtype=np.float64)
            )
        )
    )
    return float(max(values))


def conflict_rows(
    plan: np.ndarray,
    timeline: dict[float, dict[str, Any]],
) -> list[dict[str, Any]]:
    origin = timeline[1.5]
    ego_boxes = world_boxes_from_plan(plan, origin["ego_box"])
    rows = []
    previous = np.asarray(origin["ego_box"][:2], dtype=np.float64)
    for horizon, ego_box in zip(HORIZONS_S, ego_boxes, strict=True):
        actor_box = timeline[round(1.5 + float(horizon), 9)]["obj_boxes"][0]
        relation = same_lane_relation(ego_box, actor_box)
        center = np.asarray(ego_box[:2], dtype=np.float64)
        speed = float(np.linalg.norm(center - previous) / 0.5)
        applicable = bool(
            speed < 2.0 + TOLERANCE
            and relation["actor_ahead"]
            and relation["lateral_overlap"]
        )
        rows.append(
            {
                "horizon_s": float(horizon),
                "planned_speed_mps": speed,
                "gap_m": float(relation["longitudinal_bumper_gap_m"]),
                "margin_m": (
                    float(relation["longitudinal_bumper_gap_m"]) - BOUNDARY_M
                    if applicable
                    else None
                ),
                "applicable": applicable,
                "ego_box": ego_box,
                "actor_box": actor_box,
            }
        )
        previous = center
    return rows


def live_failure(repo: Path, spec: dict[str, Any]) -> dict[str, Any]:
    output = repo / spec["closed_loop_output"]
    log_path = output.with_name(output.name + ".runner.log")
    text = log_path.read_text(encoding="utf-8")
    actions = list(ACTION_PATTERN.finditer(text))
    steps = [int(match.group("step")) for match in STEP_PATTERN.finditer(text)]
    if len(actions) != 1:
        raise ValueError(f"expected one strict-action failure in {log_path}")
    action = actions[0]
    return {
        "completed_environment_steps_before_failure": (
            max(steps) + 1 if steps else 0
        ),
        "last_completed_timestamp_s": (
            1.5 + 0.25 * (max(steps) + 1) if steps else 1.5
        ),
        "requested_steer_rate_radps": float(action.group("value")),
        "lower_bound_radps": float(action.group("lower")),
        "upper_bound_radps": float(action.group("upper")),
        "strict_action_interface_completed": False,
        "runner_log": str(log_path),
        "runner_log_sha256": sha256_file(log_path),
    }


def analyze(
    repo: Path,
    preregistration: dict[str, Any],
    receiver_path: Path,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    receiver = load_json(receiver_path / "runtime_smoke.json")
    by_receiver = {item["label"]: item for item in receiver["conditions"]}
    if set(by_receiver) != set(CONDITIONS):
        raise ValueError("receiver conditions differ from preregistration")
    if not receiver["all_outputs_finite"] or not receiver[
        "all_resets_reproducible"
    ]:
        raise ValueError("receiver qualification gate failed")

    import torch

    results: dict[str, Any] = {}
    images: dict[str, np.ndarray] = {}
    for condition in CONDITIONS:
        spec = preregistration["conditions"][condition]
        config = repo / spec["config"]
        if sha256_file(config) != spec["config_sha256"]:
            raise ValueError(f"{condition}: config changed")
        source = repo / spec["source_output"]
        future = repo / "artifacts" / "sparsedrive_cf_r_boundary" / (
            f"state-{condition}-run001"
        )
        source_audit = load_json(source / "audit_summary.json")
        future_audit = load_json(future / "audit_summary.json")
        if source_audit["run_status"] != "complete" or future_audit[
            "run_status"
        ] != "complete":
            raise ValueError(f"{condition}: source state run incomplete")
        source_infos = load_pickle(source / "infos.pkl")
        future_infos = load_pickle(future / "infos.pkl")
        source_observations = load_pickle(source / "observations.pkl")
        future_observations = load_pickle(future / "observations.pkl")
        maximum_state_residual = max(
            state_residual(source_infos[index], future_infos[index])
            for index in range(7)
        )
        rgb_equal = all(
            rgb_digest(source_observations[index])
            == rgb_digest(future_observations[index])
            for index in range(7)
        )
        if maximum_state_residual > TOLERANCE or not rgb_equal:
            raise ValueError(f"{condition}: source/future prefix mismatch")
        timeline = state_timeline(future_audit)
        handoff = timeline[1.5]
        common_plan = np.stack(
            (
                np.zeros(6, dtype=np.float64),
                HORIZONS_S * float(handoff["ego_velo"]),
            ),
            axis=1,
        )
        native_path = receiver_path / f"{condition}_native_outputs.pt"
        native = torch.load(
            native_path,
            map_location="cpu",
            weights_only=False,
        )
        target_plan = native[3]["final_planning"].numpy().astype(np.float64)
        common = conflict_rows(common_plan, timeline)
        target = conflict_rows(target_plan, timeline)
        if not all(row["applicable"] for row in common):
            raise ValueError(f"{condition}: common boundary comparator inapplicable")
        applicable_target = [row for row in target if row["applicable"]]
        if not applicable_target:
            raise ValueError(f"{condition}: target plan has no applicable state")
        receiver_record = by_receiver[condition]
        frame = receiver_record["frames"][3]
        result = {
            "target_gap_m": float(spec["target_common_path_gap_m"]),
            "common_reference": {
                "minimum_gap_m": min(row["gap_m"] for row in common),
                "minimum_margin_m": min(row["margin_m"] for row in common),
                "rows": common,
            },
            "target_ad": {
                "selected_mode": int(
                    frame["planning_selection"]["selected_mode_index"]
                ),
                "plan_right_forward_m": target_plan.tolist(),
                "forward_endpoint_m": float(target_plan[-1, 1]),
                "lateral_endpoint_m": float(target_plan[-1, 0]),
                "applicable_horizon_count": len(applicable_target),
                "minimum_applicable_gap_m": min(
                    row["gap_m"] for row in applicable_target
                ),
                "minimum_applicable_margin_m": min(
                    row["margin_m"] for row in applicable_target
                ),
                "rows": target,
            },
            "diagnostic_valid_prefix_response_gain_m": (
                min(row["gap_m"] for row in applicable_target)
                - min(row["gap_m"] for row in common)
            ),
            "source_future_prefix": {
                "maximum_state_residual": maximum_state_residual,
                "rgb_byte_equal": rgb_equal,
            },
            "receiver_reset_max_plan_difference_m": float(
                receiver_record["reset_check"]["max_abs_differences"][
                    "final_planning"
                ]
            ),
            "live_failure": live_failure(repo, spec),
            "input_hashes": {
                "source_audit": sha256_file(source / "audit_summary.json"),
                "future_audit": sha256_file(future / "audit_summary.json"),
                "native_output": sha256_file(native_path),
            },
        }
        results[condition] = result
        images[condition] = source_observations[6]["rgb"]["CAM_FRONT"]

    common_gaps = [results[key]["common_reference"]["minimum_gap_m"] for key in CONDITIONS]
    response_gains = [
        results[key]["diagnostic_valid_prefix_response_gain_m"]
        for key in CONDITIONS
    ]
    forward_endpoints = [results[key]["target_ad"]["forward_endpoint_m"] for key in CONDITIONS]
    target_tolerance = all(
        abs(results[key]["common_reference"]["minimum_gap_m"] - results[key]["target_gap_m"])
        <= 0.05
        for key in CONDITIONS
    )
    stimulus_order = common_gaps[2] < common_gaps[1] < common_gaps[0]
    coverage = (
        results["above"]["common_reference"]["minimum_margin_m"] > 0
        and abs(results["near"]["common_reference"]["minimum_margin_m"]) <= 0.05
        and results["below"]["common_reference"]["minimum_margin_m"] < 0
    )
    complete_target_applicability = all(
        results[key]["target_ad"]["applicable_horizon_count"] == 6
        for key in CONDITIONS
    )
    response_order = response_gains[2] >= response_gains[1] >= response_gains[0]
    endpoint_order = forward_endpoints[2] < forward_endpoints[1] < forward_endpoints[0]
    modes = {results[key]["target_ad"]["selected_mode"] for key in CONDITIONS}
    same_mode = len(modes) == 1
    longitudinal_response = (
        target_tolerance
        and stimulus_order
        and coverage
        and endpoint_order
        and same_mode
    )
    clearance_response = (
        longitudinal_response
        and complete_target_applicability
        and response_order
    )
    result = {
        "audit_id": preregistration["audit_id"],
        "scope": "one-reset boundary-response pilot with exact future actor states",
        "conditions": results,
        "aggregate": {
            "common_gap_order_above_near_below_m": common_gaps,
            "response_gain_order_above_near_below_m": response_gains,
            "target_forward_endpoint_above_near_below_m": forward_endpoints,
            "selected_modes": sorted(modes),
            "stimulus_target_tolerance_passed": target_tolerance,
            "stimulus_order_passed": stimulus_order,
            "external_boundary_coverage_passed": coverage,
            "complete_target_plan_applicability_passed": (
                complete_target_applicability
            ),
            "valid_prefix_response_gain_order_diagnostic": response_order,
            "open_loop_forward_endpoint_order_passed": endpoint_order,
            "same_selected_mode_passed": same_mode,
            "strict_action_interface_completion_count": 0,
        },
        "evidence_decisions": {
            "source_and_feasibility_gate": "accepted",
            "external_boundary_stimulus_coverage": (
                "accepted" if target_tolerance and stimulus_order and coverage else "rejected"
            ),
            "shared_handoff_longitudinal_endpoint_direction": (
                "accepted" if longitudinal_response else "rejected"
            ),
            "preregistered_complete_clearance_response_gain": (
                "accepted" if clearance_response else "rejected"
            ),
            "strict_action_compatible_closed_loop_completion": "rejected",
            "overall_boundary_response_pilot": "down-weighted",
            "real_world_response_magnitude_or_safety": "rejected",
        },
        "strongest_interpretation": (
            "the designed boundary-spanning stimulus produced a strictly "
            "ordered same-mode longitudinal SparseDrive plan, but the "
            "near-stop heading convention invalidated the complete clearance "
            "gain in two conditions and every closed-loop condition later "
            "requested steering outside the qualified HUGSIM action interface"
        ),
        "excluded": {
            "hugsim_nc_ttc_pdms": (
                "not used: the state-only runs invoke HUGSIM's internal "
                "future scorer and are not target-AD outcomes"
            ),
            "failed_run_final_states": (
                "not compared because the three strict-interface runs stop "
                "at different timestamps"
            ),
            "invalid_target_plan_tail": (
                "near and below have only five of six applicable gap samples: "
                "centimetre-scale final motion makes successive-point heading "
                "unstable and removes lateral footprint overlap"
            ),
        },
    }
    return result, images


def make_plot(
    path: Path,
    analysis: dict[str, Any],
    images: dict[str, np.ndarray],
) -> None:
    figure, axes = plt.subplots(
        2,
        3,
        figsize=(16, 8.5),
        constrained_layout=True,
    )
    for column, condition in enumerate(CONDITIONS):
        result = analysis["conditions"][condition]
        axes[0, column].imshow(images[condition])
        axes[0, column].set_title(
            f"{condition.upper()} · common gap "
            f"{result['common_reference']['minimum_gap_m']:.1f} m"
        )
        axes[0, column].axis("off")

        axis = axes[1, column]
        target = result["target_ad"]["rows"]
        common = result["common_reference"]["rows"]
        target_plan = np.asarray(
            result["target_ad"]["plan_right_forward_m"],
            dtype=np.float64,
        )
        common_plan = np.asarray(
            [
                [0.0, row["horizon_s"] * common[0]["planned_speed_mps"]]
                for row in common
            ]
        )
        axis.plot(
            common_plan[:, 0],
            common_plan[:, 1],
            "--",
            color="#666666",
            label="common path",
        )
        axis.plot(
            target_plan[:, 0],
            target_plan[:, 1],
            "o-",
            color=COLORS[condition],
            label="SparseDrive plan",
        )
        actor = target[-1]["actor_box"]
        origin = np.asarray(common[0]["ego_box"])
        actor_forward = float(actor[0] - (origin[0] - common[0]["planned_speed_mps"] * 0.5))
        actor_right = float(-(actor[1] - origin[1]))
        axis.add_patch(
            Rectangle(
                (actor_right - actor[3] / 2, actor_forward - actor[4] / 2),
                actor[3],
                actor[4],
                facecolor="#999999",
                edgecolor="black",
                alpha=0.65,
                label="actor at +3 s",
            )
        )
        axis.set(
            title=(
                "valid-prefix gain "
                f"{result['diagnostic_valid_prefix_response_gain_m']:.2f} m · "
                f"failure after {result['live_failure']['last_completed_timestamp_s']:.2f} s"
            ),
            xlabel="right (m)",
            ylabel="forward from handoff (m)",
            xlim=(-4.5, 4.5),
            ylim=(-0.5, 16.5),
        )
        axis.grid(alpha=0.25)
        axis.set_aspect("equal", adjustable="box")
        if column == 0:
            axis.legend(fontsize=8, loc="upper left")
    figure.suptitle(
        "CF-R boundary pilot: valid open-loop ordering, closed-loop interface saturation",
        fontsize=16,
    )
    figure.savefig(path, dpi=170)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.expanduser().resolve()
    receiver_path = args.receiver.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    commit = verify_preregistration(
        repo,
        preregistration_path,
        args.preregistration_commit,
    )
    preregistration = load_json(preregistration_path)
    analysis, images = analyze(repo, preregistration, receiver_path)
    output.mkdir(parents=True)
    json_path = output / "cf_r_boundary_response_audit.json"
    plot_path = output / "cf_r_boundary_response_summary.png"
    analysis["preregistration"] = {
        "path": str(preregistration_path),
        "commit": commit,
        "sha256": sha256_file(preregistration_path),
    }
    analysis["analysis_script"] = {
        "path": str(Path(__file__).resolve()),
        "sha256": sha256_file(Path(__file__).resolve()),
    }
    analysis["artifacts"] = {
        "json": str(json_path),
        "plot": str(plot_path),
    }
    json_path.write_text(json.dumps(analysis, indent=2) + "\n")
    make_plot(plot_path, analysis, images)
    print(
        json.dumps(
            {
                "overall": analysis["evidence_decisions"][
                    "overall_boundary_response_pilot"
                ],
                "stimulus": analysis["evidence_decisions"][
                    "external_boundary_stimulus_coverage"
                ],
                "longitudinal_open_loop": analysis["evidence_decisions"][
                    "shared_handoff_longitudinal_endpoint_direction"
                ],
                "clearance_gain": analysis["evidence_decisions"][
                    "preregistered_complete_clearance_response_gain"
                ],
                "closed_loop": analysis["evidence_decisions"][
                    "strict_action_compatible_closed_loop_completion"
                ],
                "output": str(output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
