import copy
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_hugsim_multicar import (  # noqa: E402
    normalized_source_assets,
    validate_run_pairing,
)


class MulticarAnalysisTest(unittest.TestCase):
    def test_legacy_yaw_field_is_normalized_to_radians(self):
        source = {
            "vehicle_assets": [
                {"initial_state": {"yaw_deg": 0.45}},
                {"initial_state": {"yaw_rad": 0.0}},
            ]
        }
        original = copy.deepcopy(source)

        normalized = normalized_source_assets(source)

        self.assertEqual(source, original)
        self.assertEqual(
            normalized["vehicle_assets"][0]["initial_state"],
            {"yaw_rad": 0.45},
        )
        self.assertEqual(
            normalized["vehicle_assets"][1]["initial_state"],
            {"yaw_rad": 0.0},
        )

    def test_pairing_validation_rejects_different_plans(self):
        audit = {
            "hugsim_commit": "abc",
            "control_convention": "corrected",
            "requested_steps": 1,
            "completed_steps": 1,
            "eval_error": None,
            "source_assets": {"scene_cfg_sha256": "scene"},
        }
        infos = [{"timestamp": 0.0}, {"timestamp": 0.25}]
        reference_steps = [{"plan_traj": [[0.0, 1.0]]}]
        candidate_steps = [{"plan_traj": [[0.5, 1.0]]}]

        with self.assertRaisesRegex(ValueError, "planned trajectories differ"):
            validate_run_pairing(
                audit,
                copy.deepcopy(audit),
                infos,
                copy.deepcopy(infos),
                reference_steps,
                candidate_steps,
            )

    def test_pairing_validation_records_exact_match(self):
        audit = {
            "hugsim_commit": "abc",
            "control_convention": "corrected",
            "requested_steps": 1,
            "completed_steps": 1,
            "eval_error": None,
            "source_assets": {"scene_cfg_sha256": "scene"},
        }
        infos = [{"timestamp": 0.0}, {"timestamp": 0.25}]
        steps = [{"plan_traj": [[0.0, 1.0]]}]

        result = validate_run_pairing(
            audit,
            copy.deepcopy(audit),
            infos,
            copy.deepcopy(infos),
            steps,
            copy.deepcopy(steps),
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["maximum_plan_absolute_difference"], 0.0)


if __name__ == "__main__":
    unittest.main()
