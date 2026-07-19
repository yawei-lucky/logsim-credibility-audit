import copy
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_hugsim_multicar import normalized_source_assets  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
