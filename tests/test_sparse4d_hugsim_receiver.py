import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


receiver = load_module("sparse4d_receiver", "scripts/run_sparse4d_hugsim_receiver.py")
analysis = load_module("sparse4d_analysis", "scripts/analyze_sparse4d_hugsim_baseline.py")
cross_scene = load_module(
    "sparse4d_cross_scene", "scripts/analyze_sparse4d_cross_scene_baseline.py"
)
box_bias = load_module("sparse4d_box_bias", "scripts/analyze_sparse4d_box_bias.py")


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

    def test_lane_relation_uses_controlled_intervention_midpoint(self):
        self.assertEqual(cross_scene.lane_relation(0.2), "same_lane")
        self.assertEqual(cross_scene.lane_relation(-2.1), "right_adjacent_or_beyond")
        self.assertEqual(cross_scene.lane_relation(2.1), "left_adjacent_or_beyond")

    def test_normal_scene_summary_reports_threshold_stability(self):
        rows = [
            {
                "timestamp_s": 0.0,
                "predictions": [
                    {"label_id": 0, "class_name": "car", "score": 0.4, "instance_id": 7},
                    {"label_id": 8, "class_name": "pedestrian", "score": 0.6, "instance_id": 8},
                ],
            },
            {"timestamp_s": 0.5, "predictions": []},
        ]
        summary = cross_scene.summarize_normal_scene(rows)
        self.assertEqual(summary["thresholds"]["0.2"]["vehicle_positive_frame_count"], 1)
        self.assertEqual(summary["thresholds"]["0.5"]["vehicle_positive_frame_count"], 0)
        self.assertEqual(summary["thresholds"]["0.5"]["class_counts"], {"pedestrian": 1})

    def test_box_bias_iou_distinguishes_overlap(self):
        first = np.asarray([0.0, 0.0, 10.0, 10.0])
        same = np.asarray([0.0, 0.0, 10.0, 10.0])
        partial = np.asarray([5.0, 0.0, 15.0, 10.0])
        self.assertEqual(box_bias.box_iou(first, same), 1.0)
        self.assertAlmostEqual(box_bias.box_iou(first, partial), 1.0 / 3.0)


if __name__ == "__main__":
    unittest.main()
