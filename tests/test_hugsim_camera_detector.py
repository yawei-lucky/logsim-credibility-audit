import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_hugsim_camera_detector import (  # noqa: E402
    box_iou,
    causal_checks,
    detection_feature,
    summarize_rows,
)


class HugsimCameraDetectorTest(unittest.TestCase):
    def test_detection_feature_rewards_center_overlap(self):
        center = detection_feature(
            [360.0, 180.0, 460.0, 300.0],
            "car",
            0.8,
            (450, 800),
        )
        side = detection_feature(
            [650.0, 180.0, 760.0, 300.0],
            "car",
            0.8,
            (450, 800),
        )

        self.assertGreater(center["center_path_risk_proxy"], 0.0)
        self.assertEqual(side["center_path_risk_proxy"], 0.0)
        self.assertGreater(center["risk_proxy"], side["risk_proxy"])

    def test_box_iou_handles_missing_and_overlap(self):
        a = {"bbox_xyxy": [0.0, 0.0, 10.0, 10.0]}
        b = {"bbox_xyxy": [5.0, 5.0, 15.0, 15.0]}

        self.assertIsNone(box_iou(None, b))
        self.assertAlmostEqual(box_iou(a, b), 25.0 / 175.0)

    def test_summarize_rows_counts_center_presence(self):
        rows = [
            {
                "detection_count": 0,
                "center_path_detection_count": 0,
                "timestamp_s": 0.0,
                "top_score": 0.0,
                "top_risk_proxy": 0.0,
                "center_top_risk_proxy": 0.0,
                "top_bbox_area_fraction": 0.0,
                "center_top_bbox_area_fraction": 0.0,
                "top_iou_to_prev": None,
                "center_top_iou_to_prev": None,
            },
            {
                "detection_count": 2,
                "center_path_detection_count": 1,
                "timestamp_s": 0.25,
                "top_score": 0.9,
                "top_risk_proxy": 3.0,
                "center_top_risk_proxy": 2.0,
                "top_bbox_area_fraction": 0.1,
                "center_top_bbox_area_fraction": 0.08,
                "top_iou_to_prev": 0.5,
                "center_top_iou_to_prev": 0.4,
            },
        ]

        summary = summarize_rows(rows)

        self.assertEqual(summary["detected_frame_count"], 1)
        self.assertEqual(summary["center_detected_frame_count"], 1)
        self.assertEqual(summary["peak_center_risk_proxy"], 2.0)
        self.assertEqual(summary["mean_center_iou_to_prev"], 0.4)

    def test_causal_checks_accept_expected_direction(self):
        summaries = {
            "no_actor": {
                "detected_frame_count": 1,
                "peak_top_risk_proxy": 0.5,
                "peak_center_risk_proxy": 0.0,
            },
            "front_far": {
                "peak_center_risk_proxy": 2.0,
                "peak_center_bbox_area_fraction": 0.02,
                "maximum_detection_count": 1,
            },
            "front_near": {
                "peak_center_risk_proxy": 5.0,
                "peak_center_bbox_area_fraction": 0.06,
                "center_presence_stability": 1.0,
            },
            "adjacent_near": {
                "peak_center_risk_proxy": 0.0,
                "center_presence_stability": 0.0,
            },
            "multicar_merge": {
                "peak_center_risk_proxy": 8.0,
                "maximum_detection_count": 3,
            },
        }

        decisions = {
            check["id"]: check["decision"]
            for check in causal_checks(summaries)
        }

        self.assertEqual(
            decisions["detector_distance_response_front_near_vs_far"],
            "accepted",
        )
        self.assertEqual(
            decisions["detector_lane_relation_front_vs_adjacent"],
            "accepted",
        )
        self.assertEqual(decisions["detector_multicar_prominence"], "accepted")
        self.assertEqual(decisions["detector_background_response"], "accepted")


if __name__ == "__main__":
    unittest.main()
