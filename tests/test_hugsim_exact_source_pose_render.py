import sys
import tempfile
import unittest
from pathlib import Path

import imageio.v2 as imageio
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from render_hugsim_exact_source_pose import (  # noqa: E402
    CAMERAS,
    image_metrics,
    load_reference_inputs,
    parse_checkpoint_specs,
    records_without_dynamics,
    select_camera_names,
    select_camera_records,
)


def identity(size):
    return [
        [1.0 if row == column else 0.0 for column in range(size)]
        for row in range(size)
    ]


class HugsimExactSourcePoseRenderTest(unittest.TestCase):
    def complete_frames(self):
        return [
            {
                "rgb_path": f"./images/{camera}/00004.jpg",
                "timestamp": 0.4,
                "intrinsics": identity(4),
                "camtoworld": identity(4),
                "width": 8,
                "height": 6,
            }
            for camera in CAMERAS
        ]

    def test_camera_selection_preserves_default_and_explicit_order(self):
        self.assertEqual(select_camera_names(), CAMERAS)
        self.assertEqual(select_camera_names([]), CAMERAS)
        self.assertEqual(
            select_camera_names(["CAM_BACK", "CAM_FRONT"]),
            ("CAM_BACK", "CAM_FRONT"),
        )
        for names in (["CAM_FRONT", "CAM_FRONT"], ["UNKNOWN"]):
            with self.assertRaises(ValueError):
                select_camera_names(names)

        records = select_camera_records(
            {"frames": self.complete_frames()}, 4, ["CAM_BACK", "CAM_FRONT"]
        )
        self.assertEqual(list(records), ["CAM_BACK", "CAM_FRONT"])

    def test_single_camera_selection_still_validates_unselected_metadata(self):
        frames = self.complete_frames()
        invalid_groups = [frames[:-1], [*frames, dict(frames[-1])]]
        mismatched_time = [dict(frame) for frame in frames]
        mismatched_time[-1]["timestamp"] = 0.5
        invalid_groups.append(mismatched_time)
        for invalid in invalid_groups:
            with self.subTest(group=invalid):
                with self.assertRaises(ValueError):
                    select_camera_records({"frames": invalid}, 4, ["CAM_FRONT"])

    def test_single_camera_requires_only_its_source_rgb(self):
        records = select_camera_records(
            {"frames": self.complete_frames()}, 4, ["CAM_FRONT"]
        )
        source = np.full((6, 8, 3), 37, dtype=np.uint8)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "images/CAM_FRONT/00004.jpg"
            path.parent.mkdir(parents=True)
            imageio.imwrite(path, source)
            images, paths = load_reference_inputs(records, root)
            self.assertEqual(list(images), ["CAM_FRONT"])
            self.assertEqual(paths, {"CAM_FRONT": path})
            np.testing.assert_array_equal(images["CAM_FRONT"], source)

    def test_checkpoint_specs_require_existing_unique_paths(self):
        parsed = parse_checkpoint_specs([f"actor={__file__}"])
        self.assertEqual(parsed["actor"], Path(__file__).resolve())
        with self.assertRaises(ValueError):
            parse_checkpoint_specs([f"actor={__file__}", f"actor={__file__}"])
        with self.assertRaises(FileNotFoundError):
            parse_checkpoint_specs(["actor=/definitely/missing.pth"])

    def test_selects_one_complete_timestamp_group(self):
        frames = []
        for frame_index in (3, 4):
            for camera in CAMERAS:
                frames.append(
                    {
                        "rgb_path": f"./images/{camera}/{frame_index:05d}.jpg",
                        "timestamp": frame_index / 10,
                        "intrinsics": identity(4),
                        "camtoworld": identity(4),
                    }
                )
        records = select_camera_records({"frames": frames}, 4)

        self.assertEqual(set(records), set(CAMERAS))
        self.assertEqual({record["timestamp"] for record in records.values()}, {0.4})

    def test_incomplete_camera_group_is_rejected(self):
        frames = [
            {
                "rgb_path": f"./images/{camera}/00004.jpg",
                "timestamp": 0.4,
                "intrinsics": identity(4),
                "camtoworld": identity(4),
            }
            for camera in CAMERAS[:-1]
        ]
        with self.assertRaisesRegex(ValueError, "not a six-camera group"):
            select_camera_records({"frames": frames}, 4)

    def test_static_control_clears_dynamics_without_mutating_source(self):
        records = {
            "CAM_FRONT": {
                "timestamp": 1.0,
                "dynamics": {"actor": identity(4)},
            }
        }
        control = records_without_dynamics(records)

        self.assertEqual(control["CAM_FRONT"]["dynamics"], {})
        self.assertIn("actor", records["CAM_FRONT"]["dynamics"])

    def test_image_metrics_detect_identity_and_error(self):
        real = np.zeros((8, 8, 3), dtype=np.uint8)
        identical = image_metrics(real, real)
        different = image_metrics(real, np.full_like(real, 255))

        self.assertEqual(identical["mae"], 0)
        self.assertEqual(identical["mse"], 0)
        self.assertEqual(identical["psnr_db"], float("inf"))
        self.assertEqual(different["mae"], 1)
        self.assertEqual(different["mse"], 1)
        self.assertEqual(different["psnr_db"], 0)

    def test_render_only_reference_is_explicit_zero_placeholder(self):
        records = {
            camera: {
                "rgb_path": f"./images/{camera}/00004.jpg",
                "width": 8,
                "height": 6,
            }
            for camera in CAMERAS
        }
        images, paths = load_reference_inputs(records, None)

        self.assertEqual(set(images), set(CAMERAS))
        self.assertTrue(all(image.shape == (6, 8, 3) for image in images.values()))
        self.assertTrue(all(not image.any() for image in images.values()))
        self.assertTrue(all(path is None for path in paths.values()))


if __name__ == "__main__":
    unittest.main()
