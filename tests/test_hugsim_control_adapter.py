from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hugsim_control_adapter import (  # noqa: E402
    controller_reference_from_lidar_plan,
    corrected_traj2control,
    exact_control_hold_steps,
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


if __name__ == "__main__":
    unittest.main()
