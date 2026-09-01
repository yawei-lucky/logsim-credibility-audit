# LogSim Credibility Audit — Current State Index

Last updated: 2026-09-01

## 1. Project question

This project develops a credibility-validation method for log-driven,
counterfactual closed-loop simulators used to test automated driving systems.

The durable questions are:

> Does a simulator provide task-relevant information that is consistent enough
> with reality to produce credible perception, decision, planning, control, and
> closed-loop outcomes?

> Does the same fixed AD receiver form sufficiently similar task relations and
> behavior on real input and corresponding simulated input?

Credibility is argued through an evidence network, not visual realism, a
simulator's privileged semantic/depth output, one AD trajectory, or one global
score. Future synthesis is organized around log reproduction, sensor
consistency, task-level consistency, and closed-loop outcome credibility; these
are not current HUGSIM scoring stages.

## 2. Current experimental carrier

HUGSIM is the first experimental carrier, not the final research target. It is
a real-log reconstruction-driven neural simulator that renders six-camera
observations, supports designed counterfactual actors, and updates an ego state
in a closed loop.

SparseDrive-S Stage2 is the current target AD receiver. It is the system under
test, not an independent truth source. Sparse4Dv3 remains a limited supporting
receiver for vehicle-presence and ordinal-relation probes.

Current narrow setup:

```text
scene-0383 reconstruction
→ six HUGSIM RGB cameras
→ fixed SparseDrive
→ corrected plan/controller coordinate boundary
→ explicit actuation contract
→ HUGSIM kinematic state update
```

## 3. Validated capabilities

- HUGSIM's bounded loop, FIFO exchange, six-camera rendering, state logging,
  deterministic source replay, and artifact manifests are operational; see
  `docs/runs/hugsim_smoke_test_002.md`.
- Counterfactual geometry, motion, visibility, risk, and interaction laws have
  a falsifiable constraint skeleton; see
  `docs/counterfactual_credibility_constraints.md`.
- Complete-future gates reject tail-filled actor futures before NC/TTC claims;
  see `docs/runs/hugsim_horizon_factorial_001.md`.
- SparseDrive consumes fresh six-camera feedback and produces fresh native
  plans across a live loop; see `docs/runs/hugsim_sparsedrive_live_loop_001.md`.
- The raw control boundary now has explicit `strict_audit` and
  `bounded_projection` modes with per-step raw/applied records; see
  `docs/runs/hugsim_sparsedrive_actuation_contract_qualification_001.md`.
- The action semantics are source-confirmed as longitudinal acceleration in
  `[-2,2] m/s²` and steering-angle rate in
  `[-0.261799,0.261799] rad/s`; see the same actuation report.

## 4. Strongest positive evidence

- Frozen ordinal counterfactuals preserved four independent geometric
  near/far and same/adjacent directions with no available receiver reversal;
  see `docs/runs/hugsim_ordinal_metamorphic_001.md`.
- A complete-future CF-R instrument separated stronger and weaker lead-actor
  conflict and measured a SparseDrive clearance response beyond local repeat;
  see `docs/runs/hugsim_cf_r_future_conflict_001.md`.
- Earlier strong/weak closed-loop pairs preserved progress, speed, and
  footprint-clearance direction beyond two-reset variation, narrowly within
  one scene and contract; see `docs/runs/hugsim_cf_r_closed_loop_001.md`.
- Partial matched real/exact-pose HUGSIM windows produced measurable local
  SparseDrive domain differences beyond repeat, but remain down-weighted by
  provenance and scope; see
  `docs/runs/sparsedrive_real_sim_factual_001.md`.
- Actuation Contract 001 accepted strict fail-closed mechanics and six complete
  bounded executions without applying an out-of-box action; see
  `docs/runs/hugsim_sparsedrive_actuation_contract_qualification_001.md`.

These are bounded positive findings. None establishes general real-world
fitness or simulator credibility.

## 5. Strongest negative evidence

- Repeating a final actor box into an unavailable future created false NC/TTC
  risk events that disappeared when the same prefix was extended; see
  `docs/runs/hugsim_horizon_factorial_001.md`.
- RGB support does not qualify metadata boxes or a simple Gaussian-centre
  envelope as exact spatial truth; see
  `docs/runs/hugsim_interaction_observation_indicators_003.md`.
- The original 4/2/1 m boundary loop was infeasible because iLQR requested
  `0.356–0.400 rad/s` against HUGSIM's `0.261799 rad/s` limit; see
  `docs/runs/hugsim_cf_r_boundary_response_001.md`.
- Explicit bounded projection completed that loop but both resets reversed the
  planned near/below progress and speed order; near ended at
  `-0.270/-0.337 m/s`; see
  `docs/runs/hugsim_sparsedrive_actuation_contract_qualification_001.md`.
- HUGSIM's released kinematic update allows the forward-driving ego speed to
  cross zero without an explicit gear or state-admissibility contract; this is
  accepted as a diagnostic finding, while the resulting response claim is
  rejected; see the same actuation report.

## 6. Current evidence boundary

Current evidence can support claims only for a named task, scene range,
receiver, intervention, contract, and measured uncertainty/repeat range.

It cannot currently support:

- HUGSIM-wide credibility or an AD safety claim;
- real sensor equivalence from common-renderer RGB/semantic/depth agreement;
- physical TTC or collision probability from HUGSIM's internal scorer;
- absolute 3D truth from HUGSIM state or one camera-only receiver;
- real-vehicle response magnitude from bounded action projection;
- near-stop oriented-box clearance while heading semantics are unqualified;
- “no simulated danger” as evidence that an AD system is safe.

Strict infeasibility and bounded execution are separate claims: successful
bounded execution does not rewrite the raw SparseDrive–iLQR command as
feasible.

## 7. Current blocker

Credibility Method Qualification 001 has now separated the bounded claim,
hard gates, factual domain difference, counterfactual effect, uncertainty and
outcome evidence without a compensating total score. It correctly retained the
repository's known narrow positives, known failures and cross-layer
contradictions, so it is usable as a diagnostic framework.

The method remains overall `down-weighted`: its challenge set was selected
retrospectively, and no source-independent task acceptance boundary or
prospective challenge has been qualified. The vehicle-state transition also
remains unqualified, but it is now treated as a future experiment-specific
execution gate rather than the research question itself.

## 8. Next single milestone

Run **Task-Boundary Qualification 001** as defined in `CODEX_NEXT_TASK.md`:

1. freeze one bounded claim card for critical-object/conflict ordering and its
   planning or maneuver consequence;
2. obtain an independent task/decision boundary or explicitly retain a
   qualitative ordinal boundary;
3. declare required `G/F/Q/U/O` evidence and uncertainty axes;
4. select one prospective challenge not used to construct Method 001.

Do not run another scene, change the receiver, implement a vehicle model, or
derive a pass threshold from current HUGSIM outputs in this milestone.

## 9. Sources of truth

Read only what the current work needs:

1. current task: `CODEX_NEXT_TASK.md`;
2. durable principles: `docs/research_guiding_principles.md`;
3. counterfactual laws: `docs/counterfactual_credibility_constraints.md`;
4. current method: `CREDIBILITY_VALIDATION_METHOD.md`;
5. method qualification: `docs/runs/credibility_method_qualification_001.md`;
6. metric qualification: `docs/hugsim_metric_evidence_map.md`;
7. decisions: `docs/hugsim_credibility_decision_rules.md`;
8. detailed history: the relevant file under `docs/runs/` and Git history;
9. runtime operations: `docs/hugsim_cuda_pixi_runbook.md`.
