# HUGSIM Sparse4Dv3 cross-scene and task-envelope audit 001

## Purpose

Extend the first Sparse4Dv3 controlled baseline to the two additional normal
scenes, determine which current errors may still be adequate for an AD task,
and converge the evidence into a small task-relative indicator set before
adding more receivers or scenarios.

This audit reuses the frozen official Sparse4Dv3 predictions from:

```text
artifacts/sparse4d_receiver_baseline/baseline-and-response-run001
```

No model was retrained and HUGSIM semantic/depth were not receiver inputs.

## Research-layer position

The current result is a **task-level receiver-consistency candidate**, not
sensor-consistency evidence.

- Sparse4Dv3 receives HUGSIM camera observations and produces driving-domain
  perception outputs;
- there is no matched real RGB clip or independent sensor reference;
- camera array/calibration/preprocessing checks establish an input contract,
  not real-sensor equivalence;
- HUGSIM semantic, depth, and actor state remain outputs under audit.

The metric-convergence rationale is recorded in
`docs/simulator_credibility_indicator_convergence.md`.

## Cross-scene normal baseline

All scenes contain 19 receiver frames sampled at 2 Hz.

| Scene | Vehicle-positive @0.2 | @0.3 | @0.5 | Qualified classes at 0.2 |
|---|---:|---:|---:|---|
| scene-0383, no injected actor | 1/19 | 0/19 | 0/19 | bicycle 35, pedestrian 30, car 1 |
| scene-0041 | 5/19 | 1/19 | 0/19 | truck 4, car 2 |
| scene-0138 | 16/19 | 12/19 | 0/19 | pedestrian 48, bus 23, car 9 |

`scene-0041` has weak vehicle responses. Its only persistent track is a truck
in the final four frames, with maximum score 0.335. The two initial car
responses last one frame each.

`scene-0138` produces persistent pedestrian tracks around the bus-stop area and
weaker bus/car tracks near roadside or shelter structures. Its vehicle response
disappears at score 0.5 while eight pedestrian-positive frames remain.

These rates measure receiver response, threshold stability, and persistence.
They are not precision/recall because the native normal-scene objects and
nuisance regions have not yet received independent labels.

## Controlled AD-task-relative endpoints

| Endpoint | Result | Evidence decision |
|---|---:|---|
| near actor ranks closer than far actor | 6/6 aligned pairs | accepted |
| same/adjacent lane relation | 43/44 actor frames | accepted |
| far dominant track identity | 19/19 associated frames | accepted |
| near dominant track identity | 5/6 associated frames | accepted, one initial switch |
| adjacent dominant track identity | 18/18 associated frames | accepted, one missed frame |
| absolute 3D position | 2.56/4.24/3.80 m median XY error | down-weighted |

The 2 m lane-relation boundary is the midpoint between the designed y=0 m and
y=-4 m intervention centers. It is not proposed as a universal lane-width or
credibility threshold.

The near longitudinal bias is about 81% of its median configured range. The
adjacent lateral bias is about 65% of the designed 4 m offset. Therefore the
current result may support coarse object presence, near/far ordering,
same/adjacent relation, and short tracking, but it does not establish metric
3D localization suitable for planning, collision prediction, or braking.

## Box-bias diagnostic after cross-scene aggregation

The detector-box investigation was performed only after freezing the
cross-scene summary.

For each controlled frame, the associated Sparse4Dv3 3D box was projected into
the camera with the largest injected-car semantic-difference region.

| Condition | Median projected 2D IoU | Median projected-center error | Median XY metric error |
|---|---:|---:|---:|
| same-lane far | 0.69 | 3.1 px | 2.56 m |
| same-lane near | 0.74 | 17.5 px | 4.24 m |
| adjacent near | 0.82 | 9.2 px | 3.80 m |

Median Sparse4Dv3/configured-actor dimension ratios
`[longitudinal, lateral, vertical]` are:

- far: `[1.26, 1.22, 1.42]`;
- near: `[1.34, 1.25, 1.71]`;
- adjacent: `[1.55, 1.33, 2.03]`.

The receiver can therefore explain nearly the same image region with a larger,
farther 3D box. This supports a scale-depth/domain-shift diagnostic and makes a
gross image-plane projection failure unlikely as the sole cause. It does not
prove real calibration correctness because the semantic region and calibration
are HUGSIM outputs rather than independent truth.

Evidence decisions:

- `accepted`: repeated internal pixel-space overlap between the associated
  receiver box and injected rendered actor region;
- `down-weighted`: scale-depth/domain-shift explanation and absolute metric
  geometry;
- not established: metric geometry fit for planning or real sensor
  consistency.

## Converged current indicator families

The current work should stop adding unrelated proxy scores and retain:

1. mandatory evidence-validity and receiver-contract gates;
2. critical-object observability and causal sensitivity;
3. task-relevant relation and risk-order agreement;
4. metric bias, tracking continuity, and event timing;
5. nuisance robustness and cross-scene/threshold stability;
6. eventual matched real-simulation receiver equivalence and downstream
   decision invariance.

Acceptance bounds must come from a downstream AD decision margin, independent
measurement uncertainty, or a pre-specified equivalence design. The prior 2 m
and 4 m plot lines remain diagnostics only.

## Artifacts

Cross-scene summary:

```text
artifacts/sparse4d_receiver_baseline/cross-scene-summary-run003
```

- `cross_scene_summary.png`;
- `cross_scene_summary.json`;
- `normal_0041_six_camera_receiver.mp4`;
- `normal_0138_six_camera_receiver.mp4`;
- per-scene first/middle/last receiver contact sheets.

Box-bias diagnostic:

```text
artifacts/sparse4d_receiver_baseline/box-bias-diagnostic-run001
```

- `box_bias_diagnostic.png`;
- `box_bias_overlay.png`;
- `box_bias_diagnostic.json`;
- frame-level diagnostic JSON files.

## Next evidence upgrade

Fix a small labelled subset of native objects and nuisance regions in
`scene-0041` and `scene-0138`, then compute labelled nuisance robustness. The
larger upgrade remains the same frozen receiver on matched real and simulated
observations, followed by planner/action invariance under a declared task
margin.
