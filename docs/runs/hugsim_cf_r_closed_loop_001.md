# HUGSIM × SparseDrive replicated CF-R closed loop 001

Date: 2026-07-23

Preregistration commit: `4cebc93`

## Outcome

The preregistered narrow simulator-internal causal-response claim is
`accepted`.

The same lead vehicle started from the same `t=0` pose and followed one of two
ConstantPlanner speeds:

- `slow = 0.5 m/s`: stronger ego closure;
- `fast = 1.5 m/s`: weaker ego closure.

For each condition, HUGSIM first replayed the retained source actions through
`1.5 s`. All seven checked source states and six-camera RGB groups reproduced
with zero residual. SparseDrive was independently reset and pre-warmed with
the corresponding `0.0, 0.5, 1.0 s` observations, then produced nine fresh
plans over a `4.5 s` live loop. Each condition was independently repeated
twice.

All four valid runs completed without fallback, plan repetition, action-bound
violation, termination or collision. HUGSIM NC/TTC/PDMS were disabled.

## Preregistered direct outcomes

| Construct at `t=6.0 s` | Strong conflict, resets 1 / 2 | Weak conflict, resets 1 / 2 | Minimum condition effect | Maximum within-condition variation | Decision |
|---|---:|---:|---:|---:|---|
| Ego longitudinal progress | `3.871 / 3.938 m` | `6.245 / 6.253 m` | `2.315 m` | `0.067 m` | `accepted` |
| Ego speed | `0.082 / 0.280 m/s` | `0.981 / 0.977 m/s` | `0.698 m/s` | `0.198 m/s` | `accepted` |
| Oriented ego–actor footprint clearance | `11.397 / 11.326 m` | `15.266 / 15.258 m` | `3.869 m` | `0.071 m` | `accepted` |

Every paired repeat had the preregistered strict order:

```text
stronger conflict < weaker conflict
```

For all three constructs, the minimum between-condition effect exceeded the
largest same-condition repeat variation. The ratios were approximately
`34.6×` for progress, `3.5×` for speed and `54.3×` for clearance. There was no
weak-only adverse-event reversal.

Clearance is an independently recomputed oriented-footprint state outcome, not
a pure AD-response measure. Part of its strong/weak difference is created
directly by the actor-speed intervention. Ego progress and speed are the more
direct downstream AD-control outcomes.

## What happened in the loop

Both conditions started the live phase at `1.916 m/s`.

In the strong condition, SparseDrive repeatedly requested deceleration and the
ego nearly stopped, ending at `0.082 / 0.280 m/s`. The selected native planning
mode changed from `3` to `5` and finally `1` in both resets.

In the weak condition, deceleration was smaller and the ego continued at about
`0.98 m/s`. Native planning mode remained `3` throughout both resets.

The strong-condition final-speed spread and one reset's final steer-rate spike
confirm that exact closed-loop numerical reproducibility remains false. The
causal condition effect nevertheless remained larger than that repeat
sensitivity under the frozen rules.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| Exact source history reaches the live boundary | `accepted` | two retained actor-speed conditions; state and RGB zero-residual through `1.5 s` |
| The designed conflict difference reaches direct AD-controlled vehicle outcomes with an effect larger than repeat sensitivity | `accepted` | one scene, two actor speeds, frozen SparseDrive, two resets per condition and `4.5 s` live horizon |
| The complete closed loop is exactly numerically reproducible | `rejected` | strong-condition final speed differed by `0.198 m/s`; exact-repeat evidence was already rejected in the normal live gate |
| The response magnitude is realistic or externally calibrated | `down-weighted` | no matched real outcome or qualified behavior range |
| This establishes physical TTC, real-world safety or general HUGSIM credibility | `rejected` | those claims exceed this designed simulator-internal experiment |

Here `rejected` limits the specific stronger claim. It does not discard the
positive internal causal-response result.

## Inspectable artifacts

```text
artifacts/sparsedrive_cf_r_closed_loop/{slow,fast}-run00{1,2}
artifacts/sparsedrive_cf_r_closed_loop/analysis-run001/cf_r_closed_loop_audit.json
artifacts/sparsedrive_cf_r_closed_loop/analysis-run001/cf_r_closed_loop_summary.png
artifacts/sparsedrive_cf_r_closed_loop/visual-run002/cf_r_closed_loop_front_comparison_h264.mp4
artifacts/sparsedrive_cf_r_closed_loop/visual-run002/cf_r_closed_loop_front_contact_sheet.png
```

The comparison media show reset 1 from each condition. The metric plot includes
both resets.

Two startup attempts exited after FIFO readiness and are retained under
`artifacts/sparsedrive_cf_r_closed_loop/startup-failed-*`. They produced no
closed-loop outcome and are not counted as repeats. The orchestration was
changed to fail fast and retain post-readiness HUGSIM output; the experimental
conditions, horizon and decision rules were not changed.

## Strongest supported conclusion

Within this one scene, designed actor-speed range, exact source handoff, frozen
SparseDrive receiver and `4.5 s` horizon, HUGSIM preserved enough
task-relevant counterfactual information for stronger lead-actor conflict to
produce a directionally stronger closed-loop ego response, and that response
was larger than observed same-condition repeat sensitivity.

This is positive evidence for the reusable indicator:

```text
counterfactual condition effect > closed-loop repeat sensitivity
```

It does not show whether either response is the response a real vehicle should
have produced.
