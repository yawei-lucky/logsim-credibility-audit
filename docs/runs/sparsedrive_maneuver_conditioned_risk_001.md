# SparseDrive maneuver-conditioned risk refinement 001

Date: 2026-07-25

## Decision

This is a **prospective indicator refinement using existing native outputs**.
It does not rescore the preregistered same-window experiment. The original
claim that the 5 m actor should always cause less 3 s forward progress than the
10 m actor remains `rejected` at `3/5`.

The refinement is overall `down-weighted`. Native candidate-mode decomposition
is qualified as an engineering diagnostic. A static current-actor clearance is
not qualified as a dynamic-risk indicator.

## Inputs and held-fixed scope

- scene: official HUGSIM `scene-0383` source window;
- fully warmed source frames: `30, 36, 42, 48, 54`;
- receiver: unchanged SparseDrive-S Stage2;
- conditions: HUGSIM factual, 10 m path-gap actor (`weak`) and 5 m path-gap
  actor (`strong`);
- source audit:
  `artifacts/sparsedrive_same_window_counterfactual/scene-0383-source-window-run002/`;
- refinement output:
  `artifacts/sparsedrive_maneuver_conditioned_risk/scene-0383-source-window-run002/`.

No scene was rendered again and no receiver inference was rerun. The analysis
loads the recorded native `planning[3 commands, 6 modes, 6 waypoints, 2 axes]`,
`planning_score[3, 6]`, selected final plan, and declared actor transforms.
Checkpoint, adapter, command, ego state, calibration and future reference
remain those validated by the source audit.

## Prospective indicator form

The refinement intentionally avoids a weighted risk score. For every timestamp
it reports a non-compensatory response vector:

1. selected native mode and its score margin;
2. selected-plan route-relative 3 s endpoint progress;
3. strong-minus-weak progress for each of the six fixed candidate modes;
4. the extra contribution caused by choosing a different mode;
5. plan-centreline distance to the current declared actor footprint, retained
   only to test whether that geometry construct is usable.

For weak-selected mode \(m_w\), the selected endpoint response is decomposed
exactly as:

```text
selected strong − selected weak
  = (strong mode m_w − weak mode m_w)
  + (strong selected mode − strong mode m_w)
```

This separates a within-mode response from a mode-selection effect. Native
mode IDs are not assigned post-hoc semantic names such as “follow” or
“lane-change”.

## Quantitative result

The maximum selected-plan repeat variation was `0.000204 m`. Across all native
candidates it was `0.000222 m`; the maximum planning-score repeat difference
was `5.66e-7`. The observed factual real–sim forward-domain maximum remained
`0.639 m`, used only as a one-slice diagnostic scale rather than an acceptance
threshold.

| Frame | Weak→strong mode | Selected strong−weak forward | Fixed weak-mode response | Mode-selection contribution | Six-mode result | Interpretation |
|---:|---:|---:|---:|---:|---|---|
| 30 | 3→0 | `-5.287 m` | `-6.133 m` | `+0.846 m` | all six `[-6.775, -4.319] m` | mode switched, but every fixed mode still reduced progress |
| 36 | 3→0 | `-1.484 m` | `-2.621 m` | `+1.137 m` | all six `[-2.621, -1.939] m` | same candidate-wide direction |
| 42 | 3→0 | `-1.577 m` | `-2.569 m` | `+0.992 m` | all six `[-2.946, -1.648] m` | same candidate-wide direction |
| 48 | 2→3 | `+1.249 m` | `-0.366 m` | `+1.615 m` | all six `[-0.406, -0.269] m` | mode selection masks candidate-wide slowing |
| 54 | 2→2 | `+0.091 m` | `+0.091 m` | `0.000 m` | all six `[+0.046, +0.228] m` | genuine same-mode/candidate-wide local reversal |

The mode-score margins ranged from `0.000170` to `0.003600`, all above the
measured score-repeat envelope. Thus the recorded selections are not explained
by reset-scale numerical variation. The scores are not calibrated driving-risk
probabilities.

Frames `30, 36, 42` had candidate-wide less-progress effects for which even the
smallest of the six mode effects exceeded the observed `0.639 m` domain scale.
Frame `48` retained candidate-wide less progress, but its `0.269–0.406 m`
magnitude was below that scale. Frame `54` retained a candidate-wide reversal
above repeat variation but below the observed domain scale.

## What the two reversals mean

Frame `48` is a **selection confound**, not evidence that every native plan
became more aggressive. Holding each mode ID fixed, all six strong-condition
plans ended less far forward. The final endpoint reversed because the selected
mode changed from `2` to `3`, adding `1.615 m`.

Frame `54` is different. The selected mode stayed `2`, and every fixed mode
ended slightly farther forward under the strong condition. It therefore cannot
be explained by a mode switch or repeat noise. With no qualified external
response range, it remains a bounded negative observation rather than proof
that either HUGSIM or SparseDrive is globally wrong.

## Failed clearance component

The attempted current-state clearance measures the distance between the
predicted ego centreline and the actor rectangle **at the current timestamp**.
It excludes the ego footprint and does not time-align future actor motion.

It saturated at zero in `4/5` strong-condition frames and did not distinguish
the frame-48 candidate modes. This is expected when a future plan is compared
with a moving actor frozen at its current position. Therefore:

- using this quantity as dynamic risk, TTC or collision clearance is
  `rejected`;
- it may remain a visualization of current declared geometry only;
- the minimum replacement requires complete time-aligned future actor states,
  an ego footprint and valid-horizon coverage reporting.

No threshold or weighted combination is introduced to hide this failure.

## Indicator qualification

| Tool | Decision | Strongest allowed use | Missing for stronger use |
|---|---|---|---|
| native candidate/score decomposition | `accepted` | distinguish fixed-mode response from mode-selection contribution; compare margins with repeat sensitivity | candidate semantics and real-world correctness |
| route-relative endpoint progress | `down-weighted` | conditional direction within explicit comparable modes | task acceptance range and real response reference |
| current actor static clearance as dynamic risk | `rejected` | current-geometry visualization only | future actor states, time alignment, ego footprint and independent 3D truth |
| native score margin | `accepted` | numerical selection stability relative to local repeat variation | score calibration and safety meaning |

Only the candidate decomposition and score-margin check qualify as reusable
diagnostic tools. Neither is an external risk judge.

## Evidence decision

### Accepted

- all five selected responses are exactly reconstructed from fixed-mode and
  selection contributions;
- frame `48` is isolated as a mode-selection confound;
- frame `54` is isolated as a candidate-wide within-mode reversal;
- native selected plans exactly equal their recorded selected candidates.

### Down-weighted

- candidate-wide slowing at frames `30–42` is strong simulator/receiver-internal
  directional evidence, but comes from one scene, one receiver and a scripted
  actor;
- the one-slice factual domain scale is not an externally qualified threshold.

### Rejected

- retroactively converting the original `3/5` decision into a pass;
- treating forward endpoint alone as a maneuver-independent risk metric;
- treating current-static actor clearance as physical TTC, collision,
  realistic avoidance or AD safety;
- claiming HUGSIM credibility from this receiver response alone.

## Reproduction

```bash
env MPLCONFIGDIR=/tmp/matplotlib-sparsedrive-maneuver \
  /home/yawei/miniforge3/envs/sparse4d-audit/bin/python \
  scripts/analyze_sparsedrive_maneuver_conditioned_risk.py \
  --same-window-audit \
  artifacts/sparsedrive_same_window_counterfactual/scene-0383-source-window-run002/sparsedrive_same_window_counterfactual_audit.json \
  --output \
  artifacts/sparsedrive_maneuver_conditioned_risk/scene-0383-source-window-run002
```

The output directory also contains the machine-readable audit JSON, a CSV
decomposition table and the four-panel diagnostic plot.
