# Codex Next Task — Task-Boundary Qualification 001

> This is the only current milestone. Do not run another HUGSIM scene or
> closed-loop condition until this gate is frozen.

## Objective

Turn the first credibility-method qualification into one externally defensible
task or decision boundary. The boundary must state what AD-relevant difference
would change the intended conclusion; it must not be inferred from the HUGSIM
result that it will later judge.

Primary method records:

```text
CREDIBILITY_VALIDATION_METHOD.md
docs/runs/credibility_method_qualification_001.md
docs/runs/credibility_method_qualification_001.json
```

## Why this is next

Method Qualification 001 is complete using existing evidence only:

- known coordinate, horizon and action-to-state failures were detected;
- narrow motion, visibility and ordinal positive controls were retained;
- response magnitude, response direction and real-world magnitude were kept
  separate;
- pixel-positive/task-negative and interface-positive/state-negative cases
  were not collapsed into one score;
- the method is overall `down-weighted`, because the challenge set is
  retrospective and no source-independent task acceptance boundary exists.

The vehicle-state transition remains an engineering blocker for a future live
closed-loop experiment, but qualifying it now would not answer which task
conclusion the loop is meant to support.

## Single gate

Choose one task construct and freeze its bounded claim card:

```text
S: simulator/version/interface
T: intended AD testing use
Ω: scene and operating range
A: target receiver
I: intervention and held-fixed variables
Y: task relation or outcome
Θ: qualified uncertainty axes
ε: task/decision acceptance boundary
```

Preferred first construct: **critical-object/conflict ordering and the
resulting planning-direction or maneuver decision**. Do not use pixel error,
raw forward endpoint, HUGSIM TTC/PDMS, or a weighted credibility score as the
boundary.

The gate passes only when:

1. the target task consequence is explicit;
2. the boundary source is independent of the HUGSIM output under judgment;
3. missing numerical calibration is recorded rather than invented;
4. the required `G/F/Q/U/O` evidence items are declared;
5. a prospective challenge not used to form Method 001 is selected.

## Bounded work

Use existing documents and external task/vehicle/receiver evidence only as
needed. Produce a short claim card and boundary-qualification record.

Do not yet:

- run or tune a HUGSIM scene;
- change SparseDrive or add another AD receiver;
- implement a new vehicle model, PID/MPC controller, or state provider;
- set `ε` from the observed `D_domain`, `E_CF`, or desired pass result;
- claim real-world equivalence or AD safety.

## Decision after the gate

- If a defensible task boundary is qualified, preregister one prospective
  high-information HUGSIM test and qualify only the execution components it
  actually needs.
- If only a qualitative/ordinal boundary is defensible, run an ordinal
  robustness test and limit the conclusion accordingly.
- If no boundary can be defended, retain Method 001 as a diagnostic framework
  and obtain the minimal real annotation, task margin, or controlled reference
  before another closed-loop experiment.

## Stable guardrails

- Evidence is a non-compensatory network, not a global score.
- Use only `accepted`, `down-weighted`, and `rejected` for evidence decisions.
- A `rejected` claim remains useful negative method evidence.
- Local repeat error is not a real-world tolerance.
- A designed counterfactual need not have an exact real counterpart, but its
  judging instruments and uncertainty ranges need an independent basis before
  supporting real-world fitness.
