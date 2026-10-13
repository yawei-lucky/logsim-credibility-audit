import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_landmark_interval_screening import evaluate_submission


class LandmarkIntervalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        image_path = self.root / "raw.png"
        Image.new("RGB", (800, 450), (90, 90, 90)).save(image_path)
        self.image = {"rgb_path": "raw.png", "rgb_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest()}
        self.reference = {"reference_id": "bounded_test", "band_y_px": [200, 240],
                          "coordinate_convention": "outer-contour midpoint in rows [200,240)",
                          "frames": [{"frame_index": frame, "timestamp_s": time, "target": "same grey metal shaft midpoint",
                                      "visibility": "visible", "u_interval_px": [lo, lo + 10], **self.image}
                                     for frame, time, lo in ((108, 9.0, 104), (114, 9.5, 199), (120, 10.0, 304))]}
        self.submission = {"reference_id": "bounded_test", "frames": copy.deepcopy(self.reference["frames"])}
        for row in self.submission["frames"]:
            row["annotation_basis"] = "Codex visual candidate; test annotations, no RGB recognition"

    def tearDown(self):
        self.temp.cleanup()

    def evaluate(self):
        return evaluate_submission(self.reference, self.submission, self.root, self.root)

    def test_touching_is_nonconflict_tiny_disjoint_gap_is_not_hidden_by_tolerance(self):
        self.submission["frames"][0]["u_interval_px"] = [114, 118]
        result = self.evaluate()["frames"][0]
        self.assertEqual(result["comparison"], "no_conflict")
        self.assertEqual(result["evidence_label"], "down-weighted")
        self.assertTrue(result["tested"])
        self.assertEqual(result["minimum_gap_px"], 0)
        self.submission["frames"][0]["u_interval_px"] = [114.000001, 118]
        result = self.evaluate()["frames"][0]
        self.assertEqual(result["failure_kind"], "annotation_interval_conflict")
        self.assertEqual(result["evidence_label"], "rejected")
        self.assertTrue(result["tested"])
        self.assertAlmostEqual(result["minimum_gap_px"], 0.000001)

    def test_disjoint_left_side_reports_annotation_gap_not_simulator_defect(self):
        self.submission["frames"][0]["u_interval_px"] = [60, 80]
        result = self.evaluate()
        self.assertEqual(result["frames"][0]["minimum_gap_px"], 24)
        self.assertEqual(result["overall_evidence_label"], "down-weighted")
        self.assertIn("A conflict does not isolate a physical HUGSIM defect.", result["limitations"])

    def test_unknown_and_absent_are_unmeasured_not_visibility_contradictions(self):
        for visibility in ("unknown", "absent"):
            row = self.submission["frames"][0]
            row.update({"visibility": visibility, "u_interval_px": None})
            result = self.evaluate()["frames"][0]
            self.assertEqual(result["evidence_label"], "down-weighted")
            self.assertFalse(result["tested"])
            self.assertEqual(result["failure_kind"], "measurement_unqualified")
            self.assertIsNone(result["minimum_gap_px"])
        self.submission["frames"][0]["u_interval_px"] = [100, 110]
        self.assertEqual(self.evaluate()["frames"][0]["failure_kind"], "input_invalid")

    def test_wrong_time_bad_hash_missing_or_wrong_size_rgb_are_input_failures(self):
        original = copy.deepcopy(self.submission)
        changes = ({"timestamp_s": 9.000000001}, {"timestamp_s": float("nan")},
                   {"rgb_sha256": "0" * 64}, {"rgb_path": "missing.png"})
        for change in changes:
            self.submission = copy.deepcopy(original)
            self.submission["frames"][0].update(change)
            result = self.evaluate()["frames"][0]
            self.assertFalse(result["tested"])
            self.assertEqual(result["failure_kind"], "input_invalid")
        small = self.root / "small.png"
        Image.new("RGB", (799, 450)).save(small)
        self.submission = copy.deepcopy(original)
        self.submission["frames"][0].update({"rgb_path": "small.png", "rgb_sha256": hashlib.sha256(small.read_bytes()).hexdigest()})
        self.assertEqual(self.evaluate()["frames"][0]["failure_kind"], "input_invalid")

    def test_duplicate_missing_extra_or_wrong_reference_ids_cannot_be_tested(self):
        original = copy.deepcopy(self.submission)
        variants = []
        duplicate = copy.deepcopy(original)
        duplicate["frames"].append(copy.deepcopy(duplicate["frames"][0]))
        variants.append(duplicate)
        missing = copy.deepcopy(original)
        missing["frames"].pop()
        variants.append(missing)
        extra = copy.deepcopy(original)
        extra["frames"][0]["frame_index"] = 126
        variants.append(extra)
        wrong_reference = copy.deepcopy(original)
        wrong_reference["reference_id"] = "other"
        variants.append(wrong_reference)
        for variant in variants:
            self.submission = variant
            result = self.evaluate()
            self.assertTrue(result["input_errors"])
            self.assertEqual(len(result["frames"]), 3)
            self.assertTrue(all(not row["tested"] for row in result["frames"]))

    def test_invalid_interval_or_different_observable_target_is_not_a_position_conflict(self):
        original = copy.deepcopy(self.submission)
        for interval in (None, [115, 105], [104, float("inf")], [True, 110], [-1, 10], [790, 800]):
            self.submission = copy.deepcopy(original)
            self.submission["frames"][0]["u_interval_px"] = interval
            result = self.evaluate()
            self.assertEqual(result["frames"][0]["failure_kind"], "input_invalid")
            json.dumps(result, allow_nan=False)
        self.submission = copy.deepcopy(original)
        self.submission["frames"][0]["target"] = "neighboring tree or darkest ridge"
        self.assertEqual(self.evaluate()["frames"][0]["failure_kind"], "input_invalid")
        self.submission = copy.deepcopy(original)
        self.submission["coordinate_convention"] = "darkest ridge"
        self.assertTrue(self.evaluate()["input_errors"])

    def test_reference_rgb_integrity_is_checked_before_annotation_comparison(self):
        self.reference["frames"][0]["rgb_sha256"] = "0" * 64
        result = self.evaluate()
        self.assertTrue(result["input_errors"])
        self.assertTrue(all(row["failure_kind"] == "input_invalid" and not row["tested"] for row in result["frames"]))


if __name__ == "__main__":
    unittest.main()
