# Codex Next Task — Audit Metrics and Expand Bounded Scene Coverage

> Read this file first when resuming HUGSIM work.

## Project Objective

Develop a credibility-validation method for log-driven simulators.

This project uses the broad definition:

> A log-driven simulator constructs an interactive environment from real
> road-driving capture sequences and generates counterfactual closed-loop
> evolution. Exact log replay is not required.

HUGSIM is the first case study, not the final research target. It is a
real-driving-sequence reconstruction-based, counterfactual closed-loop neural
simulator.

Durable guiding questions:

> HUGSIM 提供给智驾系统的任务相关信息，是否与现实一致到足以产生可信的感知、决策和闭环结果？

> 同一个智驾模型面对现实数据和对应的仿真数据，是否形成相近的感知、风险排序、规划和控制行为？

The receiver may be an AD model/stack or a human driver in a
human-in-the-loop study. Use the receiver class that matches the intended test
domain; human and machine evidence are complementary rather than
interchangeable.

The long-term credibility metric is planned around a four-layer evidence
chain: log reproduction, sensor consistency, task-level consistency, and
closed-loop outcome credibility. That is a future metric-research structure,
not the current grading scheme.

## Read First

```text
docs/research_guiding_principles.md
docs/hugsim_matched_receiver_validation_plan.md
docs/hugsim_credibility_decision_rules.md
docs/hugsim_smoke_test_plan.md
docs/runs/hugsim_source_anchor_gate_001.md
docs/runs/hugsim_source_anchor_gate_001.json
docs/runs/hugsim_counterfactual_001.md
docs/runs/hugsim_horizon_factorial_001.md
docs/runs/hugsim_horizon_factorial_001_audit.json
docs/runs/hugsim_near_cut_in_001.md
docs/runs/hugsim_near_cut_in_001_audit.json
docs/runs/hugsim_ad_receiver_readiness_001.md
docs/runs/hugsim_ad_receiver_readiness_001.json
docs/runs/hugsim_matched_pose_manifest_001.md
docs/runs/hugsim_matched_pose_manifest_001.json
```

## Corrected State

The old 6-second lead-plus-cut-in run reported:

```text
TTC first failure: 4.75 s
NC first failure: 5.75 s
```

Those risk events are now `rejected`.

HUGSIM's saved scoring trajectory contains five future waypoints at 0.5-second
spacing, so each metric frame needs 2.5 seconds of future actor history. The
6-second run is valid only through 3.5 seconds. Its failures occur after that
point, where the scorer repeats the last actor box.

The 6-second run and a 9-second extension have an exact common
state/action/plan prefix, yet all old failures disappear in the extension.
This correction prevents an invalid metric interpretation. Keep it as a
run-level engineering validity note, not as a central theoretical finding.

## Corrected 2×2 Actor-Removal Result

Nine-second runs:

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s
artifacts/hugsim_contrast/scene-0383-lead-only-00-run002-9s
artifacts/hugsim_contrast/scene-0383-cut-in-only-00-run002-9s
artifacts/hugsim_contrast/scene-0383-multicar-cut-in-00-run002-9s
artifacts/hugsim_contrast/scene-0383-horizon-factorial-report-run002
```

Horizon-valid window, 0.25–6.5 seconds:

| Condition | NC | TTC | PDMS |
|---|---:|---:|---:|
| no actors | 1.000 | 1.000 | 1.000 |
| lead only | 1.000 | 1.000 | 1.000 |
| far cut-in only | 1.000 | 1.000 | 1.000 |
| lead + far cut-in | 1.000 | 1.000 | 1.000 |

The far cut-in crosses the centerline but retains about 4.195 meters of
minimum 2D oriented-footprint clearance. It is a negative control, not a
credible risk event.

## Near-Distance Single-Shot Result

Parameters were fixed before execution, but the scenario was not formally
committed or externally preregistered before the run. Describe it as
**pre-specified single-shot**, not formal preregistration.

```text
artifacts/hugsim_contrast/scene-0383-near-cut-in-00-run001-9s
artifacts/hugsim_contrast/scene-0383-near-cut-in-report-run001
artifacts/hugsim_contrast/scene-0383-near-cut-in-audit-run002
```

Horizon-valid result:

| Condition | NC | TTC | PDMS |
|---|---:|---:|---:|
| no actors | 1.000 | 1.000 | 1.000 |
| far cut-in control | 1.000 | 1.000 | 1.000 |
| near cut-in | 1.000 | 0.1154 | 0.3681 |

Event evidence:

```text
centerline crossing: 3.917 s
minimum 2D oriented-footprint clearance: 0.730 m at 5.5 s
horizon-valid TTC failures: 23 frames, first at 1.0 s
failed-event actor IDs: [0]
tail padding used: false
runtime collision: false
```

Accepted narrow subclaims:

- strict input/state/action/plan pairing;
- continuous actor0 motion and centerline crossing;
- positive-clearance 2D close pass;
- actor0-specific HUGSIM internal TTC surrogate response inside the
  complete-future-history window;
- internal RGB/semantic/depth co-movement.

The overall segment remains `down-weighted`. Actual collision, physical TTC
value, AD-agent response, and global HUGSIM credibility remain `rejected` or
unsupported. Real traffic validity and sensor truth remain down-weighted or
not established.

Read `rejected` at claim level. A rejected behavior/metric claim may coexist
with an accepted diagnostic finding. In the current audits:

- the old 6-second risk claim is rejected, while the tail-padding defect is
  retained as its technical invalidation reason;
- timestamp-zero/YAML equality is rejected, while the reset phase-offset
  finding is accepted;
- physical TTC interpretation is rejected, while the binary-surrogate
  construct finding is accepted;
- AD-agent and global claims are rejected because they were not tested or
  exceed scope, so they imply no HUGSIM capability failure.

## Runtime and Analysis Improvements

- The plan writer can use the same `--max-steps` value as the runner and still
  receive the final `Done` handshake.
- The runner returns success only when every requested step completes and
  scoring succeeds.
- Audit summaries record configuration and runtime script hashes.
- Pair analyzers fail closed on commit, config, step count, timestamps, plans,
  and selected report provenance.
- NC/TTC conclusions fail closed when the event uses incomplete future actor
  history.
- A fail-closed claim/finding semantics validator checks every rejected claim,
  diagnostic link, decision label, repository evidence file, and external
  reference syntax/commit alignment.
- The AD receiver readiness inventory scans all local HUGSIM scene metadata
  and fails closed before any real-vs-sim receiver claim.
- The matched-pose manifest builder selects the first reader-derived test
  candidate and records the exact metadata intrinsics, camera-to-world poses,
  native dynamic policy, and bounded camera-only receiver contract. It fails
  closed while source RGB or exact simulation renders are absent.
- Fifty-three unit tests pass.

## Immediate Goal

Do not run another same-scene cut-in parameter adjustment. Independent design,
evidence, and reproducibility reviews agreed that the pre-specified stop
criterion was met and another treatment would be post-hoc result chasing.

The source-anchor availability gate is now implemented. For `scene-0383`, it
is blocked because the released minimized scene has 1080 calibration/pose
records but none of the referenced real RGB files or original nuScenes source
tokens. Existing closed-loop observations also use a non-identical camera
template and must not be called matched-pose renders.

The AD receiver readiness inventory confirms the local machine currently has
one HUGSIM scene (`scene-0383`), zero valid real RGB files out of 1080
referenced records, incomplete source sample identity, and no source-anchor-
ready scene. It did not generate a new HUGSIM scenario or rollout; it is an
availability and pairing result. Therefore no AD real-versus-sim input
comparison is established locally yet.

The first matched-pose manifest is now prepared for `scene-0383` frame
`00004` at `t=0.333595s`, which is the first reader-derived test candidate
under the inspected local split rule. It records six exact metadata
intrinsics, `camtoworld` matrices, resolutions, native dynamic IDs, and a
`camera_only_rgb_single_frame_v0` receiver contract. The gate remains
`blocked_source_anchor`: no real RGB, exact render, pairing-integrity pass, or
receiver-equivalence result exists yet.

Because the local HUGSIM-related directories still lack source RGB and source
identity, do not keep blocking the active work on scene-0383 source recovery.
The latest material HUGSIM result is now:

```text
docs/runs/hugsim_ad_receiver_proxy_001.md
artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001
```

It generated new far-front, close-front, adjacent-lane, and multicar-merge
rollouts, then fed CAM_FRONT semantic/depth to a fixed
`simulator_internal_task_receiver_proxy_v0`. Three causal direction checks
were `accepted` under that narrow proxy: closer same-lane vehicle > far
same-lane vehicle, same-lane near > adjacent-lane near, and multicar merge >
far-front control. Overall evidence remains `down-weighted` because this is
not a real AD-agent response, not a matched real-sim comparison, and not global
HUGSIM credibility evidence.

The latest material receiver result is now:

```text
docs/runs/hugsim_camera_detector_001.md
artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001
```

A frozen torchvision Faster R-CNN MobileNetV3 COCO detector consumed only
CAM_FRONT RGB from the same five runs. It reproduced the distance,
lane-relation, and multicar causal directions through boxes, confidence,
image-plane tracking, and risk-ranking proxies. Overall evidence remains
`down-weighted` because this is a generic single-camera detector, not a full
AD stack, planning/control result, matched real-sim comparison, or global
HUGSIM credibility evidence. A useful boundary finding was also accepted:
the no-actor baseline still has background/native detections in 4/37 frames,
so a real receiver input is not cleanly zero even when no actor is injected.

The latest cross-receiver agreement result is now:

```text
docs/runs/hugsim_receiver_agreement_001.md
artifacts/hugsim_receiver_agreement/scene-0383-receiver-agreement-run002
```

It compares the semantic/depth proxy and RGB detector on the same five
rollouts using center-path task signals. All receiver-agreement checks were
`accepted`: close-front > far-front, close-front > adjacent-near, multicar >
far-front, and run-level center-path rank agreement with Spearman = 1.0. The
no-actor background/native detection boundary was also retained. Overall
evidence remains `down-weighted` because agreement is still simulator-internal
and not matched real-sim or full AD behavior.

Source-data handling is now intentionally lightweight. The HUGSIM-related
local directories currently known for this project are `/home/yawei/HUGSIM`,
`/home/yawei/HUGSIM_assets`, and this repository's `artifacts/`. They have
been checked for the released scene source images. `/home/yawei/HUGSIM_assets`
now contains reconstructed packages for `scene-0383`, `scene-0041`, and
`scene-0138`, but none contains the corresponding real camera image files or
complete immutable source identity. If a future local directory is supplied,
run the same simple inventory; if real RGB and source identity are absent, do
not spend more effort on source recovery in this phase.

The next material HUGSIM action is Route B: audit the measurements before
adding another receiver, scenario, or response curve. Use
`docs/hugsim_metric_evidence_map.md` as the current evidence map. Treat RGB,
semantic, and depth as simulator outputs under audit; semantic/depth are not
independent ground truth. Practical steps are:

1. qualify each existing geometry, rendering, perception, task, and HUGSIM
   score metric by construct, provenance, reference independence, receiver
   contract, causal sensitivity, and strongest allowed claim;
2. retain the existing proxy/detector/cross-receiver results as metric-audit
   material and correct any interpretation that promotes perception signals
   to planning, control, or simulator-credibility claims;
3. obtain the licensed nuScenes source images and the ASAP
   `interp_12Hz_trainval` mapping for `scene-0383`;
4. render split-derived test candidate poses using their exact metadata
   intrinsics and `camtoworld`, and verify checkpoint training provenance
   before calling them genuinely held out;
5. freeze a bounded camera-only AD receiver input contract and feed matched
   real/sim observations to the same AD receiver;
6. only after the matched factual comparison, use controlled distance, lane,
   occlusion, or motion interventions and then progress to planning/control.

Two additional normal-scene carriers have now been collected and executed:

- `scene-0041`: signalized intersection / cross-street geometry;
- `scene-0138`: curved school-zone road with roadside objects, pedestrians,
  vegetation, and strong occlusion conditions.

Their first/middle/last six-camera previews and bounded run records are in
`docs/runs/hugsim_scene_collection_001.md`. They extend the conditions available
to the metric audit; they do not constitute real-sim evidence, and the current
rollouts do not test injected multi-actor interaction.

The first normal-scene sensor/receiver audit is now complete. It accepted the
bounded array/calibration contract and depth numerical validity, but retained
cross-modal boundary co-variation as `down-weighted`. More importantly, it
rejected cross-scene robustness of the existing center-path risk proxy: the
`scene-0041` peak was caused by a false car detection on the ego hood/lower
image, and `scene-0138` produced two roadside false car detections. See
`docs/runs/hugsim_normal_scene_sensor_audit_001.md`.

The first driving-domain 3D receiver baseline is now complete:

```text
docs/runs/hugsim_sparse4d_receiver_baseline_001.md
docs/runs/hugsim_sparse4d_receiver_baseline_001_audit.json
artifacts/sparse4d_receiver_baseline/baseline-and-response-run001
```

A frozen official Sparse4Dv3 R50 consumed only HUGSIM six-camera RGB and
calibration. It was not fine-tuned on HUGSIM and did not receive HUGSIM
semantic/depth. Controlled vehicle sensitivity, near/far ordering, and
same-lane/adjacent-lane ordering are `accepted`. Absolute actor XY agreement is
`down-weighted`: median center errors are 2.56 m (far), 4.24 m (near), and
3.80 m (adjacent). The result supports bounded task-response and relation-
direction evidence, not real-sim equivalence or global simulator validity.

The immediate next action is no longer to add another receiver. First audit
the material absolute-position bias:

1. verify the HUGSIM vehicle/camera/Sparse4D coordinate and calibration
   transform with synthetic projected points and per-camera overlays;
2. keep HUGSIM actor-state Z outside the reference until its camera-projectable
   convention is established;
3. manually label a small, fixed set of native visible vehicles and nuisance
   regions in `scene-0041` and `scene-0138`, so normal-scene Sparse4Dv3 outputs
   can become precision/error evidence instead of unlabelled response counts;
4. only after those checks decide whether the remaining bias is more consistent
   with receiver domain shift or simulator/adapter geometry;
5. retain the source-anchor gate for eventual matched real-sim Sparse4Dv3
   comparison.

Do not use the 2 m or 4 m diagnostic lines as final credibility thresholds, and
do not add more controlled vehicles merely to produce another response curve.

Do not independently install a full AD stack, run the full benchmark, expand to
OmniDreams/Cosmos, or design the final four-layer credibility metric.

## Guardrails

- Never accept NC/TTC from a rollout tail without a future actor state for
  every scored planned waypoint.
- Preserve old raw outputs but mark superseded interpretations explicitly.
- Treat HUGSIM TTC as a binary internal surrogate, not physical
  time-to-collision.
- Do not call a scripted ConstantPlanner diagonal a validated real merge.
- Do not treat one duplicated vehicle identity as actor diversity.
- Do not treat common-renderer RGB/semantic/depth agreement as real-sensor
  correctness.
- The deterministic plan writer is a loop enabler, not an AD agent.
- Use exactly `accepted`, `down-weighted`, and `rejected`.
- Never interpret `rejected` without its tested flag and rejection basis.
