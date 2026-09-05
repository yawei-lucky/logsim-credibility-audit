import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from make_hugsim_constant_velocity_actor_metadata import (  # noqa: E402
    audit_constant_velocity,
    constant_velocity_transforms,
    parse_condition_specs,
)


class HugsimConstantVelocityActorMetadataTest(unittest.TestCase):
    def test_condition_specs_require_unique_finite_timestamps(self):
        self.assertEqual(parse_condition_specs(["nominal=5.5"]), {"nominal": 5.5})
        with self.assertRaises(ValueError):
            parse_condition_specs(["bad=nan"])
        with self.assertRaises(ValueError):
            parse_condition_specs(["same=1", "same=2"])

    def test_constant_velocity_uses_released_timestamps_without_prestep(self):
        timestamps = {10: 1.0, 11: 1.08, 12: 1.17}
        poses = np.repeat(np.eye(4)[None], 3, axis=0)
        transforms = constant_velocity_transforms(
            timestamps=timestamps,
            conflict_xz=np.asarray([4.0, 7.0]),
            heading_deg=90.0,
            speed_mps=2.0,
            arrival_timestamp_s=1.08,
            camera_poses=poses,
            camera_height=1.5,
            actor_height_offset_m=-0.3,
        )
        np.testing.assert_allclose(transforms[11][[0, 2], 3], [4.0, 7.0])
        np.testing.assert_allclose(transforms[10][[0, 2], 3], [3.84, 7.0])
        audit = audit_constant_velocity(
            timestamps,
            transforms,
            heading_deg=90.0,
            speed_mps=2.0,
            arrival_timestamp_s=1.08,
            conflict_xz=np.asarray([4.0, 7.0]),
        )
        self.assertTrue(audit["passed"])
        self.assertLess(audit["maximum_step_residual_m"], 1e-12)

    def test_non_increasing_speed_is_rejected(self):
        with self.assertRaises(ValueError):
            constant_velocity_transforms(
                timestamps={1: 0.0, 2: 0.1},
                conflict_xz=np.asarray([0.0, 0.0]),
                heading_deg=0.0,
                speed_mps=0.0,
                arrival_timestamp_s=1.0,
                camera_poses=np.repeat(np.eye(4)[None], 2, axis=0),
                camera_height=1.5,
                actor_height_offset_m=-0.3,
            )


if __name__ == "__main__":
    unittest.main()
