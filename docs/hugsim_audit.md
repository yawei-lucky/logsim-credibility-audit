# HUGSIM Credibility Audit

> Status update (2026-07-19): source discovery is complete, the simulator-side
> closed-loop chain has run locally, and the first counterfactual segment is
> `down-weighted` after third-party review. Narrow state/action pairing and
> internal-geometry response subclaims are `accepted`; sensor-level E2E
> credibility is not established. The four-layer evidence chain belongs to
> future credibility-metric research and is not used to grade this run.
>
> The detailed sections below preserve the first-pass extraction and should be
> read as historical pipeline analysis where their old status wording differs.
>
> Scope: audit HUGSIM as a runnable 3DGS-based log-driven closed-loop simulator, not a general autonomous-driving simulator survey.

## Source Availability Gate

### Gate Status

**First-pass status: complete for Phase 1 source discovery.**

HUGSIM has enough public artifacts to be treated as a runnable Phase 1 audit target: paper, project page, code repository, license, sample data link, released scene/vehicle/scenario asset link, closed-loop runtime entry point, Gymnasium environment, AD-client interface, and metric implementation code are all publicly inspectable.

This does **not** mean HUGSIM's closed-loop results are automatically credible. It means the project has enough public artifacts to proceed from paper-only review to implementation-level audit and smoke-test planning.

### Availability Table

| Item | Status | Evidence | Audit Consequence |
|---|---|---|---|
| Paper | Available | https://arxiv.org/abs/2412.01718 | Paper claims can be cited and audited as reported evidence. |
| Project page | Available | https://xdimlab.github.io/HUGSIM/ | Can inspect official claims, demos, architecture overview, benchmark claims, and links to paper/code. |
| Code repo | Available | https://github.com/hyzhou404/HUGSIM | Can inspect implementation structure, installation, reconstruction, scene export, GUI, closed-loop runtime, Gym env, and metrics. |
| License | Available: MIT | `LICENSE` in official repository | Code reuse is governed by MIT license, but datasets and third-party assets retain their own access/licensing constraints. |
| Sample data | Available | https://huggingface.co/datasets/hyzhou404/HUGSIM/tree/main/sample_data | Good first artifact for smoke-test setup before full dataset conversion. |
| Released scenes / vehicles / scenarios | Available / partly restricted | https://huggingface.co/datasets/XDimLab/HUGSIM | Public release exists, but README notes some RealADSim competition scenarios are private; smoke tests should use public assets only. |
| Original datasets | Restricted / external | KITTI-360, Waymo, nuScenes, PandaSet | Full training/evaluation reproduction requires satisfying each dataset's access and license requirements. |
| Data preparation scripts | Available | `data/README.md`, `data/kitti360`, `data/waymo`, `data/nusc`, `data/pandaset` | Dataset conversion is inspectable; still requires external datasets and model checkpoints such as InverseForm. |
| Reconstruction runtime | Available | `train_ground.py`, `train.py`, dataset configs | New reconstruction is possible in principle, but Phase 1 should avoid training from scratch. |
| Scene export runtime | Available | `eval_render/export_scene.py`, `eval_render/convert_scene.py`, `eval_render/convert_vehicles.py` | Export/convert path is inspectable and relevant for public scene-based smoke testing. |
| Simulator runtime | Available | `closed_loop.py`, `configs/sim/*`, `sim/` | Closed-loop runtime is inspectable; actual execution depends on local paths, CUDA, public assets, and AD-client setup. |
| Gym environment | Available | `sim/hugsim_env/envs/hug_sim.py` | Observation/action spaces and state update logic can be audited directly. |
| Policy agent / AD client | Available / external dependency | README mentions UniAD_SIM, VAD_SIM, and NAVSIM / LTF-style clients | Closed-loop evaluation depends on external AD clients; simulator credibility should be separated from policy-agent performance. |
| Orchestrator | Available | `closed_loop.py` | It launches AD clients, creates Gym env, writes observations to pipe, reads planned trajectory, converts trajectory to controls, steps env, stores outputs, and invokes metrics. |
| Evaluation scripts / metrics | Available | `sim/utils/score_calculator.py` | NC, DAC, TTC, comfort, PDMS, route completion, and hdscore are implementation-inspectable. |
| Debug path | Available | README notes modifying final code path to call `create_gym_env(cfg, output)` directly | Useful for smoke testing simulator loop without first depending on a heavy AD client, but `create_gym_env()` still expects a `plan_pipe` trajectory producer. |

### Current Blockers

- We have not run HUGSIM locally yet.
- Public release size is non-trivial; sample data is smaller than the full release and should be used first.
- Some competition scenarios are explicitly private according to README.
- AD clients are external dependencies; a lightweight or dummy client strategy is still needed for minimal audit workflow testing.
- Source availability does not yet validate reconstruction fidelity, extrapolated-view stability, or metric credibility.

---

## Pipeline Trace

This is the current implementation-level trace of the HUGSIM closed-loop path.

```text
scenario YAML
→ OmegaConf load and merge with base / camera / kinematic config
→ model config loaded from exported scene folder
→ optional AD client launched by shell path
→ Gymnasium env `hugsim_env/HUGSim-v0` created
→ env.reset()
→ render multi-camera observation + info
→ write `(obs, info)` to `obs_pipe`
→ read planned trajectory from `plan_pipe`
→ convert planned trajectory to acceleration / steer-rate
→ env.step(action)
→ update actor plans and ego kinematic state
→ render next observation
→ store frames, infos, video, ground/scene point clouds
→ compute NC / DAC / TTC / comfort / PDMS / route completion / hdscore
```

### Implementation Nodes

| Node | File | Role | Audit Concern |
|---|---|---|---|
| Simulation orchestrator | `closed_loop.py` | Loads configs, launches AD client, pipes observations/plans, saves outputs, invokes evaluation | Pipe-based loop may require a deterministic plan writer for smoke testing. |
| Gym environment | `sim/hugsim_env/envs/hug_sim.py` | Defines observation/action space, loads scene/dynamic Gaussians, renders observations, updates ego state | This is the main simulator-state and sensor-generation surface. |
| Actor planner | `sim/utils/plan.py` | Converts scenario `plan_list` into actor controllers and updates actor states | Actor behavior credibility depends on controller assumptions and map availability. |
| Agent controllers | `sim/utils/agent_controller.py` | Implements IDM, AttackPlanner, ConstantPlanner, UnicyclePlanner | Safety-critical outcomes may be artifacts of controller choice or parameters. |
| Trajectory-to-control | `sim/utils/sim_utils.py` | Converts AD planned trajectory into acceleration and steer-rate | Planner output semantics and coordinate transforms must be audited. |
| Scoring | `sim/utils/score_calculator.py` | Computes NC, DAC, TTC, comfort, PDMS, route completion, hdscore | Metrics score internal state; they do not automatically validate rendered evidence. |

---

## 0. Audit Summary

### Paper Claim

HUGSIM claims to be a real-time, photo-realistic, closed-loop simulator for autonomous driving. It lifts captured 2D RGB images into 3D space with 3D Gaussian Splatting, supports dynamic updating of ego and actor states and observations based on control commands, and provides a benchmark across KITTI-360, Waymo, nuScenes, and PandaSet sequences.

### Evidence Provided

- Paper: https://arxiv.org/abs/2412.01718
- Project page: https://xdimlab.github.io/HUGSIM/
- Official implementation: https://github.com/hyzhou404/HUGSIM
- Sample data: https://huggingface.co/datasets/hyzhou404/HUGSIM/tree/main/sample_data
- Released HUGSIM assets: https://huggingface.co/datasets/XDimLab/HUGSIM

### Audit Judgment

HUGSIM is a stronger Phase 1 runnable target than OmniDreams/Cosmos because it has a public paper, public project page, public code repository, MIT-licensed code, sample/released asset links, and an explicit closed-loop simulation entry point.

However, the presence of a runnable simulator does not by itself prove that closed-loop evaluation results are credible. The audit must still examine reconstruction fidelity, extrapolated-view stability, actor insertion fidelity, scenario-editing validity, ego/actor state update logic, and whether evaluation metrics detect simulator artifacts or only score AD-agent behavior.

### Open Questions

- Which public released scene/scenario should be selected for the first smoke test?
- Can HUGSIM run with a lightweight / dummy AD client for audit workflow smoke testing?
- Can the debug path enter `create_gym_env(cfg, output)` without launching UniAD/VAD/LTF?
- Does the simulator provide enough evidence to distinguish real AD-agent failure from reconstruction or interaction artifacts?

---

## 1. Basic Pipeline

### Paper Claim

HUGSIM reconstructs dynamic urban scenes using 3DGS and then builds a closed-loop simulator on top of the reconstructed scene. The simulator can update ego/actor states and observations based on control commands.

### Evidence Provided

- The paper describes HUGSIM as lifting captured 2D RGB images into 3D space via 3D Gaussian Splatting and enabling a full closed simulation loop.
- The project page states that HUGSIM decomposes the scene into static and dynamic 3D Gaussians and models dynamic vehicle motion with a unicycle model.
- The official repository exposes reconstruction (`train_ground.py`, `train.py`), scene export (`eval_render/export_scene.py`), conversion (`eval_render/convert_scene.py`, `eval_render/convert_vehicles.py`), GUI configuration (`gui/app.py`), and simulation (`closed_loop.py`) paths.
- `closed_loop.py` confirms the runtime sequence: merge configs, load scene model config, select AD client path, launch AD client, run `create_gym_env`, and save outputs.

### Audit Judgment

The claimed pipeline is credible enough to justify Phase 1 implementation inspection and smoke testing. The key audit target is whether this pipeline preserves task-relevant spatial and temporal relations under closed-loop deviation, not merely whether rendered frames look photorealistic.

### Open Questions

- Which intermediate artifacts are saved after reconstruction?
- Does scene export preserve enough geometry / semantics for independent audit?
- How are actor trajectories represented and updated frame to frame?

---

## 2. Log-Driven Scene Reconstruction

### Paper Claim

HUGSIM starts from captured posed images of dynamic urban scenes and reconstructs urban scenes by disentangling ground, non-ground static background, and dynamic objects.

### Evidence Provided

- `data/README.md` documents dataset preparation for KITTI-360, Waymo Open Dataset, nuScenes, and PandaSet.
- The data preparation path requires external datasets and, for 2D semantic labels, InverseForm checkpoints.
- Reconstruction scripts include `train_ground.py` and `train.py`.
- The scene export path minimizes reconstructed scene folders for sharing and simulation.

### Audit Judgment

The log-driven reconstruction claim is central. The audit should determine whether reconstruction quality is evaluated only by image similarity or also by task-relevant geometry, semantics, occlusion, and lane/drivable-area consistency.

### Open Questions

- What source annotations are required: camera poses, 2D predictions, 3D boxes, semantic masks, HD maps?
- How robust is reconstruction when annotations are noisy?
- Are failed reconstructions detectable before closed-loop evaluation?

---

## 3. 3DGS Representation

### Paper Claim

HUGSIM extends 3DGS to dynamic urban scenes and represents appearance, semantics, optical flow, depth, and object motion.

### Evidence Provided

- Paper Section 3 describes 3DGS representation, decomposed scene representation, ground Gaussians, native dynamic vehicle Gaussians, and unicycle-model regularization.
- The Gym environment loads `scene.pth` into `GaussianModel` and dynamic actor checkpoints into `ObjModel`.
- The environment exports `ground.ply` and `scene.ply` from semantic-indexed Gaussian points for later metric computation.
- `_get_obs()` renders RGB, semantic argmax labels, and depth for each configured camera.

### Audit Judgment

3DGS improves rendering speed and real-time feasibility, but speed does not prove credibility. The audit must test whether the Gaussian representation preserves relational consistency under extrapolated ego poses and inserted actor viewpoints.

### Open Questions

- Which 3DGS components are static vs dynamic?
- How are semantics and flow attached to Gaussians?
- Can semantic/depth outputs be used as audit evidence for collision or near-miss claims?

---

## 4. Dynamic Actor Modeling

### Paper Claim

HUGSIM models dynamic vehicle motion with a unicycle model and uses 360-degree high-fidelity actor insertion.

### Evidence Provided

- The paper claims a unicycle model regularizes dynamic vehicle trajectories.
- The environment constructs a planner from scenario `plan_list`, loads dynamic object checkpoints for each planned actor, and derives object boxes from planned actor transforms.
- `plan.py` interprets `plan_list` entries as initial actor state plus model/controller/controller-args; it loads each actor's `gs.pth` and `wlh.json`.
- `plan.py` supports controllers including IDM, AttackPlanner, ConstantPlanner, and UnicyclePlanner.
- The README says released assets include 3DRealCar files.

### Audit Judgment

Actor modeling is a major credibility risk. Collisions and near-misses can be caused by actor insertion artifacts, incorrect scale, incorrect orientation, bad occlusion, or unrealistic behavior generation.

The code makes actor behavior inspectable, which is good for audit. But it also means each scenario outcome must be attributed to a specific actor controller and parameters, not just to the AD agent.

### Open Questions

- Are inserted actors physically and semantically aligned with the scene?
- Is actor scale consistent across viewpoints?
- Are occluding / occluded-by relations stable as ego moves?
- Which actor controller is used in the selected smoke-test scenario?

---

## 5. Counterfactual / Scenario Editing

### Paper Claim

HUGSIM supports edited scenarios and aggressive actor behavior generation for safety-critical simulation.

### Evidence Provided

- The paper claims normal actors can use IDM when HD maps are available and aggressive actors can use an attack planning strategy.
- The README describes a GUI for configuring scenarios and downloading scenario YAML files.
- `closed_loop.py` consumes `--scenario_path ./configs/benchmark/${dataset_name}/${scenario_name}.yaml`.
- Example scenario YAML files contain `mode`, `plan_list`, `load_HD_map`, `start_euler`, `start_ab`, `start_velo`, `start_steer`, `scene_name`, and `iteration`.
- Easy/medium/hard scenarios can use `ConstantPlanner`; extreme examples can use `AttackPlanner` with `pred_steps`, `ATTACK_FREQ`, and `best_k`.

### Audit Judgment

This is directly relevant to credibility audit. Any edited or aggressive scenario should carry evidence that the edit remains physically plausible, geometrically consistent, and sensor-observable.

Scenario YAML is a useful audit anchor because it records actor initial state, asset ID, controller type, controller parameters, ego start state, map usage, scene name, and reconstruction iteration. The audit layer should include the scenario YAML in every closed-loop evidence record.

### Open Questions

- Can an edited actor be traced back to source evidence and released 3DRealCar asset metadata?
- Does the simulator flag edits outside reconstruction support?
- Do attack-planner scenarios remain physically and contextually plausible when `load_HD_map: false`?

---

## 6. Sensor-Level Observation Generation

### Paper Claim

HUGSIM renders RGB images and can also represent semantic labels and optical flow through its Gaussian representation.

### Evidence Provided

- Project page states HUGSIM renders RGB images, semantic labels, and optical flow.
- The Gym environment's observation space exposes `rgb`, `semantic`, and `depth` dictionaries per camera.
- `_get_obs()` renders per-camera RGB, semantic argmax labels, and depth from the Gaussian renderer.
- `closed_loop.py` saves multi-camera RGB observations into `video.mp4` and pickles `infos.pkl`; it does not yet clearly save semantic/depth outputs into the default evaluation artifacts.

### Audit Judgment

Sensor-level generation should be audited using more than visual quality. The important question is whether the observations preserve task-relevant relations needed by vision-based AD agents.

Semantic/depth are available in the Gym observation, which is valuable for audit. The smoke test should explicitly log or export these modalities if possible, because default AD-video output alone is insufficient for relation-level credibility inspection.

### Open Questions

- Are depth / semantics / flow available to AD clients, or only RGB is actually piped to the selected AD client?
- Can depth / semantics be logged for independent consistency checks?
- Do per-camera outputs remain relation-consistent under extrapolated ego poses?

---

## 7. Closed-Loop Rollout

### Paper Claim

HUGSIM closes the loop by querying waypoints from AD algorithms, applying control, and updating ego and actor states and observations.

### Evidence Provided

- README documents `closed_loop.py` with `--scenario_path`, `--base_path`, `--camera_path`, `--kinematic_path`, `--ad`, and `--ad_cuda` arguments.
- `closed_loop.py` creates a Gymnasium environment, writes `(obs, info)` to `obs_pipe`, reads `plan_traj` from `plan_pipe`, converts trajectory to acceleration/steer-rate control with `traj2control`, calls `env.step(action)`, and saves `data.pkl`, `video.mp4`, `infos.pkl`, and `eval.json`.
- README provides a debug modification that bypasses launching AD clients and directly calls `create_gym_env(cfg, output)`.
- `launch_ad.py` shows that the AD client is launched as a separate shell process with arguments `(cuda_id, output)` and logs stdout/stderr to `output.txt`.

### Audit Judgment

This is the key reason HUGSIM is selected as Phase 1 target. The next step is not to reproduce the full benchmark, but to run or design a minimal smoke test that logs every observation, action, state update, and metric event.

The pipe-based design creates a clean audit boundary: simulator state and observation are emitted before each AD decision, and planned trajectory is consumed before each simulator update. For the first smoke test, a deterministic `plan_pipe` writer is likely more useful than installing a heavy AD model immediately.

### Open Questions

- Can the debug path produce useful output without an AD client, or does it still block while waiting on `plan_pipe`?
- Can a deterministic waypoint client be added with minimal code?
- What exactly should be logged for audit: RGB, semantic, depth, ego state, actor state, plan trajectory, action, collision, route completion, and metric scores?

---

## 8. Ego / Actor State Update

### Paper Claim

HUGSIM updates ego vehicle pose and actor trajectories during simulation; normal actors can use IDM and aggressive actors can use an attack planning strategy.

### Evidence Provided

- `HUGSimEnv.step()` increments timestamp, updates actor planning through `planner.plan_traj`, applies acceleration and steer-rate to ego velocity and steering, updates ego position/orientation using kinematic parameters, checks background and foreground collision, checks route completion, then renders the next observation.
- `HUGSimEnv._get_info()` returns ego pose, ego velocity, steering, command, ego box, object boxes, camera parameters, route completion, and collision status.
- `configs/sim/kinematic.yaml` defines `min_steer`, `max_steer`, `min_acc`, `max_acc`, `fric`, `Lr`, `Lf`, `max_speed`, and `dt`.
- `plan.py` calls each actor controller to update actor states, then constructs body-to-world transforms for dynamic Gaussians.

### Audit Judgment

State update credibility is separate from rendering credibility. The audit must determine whether dangerous outcomes are caused by plausible state evolution or simulator/planner artifacts.

The ego update is inspectable and kinematic. Actor update is controller-dependent. This means every collision or near-miss needs a state-update trace that records ego action, actor controller state, and rendered observation evidence.

### Open Questions

- Are kinematic bounds realistic for all datasets and scenarios?
- How are actor paths constrained by lanes or HD maps?
- How are aggressive actors generated in scenes without HD maps?
- Does route-completion termination hide or truncate some failure modes?

---

## 9. Supported AD Agents

### Paper Claim

HUGSIM evaluates UniAD, VAD, and Latent-Transfuser / LTF-style agents according to the project page and README.

### Evidence Provided

- Project page states HUGSIM evaluates UniAD, VAD, and Latent-Transfuser.
- README says UniAD_SIM, VAD_SIM, and NAVSIM clients should be installed before simulation.
- `closed_loop.py` supports `--ad uniad`, `--ad vad`, and `--ad ltf`, and selects `cfg.base.uniad_path`, `cfg.base.vad_path`, or `cfg.base.ltf_path`.
- `launch_ad.py` launches the selected AD client as a separate process.

### Audit Judgment

Supported AD agents should be treated as evaluation subjects, not credibility validators. A simulator can produce agent scores without proving that its generated evidence is trustworthy.

### Open Questions

- Which agents can be run from public code today with the least setup burden?
- Can a dummy agent be used for audit smoke testing?
- Is the pipe-based AD interface stable enough to wrap with audit logging?

---

## 10. Evaluation Metrics

### Paper Claim

HUGSIM proposes HD-Score, based on No Collision, Drivable Area Compliance, Time to Collision, Comfort, and Route Completion.

### Evidence Provided

- `sim/utils/score_calculator.py` implements `ScoreCalculator`.
- Metric components include `_calculate_no_collision`, `_calculate_drivable_area_compliance`, `_calculate_time_to_collision`, `_calculate_is_comfortable`, route completion from frame data, PDMS, and final `hdscore`.
- `closed_loop.py` invokes `hugsim_evaluate([save_data], ground_xyz, scene_xyz)` after simulation and writes `eval.json`.
- NC checks planned ego boxes against foreground object boxes and background scene points.
- DAC checks trajectory footprint against exported ground points.
- TTC projects planned trajectory forward and reuses collision checking.
- Comfort checks kinematic boundaries.
- `hdscore` is computed from PDMS and route completion.

### Audit Judgment

These are primarily AD performance metrics. They do not automatically validate simulator credibility. The audit must check whether metrics can detect invalid or low-confidence simulator evidence.

Implementation inspection shows that key scores are computed from simulator state, object boxes, ground point cloud, scene point cloud, planned trajectory, and route completion. That makes the metrics reproducible in code, but still does not prove rendered observations are free of artifacts or relation errors.

### Open Questions

- Are NC/DAC/TTC/COM/route computed consistently across all datasets and scenarios?
- Can the metrics distinguish real agent failures from rendering or scenario artifacts?
- Are low-confidence scenarios down-weighted or rejected?

---

## 11. What the Metrics Prove

Current first-pass judgment:

- NC proves whether the ego bounding geometry intersects foreground actors or enough background scene points under HUGSIM's internal geometric representation.
- DAC proves whether the ego trajectory has enough ground/drivable support according to the exported ground point cloud heuristic.
- TTC proves whether forward-projected trajectories collide within selected short time windows under the same internal geometry.
- Comfort proves whether trajectory kinematics stay within predefined comfort boundaries.
- Route completion proves progress along HUGSIM's route-completion proxy.
- HDScore aggregates these performance signals for AD-agent evaluation.

These metrics are useful for scoring closed-loop outcomes once the simulator state is accepted as credible.

---

## 12. What the Metrics Do Not Prove

The metrics do not by themselves prove:

- that 3DGS reconstruction is geometrically correct;
- that extrapolated views preserve lane/drivable-area geometry;
- that inserted actors have correct scale, orientation, and occlusion;
- that RGB observations contain enough task-relevant evidence for the AD agent;
- that semantic/depth outputs are consistent with rendered RGB;
- that aggressive actor behavior is physically or contextually plausible;
- that a collision or near-miss is caused by real AD-agent failure rather than simulator artifact.

Therefore, HDScore should be treated as an AD-performance metric under HUGSIM, not as a standalone simulator-credibility metric.

---

## 13. Credibility Gaps

Priority gaps:

- Extrapolated-view artifacts on lane/drivable regions.
- 360-degree inserted actor fidelity.
- Actor scale/orientation consistency.
- Occlusion correctness under ego deviation.
- Depth/semantic consistency under edited scenarios.
- Whether collisions or near-misses are caused by real agent failure or simulator artifact.
- Whether aggressive actor behavior remains physically and contextually plausible.
- Whether HD-Score should be accepted, down-weighted, or rejected for low-confidence scenarios.

---

## 14. Minimal Smoke Test Plan

See `docs/hugsim_smoke_test_plan.md`.

The first smoke test should use public sample/released assets and should prioritize a debug or lightweight client path. It should not attempt to reproduce the full HUGSIM benchmark.

---

## 15. Preliminary Judgment

HUGSIM is currently the best Phase 1 target for this project because it is public, 3DGS-based, closed-loop, and directly aimed at autonomous-driving evaluation. The first audit should prioritize runnable evidence and relation-level consistency over broad literature coverage.

Issue #5 can be considered complete at the first-pass pipeline-extraction level. The next step is Issue #6: turn this into a concrete smoke-test path, likely by selecting one public released scenario and creating a deterministic plan-pipe writer or dummy client.
