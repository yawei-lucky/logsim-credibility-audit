# CF-I-STATE-001 state-level indicator preregistration

## Purpose

Validate four CF-I audit indicators against named positive and negative
controls before rendering a scene. The research product is indicator evidence,
not a repaired or passing HUGSIM result.

Exploratory state probes were used to select a deterministic responder state,
stimulus and run length. They are not formal output. The conditions, tolerances
and stop rule in the accompanying JSON are frozen before the formal run.

## Design

- HUGSIM revision: `adeca402cad4af8635e13d0a105e2fee6a14de85`.
- One `AttackPlanner` responder, `best_k=1`, replanned every transition.
- 24 transitions; ego speed changes from `0.5 m/s` to `0` at declared index 8.
- Released prediction grid is the known time negative; an index-aligned grid is
  the positive control.
- A stimulus applied one transition early is the causal-order negative.
- `ConstantPlanner` is the known no-online-response negative.

## Frozen indicators

| ID | Check | Known negative | Positive control |
|---|---|---|---|
| CF-I-T1 | compared future indices represent the same time | released grid | aligned grid |
| CF-I-T2 | responder does not diverge before declared stimulus | one-step-early stimulus | stimulus at declared index |
| CF-I-T3 | a responsive mechanism changes after stimulus | ConstantPlanner | aligned AttackPlanner |
| CF-I-T4 | displacement agrees with speed over world time and declared acceleration range | released grid | aligned grid |

If any indicator cannot distinguish its named controls, stop before rendering
or adding an AD receiver. Any accepted result is limited to this deterministic
state-level construction.

Machine-readable preregistration:
`docs/runs/hugsim_interaction_state_preregistration_001.json`.
