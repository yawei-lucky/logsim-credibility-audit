import math
import sys
import unittest
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_sparsedrive_hugsim_receiver import (  # noqa: E402
    command_vector,
    ego_status_vector,
    tensor_summary,
    wrapped_rate,
)


def info(
    *,
    timestamp=0.0,
    yaw=0.0,
    command=2,
    acceleration=0.5,
    speed=3.0,
    steer=0.1,
):
    return {
        "timestamp": timestamp,
        "ego_box": [0, 0, 0, 1.6, 3.0, 1.5, yaw],
        "command": command,
        "accelerate": acceleration,
        "ego_velo": speed,
        "ego_steer": steer,
    }


class SparseDriveHugsimReceiverTest(unittest.TestCase):
    def test_command_order_is_right_left_straight(self):
        np.testing.assert_array_equal(command_vector(info(command=0)), [1, 0, 0])
        np.testing.assert_array_equal(command_vector(info(command=1)), [0, 1, 0])
        np.testing.assert_array_equal(command_vector(info(command=2)), [0, 0, 1])
        with self.assertRaisesRegex(ValueError, "unsupported"):
            command_vector(info(command=3))

    def test_ego_status_mapping_and_yaw_rate(self):
        previous = info(timestamp=1.0, yaw=0.2)
        current = info(
            timestamp=1.5,
            yaw=0.3,
            acceleration=1.25,
            speed=4.5,
            steer=-0.2,
        )
        status = ego_status_vector(current, previous)

        self.assertEqual(status.shape, (10,))
        self.assertAlmostEqual(status[0], 1.25)
        self.assertAlmostEqual(status[5], 0.2)
        self.assertAlmostEqual(status[6], 4.5)
        self.assertAlmostEqual(status[9], -0.2)

    def test_wrapped_rate_crosses_pi_without_jump(self):
        rate = wrapped_rate(-math.pi + 0.05, math.pi - 0.05, 0.5)
        self.assertAlmostEqual(rate, 0.2)

    def test_numpy_tensor_summary_reports_non_finite(self):
        class FakeTorch:
            @staticmethod
            def is_tensor(_value):
                return False

        summary = tensor_summary(np.asarray([1.0, np.nan]), torch=FakeTorch())
        self.assertEqual(summary["shape"], [2])
        self.assertFalse(summary["finite"])


if __name__ == "__main__":
    unittest.main()
