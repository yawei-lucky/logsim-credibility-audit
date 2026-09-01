import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from make_hugsim_actor_placement_metadata import (  # noqa: E402
    candidate_transform,
    heading_vector,
    nearest_path_relation,
    parse_candidate_specs,
)


class HugsimActorPlacementMetadataTest(unittest.TestCase):
    def test_candidate_specs_are_finite_and_unique(self):
        self.assertEqual(
            parse_candidate_specs(["left=-8,30,90", "right=4,30,-90"]),
            {"left": (-8.0, 30.0, 90.0), "right": (4.0, 30.0, -90.0)},
        )
        with self.assertRaises(ValueError):
            parse_candidate_specs(["bad=1,2"])
        with self.assertRaises(ValueError):
            parse_candidate_specs(["same=1,2,3", "same=4,5,6"])
        with self.assertRaises(ValueError):
            parse_candidate_specs(["bad=nan,2,3"])

    def test_heading_uses_world_positive_z_as_zero(self):
        np.testing.assert_allclose(heading_vector(0.0), [0.0, 1.0], atol=1e-12)
        np.testing.assert_allclose(heading_vector(90.0), [1.0, 0.0], atol=1e-12)
        np.testing.assert_allclose(heading_vector(-90.0), [-1.0, 0.0], atol=1e-12)

    def test_candidate_transform_places_actor_on_flat_ground(self):
        camera_poses = np.repeat(np.eye(4)[None], 2, axis=0)
        transform = candidate_transform(
            -2.0,
            30.0,
            90.0,
            camera_poses,
            1.5,
            -0.3,
        )
        np.testing.assert_allclose(transform[:3, 3], [-2.0, 1.2, 30.0])
        np.testing.assert_allclose(transform[:3, 0], [1.0, 0.0, 0.0], atol=1e-7)

    def test_nearest_path_relation_distinguishes_opposing_from_crossing(self):
        path = [
            {
                "frame_index": index,
                "timestamp_s": float(index),
                "world_x_m": -float(index),
                "world_z_m": 30.0,
            }
            for index in range(5)
        ]
        opposing = nearest_path_relation(path, -2.1, 30.0, 90.0)
        crossing = nearest_path_relation(path, -2.1, 30.0, 0.0)

        self.assertEqual(opposing["nearest_frame_index"], 2)
        self.assertAlmostEqual(opposing["centre_distance_m"], 0.1)
        self.assertAlmostEqual(opposing["absolute_heading_difference_deg"], 180.0)
        self.assertAlmostEqual(crossing["absolute_heading_difference_deg"], 90.0)


if __name__ == "__main__":
    unittest.main()
