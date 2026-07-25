# SparseDrive natural-actor receiver bridge 001

Date: 2026-07-25

## Outcome

This preregistered pilot connected the prior source-side dynamic-support result
to a target AD consequence. The same frozen SparseDrive processed one
four-frame, approximately 2 Hz history under three RGB conditions:

1. official real source RGB;
2. exact-pose HUGSIM factual RGB with the released native dynamic;
3. the same HUGSIM render with the native dynamic path omitted.

Only frame `44` was judged. It had a complete four-frame receiver history
`26, 32, 38, 44` and prior source-side support for the native dynamic in
`CAM_FRONT_LEFT`. Each condition was run twice after an independent reset.
The three preceding warm-up frames are not claimed to form an independently
held-out four-frame test sequence.

The result separates two claims:

- the native dynamic caused a repeat-resolved SparseDrive planning response:
  `accepted`;
- adding that dynamic moved the plan toward the matched real-RGB response:
  `rejected`.

The experiment as a whole remains `down-weighted`. It has one endpoint, one
native actor, one reconstruction and one target AD, and the static
reconstruction is not actor-free.

## Frozen comparison

Camera order, timestamps, source poses, intrinsics, provisional model-to-camera
calibration, pose-derived ego state, command, future route reference,
SparseDrive checkpoint, adapter and reset procedure were held fixed.

The endpoint's native six-waypoint final plan was the primary output.
Six-waypoint ADE was the primary distance. Every cross-condition range below
contains all four `2 × 2` reset pairings.

| Comparison at frame 44 | Plan ADE range | Plan FDE range |
|---|---:|---:|
| factual ↔ static | `0.094668–0.094669 m` | `0.179851–0.179853 m` |
| real ↔ factual | `0.081572–0.081573 m` | `0.203609–0.203611 m` |
| real ↔ static | `0.062376–0.062376 m` | `0.068924–0.068924 m` |

The largest within-condition repeat ADE was only
`8.04 × 10⁻⁷ m`. Therefore the factual–static effect is not numerical reset
noise.

The primary real-gap ranges were strictly ordered in the opposite direction
to the preregistered positive claim:

```text
real ↔ static ADE < real ↔ factual ADE
```

At the 3 s endpoint:

- factual minus real was `+0.193 m` forward and `+0.065 m` right;
- static minus real was `+0.013 m` forward and `+0.068 m` right;
- omitting the native dynamic reduced the factual plan by about `0.180 m`
  forward.

All six runs selected SparseDrive planning mode `3`. The negative primary
result is therefore not caused by switching the selected planning mode.

## Why this matters

The prior image-support audit was locally positive at the same endpoint:

- `80.5%` of factual-minus-static difference energy was inside the exact source
  dynamic mask;
- `95.8%` was inside a 16-pixel dilation;
- the energy-centroid error was `2.33 px`;
- as a post-hoc diagnostic, factual RGB improved source-mask photometric MAE
  over static RGB by `32.8%`.

Nevertheless, the target-AD plan moved farther from the real-input plan.
Thus correct camera membership, overlapping pixel support and even improved
local photometric agreement are not sufficient evidence of task-level
equivalence. A receiver-consequence indicator adds information that the
pixel-support indicator cannot provide.

This does not establish that the native dynamic renderer is the sole cause.
The static crop already contains person-like residual structure, so factual
RGB may contain duplicated or over-strong actor information. SparseDrive
domain sensitivity and the partial source-mask reference are additional
uncertainties. These are plausible mechanisms, not proven diagnoses.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| The native dynamic path causes a SparseDrive plan response beyond reset sensitivity | `accepted` | one fully warmed endpoint; effect ADE about `0.0947 m` versus repeat `8.04e-7 m` |
| The selected planning mode is invariant across the three conditions | `accepted` | mode `3` in all six runs |
| Adding the native dynamic moves the plan toward the matched real-input plan | `rejected` | real–factual ADE and FDE are both strictly larger than real–static |
| Pixel-support agreement is sufficient for target-AD task equivalence | `rejected` | positive image support coexists with the negative task-direction result |
| The static control is an actor-free world | `rejected` | visible person-like residual structure remains |
| This proves SparseDrive correctness, sensor equivalence, general HUGSIM credibility or AD safety | `rejected` | scope exceeds one receiver endpoint |

## Artifacts

```text
docs/runs/sparsedrive_natural_actor_bridge_preregistration_001.json
artifacts/hugsim_source_anchor/scene-0383-natural-actor-window-run001
artifacts/hugsim_matched_pose/scene-0383-frame000{26,32,38,44}-natural-actor-bridge-run001
artifacts/hugsim_matched_pose/scene-0383-natural-actor-factual-window-run001
artifacts/hugsim_matched_pose/scene-0383-natural-actor-static-window-run001
artifacts/sparsedrive_real_source/scene-0383-natural-actor-{real,factual,static}-run001
artifacts/sparsedrive_natural_actor_bridge/scene-0383-frame00044-run003
```

Primary inspection files:

- `sparsedrive_natural_actor_bridge.png`: source/factual/static actor crops,
  isolated dynamic support, the three native plans and distance comparison;
- `sparsedrive_natural_actor_bridge_audit.json`: all reset pairings, held-fixed
  checks, preregistered decisions and evidence boundaries.

## Next boundary

Do not search nearby timestamps or tune the metric merely to obtain a positive
direction. This pilot has already demonstrated the intended indicator logic:
pixel-level positive evidence can coexist with task-level negative evidence.

Before treating dynamic removal as an actor-free counterfactual, a later
experiment needs either a leakage-bounded static control or another source
scene/object with clean static–dynamic separation. If existing data cannot
supply that control, retain this result as negative method evidence and defer
the generality upgrade rather than forcing another same-scene curve.
