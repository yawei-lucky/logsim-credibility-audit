import copy
import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_sparsedrive_real_sim_factual import (  # noqa: E402
    cf_r_scale,
    validate_pair,
)


def report(plan):
    plan = np.asarray(plan, dtype=float)
    return {
        "model": {
            "checkpoint_sha256": "checkpoint",
            "config_sha256": "config",
        },
        "adapter": {"sha256": "adapter"},
        "baseline": {
            "frames": [
                {
                    "source_frame_index": 30,
                    "timestamp_s": 2.5,
                    "input_contract": {
                        "ego_status_10d": [0.0] * 10,
                        "command_one_hot_right_left_straight": [0.0, 0.0, 1.0],
                        "front_model_to_camera": np.eye(4).tolist(),
                        "camera_inputs": [
                            {
                                "camera": "CAM_FRONT",
                                "image_path": "/tmp/front.png",
                            }
                        ],
                    },
                    "native": {
                        "final_planning_values": plan.tolist(),
                        "planning_score_values": np.zeros((3, 6)).tolist(),
                    },
                    "planning_selection": {"selected_mode_index": 3},
                    "recorded_camera_rig_future_xy_m": np.zeros((6, 2)).tolist(),
                    "plan_reference_error": {"ade_m": 0.0, "fde_m": 0.0},
                }
            ]
        },
    }


class SparseDriveRealSimFactualTest(unittest.TestCase):
    def test_validate_pair_measures_native_plan_domain_difference(self):
        real = report(np.zeros((6, 2)))
        sim_plan = np.zeros((6, 2))
        sim_plan[:, 1] = 1.0
        sim = report(sim_plan)
        row = validate_pair(real, sim)["rows"][0]
        self.assertAlmostEqual(row["plan_domain_ade_m"], 1.0)
        self.assertAlmostEqual(row["plan_domain_fde_m"], 1.0)
        self.assertAlmostEqual(
            row["final_forward_delta_sim_minus_real_m"],
            1.0,
        )
        self.assertTrue(row["mode_equal"])

    def test_validate_pair_fails_when_held_fixed_state_differs(self):
        real = report(np.zeros((6, 2)))
        sim = copy.deepcopy(real)
        sim["baseline"]["frames"][0]["input_contract"]["ego_status_10d"][0] = 1.0
        with self.assertRaises(ValueError):
            validate_pair(real, sim)

    def test_cf_r_scale_is_diagnostic_not_an_upgrade(self):
        audit = {
            "planning": {
                "median_final_forward_m": {
                    "slow": 3.0,
                    "nominal": 4.0,
                    "fast": 4.5,
                },
                "pair_results": {
                    "a": {"minimum_margin_m": 0.2},
                    "b": {"minimum_margin_m": 0.1},
                },
            }
        }
        result = cf_r_scale(audit)
        self.assertAlmostEqual(result["strong_to_weak_median_effect_m"], 1.5)
        self.assertAlmostEqual(
            result["minimum_adjacent_or_pairwise_margin_m"],
            0.1,
        )
        self.assertIn("cannot upgrade", result["comparison_boundary"])


if __name__ == "__main__":
    unittest.main()
