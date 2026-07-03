# HUGSIM Credibility Audit

> Status: Phase 1 working draft.  
> Scope: audit HUGSIM as a runnable 3DGS-based log-driven closed-loop simulator, not a general autonomous-driving simulator survey.

## Source Availability Gate

| Item | Status | Evidence | Audit Consequence |
|---|---|---|---|
| Paper | Available | https://arxiv.org/abs/2412.01718 | Paper claims can be cited and audited as reported evidence. |
| Project page | Available | https://xdimlab.github.io/HUGSIM/ | Can inspect official claims, demos, architecture overview, and benchmark claims. |
| Code repo | Available | https://github.com/hyzhou404/HUGSIM | Can inspect implementation structure, installation, reconstruction, scene export, GUI, and closed-loop simulation entry points. |
| License | Available | https://github.com/hyzhou404/HUGSIM/blob/main/LICENSE | Repository license can be checked before reuse. |
| Reconstructed scenes / vehicles / scenarios | Available / partly restricted | HUGSIM README links to released 3DRealCar files, scenes, and scenarios, while noting some competition scenarios are private. | Some smoke tests should use released public assets only; private competition scenarios cannot be assumed available. |
| Sample data | Available | HUGSIM README links to sample data on Hugging Face. | Can start with sample data before attempting full dataset conversion. |
| Original datasets | Restricted / external | KITTI-360, Waymo, nuScenes, PandaSet | Training/evaluation distribution cannot be fully reproduced without satisfying each dataset's access and license requirements. |
| Simulator runtime | Available | `closed_loop.py`, `configs/sim/*`, `sim/` in the official repository | Closed-loop runtime is inspectable, but actual execution depends on local paths, CUDA, AD clients, and released scenes/scenarios. |
| Policy agent / AD client | Available / external dependency | README mentions UniAD_SIM, VAD_SIM, and NAVSIM clients before simulation. | Closed-loop evaluation depends on installing or replacing external AD clients; simulator credibility should be separated from policy-agent performance. |
| Orchestrator | Available | `closed_loop.py` launches simulation and AD algorithms according to README. | Can inspect state-update and evaluation flow, but must verify runtime behavior through a smoke test. |
| Evaluation scripts / metrics | TODO_NOT_CONFIRMED | TODO_SOURCE | Need inspect code paths for HD-Score, NC, DAC, TTC, COM, and route completion before treating metrics as reproducible. |

## 0. Audit Summary

### Paper Claim

HUGSIM claims to be a real-time, photo-realistic, closed-loop simulator for autonomous driving. It lifts captured 2D RGB images into 3D space with 3D Gaussian Splatting, supports dynamic updating of ego and actor states and observations based on control commands, and provides a benchmark across KITTI-360, Waymo, nuScenes, and PandaSet sequences.

### Evidence Provided

- Paper: https://arxiv.org/abs/2412.01718
- Project page: https://xdimlab.github.io/HUGSIM/
- Official implementation: https://github.com/hyzhou404/HUGSIM

### Audit Judgment

HUGSIM is a stronger Phase 1 runnable target than OmniDreams/Cosmos because it has a public paper, public project page, public code repository, sample/released asset links, and an explicit closed-loop simulation entry point.

However, the presence of a runnable simulator does not by itself prove that closed-loop evaluation results are credible. The audit must still examine reconstruction fidelity, extrapolated-view stability, actor insertion fidelity, scenario-editing validity, ego/actor state update logic, and whether evaluation metrics detect simulator artifacts or only score AD-agent behavior.

### Open Questions

- Which released scenes and scenarios are fully public and immediately runnable?
- Can HUGSIM run with a lightweight / dummy AD client for audit workflow smoke testing?
- Which metrics are computed by code, and where are they implemented?
- Does the simulator provide enough evidence to distinguish real AD-agent failure from reconstruction or interaction artifacts?

---

## 1. Basic Pipeline

### Paper Claim

HUGSIM reconstructs dynamic urban scenes using 3DGS and then builds a closed-loop simulator on top of the reconstructed scene. The simulator can update ego/actor states and observations based on control commands.

### Evidence Provided

- The paper describes HUGSIM as lifting captured 2D RGB images into 3D space via 3D Gaussian Splatting and enabling a full closed simulation loop.
- The project page states that HUGSIM decomposes the scene into static and dynamic 3D Gaussians and models dynamic vehicle motion with a unicycle model.

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

TODO_SOURCE: extract exact section and figure references from the paper.

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

TODO_SOURCE: extract exact representation details from paper Section 3.

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

TODO_SOURCE

### Audit Judgment

Actor modeling is a major credibility risk. Collisions and near-misses can be caused by actor insertion artifacts, incorrect scale, incorrect orientation, bad occlusion, or unrealistic behavior generation.

### Open Questions

- Are inserted actors physically and semantically aligned with the scene?
- Is actor scale consistent across viewpoints?
- Are occluding / occluded-by relations stable as ego moves?

---

## 5. Counterfactual / Scenario Editing

### Paper Claim

HUGSIM supports edited scenarios and aggressive actor behavior generation for safety-critical simulation.

### Evidence Provided

TODO_SOURCE

### Audit Judgment

This is directly relevant to credibility audit. Any edited or aggressive scenario should carry evidence that the edit remains physically plausible, geometrically consistent, and sensor-observable.

### Open Questions

- How are scenario yaml files structured?
- Can an edited actor be traced back to source evidence?
- Does the simulator flag edits outside reconstruction support?

---

## 6. Sensor-Level Observation Generation

### Paper Claim

HUGSIM renders RGB images and can also represent semantic labels and optical flow through its Gaussian representation.

### Evidence Provided

TODO_SOURCE

### Audit Judgment

Sensor-level generation should be audited using more than visual quality. The important question is whether the observations preserve task-relevant relations needed by vision-based AD agents.

### Open Questions

- Which modalities are exposed to AD clients in closed loop?
- Are depth / semantics / flow available during evaluation or only for reconstruction/evaluation?
- Can these modalities be used for independent consistency checks?

---

## 7. Closed-Loop Rollout

### Paper Claim

HUGSIM closes the loop by querying waypoints from AD algorithms, applying control, and updating ego and actor states and observations.

### Evidence Provided

The README describes `closed_loop.py`, simulation configs, AD client setup, and command-line arguments for running scenarios.

### Audit Judgment

This is the key reason HUGSIM is selected as Phase 1 target. The next step is not to reproduce the full benchmark, but to run or design a minimal smoke test that logs every observation, action, state update, and metric event.

### Open Questions

- Can the closed-loop runtime run without UniAD/VAD using debug mode or a lightweight stand-in client?
- What state variables are logged at each step?
- Where are collision, TTC, drivable-area, comfort, and route metrics computed?

---

## 8. Ego / Actor State Update

### Paper Claim

HUGSIM updates ego vehicle pose and actor trajectories during simulation; normal actors can use IDM and aggressive actors can use an attack planning strategy.

### Evidence Provided

TODO_SOURCE

### Audit Judgment

State update credibility is separate from rendering credibility. The audit must determine whether dangerous outcomes are caused by plausible state evolution or simulator/planner artifacts.

### Open Questions

- What kinematic model is used for ego control?
- How are actor paths constrained by lanes or HD maps?
- How are aggressive actors generated in scenes without HD maps?

---

## 9. Supported AD Agents

### Paper Claim

HUGSIM evaluates UniAD, VAD, and Latent-Transfuser / LTF-style agents according to the project page and README.

### Evidence Provided

TODO_SOURCE

### Audit Judgment

Supported AD agents should be treated as evaluation subjects, not credibility validators. A simulator can produce agent scores without proving that its generated evidence is trustworthy.

### Open Questions

- Which agents can be run from public code today?
- Can a dummy agent be used for audit smoke testing?
- Is there a clean API boundary between simulator and agent?

---

## 10. Evaluation Metrics

### Paper Claim

HUGSIM proposes HD-Score, based on No Collision, Drivable Area Compliance, Time to Collision, Comfort, and Route Completion.

### Evidence Provided

TODO_SOURCE

### Audit Judgment

These are primarily AD performance metrics. They do not automatically validate simulator credibility. The audit must check whether metrics can detect invalid or low-confidence simulator evidence.

### Open Questions

- Are NC/DAC/TTC/COM/route computed from simulator state, rendered observations, maps, or a mix?
- Can the metrics distinguish real agent failures from rendering or scenario artifacts?
- Are low-confidence scenarios down-weighted or rejected?

---

## 11. What the Metrics Prove

TODO_SOURCE

---

## 12. What the Metrics Do Not Prove

Preliminary hypothesis: HUGSIM metrics likely measure AD-agent performance under the simulator, but do not by themselves prove that the simulator's counterfactual evidence is credible.

TODO_SOURCE

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

---

## 15. Preliminary Judgment

HUGSIM is currently the best Phase 1 target for this project because it is public, 3DGS-based, closed-loop, and directly aimed at autonomous-driving evaluation. The first audit should prioritize runnable evidence and relation-level consistency over broad literature coverage.
