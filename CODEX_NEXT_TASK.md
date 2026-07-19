# Codex Next Task — Review and Strengthen the Multi-Actor Stress Test

> Read this file first when resuming HUGSIM work.

## Project Objective

Develop a credibility-validation method for log-driven simulators.

This project uses the broad definition:

> A log-driven simulator constructs an interactive environment from real
> road-driving capture sequences and generates counterfactual closed-loop
> evolution. Exact log replay is not required.

HUGSIM is the first case study, not the final research target. It is classified
as a real-driving-sequence reconstruction-based, counterfactual closed-loop
neural simulator.

## Current Work Process

The current work follows four practical steps:

```text
Source Availability Gate
→ Closed-Loop Evidence Completeness
→ Segment-Level Evidence Judgment
→ Future Credibility Metric
```

Current HUGSIM status:

- source availability discovery is complete for the present phase;
- the simulator-side closed-loop evidence chain runs reproducibly;
- the first paired counterfactual segment is `down-weighted` overall;
- narrow state/action pairing and internal-geometry response subclaims are
  `accepted`;
- a 6-second lead-vehicle plus right-side cut-in stress test has completed;
- the multi-actor run is `down-weighted` overall, while strict pairing,
  multi-instance rendering/state evolution, and internal risk timing are
  `accepted` narrow subclaims;
- sensor-input AD-agent performance and global HUGSIM credibility are not
  established.

The long-term credibility metric is planned around a four-layer evidence chain:
log reproduction, sensor consistency, task-level consistency, and closed-loop
outcome credibility. That is a future metric-research direction, not the
current experimental grading scheme. Do not assign HUGSIM per-layer scores or
design the metric during this task.

Read:

```text
docs/hugsim_credibility_decision_rules.md
docs/hugsim_smoke_test_plan.md
docs/runs/hugsim_counterfactual_001.md
docs/runs/hugsim_counterfactual_001_audit.json
docs/runs/hugsim_multicar_cut_in_001.md
docs/runs/hugsim_multicar_cut_in_001_audit.json
```

## Corrected Baseline

Third-party review found a one-step mismatch between the metric frame and its
planned-trajectory anchor. The runner now anchors timestamp, ego/actor state,
and global plan at the same post-step state and includes a regression test.

Aligned outputs:

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run004-aligned
artifacts/hugsim_contrast/scene-0383-medium-00-run003-aligned
artifacts/hugsim_contrast/scene-0383-adjacent-static-00-run002-aligned
artifacts/hugsim_contrast/scene-0383-counterfactual-report-run003-aligned
```

Aligned internal metrics:

| Actor placement | NC | TTC | PDMS | HDScore |
|---|---:|---:|---:|---:|
| none | 1.000 | 1.000 | 1.000 | 0.150333 |
| lateral 0.0 m, forward 15.0 m | 0.700 | 0.500 | 0.557 | 0.083757 |
| lateral 3.5 m, forward 15.0 m | 1.000 | 1.000 | 1.000 | 0.150333 |

These results establish a narrow internal-geometry response, not sensor-level
E2E evaluation credibility.

## Strong Multi-Actor Result

Paired outputs:

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run006-6s
artifacts/hugsim_contrast/scene-0383-multicar-cut-in-00-run001
artifacts/hugsim_contrast/scene-0383-multicar-report-run003
```

The treatment contains a slower lead vehicle and a right-side vehicle moving
diagonally across the ego path. Both actors reuse the same locally available
3DRealCar asset.

| Condition | NC | TTC | PDMS | HDScore |
|---|---:|---:|---:|---:|
| no actors | 1.000 | 1.000 | 1.000 | 0.185374 |
| lead + cut-in | 0.9167 | 0.750 | 0.7976 | 0.147857 |

The paired ego states and actions are identical. The cut-in crosses the ego
centerline at approximately 5.0 seconds; TTC first fails at 4.75 seconds and NC
at 5.75 seconds. No actual runtime collision occurs.

## Immediate Goal

Review whether the large intervention produces mutually consistent visual,
actor-state, and internal-risk evidence.

Target test chain:

```text
no-actor baseline
→ lead vehicle + right-side diagonal cut-in
→ synchronized RGB / semantic / depth and actor trajectories
→ TTC / NC event timing
→ segment-level accepted / down-weighted / rejected judgment
```

## Required Questions

1. Does the right-side vehicle move continuously from the image edge through
   the ego-path region in RGB, semantic, depth, and recorded actor state?
2. Does the TTC/NC timing align with the actor's centerline crossing rather
   than merely with actor presence?
3. How much do duplicated vehicle identity, foreground/background appearance
   mismatch, and reset-time actor advancement weaken the evidence?
4. Is the scripted `ConstantPlanner` diagonal adequate for renderer/metric
   stress testing while remaining insufficient as realistic merge behavior?
5. If another run is justified, should it use distinct vehicle assets and a
   map-aware or explicitly staged merge instead of another placement tweak?

## Near-Term Outputs

- an inspectable front comparison video;
- a five-timepoint RGB / semantic / depth contact sheet;
- a top-down actor-trajectory and risk timeline;
- a reproducible multi-actor run report and compact audit record;
- claim-specific decisions that separate internal response from traffic
  realism and AD-agent claims;
- no final credibility metric or per-layer simulator score.

## Guardrails

Do not:

- treat real-log origin as proof of counterfactual credibility;
- equate RGB/semantic/depth agreement from one renderer with real-world
  agreement;
- call the scripted diagonal a validated real-world merge;
- treat two instances of one vehicle asset as appearance diversity;
- report internal NC/TTC response as sensor-input AD-agent validity;
- install full AD agents before source and simulator evidence are understood;
- run a full benchmark or design the final credibility metric;
- grade HUGSIM using the future four-layer evidence-chain concept;
- expand to OmniDreams / Cosmos during this task;
- overwrite successful outputs.

## Success Criterion

This task succeeds when the visually obvious cut-in can be traced through
rendered observations, actor states, and metric timing, while the limitations
of duplicated appearance, scripted behavior, and the dummy ego planner remain
explicit. More runs are justified only if they materially improve actor
diversity or behavior realism.
