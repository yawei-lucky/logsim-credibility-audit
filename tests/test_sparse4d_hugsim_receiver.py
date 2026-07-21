import importlib.util
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


receiver = load_module("sparse4d_receiver", "scripts/run_sparse4d_hugsim_receiver.py")
analysis = load_module("sparse4d_analysis", "scripts/analyze_sparse4d_hugsim_baseline.py")


class Sparse4DHugsimReceiverTest(unittest.TestCase):
    def test_half_resolution_image_preserves_official_crop_ratio(self):
        image = np.zeros((450, 800, 3), dtype=np.uint8)
        transformed, matrix, contract = receiver.resize_crop_rgb(image)
        self.assertEqual(transformed.shape, (256, 704, 3))
        self.assertAlmostEqual(contract["resize"], 0.88)
        self.assertEqual(contract["crop_xyxy"], [0, 140, 704, 396])
        np.testing.assert_allclose(matrix[:2, :2], [[0.88, 0], [0, 0.88]])
        np.testing.assert_allclose(matrix[:2, 2], [0, -140])

    def test_actor_matching_separates_score_and_geometry(self):
        actor = [{"actor_index": 0, "center_vehicle_xyz": [7.0, 0.0, 0.0]}]
        predictions = [
            {
                "rank": 0,
                "label_id": 0,
                "class_name": "car",
                "score": 0.8,
                "box_xyz_wlh_yaw_vxyz": [11.5, 0.0, 0.0, 4, 2, 1.5, 0],
            },
            {
                "rank": 1,
                "label_id": 0,
                "class_name": "car",
                "score": 0.1,
                "box_xyz_wlh_yaw_vxyz": [7.2, 0.0, 0.0, 4, 2, 1.5, 0],
            },
        ]
        match = receiver.match_actors(actor, predictions, score_threshold=0.2)[0]
        self.assertAlmostEqual(match["nearest_all"]["center_xy_error_m"], 0.2)
        self.assertAlmostEqual(match["nearest_qualified"]["center_xy_error_m"], 4.5)
        self.assertFalse(match["qualified_within_4m"])

    def test_run_metrics_counts_only_qualified_vehicle_classes(self):
        rows = [
            {
                "timestamp_s": 0.0,
                "predictions": [
                    {"label_id": 0, "score": 0.3},
                    {"label_id": 8, "score": 0.9},
                    {"label_id": 1, "score": 0.1},
                ],
                "actor_references": [],
                "actor_matches": [],
            },
            {
                "timestamp_s": 0.5,
                "predictions": [],
                "actor_references": [],
                "actor_matches": [],
            },
        ]
        metrics = analysis.run_metrics(rows, threshold=0.2)
        self.assertEqual(metrics["vehicle_detection_count"], 1)
        self.assertEqual(metrics["vehicle_detections_per_frame"], 0.5)
        self.assertEqual(metrics["vehicle_positive_frame_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
