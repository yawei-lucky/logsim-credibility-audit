# HUGSIM Counterfactual Audit 001 — Relation-Specific Stationary Actor

Date: 2026-07-18

## Result

This experiment is the first HUGSIM run in this repository that supports a
specific simulator-side credibility statement rather than only proving that
the loop executes:

> With ego state, planner output, control action, scene, and time held exactly
> constant, a stationary car on the ego path is consistently represented in
> RGB, semantic, depth, and internal geometry, and it causes HUGSIM's
> planned-path TTC and NC checks to fail. Moving the same car 3.5 m laterally
> removes those metric failures.

The narrow evidence judgment is:

```text
accepted
```

This does **not** establish global HUGSIM credibility, AD-agent performance, or
an actual physical collision during the five-second rollout.

## Why the Previous Longer Run Was Invalid

The first 20-step attempt used HUGSIM's released `traj2control` conversion.
Both the no-actor and same-lane-actor runs followed the same curved trajectory,
hit reconstructed background at 3.25 seconds, terminated after 13 steps, and
produced bit-for-bit identical aggregate metrics.

That pair is `rejected` as evidence that the injected actor caused the event.
It was nevertheless useful diagnostically because it exposed a control
confound:

```text
planner coordinates: [right, forward]
controller positions: [forward, lateral]  (axes swapped)
released heading: calculated from the pre-swap axis order
effect: a straight-forward plan receives an approximately 90° heading target
```

The audit runner now uses `scripts/hugsim_control_adapter.py`. It calculates
heading after converting the waypoint positions to the controller frame.
`--control-convention upstream` remains available to reproduce the released
behavior. Four control-adapter regression tests cover straight, diagonal,
state-forwarding, and invalid-input cases.

The HUGSIM source checkout itself was not modified.

## Controlled Design

All three runs used:

- HUGSIM commit `adeca402cad4af8635e13d0a105e2fee6a14de85`;
- released nuScenes `scene-0383`;
- the same initial ego state;
- the same six-waypoint deterministic forward plan;
- the corrected coordinate adapter;
- 20 steps at 0.25 seconds per step;
- identical ego actions and ego trajectory.

Only actor placement changed:

| Condition | Actor placement | Purpose |
|---|---|---|
| no actor | none | baseline |
| same-lane actor | forward 15.0 m, lateral 0.0 m | risk-increasing treatment |
| adjacent-lane actor | forward 15.0 m, right 3.5 m | relation negative control |

The actor was the public `3DRealCar/2024_07_05_15_57_10` asset under a
stationary `ConstantPlanner`.

## Run Outputs

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run003-corrected
artifacts/hugsim_contrast/scene-0383-medium-00-run002-corrected
artifacts/hugsim_contrast/scene-0383-adjacent-static-00-run001-corrected
artifacts/hugsim_contrast/scene-0383-counterfactual-report-run002
```

The report directory contains:

```text
contrast_summary.json
front_counterfactual_contact_sheet.png
front_counterfactual.mp4
relation_negative_control.png
risk_timeline.png
```

## Quantitative Result

| Metric | No actor | Same-lane actor | Adjacent-lane actor |
|---|---:|---:|---:|
| NC | 1.000 | 0.750 | 1.000 |
| DAC | 1.000 | 1.000 | 1.000 |
| TTC | 1.000 | 0.550 | 1.000 |
| Comfort | 1.000 | 1.000 | 1.000 |
| PDMS | 1.000 | 0.607 | 1.000 |
| Route completion | 0.150333 | 0.150333 | 0.150333 |
| HDScore | 0.150333 | 0.091274 | 0.150333 |

Pairing checks:

```text
maximum ego-box difference across runs: 0.0
maximum action difference across runs: 0.0
actual collision flag in all three runs: false
```

In the same-lane treatment:

- the first TTC failure occurs at 3.00 seconds;
- the first NC failure occurs at 4.00 seconds;
- final actual longitudinal box clearance is still 2.20 m.

Therefore NC/TTC here describe HUGSIM's collision checks over the supplied
future planned trajectory. They must not be reported as an actual collision
already observed in the rollout.

## Cross-Modal Attribution

The same-lane actor is present in the front camera for every observation from
0.00 through 5.00 seconds.

```text
injected car semantic pixels:
  initial: 4,264
  final: 41,023

final actor semantic mask supported by RGB difference: 97.4%
final actor semantic mask supported by depth difference (>0.5 m): 100.0%
RGB changed pixels in the other five cameras across all 21 frames: 0
```

Manual review of the generated contact sheet found:

- plausible vehicle orientation and scale growth during approach;
- spatial agreement between the RGB vehicle, car semantic mask, and depth
  discontinuity;
- stable temporal approach without actor jumps;
- no relevant malformed, floating, duplicated, or contradictory actor evidence.

## Evidence Judgment

### Accepted

The same-lane risk event is `accepted` as narrow evidence that:

- the public actor asset is injected into the intended front relation;
- RGB, semantic, depth, and actor geometry support the same object;
- TTC and NC change only when that object intersects the planned path;
- an adjacent-lane placement acts as a successful negative control.

### Rejected

The earlier background-collision pair under the released control conversion is
`rejected` as evidence of actor-caused collision because the no-actor run
failed identically.

### Not established

This experiment does not establish:

- an actual collision within the five-second segment;
- a credible avoidance response from an AD agent;
- correctness across actors, scenes, distances, or reconstruction boundaries;
- global HUGSIM credibility.

The deterministic plan-pipe writer remains a simulator-loop enabler, not an AD
agent.

## Reproduction

Run the bounded simulator first in a GPU-visible context, then the plan writer
against the same new output directory:

```bash
env \
  PATH=/usr/local/cuda-12.1/bin:/home/yawei/.pixi/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CUDA_HOME=/usr/local/cuda-12.1 \
  TORCH_CUDA_ARCH_LIST=8.9 \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/run_hugsim_debug_smoke.py \
  --scenario SCENARIO_YAML \
  --max-steps 20 \
  --control-convention corrected \
  --output NEW_OUTPUT_DIRECTORY
```

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/hugsim_plan_pipe_writer.py \
  --output NEW_OUTPUT_DIRECTORY \
  --horizon 6 \
  --step-m 1.0 \
  --max-steps 21
```

Generate the synchronized analysis:

```bash
MPLCONFIGDIR=/tmp/matplotlib-hugsim-contrast \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/analyze_hugsim_counterfactual.py \
  --baseline artifacts/hugsim_contrast/scene-0383-easy-00-run003-corrected \
  --treatment artifacts/hugsim_contrast/scene-0383-medium-00-run002-corrected \
  --adjacent-control artifacts/hugsim_contrast/scene-0383-adjacent-static-00-run001-corrected \
  --output NEW_REPORT_DIRECTORY
```

## Next Research Step

The next material experiment should map the **relation boundary**, not merely
run longer:

- hold the car model and deterministic ego plan fixed;
- sweep a small set of lateral and longitudinal actor offsets;
- compare the exact geometry boundary with TTC/NC transition times;
- look for non-monotonic or cross-modal contradictions;
- retain paired no-actor controls.

That would test whether the relation-sensitive result generalizes beyond one
same-lane and one adjacent-lane placement without yet installing a full AD
agent or claiming a final credibility metric.
