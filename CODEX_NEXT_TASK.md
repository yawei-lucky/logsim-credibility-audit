# Codex Next Task — Counterfactual Credibility Constraints

> Current phase only. Historical results remain in `PROJECT_STATE.md` and
> `docs/runs/`; do not reconstruct all history before routine work.

## Objective

Develop a credibility-validation method for log-driven world simulators.
HUGSIM is the first experimental carrier, not the result to prove.

Durable questions:

> HUGSIM 提供给智驾系统的任务相关信息，是否与现实一致到足以产生可信的感知、决策和闭环结果？

> 同一个智驾模型面对现实数据和对应的仿真数据，是否形成相近的感知、风险排序、规划和控制行为？

## Immediate Direction — Target Risk / Planning Receiver Qualification

The first simulator-internal causal-law and indicator pilot is closed. Its
scope and remaining boundaries are recorded in
`docs/runs/counterfactual_indicator_phase_001_closure.md`.

Sparse4Dv3 R50 has passed a bounded supporting-receiver qualification gate for
vehicle presence, longitudinal/lateral ordinal relations, and short temporal
identity. It is not qualified as absolute 3D truth, a risk model, or a
planning/control judge. See
`docs/runs/hugsim_supporting_receiver_qualification_001.md`.

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

CF-R 001 is complete and overall `down-weighted`. State order passed 26/26;
the supporting receiver retained the aggregate closure hierarchy, with one
small early pairwise reversal and several within-trace non-closing steps. See
`docs/runs/hugsim_cf_risk_causality_001.md`.

## Current Deliverable

Do not add another Sparse4Dv3 curve. Identify and qualify the smallest target
AD receiver whose native outputs include critical-object/risk ranking or a
planning/control response. Record its real-data task basis, required input and
temporal contract, output construct, uncertainty/failure modes, and strongest
allowed HUGSIM claim before integration.

The next experiment should connect the retained dynamic conflict direction to
an actual downstream output:

```text
qualified conflict information
  -> target critical-object / risk decision
  -> planning or control direction
```

Do not relabel Sparse4Dv3 confidence or distance as a risk output, and do not
install or run a full AD stack before this qualification gate is reviewed.
Closed-loop outcome validation remains later.

## Completed Basis

CF-I-CAP-001 confirmed narrow internal stimulus-response paths in IDM and
AttackPlanner, including an AttackPlanner response under inputs reachable from
the scene loop. ConstantPlanner and UnicyclePlanner do not consume live vehicle
state, so their independent trajectories are not interaction. The released
scene-level gate is nevertheless rejected: ego prediction indices use
`dt=0.25 s`, AttackPlanner candidate indices use `2/19≈0.1053 s`, and
indexwise costs compare mismatched future times. See
`docs/runs/hugsim_interaction_capability_001.md`.

The research output is an audited indicator, not a repaired HUGSIM result.
CF-I-STATE-001 has now validated four state-level indicators against frozen
known controls:

- `CF-I-T1` indexed-time alignment;
- `CF-I-T2` causal response onset;
- `CF-I-T3` post-stimulus response existence;
- `CF-I-T4` world-time state continuity.

All four control-discrimination claims are narrowly `accepted`. The released
grid was correctly rejected by T1/T4; a one-step-early response was rejected by
T2; independent ConstantPlanner motion was rejected as interaction by T3. See
`docs/runs/hugsim_interaction_state_indicators_001.md`.

CF-I-LOOP-001 has now transported the same four decisions into HUGSIM's actual
`planner.plan_traj` loop. The aligned controls passed; the released timing,
one-step-early cause, and ConstantPlanner controls retained their expected
negative decisions. All four transport claims are narrowly `accepted`, while
overall evidence remains `down-weighted`. See
`docs/runs/hugsim_interaction_planner_loop_indicators_001.md`.

The exact AttackPlanner traces changed relative to the direct state harness.
A bounded replay isolated HUGSIM's float32 state writeback as the cause: a
cast-matched direct replay reproduced the actual loop traces exactly, while the
four indicator decisions were unchanged. Treat this as a precision-sensitivity
boundary; only the decisions, not exact trajectories, transported robustly.

CF-I-OBS-001 then exposed a paired-control defect: HUGSIM `Camera` instances
share a mutable default dynamics dictionary, so the actor persisted into the
nominal no-actor render. This is retained as negative method evidence, not
misreported as a HUGSIM visual failure.

The frozen corrective repeat CF-I-OBS-002 accepted state-to-transform fidelity,
six-camera membership, and causal observation onset. It rejected spatial
localization: RGB support inside the projected `wlh.json` box plus 16 pixels
fell from about `0.98` to `0.48` as the actor approached. Asset inspection found
that the high-opacity Gaussian envelope is larger than the declared dimensions
and vertically offset from the transform origin. See
`docs/runs/hugsim_interaction_observation_indicators_002.md`.

CF-I-OBS-003 completed the planned localization split without relaxing the
threshold. The Gaussian asset envelope improved minimum close-range RGB support
coverage from about `0.48` to `0.66`, but still failed the frozen `0.90` gate.
Metadata geometry therefore contributes to the mismatch but is not the only
explanation; a centre-only Gaussian envelope also does not qualify as precise
spatial truth. See
`docs/runs/hugsim_interaction_observation_indicators_003.md`.

The first internal CF-I round is now closed with positive evidence, negative
evidence, and explicit boundaries. Do not add more CF-I scenes or tune opacity,
quantiles, dilation, or thresholds merely to turn O3 green.

The bounded supporting-receiver gate and CF-R transport experiment are now
complete. Their unresolved spatial-ground-truth and receiver-jitter boundaries
must be carried into every later association, distance, risk, or action claim.

This experiment may support only an adversarial ego-response capability claim.
It must not be generalized to realistic merging, yielding, or traffic-agent
behavior. IDM remains a later option if a qualified route becomes available.

Do not relabel independent ConstantPlanner trajectories as credible interaction,
and do not add a receiver or more scenes merely to produce curves.

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
- CF-M 001 accepted the narrow ConstantPlanner constant-speed state and
  controlled relative-motion relations: 108/108 transitions and all 110
  accumulated relation-check timestamps passed with zero reversal/tie. These
  are checks, not independent statistical samples. Overall evidence remains
  `down-weighted` because the state source is HUGSIM and the actor is scripted.
  See `docs/runs/hugsim_motion_metamorphic_001.md`.
- CF-O 001 rejected its camera-space measurement chain after diagnosing an
  inverted stored-height convention; this is method evidence, not a HUGSIM
  visibility failure.
- CF-O 002 accepted the narrow controlled-geometry and extreme two-level target
  RGB-support direction checks across all 37 frames. Overall evidence remains
  `down-weighted`: it is a corrective repeat using HUGSIM-produced state,
  calibration, and RGB, not a continuous visibility law or independent reality
  anchor. See `docs/runs/hugsim_occlusion_metamorphic_002.md`.
- CF-I-CAP-001 accepted narrow internal IDM and AttackPlanner response
  diagnostics, including a reachable AttackPlanner input and aligned-grid
  control. It rejected the released scene loop as temporally qualified
  interaction because its compared futures use `0.25 s` and about `0.1053 s`
  index steps. Overall evidence is `down-weighted`; independent ConstantPlanner
  trajectories remain rejected as interaction evidence.
- CF-I-STATE-001 validated T1--T4 on preregistered state-level controls. It
  accepted their narrow control discrimination and preserved the released
  time-grid and ConstantPlanner cases as negative evidence. Overall evidence is
  still `down-weighted`: the direct controller harness is not a rendered scene
  or realistic behavior.
- CF-I-LOOP-001 reproduced all four frozen control decisions inside the actual
  `planner.plan_traj` loop. It also found that exact AttackPlanner traces are
  sensitive to the loop's float32 state writeback, while the indicator
  decisions remained stable. This qualifies only pre-render planner-loop
  indicator transport; rendering and realism remain untested.
- CF-I-OBS-001 rejected its paired RGB measurement after diagnosing shared
  mutable camera dynamics that retained the actor in the no-actor control.
  CF-I-OBS-002 corrected only that contamination: state transform, camera
  membership, and causal onset were accepted, while projected metadata-box
  localization remained rejected and worsened with proximity. This is bounded
  internal state-to-observation evidence, not real-sensor equivalence.
- CF-I-OBS-003 projected a frozen opacity-qualified Gaussian centre envelope.
  It improved minimum localization coverage from about `0.48` to `0.66` but
  remained below the `0.90` gate. Both metadata-box and simple asset-envelope
  spatial-truth claims remain rejected; first-round CF-I is closed without
  further tuning.
- Independently recomputed planar geometry verifies only HUGSIM-declared state,
  not real-world state.
- Sparse4Dv3 is a provisional supporting receiver probe, not truth.
- HUGSIM RGB/semantic/depth and NC/TTC/PDMS are internal evidence and
  diagnostics, not independent reality references.
- Direct matched real–sim work remains a later, stronger path when source data
  are available; it is not a prerequisite for defining designed-counterfactual
  laws.

## Explicitly Deferred

- Do not run a target risk/planning/control experiment before that receiver and
  its allowed claims pass the new qualification gate.
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
