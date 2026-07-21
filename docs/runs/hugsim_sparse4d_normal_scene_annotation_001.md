# HUGSIM Sparse4Dv3 normal-scene annotation audit 001

## Purpose

Replace unlabelled normal-scene response counts with a fixed, inspectable
sample that distinguishes Sparse4Dv3 responses supported by visible simulated
RGB targets from responses on road edges, vegetation, camera boundaries, and
reconstruction blur.

This is a receiver/nuisance audit inside the simulated visual world. It is not
a real-versus-simulation comparison and does not treat HUGSIM semantic, depth,
or internal actor state as truth.

## Frozen protocol

- scenes: `normal_0041` and `normal_0138`;
- receiver: unchanged official Sparse4Dv3 R50 nuScenes weights;
- sample positions: first, middle, and last of the 37 receiver frames;
- inclusion: every prediction with score >= 0.2, all predicted classes;
- review input: up to two HUGSIM RGB cameras with the largest visible
  projection area for the predicted 3D box;
- review labels: `supported_target`, `class_mismatch`, `nuisance`, or
  `uncertain`;
- selection was frozen before human labels, and every source RGB array is
  linked by SHA-256 in the manifest.

The label answers only: **does a human-visible target in the rendered RGB
support this sampled receiver response?** The sample is detection-conditioned,
so it cannot reveal missed objects or estimate recall.

## Result

| Scene | Sampled responses | Supported target | Nuisance | Support fraction |
|---|---:|---:|---:|---:|
| `scene-0041` | 3 | 1 | 2 | 33% |
| `scene-0138` | 11 | 6 | 5 | 55% |
| Total | 14 | 7 | 7 | 50% |

Class-level observations in this fixed sample:

- the single truck response has a visible vehicle inside its projected box;
- six of eight pedestrian responses have visible pedestrian support;
- all three car responses are nuisance responses on road/edge/blur regions;
- both bus responses are nuisance responses on vegetation/reconstruction
  regions.

These class ratios are diagnostic descriptions of 14 selected responses, not
class performance estimates. In particular, the sample is too small and too
sparsely sampled to represent the scene ODD.

## Evidence decisions

- `accepted`: the sample identity, inclusion rule, receiver input linkage, and
  the reproducible fact that the fixed sample contains seven visibly supported
  and seven nuisance responses;
- `rejected`: the narrow claim that all score >= 0.2 normal-scene responses in
  this fixed sample correspond to a visible target. This claim was tested and
  is contradicted by the seven nuisance labels; it links to the accepted
  diagnostic finding `normal_scene_visible_nuisance_responses` below;
- `down-weighted`: normal-scene receiver semantic support as evidence of
  simulator usefulness, because the review uses HUGSIM-rendered RGB, only six
  sampled scene-times, one human review pass, and no matched real reference.

No claim is made about receiver recall, ODD-wide precision, real-sensor
correctness, planning behavior, or HUGSIM's overall credibility.

Rejected-claim context:

| Field | Value |
|---|---|
| `tested` | `true` |
| `rejection_basis` | `contradicted_by_evidence` |
| `reason` | 7 of 14 frozen responses have no visible matching target in the reviewed RGB views |
| `diagnostic_finding` | `normal_scene_visible_nuisance_responses` |
| evidence | `annotation_atlas.png`, `labelled_nuisance_summary.json`, and the tracked annotation JSON |

Diagnostic finding `normal_scene_visible_nuisance_responses`:

| Field | Value |
|---|---|
| component | Sparse4Dv3 normal-scene response baseline |
| expected | A response count used as visible semantic support should be backed by a matching visible target |
| observed | Seven frozen responses lie on road/edge/vegetation/reconstruction regions without a matching visible target |
| expectation_met | `false` |
| decision | `accepted`, limited to the frozen sample and the presence of nuisance responses; root cause is not assigned |
| implication | Raw response count/persistence cannot be used alone as a simulator-validity indicator |

## What this changes

The earlier response-count baseline showed that Sparse4Dv3 reacts in the two
normal scenes. This audit now shows that raw count/persistence is not a safe
standalone indicator: in the fixed sample, half of the responses have no
visible target support. At the same time, the supported truck and pedestrian
responses show that the receiver is not reacting only to artifacts.

Therefore nuisance robustness remains a required member of the task-level
indicator set. The next threshold cannot be chosen from this 50% sample result;
it must be tied to a downstream AD decision margin and a declared critical-
object/risk-order task.

## Executed command

```text
/home/yawei/miniforge3/envs/sparse4d-audit/bin/python \
  scripts/audit_sparse4d_normal_scene_annotations.py \
  --experiment artifacts/sparse4d_receiver_baseline/baseline-and-response-run001 \
  --annotations docs/runs/hugsim_sparse4d_normal_scene_annotations_001.json \
  --output artifacts/sparse4d_receiver_baseline/normal-scene-annotation-run003
```

The output directory is immutable for this completed run. It contains:

- `annotation_manifest.json`;
- `annotation_atlas.png`;
- `labelled_nuisance_summary.json`;
- `labelled_nuisance_summary.png`.

The annotation source is
`docs/runs/hugsim_sparse4d_normal_scene_annotations_001.json`.
For a rerun, use a new output directory rather than `run003`.
