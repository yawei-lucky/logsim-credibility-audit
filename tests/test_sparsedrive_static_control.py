import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit_sparsedrive_static_control import (  # noqa: E402
    dynamic_inventory,
    nearest_class_detection,
    pairwise_detection_differences,
)


class SparseDriveStaticControlTest(unittest.TestCase):
    def test_nearest_class_detection_keeps_association_margin(self):
        frame = {
            "native": {
                "top_detections": [
                    {
                        "rank": 0,
                        "label_id": 8,
                        "score": 0.7,
                        "box": [1.0, 1.0, 0.0],
                    },
                    {
                        "rank": 1,
                        "label_id": 8,
                        "score": 0.5,
                        "box": [5.0, 5.0, 0.0],
                    },
                ]
            }
        }

        result = nearest_class_detection(frame, np.zeros(2), 8)

        self.assertEqual(result["rank"], 0)
        self.assertAlmostEqual(
            result["distance_to_declared_actor_xy_m"], np.sqrt(2)
        )
        self.assertGreater(result["association_margin_m"], 0.0)

    def test_missing_class_fails_closed(self):
        frame = {"native": {"top_detections": []}}
        with self.assertRaises(ValueError):
            nearest_class_detection(frame, np.zeros(2), 8)

    def test_pairwise_detection_differences_uses_all_resets(self):
        first = [
            {"center_xy_m": [0.0, 0.0], "score": 0.5},
            {"center_xy_m": [0.0, 0.0], "score": 0.5},
        ]
        second = [
            {"center_xy_m": [3.0, 4.0], "score": 0.6},
            {"center_xy_m": [3.0, 4.0], "score": 0.6},
        ]

        result = pairwise_detection_differences(first, second)

        self.assertEqual(len(result["pairings"]), 4)
        self.assertEqual(result["center_xy_distance_m"]["mean"], 5.0)
        self.assertAlmostEqual(
            result["absolute_score_difference"]["mean"], 0.1
        )

    def test_dynamic_inventory_preserves_empty_tail(self):
        metadata = {"frames": []}
        for index, present in ((0, True), (1, False)):
            for camera in range(6):
                metadata["frames"].append(
                    {
                        "rgb_path": f"./images/CAM_{camera}/{index:05d}.jpg",
                        "dynamics": {"actor": []} if present else {},
                    }
                )

        result = dynamic_inventory(metadata)

        self.assertEqual(result["dynamic_ids"], ["actor"])
        self.assertEqual(result["all_six_cameras_dynamic_frame_count"], 1)
        self.assertEqual(result["all_six_cameras_empty_frame_count"], 1)
        self.assertEqual(result["empty_dynamic_frame_indices"], [1])


if __name__ == "__main__":
    unittest.main()
