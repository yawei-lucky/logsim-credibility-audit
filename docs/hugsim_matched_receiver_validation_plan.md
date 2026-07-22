# HUGSIM Matched Real–Simulation Receiver Validation Plan

> Purpose: turn HUGSIM from a visual counterfactual demonstration into the
> first evidence carrier for validating whether a world simulator is fit for
> intelligent-driving testing.

This is a bounded next-stage plan, not the final credibility metric.

## Scope of This Plan

This document specifies the strongest **direct matched real–simulation**
evidence branch. Its Source Anchor Gate is mandatory before a claim of direct
real–simulation equivalence for the selected factual condition, but it is not a
universal prerequisite for every designed counterfactual experiment.

A counterfactual without an exact factual counterpart may proceed under the
two-level principle in `docs/research_guiding_principles.md` once its metrics,
constraints, receivers, and uncertainty ranges have an explicit qualification
basis. Such a run can support bounded causal-consistency and robustness claims;
it cannot be relabelled as direct matched real–simulation evidence.

## Research Question

For a fixed receiver, task, ODD, and intervention range:

> Does the receiver obtain sufficiently consistent task information from the
> real log and its matched HUGSIM reconstruction to produce equivalent risk
> ordering and response direction within pre-specified bounds—and task outcome
> only where a matched real closed-loop counterpart exists?

## Receiver Convergence

Human and AD receivers are not required to use identical internal visual
cues. A six-camera surround interface controls available coverage and timing,
not attention or perception mechanisms.

Use two separate paired comparisons:

```text
AD evidence:    same frozen AD receiver(real, simulation)
Human evidence: same participant or matched population(real, simulation)
```

Only then compare whether each receiver preserves its own real-to-simulation
relationship, and whether the real–simulation gaps and intervention-effect
directions converge across receiver types. Raw human and AD outputs need not
agree in reality. Cross-receiver convergence is supporting robustness
evidence, not a mandatory substitute for either receiver's own evidence.

Freeze and record the receiver input contract before comparison. This includes
every input modality, calibration, preprocessing operation, frame history,
timestamp/clock convention, and state input used by the receiver. If only the
six RGB cameras can be matched, the result is camera-only receiver evidence,
not evidence for a multimodal AD stack that also consumes lidar, radar, maps,
localization, or vehicle state.

## Stage A — Source Anchor Availability Gate

Before any real–simulation claim, require:

- real RGB for the selected timestamp and all six cameras;
- source sample/sample-data identity or an equivalent immutable mapping;
- per-camera timestamp, intrinsics, and camera-to-world pose;
- identification of train versus held-out reconstruction views;
- native dynamic-object identity and pose where visible;
- hashes for processed real observations and reconstruction metadata.

The released `scene-0383` package currently provides 180 timestamps and six
camera calibration/pose records per timestamp, but not the referenced real RGB
files or original nuScenes sample tokens. Therefore the current gate is
blocked: it has frame-index candidates, not a complete real–simulation pair.

Keep three decisions separate:

1. **Availability ready** — required source observations, identities,
   calibration, timing, dynamics, and reconstruction assets exist and pass
   format/integrity checks.
2. **Pairing integrity pass** — every selected real/sim camera and time step is
   one-to-one matched on immutable identity, timestamp, intrinsics, pose,
   resolution, native dynamic state, preprocessing, and recorded hashes.
3. **Receiver equivalence pass** — every pre-specified primary receiver
   endpoint and its uncertainty interval satisfies its pre-specified
   equivalence bound; a missing primary endpoint fails closed.

Availability is only a material gate. It does not itself establish sensor
consistency, receiver equivalence, or simulator credibility.

## Stage B — Exact Matched-Pose Rendering

After obtaining the source images and provenance:

1. Select a split-derived test candidate timestamp, beginning with frame
   `00004` if its full six-camera source set is recovered. Confirm the
   checkpoint's training provenance before calling that timestamp genuinely
   held out from reconstruction training.
2. Render each camera using that frame's `meta_data.json` intrinsics and
   `camtoworld` directly.
3. Load the released native dynamic model and the timestamp-specific native
   dynamic pose. Removing it would confound the comparison with a missing
   real-world actor.
4. Record pose, calibration, timestamp, visibility, and image hashes in a pair
   manifest.

Do not call the current closed-loop reset observation a matched-pose render.
The standard simulation camera template includes a camera rectification offset
and calibration differences relative to reconstruction metadata.

This first single-frame anchor can test only spatial, semantic, visibility,
and per-frame receiver outputs. It cannot support motion direction, response
time, planning, or control claims.

## Stage B2 — Matched Temporal Clip

Before testing matched real–simulation temporal or behavioral equivalence
endpoints, recover and render a contiguous matched real–simulation clip. Freeze
and verify:

- per-camera capture timestamps and inter-camera timing offsets;
- camera ordering, intrinsics, extrinsics, resize/crop, and normalization;
- clip start/end, frame history, and dropped-frame handling;
- ego pose, speed, vehicle state, route/navigation input, and every other
  receiver input used by the selected AD model or stack;
- receiver weights, software version, random seeds, and deterministic settings
  where applicable.

Without this temporal input contract, evidence remains single-frame or
camera-only and output differences cannot be attributed solely to real versus
simulated observations.

## Stage C — Reference Variables and Receiver Endpoints

Pixel similarity may remain a diagnostic, but acceptance is driven by task
information and behavior defined at two distinct levels.

Reference task variables describe the matched scene independently of a
receiver:

- relative bearing and distance band;
- same-lane, adjacent-lane, and drivable-corridor relation;
- occluding/occluded and visible/not-visible relation;
- approaching/receding and risk-intensity ordering;

Establish these references from independent real-log annotation or
measurement, or from a pre-defined blinded review protocol. Record the
coordinate frame, annotation procedure, error bounds, and uncertainty. Do not
derive the reference solely from HUGSIM internal state and then use it to
validate HUGSIM.

Receiver endpoints describe what the human or AD receiver produces:

- critical-object discovery and identity;
- receiver-specific risk score mapped to a pre-defined common risk order;
- `go / slow / stop`, brake, and steer response direction;
- response time relative to a defined event;
- task completion and safety outcome.

Define the mapping from human and AD outputs to the common endpoint categories
before seeing the comparison results. Do not use a receiver's own risk output
as the reference truth used to judge that same output.
For human critical-object discovery, predefine an observable response such as
a button press, verbal identification, or task action; gaze alone does not
establish discovery.

## Stage D — 2×2 Receiver Evidence Layout

| Receiver | Real matched observation | Simulated matched observation |
|---|---|---|
| Frozen AD receiver with fully matched required inputs | perception, risk, plan, control | same input contract and outputs |
| Human participant/group | observation/decision response | same display, FOV, timing, and task |

The initial human study is an open-loop paired observation/decision study.
Real-log playback is not a controllable real-world closed loop. A human
closed-loop credibility claim requires matched real driving, comparable
naturalistic events, or a controlled-track baseline.

Prefer a within-participant, randomized or counterbalanced study; blind the
real/simulation label where practical. Pre-specify sample size, exclusions,
primary endpoints, and equivalence bounds. A single-participant pilot may
validate the procedure, but it cannot establish population-level consistency.

## Stage E1 — Real-Anchored Controlled Counterfactuals

Within the direct matched-anchor branch, only after Availability is ready and
Pairing Integrity passes for the factual anchor:

- introduce positive and negative controls;
- vary object distance, lane relation, visibility, or approach rate in
  pre-specified levels;
- test whether real-anchored task variables and each receiver under study
  change in the expected direction and ordering;
- retain failures and boundary cases as evidence for the general framework.

A counterfactual branch has no real pixel counterpart unless the same
intervention is reproduced in controlled real driving or on a test track.
Without that counterpart, it is not direct real–simulation consistency
evidence. If the instruments have an independent qualification basis, the
branch may still support the bounded claims described below.

## Stage E2 — Designed Counterfactuals Without an Exact Real Counterpart

These experiments do not wait for an exact matched starting scene when their
purpose is mechanism audit, stress testing, or robustness analysis. Before a
claim is accepted, record:

- which physical, geometric, visibility, or causal constraints define an
  admissible intervention;
- how each metric or receiver was qualified independently of the current
  HUGSIM outcome;
- the plausible parameter and model uncertainty range;
- whether materially different qualified receivers preserve the same task
  relation, critical-object ordering, or response direction;
- whether the downstream conclusion remains stable across the declared range;
- the strongest allowed claim and the unavailable direct-equivalence claim.

Agreement inside a single HUGSIM state/render/metric loop is insufficient.
Conversely, the exact unobserved trajectory need not be claimed as truth: the
relevant result is whether a bounded task conclusion is physically admissible,
causally coherent, and robust to plausible world-model uncertainty.

## Statistical Interpretation

- Define acceptable real–simulation differences before looking at results.
- Use paired differences and uncertainty intervals.
- For ranking, report rank agreement or top-risk agreement.
- For discrete actions, report disagreement and chance-corrected agreement.
- For response time, report paired differences relative to the same event.
- Use equivalence testing with pre-specified bounds; “not statistically
  significant” is not evidence of equivalence.
- Limit conclusions to the tested receiver, task, ODD, and intervention range.

Without a real closed-loop counterpart, do not claim direct real closed-loop
equivalence. A separately qualified designed counterfactual may still support
bounded planner/control robustness or stress-test fitness when the evidence
network covers intervention validity, uncertainty sensitivity, receiver
dependence, and outcome stability.
