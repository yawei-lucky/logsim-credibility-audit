import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_sparsedrive_exact_render_sequence import (  # noqa: E402
    load_render_reports,
    parse_condition_specs,
)


class SparseDriveExactRenderSequenceTest(unittest.TestCase):
    def test_condition_specs_are_unique(self):
        parsed = parse_condition_specs(["factual=/tmp/a", "overlap=/tmp/b"])
        self.assertEqual(set(parsed), {"factual", "overlap"})
        with self.assertRaises(ValueError):
            parse_condition_specs(["same=/tmp/a", "same=/tmp/b"])

    def test_render_reports_must_exactly_match_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            first.write_text(json.dumps({"frame_index": 30}), encoding="utf-8")
            second.write_text(json.dumps({"frame_index": 36}), encoding="utf-8")
            reports = load_render_reports([first, second], [30, 36])
            self.assertEqual(set(reports), {30, 36})
            with self.assertRaises(ValueError):
                load_render_reports([first], [30, 36])


if __name__ == "__main__":
    unittest.main()
