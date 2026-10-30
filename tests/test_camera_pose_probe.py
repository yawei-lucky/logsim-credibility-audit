import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_camera_pose_probe import camera_reference_points, load_config, object_pose, predictions, preflight, relative_camera_pose


class CameraPoseContractTest(unittest.TestCase):
    def setUp(self):
        self.cfg, _ = load_config(ROOT / "configs/camera_pose_probe_001.json")

    def test_scalar_camera_inverse_matches_homogeneous_route(self):
        for fixture in self.cfg["objects"].values():
            points = np.column_stack([fixture["body_points_m"], np.ones(2)])
            for case in self.cfg["camera_poses"]:
                expected = (np.linalg.inv(relative_camera_pose(case)) @ object_pose(self.cfg, fixture) @ points.T).T[:, :3]
                np.testing.assert_allclose(camera_reference_points(self.cfg, fixture, case), expected, atol=1e-12)
        self.assertEqual(preflight(self.cfg)["primary_pairs"], 44)

    def test_camera_translation_has_inverse_sign_for_fixed_world(self):
        fixture = self.cfg["objects"]["level"]
        baseline = self.cfg["camera_poses"][0]
        right = next(c for c in self.cfg["camera_poses"] if c["id"] == "shift_right")
        delta = camera_reference_points(self.cfg, fixture, right) - camera_reference_points(self.cfg, fixture, baseline)
        np.testing.assert_allclose(delta, [[-1.5, 0, 0], [-1.5, 0, 0]], atol=1e-12)

    def test_baseline_ambiguity_and_moved_camera_discrimination(self):
        budget = self.cfg["suite"]["measurement"]["position_error_bound_px"]
        for fixture in self.cfg["objects"].values():
            for case in self.cfg["camera_poses"]:
                values = predictions(self.cfg, fixture, case)
                error = max(np.max(np.abs(np.asarray(values["inverse_camera_pose"][key]) - values["target_attached_to_camera"][key])) for key in ("left", "right"))
                self.assertEqual(error <= budget, case["family"] == "baseline")

    def test_equivalent_object_route_preserves_relative_pose(self):
        origin = np.eye(4)
        origin[:3, 3] = [13.5, -7.2, .8]
        for fixture in self.cfg["objects"].values():
            for case in self.cfg["camera_poses"]:
                a, body = relative_camera_pose(case), object_pose(self.cfg, fixture)
                moved_camera_relative = np.linalg.inv(origin @ a) @ (origin @ body)
                moved_object_relative = np.linalg.inv(origin) @ (origin @ np.linalg.inv(a) @ body)
                np.testing.assert_allclose(moved_camera_relative, moved_object_relative, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
