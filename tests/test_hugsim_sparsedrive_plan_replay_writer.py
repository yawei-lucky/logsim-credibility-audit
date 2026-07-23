from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hugsim_sparsedrive_plan_replay_writer import load_plans  # noqa: E402


class SparseDrivePlanReplayWriterTest(unittest.TestCase):
    def test_selects_exact_native_plan_without_repetition(self) -> None:
        plans = [
            {"final_planning": torch.full((6, 2), float(index))}
            for index in range(3)
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native.pt"
            torch.save(plans, path)

            selected = load_plans(path, start_index=1, max_plans=1)

        self.assertEqual(len(selected), 1)
        np.testing.assert_allclose(selected[0], 1.0)

    def test_rejects_request_past_available_plans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native.pt"
            torch.save([{"final_planning": torch.zeros((6, 2))}], path)

            with self.assertRaisesRegex(ValueError, "source contains only"):
                load_plans(path, start_index=1, max_plans=1)


if __name__ == "__main__":
    unittest.main()
