# HUGSIM Multi-Actor Cut-In Stress Test 001

Date: 2026-07-19

## Correction — 2026-07-20

The original internal-risk interpretation has been withdrawn.

An independent evidence review found that HUGSIM's scorer needs 2.5 seconds of
future actor history for each frame. This 6-second run has complete history
only through 3.5 seconds, while its TTC and NC failures begin at 4.75 and 5.75
seconds. When the exact same state/action/plan prefix was extended to 9
seconds, all corresponding failures disappeared.

The old TTC/NC decrease is therefore a finite-rollout tail-padding artifact,
not accepted dynamic-risk evidence. See:

```text
docs/runs/hugsim_horizon_factorial_001.md
```

## Purpose

Replace the previous small lateral-placement contrast with a visibly large,
bounded intervention:

- a slower lead vehicle remains ahead of ego;
- a second vehicle starts at the front-right and moves diagonally across the
  ego path;
- a no-actor run uses the same ego plan, control convention, duration, and
  scene as the paired baseline.

This is a simulator stress test. The deterministic plan-pipe writer remains a
loop enabler, not an AD agent.

## Configuration

Scenario:

```text
configs/hugsim/scenarios/scene-0383-multicar-cut-in-00.yaml
```

Background:

```text
/home/yawei/HUGSIM_assets/scenes/nuscenes/scene-0383
```

Both actor instances reuse the only locally available 3DRealCar asset:

```text
2024_07_05_15_57_10
```

Configured actor states:

| Actor | Right | Forward | Yaw | Speed | Role |
|---|---:|---:|---:|---:|---|
| 0 | 4.5 m | 8.0 m | 0.45 rad | 2.0 m/s | right-side diagonal cut-in |
| 1 | 0.0 m | 24.0 m | 0.0 rad | 0.5 m/s | slower lead vehicle |

Both use `ConstantPlanner`. The cut-in is therefore a scripted straight
diagonal, not a map-aware lane-change policy.

## Runs

Successful paired runs:

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run006-6s
artifacts/hugsim_contrast/scene-0383-multicar-cut-in-00-run001
artifacts/hugsim_contrast/scene-0383-multicar-report-run003
```

Each successful run completed 24 steps over 6 seconds with the corrected
control convention.

An earlier baseline attempt was incomplete:

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run005-6s
```

The writer exited immediately after its 24th plan response while the runner
was waiting to send the final FIFO `Done` signal. It contains only partial
bring-up artifacts and is not used as evidence. The successful rerun allowed
the writer one additional FIFO read.

## Results

The paired ego trajectory and actions remained identical:

```text
maximum ego-box absolute difference: 0.0
maximum action absolute difference: 0.0
```

Run-level metrics:

| Condition | NC | TTC | PDMS | RC | HDScore |
|---|---:|---:|---:|---:|---:|
| no actors | 1.000 | 1.000 | 1.000 | 0.185374 | 0.185374 |
| lead + cut-in | 0.9167 | 0.750 | 0.7976 | 0.185374 | 0.147857 |

Event timing:

```text
cut-in crosses the ego centerline: approximately 5.0 s
first planned-path TTC failure: 4.75 s
first NC failure: 5.75 s
actual runtime collision observed: false
```

These are retained as the raw 6-second outputs. The TTC/NC event times fall
inside the horizon-invalid tail and must not be interpreted as credible risk.

The cut-in actor moves from approximately:

```text
longitudinal/lateral [8.45, -4.28] m
→ [19.26, 0.94] m
```

The lead actor moves from approximately:

```text
[24.13, 0.0] m
→ [27.13, 0.0] m
```

HUGSIM advances the actor controller once during `env.reset`, so the
timestamp-zero recorded actor state is already one controller update beyond
the YAML initial state. This weakens exact actor-time provenance and must be
retained as a limitation.

## Sensor-Side Evidence

At the five selected frames, the injected-car semantic mask was supported by
RGB differences for approximately 97.0% to 98.5% of its pixels and by depth
differences for 100% of its pixels.

This shows internal RGB / semantic / depth co-movement during the cut-in. It
does not independently establish real-sensor correctness because all three
modalities come from the same renderer.

Visual artifacts remain obvious:

- both actors use the same vehicle identity;
- foreground appearance differs visibly from the background;
- the scripted diagonal motion is not constrained by a lane map;
- the deterministic ego planner does not react to either vehicle.

## Artifacts

```text
artifacts/hugsim_contrast/scene-0383-multicar-report-run003/front_multicar_comparison.mp4
artifacts/hugsim_contrast/scene-0383-multicar-report-run003/front_multicar_contact_sheet.png
artifacts/hugsim_contrast/scene-0383-multicar-report-run003/multicar_trajectory_and_risk.png
artifacts/hugsim_contrast/scene-0383-multicar-report-run003/multicar_summary.json
```

## Credibility Judgment

Overall decision:

```text
down-weighted
```

Accepted narrow subclaims:

- the 6-second no-actor and multi-actor runs are strictly paired in ego state
  and action;
- HUGSIM renders two actor instances with synchronized RGB, semantic, depth,
  and state evolution;
- the old and extended runs have an exact common state/action/plan prefix.

Down-weighted claims:

- the visual observations are suitable sensor evidence for an E2E agent;
- the scripted diagonal trajectory represents a realistic merge;
- the two duplicated vehicle instances represent diverse traffic.

Rejected claims:

- the 6-second NC/TTC decrease is credible dynamic-risk evidence;
- an actual runtime collision occurred;
- an AD agent responded to the cut-in;
- this single stress test establishes global HUGSIM credibility.

## Next Material Improvement

Before adding more appearance or behavior diversity, require complete future
actor history for every scored planned waypoint. A later pre-specified
near-distance cut-in satisfies that gate and is documented in
`docs/runs/hugsim_near_cut_in_001.md`.
