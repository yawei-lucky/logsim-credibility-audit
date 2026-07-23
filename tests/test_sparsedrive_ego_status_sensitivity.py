import copy
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_sparsedrive_ego_status_sensitivity import analyze_reports  # noqa: E402


def report(mode: str, forward: float = 5.0) -> dict:
    frame = {
        "frame_index": 10,
        "timestamp_s": 2.5,
        "native": {
            "final_planning_values": [
                [0.0, 1.0],
                [0.0, 2.0],
                [0.0, 3.0],
                [0.0, 4.0],
                [0.0, 4.5],
                [0.0, forward],
            ]
        },
        "plan_geometry": {
            "forward_monotonic_non_decreasing": True,
            "final_forward_m": forward,
            "final_right_m": 0.0,
            "first_step_speed_mps": 2.0,
        },
        "planning_selection": {"selected_mode_index": 2},
    }
    return {
        "all_outputs_finite": True,
        "all_resets_reproducible": True,
        "model": {"checkpoint_sha256": "checkpoint"},
        "conditions": [
            {
                "input": "/same/run",
                "ego_status_mode": mode,
                "selected_frame_indices": [10],
                "frames": [frame],
                "input_contracts": [{"ego_status_10d": [0.0] * 10}],
            }
        ],
    }


class SparseDriveEgoStatusSensitivityTest(unittest.TestCase):
    def test_accepts_shared_forward_structure_and_reports_delta(self):
        result = analyze_reports(
            report("recorded_scalar", 5.0),
            report("pose_derived", 4.8),
        )

        self.assertEqual(
            result["evidence_decisions"]["structural_baseline_stability"][
                "decision"
            ],
            "accepted",
        )
        self.assertAlmostEqual(
            result["fully_warmed_frame"]["final_endpoint_delta_m"],
            0.2,
        )
        self.assertEqual(
            result["evidence_decisions"]["quantitative_plan_equivalence"][
                "decision"
            ],
            "down-weighted",
        )

    def test_accepts_numerical_equivalence_inside_reset_envelope(self):
        result = analyze_reports(
            report("recorded_scalar", 5.0),
            report("pose_derived", 5.00001),
        )

        self.assertTrue(result["within_reset_numerical_envelope"])
        self.assertEqual(
            result["evidence_decisions"]["quantitative_plan_equivalence"][
                "decision"
            ],
            "accepted",
        )

    def test_rejects_mismatched_frame_contract(self):
        pose = report("pose_derived")
        pose["conditions"][0]["selected_frame_indices"] = [12]

        with self.assertRaisesRegex(ValueError, "different receiver frames"):
            analyze_reports(report("recorded_scalar"), pose)

    def test_rejects_non_forward_pose_variant(self):
        pose = report("pose_derived", -1.0)
        pose["conditions"][0]["frames"][0]["plan_geometry"][
            "forward_monotonic_non_decreasing"
        ] = False

        result = analyze_reports(report("recorded_scalar"), pose)

        self.assertEqual(
            result["evidence_decisions"]["structural_baseline_stability"][
                "decision"
            ],
            "rejected",
        )


if __name__ == "__main__":
    unittest.main()
