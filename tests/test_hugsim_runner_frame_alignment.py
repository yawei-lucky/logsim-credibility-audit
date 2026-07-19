from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_hugsim_debug_smoke import build_scoring_frame  # noqa: E402


class ScoringFrameAlignmentTest(unittest.TestCase):
    def test_plan_and_state_use_same_post_step_pose(self) -> None:
        plan = np.array([[0.0, 1.0], [0.0, 2.0]], dtype=np.float32)
        post_step_box = [4.0, 5.0, 0.0, 1.6, 3.0, 1.5, 0.2]
        info_after = {
            "timestamp": 1.25,
            "ego_box": post_step_box,
            "obj_boxes": [],
            "collision": False,
            "rc": 0.1,
        }
        captured: dict[str, object] = {}

        def fake_transform(
            transformed_plan: np.ndarray,
            anchor_box: list[float],
        ) -> list[tuple[float, float, float]]:
            captured["plan"] = transformed_plan
            captured["anchor_box"] = anchor_box
            return [(5.0, 5.0, 0.2)]

        frame = build_scoring_frame(plan, info_after, fake_transform)

        self.assertIs(captured["anchor_box"], post_step_box)
        self.assertIs(frame["ego_box"], post_step_box)
        self.assertEqual(frame["time_stamp"], info_after["timestamp"])
        np.testing.assert_allclose(
            captured["plan"],
            np.array([[1.0, -0.0], [2.0, -0.0]]),
        )


if __name__ == "__main__":
    unittest.main()
