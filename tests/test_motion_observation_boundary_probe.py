import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compare_motion_observation_boundary_runs import compare_runs
from run_motion_observation_boundary_probe import (
    common_depth_width,
    is_single_marker_failure,
    marker_points,
    occluder_point,
    project_width,
    roundtrip_render_camera_points,
)

CFG = json.loads((ROOT / "configs/motion_observation_boundary_001.json").read_text())
K = np.array([[633.2, 0, 408.1], [0, 633.2, 245.8], [0, 0, 1]])


class BoundaryProbeTests(unittest.TestCase):
    def test_equal_depth_matches_simple_formula(self):
        condition = next(row for row in CFG["conditions"] if row["id"] == "equal_depth")
        points = marker_points(condition, CFG["marker_separation_m"])
        full, _ = project_width(points, 24, K)
        simple = K[0, 0] * CFG["marker_separation_m"] / 24
        self.assertAlmostEqual(full, simple)

    def test_rotated_and_skewed_geometry_differs_from_simple_formula(self):
        for condition in CFG["conditions"]:
            if condition["kind"] not in {"rigid_yaw", "depth_skew"}:
                continue
            for depth in CFG["center_depths_m"]:
                full, _ = project_width(
                    marker_points(condition, CFG["marker_separation_m"]), depth, K
                )
                simple = K[0, 0] * CFG["marker_separation_m"] / depth
                self.assertGreater(abs(full - simple), CFG["width_error_bound_px"])

    def test_offset_yaws_separate_common_depth_from_full_projection(self):
        selected = [
            row
            for row in CFG["conditions"]
            if row["id"] in {"yaw_plus45_offset3m", "yaw_minus45_offset3m"}
        ]
        self.assertEqual(len(selected), 2)
        for depth in CFG["center_depths_m"]:
            full = []
            common = []
            for condition in selected:
                points = marker_points(condition, CFG["marker_separation_m"])
                full.append(project_width(points, depth, K)[0])
                common.append(common_depth_width(points, depth, K))
            self.assertAlmostEqual(common[0], common[1])
            self.assertGreater(abs(full[0] - full[1]), 2 * CFG["width_error_bound_px"])
            for value, approximation in zip(full, common, strict=True):
                self.assertGreater(
                    abs(value - approximation), CFG["width_error_bound_px"]
                )

    def test_unavailable_requires_exact_single_marker_failure(self):
        self.assertTrue(
            is_single_marker_failure("expected exactly two visible markers, found 1")
        )
        self.assertFalse(
            is_single_marker_failure("expected exactly two visible markers, found 0")
        )
        self.assertFalse(is_single_marker_failure("marker touches image boundary"))

    def test_b2w_roundtrip_recovers_designed_camera_coordinates(self):
        angle = np.deg2rad(17)
        c2w = np.array(
            [
                [np.cos(angle), 0, np.sin(angle), 12],
                [0, 1, 0, -3],
                [-np.sin(angle), 0, np.cos(angle), 7],
                [0, 0, 0, 1],
            ]
        )
        condition = next(
            row for row in CFG["conditions"] if row["id"] == "yaw_plus45_offset3m"
        )
        points = marker_points(condition, CFG["marker_separation_m"])
        actual = roundtrip_render_camera_points(points, 24, c2w)
        np.testing.assert_allclose(actual, points + [0, 0, 24], atol=1e-12)

    def test_occluder_front_and_behind_share_left_marker_ray(self):
        conditions = [row for row in CFG["conditions"] if row["kind"] == "occlusion"]
        self.assertEqual(len(conditions), 2)
        for condition in conditions:
            points = marker_points(condition, CFG["marker_separation_m"])
            for depth in CFG["center_depths_m"]:
                occ = occluder_point(points, depth, condition)
                _, marker_uv = project_width(points, depth, K)
                _, occ_uv = project_width(np.stack([occ, occ]), depth, K)
                is_front = depth + occ[2] < depth + points[0, 2]
                self.assertEqual(is_front, condition["expected_occluded"])
                np.testing.assert_allclose(occ_uv[0], marker_uv[0], atol=1e-12)

    def test_repeat_comparison_catches_hash_or_measurement_change(self):
        row = {
            "context": "isolated",
            "center_depth_m": 16,
            "condition": "equal_depth",
            "kind": "equal_depth",
            "rgb_sha256": ["a", "b"],
            "measurement": {"width_px": 1},
            "measurement_failure": None,
            "full_prediction_within_budget": True,
            "simple_prediction_excluded": False,
            "common_depth_prediction_excluded": False,
            "availability_correct": True,
            "state_restore_check": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in [("left", [row]), ("right", [dict(row)])]:
                (root / name).mkdir()
                (root / name / "measurements.json").write_text(json.dumps(value))
            self.assertTrue(compare_runs(root / "left", root / "right")["all_repeat_checks_passed"])
            changed = dict(row)
            changed["rgb_sha256"] = ["x", "b"]
            (root / "right" / "measurements.json").write_text(json.dumps([changed]))
            self.assertFalse(compare_runs(root / "left", root / "right")["all_repeat_checks_passed"])


if __name__ == "__main__":
    unittest.main()
