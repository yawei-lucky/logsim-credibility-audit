# HUGSIM supporting receiver qualification 001 — Sparse4Dv3 R50

Date: 2026-07-22

## Purpose

Decide whether the already integrated Sparse4Dv3 R50 can be used as a bounded
supporting receiver in the next counterfactual risk-causality experiment. This
qualifies a measurement role; it does not validate HUGSIM and does not promote
Sparse4Dv3 to ground truth.

## Frozen identity and external task basis

- source: official `HorizonRobotics/Sparse4D` checkout at commit
  `249ffbb695f4e9db628d953e2bf6d36de04bbb69`;
- official R50 checkpoint SHA-256:
  `5beed4d4933ca6448d72586b0f8812863574289ff3c4192de71dc9f46a42f0ed`;
- official config SHA-256:
  `22ae67545157a43786356b1e7c4f9fc50076ab29062acef71f4163a3609626dc`;
- model task: temporal six-camera 3D object detection and tracking;
- training/evaluation domain: nuScenes camera data;
- official release reports for the R50 256x704 validation model: NDS 0.5637,
  mAP 0.4646, AMOTA 0.477, AMOTP 1.167, and 456 ID switches;
- primary sources: [official repository](https://github.com/HorizonRobotics/Sparse4D)
  and [Sparse4Dv3 paper](https://arxiv.org/abs/2311.11722).

These benchmark values are author-reported external evidence, not a local
nuScenes reproduction. They qualify the model family for detection/tracking on
its source benchmark; they do not provide a per-scenario HUGSIM error bound or
a calibrated risk threshold.

## Input and runtime compatibility

The local receiver consumes only:

- six HUGSIM RGB arrays;
- camera intrinsics and extrinsics;
- timestamp and ego transform needed by the temporal model.

HUGSIM semantic and depth are excluded. Camera order matches the official
nuScenes converter. HUGSIM's 4 Hz stream is sampled at 2 Hz. Each 450x800 image
is resized to 396x704 and bottom-cropped to 256x704; the same transform is
applied to the projection matrix. Unit tests verify this half-resolution form
preserves the official crop geometry.

The local runtime disables the optional custom deformable CUDA operator and
uses the repository's PyTorch fallback. The checkpoint and model parameters
are unchanged, but numerical equivalence to the official benchmark runtime has
not been independently established. Physical equivalence of HUGSIM calibration
to nuScenes calibration is also not established.

## Output semantics and qualified use

Sparse4Dv3 supplies class, confidence, 3D centre/size/yaw/velocity, and temporal
instance identity. The HUGSIM adapter additionally performs a custom nearest-XY
association to the controlled actor; that association is an audit operation,
not a native Sparse4D output.

| Candidate use | Decision | Basis and boundary |
|---|---|---|
| Frozen model/checkpoint identity and software input contract | `accepted` | hashes, camera order, preprocessing, excluded modalities, rate, and raw inputs are recorded |
| External basis as a real-data-trained detection/tracking receiver | `accepted` | official nuScenes training and benchmark evidence exists; benchmark performance is author-reported |
| Vehicle presence and near/far or same/adjacent ordinal response | `accepted` | known-control HUGSIM experiments produced causal sensitivity and no observed ordinal reversal in available comparisons |
| Short-window instance continuity | `down-weighted` | tracking is a native model task, but current HUGSIM evidence is small and includes a missing association |
| Absolute metric position, size, velocity, or calibrated uncertainty | `down-weighted` | HUGSIM runs show material position/scale bias; no independent HUGSIM 3D truth or local real-data error envelope exists |
| Risk probability, braking need, planner action, or safety outcome | `rejected` | these are not Sparse4Dv3 output constructs and exceed the available evidence |
| Sparse4Dv3 as the sole truth source for HUGSIM validity | `rejected` | domain shift, calibration adaptation, nuisance response, and shared observation dependence remain unresolved |

## Known failure modes and uncertainty carried forward

- domain shift from real nuScenes imagery to reconstructed HUGSIM RGB;
- calibration/coordinate adaptation and vertical-convention uncertainty;
- scale-depth ambiguity and material metric-centre bias in existing runs;
- nuisance responses on ego hood, road edge, vegetation, and reconstruction
  artifacts in the fixed normal-scene sample;
- detection or association unavailability, which must remain unavailable and
  must never be imputed as safe;
- score threshold 0.2 is the official tracking threshold reused as an operating
  point, not a calibrated HUGSIM confidence boundary;
- benchmark average metrics do not supply a scenario-specific acceptance
  margin for the next counterfactual.

## Qualification gate

`accepted` for one narrow role:

> Sparse4Dv3 R50 may be used as a supporting receiver to test whether vehicle
> presence, longitudinal/lateral relation, short temporal identity, and a
> predeclared ordinal conflict direction survive transport through HUGSIM's
> six-camera RGB interface.

It must be paired with independently recomputed state geometry and fail-closed
coverage reporting. It may not determine physical risk truth, supply a real
safety threshold, adjudicate absolute distance by itself, or support a
planning/control/closed-loop claim.

The strongest permitted HUGSIM statement is:

> Within a declared designed range, HUGSIM RGB supplies enough vehicle
> information for this frozen real-data-trained receiver to preserve a
> predeclared ordinal task relation on every available observation.

This qualification is sufficient to design CF-R, but not to interpret a
receiver response as a final AD risk decision.

## Local evidence reused

- `docs/runs/hugsim_sparse4d_receiver_baseline_001.md`;
- `docs/runs/hugsim_sparse4d_cross_scene_001.md`;
- `docs/runs/hugsim_sparse4d_normal_scene_annotation_001.md`;
- `docs/runs/hugsim_ordinal_metamorphic_001.md`;
- `artifacts/sparse4d_receiver_baseline/baseline-and-response-run001/manifest.json`.
