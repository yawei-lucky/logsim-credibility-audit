from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hugsim_control_adapter import (  # noqa: E402
    HUGSIM_ACTION_SEMANTICS,
    controller_reference_from_lidar_plan,
    corrected_traj2control,
    evaluate_actuation_contract,
    execute_actuation_contract,
    exact_control_hold_steps,
    hugsim_action_bounds,
    sparsedrive_plan_to_hugsim_lidar_plan,
)


class ControllerReferenceTest(unittest.TestCase):
    def test_sparsedrive_plan_is_identity_mapped_without_padding(self) -> None:
        plan = np.array(
            [[0.1 * index, 1.0 + index] for index in range(6)],
            dtype=np.float32,
        )

        mapped = sparsedrive_plan_to_hugsim_lidar_plan(plan)

        np.testing.assert_allclose(mapped, plan)
        self.assertIsNot(mapped, plan)

    def test_sparsedrive_plan_rejects_horizon_or_timestep_changes(self) -> None:
        with self.assertRaisesRegex(ValueError, "shape"):
            sparsedrive_plan_to_hugsim_lidar_plan(np.zeros((5, 2)))
        with self.assertRaisesRegex(ValueError, "timesteps differ"):
            sparsedrive_plan_to_hugsim_lidar_plan(
                np.zeros((6, 2)),
                source_timestep_s=0.5,
                controller_timestep_s=0.25,
            )

    def test_half_second_control_maps_to_two_quarter_second_steps(self) -> None:
        self.assertEqual(exact_control_hold_steps(0.5, 0.25), 2)
        with self.assertRaisesRegex(ValueError, "integer multiple"):
            exact_control_hold_steps(0.5, 0.3)

    def test_forward_plan_has_forward_positions_and_zero_heading(self) -> None:
        plan = np.array([[0.0, 1.0], [0.0, 2.0], [0.0, 3.0]])

        reference = controller_reference_from_lidar_plan(plan)

        np.testing.assert_allclose(reference[1:, 0], [1.0, 2.0, 3.0])
        np.testing.assert_allclose(reference[1:, 1], 0.0)
        np.testing.assert_allclose(reference[1:, 2], 0.0)

    def test_rightward_plan_uses_controller_frame_heading(self) -> None:
        plan = np.array([[1.0, 1.0], [2.0, 2.0]])

        reference = controller_reference_from_lidar_plan(plan)

        np.testing.assert_allclose(reference[1:, 2], np.pi / 4)

    def test_control_receives_consistent_reference_and_current_state(self) -> None:
        captured: dict[str, np.ndarray] = {}

        def fake_plan2control(
            reference: np.ndarray,
            current_state: np.ndarray,
        ) -> tuple[float, float]:
            captured["reference"] = reference
            captured["current_state"] = current_state
            return 1.25, -0.125

        result = corrected_traj2control(
            np.array([[0.0, 1.0], [0.0, 2.0]]),
            {"ego_velo": 2.5, "ego_steer": 0.1},
            fake_plan2control,
        )

        self.assertEqual(result, (1.25, -0.125))
        np.testing.assert_allclose(captured["reference"][1:, 2], 0.0)
        np.testing.assert_allclose(captured["current_state"], [0, 0, 0, 2.5, 0.1])

    def test_rejects_invalid_plan(self) -> None:
        with self.assertRaisesRegex(ValueError, "shape"):
            controller_reference_from_lidar_plan(np.zeros((3, 3)))


class ActuationContractTest(unittest.TestCase):
    BOUNDS = {
        "acc": {"low": -2.0, "high": 2.0},
        "steer_rate": {"low": -0.25, "high": 0.25},
    }

    def evaluate(
        self,
        raw: dict[str, float],
        mode: str,
        **overrides: object,
    ) -> dict[str, object]:
        arguments: dict[str, object] = {
            "bounds": self.BOUNDS,
            "contract_mode": mode,
            "semantic_contract": HUGSIM_ACTION_SEMANTICS,
        }
        arguments.update(overrides)
        return evaluate_actuation_contract(raw, **arguments)  # type: ignore[arg-type]

    def test_in_range_is_unchanged_in_both_modes(self) -> None:
        raw = {"acc": 1.25, "steer_rate": -0.1}
        for mode in ("strict_audit", "bounded_projection"):
            with self.subTest(mode=mode):
                record = self.evaluate(raw, mode)
                self.assertEqual(record["applied_control"], raw)
                self.assertEqual(record["decision"], "accepted_unchanged")
                self.assertFalse(record["saturation_active"])

    def test_exact_boundary_values_are_accepted(self) -> None:
        for raw in (
            {"acc": -2.0, "steer_rate": -0.25},
            {"acc": 2.0, "steer_rate": 0.25},
        ):
            for mode in ("strict_audit", "bounded_projection"):
                with self.subTest(raw=raw, mode=mode):
                    record = self.evaluate(raw, mode)
                    self.assertEqual(record["applied_control"], raw)
                    self.assertFalse(record["saturation_active"])

    def test_positive_overflow_is_rejected_by_strict_contract(self) -> None:
        record = self.evaluate(
            {"acc": 2.01, "steer_rate": 0.251},
            "strict_audit",
        )
        self.assertIsNone(record["applied_control"])
        self.assertEqual(record["decision"], "rejected_out_of_bounds")
        self.assertEqual(
            record["violation_mask"], {"acc": True, "steer_rate": True}
        )

    def test_negative_overflow_is_rejected_by_strict_contract(self) -> None:
        record = self.evaluate(
            {"acc": -2.01, "steer_rate": -0.251},
            "strict_audit",
        )
        self.assertIsNone(record["applied_control"])
        self.assertEqual(record["decision"], "rejected_out_of_bounds")

    def test_bounded_projection_clips_exactly_to_box(self) -> None:
        record = self.evaluate(
            {"acc": 3.0, "steer_rate": -0.4},
            "bounded_projection",
        )
        self.assertEqual(
            record["applied_control"], {"acc": 2.0, "steer_rate": -0.25}
        )
        residual = record["projection_residual"]
        assert isinstance(residual, dict)
        self.assertAlmostEqual(residual["acc"], -1.0)
        self.assertAlmostEqual(residual["steer_rate"], 0.15)

    def test_bounded_projection_preserves_raw_control(self) -> None:
        raw = {"acc": 3.0, "steer_rate": -0.4}
        before = raw.copy()
        record = self.evaluate(raw, "bounded_projection")
        self.assertEqual(raw, before)
        self.assertEqual(record["raw_control"], before)

    def test_applied_control_always_satisfies_confirmed_bounds(self) -> None:
        for raw in (
            {"acc": -20.0, "steer_rate": 10.0},
            {"acc": 20.0, "steer_rate": -10.0},
            {"acc": 0.0, "steer_rate": 0.0},
        ):
            applied = self.evaluate(raw, "bounded_projection")["applied_control"]
            assert isinstance(applied, dict)
            self.assertLessEqual(abs(applied["acc"]), 2.0)
            self.assertLessEqual(abs(applied["steer_rate"]), 0.25)

    def test_nan_and_infinity_fail_closed(self) -> None:
        for value in (np.nan, np.inf, -np.inf):
            for mode in ("strict_audit", "bounded_projection"):
                with self.subTest(value=value, mode=mode):
                    record = self.evaluate(
                        {"acc": value, "steer_rate": 0.0},
                        mode,
                    )
                    self.assertIsNone(record["applied_control"])
                    self.assertEqual(
                        record["decision"], "rejected_invalid_contract"
                    )

    def test_unknown_semantics_or_missing_bounds_fail_closed(self) -> None:
        raw = {"acc": 0.0, "steer_rate": 0.0}
        no_semantics = self.evaluate(
            raw,
            "strict_audit",
            semantic_contract=None,
        )
        no_bounds = self.evaluate(
            raw,
            "bounded_projection",
            bounds=None,
        )
        self.assertIsNone(no_semantics["applied_control"])
        self.assertIsNone(no_bounds["applied_control"])

    def test_contract_mode_is_explicit_in_every_record(self) -> None:
        for mode in ("strict_audit", "bounded_projection"):
            record = self.evaluate({"acc": 0.0, "steer_rate": 0.0}, mode)
            self.assertEqual(record["contract_mode"], mode)

    def test_strict_rejection_never_calls_environment(self) -> None:
        calls: list[dict[str, float]] = []
        record, result = execute_actuation_contract(
            {"acc": 0.0, "steer_rate": 0.4},
            bounds=self.BOUNDS,
            contract_mode="strict_audit",
            semantic_contract=HUGSIM_ACTION_SEMANTICS,
            environment_step=lambda action: calls.append(action),
        )
        self.assertIsNone(result)
        self.assertEqual(calls, [])
        self.assertEqual(record["decision"], "rejected_out_of_bounds")

    def test_bounded_mode_calls_environment_with_applied_only(self) -> None:
        calls: list[dict[str, float]] = []
        record, result = execute_actuation_contract(
            {"acc": 3.0, "steer_rate": -0.4},
            bounds=self.BOUNDS,
            contract_mode="bounded_projection",
            semantic_contract=HUGSIM_ACTION_SEMANTICS,
            environment_step=lambda action: calls.append(action) or "stepped",
        )
        self.assertEqual(result, "stepped")
        self.assertEqual(calls, [record["applied_control"]])

    def test_action_space_bounds_require_confirmed_semantics(self) -> None:
        class ScalarBox:
            def __init__(self, low: float, high: float) -> None:
                self.low = np.array([low])
                self.high = np.array([high])

        action_space = {
            "acc": ScalarBox(-2.0, 2.0),
            "steer_rate": ScalarBox(-0.25, 0.25),
        }
        self.assertEqual(
            hugsim_action_bounds(
                action_space,
                semantic_contract=HUGSIM_ACTION_SEMANTICS,
            ),
            self.BOUNDS,
        )
        with self.assertRaisesRegex(ValueError, "semantics"):
            hugsim_action_bounds(action_space, semantic_contract=None)


if __name__ == "__main__":
    unittest.main()
