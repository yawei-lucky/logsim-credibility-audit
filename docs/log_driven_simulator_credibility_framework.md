# Four-Level Credibility Validation for Log-Driven Simulators

## 1. Scope

This project uses the following broad definition:

> A log-driven simulator starts from real road-driving capture sequences,
> reconstructs or derives an interactive environment from those observations,
> and generates counterfactual closed-loop evolution on top of that
> environment.

It does not need to replay the original log. The source scene comes from real
data, while novel ego views, inserted actors, edited scenarios, and future
interactions may be simulated.

Under this definition, HUGSIM is in scope. More precisely, it is a
**real-driving-sequence reconstruction-based, counterfactual closed-loop neural
simulator**:

- its official pipeline takes posed images from dynamic urban scenes;
- it reconstructs static and dynamic 3D Gaussians;
- it uses sequences from KITTI-360, Waymo, nuScenes, and PandaSet;
- it updates ego state, actor state, and observations in a closed loop;
- edited actors and novel viewpoints are simulated rather than copied directly
  from the source sequence.

Official references:

- https://arxiv.org/abs/2412.01718
- https://xdimlab.github.io/HUGSIM/
- https://github.com/hyzhou404/HUGSIM

## 2. Research Question

The project does not ask only whether a simulator is runnable or visually
attractive. It asks:

> Under what evidence conditions can a counterfactual closed-loop result from
> a log-driven simulator be trusted as evidence for evaluating an autonomous
> driving system?

HUGSIM is the first case study. The intended output is a validation method that
can later be applied to other real-data reconstruction simulators.

## 3. Four Levels of Credibility Evidence

### Level 1 — Source Availability and Provenance

Question:

> Can an auditor identify and inspect what the simulator, reconstruction, and
> scenario are built from?

Required evidence includes:

- paper, code, license, runtime, and evaluation implementation;
- source dataset and sequence identity;
- reconstruction and preprocessing path;
- scene, vehicle, scenario, and model versions or hashes;
- public availability or clearly recorded access restrictions.

Level 1 establishes traceability. It does not establish simulation fidelity.

### Level 2 — Closed-Loop Evidence Completeness

Question:

> Does a run preserve the complete causal chain needed to inspect what
> happened?

Required evidence includes:

```text
source scene and scenario
→ rendered sensor observation
→ agent or test planner output
→ control action
→ ego and actor state transition
→ next observation
→ metric event
```

The run must record synchronized observations, plans, actions, states, actor
geometry, timestamps, metrics, and reproducibility metadata.

Level 2 establishes observability of the process. It does not show that the
process is realistic or correct.

### Level 3 — Segment-Level Credibility Judgment

Question:

> Is a particular normal, risk, collision, off-road, or interaction event
> supported by sufficiently independent and task-relevant evidence?

Each segment uses exactly one evidence label:

```text
accepted
down-weighted
rejected
```

The judgment should consider:

- agreement with source-log evidence at observed poses;
- geometric, semantic, temporal, and relational consistency;
- counterfactual intervention validity;
- whether the event is caused by agent behavior or a simulator artifact;
- whether the relevant sensor region contains reconstruction or insertion
  artifacts;
- whether internal metrics agree with rendered and state evidence.

Internal consistency alone is insufficient. RGB, semantic, and depth produced
by one renderer may agree with each other while all differ from real sensor
data.

### Level 4 — Cross-Segment Simulator Credibility

Question:

> Across representative scenes, interventions, and operating regions, how much
> confidence should be assigned to results from this simulator?

Level 4 will eventually aggregate:

- Level 3 decisions across scenes and event types;
- coverage of source domains and reconstruction support;
- failure and uncertainty detection;
- repeatability and sensitivity;
- correlation with real-world or independently grounded outcomes;
- credibility calibration for downstream AD evaluation.

The final quantitative credibility metric belongs here. It must not be defined
from one scene or a small smoke test.

## 4. Non-Equivalences

The framework keeps the following claims separate:

```text
real-log origin           ≠ credible counterfactual output
closed-loop execution     ≠ credible closed-loop evidence
cross-modal consistency   ≠ agreement with real sensor data
internal metric response  ≠ trustworthy E2E-agent evaluation
photo-realistic appearance ≠ causal or geometric validity
```

## 5. Current HUGSIM Position

| Level | Current status | Current evidence | Main gap |
|---|---|---|---|
| Level 1 | Phase 1 complete | Public paper, code, runtime, datasets, released scene/vehicle/scenario assets | Full reconstruction provenance is not yet packaged for independent reproduction |
| Level 2 | Simulator-side chain complete | Synchronized observations, dummy plan, action, ego/actor state, rollout, and metrics are recorded | No real sensor-input AD agent in the current experiment |
| Level 3 | `down-weighted` overall | Paired actor-placement runs show a valid internal geometry/metric response | Visible rendering domain gap, no real-log reference comparison, and limited intervention coverage |
| Level 4 | Not started | Decision rules and evidence format exist | Insufficient accepted/down-weighted/rejected segments across scenes and event types |

The current actor experiment should therefore be interpreted as:

> a useful Level 2 completion and a partial Level 3 internal-geometry test,
> not a Level 4 simulator credibility result.

## 6. Near-Term Research Program

The next phase should build representative Level 3 evidence, not a final score.

Priority order:

1. **Source fidelity:** compare reconstructed observations with the original
   real capture at matched poses.
2. **Counterfactual validity:** test whether controlled actor and ego changes
   preserve geometry, semantics, occlusion, and temporal relations.
3. **Causal attribution:** distinguish AD-agent failure from reconstruction,
   control, scenario, and metric artifacts.
4. **Support awareness:** determine whether the simulator can identify
   extrapolated or low-support regions where evidence should be down-weighted
   or rejected.
5. **Generalization:** repeat the same evidence protocol across scenes,
   datasets, actors, and event types before designing Level 4 aggregation.

This keeps HUGSIM work aligned with the final objective: credible validation of
the class of log-driven simulators.
