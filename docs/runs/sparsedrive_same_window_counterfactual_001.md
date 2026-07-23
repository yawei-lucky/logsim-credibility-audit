# SparseDrive same-window lead counterfactual 001

Date: 2026-07-23

## Outcome

The matched `scene-0383` source-pose window was extended from four to eight
2 Hz frames. This supplied five fully warmed SparseDrive timestamps rather
than one. The same frozen receiver then processed:

1. official-sample real RGB;
2. factual HUGSIM RGB;
3. HUGSIM with the same RealCar asset 10 m ahead on the source path;
4. HUGSIM with that asset 5 m ahead on the source path.

The preregistered scalar response claim was **`rejected`**: the 5 m actor
produced less 3 s forward progress than the 10 m actor at only 3/5 warmed
timestamps, below the frozen 4/5 rule.

This does not make the experiment or HUGSIM globally failed. The held-fixed
stimulus and receiver response are valid observations. The negative result
shows that raw longitudinal endpoint is not a generally valid risk indicator
when the planner changes maneuver mode.

## Setup and controls

- source frames: `12, 18, 24, 30, 36, 42, 48, 54`;
- evaluation frames after four-frame warm-up: `30, 36, 42, 48, 54`;
- the actor followed the recorded source path at a scripted 10 m or 5 m
  forward arc-length gap;
- the background checkpoint, native reconstructed dynamics, camera poses,
  intrinsics, actor asset, receiver checkpoint, command, ego state and reset
  protocol were held fixed;
- the 5 m centre gap remained above the `3.288 m` non-overlap boundary implied
  by the declared ego and actor lengths;
- setup-only runs 001 and 002 were excluded before inference because their
  farther fixed/path placements mixed longitudinal distance with excessive
  lateral displacement within the window.

The actor is scripted and does not interact with ego or traffic. This is a
designed sensor/task stimulus, not realistic traffic behavior.

## Expanded factual domain discrepancy

`D_domain` compares the factual HUGSIM and real-input SparseDrive plans at the
same source timestamp.

| Frame | Plan ADE | Endpoint difference | Sim minus real 3 s forward | Mode equal |
|---:|---:|---:|---:|---:|
| 30 | `0.358 m` | `0.639 m` | `-0.639 m` | yes |
| 36 | `0.286 m` | `0.583 m` | `-0.582 m` | yes |
| 42 | `0.023 m` | `0.067 m` | `+0.067 m` | yes |
| 48 | `0.055 m` | `0.059 m` | `-0.025 m` | yes |
| 54 | `0.197 m` | `0.392 m` | `+0.371 m` | yes |

Across the warmed window, factual plan ADE ranged from `0.023` to `0.358 m`;
absolute forward-domain discrepancy had median `0.371 m` and maximum
`0.639 m`. All five factual real/sim mode selections agreed. This is an
empirical same-window range, not an externally qualified equivalence
threshold.

## Counterfactual response

Signed effects use negative values for less forward progress.

| Frame | `E_CF` weak minus factual | `E_CF` strong minus factual | Strong minus weak | Modes real / factual / weak / strong |
|---:|---:|---:|---:|---|
| 30 | `-0.823 m` | `-6.110 m` | `-5.287 m` | `3 / 3 / 3 / 0` |
| 36 | `-1.712 m` | `-3.195 m` | `-1.484 m` | `3 / 3 / 3 / 0` |
| 42 | `-0.467 m` | `-2.044 m` | `-1.577 m` | `3 / 3 / 3 / 0` |
| 48 | `-0.645 m` | `+0.604 m` | `+1.249 m` | `2 / 2 / 2 / 3` |
| 54 | `-0.844 m` | `-0.753 m` | `+0.091 m` | `2 / 2 / 2 / 2` |

The median strong-minus-weak response was `-1.484 m`, much larger than the
measured `0.000204 m` final-forward repeat envelope. The strong effect exceeded
the same-frame absolute factual domain discrepancy at all 5/5 warmed
timestamps; its median absolute magnitude was `2.044 m`.

Those scale facts establish that the receiver responded materially. They do
not rescue the rejected directional claim:

- frames 30--42 followed the expected direction;
- at frame 48 the strong condition switched planning mode, moved farther left
  (`-2.982 m` versus `-2.574 m`) and also progressed `1.249 m` farther than
  weak;
- at frame 54 all modes matched, but strong still progressed `0.091 m` farther.

The strong sequence's repeat difference also exceeded the earlier fixed
`1e-4 m` engineering tolerance (`0.000204 m`). The analysis used the larger
measured envelope rather than hiding it; it remains negligible relative to
the metre-scale effects.

## Indicator lesson

The failed scalar rule identifies a qualification condition:

> Forward-progress monotonicity may be tested only while route branch and
> maneuver choice remain comparable. If a closer actor changes the maneuver,
> more forward progress may reflect avoidance rather than lower perceived
> risk.

A successor indicator should therefore combine:

- route-relative progress;
- predicted actor clearance or path conflict;
- maneuver/mode identity and score;
- longitudinal response only within comparable maneuver branches.

This refinement is prospective. It must not be used after the fact to relabel
the preregistered 3/5 result as accepted.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| The held-fixed 10 m/5 m stimuli reached the same SparseDrive receiver and caused effects far beyond repeat sensitivity | `accepted` | one scene, one target AD, scripted actor |
| The 5 m actor consistently causes less raw forward progress than the 10 m actor | `rejected` | only 3/5 warmed timestamps; two observed reversals |
| Raw final-forward progress is a maneuver-independent risk indicator | `rejected` | mode switch and lateral response invalidate that interpretation |
| The observed effect magnitude is externally real-world-valid | `down-weighted` | no real counterfactual counterpart or qualified task threshold |
| This establishes realistic interaction, collision validity or AD safety | `rejected` | outside experiment capability |

Overall evidence is `down-weighted`: it supplies a strong receiver-response
observation and a useful negative metric result, but not a real-world
counterfactual truth.

## Artifacts

```text
artifacts/hugsim_source_anchor/scene-0383-sparsedrive-real-window-002
artifacts/hugsim_counterfactual_metadata/scene-0383-source-window-lead-run003
artifacts/hugsim_matched_pose/scene-0383-frame000{12,18,24,30,36,42,48,54}-source-window-cf-run001
artifacts/sparsedrive_real_sim_factual/scene-0383-source-window-run002
artifacts/sparsedrive_same_window_counterfactual/scene-0383-source-window-run002
artifacts/sparsedrive_same_window_counterfactual/scene-0383-source-window-run002/sparsedrive_same_window_counterfactual_effects.png
artifacts/sparsedrive_same_window_counterfactual/scene-0383-source-window-run002/sparsedrive_same_window_counterfactual_contact_sheet.png
artifacts/sparsedrive_same_window_counterfactual/scene-0383-source-window-run002/sparsedrive_same_window_counterfactual_front_h264.mp4
```
