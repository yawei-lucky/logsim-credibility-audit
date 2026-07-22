import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "cf_risk", ROOT / "scripts" / "analyze_hugsim_cf_risk_causality.py"
)
cf_risk = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(cf_risk)


def receiver_row(timestamp, x=None):
    prediction = [] if x is None else [{"instance_id": 4}]
    match = None if x is None else {
        "prediction_center_vehicle_xy": [x, 0.0],
        "prediction_rank": 0,
    }
    return {
        "timestamp_s": timestamp,
        "predictions": prediction,
        "actor_matches": [{"nearest_qualified": match}],
    }


class CFRiskCausalityTest(unittest.TestCase):
    def test_receiver_relation_preserves_unavailable(self):
        riskier = [receiver_row(0.5, 10.0), receiver_row(1.0, None)]
        safer = [receiver_row(0.5, 20.0), receiver_row(1.0, 20.0)]
        result = cf_risk.receiver_relation(riskier, safer, 1.0)
        self.assertEqual(result["expected_count"], 1)
        self.assertEqual(result["unavailable_count"], 1)
        self.assertEqual(cf_risk.evidence_label(True, result), "down-weighted")

    def test_receiver_relation_rejects_aggregate_reversal(self):
        riskier = [receiver_row(0.5, 30.0)]
        safer = [receiver_row(0.5, 20.0)]
        result = cf_risk.receiver_relation(riskier, safer, 1.0)
        self.assertFalse(result["aggregate_direction_expected"])
        self.assertEqual(cf_risk.evidence_label(True, result), "rejected")

    def test_receiver_motion_reports_closing_slope(self):
        rows = [
            receiver_row(0.5, 10.0),
            receiver_row(1.0, 9.0),
            receiver_row(1.5, 8.0),
        ]
        result = cf_risk.receiver_motion(rows, 1.5)
        self.assertLess(result["slope_mps"], 0.0)
        self.assertEqual(result["closing_step_count"], 2)
        self.assertEqual(result["dominant_instance_fraction"], 1.0)

    def test_expected_receiver_timestamps_fail_closed(self):
        self.assertEqual(
            cf_risk.expected_receiver_timestamps(1.5, 2.0),
            [0.5, 1.0, 1.5],
        )


if __name__ == "__main__":
    unittest.main()
