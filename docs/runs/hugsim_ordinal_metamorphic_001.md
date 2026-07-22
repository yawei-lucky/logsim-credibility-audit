# HUGSIM Ordinal Metamorphic Audit 001

Date: 2026-07-22

Preregistration commit:
`c784cbcdd6c3ff4554a26e79d683bcf8703b42b1`

## Purpose

Test one task-relevant construct without using HUGSIM's own score as truth:
when the same injected vehicle moves closer or toward the deterministic ego
plan corridor, do independently recomputed geometry and a frozen Sparse4Dv3
receiver preserve the predeclared risk direction?

The exact inputs, hashes, factor levels, partial order, stop rules and claim
boundary were published before these outputs in
`docs/runs/hugsim_ordinal_metamorphic_preregistration_001.md` and its JSON.
The 16 m, 24 m and 4 m levels are test-design coverage, not real-world safety
thresholds.

## Runs and Integrity Gates

All five new outputs completed 36/36 steps:

```text
artifacts/hugsim_ordinal_metamorphic/scene-0383-ordinal-no-actor-001-run001
artifacts/hugsim_ordinal_metamorphic/scene-0383-ordinal-center-near-001-run001
artifacts/hugsim_ordinal_metamorphic/scene-0383-ordinal-center-far-001-run001
artifacts/hugsim_ordinal_metamorphic/scene-0383-ordinal-adjacent-near-001-run001
artifacts/hugsim_ordinal_metamorphic/scene-0383-ordinal-adjacent-far-001-run001
```

All timestamps, ego states, deterministic plans and actions pair exactly.
The planned future requires 2.5 seconds of actor history, so the fail-closed
analysis window is `(0, 6.5] s`: 26 simulator timestamps and 13 Sparse4Dv3
timestamps.

The first command attempt stopped before HUGSIM started because the new
artifact parent directory did not exist. It created no simulator output and
exposed no result; the parent was created and the already-published command was
reissued unchanged. This is retained as run provenance, not experimental
evidence.

## Independent Geometry Result

The independent oriented-footprint and planned-corridor recomputation passes
all four predeclared relations at every one of the 26 valid timestamps.

| Relation | Factor margin | Minimum ego-clearance margin | Minimum planned-corridor margin |
|---|---:|---:|---:|
| centre/near > centre/far | 8.00 m | 8.00 m | 8.00 m |
| centre/near > adjacent/near | 4.00 m | 0.219 m | 0.271 m |
| centre/far > adjacent/far | 4.00 m | 0.136 m | 0.154 m |
| adjacent/near > adjacent/far | 8.00 m | 7.791 m | 7.627 m |

This accepts only that the intended intervention exists in the recorded
HUGSIM state and satisfies the declared planar geometry. The actor boxes and
ego state still originate from HUGSIM; this is not independent real-world
state truth.

## Frozen Sparse4Dv3 Result

Sparse4Dv3 receives the raw six-camera HUGSIM RGB and camera calibration;
HUGSIM semantic and depth are excluded. The no-actor baseline has zero
qualified vehicle detections inside the valid window. Its one low-confidence
car response occurs only at reset timestamp `0.0 s`, outside this audit
window.

| Predeclared receiver relation | Expected frames | Reversals | Unavailable | Decision |
|---|---:|---:|---:|---|
| centre/near > centre/far | 13 | 0 | 0 | `accepted` |
| centre/near > adjacent/near | 12 | 0 | 1 | `down-weighted` |
| centre/far > adjacent/far | 13 | 0 | 0 | `accepted` |
| adjacent/near > adjacent/far | 12 | 0 | 1 | `down-weighted` |

Both unavailable comparisons are the same `adjacent_near` association at
`t=6.5 s`. They are not imputed. The aggregate relation direction remains as
expected, but the preregistered “every timestamp available” condition is not
met; therefore the two affected relations cannot be accepted.

Median associated receiver positions in the valid window are:

| Condition | Available frames | Median receiver XY (m) |
|---|---:|---:|
| centre/near | 13/13 | `[16.109, 0.276]` |
| centre/far | 13/13 | `[22.956, 0.371]` |
| adjacent/near | 12/13 | `[16.961, -4.415]` |
| adjacent/far | 13/13 | `[23.236, -3.915]` |

## HUGSIM Internal Score Is Not the Judge

Inside the complete-future window, HUGSIM's NC/TTC/PDMS remain `1.0` for all
five conditions. The centre/near run's first internal TTC and NC failures occur
only at `7.75 s` and `8.75 s`, outside that window, and are not used.

This contrast is useful: the new ordinal task relation detects a consistent
near/far and centre/adjacent change even when HUGSIM's coarse binary score does
not change. It does not prove that the new relation is calibrated to real
danger; it shows that metric audit can produce a more task-sensitive,
non-self-referential test than simply reading HUGSIM's score.

## Credibility Judgment

Overall segment: `down-weighted`.

Positive evidence:

- the published manifest and all input/config hashes remain fixed;
- all four geometry relations pass across the complete-future window;
- all available Sparse4Dv3 comparisons have the expected direction;
- two complete receiver relations are `accepted` with zero reversal;
- the valid-window no-actor baseline has no qualified vehicle response.

Negative/boundary evidence:

- the claim that every receiver relation is available at every planned
  timestamp is `rejected`: `adjacent_near` is unavailable at `6.5 s`;
- two task relations are consequently `down-weighted`;
- the cause of the missing association is not isolated between rendering,
  calibration/domain shift and Sparse4Dv3, so it is not assigned to HUGSIM
  alone;
- only one receiver, one scene, one asset and a designed—not
  real-distribution-qualified—factor range are covered.

Strongest supported statement:

> Within the declared 2x2 design range and complete-future window, the HUGSIM
> intervention satisfies the independently recomputed geometric order and the
> frozen Sparse4Dv3 probe preserves every available predeclared longitudinal
> and lateral ordinal comparison without reversal.

Still unavailable: real-world frequency or thresholds, realistic actor policy,
real-sensor equivalence, AD planning/control response, direct real-sim
equivalence, and general HUGSIM fitness as an AD test domain.

## Inspectable Results

```text
artifacts/hugsim_ordinal_metamorphic/analysis-run002/ordinal_audit_summary.png
artifacts/hugsim_ordinal_metamorphic/analysis-run002/ordinal_receiver_contact_sheet.png
artifacts/hugsim_ordinal_metamorphic/analysis-run002/ordinal_receiver_comparison.mp4
artifacts/hugsim_ordinal_metamorphic/analysis-run002/ordinal_metamorphic_audit.json
artifacts/hugsim_ordinal_metamorphic/analysis-run002/REPORT.md
```

The contact sheet and video show the raw HUGSIM `CAM_FRONT` arrays supplied to
Sparse4Dv3, with only the frozen actor-associated receiver box shown for actor
conditions. The summary figure shows receiver expected/reversal/unavailable
counts beside the independently recomputed planned-corridor clearances.

## Reproduction

Run the five conditions exactly as declared in the preregistration, then run
the frozen receiver once for all five outputs. Generate the final audit with:

```bash
MPLCONFIGDIR=/tmp/matplotlib-hugsim-ordinal \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/analyze_hugsim_ordinal_metamorphic.py \
  --preregistration docs/runs/hugsim_ordinal_metamorphic_preregistration_001.json \
  --receiver-output artifacts/hugsim_ordinal_metamorphic/sparse4d-run001 \
  --output NEW_ANALYSIS_DIRECTORY \
  --preregistration-commit c784cbcdd6c3ff4554a26e79d683bcf8703b42b1
```
