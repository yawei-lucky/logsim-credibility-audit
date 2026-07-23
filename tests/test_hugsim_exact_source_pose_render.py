import sys
import unittest
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from render_hugsim_exact_source_pose import (  # noqa: E402
    CAMERAS,
    image_metrics,
    select_camera_records,
)


def identity(size):
    return [
        [1.0 if row == column else 0.0 for column in range(size)]
        for row in range(size)
    ]


class HugsimExactSourcePoseRenderTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
