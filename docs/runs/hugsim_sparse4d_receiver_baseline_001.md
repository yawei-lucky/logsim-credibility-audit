# HUGSIM Sparse4Dv3 receiver baseline 001

## Purpose

Establish the first bounded, driving-domain 3D receiver baseline on recorded
HUGSIM six-camera RGB, then check whether the current metric-audit approach can
separate:

1. receiver sensitivity to a controlled vehicle injection;
2. correct near/far and same-lane/adjacent-lane direction;
3. absolute 3D position agreement;
4. normal-scene or no-injection nuisance response.

This is not a real-versus-sim comparison and does not establish global HUGSIM
credibility.

## Frozen receiver and input contract

- receiver: official Sparse4Dv3 R50 release;
- Sparse4D source commit: `249ffbb695f4e9db628d953e2bf6d36de04bbb69`;
- checkpoint: `/home/yawei/Sparse4D/ckpt/sparse4dv3_r50.pth`;
- checkpoint SHA-256:
  `5beed4d4933ca6448d72586b0f8812863574289ff3c4192de71dc9f46a42f0ed`;
- frozen real-nuScenes-trained weights; no HUGSIM fine-tuning;
- receiver input: six HUGSIM RGB arrays plus HUGSIM camera intrinsics and
  extrinsics;
- explicitly excluded: HUGSIM semantic and depth;
- camera order follows the official Sparse4D nuScenes converter;
- HUGSIM 4 Hz records are sampled every second frame to match the receiver's
  0.5-second temporal interval;
- 450x800 input is resized to 396x704 and bottom-cropped to 256x704. The same
  image transform is applied to each projection matrix;
- the official PyTorch deformable-aggregation fallback is used instead of the
  optional custom CUDA operator. The model weights and computation remain
  unchanged, but runtime implementation provenance is recorded in the run
  manifest.

The first-frame display in `receiver_front_views.png` is generated from the
same raw RGB arrays passed to the adapter. The receiver subsequently performs
the recorded deterministic resize, crop and normalization.

## Runs

Controlled paired scene:

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s
artifacts/hugsim_contrast/scene-0383-ad-receiver-front-far-00-run001-9s
artifacts/hugsim_contrast/scene-0383-ad-receiver-front-near-00-run001-9s
artifacts/hugsim_contrast/scene-0383-ad-receiver-adjacent-near-00-run001-9s
```

Additional normal-scene receiver baselines:

```text
artifacts/hugsim_scene_collection/scene-0041-easy-00-run001-9s
artifacts/hugsim_scene_collection/scene-0138-easy-00-run001-9s
```

Formal output:

```text
artifacts/sparse4d_receiver_baseline/baseline-and-response-run001
artifacts/sparse4d_receiver_baseline/baseline-and-response-run001/analysis-run002
```

Smoke outputs `scene-0383-smoke-run001`, `scene-0383-smoke-run002`,
`scene-0383-smoke-run003`, and `scene-0383-temporal-smoke-run001` are retained
as failed or preliminary adapter checks and are not the formal evidence run.

## Measurement definitions

- `qualified vehicle`: Sparse4Dv3 class `car`, `truck`,
  `construction_vehicle`, `bus`, or `trailer` with score at least 0.2;
- `vehicle-positive frame`: at least one qualified vehicle;
- `actor association`: nearest qualified vehicle center to HUGSIM's controlled
  actor center in ego-frame XY;
- `XY center error`: Euclidean distance between those two centers;
- 2 m and 4 m lines: diagnostics, not validated credibility thresholds;
- HUGSIM actor Z is not used as camera-projectable truth because its vertical
  convention has not been established for this receiver contract.

## Results

| Condition | Vehicle-positive frames | Median receiver XY (m) | Median HUGSIM actor XY (m) | Median XY error (m) |
|---|---:|---:|---:|---:|
| no injected actor | 1/19 (5.3%) | n/a | n/a | n/a |
| same-lane far | 19/19 (100%) | `[19.41, 0.34]` | `[17.86, 0.00]` | 2.56 |
| same-lane near | 6/6 (100%) | `[9.46, 0.15]` | `[5.22, 0.00]` | 4.24 |
| adjacent-lane near | 18/19 (94.7%) | `[1.55, -6.59]` | `[-0.11, -4.00]` | 3.80 |

The normal-scene baselines produced qualified vehicle responses in 5/19
`scene-0041` frames and 16/19 `scene-0138` frames. Those rates are not precision
or recall: the runs do not contain independent 3D annotations for their native
objects. They are nuisance and manual-review baselines only.

The no-injection run's only qualified vehicle response appears in the first
frame over the lower road/ego-hood region. It must not be interpreted as an
injected actor, and it shows why a receiver baseline is required before using
detection count as a simulator metric.

## Metric judgments

### `accepted` — controlled vehicle sensitivity

All three injected-vehicle conditions raise the vehicle-positive frame rate by
more than 0.5 relative to the paired no-injection baseline. The frozen receiver
therefore responds causally to the visible controlled vehicle in these runs.

### `accepted` — relation direction

- near receiver x (9.46 m) is smaller than far receiver x (19.41 m);
- adjacent receiver y (-6.59 m) is substantially more negative than same-lane
  receiver y (0.15 m).

The receiver preserves the intended longitudinal and lateral ordering.

### `down-weighted` — absolute actor position consistency

The median XY errors of 2.56 m, 4.24 m, and 3.80 m are material. The near actor
is consistently perceived too far away, while the adjacent actor is perceived
too far to the right. The present experiment cannot uniquely attribute this to
HUGSIM rendering, the HUGSIM-to-Sparse4D calibration/coordinate contract, or
Sparse4Dv3 domain shift.

## What this establishes

The current metrics are useful because they did not collapse all outcomes into
one score. They separately expose:

- strong causal task response;
- correct relation direction;
- weak absolute geometry agreement;
- non-zero nuisance response without an injected actor.

The bounded result is:

> In the tested scene and receiver contract, HUGSIM RGB contains task-relevant
> vehicle information that drives a frozen real-data-trained 3D receiver in the
> intended causal direction, but absolute 3D geometry is not yet sufficiently
> established for a simulator-validity claim.

Not tested: real-versus-sim equivalence, planning/control behavior, closed-loop
outcome credibility, and global HUGSIM validity.

## Inspectable artifacts

- `analysis-run002/metric_overview.png`: detection, longitudinal, lateral and
  XY-error curves;
- `analysis-run002/receiver_front_views.png`: raw front tri-camera arrays with
  the top qualified Sparse4Dv3 vehicle box;
- `analysis-run002/counterfactual_receiver_comparison.mp4`: synchronized 3 s
  no-actor/far/near/adjacent comparison;
- `analysis-run002/metric_audit.json`: machine-readable metrics and judgments;
- `manifest.json`: model, input, run and preprocessing provenance;
- `*_predictions.json`: frame-level receiver outputs and associations.

## Validation

- one-frame and three-frame temporal smoke runs completed on the RTX 4090;
- all six formal sequences completed without temporal-state failure;
- formal video passes `ffprobe` with duration 3.0 s;
- repository test suite: 53 tests passed, including three new adapter/metric
  tests.
