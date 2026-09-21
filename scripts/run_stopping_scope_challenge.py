#!/usr/bin/env python3
"""Frozen V2 instrument challenged by a held-out brake buildup mechanism."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_stopping_metric_blindspot import (
    ROOT, boundary_interval, dump_json, interval_verdict, outcome, sha256,
    stopping_boundary,
)


def ramp_reference(v: float, b: float, start: float, ramp: float) -> float:
    if ramp < 0 or v <= b * ramp / 2:
        raise ValueError("Reference requires stopping strictly after brake buildup")
    return v * start + v * v / (2 * b) + v * ramp / 2 - b * ramp * ramp / 24


def integrate_ramp(v: float, b: float, start: float, ramp: float, dt: float) -> float:
    """Integrate the prescribed acceleration, independently of either distance formula.

    Split at phase boundaries; midpoint acceleration is exact for velocity in the
    linear buildup. Trapezoidal position has O(dt^2) global error there.
    """
    t, x = 0.0, 0.0
    while v > 1e-12:
        h = dt
        if t < start - 1e-10:
            h = min(h, start - t)
            a = 0.0
        elif ramp > 0 and t < start + ramp - 1e-10:
            h = min(h, start + ramp - t)
            a = -b * (t + h / 2 - start) / ramp
        else:
            h = min(h, v / b)
            a = -b
        next_v = v + a * h
        if next_v < -1e-10:
            raise ValueError("Unexpected stop during buildup; outside frozen reference")
        x += (v + max(0.0, next_v)) * h / 2
        v = max(0.0, next_v)
        t += h
    return x


def run(out: Path) -> dict:
    if out.exists():
        raise FileExistsError(f"Refusing existing output: {out}")
    out.mkdir(parents=True)
    prereg = ROOT / "docs/runs/stopping_metric_scope_challenge_001.md"
    instrument = ROOT / "scripts/run_stopping_metric_blindspot.py"
    frozen_sha = "a56915b456984a6c6c6ae1c74704dceaa76e55336edd933d1a90704175e41df4"
    if sha256(instrument) != frozen_sha:
        raise ValueError("V2 source differs from the frozen run002 instrument")
    config = {"v_mps": 10.0, "b_mps2": 5.0, "confirmation_s": 0.2,
              "delay_s": 0.1, "gap_m": 14.0, "ramps_s": [0.0, 0.6],
              "integration_steps_s": [0.002, 0.001, 0.0005], "tolerance_m": 1e-4}
    dump_json(out / "manifest.json", {
        "started_utc": datetime.now(timezone.utc).isoformat(), "role": "synthetic mechanism challenge",
        "command": sys.argv, "cwd": str(Path.cwd()), "config": config,
        "instrument_sha256": frozen_sha, "preregistration_sha256": sha256(prereg),
        "source_sha256": sha256(Path(__file__)),
    })
    v, b, c, delay, gap = 10.0, 5.0, 0.2, 0.1, 14.0
    point = stopping_boundary(v, b, c, delay)
    interval = boundary_interval(v, b, c, 0, (0.1, 0.3))
    rows = []
    for ramp in config["ramps_s"]:
        reference = ramp_reference(v, b, c + delay, ramp)
        checks = [{"dt_s": dt, "numeric_boundary_m": integrate_ramp(v, b, c + delay, ramp, dt)}
                  for dt in config["integration_steps_s"]]
        error = max(abs(x["numeric_boundary_m"] - reference) for x in checks)
        rows.append({"ramp_s": ramp, "reference_boundary_m": reference,
                     "frozen_v2_boundary_m": point, "frozen_v2_outcome": outcome(gap, point),
                     "reference_outcome": outcome(gap, reference),
                     "old_delay_interval_m": interval,
                     "old_interval_verdict": interval_verdict(gap, interval),
                     "old_interval_contains_reference": interval[0] <= reference <= interval[1],
                     "integration_checks": checks, "max_numeric_error_m": error})
    result = {"scope": "held-out synthetic mechanism, not HUGSIM or real-world evidence",
              "instrument_modified": False, "cases": rows,
              "numerical_verification_passed": all(r["max_numeric_error_m"] <= config["tolerance_m"] for r in rows)}
    dump_json(out / "summary.json", result)
    if not result["numerical_verification_passed"]:
        raise RuntimeError("Reference crosscheck failed; preserve output and do not accept")
    dump_json(out / "run_status.json", {"health": "complete", "completed_utc": datetime.now(timezone.utc).isoformat()})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    run(parser.parse_args().output_dir)
