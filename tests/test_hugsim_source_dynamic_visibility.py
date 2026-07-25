import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_hugsim_source_dynamic_visibility import (  # noqa: E402
    support_metrics,
)


class HugsimSourceDynamicVisibilityTest(unittest.TestCase):
    def test_aligned_support_concentrates_energy_inside_source_mask(self):
        mask = np.zeros((12, 12), dtype=bool)
        mask[4:8, 5:9] = True
        static = np.zeros((12, 12, 3), dtype=np.uint8)
        factual = static.copy()
        factual[mask] = 20

        result = support_metrics(mask, factual, static, [4, 16], 1)

        self.assertEqual(result["source_mask_pixels"], 16)
        self.assertEqual(result["exact_source_mask_energy_fraction"], 1.0)
        self.assertEqual(result["centroid_error_px"], 0.0)
        self.assertEqual(
            result["threshold_sensitivity"]["16"]["iou"],
            1.0,
        )

    def test_empty_source_and_render_support_remain_explicit(self):
        mask = np.zeros((8, 8), dtype=bool)
        image = np.zeros((8, 8, 3), dtype=np.uint8)

        result = support_metrics(mask, image, image, [4], 1)

        self.assertFalse(result["source_mask_nonempty"])
        self.assertFalse(result["render_difference_nonzero"])
        self.assertIsNone(result["exact_source_mask_energy_fraction"])
        self.assertIsNone(
            result["threshold_sensitivity"]["4"]["source_mask_recall"]
        )

    def test_shape_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            support_metrics(
                np.zeros((4, 4), dtype=bool),
                np.zeros((5, 4, 3), dtype=np.uint8),
                np.zeros((5, 4, 3), dtype=np.uint8),
                [4],
                1,
            )


if __name__ == "__main__":
    unittest.main()
