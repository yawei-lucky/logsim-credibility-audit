import copy
import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_sparsedrive_same_window_counterfactual import (  # noqa: E402
    repeat_forward_envelope,
    validate_reports,
)


def frame(frame_index, forward):
    plan = np.zeros((6, 2), dtype=float)
    plan[:, 1] = forward
    return {
        "source_frame_index": frame_index,
        "timestamp_s": frame_index / 12,
        "input_contract": {
            "ego_status_10d": [0.0] * 10,
            "command_one_hot_right_left_straight": [0.0, 0.0, 1.0],
            "front_model_to_camera": np.eye(4).tolist(),
            "camera_inputs": [
                {"camera": "CAM_FRONT", "image_path": "/tmp/front.png"}
            ],
        },
        "recorded_camera_rig_future_xy_m": np.zeros((6, 2)).tolist(),
        "native": {
            "final_planning_values": plan.tolist(),
        },
        "planning_selection": {"selected_mode_index": 2},
    }


def report(offset):
    frames = [
        frame(12 + 6 * index, float(index) + offset)
        for index in range(5)
    ]
    repeated = copy.deepcopy(frames)
    repeated[-1]["native"]["final_planning_values"][-1][1] += 1e-5
    return {
        "model": {
            "checkpoint_sha256": "checkpoint",
            "config_sha256": "config",
        },
        "adapter": {"sha256": "adapter"},
        "baseline": {"frames": frames},
        "baseline_repeat": {"frames": repeated},
    }


class SparseDriveSameWindowCounterfactualTest(unittest.TestCase):
    def test_validates_held_fixed_contract_and_signed_effects(self):
        reports = {
            "real": report(0.0),
            "factual": report(0.5),
            "weak": report(0.2),
            "strong": report(-0.3),
        }
        rows = validate_reports(reports)
        warmed = [row for row in rows if row["fully_warmed_four_frame_history"]]
        self.assertEqual(len(warmed), 2)
        self.assertAlmostEqual(
            warmed[0]["D_domain_forward_sim_minus_real_m"],
            0.5,
        )
        self.assertAlmostEqual(
            warmed[0]["strong_minus_weak_final_forward_m"],
            -0.5,
        )

    def test_repeat_envelope_uses_only_fully_warmed_final_forward(self):
        reports = {
            label: report(offset)
            for label, offset in (
                ("real", 0.0),
                ("factual", 0.5),
                ("weak", 0.2),
                ("strong", -0.3),
            )
        }
        result = repeat_forward_envelope(reports)
        self.assertAlmostEqual(result["maximum_m"], 1e-5)

    def test_rejects_changed_receiver_state(self):
        reports = {
            "real": report(0.0),
            "factual": report(0.5),
            "weak": report(0.2),
            "strong": report(-0.3),
        }
        reports["strong"]["baseline"]["frames"][0]["input_contract"][
            "ego_status_10d"
        ][0] = 1.0
        with self.assertRaises(ValueError):
            validate_reports(reports)


if __name__ == "__main__":
    unittest.main()
