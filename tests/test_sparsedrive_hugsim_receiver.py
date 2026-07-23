import math
import sys
import unittest
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_sparsedrive_hugsim_receiver import (  # noqa: E402
    CAMERA_ORDER,
    command_vector,
    densify_plan,
    ego_status_vector,
    ego_status_sources,
    model_lidar_to_hugsim_vehicle,
    plan_kinematics,
    project_model_plan_to_raw_camera,
    tensor_summary,
    wrapped_rate,
)


def info(
    *,
    timestamp=0.0,
    yaw=0.0,
    command=2,
    acceleration=0.5,
    speed=3.0,
    steer=0.1,
):
    return {
        "timestamp": timestamp,
        "ego_box": [0, 0, 0, 1.6, 3.0, 1.5, yaw],
        "command": command,
        "accelerate": acceleration,
        "ego_velo": speed,
        "ego_steer": steer,
    }


class SparseDriveHugsimReceiverTest(unittest.TestCase):
    def test_model_lidar_calibration_rotates_axes_and_is_shared(self):
        model_right = np.asarray([1.0, 0.0, 0.0, 1.0])
        model_forward = np.asarray([0.0, 1.0, 0.0, 1.0])
        expected = np.asarray(
            [
                [0.0, 1.0, 0.0, 0.0],
                [-1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        camera = {"v2c": np.eye(4), "l2c": expected}
        calibration = model_lidar_to_hugsim_vehicle(
            {"cam_params": {name: camera for name in CAMERA_ORDER}}
        )

        np.testing.assert_allclose(
            calibration @ model_right,
            [0.0, -1.0, 0.0, 1.0],
        )
        np.testing.assert_allclose(
            calibration @ model_forward,
            [1.0, 0.0, 0.0, 1.0],
        )

    def test_plan_kinematics_uses_half_second_waypoints(self):
        diagnostic = plan_kinematics(
            np.asarray([[0.0, 1.0], [0.0, 2.5]]),
            ego_speed_mps=2.0,
        )

        self.assertEqual(diagnostic["horizon_seconds"], 1.0)
        self.assertEqual(diagnostic["step_speeds_mps"], [2.0, 3.0])
        self.assertTrue(diagnostic["forward_monotonic_non_decreasing"])
        self.assertEqual(diagnostic["first_step_speed_error_mps"], 0.0)
        self.assertEqual(
            diagnostic["first_step_equivalent_constant_acceleration_mps2"],
            0.0,
        )

    def test_densify_plan_includes_origin_and_final_waypoint(self):
        dense = densify_plan(np.asarray([[0.0, 1.0], [1.0, 2.0]]), 2)

        np.testing.assert_allclose(
            dense,
            [[0.0, 0.0], [0.0, 0.5], [0.0, 1.0], [0.5, 1.5], [1.0, 2.0]],
        )

    def test_forward_plan_projects_near_front_image_center(self):
        camera = {
            "intrinsic": {
                "H": 100,
                "W": 200,
                "cx": 100.0,
                "cy": 50.0,
                "fovx": np.pi / 2,
                "fovy": np.pi / 2,
            },
            "v2c": np.asarray(
                [
                    [0.0, -1.0, 0.0, 0.0],
                    [0.0, 0.0, -1.0, 0.0],
                    [1.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0],
                ]
            ),
        }
        model_to_vehicle = np.asarray(
            [
                [0.0, 1.0, 0.0, 0.0],
                [-1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        camera["l2c"] = camera["v2c"] @ model_to_vehicle
        projected = project_model_plan_to_raw_camera(
            np.asarray([[0.0, 10.0]]),
            {"cam_params": {name: camera for name in CAMERA_ORDER}},
            model_z_m=0.0,
            points_per_step=1,
        )

        self.assertTrue(projected["waypoint_visible"][0])
        np.testing.assert_allclose(projected["waypoint_pixels"][0], [100.0, 50.0])

    def test_command_order_is_right_left_straight(self):
        np.testing.assert_array_equal(command_vector(info(command=0)), [1, 0, 0])
        np.testing.assert_array_equal(command_vector(info(command=1)), [0, 1, 0])
        np.testing.assert_array_equal(command_vector(info(command=2)), [0, 0, 1])
        with self.assertRaisesRegex(ValueError, "unsupported"):
            command_vector(info(command=3))

    def test_ego_status_mapping_and_yaw_rate(self):
        previous = info(timestamp=1.0, yaw=0.2)
        current = info(
            timestamp=1.5,
            yaw=0.3,
            acceleration=1.25,
            speed=4.5,
            steer=-0.2,
        )
        status = ego_status_vector(current, previous)

        self.assertEqual(status.shape, (10,))
        self.assertAlmostEqual(status[0], 1.25)
        self.assertAlmostEqual(status[5], 0.2)
        self.assertAlmostEqual(status[6], 4.5)
        self.assertAlmostEqual(status[9], -0.2)

    def test_pose_derived_ego_status_uses_three_sampled_poses(self):
        earlier = info(timestamp=0.0, speed=99.0)
        earlier["ego_box"][:3] = [0.0, 0.0, 0.0]
        previous = info(timestamp=0.5, speed=99.0)
        previous["ego_box"][:3] = [0.5, 0.0, 0.0]
        current = info(timestamp=1.0, speed=99.0, steer=0.1)
        current["ego_box"][:3] = [1.5, 0.0, 0.0]

        status = ego_status_vector(
            current,
            previous,
            earlier,
            mode="pose_derived",
        )

        np.testing.assert_allclose(status[:3], [2.0, 0.0, 0.0])
        np.testing.assert_allclose(status[3:6], [0.0, 0.0, 0.0])
        np.testing.assert_allclose(status[6:9], [2.0, 0.0, 0.0])
        self.assertAlmostEqual(status[9], 0.1)

    def test_pose_derived_ego_status_requires_two_preceding_poses(self):
        with self.assertRaisesRegex(ValueError, "two preceding"):
            ego_status_vector(
                info(timestamp=1.0),
                info(timestamp=0.5),
                mode="pose_derived",
            )

    def test_ego_status_sources_are_explicit(self):
        self.assertIn("observed", " ".join(ego_status_sources("recorded_scalar")))
        self.assertIn(
            "finite difference",
            " ".join(ego_status_sources("pose_derived")),
        )

    def test_wrapped_rate_crosses_pi_without_jump(self):
        rate = wrapped_rate(-math.pi + 0.05, math.pi - 0.05, 0.5)
        self.assertAlmostEqual(rate, 0.2)

    def test_numpy_tensor_summary_reports_non_finite(self):
        class FakeTorch:
            @staticmethod
            def is_tensor(_value):
                return False

        summary = tensor_summary(np.asarray([1.0, np.nan]), torch=FakeTorch())
        self.assertEqual(summary["shape"], [2])
        self.assertFalse(summary["finite"])


if __name__ == "__main__":
    unittest.main()
