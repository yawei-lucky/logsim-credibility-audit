import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_hugsim_motion_metamorphic import (  # noqa: E402
    add_travel_distance,
    actor_state_rows,
    motion_metrics,
    strict_order_result,
)


TOLERANCES = {
    "integration_residual_m": 1e-5,
    "speed_error_mps": 1e-5,
    "heading_change_rad": 1e-5,
    "acceleration_residual_mps2": 1e-4,
}


def info(timestamp, actor_x):
    return {
        "timestamp": timestamp,
        "ego_box": [0.0, 0.0, 0.0, 1.6, 3.0, 1.5, 0.0],
        "obj_boxes": [[actor_x, 0.0, 0.0, 1.6, 3.6, 1.2, 0.0]],
    }


def states(speed):
    infos = [
        info(0.0, 10.0),
        info(0.25, 10.0 + speed * 0.25),
        info(0.5, 10.0 + speed * 0.5),
    ]
    return add_travel_distance(actor_state_rows(infos))


class MotionMetamorphicAnalysisTest(unittest.TestCase):
    def test_constant_speed_series_passes_hard_constraints(self):
        result = motion_metrics(states(1.0), 1.0, TOLERANCES)
        self.assertTrue(result["passed"])
        self.assertEqual(result["maxima"]["integration_residual_m"], 0.0)

    def test_synthetic_teleport_fails_hard_constraints(self):
        rows = add_travel_distance(
            actor_state_rows([info(0.0, 10.0), info(0.25, 10.25), info(0.5, 11.5)])
        )
        result = motion_metrics(rows, 1.0, TOLERANCES)
        self.assertFalse(result["passed"])
        self.assertGreaterEqual(result["maxima"]["integration_residual_m"], 1.0)

    def test_synthetic_reverse_motion_fails_vector_integration(self):
        rows = add_travel_distance(
            actor_state_rows([info(0.0, 10.0), info(0.25, 9.75), info(0.5, 9.5)])
        )
        result = motion_metrics(rows, 1.0, TOLERANCES)
        self.assertFalse(result["passed"])
        self.assertGreater(result["maxima"]["integration_residual_m"], 0.4)

    def test_speed_order_passes(self):
        result = strict_order_result(
            {"slow": states(0.5), "nominal": states(1.0), "fast": states(1.5)},
            "travel_from_first_observation_m",
            skip_initial=True,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["reversal_or_tie_count"], 0)

    def test_synthetic_order_reversal_fails(self):
        result = strict_order_result(
            {"slow": states(1.5), "nominal": states(1.0), "fast": states(0.5)},
            "travel_from_first_observation_m",
            skip_initial=True,
        )
        self.assertFalse(result["passed"])
        self.assertGreater(result["reversal_or_tie_count"], 0)


if __name__ == "__main__":
    unittest.main()
