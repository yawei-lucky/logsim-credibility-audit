#!/usr/bin/env python3
"""Coordinate adapter between HUGSIM planner output and its iLQR controller.

HUGSIM documents planner trajectories as ``[right, forward]`` lidar-local
coordinates.  Its iLQR controller uses ``[forward, lateral, yaw, ...]``.  The
released ``traj2control`` swaps the point coordinates but calculates yaw from
the unswapped axes, which turns a straight-forward plan into a 90-degree
heading target.  This module keeps the released simulator untouched and makes
the conversion explicit and auditable for controlled experiments.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np


ACTUATION_CONTRACT_MODES = ("strict_audit", "bounded_projection")
ACTUATION_CONTROL_KEYS = ("acc", "steer_rate")
HUGSIM_ACTION_SEMANTICS = {
    "acc": "longitudinal_acceleration_mps2",
    "steer_rate": "steering_angle_rate_radps",
}


def hugsim_action_bounds(
    action_space: Any,
    *,
    semantic_contract: Mapping[str, str] | None,
) -> dict[str, dict[str, float]]:
    """Extract a qualified scalar box from HUGSIM's declared action space.

    Bounds alone are not enough: the caller must explicitly confirm the two
    command semantics. This makes an unknown or renamed interface fail closed.
    """
    if dict(semantic_contract or {}) != HUGSIM_ACTION_SEMANTICS:
        raise ValueError("HUGSIM actuation semantics are missing or unconfirmed")

    bounds: dict[str, dict[str, float]] = {}
    for name in ACTUATION_CONTROL_KEYS:
        try:
            space = action_space[name]
            low_values = np.asarray(space.low, dtype=np.float64).reshape(-1)
            high_values = np.asarray(space.high, dtype=np.float64).reshape(-1)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"Missing HUGSIM action bound for {name}") from exc
        if low_values.size != 1 or high_values.size != 1:
            raise ValueError(f"HUGSIM action bound for {name} is not scalar")
        low = float(low_values[0])
        high = float(high_values[0])
        if not np.isfinite([low, high]).all() or low > high:
            raise ValueError(f"Invalid HUGSIM action bounds for {name}")
        bounds[name] = {"low": low, "high": high}
    return bounds


def _audit_scalar(value: Any) -> float | str:
    try:
        scalar = float(value)
    except (TypeError, ValueError):
        return repr(value)
    if np.isnan(scalar):
        return "nan"
    if np.isposinf(scalar):
        return "inf"
    if np.isneginf(scalar):
        return "-inf"
    return scalar


def evaluate_actuation_contract(
    raw_control: Mapping[str, Any],
    *,
    bounds: Mapping[str, Mapping[str, float]] | None,
    contract_mode: str,
    semantic_contract: Mapping[str, str] | None,
) -> dict[str, Any]:
    """Audit a raw command and, when allowed, return the environment command.

    ``strict_audit`` rejects the complete command if either component is out
    of range. ``bounded_projection`` uses the Euclidean projection onto the
    confirmed axis-aligned box, which is component-wise clipping. Invalid
    values, bounds, or semantics reject in both modes.
    """
    record: dict[str, Any] = {
        "contract_mode": contract_mode,
        "semantic_contract": dict(semantic_contract or {}),
        "raw_control": {
            name: _audit_scalar(raw_control.get(name))
            for name in ACTUATION_CONTROL_KEYS
        },
        "applied_control": None,
        "bounds": None,
        "violation_mask": None,
        "violation_amount": None,
        "projection_residual": None,
        "projection_residual_l2": None,
        "saturation_active": None,
        "decision": "rejected_invalid_contract",
        "reason": None,
    }
    if contract_mode not in ACTUATION_CONTRACT_MODES:
        record["reason"] = f"unknown contract mode: {contract_mode}"
        return record
    if dict(semantic_contract or {}) != HUGSIM_ACTION_SEMANTICS:
        record["reason"] = "actuation semantics are missing or unconfirmed"
        return record
    if bounds is None:
        record["reason"] = "qualified action bounds are missing"
        return record

    normalized_bounds: dict[str, dict[str, float]] = {}
    numeric_raw: dict[str, float] = {}
    for name in ACTUATION_CONTROL_KEYS:
        if name not in raw_control:
            record["reason"] = f"raw control is missing {name}"
            return record
        try:
            raw = float(raw_control[name])
            low = float(bounds[name]["low"])
            high = float(bounds[name]["high"])
        except (KeyError, TypeError, ValueError) as exc:
            record["reason"] = f"invalid value or bound for {name}: {exc}"
            return record
        if not np.isfinite([raw, low, high]).all() or low > high:
            record["reason"] = f"non-finite value or invalid bounds for {name}"
            return record
        numeric_raw[name] = raw
        normalized_bounds[name] = {"low": low, "high": high}

    violation_amount = {
        name: max(
            normalized_bounds[name]["low"] - numeric_raw[name],
            numeric_raw[name] - normalized_bounds[name]["high"],
            0.0,
        )
        for name in ACTUATION_CONTROL_KEYS
    }
    violation_mask = {
        name: amount > 0.0 for name, amount in violation_amount.items()
    }
    saturation_active = any(violation_mask.values())
    record.update(
        {
            "bounds": normalized_bounds,
            "violation_mask": violation_mask,
            "violation_amount": violation_amount,
            "saturation_active": saturation_active,
        }
    )

    if contract_mode == "strict_audit" and saturation_active:
        record.update(
            {
                "decision": "rejected_out_of_bounds",
                "reason": "raw control is outside the qualified action box",
            }
        )
        return record

    applied = {
        name: float(
            np.clip(
                numeric_raw[name],
                normalized_bounds[name]["low"],
                normalized_bounds[name]["high"],
            )
        )
        for name in ACTUATION_CONTROL_KEYS
    }
    residual = {
        name: applied[name] - numeric_raw[name]
        for name in ACTUATION_CONTROL_KEYS
    }
    record.update(
        {
            "applied_control": applied,
            "projection_residual": residual,
            "projection_residual_l2": float(
                np.linalg.norm([residual[name] for name in ACTUATION_CONTROL_KEYS])
            ),
            "decision": (
                "accepted_projected" if saturation_active else "accepted_unchanged"
            ),
            "reason": None,
        }
    )
    return record


def execute_actuation_contract(
    raw_control: Mapping[str, Any],
    *,
    bounds: Mapping[str, Mapping[str, float]] | None,
    contract_mode: str,
    semantic_contract: Mapping[str, str] | None,
    environment_step: Callable[[dict[str, float]], Any],
) -> tuple[dict[str, Any], Any | None]:
    """Evaluate the contract and call the environment only when qualified."""
    record = evaluate_actuation_contract(
        raw_control,
        bounds=bounds,
        contract_mode=contract_mode,
        semantic_contract=semantic_contract,
    )
    applied = record["applied_control"]
    if applied is None:
        return record, None
    return record, environment_step(dict(applied))


def sparsedrive_plan_to_hugsim_lidar_plan(
    final_planning: np.ndarray,
    *,
    source_timestep_s: float = 0.5,
    controller_timestep_s: float = 0.5,
    expected_waypoints: int = 6,
) -> np.ndarray:
    """Validate the identity mapping from SparseDrive to HUGSIM plan-pipe.

    Both interfaces use ``[right, forward]`` metres.  The mapping is therefore
    intentionally an identity copy, but timing and horizon are checked so a
    caller cannot silently pad, truncate, repeat, or reinterpret the plan.
    """
    plan = np.asarray(final_planning, dtype=np.float64)
    if plan.shape != (expected_waypoints, 2):
        raise ValueError(
            "Expected SparseDrive plan shape "
            f"({expected_waypoints}, 2), got {plan.shape}"
        )
    if not np.isfinite(plan).all():
        raise ValueError("SparseDrive plan contains non-finite values")
    if not np.isclose(source_timestep_s, controller_timestep_s, atol=1e-12):
        raise ValueError(
            "SparseDrive and HUGSIM controller timesteps differ: "
            f"{source_timestep_s} vs {controller_timestep_s}"
        )
    return plan.copy()


def exact_control_hold_steps(
    controller_timestep_s: float,
    environment_timestep_s: float,
) -> int:
    """Return the exact number of environment steps per controller input."""
    if controller_timestep_s <= 0 or environment_timestep_s <= 0:
        raise ValueError("Timesteps must be positive")
    ratio = controller_timestep_s / environment_timestep_s
    rounded = round(ratio)
    if rounded < 1 or not np.isclose(ratio, rounded, atol=1e-12):
        raise ValueError(
            "Controller timestep must be an integer multiple of the "
            f"environment timestep, got ratio={ratio}"
        )
    return int(rounded)


def controller_reference_from_lidar_plan(plan_traj: np.ndarray) -> np.ndarray:
    """Convert ``[right, forward]`` points to iLQR reference states.

    The returned columns are ``[forward, lateral, yaw, velocity, steering]``.
    Heading is calculated *after* the coordinate swap so positions and yaw use
    the same controller frame.
    """
    plan = np.asarray(plan_traj, dtype=np.float64)
    if plan.ndim != 2 or plan.shape[1] != 2:
        raise ValueError(f"Expected plan shape (N, 2), got {plan.shape}")
    if len(plan) == 0:
        raise ValueError("Plan must contain at least one waypoint")
    if not np.isfinite(plan).all():
        raise ValueError("Plan contains non-finite values")

    reference = np.zeros((len(plan) + 1, 5), dtype=np.float64)
    reference[1:, :2] = plan[:, [1, 0]]

    deltas = np.diff(reference[:, :2], axis=0)
    headings = np.arctan2(deltas[:, 1], deltas[:, 0])
    # The controller is configured for forward driving. Match HUGSIM's
    # released behavior by folding reverse-facing headings into that range.
    headings = np.where(headings > np.pi / 2, headings - np.pi, headings)
    headings = np.where(headings < -np.pi / 2, headings + np.pi, headings)
    reference[1:, 2] = headings
    return reference


def corrected_traj2control(
    plan_traj: np.ndarray,
    info: Mapping[str, Any],
    plan2control_fn: Callable[[np.ndarray, np.ndarray], tuple[float, float]],
) -> tuple[float, float]:
    """Calculate control using the corrected coordinate conversion."""
    reference = controller_reference_from_lidar_plan(plan_traj)
    current_state = np.array(
        [0.0, 0.0, 0.0, float(info["ego_velo"]), float(info["ego_steer"])],
        dtype=np.float64,
    )
    return plan2control_fn(reference, current_state)
