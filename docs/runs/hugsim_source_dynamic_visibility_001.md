# HUGSIM source-side dynamic visibility audit 001

Date: 2026-07-25

## Outcome

The second-source-scene availability gate did not pass:

- local `scene-0041` and `scene-0138` archives contain reconstruction
  checkpoints and metadata, but no real source RGB;
- the official 2.38 GB sample-data ZIP contains source observations only for
  `scene-0383`.

Those reconstructions therefore cannot be presented as a second matched
real–sim anchor. The experiment instead used a stronger reference already
available in `scene-0383`: source RGB and upstream source dynamic masks at two
reader-declared test timestamps.

The bounded result is positive. Across 12 camera–frame pairs, the HUGSIM native
dynamic path changed exactly the same three views supported by the source-side
dynamic mask. Its difference energy was spatially concentrated in the source
region, including a front-left to back-left camera-boundary case.

Overall evidence remains `down-weighted`. The source mask is independent of
HUGSIM rendered RGB, but it shares source geometry and preprocessing with the
reconstruction and is not real-world ground truth.

## Frozen design

Frames `44` and `49` were selected before their exact RGB, mask or render
outputs were inspected:

- all six camera records at each timestamp satisfy the released reader rule
  `idx % 30 >= 24`;
- frame `44` projects the native dynamic into `CAM_FRONT_LEFT`;
- frame `49` projects it across `CAM_FRONT_LEFT` and `CAM_BACK_LEFT`.

For each frame HUGSIM rendered:

1. `factual`: source pose and released native dynamic checkpoint;
2. `static_control`: identical pose, intrinsics, static checkpoint and renderer,
   with only the selected frame's dynamics dictionary cleared.

The resulting factual-minus-static image isolates the native dynamic render
path. It does not necessarily isolate all actor-like content in the complete
image.

The source mask is generated upstream as the intersection of the
source-metadata projected dynamic box and selected road-user semantic train
IDs: person, rider, car, truck, bus and bicycle. This clarifies the
preregistration's shorthand “vehicle-class pixels” without changing the frozen
selection, measurement or decision. The recorded mask-generator SHA-256 is
`644653d38ce63fb7d88907899e4e0f73e96d91b27bdac949584a52d943d7143e`.

## Quantitative results

| Frame / camera | Source-mask pixels | Dynamic energy inside exact mask | Inside 16 px dilation | Energy-centroid error | IoU at 8-intensity threshold |
|---|---:|---:|---:|---:|---:|
| `44 / CAM_FRONT_LEFT` | `6,126` | `0.805` | `0.958` | `2.33 px` | `0.567` |
| `49 / CAM_BACK_LEFT` | `10,729` | `0.762` | `0.953` | `4.53 px` | `0.521` |
| `49 / CAM_FRONT_LEFT` | `9,829` | `0.750` | `0.956` | `9.13 px` | `0.543` |

Summary:

- camera membership matched in all `12/12` camera–frame pairs;
- all `3/3` source-supported views had nonzero native-dynamic render energy;
- all `9/9` source-empty views had exactly zero factual-minus-static energy;
- exact-mask energy fraction: mean `0.773`, range `0.750–0.805`;
- 16-pixel-dilated energy fraction: mean `0.956`, range `0.953–0.958`;
- centroid error: mean `5.33 px`, range `2.33–9.13 px`.

Thresholds `4, 8, 16, 32` were all reported as sensitivity analysis rather
than selecting one after seeing the result. Across supported views, IoU at
threshold `8` was `0.521–0.567`. Higher thresholds increased precision and
reduced recall, so none is promoted to an acceptance boundary.

## Post-run descriptive diagnostic

This diagnostic was not preregistered and does not upgrade the evidence
decision. Within the source dynamic mask, adding the native dynamic reduced
real-image MAE relative to the static control in all `3/3` views:

- relative improvement range: `9.8%–32.8%`;
- mean relative improvement: `21.4%`.

Thus the dynamic path adds image content in the useful direction for these
source pixels. It does not establish photometric equivalence.

## Important negative boundary

The static-control crops still contain person-like residual structure. This
means:

- factual-minus-static cleanly measures the **additional native dynamic
  contribution**;
- it does not prove the static reconstruction is actor-free;
- an AD receiver may see a mixture of native dynamic content, static leakage,
  blur and reconstruction artifacts.

This is more important than whether the inserted object looks aesthetically
sharp. Correct camera membership and approximate support are positive
task-information evidence; incomplete static/dynamic separation is a nuisance
channel that may still alter perception or planning.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| The native dynamic path activates the same selected camera views as the source-side mask | `accepted` | `12/12` camera–frame pairs; two timestamps and one actor |
| Its added pixel support overlaps the source-side region | `accepted` | exact energy fraction `0.750–0.805`; no universal threshold |
| The source mask is independent real-world ground truth | `rejected` | renderer-independent, but shares source geometry and preprocessing |
| Support overlap proves photometric, semantic, depth or sensor equivalence | `rejected` | appearance, labels, depth and task consequences are not qualified |
| Support overlap proves sufficient information for an AD | `rejected` | no receiver was evaluated in this experiment |
| The pilot establishes general HUGSIM credibility or AD safety | `rejected` | scope exceeds the evidence |

The complete run is `down-weighted`.

## What this adds to the credibility method

This is the first current pilot to compare native dynamic support with a
source-side observation reference rather than HUGSIM semantic/depth or an
injected actor's declared box. It separates three questions that must not be
collapsed:

1. **camera membership:** does the object appear in the correct camera?
2. **spatial support:** does the added information occupy the corresponding
   image region?
3. **receiver consequence:** does the same AD extract a corresponding task
   relation or action?

The first two now have narrow positive evidence. The third remains untested.

## Artifacts

```text
docs/runs/hugsim_source_dynamic_visibility_preregistration_001.json
artifacts/hugsim_source_anchor/scene-0383-dynamic-visibility-heldout-run001
artifacts/hugsim_matched_pose/scene-0383-frame00044-source-dynamic-visibility-run001
artifacts/hugsim_matched_pose/scene-0383-frame00049-source-dynamic-visibility-run001
artifacts/hugsim_source_dynamic_visibility/scene-0383-heldout-run002
```

Primary inspection files:

- `hugsim_source_dynamic_visibility.png`: source mask, factual render, static
  control and isolated dynamic support for the three supported views;
- `hugsim_source_dynamic_visibility_audit.json`: all 12 pairs, threshold
  sensitivity, hashes and evidence decisions.

## Next bounded step

Do not add more overlap thresholds or same-scene timestamps merely to refine
the current percentages. The next useful bridge is a receiver-level natural
actor control:

1. build the minimum valid temporal history ending at one of these
   source-supported timestamps;
2. hold pose, calibration, ego state and receiver reset fixed;
3. compare the same target receiver on real RGB, factual HUGSIM RGB and the
   static-control HUGSIM RGB;
4. ask whether adding the native dynamic moves the factual receiver output
   toward the real-source output, while preserving the static-leakage
   limitation;
5. retain second-scene evidence as a later generality requirement.
