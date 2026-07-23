# SparseDrive matched factual real–HUGSIM audit 001

Date: 2026-07-23

## Outcome

The same frozen SparseDrive checkpoint processed:

1. official-sample real six-camera RGB;
2. HUGSIM RGB rendered at the same declared source timestamps, intrinsics and
   pre-bundle-adjustment source poses.

Vehicle-state history, command, future motion reference, receiver adapter,
model checkpoint and model calibration were held byte/numerically equal. This
is the repository's first direct matched factual **AD-response** comparison,
rather than a pixel-only comparison.

The observed domain discrepancy is real and measurable, but overall evidence
remains `down-weighted`: only one frame has the complete four-frame receiver
history, and no externally qualified acceptance threshold exists.

## Rendered factual slice

| Source frame | Mean PSNR | Mean SSIM | Mean MAE |
|---:|---:|---:|---:|
| 12 | `19.10 dB` | `0.474` | `0.0733` |
| 18 | `18.34 dB` | `0.447` | `0.0816` |
| 24 | `17.55 dB` | `0.433` | `0.0881` |
| 30 | `16.63 dB` | `0.395` | `0.0994` |

These values are descriptive. The source-initial poses are closer to the
physical conversion than reconstruction-optimized poses, but the current
checkpoint was trained with optimized metadata. The declining pixel agreement
therefore includes reconstruction and pose-model mismatch; it must not be
interpreted as a standalone task failure.

## Native SparseDrive domain difference

`D_domain` is the pointwise difference between the real-input and
HUGSIM-input native final planning trajectories.

| Frame | Receiver history | Plan ADE | Plan endpoint difference | Sim minus real 3 s forward |
|---:|---:|---:|---:|---:|
| 12 | 1/4 | `1.578 m` | `2.632 m` | `+2.632 m` |
| 18 | 2/4 | `0.069 m` | `0.178 m` | `+0.177 m` |
| 24 | 3/4 | `0.040 m` | `0.049 m` | `+0.049 m` |
| 30 | 4/4 | `0.358 m` | `0.639 m` | `-0.639 m` |

At the fully warmed frame:

- the selected planning mode remained `3` on both sides;
- the final lateral difference was only `0.015 m`;
- HUGSIM caused SparseDrive to plan `0.639 m` less forward over 3 seconds;
- the endpoint difference was much larger than the `9.54e-6 m` paired reset
  envelope.

The cold-frame discrepancy is not an admissible equivalence result because
SparseDrive lacks its required history there. The fully warmed result is the
primary factual domain observation.

## Post-run adapter correction

A later audit corrected the pose-derived ego-status vector from source/model
`[right, forward, up]` order to SparseDrive CAN-bus
`[forward, left, up]` order. The corrected real baseline differed from this
run by at most `9.54e-6 m`, within paired repeat noise. Released Stage2
inference does not consume supplied `data["ego_status"]` as a planning input;
it trains an auxiliary status prediction and caches that network prediction.

The numeric factual `D_domain` observation therefore remains unchanged for
this pinned checkpoint. The original adapter contract remains negative method
evidence and must not be copied into another receiver.

## What this newly shows

Pixel and task-output differences are not interchangeable:

- SSIM declines monotonically from `0.474` to `0.395`;
- the planning domain difference instead changes from large, to very small,
  and then moderate after full warm-up.

Thus a visually imperfect reconstruction can sometimes preserve this AD
output closely, while visual similarity alone cannot guarantee task
equivalence. The task receiver must be measured directly.

The earlier CF-R plan experiment had:

- minimum pairwise longitudinal margin: `0.0868 m`;
- median strongest-to-weakest effect: `1.270 m`.

The fully warmed factual forward-domain gap of `0.639 m` lies between those
two scales. This is only a cross-experiment diagnostic because CF-R used a
different simulated timeline and intervention. It does **not** yet justify
subtracting `D_domain` from `E_CF` or upgrading CF-R's real-world magnitude.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| A matched factual real–HUGSIM SparseDrive response difference was measured under a held-fixed receiver contract | `accepted` | four declared timestamps; one fully warmed frame |
| The fully warmed factual `D_domain` is nonzero beyond numerical repeat noise | `accepted` | `0.358 m` plan ADE and `0.639 m` endpoint difference |
| The factual responses satisfy a real-world equivalence threshold | `down-weighted` | no externally qualified threshold and only one fully warmed timestamp |
| Pixel agreement proves or disproves AD-task equivalence | `rejected` | planning and pixel differences did not co-vary monotonically |
| This pilot upgrades the earlier CF-R response magnitude to real-world validity | `rejected` | different window and intervention; no same-window `E_CF` yet |
| This proves SparseDrive, HUGSIM or an AD system safe | `rejected` | scope exceeds the experiment |

## Artifacts

```text
artifacts/hugsim_matched_pose/scene-0383-frame000{12,18,24,30}-source-init-render-run001
artifacts/hugsim_matched_pose/scene-0383-sparsedrive-source-init-window-run001
artifacts/sparsedrive_real_source/scene-0383-sim-factual-source-init-run001
artifacts/sparsedrive_real_sim_factual/scene-0383-source-init-run001
artifacts/sparsedrive_real_sim_factual/scene-0383-source-init-run001/sparsedrive_real_sim_factual_comparison.png
artifacts/sparsedrive_real_sim_factual/scene-0383-source-init-run001/sparsedrive_real_sim_factual_audit.json
```

## Next bounded step

Do not change receiver or scene yet.

1. extend this same source window enough to obtain several fully warmed
   factual timestamps and estimate a small within-window `D_domain` range;
2. add one controlled lead-vehicle counterfactual to this exact rendered
   window;
3. compute same-construct `E_CF` and compare it with factual-domain and reset
   envelopes;
4. retain the result as receiver- and window-specific unless an external
   threshold or additional receiver is later qualified.
