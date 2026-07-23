from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hugsim_sparsedrive_live_writer import (  # noqa: E402
    adjusted_live_info,
    maximum_boundary_state_residual,
    rgb_maximum_difference,
)


def info(timestamp: float, acceleration: float) -> dict:
    return {
        "timestamp": timestamp,
        "ego_box": np.zeros(7),
        "ego_pos": np.zeros(3),
        "ego_rot": np.zeros(3),
        "ego_velo": 2.0,
        "ego_steer": 0.0,
        "accelerate": acceleration,
        "steer_rate": 0.1,
    }


class SparseDriveLiveWriterTest(unittest.TestCase):
    def test_first_live_info_uses_continuous_time_and_boundary_history(self):
        live = info(0.0, 0.0)
        boundary = info(1.5, 0.2)

        adjusted = adjusted_live_info(
            live,
            boundary,
            first_live_frame=True,
        )

        self.assertEqual(adjusted["timestamp"], 1.5)
        self.assertEqual(adjusted["accelerate"], 0.2)
        self.assertEqual(adjusted["steer_rate"], 0.1)

    def test_later_live_info_keeps_actual_action_history(self):
        live = info(0.5, -0.4)
        boundary = info(1.5, 0.2)

        adjusted = adjusted_live_info(
            live,
            boundary,
            first_live_frame=False,
        )

        self.assertEqual(adjusted["timestamp"], 2.0)
        self.assertEqual(adjusted["accelerate"], -0.4)

    def test_source_warm_started_info_is_not_offset_or_rewritten(self):
        live = info(1.5, 0.2)
        boundary = info(1.5, 0.2)

        adjusted = adjusted_live_info(
            live,
            boundary,
            first_live_frame=True,
            source_warm_started=True,
        )

        self.assertEqual(adjusted["timestamp"], 1.5)
        self.assertEqual(adjusted["accelerate"], 0.2)
        self.assertEqual(adjusted["steer_rate"], 0.1)

    def test_boundary_state_and_rgb_residuals_detect_change(self):
        boundary = info(1.5, 0.2)
        live = info(0.0, 0.0)
        self.assertEqual(maximum_boundary_state_residual(live, boundary), 0.0)
        live["ego_velo"] = 2.1
        self.assertAlmostEqual(
            maximum_boundary_state_residual(live, boundary),
            0.1,
        )

        source = {"rgb": {"CAM_FRONT": np.zeros((2, 2, 3), dtype=np.uint8)}}
        current = {"rgb": {"CAM_FRONT": np.zeros((2, 2, 3), dtype=np.uint8)}}
        self.assertEqual(rgb_maximum_difference(current, source), 0)
        current["rgb"]["CAM_FRONT"][0, 0, 0] = 3
        self.assertEqual(rgb_maximum_difference(current, source), 3)


if __name__ == "__main__":
    unittest.main()
