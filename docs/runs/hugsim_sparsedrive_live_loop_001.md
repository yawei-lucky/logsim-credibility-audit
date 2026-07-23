# HUGSIM × SparseDrive live feedback capability 001

Date: 2026-07-23

## Outcome

The narrow live AD feedback capability is `accepted`.

SparseDrive was independently reset, pre-warmed with exact recorded frames at
`0.0, 0.5, 1.0 s`, and connected to HUGSIM at the matching `1.5 s` state.
During each two-second run it consumed four newly returned six-camera
observations and produced four fresh native plans. Each plan drove HUGSIM for
two `0.25 s` substeps through the qualified iLQR interface.

The run was repeated in a new HUGSIM process and a newly loaded SparseDrive
process. Both runs completed without fallback, plan repetition, action-bound
violation, termination, collision, or HUGSIM safety scoring.

Exact numerical closed-loop reset reproducibility is `rejected`: small initial
GPU variation was amplified by feedback. Short-horizon task-direction stability
is `down-weighted`, not rejected, because both runs retained the same planning
mode, acceleration-sign sequence and no-event outcome.

## Boundary and live handoff

For both runs:

- initial HUGSIM vehicle-state residual from the recorded boundary: `0`;
- initial six-camera RGB maximum pixel difference: `0`;
- first live plan versus the qualified offline plan:
  `3.8e-6 m` and `6.2e-6 m`, within the frozen `1e-4 m` reset envelope;
- plans sent: `4/4`;
- returned observation hashes: four distinct values per run;
- selected native planning mode: `3` at every update.

Thus the first plan reproduces the qualified offline receiver boundary, while
the later plans genuinely consume feedback observations produced by prior AD
actions.

## Reset sensitivity

| Receiver time | Maximum plan difference | Acceleration difference | Same mode / acceleration direction |
|---:|---:|---:|---|
| 1.5 s | `0.000010 m` | `0.0000036 m/s²` | yes |
| 2.0 s | `0.000926 m` | `0.000377 m/s²` | yes |
| 2.5 s | `0.008458 m` | `0.002742 m/s²` | yes |
| 3.0 s | `0.032244 m` | `0.015898 m/s²` | yes |

At the end of two seconds, the independent runs differed by:

- at most `0.00204 m` or radians in the reported ego box;
- `0.00677 m/s` in ego speed.

This is not evidence of state contamination: each process was independently
created, the first observation and receiver output matched, and divergence
began only after the first slightly different control entered the feedback
loop. It is evidence that exact numerical receiver reproducibility does not
transport unchanged into closed-loop numerical reproducibility.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| SparseDrive consumes new HUGSIM observations and returns fresh plans through the qualified interface | `accepted` | one no-actor scene, four 2 Hz plans over two seconds |
| The complete live loop is numerically identical after independent reset | `rejected` | plan differences exceed the inherited `1e-4 m` receiver reset envelope after feedback begins |
| Planning mode, action direction and no-event outcome are stable in this short normal run | `down-weighted` | two repeats; no externally qualified magnitude tolerance or task boundary |
| The result establishes realistic control or real-world closed-loop credibility | `rejected` | no matched real outcome, conflict intervention or external behavior range |

The rejected exact-repeat claim does not mean the live loop failed. It means
future counterfactual effects must be evaluated against within-condition
closed-loop variation rather than assuming a deterministic zero-width
baseline.

## Inspectable artifacts

```text
artifacts/sparsedrive_live_loop/normal-run001
artifacts/sparsedrive_live_loop/normal-run002
artifacts/sparsedrive_live_loop/analysis-run001/live_loop_audit.json
artifacts/sparsedrive_live_loop/analysis-run001/live_loop_summary.png
```

## Next experiment rule

The next CF-R closed-loop experiment should use at least two independent runs
for both stronger and weaker conflict conditions. A positive directional claim
requires:

1. the expected ordering of direct ego progress, speed or actor clearance in
   every paired repeat;
2. no task-level outcome reversal;
3. the minimum between-condition separation to exceed the maximum
   within-condition reset variation for that same construct.

This forms a reusable robustness indicator:

```text
counterfactual effect separation > closed-loop repeat sensitivity
```

Use direct state and geometry outcomes. Keep HUGSIM NC/TTC/PDMS disabled for
the acceptance decision.
