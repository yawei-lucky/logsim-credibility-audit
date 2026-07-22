import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_hugsim_occlusion_metamorphic import (  # noqa: E402
    background_changed_fraction,
    box_in_vehicle_frame,
    depth_order_passes,
    evaluate_support_masks,
    nested_support_domain,
    overlap_relation,
    planar_offset_residual,
    role_invariance,
)


def info(timestamp, boxes):
    return {"timestamp": timestamp, "obj_boxes": boxes}


TARGET = [24.0, 0.0, -1.0, 1.6, 3.6, 1.2, 0.0]
PARTIAL = [20.0, -2.0, -1.0, 1.6, 3.6, 1.2, 0.0]
STRONG = [20.0, 0.0, -1.0, 1.6, 3.6, 1.2, 0.0]


class OcclusionMetamorphicAnalysisTest(unittest.TestCase):
    def test_nested_overlap_order_passes(self):
        target = np.ones((8, 8), dtype=bool)
        partial = np.zeros_like(target)
        partial[:, :3] = True
        strong = np.zeros_like(target)
        strong[:, :6] = True
        result = overlap_relation(target, partial, strong, 0.0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["partial_outside_strong_pixels"], 0)

    def test_non_nested_overlap_fails_even_when_strong_is_larger(self):
        target = np.ones((8, 8), dtype=bool)
        partial = np.zeros_like(target)
        partial[:4, :4] = True
        strong = np.zeros_like(target)
        strong[:, 2:7] = True
        result = overlap_relation(target, partial, strong, 0.01)
        self.assertFalse(result["passed"])
        self.assertGreater(result["partial_outside_strong_pixels"], 0)

    def test_partial_only_pixels_are_removed_from_support_domain(self):
        target = np.ones((4, 4), dtype=bool)
        partial = np.zeros_like(target)
        partial[0, 0] = True
        partial[1:3, 1:3] = True
        strong = np.zeros_like(target)
        strong[1:4, 1:4] = True
        domain, excluded = nested_support_domain(target, partial, strong)
        self.assertTrue(excluded[0, 0])
        self.assertFalse(domain[0, 0])
        self.assertFalse(np.any((partial & domain) & ~(strong & domain)))

    def test_depth_order_rejects_occluder_behind_target(self):
        self.assertTrue(depth_order_passes(20.0, 24.0, 0.2))
        self.assertFalse(depth_order_passes(26.0, 24.0, 0.2))

    def test_global_box_is_transformed_to_vehicle_frame(self):
        state = {
            "ego_box": [10.0, 4.0, -1.5, 1.6, 3.0, 1.5, np.pi / 2],
        }
        global_box = np.asarray(
            [10.0, 14.0, -1.0, 1.6, 3.6, 1.2, np.pi / 2]
        )
        local = box_in_vehicle_frame(state, global_box)
        np.testing.assert_allclose(local[:3], [10.0, 0.0, -0.5], atol=1e-12)
        self.assertAlmostEqual(local[6], 0.0)

    def test_declared_planar_actor_offset_is_checked(self):
        self.assertEqual(
            planar_offset_residual(
                np.asarray(TARGET), np.asarray(PARTIAL), 4.0, 2.0
            ),
            0.0,
        )
        self.assertGreater(
            planar_offset_residual(
                np.asarray(TARGET), np.asarray(PARTIAL), 4.0, 1.5
            ),
            0.4,
        )

    def test_role_state_invariance_and_perturbation(self):
        conditions = {
            "target_only": [info(0.0, [TARGET])],
            "partial_occluder_only": [info(0.0, [PARTIAL])],
            "partial_both": [info(0.0, [PARTIAL, TARGET])],
            "strong_occluder_only": [info(0.0, [STRONG])],
            "strong_both": [info(0.0, [STRONG, TARGET])],
        }
        self.assertTrue(role_invariance(conditions, 1e-8)["passed"])
        changed = {name: list(rows) for name, rows in conditions.items()}
        changed["strong_both"] = [info(0.0, [STRONG, [24.01, *TARGET[1:]]])]
        self.assertFalse(role_invariance(changed, 1e-8)["passed"])

    def test_target_support_expected_and_swap_rejected(self):
        reference = np.zeros((10, 10), dtype=bool)
        reference[:5, :] = True
        partial = np.zeros_like(reference)
        partial[:4, :] = True
        strong = np.zeros_like(reference)
        strong[:2, :] = True
        expected = evaluate_support_masks(reference, partial, strong, 25)
        reversed_result = evaluate_support_masks(reference, strong, partial, 25)
        self.assertEqual(expected["outcome"], "expected")
        self.assertEqual(reversed_result["outcome"], "reversal")

    def test_small_reference_is_unavailable(self):
        reference = np.zeros((10, 10), dtype=bool)
        reference[:2, :] = True
        result = evaluate_support_masks(reference, reference, reference, 25)
        self.assertEqual(result["outcome"], "unavailable")

    def test_background_control_detects_global_pair_drift(self):
        left = np.zeros((100, 100, 3), dtype=np.uint8)
        right = left.copy()
        right[:20] = 30
        self.assertEqual(background_changed_fraction(left, left, 10, 0.2), 0.0)
        self.assertEqual(background_changed_fraction(left, right, 10, 0.2), 1.0)


if __name__ == "__main__":
    unittest.main()
