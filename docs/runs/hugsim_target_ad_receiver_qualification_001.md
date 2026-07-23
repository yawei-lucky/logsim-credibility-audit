# HUGSIM target AD receiver qualification 001 — route decision

Date: 2026-07-22

## Decision

Use **SparseDrive-S Stage2** as the first target AD receiver. It passes the
pre-integration selection gate for one bounded role: consume the six-camera
stream and produce a native open-loop ego planning trajectory. This does not
qualify SparseDrive as truth and does not yet produce HUGSIM planning evidence.

Runtime update (2026-07-23): the official checkpoint now loads strictly and
emits finite native outputs on a bounded four-frame HUGSIM sequence through a
tracked PyTorch compatibility path. Reset reproducibility also passed. The
remaining gate is the virtual-frame, 10-D ego-status and equal-warm-up input
contract, not installation. See
`docs/runs/hugsim_sparsedrive_runtime_smoke_001.md`.

Do **not** make a full real-nuScenes ground-truth rerun of Sparse4Dv3 the next
blocking task. Sparse4Dv3 remains a supporting detection/tracking probe. A
small real-GT check becomes necessary only if a later claim depends on its
absolute position, velocity, identity error, or if another module directly
uses its outputs. It is also required before its ordinal response defines an
externally valid acceptance boundary, receiver uncertainty range or bounded
real-world fitness claim. SparseDrive is a self-contained model and does not
consume the separately integrated Sparse4Dv3 predictions.

## Why this route

| Candidate | Native downstream output | Fit to current six-camera data | Decision |
|---|---|---|---|
| SparseDrive-S Stage2 | agent motion predictions, planning scores, candidate plans and final ego plan | nuScenes six-camera contract; Sparse4D lineage makes the first adapter relatively direct | selected first |
| VAD-Tiny | vectorized agents/maps and ego plan | compatible task, but a separate BEVFormer/MapTR-era stack | retain as later architecture cross-check |
| UniAD Stage2 | tracking, mapping, motion, occupancy and planning | complete but substantially heavier and more stateful | defer |
| SparseDriveV2 | dense candidate-trajectory scoring | current release targets NAVSIM/Bench2Drive rather than the present nuScenes/HUGSIM contract | defer despite being newer |

SparseDrive is the smallest useful step beyond perception because its released
decoder natively returns `planning_score`, all candidate `planning` trajectories
and `final_planning`. Its collision-aware re-score consumes its own detections
and agent-motion predictions before selecting the final plan. It does not expose
a calibrated risk probability, brake/steer command, or an explicit single
`critical_object_id`; those constructs must not be invented from confidence or
distance.

SparseDrive shares the Sparse4D sparse-perception lineage. It is therefore a
good first target planner but **not** an independent second perception ruler.
If the first planning result matters, VAD-Tiny should later test whether the
direction survives a different architecture.

Primary sources:

- [SparseDrive official repository](https://github.com/swc-17/SparseDrive)
  and [paper](https://arxiv.org/abs/2405.19620);
- [VAD official repository](https://github.com/hustvl/VAD);
- [UniAD official repository](https://github.com/OpenDriveLab/UniAD);
- [SparseDriveV2 official repository](https://github.com/swc-17/SparseDriveV2)
  and [paper](https://arxiv.org/abs/2603.29163).

The official SparseDrive release reports nuScenes detection, tracking, mapping,
motion and open-loop planning metrics and provides a Stage2 checkpoint. These
are author-reported external task evidence, not a local reproduction. The
repository also states that its released collision evaluation was corrected
after omitted collision cases were found. Consequently, its collision rate is
benchmark evidence, not a safety truth source for HUGSIM.

## Native input and temporal contract

The released Stage2 test pipeline requires:

- six RGB images, image size and camera projection matrices;
- timestamp and global/ego transforms for temporal memory;
- a nuScenes LiDAR-frame 3D reference convention for projection, global
  transforms, ground height and predicted boxes, despite camera-only sensing;
- a four-frame history including the current frame;
- a 10-value `ego_status`: ego-frame acceleration XYZ, angular velocity XYZ,
  velocity XYZ and steering angle;
- one of three right/left/straight planning-conditioning labels. In the
  official converter, `gt_ego_fut_cmd` is derived offline from the endpoint of
  the future ego trajectory; it is not an ordinary online navigation command.

The model is camera-only at inference (`use_lidar=False`, `use_map=False`,
`use_external=False`). HUGSIM semantic and depth must remain excluded. The
released small config uses 256x704 images, six cameras, six future ego-plan
steps and collision-aware re-scoring.

### Existing CF-R input feasibility

A bounded inspection of the existing slow/nominal/fast CF-R sources found:

- 37 observations per condition at 4 Hz from `t=0` through `9 s`;
- all six RGB cameras and camera parameters at every observation;
- timestamp, ego pose/rotation, velocity, steering, acceleration, steering
  rate and HUGSIM command in every `infos.pkl` record;
- `command=2` in all records. It can be frozen as SparseDrive's straight label
  for this paired experiment, but the two fields do not yet have a validated
  deployment-equivalent meaning;
- the recorded ego-state sequence and camera parameters are exactly identical
  across slow, nominal and fast. Only the controlled actor evolution differs.

This is a suitable paired-input basis after 2 Hz sampling. It is not yet a
complete SparseDrive input contract. HUGSIM records scalar vehicle values,
whereas SparseDrive was trained with the 10-value vector above. Ego-frame
components, signs, units and finite-difference derivation from pose history must
be specified and checked before inference. HUGSIM camera/ego parameters must
also be mapped into an explicit virtual LiDAR/ego reference frame with audited
axes, origin, units, ground convention, projections and global transforms.
Temporal memory must reset at the start of each independent condition.

The existing `sparse4d-audit` environment is not directly runnable for
SparseDrive: the shared MMCV/MMDetection versions are close, but `flash_attn`
and an importable `mmdet3d` are absent. Integration must use a pinned isolated
environment rather than mutating the working Sparse4Dv3 receiver.

## Qualification decisions

| Candidate use or claim | Decision | Boundary |
|---|---|---|
| Proceed with a pinned SparseDrive-S Stage2 adapter | `accepted` | native planning outputs, official code/checkpoint and a compatible six-camera basis exist |
| Existence of a published real-data task basis | `accepted` | official nuScenes benchmark evidence and a released checkpoint exist |
| SparseDrive as a locally qualified project receiver | `down-weighted` | published results are author-reported; the local runtime and adapter have not passed |
| Current HUGSIM input-contract completeness | `down-weighted` | RGB, calibration, pose, command and paired timing exist; virtual LiDAR frame, conditioning-label semantics, 10-D `ego_status` and reset remain unresolved |
| Native final trajectory as an admissible target-output construct | `accepted` | source code exposes it directly; no HUGSIM response evidence exists yet |
| Explicit critical-object identity or calibrated risk probability | `rejected` | neither is a released native output |
| Brake, steering control or physical closed-loop outcome | `rejected` | SparseDrive Stage2 outputs an open-loop trajectory, not actuator commands or a vehicle response |
| SparseDrive/Sparse4D alone as proof that HUGSIM is credible | `rejected` | shared observation dependence, domain shift and model-family dependence remain |

The selection gate is therefore complete, while the receiver is not yet
qualified to judge a HUGSIM experiment. The next gate is adapter/runtime
qualification, not another model comparison.

## Sparse4Dv3 real-GT decision rule

| Intended use | Is local real-GT testing needed first? |
|---|---|
| Preserve its current vehicle-presence and ordinal supporting role | no; retain the existing bounded qualification |
| Treat its metric XYZ, velocity, identity or uncertainty as an error-bounded ruler | yes; use the same local runtime on a preregistered nuScenes validation subset |
| Use its ordinal response to set an external acceptance boundary, uncertainty range or bounded real-world fitness claim | yes; the current internal known controls are insufficient |
| Feed its boxes into a hand-built risk/planning module | yes; otherwise receiver error is silently inherited by the target result |
| Run self-contained SparseDrive on RGB | no; qualify SparseDrive itself instead |
| Prove HUGSIM credible | no; even a successful Sparse4D real-GT test cannot prove that |

If this conditional branch is triggered, the minimum useful test is not a full
benchmark rerun. It should check vehicle coverage, coordinate adaptation,
longitudinal/lateral ordering, short identity continuity, position error and
jitter on a fixed small official validation slice using the exact local
preprocessing/runtime. No local raw nuScenes images, annotations or generated
infos are currently available, so expanding into data acquisition now would
not advance the selected planning construct.

## Next executable gate

Implement only the SparseDrive-S Stage2 input adapter and runtime smoke test:

1. without downloading a model, first define and unit-check camera order,
   virtual LiDAR/ego reference frame, transforms, 2 Hz sampling, 10-D
   `ego_status`, the straight future-trajectory conditioning label and per-run
   temporal reset;
2. only after that passes, pin source commit, config and checkpoint hashes in
   an isolated environment;
3. load the unchanged checkpoint and preserve the native `planning_score`,
   candidate `planning`, `final_planning` and agent-motion outputs;
4. run one short sequence only to verify shapes, timestamps, finite values and
   deterministic reset; do not yet interpret the trajectory;
5. preregister the paired slow/nominal/fast planning-direction test only after
   the contract gate passes.

The first experiment will ask whether stronger closure changes the frozen
planner in the expected task direction: less longitudinal progress or an
explicit clearance-increasing lateral alternative, with the conditioning label
and ego history fixed. It must report unavailable output, mode switches and
reversals.
It may support at most:

> Under a fixed and audited input contract, the designed HUGSIM conflict change
> caused this frozen real-data-trained planner's native trajectory to change in
> the declared direction over the tested range.

It cannot establish real-world safety, physical TTC, correct control action,
closed-loop credibility or general HUGSIM fitness.
