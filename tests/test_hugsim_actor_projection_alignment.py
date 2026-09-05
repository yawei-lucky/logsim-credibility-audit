import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_hugsim_actor_projection_alignment import (  # noqa: E402
    alignment_metrics,
    difference_support,
    project_world_points,
    projection_support_mask,
)


class HugsimActorProjectionAlignmentTest(unittest.TestCase):
    def test_standard_camera_projection(self):
        pixels, depth = project_world_points(
            np.asarray([[0.0, 0.0, 2.0], [1.0, 0.0, 2.0]]),
            np.eye(4),
            np.asarray([[100.0, 0.0, 50.0], [0.0, 100.0, 40.0], [0.0, 0.0, 1.0]]),
        )
        np.testing.assert_allclose(pixels, [[50.0, 40.0], [100.0, 40.0]])
        np.testing.assert_allclose(depth, [2.0, 2.0])

    def test_aligned_difference_passes(self):
        baseline = np.zeros((80, 100, 3), dtype=np.uint8)
        actor = baseline.copy()
        actor[30:50, 40:60] = 100
        difference, _ = difference_support(baseline, actor, 5)
        pixels = np.asarray([[40, 30], [59, 30], [59, 49], [40, 49]], dtype=float)
        projected, dilated, _ = projection_support_mask(
            pixels, np.ones(4), (80, 100), 2
        )
        result = alignment_metrics(projected, dilated, difference, 40, 0.85, 24.0)
        self.assertTrue(result["rgb_difference_visible"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["difference_support_coverage"], 1.0)

    def test_visible_misalignment_fails(self):
        difference = np.zeros((80, 100), dtype=bool)
        difference[50:70, 70:90] = True
        projected = np.zeros_like(difference)
        projected[5:20, 5:20] = True
        result = alignment_metrics(projected, projected, difference, 40, 0.85, 24.0)
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
