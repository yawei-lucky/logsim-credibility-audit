# Codex Next Task — Counterfactual Credibility Constraints

> Current phase only. Historical results remain in `PROJECT_STATE.md` and
> `docs/runs/`; do not reconstruct all history before routine work.

## Objective

Develop a credibility-validation method for log-driven world simulators.
HUGSIM is the first experimental carrier, not the result to prove.

Durable questions:

> HUGSIM 提供给智驾系统的任务相关信息，是否与现实一致到足以产生可信的感知、决策和闭环结果？

> 同一个智驾模型面对现实数据和对应的仿真数据，是否形成相近的感知、风险排序、规划和控制行为？

## Immediate Direction

Finish a usable first version of the counterfactual law-and-constraint system
before running more specific HUGSIM or receiver experiments.

The current framework is:

```text
docs/counterfactual_credibility_constraints.md
```

It organizes five complementary families:

1. geometry and projection;
2. motion and dynamics;
3. visibility and sensor observability;
4. risk causality;
5. multi-actor interaction.

For each selected law, state the intervention, held-fixed conditions, expected
relationship, whether it is a hard constraint / conditional monotonic relation
/ statistical regularity, where it is observed, what falsifies it, its
qualification basis and source independence, and the strongest allowed claim.
Keep each falsifiable relation atomic; do not combine a hard constraint and a
statistical range into one pass/fail decision.

The purpose is a revisable research skeleton, not an exhaustive standard.
Leave numerical tolerances and behavior ranges open when they lack a defensible
basis.

## Current Deliverable

The first representative intervention matrix is now drafted in section 9 of
`docs/counterfactual_credibility_constraints.md`. It covers four different
mechanisms:

- longitudinal/lateral geometry;
- speed and continuous motion;
- controlled occlusion;
- merge or crossing interaction.

Review it only for overall causal logic and falsifiability. Do not expand it
into an exhaustive taxonomy. Once that bounded review passes, preserve CF-G as
the existing pilot and prepare CF-M, CF-O, and CF-I in that order, choosing a
small implementable subset rather than another cosmetic scene collection.

After the matrix is ready, execute in this order:

```text
world state and causal timing
  -> projection, visibility, and multi-camera observation
  -> supporting receiver response
  -> target AD / planning / control
  -> closed-loop result
```

Simulator-internal mechanism checks may run before external qualification, but
their claims must remain internal. Before claiming bounded real-world
robustness, qualify the relevant law, range, and receiver with source-independent
evidence. Exact matched real–sim data remain specific to the direct-equivalence
branch.

## Existing Evidence to Retain

- The ordinal near/far and same/adjacent experiment is an early method pilot.
- Independently recomputed planar geometry verifies only HUGSIM-declared state,
  not real-world state.
- Sparse4Dv3 is a provisional supporting receiver probe, not truth.
- HUGSIM RGB/semantic/depth and NC/TTC/PDMS are internal evidence and
  diagnostics, not independent reality references.
- Direct matched real–sim work remains a later, stronger path when source data
  are available; it is not a prerequisite for defining designed-counterfactual
  laws.

## Explicitly Deferred

- Do not make Sparse4Dv3 external benchmark qualification the immediate task.
- Do not add another receiver or more HUGSIM scenes merely to obtain curves.
- Do not install a full AD stack yet.
- Do not define final numerical credibility thresholds or the final four-layer
  metric yet.
- Do not claim general HUGSIM or AD-test-domain credibility from current pilots.

## Read Only as Needed

Start with:

```text
docs/counterfactual_credibility_constraints.md
docs/research_guiding_principles.md
```

Use `docs/hugsim_metric_evidence_map.md` when mapping tools or prior evidence.
Open individual run records only when their result is directly reused. Read
runtime, source-anchor, matched-pairing, or decision-rule documents only when
the task reaches those concerns.

## Proportional Review Rule

For ordinary iterations, check whether the overall direction, causal logic,
claim boundary, and immediate deliverable are coherent. Do not reconcile every
historical document or close every uncertainty. Perform a broad consistency
sweep only when the user asks for it or a phase is being finalized.

## Stable Guardrails

- Use only `accepted`, `down-weighted`, and `rejected` for segment-level
  evidence judgments.
- A `rejected` claim remains useful negative or diagnostic evidence.
- HUGSIM TTC is an internal binary planned-path surrogate, not physical TTC.
- Do not accept tail-window NC/TTC without complete future actor states.
- Common-renderer RGB/semantic/depth agreement is not real-sensor correctness.
- A deterministic plan writer enables the simulator loop; it is not an AD
  agent.
