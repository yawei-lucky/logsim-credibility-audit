import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from make_hugsim_lead_counterfactual_metadata import (  # noqa: E402
    add_actor,
    lead_transform,
    path_lead_anchor,
    parse_condition_specs,
)
from render_hugsim_exact_source_pose import CAMERAS  # noqa: E402


class HugsimLeadCounterfactualMetadataTest(unittest.TestCase):
    def test_condition_specs_are_positive_and_unique(self):
        self.assertEqual(
            parse_condition_specs(["weak=32", "strong=23"]),
            {"weak": 32.0, "strong": 23.0},
        )
        with self.assertRaises(ValueError):
            parse_condition_specs(["strong=-1"])
        with self.assertRaises(ValueError):
            parse_condition_specs(["weak=32", "weak=23"])

    def test_stationary_lead_is_placed_forward_on_flat_ground(self):
        camera_poses = np.repeat(np.eye(4)[None], 2, axis=0)
        transform = lead_transform(
            np.asarray([0.0, 20.0]),
            np.asarray([0.0, 1.0]),
            camera_poses,
            1.5,
            -0.3,
        )
        np.testing.assert_allclose(transform[:3, 3], [0.0, 1.2, 20.0])
        np.testing.assert_allclose(transform[:3, 0], [0.0, 0.0, 1.0], atol=1e-7)

    def test_path_anchor_interpolates_along_source_curve(self):
        frames = []
        positions = {12: (0.0, 0.0), 13: (0.0, 4.0), 14: (3.0, 8.0)}
        for frame_index, (world_x, world_z) in positions.items():
            for camera in CAMERAS:
                pose = np.eye(4)
                pose[0, 3] = world_x
                pose[2, 3] = world_z
                frames.append(
                    {
                        "rgb_path": f"./images/{camera}/{frame_index:05d}.jpg",
                        "timestamp": frame_index / 12,
                        "intrinsics": np.eye(4).tolist(),
                        "camtoworld": pose.tolist(),
                    }
                )
        result = path_lead_anchor(
            {"frames": frames},
            12,
            6.5,
            np.eye(4),
        )
        self.assertEqual(result["bracketing_frames"], [13, 14])
        np.testing.assert_allclose(result["world_xz"], [1.5, 6.0])

    def test_actor_is_added_to_each_selected_camera_only(self):
        frames = []
        for frame_index in (12, 18):
            for camera in CAMERAS:
                frames.append(
                    {
                        "rgb_path": f"./images/{camera}/{frame_index:05d}.jpg",
                        "timestamp": frame_index / 12,
                        "dynamics": {},
                    }
                )
        result = add_actor(
            {"frames": frames},
            [18],
            "audit_lead",
            {18: np.eye(4)},
        )
        for frame in result["frames"]:
            if frame["rgb_path"].endswith("00018.jpg"):
                self.assertIn("audit_lead", frame["dynamics"])
            else:
                self.assertNotIn("audit_lead", frame["dynamics"])


if __name__ == "__main__":
    unittest.main()
