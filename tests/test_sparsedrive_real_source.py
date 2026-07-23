import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_sparsedrive_real_source import (  # noqa: E402
    command_from_reference,
    future_reference,
    plan_reference_error,
    pose_derived_ego_status,
    validate_indices,
)


def pose(right: float, forward: float, yaw: float = 0.0) -> np.ndarray:
    cosine, sine = np.cos(yaw), np.sin(yaw)
    transform = np.eye(4)
    transform[:3, :3] = np.asarray(
        [
            [cosine, -sine, 0.0],
            [sine, cosine, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    transform[:3, 3] = [right, forward, 0.0]
    return transform


class SparseDriveRealSourceTest(unittest.TestCase):
    def test_validate_indices_requires_four_uniform_frames(self):
        self.assertEqual(validate_indices([12, 18, 24, 30]), 6)
        with self.assertRaises(ValueError):
            validate_indices([12, 18, 25, 30])
        with self.assertRaises(ValueError):
            validate_indices([12, 18, 24])

    def test_pose_status_recovers_forward_speed_and_acceleration(self):
        status = pose_derived_ego_status(
            pose(0.0, 3.0),
            pose(0.0, 1.0),
            pose(0.0, 0.0),
            2.0,
            1.0,
            0.0,
        )
        self.assertAlmostEqual(float(status[1]), 1.0)
        self.assertAlmostEqual(float(status[6]), 0.0)
        self.assertAlmostEqual(float(status[7]), 2.0)
        self.assertAlmostEqual(float(status[9]), 0.0)

    def test_future_reference_is_expressed_in_current_model_frame(self):
        current = pose(10.0, 20.0, yaw=np.pi / 2)
        future = [
            current @ pose(0.2 * step, 1.5 * step)
            for step in range(1, 7)
        ]
        reference = future_reference(current, future)
        np.testing.assert_allclose(
            reference[-1],
            np.asarray([1.2, 9.0]),
            atol=1e-6,
        )

    def test_command_uses_released_lateral_rule(self):
        straight = np.zeros((6, 2), dtype=np.float32)
        right = straight.copy()
        right[-1, 0] = 2.0
        left = straight.copy()
        left[-1, 0] = -2.0
        np.testing.assert_array_equal(
            command_from_reference(straight),
            np.asarray([0.0, 0.0, 1.0]),
        )
        np.testing.assert_array_equal(
            command_from_reference(right),
            np.asarray([1.0, 0.0, 0.0]),
        )
        np.testing.assert_array_equal(
            command_from_reference(left),
            np.asarray([0.0, 1.0, 0.0]),
        )

    def test_plan_error_reports_ade_fde_and_declared_horizons(self):
        reference = np.column_stack(
            (np.zeros(6), np.arange(1.0, 7.0))
        )
        plan = reference.copy()
        plan[:, 0] = 1.0
        result = plan_reference_error(plan, reference)
        self.assertAlmostEqual(result["ade_m"], 1.0)
        self.assertAlmostEqual(result["fde_m"], 1.0)
        self.assertEqual(set(result["horizons"]), {"1s", "2s", "3s"})


if __name__ == "__main__":
    unittest.main()
