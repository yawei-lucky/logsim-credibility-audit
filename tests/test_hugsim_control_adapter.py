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
)


class ControllerReferenceTest(unittest.TestCase):
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
