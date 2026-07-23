# SparseDrive visual-necessity audit 002

Date: 2026-07-23

Corrective preregistration commit: `711f53e`

## Outcome

The strong hypothesis that SparseDrive produced the tested plan by ignoring
RGB and copying the supplied scalar ego state is not supported.

On the same real four-frame source window:

- removing all spatial RGB information changed the fully warmed 3 s endpoint
  by `1.405 m`;
- freezing RGB history changed it by `0.158 m`;
- changing supplied forward velocity by `-2 / +2 m/s` changed the plan only at
  the `10^-6 m` repeat-noise scale;
- freezing model-to-world pose history collapsed the 3 s endpoint from
  `9.821 m` to `0.019 m` and changed planning mode from `3` to `1`.

Thus RGB and temporal pose alignment both causally affect the released
receiver. The experiment does not establish that the RGB contribution uses
the correct objects, lanes or risks, and pose-history dependence is not by
itself evidence of a shortcut.

Overall evidence is `down-weighted`.

## Corrective method note

Run001 changed `ego_status[7]` under the mistaken assumption that the source
model-axis order was also SparseDrive's CAN-bus order. Source inspection found:

- source/model pose vectors use `[right, forward, up]`;
- SparseDrive's converter stores `[forward, left, up]`;
- released `InstanceQueue` addresses longitudinal status at index `6`.

Run001's ego-speed conclusion is therefore `rejected` method evidence and its
output remains preserved. Run002 corrected both the real-source adapter and
the intervention.

The corrected adapter changed the previous baseline by only `9.54e-6 m`.
Inspection of the released inference graph explains this:

- `data["ego_status"]` is used as a target by `loss_planning` during training;
- the live inference queue caches the network-predicted `plan_status`;
- changing the supplied inference-time `ego_status` therefore does not change
  this checkpoint's plan.

This is an architectural property of the pinned SparseDrive source and
checkpoint, not evidence that ego motion is irrelevant. SparseDrive separately
uses `T_global` / `T_global_inv` to align temporal anchors.

## Fully warmed result

The paired repeat maximum over all trajectory coordinates was
`8.58e-6 m`; the frozen local decision threshold was repeat plus
`1e-4 m`.

| Intervention | Plan ADE from baseline | Endpoint difference | Final forward change | Mode |
|---|---:|---:|---:|---:|
| constant normalization-centre RGB | `0.582 m` | `1.405 m` | `+1.405 m` | `3 → 3` |
| first RGB frame repeated | `0.123 m` | `0.158 m` | `-0.152 m` | `3 → 3` |
| supplied forward speed `-2 m/s` | `0.000002 m` | `0.000005 m` | `+0.000005 m` | `3 → 3` |
| supplied forward speed `+2 m/s` | `0.000004 m` | `0.000009 m` | `+0.000009 m` | `3 → 3` |
| first ego pose repeated | `6.332 m` | `9.802 m` | `-9.802 m` | `3 → 1` |

All outputs except the frozen-pose condition remained non-degenerate.

Most importantly, constant six-camera RGB still produced a visually plausible
forward plan ending at `11.225 m`, compared with `9.821 m` for real RGB. This
does not show that the constant-RGB plan is safe or correct. It shows that a
planning prior, command and temporal machinery can produce a plausible-looking
trajectory even after task-relevant visual content is removed.

Consequently:

> Trajectory plausibility is not evidence of scene understanding. A receiver
> must also pass controlled task-content tests in which vehicles, lanes,
> occlusion or conflict strength change in a declared direction.

The earlier CF-R planning experiment supplies one such narrow positive result:
with equal ego state and command, changing rendered lead-actor closure produced
the preregistered longitudinal plan order at all ten warmed timestamps. That
still establishes only bounded simulator-internal direction, not realistic
response magnitude.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| RGB content causally influences the native plan | `accepted` | one real four-frame slice; constant-RGB effect exceeds paired repeat |
| Short RGB history causally influences the native plan | `accepted` | first-frame-repeat control on the same slice |
| Supplied inference-time `ego_status` changes the released Stage2 plan | `rejected` | two-sided `±2 m/s` control remained within repeat; released source uses it as a training target, not a planning input |
| Temporal model-to-world pose history influences the plan | `accepted` | frozen-pose control; deliberately invalid temporal alignment |
| SparseDrive completely ignores images in this slice | `rejected` | both spatial and temporal RGB controls changed the plan |
| Pose sensitivity proves shortcut learning | `rejected` | ego-motion compensation is also required for legitimate temporal alignment |
| This proves correct visual semantics or absence of shortcuts | `rejected` | no independent object/lane/risk truth in this audit |
| Effect magnitudes prove whether image or pose is more important | `rejected` | interventions are not commensurate |

## Artifacts

```text
artifacts/sparsedrive_visual_necessity/scene-0383-real-run001
artifacts/sparsedrive_real_source/scene-0383-real-qual-can-axis-run003
artifacts/sparsedrive_visual_necessity/scene-0383-real-corrected-run002
artifacts/sparsedrive_visual_necessity/scene-0383-real-corrected-run002/sparsedrive_visual_necessity.png
artifacts/sparsedrive_visual_necessity/scene-0383-real-corrected-run002/sparsedrive_visual_necessity.json
```

Formal corrective command:

```bash
/home/yawei/miniforge3/envs/sparse4d-audit/bin/python \
  scripts/run_sparsedrive_visual_necessity.py \
  --qualification-report artifacts/sparsedrive_real_source/scene-0383-real-qual-can-axis-run003/sparsedrive_real_source_qualification.json \
  --preregistration docs/runs/sparsedrive_visual_necessity_preregistration_002.json \
  --runtime-deps artifacts/sparsedrive_receiver/runtime-deps-v1 \
  --anchor-dir artifacts/sparsedrive_receiver/official-v1.0/anchors \
  --output artifacts/sparsedrive_visual_necessity/scene-0383-real-corrected-run002
```

## Research consequence

SparseDrive remains usable as the fixed target AD, but plan shape alone is not
a qualified semantic receiver metric. The next same-window counterfactual must
hold command and ego-pose history fixed, introduce one declared lead-vehicle
change, and judge task-direction response against factual-domain and repeat
envelopes. No additional target model is needed first.
