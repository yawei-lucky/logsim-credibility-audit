# SparseDrive real-source minimum qualification 001

Date: 2026-07-23

## Outcome

The official HUGSIM sample supplied a bounded real `scene-0383` sequence at
approximately 2 Hz. The unchanged SparseDrive-S Stage2 checkpoint consumed
four real six-camera frames, emitted finite non-degenerate native plans and
repeated within the existing `1e-4 m` numerical tolerance.

This closes the minimum local engineering gate for using SparseDrive as the
**target AD** in a real-versus-simulation comparison. The overall evidence is
`down-weighted`; it does not locally reproduce the official nuScenes benchmark
or qualify SparseDrive as a truth instrument.

## Source and input contract

- official archive: `hyzhou404/HUGSIM/sample_data/data.zip`;
- selected source frames: `12, 18, 24, 30`;
- timestamps: about `1.0, 1.5, 2.0, 2.5 s`;
- 24 real RGB images were extracted with ZIP CRC and local SHA-256 checks;
- source intrinsics and pre-bundle-adjustment camera-rig poses came from the
  official sample's `meta_data_init.json`;
- semantic and depth were not passed to SparseDrive;
- velocity, acceleration and yaw rate were derived from continuous source
  camera-rig poses;
- steering was unavailable and set to zero;
- the planning command used SparseDrive's released final-lateral-offset rule.

The exact original nuScenes sample tokens, CAN bus, calibrated-sensor table and
scene-specific `LIDAR_TOP` to `CAM_FRONT` transform are absent. The absolute
model-LiDAR/front-camera anchor is therefore provisionally inherited from the
frozen HUGSIM nuScenes camera configuration. This is sufficient for a paired
target-receiver pilot when frozen identically on both sides, but not for an
absolute SparseDrive accuracy claim.

## Main result

| Check | Result |
|---|---:|
| all native outputs finite | yes |
| baseline plans non-degenerate | yes |
| reset maximum plan difference | `9.54e-6 m` |
| four-frame mean ADE to recorded camera-rig motion | `0.907 m` |
| four-frame mean FDE | `1.816 m` |
| fully warmed frame ADE | `0.706 m` |
| fully warmed frame FDE | `1.630 m` |

The recorded camera-rig path is a descriptive behavior reference, not the
unique correct driving plan. These errors therefore do not constitute a
SparseDrive benchmark score.

## Negative controls

Three known input corruptions changed the native plan by much more than reset
variation:

| Control | Maximum plan change |
|---|---:|
| swap front-left/front-right RGB | `2.481 m` |
| reverse the four-frame RGB time order | `0.958 m` |
| shift `CAM_FRONT` principal point by 80 px | `0.591 m` |

However, they did **not** uniformly worsen error to the recorded path:

- camera swap mean ADE: `0.556 m`;
- temporal reversal mean ADE: `0.848 m`;
- front-intrinsic shift mean ADE: `0.976 m`.

The baseline mean was `0.907 m`. A corruption can accidentally move one
predicted trajectory closer to one recorded human trajectory, especially in a
single near-straight slice. Consequently:

> Plan change proves that the corruption reached the receiver. A lower or
> higher ADE on this slice does not prove that SparseDrive became better or
> worse.

This is useful negative method evidence: trajectory imitation error alone is
not a qualified receiver-correctness test.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| The pinned local adapter can run SparseDrive on the selected real six-camera sequence | `accepted` | finite native output, non-degenerate plan and bounded reset variation |
| Known camera/time/calibration corruptions reach and change the receiver | `accepted` | sensitivity only, not guaranteed performance degradation |
| The local trajectory error establishes SparseDrive planning accuracy | `down-weighted` | one slice, pose-derived status, unavailable steering and provisional absolute calibration |
| This reruns the official nuScenes benchmark or proves SparseDrive safe/correct | `rejected` | scope exceeds the experiment |
| This result by itself qualifies HUGSIM | `rejected` | no real-sim comparison in this gate |

## Artifacts

```text
artifacts/hugsim_source_anchor/scene-0383-sparsedrive-real-window-001
artifacts/sparsedrive_real_source/scene-0383-real-qual-run002
artifacts/sparsedrive_real_source/scene-0383-real-qual-run002/sparsedrive_real_source_qualification.png
artifacts/sparsedrive_real_source/scene-0383-real-qual-run002/sparsedrive_real_source_qualification.json
```
