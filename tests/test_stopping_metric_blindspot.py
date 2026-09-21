import itertools
import math
from pathlib import Path
import tempfile
import unittest

from scripts.run_stopping_metric_blindspot import (
    ROOT, boundary_interval, confirmation_index, interval_verdict,
    longest_missing, mask_from_indices, outcome, run,
    simulate_reference, stopping_boundary,
)
from scripts.run_stopping_scope_challenge import integrate_ramp, ramp_reference


class StoppingMetricBlindspotTests(unittest.TestCase):
    def test_hand_computable_cases(self):
        for indices, boundary, confirmation in (
            ([], 12.0, 0.1), ([0, 3, 6, 9], 13.0, 0.2),
            ([0, 1, 2, 3], 16.0, 0.5), ([0, 2, 4, 6], 19.0, 0.8),
            ([8, 9, 10, 11], 12.0, 0.1),
        ):
            with self.subTest(indices=indices):
                mask = mask_from_indices(12, indices)
                result = simulate_reference(mask, 10, 5, 0.1, record=True)
                self.assertAlmostEqual(result["free_stop_distance_m"], boundary, places=9)
                self.assertAlmostEqual(result["command_time_s"], confirmation, places=9)
                self.assertEqual(result["states"][-1]["v_mps"], 0)
                self.assertTrue(all(s["v_mps"] >= 0 for s in result["states"]))

    def test_same_marginal_and_longest_gap_different_boundary(self):
        masks = [mask_from_indices(12, x) for x in ([0, 3, 6, 9], [0, 2, 4, 6])]
        self.assertEqual([sum(m) for m in masks], [4, 4])
        self.assertEqual([longest_missing(m) for m in masks], [1, 1])
        results = [simulate_reference(m, 10, 5, 0.1) for m in masks]
        self.assertEqual([outcome(15.5, r["free_stop_distance_m"]) for r in results],
                         ["clear", "crossing"])

    def test_post_latch_missing_does_not_change_behavior(self):
        cases = [mask_from_indices(12, x) for x in ([], [8, 9, 10, 11], [3, 5, 7, 9])]
        boundaries = [simulate_reference(m, 10, 5, 0.1)["free_stop_distance_m"] for m in cases]
        for value in boundaries:
            self.assertAlmostEqual(value, 12)

    def test_no_tail_fill(self):
        mask = (True, False, True, False)
        with self.assertRaises(ValueError):
            confirmation_index(mask)
        with self.assertRaises(ValueError):
            simulate_reference(mask, 10, 5, 0.1)

    def test_irregular_integrator_step_splits_observation_and_actuation(self):
        mask = mask_from_indices(12, [0, 2, 4, 6])
        for h in (0.005, 0.01, 0.02, 0.037):
            result = simulate_reference(mask, 9, 6, 0.153, integration_dt=h)
            expected = stopping_boundary(9, 6, 0.8, 0.153)
            self.assertAlmostEqual(result["free_stop_distance_m"], expected, places=8)

    def test_actuation_uncertainty_must_be_included(self):
        interval = boundary_interval(10, 5, 0.2, 0, (0.1, 0.3))
        self.assertAlmostEqual(interval[0], 13)
        self.assertAlmostEqual(interval[1], 15)
        self.assertEqual(interval_verdict(14, interval), "unresolved")
        self.assertEqual(outcome(14, 13), "clear")
        self.assertEqual(outcome(14, 15), "crossing")

    def test_boundary_is_not_clear(self):
        self.assertEqual(outcome(13, 13), "boundary")
        self.assertEqual(interval_verdict(13, (13, 13)), "unresolved")

    def test_uncertainty_bound_contains_truth(self):
        for v, b, c, error in itertools.product((6, 15), (3, 6), (0.1, 0.8), (-0.025, 0, 0.025)):
            lo, hi = boundary_interval(v, b, c + error, 0.025, (0.1, 0.1))
            truth = stopping_boundary(v, b, c, 0.1)
            self.assertLessEqual(lo - 1e-10, truth)
            self.assertGreaterEqual(hi + 1e-10, truth)

    def test_speed_scaling_of_boundary_difference(self):
        for v in (6, 10, 15):
            a = stopping_boundary(v, 5, 0.2, 0.1)
            b = stopping_boundary(v, 5, 0.8, 0.1)
            self.assertAlmostEqual(b - a, v * 0.6)

    def test_negative_or_nonfinite_parameters_rejected(self):
        for v, b, delay in ((-1, 5, 0), (1, 0, 0), (1, 5, -1), (math.nan, 5, 0)):
            with self.assertRaises(ValueError):
                stopping_boundary(v, b, 0.1, delay)

    def test_invalid_missing_indices_rejected(self):
        for indices in ([0, 0], [-1], [12]):
            with self.assertRaises(ValueError):
                mask_from_indices(12, indices)

    def test_refuse_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileExistsError):
                run(ROOT / "configs/stopping_metric_blindspot_001.json", Path(temp), video=False)

    def test_heldout_zero_ramp_recovers_frozen_contract(self):
        self.assertAlmostEqual(ramp_reference(10, 5, 0.3, 0), 13)
        self.assertAlmostEqual(integrate_ramp(10, 5, 0.3, 0, 0.001), 13, places=8)

    def test_heldout_buildup_changes_boundary_not_observation(self):
        reference = ramp_reference(10, 5, 0.3, 0.6)
        self.assertAlmostEqual(reference, 15.925)
        self.assertAlmostEqual(integrate_ramp(10, 5, 0.3, 0.6, 0.001), reference, places=5)
        self.assertEqual(outcome(14, reference), "crossing")
        self.assertEqual(outcome(14, stopping_boundary(10, 5, 0.2, 0.1)), "clear")

    def test_ramp_reference_does_not_extrapolate_past_contract(self):
        with self.assertRaises(ValueError):
            ramp_reference(1, 5, 0.3, 0.6)


if __name__ == "__main__":
    unittest.main()
