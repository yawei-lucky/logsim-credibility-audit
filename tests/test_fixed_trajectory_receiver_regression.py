import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compare_fixed_trajectory_receiver_regression import (
    compare_native_nodes,
    domain_row,
    normalized_input_contract,
    recompute_reset_repeat,
    report_native_plan_difference,
)


class FixedTrajectoryReceiverRegressionTests(unittest.TestCase):
    def test_native_comparison_accepts_small_float_change_and_counts_it(self):
        first = {
            "float": np.asarray([1.0, 2.0], dtype=np.float32),
            "integer": np.asarray([1, 2], dtype=np.int64),
            "nested": [True, "fixed", None],
        }
        second = {
            "float": np.asarray([1.0, 2.00001], dtype=np.float32),
            "integer": np.asarray([1, 2], dtype=np.int64),
            "nested": [True, "fixed", None],
        }
        result = compare_native_nodes(first, second)
        self.assertTrue(result["structure_equal"])
        self.assertTrue(result["float_all_finite"])
        self.assertEqual(result["float_changed_count"], 1)
        self.assertEqual(result["integer_mismatch_count"], 0)
        self.assertGreater(result["max_abs_float_difference"], 0)
        self.assertLess(result["max_abs_float_difference"], 1e-4)

    def test_native_comparison_rejects_structure_dtype_and_integer_changes(self):
        shape = compare_native_nodes(
            np.zeros((2,), dtype=np.float32),
            np.zeros((3,), dtype=np.float32),
        )
        self.assertFalse(shape["structure_equal"])
        dtype = compare_native_nodes(
            np.zeros((2,), dtype=np.float32),
            np.zeros((2,), dtype=np.float64),
        )
        self.assertFalse(dtype["structure_equal"])
        integer = compare_native_nodes(
            np.asarray([1, 2], dtype=np.int64),
            np.asarray([1, 3], dtype=np.int64),
        )
        self.assertEqual(integer["integer_mismatch_count"], 1)

    def test_native_comparison_distinguishes_bool_from_integer(self):
        result = compare_native_nodes(True, 1)
        self.assertFalse(result["structure_equal"])

    def test_native_comparison_distinguishes_numpy_scalar_dtypes(self):
        self.assertFalse(
            compare_native_nodes(np.int32(1), np.int64(1))["structure_equal"]
        )
        self.assertFalse(
            compare_native_nodes(np.float32(1), np.float64(1))["structure_equal"]
        )

    def test_native_comparison_rejects_non_finite_values(self):
        result = compare_native_nodes(
            np.asarray([1.0], dtype=np.float32),
            np.asarray([np.nan], dtype=np.float32),
        )
        self.assertFalse(result["float_all_finite"])
        self.assertFalse(result["structure_equal"])

    def test_normalized_contract_only_ignores_image_paths(self):
        first = {
            "timestamp_s": 1.0,
            "camera_inputs": [
                {"camera": "CAM_FRONT", "image_path": "/old/image.png"}
            ],
            "ego_status_10d": [1.0, 2.0],
        }
        second = {
            "timestamp_s": 1.0,
            "camera_inputs": [
                {"camera": "CAM_FRONT", "image_path": "/new/image.png"}
            ],
            "ego_status_10d": [1.0, 2.0],
        }
        self.assertEqual(
            normalized_input_contract(first), normalized_input_contract(second)
        )
        second["ego_status_10d"][1] = 3.0
        self.assertNotEqual(
            normalized_input_contract(first), normalized_input_contract(second)
        )

    def test_domain_row_uses_all_six_plan_steps_and_final_step(self):
        real = {
            "source_frame_index": 12,
            "native": {"final_planning_values": [[0.0, 0.0]] * 6},
            "planning_selection": {"selected_mode_index": 1},
        }
        sim = {
            "source_frame_index": 12,
            "native": {
                "final_planning_values": [[3.0, 4.0]] * 5 + [[0.0, 10.0]]
            },
            "planning_selection": {"selected_mode_index": 2},
        }
        result = domain_row(real, sim, history_depth=4)
        self.assertAlmostEqual(result["plan_domain_ade_m"], 35.0 / 6.0)
        self.assertAlmostEqual(result["plan_domain_fde_m"], 10.0)
        self.assertEqual(result["final_right_delta_sim_minus_real_m"], 0.0)
        self.assertEqual(result["final_forward_delta_sim_minus_real_m"], 10.0)
        self.assertTrue(result["fully_warmed_four_frame_history"])
        self.assertEqual(result["real_selected_mode"], 1)
        self.assertEqual(result["sim_selected_mode"], 2)

    def test_repeat_metric_is_recomputed_and_report_is_bound_to_native(self):
        baseline = []
        repeated = []
        report = {"baseline": {"frames": []}, "baseline_repeat": {"frames": []}}
        for index in range(8):
            base = np.zeros((6, 2), dtype=np.float32)
            repeat = base.copy()
            if index == 7:
                repeat[-1, -1] = 5e-5
            baseline.append({"final_planning": base})
            repeated.append({"final_planning": repeat})
            report["baseline"]["frames"].append(
                {"native": {"final_planning_values": base.tolist()}}
            )
            report["baseline_repeat"]["frames"].append(
                {"native": {"final_planning_values": repeat.tolist()}}
            )
        native = {"baseline": baseline, "baseline_repeat": repeated}
        self.assertAlmostEqual(recompute_reset_repeat(native), 5e-5, places=10)
        self.assertEqual(report_native_plan_difference(report, native), 0.0)
        report["baseline_repeat"]["frames"][-1]["native"][
            "final_planning_values"
        ][-1][-1] = 0.0
        self.assertGreater(report_native_plan_difference(report, native), 0.0)


if __name__ == "__main__":
    unittest.main()
