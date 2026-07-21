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
| Task-level consistency | controlled receiver sensitivity, relation, ordering, and tracking | same frozen receiver on matched real and simulated observations |
| Closed-loop outcome credibility | HUGSIM loop and scoring diagnostics only | target planner/controller plus matched real or controlled-track outcome |

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

The normal scenes currently provide response and persistence baselines only.
Independent labels are required before these become precision or false-positive
metrics.

### F. Matched real-simulation task equivalence

This is the required credibility upgrade:

- same frozen receiver and complete input contract;
- paired differences for object discovery, relations, geometry, tracking, and
  risk ordering;
- pre-specified equivalence bounds and uncertainty intervals;
- decision/action invariance for the intended planner or controller;
- explicit receiver, ODD, task, and intervention applicability range.

## 5. Threshold rule

Every acceptance bound must come from one of three sources:

1. a downstream AD decision margin;
2. an independently justified measurement/annotation uncertainty;
3. a pre-specified real-simulation equivalence study design.

Do not choose a bound because it makes the current simulator pass. The former
2 m and 4 m lines remain visualization diagnostics only.

## 6. Near-term execution order

1. freeze the cross-scene Sparse4Dv3 response summary;
2. label a small fixed normal-scene subset for native objects and nuisance
   regions;
3. calculate labelled nuisance robustness and threshold stability;
4. define one downstream task boundary, preferably lane relation plus critical-
   object risk ordering before metric planning;
5. when source RGB becomes available, run the same endpoints on matched real
   and simulated inputs;
6. only then add planner/control equivalence and closed-loop outcomes.

The detector-box/calibration root-cause investigation follows the cross-scene
summary. It should diagnose why absolute geometry is weak, but it does not
replace the task-relative credibility indicators above.
