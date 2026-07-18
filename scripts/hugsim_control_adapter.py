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
