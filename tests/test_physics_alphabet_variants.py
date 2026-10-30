import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_physics_alphabet_variants import cases, geometries, geometry_config, preflight, statistics, validate_frozen_rules


class VariantContractTest(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((ROOT / "configs/physics_alphabet_variants_001.json").read_text())

    def test_one_axis_controls_and_all_joint_variants_are_distinct(self):
        controls = geometries(self.cfg)
        self.assertEqual(len(controls), 14)
        for row in controls:
            changed = sum([row["angle"] != 30, row["base_depth_m"] != 24, row["layout"] != "reference"])
            self.assertEqual(changed, 3 if row["family"] == "joint" else 1)
        self.assertEqual(len({row["id"] for row in cases(self.cfg)}), 56)
        self.assertEqual(preflight(self.cfg, cases(self.cfg))["pair_count"], 112)

    def test_camera_and_measurement_gates_cannot_be_relaxed(self):
        for field in ("position_error_bound_px", "identity_min_channel_fraction"):
            changed = copy.deepcopy(self.cfg)
            changed["suite"]["measurement"][field] *= 2
            with self.assertRaisesRegex(ValueError, "frozen camera"):
                validate_frozen_rules(changed)

    def test_layout_and_depth_are_parameters_and_do_not_mutate_reference(self):
        original = copy.deepcopy(self.cfg)
        row = next(row for row in cases(self.cfg) if row["family"] == "joint")
        local = geometry_config(self.cfg, row)
        self.assertNotEqual(local["body_points_m"], self.cfg["body_points_m"])
        self.assertNotEqual(local["base_center_camera_m"][2], self.cfg["base_center_camera_m"][2])
        self.assertEqual(self.cfg, original)

    def test_unqualified_readouts_never_count_as_mechanism_contradictions(self):
        row = {"case": {"family": "angle"}, "judgements": {name: {"tested": False, "contract_passed": False} for name in
               ("R_T_P_V", "T_R_P_V", "without_R", "without_T", "fixed_depth_P", "without_V")}}
        result = statistics([row])["R_T_P_V"]["all"]
        self.assertEqual(result, {"count": 1, "tested": 0, "passed": 0, "max_position_error_px": None})


if __name__ == "__main__":
    unittest.main()
