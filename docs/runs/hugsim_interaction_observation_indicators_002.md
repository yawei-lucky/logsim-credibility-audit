# CF-I-OBS-002 corrected state-to-observation result

## Result

The corrective repeat cleared the shared `Camera.dynamics` state before both
members of every actor/no-actor pair and changed no frozen state, frame,
camera, threshold, or negative control. Three indicators are `accepted`; the
spatial-localization indicator remains `rejected`. The stop rule therefore
remains active and no AD receiver should be added yet.

| Indicator | Result | Main observation |
|---|---|---|
| `CF-I-O1` state to render transform | `accepted` | state replay and rendered position error `0`; yaw error below `9e-16 rad`; shifted-state negative rejected |
| `CF-I-O2` camera membership | `accepted` | 84/84 frame-camera rows matched; RGB actor support occurred only in `CAM_BACK`; rotated-camera negative produced 28 mismatches |
| `CF-I-O3` projected localization | `rejected` | support inside the projected `wlh.json` box plus 16 px fell from `0.983` to `0.479`; required minimum was `0.90` |
| `CF-I-O4` causal observation onset | `accepted` | state cause at index 8, first qualified RGB divergence at 9; two-frame-early label diverged at 6 and was rejected |

Overall evidence remains `down-weighted`: all state, calibration, dimensions,
RGB, and scene assets come from HUGSIM. The run checks internal transport, not
real-camera equivalence.

## What the accepted results mean

- The exact frozen planner state reaches the renderer transform without an
  observed position or yaw mismatch in this window.
- Independent projection and paired RGB agree on which camera receives the
  actor: rear camera positive, other five cameras negative.
- The rendered response did not appear before its state cause. The one-frame
  delay from state divergence at 8 to qualified uint8 RGB divergence at 9 is a
  bounded observation-resolution result, not a realistic sensor-latency claim.

## Why spatial localization remains rejected

The failure is systematic rather than a single bad frame. As the rear vehicle
approaches, the fraction of actor-caused RGB support covered by its projected
box declines monotonically:

| Frame | 6 | 7 | 8 | 9 | 10 | 11 | 14 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline coverage | 0.983 | 0.961 | 0.920 | 0.874 | 0.824 | 0.770 | 0.479 |
| Treatment coverage | 0.983 | 0.961 | 0.921 | 0.877 | 0.822 | 0.757 | 0.487 |

The 200-pixel shifted projection remained a valid gross negative, reaching at
most `0.192` coverage. Thus O3 can detect a large wrong-location control, but
its current positive model does not describe the rendered asset closely enough
across distance.

A post-run asset diagnostic found a concrete likely mechanism. `wlh.json`
declares `[width, length, height] = [1.625, 3.576, 1.175] m`. The central 99%
envelope of Gaussian points with opacity at least 0.5 is approximately
`[1.635, 3.921, 1.318] m`, and its local vertical center is offset by about
`-0.659 m` from the transform origin. The metadata box is therefore not the
same geometric envelope or origin as the rendered asset. This can explain why
a fixed-pixel dilation becomes increasingly inadequate at close range, but it
is not an external reality anchor.

This is task-relevant negative evidence: even when RGB visibly looks coherent,
the simulator-provided object box may not tightly describe the rendered object.
That can affect ground-truth association, evaluation, and any credibility
metric that treats `obj_boxes` as privileged truth. It is not, by itself,
evidence that the RGB vehicle appearance is unrealistic.

## Inspectable outputs

```text
docs/runs/hugsim_interaction_observation_indicators_002.json
artifacts/hugsim_interaction_observation/analysis-run002/interaction_observation_measurements.json
artifacts/hugsim_interaction_observation/analysis-run002/interaction_observation_summary.png
artifacts/hugsim_interaction_observation/analysis-run002/interaction_observation_cam_back_contact_sheet.png
artifacts/hugsim_interaction_observation/analysis-run002/interaction_observation_localization_diagnostic.png
```

## Next bounded step

Do not relax the frozen 0.90 gate merely to turn O3 green. Split the next audit
into two different questions:

1. `metadata-box consistency`: does HUGSIM's declared `obj_boxes` envelope the
   rendered actor across distance and cameras? The current rear-window claim
   remains rejected.
2. `asset-envelope localization`: after deriving an opacity-qualified Gaussian
   envelope and its origin independently from the asset, does RGB support stay
   consistently localized? This diagnoses whether the mismatch comes from box
   metadata or a deeper state-to-render projection error.

Only after that distinction is qualified should the rendered observation be
passed to an AD receiver.
