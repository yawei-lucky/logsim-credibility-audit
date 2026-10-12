import copy
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_credibility_screening import evaluate_submission, projection_width
from run_motion_observation_probe import synthetic_pair


class CredibilityScreeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.suite = {"schema_version": 1, "suite_id": "test", "camera": {"width": 160, "height": 100,
                      "intrinsics": [[100, 0, 80], [0, 100, 50], [0, 0, 1]]},
                      "measurement": {"difference_threshold_u8": 8, "min_component_area_px": 3, "width_error_bound_px": 0.5},
                      "cases": [{"id": "projection", "question": "full endpoint projection", "frames": [
                          {"id": "frame", "capture_time_s": 0, "marker_camera_xyz_m": [[-1, 0, 4], [1, 0, 8]], "expected_visible_markers": 2}]}]}
        self.submission = {"schema_version": 1, "suite_id": "test", "simulator": {"name": "independent 2D qualification", "version": "1"},
                           "cases": [{"id": "projection", "frames": [{"id": "frame", "capture_time_s": 0, "bright": "bright.png", "dim": "dim.png"}]}]}
        _, centres = projection_width(self.suite["cases"][0]["frames"][0]["marker_camera_xyz_m"], self.suite["camera"]["intrinsics"])
        self.write_pair(centres)

    def tearDown(self):
        self.temp.cleanup()

    def write_pair(self, centres, shape=(100, 160, 3)):
        pair = synthetic_pair(np.full(shape, 80, dtype=np.uint8), centres, 1.2, 0.9, [0.9, 0.1])
        for filename, image in zip(("bright.png", "dim.png"), pair):
            self.assertTrue(cv2.imwrite(str(self.root / filename), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)))

    def evaluate(self):
        return evaluate_submission(self.suite, self.submission, self.root)

    def test_full_projection_passes_but_wrong_common_depth_rgb_fails(self):
        result = self.evaluate()
        self.assertTrue(result["screening_contract_satisfied"])
        self.assertEqual(result["overall_evidence_label"], "down-weighted")
        self.assertAlmostEqual(result["cases"][0]["frames"][0]["expected_width_px"], 37.5)
        self.write_pair([(80 - 100 / 6, 50), (80 + 100 / 6, 50)])
        result = self.evaluate()
        self.assertFalse(result["screening_contract_satisfied"])
        self.assertEqual(result["cases"][0]["frames"][0]["failure_kind"], "contradiction")

    def test_single_marker_requires_exactly_one_not_zero_or_two(self):
        self.suite["cases"][0]["frames"][0]["expected_visible_markers"] = 1
        self.assertFalse(self.evaluate()["screening_contract_satisfied"])
        self.write_pair([(55, 50)])
        frame = self.evaluate()["cases"][0]["frames"][0]
        self.assertEqual(frame["evidence_label"], "accepted")
        self.assertIsNone(frame["measured_width_px"])
        self.write_pair([])
        self.assertFalse(self.evaluate()["screening_contract_satisfied"])

    def test_wrong_time_nonfinite_time_and_wrong_image_shape_are_unmeasured(self):
        submitted_frame = self.submission["cases"][0]["frames"][0]
        for bad_time in (0.25, float("nan"), "0", True):
            submitted_frame["capture_time_s"] = bad_time
            frame = self.evaluate()["cases"][0]["frames"][0]
            self.assertEqual(frame["failure_kind"], "input_invalid")
            self.assertFalse(frame["tested"])
        submitted_frame["capture_time_s"] = 0
        self.write_pair([(55, 50), (92.5, 50)], (110, 160, 3))
        frame = self.evaluate()["cases"][0]["frames"][0]
        self.assertFalse(frame["tested"])
        self.assertIn("declared height", frame["reason"])

    def test_duplicate_missing_extra_case_or_frame_cannot_pass(self):
        original = copy.deepcopy(self.submission)
        self.submission["cases"].append(copy.deepcopy(self.submission["cases"][0]))
        result = self.evaluate()
        self.assertIn("duplicate", result["input_errors"][0])
        self.assertEqual(result["not_tested_case_ids"], ["projection"])
        self.submission = copy.deepcopy(original)
        self.submission["cases"][0]["id"] = "other"
        result = self.evaluate()
        self.assertFalse(result["screening_contract_satisfied"])
        self.assertEqual(result["not_tested_case_ids"], ["projection"])
        self.submission = copy.deepcopy(original)
        self.submission["cases"][0]["frames"].append(copy.deepcopy(self.submission["cases"][0]["frames"][0]))
        result = self.evaluate()
        self.assertFalse(result["screening_contract_satisfied"])
        self.assertEqual(result["cases"][0]["not_tested_frame_ids"], ["frame"])
        self.submission = copy.deepcopy(original)
        self.submission["cases"][0]["frames"][0]["id"] = "other"
        self.assertFalse(self.evaluate()["screening_contract_satisfied"])

    def test_missing_file_and_invalid_reference_cannot_pass(self):
        (self.root / "bright.png").unlink()
        self.assertFalse(self.evaluate()["cases"][0]["frames"][0]["tested"])
        for point in ([0, 0, -1], [0, 0, float("inf")]):
            self.suite["cases"][0]["frames"][0]["marker_camera_xyz_m"][0] = point
            result = self.evaluate()
            self.assertEqual(result["overall_evidence_label"], "rejected")
            self.assertTrue(result["input_errors"])

    def test_common_translation_is_explicit_width_blindspot(self):
        self.write_pair([(57, 53), (94.5, 53)])
        result = self.evaluate()
        self.assertTrue(result["screening_contract_satisfied"])
        self.assertTrue(any("common translation" in limitation for limitation in result["limitations"]))

    def test_position_gate_passes_correct_rgb_and_rejects_width_preserving_translations(self):
        self.suite["measurement"]["position_error_bound_px"] = 0.25
        frame = self.evaluate()["cases"][0]["frames"][0]
        self.assertEqual(frame["evidence_label"], "accepted")
        self.assertLessEqual(frame["max_abs_position_residual_px"], 0.25)
        # These centres are known image coordinates, not simulator outputs.
        for dx, dy in ((2, 0), (0, 3)):
            self.write_pair([(55 + dx, 50 + dy), (92.5 + dx, 50 + dy)])
            result = self.evaluate()
            frame = result["cases"][0]["frames"][0]
            self.assertFalse(result["screening_contract_satisfied"])
            self.assertTrue(frame["tested"])
            self.assertEqual(frame["failure_kind"], "contradiction")
            self.assertTrue(frame["width_within_budget"])
            self.assertFalse(frame["position_within_budget"])
            self.assertIn("position residual", frame["reason"])

    def test_position_budget_invalid_or_single_marker_contract_is_unmeasured(self):
        for budget in (None, 0, -1, True, float("nan"), float("inf"), "0.25"):
            self.suite["measurement"]["position_error_bound_px"] = budget
            result = self.evaluate()
            self.assertFalse(result["screening_contract_satisfied"])
            self.assertTrue(result["input_errors"])
            self.assertEqual(result["tested_frame_count"] if "tested_frame_count" in result else 0, 0)
        self.suite["measurement"]["position_error_bound_px"] = 0.25
        self.suite["cases"][0]["frames"][0]["expected_visible_markers"] = 1
        self.assertIn("two visible markers", self.evaluate()["input_errors"][0])

    def test_general_projection_matrix_is_not_silently_treated_as_camera_intrinsics(self):
        self.suite["camera"]["intrinsics"] = [[100, 0, 80, 40], [0, 100, 50, 0], [0, 0, 1, 0]]
        result = self.evaluate()
        self.assertFalse(result["contract_passed"])
        self.assertIn("3x3 camera matrix", result["input_errors"][0])


if __name__ == "__main__":
    unittest.main()
