# SparseDrive matched factual turning-window audit 001

Date: 2026-07-25

## Outcome

A second, non-overlapping real–HUGSIM factual window was preregistered and run
with the same frozen SparseDrive receiver contract as the prior window. It was
selected from real source poses before inspecting the new renders or AD
outputs:

- source frames: `60, 66, 72, 78, 84, 90, 96, 102` at 2 Hz;
- fully warmed evaluation frames: `78, 84, 90, 96, 102`;
- source-pose heading change: about `41.8°`, versus about `6.5°` in the prior
  straight/turn-entry window;
- all five warmed commands were source-derived left-turn commands.

The checkpoint, config, adapter, reset procedure, camera order, calibration,
ego-state construction, commands and recorded future-path reference were held
fixed. All 48 official-source RGB images were fetched, HUGSIM rendered the same
eight declared source poses, and both sides completed independent-reset
SparseDrive inference.

This is a useful external-validity increment, but the overall decision remains
`down-weighted`: both windows come from one reconstruction, use one target AD,
and have no externally qualified task-equivalence threshold.

## Cross-window result

Only frames with a complete four-frame receiver history enter the comparison.

| Fully warmed result | Straight/turn-entry | Sustained left turn |
|---|---:|---:|
| frames | `30,36,42,48,54` | `78,84,90,96,102` |
| repeat envelope | `6.68e-6 m` | `1.34e-5 m` |
| mean real–sim plan ADE | `0.184 m` | `0.360 m` |
| mean real–sim plan FDE | `0.348 m` | `0.754 m` |
| maximum real–sim plan FDE | `0.639 m` | `1.047 m` |
| mean 3 s forward shift, sim minus real | `-0.162 m` | `+0.683 m` |
| mean 3 s right shift, sim minus real | `-0.005 m` | `-0.307 m` |
| real/sim selected-mode agreement | `5/5` | `5/5` |
| warmed six-camera mean SSIM | `0.3836` | `0.3828` |

Relative to the first window, the turning-window mean domain ADE was `1.96×`
and mean domain FDE was `2.17×`. Every warmed discrepancy exceeded its local
repeat envelope.

The signed turning-window shift was also consistent at all five warmed
timestamps: HUGSIM RGB caused the same SparseDrive to plan farther forward and
farther left than real RGB. Because the selected planning mode remained equal
on both sides at all five timestamps, this specific pattern is not explained
by a real/sim mode-selection switch.

This does **not** show that the HUGSIM plan is physically wrong. It shows that
the receiver's factual domain difference varies materially with the observed
maneuver and has a systematic signed component in this window. Therefore the
earlier `0.639 m` maximum cannot be promoted to a maneuver-independent
acceptance boundary.

## Reality-derived route diagnostic

The recorded camera-rig path was compared with both plans, but it is not
treated as the unique correct driving trajectory.

| Mean diagnostic | Straight/turn-entry | Sustained left turn |
|---|---:|---:|
| real-input plan ADE to recorded path | `0.927 m` | `1.742 m` |
| HUGSIM-input plan ADE to recorded path | `1.012 m` | `1.424 m` |
| real-input plan FDE to recorded path | `2.098 m` | `3.474 m` |
| HUGSIM-input plan FDE to recorded path | `2.231 m` | `2.763 m` |
| HUGSIM minus real FDE | `+0.133 m` | `-0.711 m` |

The HUGSIM-input plan happened to lie closer to the recorded path in the turn
window. This cannot be interpreted as “simulation is more realistic” or
“SparseDrive is more correct”: a recorded human route is only one feasible
trajectory, and prior controls show that SparseDrive can produce plausible
trajectories from severely altered inputs.

## What this adds to indicator design

1. `D_domain` must be conditioned on maneuver and scene context; a single
   scalar from one factual window is not a qualified uncertainty bound.
2. Repeat sensitivity and factual domain difference remain different
   quantities. Numerical repeat was about five orders of magnitude smaller
   than the task response differences in both windows.
3. Signed longitudinal and lateral components should accompany ADE/FDE.
   Euclidean distance alone hides the stable left/forward bias observed here.
4. Pixel similarity remains descriptive. Warmed SSIM was nearly unchanged
   between windows while mean plan FDE more than doubled.
5. A recorded route is a useful independent reality diagnostic, but not a
   standalone correctness judge or acceptance threshold.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| Both matched windows produce measurable SparseDrive response differences beyond local repeat sensitivity | `accepted` | ten fully warmed timestamps, one scene and one receiver |
| The turning-window mean ADE/FDE is descriptively larger than in the prior window | `accepted` | `1.96× / 2.17×`; no population-level inference |
| A single factual-domain maximum is a general real–sim acceptance threshold | `rejected` | the second motion regime exceeds and changes the signed pattern |
| Being closer to the recorded ego path proves greater simulation realism or AD correctness | `rejected` | recorded motion is not the unique correct plan |
| The two windows establish HUGSIM, SparseDrive or AD safety | `rejected` | claim scope exceeds the evidence |

The run as a whole remains `down-weighted`.

## Artifacts

```text
docs/runs/sparsedrive_real_sim_turn_window_preregistration_001.json
artifacts/hugsim_source_anchor/scene-0383-sparsedrive-real-turn-window-run001
artifacts/hugsim_matched_pose/scene-0383-source-turn-window-factual-run001
artifacts/sparsedrive_real_source/scene-0383-real-source-turn-window-run001
artifacts/sparsedrive_real_source/scene-0383-sim-factual-source-turn-window-run001
artifacts/sparsedrive_real_sim_factual/scene-0383-source-turn-window-run001
artifacts/sparsedrive_real_sim_cross_window/scene-0383-run002
```

Primary inspection files:

- `sparsedrive_real_sim_factual_comparison.png`: source RGB, matched HUGSIM RGB
  and both SparseDrive trajectories for all eight turn-window timestamps;
- `sparsedrive_real_sim_window_comparison.png`: cross-window task difference,
  signed endpoint shift, recorded-path diagnostic and pixel/task scatter;
- `sparsedrive_real_sim_warmed_rows.csv`: ten warmed observations in a
  machine-readable table;
- `sparsedrive_real_sim_cross_window_audit.json`: inputs, hashes, summaries,
  boundaries and evidence decisions.

## Next bounded step

Do not turn the two observed windows into a universal threshold and do not add
more same-scene windows merely to stabilize a number. The next upgrade should
target one missing source-independent task variable:

1. obtain a second source scene or independent actor/visibility reference with
   the same six-camera/time/pose contract;
2. preregister a maneuver-conditioned `D_domain(context)` comparison and the
   task consequence that would make its error material;
3. only then reuse a context-matched domain envelope when judging a
   counterfactual response;
4. defer another AD receiver until a key conclusion is shown to depend on
   SparseDrive.
