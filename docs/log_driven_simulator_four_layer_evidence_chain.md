# Four-Layer Credibility Evidence Chain for Log-Driven Simulators

## 1. Objective

This project asks:

> When can a counterfactual closed-loop result from a simulator reconstructed
> from real driving logs be treated as credible evidence for evaluating an
> autonomous-driving system?

The answer is organized as a four-layer evidence chain:

```text
Layer 1 — Log Reproduction
Layer 2 — Sensor Consistency
Layer 3 — Task-Level Consistency
Layer 4 — Closed-Loop Outcome Credibility
```

These are evidence layers, not project phases or four successive experiments.
An upper-layer claim depends on adequate evidence from the lower layers.

## 2. Scope

“Log-driven” is used in the broad sense:

> The simulator constructs its environment from real road-driving capture
> sequences and generates counterfactual closed-loop evolution. Exact replay of
> the original log is not required.

This includes reconstruction-based neural simulators such as HUGSIM. Real-data
origin alone does not make novel views, inserted actors, or closed-loop outcomes
credible.

## 3. Four Evidence Layers

### Layer 1 — Log Reproduction

Question:

> Can the simulator trace and reproduce the relevant facts of the real source
> log before counterfactual modification?

Required evidence includes:

- source dataset, sequence, frame, timestamp, calibration, and pose provenance;
- a reproducible mapping from source logs to reconstructed scene assets;
- matched-pose comparison between real observations and reconstructed output;
- preservation of logged road layout, actors, motion, and timing;
- explicit records of unavailable or transformed source information.

Layer 1 establishes the real-world anchor. Public code and downloadable assets
help satisfy the Source Availability Gate, but availability is not itself log
reproduction evidence.

### Layer 2 — Sensor Consistency

Question:

> Are the simulator-generated sensor observations consistent with the real
> sensor evidence and with each other?

Required evidence includes:

- RGB, semantic, depth, and multi-camera spatial alignment;
- temporal consistency across consecutive observations;
- agreement with real captured observations at logged poses;
- calibrated behavior when the ego or actors move away from logged states;
- visibility of blur, ghosting, holes, incorrect occlusion, scale, lighting, or
  domain mismatch in task-relevant regions;
- identification of unsupported or extrapolated observation regions.

Cross-modal agreement produced by one renderer is internal evidence only. It
does not replace comparison with real sensor data.

### Layer 3 — Task-Level Consistency

Question:

> Does the simulator preserve the relations and events that matter to the
> driving task under controlled counterfactual changes?

Required evidence includes:

- lane, drivable-area, front/rear, left/right, and actor relations;
- approach, recession, occlusion, collision, near-miss, and TTC consistency;
- agreement among sensor evidence, internal geometry, state transitions, map
  evidence, and task metrics;
- strictly paired interventions and meaningful negative controls;
- risk-increasing and risk-decreasing counterfactuals;
- causal attribution that separates reconstruction, scenario editing,
  controller, metric, and agent effects.

A metric response can support a narrow task-level claim, but metric values
alone do not establish simulator credibility.

### Layer 4 — Closed-Loop Outcome Credibility

Question:

> Can the resulting closed-loop outcome be trusted as evidence about the
> evaluated autonomous-driving system?

Required evidence includes:

- a real sensor-input AD agent rather than a loop-enabling dummy planner;
- an inspectable observation-to-decision-to-action-to-state causal chain;
- repeatable and sensitivity-aware outcomes under bounded perturbations;
- evidence that reported failures come from the evaluated agent rather than
  simulator, reconstruction, interface, scenario, or scoring artifacts;
- representative evidence across scenes, tasks, interventions, and operating
  regions;
- calibration against real or independently grounded outcomes where possible.

Only Layer 4 supports claims about AD-system performance under the simulator.
It is not established merely because the simulator runs in closed loop.

## 4. Supporting Mechanisms, Not Evidence Layers

The following mechanisms support the chain but are not its four layers:

- **Source Availability Gate:** determines whether external audit is possible.
- **Closed-loop Evidence Completeness:** checks that required artifacts were
  recorded.
- **`accepted`, `down-weighted`, `rejected`:** claim-specific evidence labels.
- **Future credibility metrics:** possible aggregation after sufficient
  evidence exists; not a layer by itself.

## 5. Current HUGSIM Position

| Evidence layer | Current decision | What is established | Main gap |
|---|---|---|---|
| Log reproduction | `down-weighted` | The released scene is tied to a real-driving dataset and runs reproducibly | Exact source frames, poses, and matched real-versus-reconstructed observations have not been audited |
| Sensor consistency | `down-weighted` | RGB, semantic, and depth outputs are synchronized and the inserted actor has internal cross-modal support | Visible synthetic/domain artifacts and no comparison with real sensor observations |
| Task-level consistency | `down-weighted` overall | Strictly paired actor placements produce an `accepted` narrow internal geometry/metric response | Only two exact actor placements, no motion sweep, and limited causal coverage |
| Closed-loop outcome credibility | `rejected` for AD-evaluation claims | The simulator-side loop and scoring path execute reproducibly | The deterministic planner is not an AD agent, and no agent-performance conclusion is supported |

The current experiment therefore shows that the experimental loop and one
narrow internal task relation respond as designed. It does not yet establish
that HUGSIM closed-loop outcomes are credible evidence for evaluating an AD
system.

## 6. Immediate Research Direction

The next material step begins at Layer 1 and then strengthens Layer 2:

```text
exact real source frame and pose
→ matched reconstruction output
→ measurable sensor consistency gap
→ controlled task-level counterfactual
→ claim-specific evidence judgment
```

After the lower layers are grounded, the existing paired actor experiment can
be extended at Layer 3. Layer 4 should wait until the lower layers are
sufficient and a real sensor-input AD agent is introduced.
