# HUGSIM × SparseDrive ego-status sensitivity 001

Date: 2026-07-23

## Question

SparseDrive expects a 10-D ego-state vector, while HUGSIM records scalar speed,
acceleration and steering plus consecutive poses. Before using SparseDrive to
judge a counterfactual, test whether two reasonable constructions materially
change the warmed native plan:

- `recorded_scalar`: recorded longitudinal speed, acceleration and steering,
  with yaw rate derived from consecutive poses;
- `pose_derived`: velocity, acceleration and yaw rate derived from consecutive
  poses in the current ego frame, with recorded steering.

Both variants use the same RGB, calibration, checkpoint, frames and four-frame
warm-up, with an independent model-state reset.

## Result

- frames: source indices `4, 6, 8, 10` (`1.0–2.5 s`);
- maximum native-plan waypoint difference: about `1.15e-5 m`;
- frozen reset numerical envelope: `1e-4 m`;
- selected planning mode was identical for both variants at every frame;
- both fully warmed plans remained finite, forward-positive and monotonically
  forward.

Artifacts:

- analysis:
  `artifacts/sparsedrive_receiver/ego-status-sensitivity-analysis-run002/ego_status_sensitivity.json`;
- visual:
  `artifacts/sparsedrive_receiver/ego-status-sensitivity-analysis-run002/ego_status_sensitivity.png`;
- recorded-scalar receiver run:
  `artifacts/sparsedrive_receiver/ego-status-recorded-run001`;
- pose-derived receiver run:
  `artifacts/sparsedrive_receiver/ego-status-pose-run001`.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| The fully warmed internal baseline is structurally stable under the two tested ego-status constructions | `accepted` | one normal HUGSIM segment and one frozen receiver |
| The two constructions are plan-equivalent within the frozen reset numerical envelope for this segment | `accepted` | internal sensitivity statement only; `1e-4 m` is not an externally qualified task threshold |
| Either construction is physically correct for real deployment | `down-weighted` | no independent vehicle-state truth establishes the complete 10-D convention |
| This audit establishes SparseDrive or HUGSIM real-world credibility | `rejected` | that claim exceeds an internal input-sensitivity test |

## Consequence

Use `recorded_scalar` for the first CF-R planning experiment because it changes
fewer source quantities. Hold the command, cadence and warm-up fixed. Retain
`pose_derived` as a sensitivity control rather than treating either vector as
ground truth.
