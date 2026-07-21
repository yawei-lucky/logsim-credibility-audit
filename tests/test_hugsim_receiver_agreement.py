import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_hugsim_receiver_agreement import (  # noqa: E402
    agreement_checks,
    average_ranks,
    classify_run,
    spearman_from_values,
)


class HugsimReceiverAgreementTest(unittest.TestCase):
    def test_average_ranks_handles_ties(self):
        ranks = average_ranks({"a": 0.0, "b": 0.0, "c": 2.0})

        self.assertEqual(ranks["a"], 1.5)
        self.assertEqual(ranks["b"], 1.5)
        self.assertEqual(ranks["c"], 3.0)

    def test_spearman_is_one_for_same_tied_order(self):
        value = spearman_from_values(
            {"a": 0.0, "b": 0.0, "c": 1.0, "d": 2.0},
            {"a": 0.0, "b": 0.0, "c": 3.0, "d": 4.0},
        )

        self.assertAlmostEqual(value, 1.0)

    def test_classify_run_distinguishes_background_and_center(self):
        self.assertEqual(
            classify_run(
                {
                    "peak_proxy_center_signal": 1.0,
                    "peak_detector_center_signal": 2.0,
                    "proxy_visible_frames": 5,
                    "detector_detected_frames": 5,
                }
            ),
            "converged_center_path_signal",
        )
        self.assertEqual(
            classify_run(
                {
                    "peak_proxy_center_signal": 0.0,
                    "peak_detector_center_signal": 0.0,
                    "proxy_visible_frames": 0,
                    "detector_detected_frames": 4,
                }
            ),
            "converged_noncenter_or_background_signal",
        )

    def test_agreement_checks_accept_shared_directions(self):
        summaries = {
            "no_actor": {
                "peak_proxy_center_signal": 0.0,
                "peak_detector_center_signal": 0.0,
                "proxy_visible_frames": 0,
                "detector_detected_frames": 4,
            },
            "front_far": {
                "peak_proxy_center_signal": 1.0,
                "peak_detector_center_signal": 2.0,
            },
            "front_near": {
                "peak_proxy_center_signal": 3.0,
                "peak_detector_center_signal": 4.0,
            },
            "adjacent_near": {
                "peak_proxy_center_signal": 0.0,
                "peak_detector_center_signal": 0.0,
            },
            "multicar_merge": {
                "peak_proxy_center_signal": 5.0,
                "peak_detector_center_signal": 6.0,
            },
        }

        decisions = {item["id"]: item["decision"] for item in agreement_checks(summaries)}

        self.assertEqual(decisions["receiver_distance_direction_agreement"], "accepted")
        self.assertEqual(decisions["receiver_lane_direction_agreement"], "accepted")
        self.assertEqual(decisions["receiver_multicar_direction_agreement"], "accepted")
        self.assertEqual(decisions["receiver_background_divergence_boundary"], "accepted")


if __name__ == "__main__":
    unittest.main()
