# Simulator Credibility Indicator Convergence

> Status: current metric-convergence direction. This document narrows the
> evidence collected from HUGSIM without defining a final credibility score or
> assigning HUGSIM a score on the future four-layer evidence chain.

## 1. The fitness-for-use question

The relevant question is not whether a receiver produces a numerically perfect
3D box. It is:

> Does the simulator preserve enough task information that the intended AD
> receiver produces the same scene relation, risk ordering, decision direction,
> and ultimately outcome as it would under the corresponding real condition?

An error is acceptable only relative to a declared use. A four-meter range
error may preserve `near < far`, but it may cross a braking or collision-
prediction boundary. Therefore no universal pixel, box, or meter threshold is
used as the final credibility threshold.

A matched real starting scene is a strong direct-equivalence design, not a
mandatory starting point for every counterfactual. Designed counterfactuals may
be evaluated without an exact real counterpart after the relevant metrics,
constraints, receivers, and uncertainty ranges are qualified using independent
reality evidence or testable laws. Their strongest claim is bounded causal and
decision robustness, not exact real–simulation equivalence.

## 2. Where the current experiment sits

The Sparse4Dv3 experiment is primarily a **task-level receiver-consistency
candidate**, more precisely simulator-internal task-response evidence.

It is not yet sensor-consistency evidence:

- the receiver consumes HUGSIM camera arrays, but there is no matched real RGB
  reference;
- array shape, preprocessing, intrinsics/extrinsics format, and temporal rate
  checks establish an input contract only;
- HUGSIM semantic, depth, and actor state are outputs under audit, not
  independent sensor truth;
- comparing Sparse4Dv3 to a HUGSIM actor box tests renderer/receiver/internal-
  state agreement, not agreement with reality.

The current evidence can later contribute to the planned four-layer evidence
chain, but the layers are not current project stages or a grading rubric:

| Future evidence family | Current contribution | Missing upgrade |
|---|---|---|
| Log reproduction | source gate and pose manifest only | matched real source observations and immutable identity |
| Sensor consistency | camera input contract and internal diagnostics only | matched real sensor reference or independent measurement |
| Task-level consistency | controlled receiver sensitivity, relation, ordering, and tracking | same frozen receiver on matched real/sim observations, or externally qualified instruments plus uncertainty-robust task conclusions |
| Closed-loop outcome credibility | HUGSIM loop and scoring diagnostics only | target planner/controller plus matched real/controlled-track outcome, or a separately qualified bounded robustness claim that is not direct real-outcome equivalence |

## 3. Current fit-for-use conclusion

The controlled Sparse4Dv3 evidence supports a bounded coarse-perception use:

- qualified actor presence is continuous in 43/44 controlled actor frames;
- near/far ordering is correct in 6/6 aligned pairs;
- same-lane/adjacent relation is correct in 43/44 actor frames;
- the dominant identity covers 100%, 83%, and 100% of associated far, near,
  and adjacent frames.

It does not yet support metric localization for planning:

- median XY error is 2.56 m for the far actor;
- median XY error is 4.24 m for the near actor;
- median XY error is 3.80 m for the adjacent actor;
- the near longitudinal bias is about 81% of its median configured range;
- the adjacent lateral bias is about 65% of the designed 4 m lane offset.

Thus the present answer to “does it meet AD needs?” is use-dependent:

| Intended use | Current answer |
|---|---|
| Actor presence and coarse scene understanding | bounded support |
| Near/far and same/adjacent risk ordering | bounded support |
| Short temporal identity continuity | bounded support |
| Metric 3D state consumed directly by a planner | not established |
| Braking, collision prediction, or control timing | not tested |
| Complete AD test-domain credibility | not tested |

## 4. Minimal converged candidate indicator set

The current evidence should converge around a small set of indicator families,
not continue accumulating unrelated proxy scores.

### A. Evidence validity gates

These are mandatory conditions, not quality scores:

- immutable input/run identity;
- exact receiver contract and frozen weights;
- camera/time/calibration/preprocessing completeness;
- complete history/future windows;
- absence of invalid padding, frame reuse, or unrecorded fallback.

Failure invalidates the affected claim before any accuracy metric is examined.

### B. Receiver observability and causal sensitivity

Candidate endpoints:

- critical-object positive-frame rate;
- missed-event duration;
- intervention effect relative to a paired no-injection baseline;
- positive and negative control separation.

This answers whether task information reaches the receiver, not whether its
metric value is correct.

### C. Task-relevant relation and ordering consistency

Candidate endpoints:

- same/adjacent/off-road relation agreement;
- front/rear/left/right relation agreement;
- near/far and risk-order pair agreement;
- top-risk-object identity agreement;
- approaching/receding and occlusion-relation agreement.

These ordinal endpoints are less sensitive to harmless rendering differences
than raw pixels, while remaining directly relevant to AD behavior.

### D. Metric and temporal consistency

Candidate endpoints:

- longitudinal/lateral/range bias and uncertainty;
- velocity and approach-rate error;
- dominant-track fraction, identity switches, missed-track gaps;
- visibility and occlusion transition timing.

Metric errors are normalized by a task margin only after the downstream task
boundary is defined. Examples include distance to a braking threshold, lateral
margin to a lane boundary, or time margin to an intervention event.

### E. Nuisance robustness and cross-scene coverage

Candidate endpoints:

- response stability across score/decision thresholds;
- false-response rate on labelled ego hood, vegetation, sign, shelter, shadow,
  and reconstruction-artifact regions;
- persistence of a false response;
- performance stratified by scene, camera, range, occlusion, and reconstruction
  support.

The normal scenes now have a fixed human-visible support audit over 14
detection-conditioned responses: 7 are visibly supported and 7 are nuisance
responses. This is enough to show that raw count/persistence is not a safe
standalone endpoint. It is not ODD precision/recall: the labels inspect HUGSIM
RGB rather than matched reality, and the sample cannot expose false negatives.

### F. External validity and task-equivalence qualification

The strongest direct upgrade is matched real-simulation task equivalence:

- same frozen receiver and complete input contract;
- paired differences for object discovery, relations, geometry, tracking, and
  risk ordering;
- pre-specified equivalence bounds and uncertainty intervals;
- decision/action invariance for the intended planner or controller;
- explicit receiver, ODD, task, and intervention applicability range.

It is one branch rather than a universal sequence gate. For designed
counterfactuals without an exact real counterpart, the validation instruments
must first be qualified on independent reality evidence, controlled
measurements, or testable physical/causal laws. The resulting claim is bounded
fitness-for-use or robustness across a declared uncertainty range, not that the
generated future is the unique real outcome.

## 5. Threshold rule

Every acceptance bound must come from one of three sources:

1. a downstream AD decision margin;
2. an independently justified measurement/annotation uncertainty;
3. a pre-specified real-simulation equivalence study design.

Do not choose a bound because it makes the current simulator pass. The former
2 m and 4 m lines remain visualization diagnostics only.

## 6. Near-term execution order

1. keep the frozen cross-scene Sparse4Dv3 response summary;
2. keep the fixed normal-scene human-visible target/nuisance audit;
3. do not turn its detection-conditioned 50% support result into ODD precision;
4. keep the completed validation-instrument qualification table and its two
   limited-use candidates: temporal/planar-geometry constraints and Sparse4Dv3
   ordinal response;
5. keep the qualified critical-object/risk-order partial-order task boundary;
   its numerical geometry, motion, rendering, and receiver uncertainty ranges
   remain unqualified and must not be replaced with convenient thresholds;
6. keep the published preregistration for ordinal metamorphic audit 001,
   labeling its 2x2 interventions as test-design coverage and preserving the
   frozen expected relations and reversal stop rules;
7. in parallel, keep source RGB recovery as the direct matched real–simulation
   upgrade rather than a gate on all designed counterfactuals;
8. run the declared five-condition matrix exactly once, then decide from its
   bounded result whether any later planner/control experiment is justified.

The detector-box/calibration root-cause investigation follows the cross-scene
summary. It should diagnose why absolute geometry is weak, but it does not
replace the task-relative credibility indicators above.
