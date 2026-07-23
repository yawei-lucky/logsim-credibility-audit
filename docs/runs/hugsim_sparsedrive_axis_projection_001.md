# HUGSIM × SparseDrive axis and plan-projection audit 001

Date: 2026-07-23

## Outcome

The first runtime adapter omitted the full transform between SparseDrive's
nuScenes LiDAR frame and HUGSIM's vehicle frame. Its native tensors remain
valid evidence that the runtime executed, but every interpretation of the old
plan geometry is `rejected`.

The corrective run now makes the plan directly inspectable in two views:

- the native trajectory is projected onto the **raw, unmodified HUGSIM
  `CAM_FRONT` RGB**;
- the same trajectory is plotted top-down as model `x=right, y=forward`.

HUGSIM already records both vehicle-to-camera (`v2c`) and
LiDAR-to-camera (`l2c`) calibration. All six cameras independently recover the
same LiDAR-to-vehicle transform. With that exact internal transform, the fully
warmed plan is directionally coherent and passes a basic speed-continuity
sanity check. This qualifies the adapter's internal baseline, not SparseDrive
or HUGSIM as a real-world planning judge.

## Root cause and correction

The official SparseDrive converter uses the final plan's first coordinate to
classify right versus left, so its plan convention is `x=right, y=forward`.
HUGSIM's camera extrinsics consume vehicle coordinates
`x=forward, y=left, z=up`. The nominal direction relationship is:

```text
HUGSIM forward = SparseDrive forward
HUGSIM left    = -SparseDrive right
HUGSIM up      = SparseDrive up
```

The actual transform is not an assumed 90-degree rotation. It is recovered for
each camera as:

```text
LiDAR-to-vehicle = inverse(v2c) × l2c
```

The maximum disagreement among the six recovered transforms is about
`1.6e-15`. It contains the nominal axis rotation plus the configured LiDAR
origin at approximately `0.99 m` forward and `1.84 m` above the HUGSIM vehicle
origin, including the small configured sensor rotation.

The adapter applies this transform to both camera projection matrices and the
model-to-global transform. Unit checks require model-right to become
HUGSIM-right and model-forward to project near the front-camera centre. This
qualifies HUGSIM's internal calibration contract; it does not independently
prove that the calibration is physically correct.

## Corrective run

- input:
  `artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s`;
- frames: `0, 2, 4, 6` at `0.0, 0.5, 1.0, 1.5 s`;
- output:
  `artifacts/sparsedrive_receiver/scene-0383-runtime-smoke-l2c-calibrated-run001`;
- machine-readable report:
  `runtime_smoke.json`;
- visual:
  `no_actor_runtime_smoke.png`.

All native tensors were finite and the reset repeat remained within the frozen
`1e-4` absolute tolerance.

## What the visual shows

Orange lines and circles are SparseDrive's six future waypoints projected at
the official visualization ground height through HUGSIM's raw camera
calibration. Four waypoints are visible for frame 0 and three for frame 2. The
warmed frame-4 and frame-6 plans end within about `5.5 m`, entirely below the
front camera's ground-plane field of view, so no orange points are drawn there.
They remain visible in the lower top-down plot.

The lateral scale in the lower plot is deliberately enlarged. Across the four
frames:

- all six-step plans progress monotonically forward;
- final lateral offsets remain within `0.20 m`;
- the projected path remains near the visible road direction.

These are narrow positive geometry observations, not evidence that HUGSIM
matches reality.

## Kinematic sanity check

SparseDrive outputs six positions at `0.5 s` intervals. The first-displacement
average speed and an equivalent constant acceleration from the supplied scalar
ego speed are:

| Frame | HUGSIM ego speed (m/s) | First plan step (m/s) | Equivalent acceleration (m/s²) | 3 s plan endpoint: right, forward (m) | Recorded HUGSIM forward (m) |
|---:|---:|---:|---:|---:|---:|
| 0 | 1.00 | 5.62 | 18.48 | `0.10, 15.79` | 5.51 |
| 2 | 1.56 | 3.38 | 7.26 | `-0.20, 8.66` | 5.79 |
| 4 | 1.81 | 2.17 | 1.47 | `0.05, 5.47` | 5.91 |
| 6 | 1.92 | 1.82 | -0.37 | `0.09, 4.72` | 5.96 |

The equivalent acceleration is only a descriptive sanity calculation; it
assumes constant acceleration along the first predicted displacement. The
recorded HUGSIM ego path is an internal sequence reference, not reality ground
truth.

The first frame is cold and frame 2 is only partially warmed. At frame 6, the
declared four-frame history-plus-current window is populated: the first
predicted step is `1.82 m/s` versus an observed `1.92 m/s`, and the trajectory
uses small monotonic forward displacements with only `0.09 m` final lateral
offset. This is a plausible basic internal baseline. The `1.24 m` difference
from HUGSIM's own 3-second executed endpoint remains a receiver-versus-source
choice, not a reality error measurement.

## Evidence decisions

| Claim or finding | Decision | Boundary |
|---|---|---|
| Old run 006 can support runtime execution and native-output availability | `accepted` | engineering claim only |
| Old run 006 plan geometry can be interpreted | `rejected` | missing model-LiDAR-to-HUGSIM-vehicle transform |
| Six cameras imply one common model-LiDAR-to-vehicle transform | `accepted` | HUGSIM internal calibration; maximum residual about `1.6e-15` |
| Corrected raw front-camera projection is directionally coherent | `accepted` | HUGSIM calibration and official plan ground height |
| HUGSIM's recorded LiDAR/camera calibration is physically correct | `down-weighted` | internally exact, not checked against an independent calibration target |
| Fully warmed plan passes basic no-actor geometry and speed-continuity sanity | `accepted` | one normal segment; internal baseline only |
| The current plan proves real-world planning consistency or HUGSIM credibility | `rejected` | no real matched AD output, ego-status sensitivity or counterfactual response yet |

## Next gate

Do not use this plan to judge a counterfactual yet. First audit the observed,
derived and unavailable 10-D `ego_status` fields and test reasonable
alternatives at an equally warmed frame. If the baseline conclusion remains
stable, freeze the command and warm-up contract and proceed to the
preregistered slow/nominal/fast planning-direction experiment.
