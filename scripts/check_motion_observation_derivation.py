"""Check analytic identities, not HUGSIM or real-camera validity. Standard library only."""

import itertools
import math
import sys
import unittest


def growth(width0, width1, dt):
    return math.log(width1 / width0) / dt


class DerivationChecks(unittest.TestCase):
    def test_documented_delay_examples(self):
        for z, v, expected in (
            (20.0, 10.0, -1.0 / 21.0),
            (5.0, 10.0, -1.0 / 6.0),
            (40.0, 20.0, -1.0 / 21.0),
        ):
            baseline = v / z
            delayed = v / (z + v * 0.1)
            self.assertAlmostEqual((delayed - baseline) / baseline, expected)

    def test_dimensionless_relation(self):
        for z, v, delay, bias in itertools.product(
            (5.0, 20.0, 40.0), (2.0, 10.0, 20.0), (0.0, 0.1, 0.2),
            (-0.25, 0.0, 0.5),
        ):
            eta = (v * delay + bias) / z
            ratio = (v / (z + v * delay + bias)) / (v / z)
            self.assertAlmostEqual(ratio, 1.0 / (1.0 + eta))

    def test_pure_delay_tolerance_boundary(self):
        for z, v, eps in itertools.product(
            (5.0, 20.0), (3.0, 10.0), (0.01, 0.05, 0.2)
        ):
            limit = eps / (1.0 - eps) * z / v
            error = v * limit / (z + v * limit)
            self.assertAlmostEqual(error, eps)
            larger_delay = 1.01 * limit
            self.assertGreater(v * larger_delay / (z + v * larger_delay), eps)

    def test_constant_scale_preserves_growth_not_width(self):
        w0, w1, dt = 70.0, 84.0, 0.2
        for scale in (0.9, 1.1, 1.5):
            self.assertNotEqual(scale * w0, w0)
            self.assertAlmostEqual(
                growth(scale * w0, scale * w1, dt), growth(w0, w1, dt)
            )

    def test_time_varying_scale_finite_window(self):
        a, omega, t0, dt = 0.01, 3.0, 0.4, 0.1
        t1 = t0 + dt
        k0 = math.exp(a * math.sin(omega * t0))
        k1 = math.exp(a * math.sin(omega * t1))
        base0, base1 = 80.0, 85.0
        measured_difference = (
            growth(k0 * base0, k1 * base1, dt) - growth(base0, base1, dt)
        )
        predicted_difference = a * (math.sin(omega * t1) - math.sin(omega * t0)) / dt
        self.assertAlmostEqual(measured_difference, predicted_difference)

    def test_two_speed_identification(self):
        bias, delay, scale, focal_width = 0.4, 0.12, 1.08, 2000.0
        speeds = (3.0, 9.0)
        distances = (30.0, 20.0)
        offsets = []
        for v, z in zip(speeds, distances):
            width = scale * focal_width / (z + bias + v * delay)
            offsets.append(scale * focal_width / width - z)
        recovered_delay = (offsets[1] - offsets[0]) / (speeds[1] - speeds[0])
        recovered_bias = offsets[0] - speeds[0] * recovered_delay
        self.assertAlmostEqual(recovered_delay, delay)
        self.assertAlmostEqual(recovered_bias, bias)
        # A different parameter pair is indistinguishable at the first speed.
        alternate_delay = delay + 0.05
        alternate_bias = bias - speeds[0] * 0.05
        self.assertAlmostEqual(alternate_bias + speeds[0] * alternate_delay, offsets[0])
        self.assertNotAlmostEqual(alternate_bias + speeds[1] * alternate_delay, offsets[1])

    def test_finite_window_measurement_bound(self):
        e_max = 0.01
        for dt, e0, e1 in itertools.product(
            (0.05, 0.1, 0.25), (-e_max, 0.0, e_max), (-e_max, 0.0, e_max)
        ):
            w0, w1 = 60.0, 65.0
            measured = growth(w0 * math.exp(e0), w1 * math.exp(e1), dt)
            true = growth(w0, w1, dt)
            self.assertLessEqual(abs(measured - true), 2.0 * e_max / dt + 1e-12)

    def test_general_chain_rule_against_numerical_derivative(self):
        def depth(t):
            return 30.0 - 4.0 * t - 0.25 * t * t

        def width(t):
            delay = 0.12 + 0.02 * math.sin(0.4 * t)
            bias = 0.2 + 0.03 * math.cos(0.7 * t)
            scale = math.exp(0.01 * math.sin(1.1 * t))
            return scale * 2000.0 / (depth(t - delay) + bias)

        h = 1e-4
        for t in (0.0, 0.4, 1.0, 2.0, 3.0):
            delay = 0.12 + 0.02 * math.sin(0.4 * t)
            delay_rate = 0.008 * math.cos(0.4 * t)
            s = t - delay
            bias = 0.2 + 0.03 * math.cos(0.7 * t)
            bias_rate = -0.021 * math.sin(0.7 * t)
            log_scale_rate = 0.011 * math.cos(1.1 * t)
            predicted = log_scale_rate - (
                (-4.0 - 0.5 * s) * (1.0 - delay_rate) + bias_rate
            ) / (depth(s) + bias)
            numerical = (
                math.log(width(t + h)) - math.log(width(t - h))
            ) / (2.0 * h)
            self.assertAlmostEqual(predicted, numerical, delta=1e-8)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DerivationChecks)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    print("Analytic identity checks only; no simulator or real-world validation.")
    print("Z_m v_mps delay_s eta growth_baseline_per_s growth_delayed_per_s relative_error_percent")
    for z, v in ((20.0, 10.0), (5.0, 10.0), (40.0, 20.0)):
        delay = 0.1
        baseline = v / z
        delayed = v / (z + v * delay)
        print(
            f"{z:.1f} {v:.1f} {delay:.3f} {v * delay / z:.2f} "
            f"{baseline:.6f} {delayed:.6f} "
            f"{100.0 * (delayed / baseline - 1.0):.4f}"
        )
