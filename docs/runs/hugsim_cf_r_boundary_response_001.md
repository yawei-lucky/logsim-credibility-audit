# CF-R external-boundary response pilot 001

Date: 2026-07-26

Preregistration commit: `76b7ffe`

## Outcome

The pilot is overall `down-weighted`.

It produced one useful positive result and two consequential negative results:

1. the designed common-path stimulus covered the external boundary exactly,
   and SparseDrive's same-mode longitudinal plan responded in the expected
   order;
2. the preregistered complete-horizon clearance-gain indicator became
   inapplicable when near/below plans nearly stopped;
3. none of the three strict SparseDrive–HUGSIM closed loops completed because
   the trajectory-to-control adapter later requested steering outside
   HUGSIM's declared action range.

This is more informative than another far-boundary speed curve. It shows both
that the receiver reacts to boundary-spanning inputs and that the current
metric/control contracts do not yet support a boundary-level closed-loop
credibility claim.

## Frozen conditions

Only the lead actor's initial longitudinal centre changed. Scene, vehicle
asset, actor speed (`0.5 m/s`), source ego history, SparseDrive, camera
contract, horizon and loop interface were held fixed.

| Condition | Actor initial centre | Common-path gap at `t=1.5 + 3.0 s` | Margin to 2 m comparator |
|---|---:|---:|---:|
| above | `13.211404 m` | `4.000000 m` | `+2.000000 m` |
| near | `11.211404 m` | `2.000000 m` | approximately `0 m` |
| below | `10.211404 m` | `1.000000 m` | `-1.000000 m` |

All three actual source runs passed the preregistered geometry gate:

- actor remained ahead and laterally overlapping;
- the front-camera actor centre stayed inside the image at all four 2 Hz
  warm-up frames;
- at least `8 / 6 / 4` projected actor-box corners were inside the first
  above/near/below frame, respectively;
- the six common-reference future states were exact rather than padded.

The below actor is partially cropped by the lower image boundary early in the
warm-up. It remains visible, but this is an explicit condition boundary.

## Open-loop target-AD response

At the shared fully warmed `t=1.5 s` handoff, all three plans selected native
mode `3`.

| Condition | SparseDrive 3 s forward endpoint | Valid complete-gap samples | Valid-prefix clearance gain |
|---|---:|---:|---:|
| above | `3.252968 m` | `6/6` | `2.479754 m` |
| near | `1.658163 m` | `5/6` | `3.500721 m` |
| below | `1.368970 m` | `5/6` | `3.699764 m` |

The same-mode longitudinal relation is strict:

```text
below < near < above
```

This is `accepted` as a narrow open-loop response-direction result. It shows
that moving the same lead actor across this external design boundary changed
the frozen receiver's longitudinal plan in the expected direction.

The valid-prefix clearance gains also have the expected diagnostic order, but
they are not accepted as the preregistered complete-horizon result.

## Negative metric result: near-stop heading

SparseDrive's near and below plans almost stop by the final waypoint. Their
last `0.5 s` displacement is only about `0.018 m` and `0.012 m`.

The current footprint tool infers each planned box heading from two successive
waypoints. At such small displacement, millimetre-scale lateral changes produce
about `17°` and `24°` final inferred headings. Projecting the distant actor
onto those unstable axes makes the same-lane overlap gate fail at horizon
`3.0 s`.

Therefore:

- the complete-horizon clearance-gain claim is `rejected`;
- the five-point prefix remains a diagnostic only;
- the result is not repaired post hoc by deleting the last waypoint or
  silently carrying the previous heading.

This identifies a reusable indicator requirement: planned footprint heading
needs a qualified near-zero-speed convention before clearance is interpreted
through stop states.

## Negative closed-loop result: action-interface saturation

Every preregistered strict loop stopped when the converted SparseDrive plan
requested steering beyond HUGSIM's declared `±0.261799 rad/s` action bound:

| Condition | Last completed world time | Rejected requested steer rate |
|---|---:|---:|
| above | `3.50 s` | `0.400000 rad/s` |
| near | `4.50 s` | `0.355631 rad/s` |
| below | `3.00 s` | `0.400000 rad/s` |

The three failures occur at different times, so their partial final states are
not compared. Commands were not clipped after seeing the result.

This does not show that the AD response is physically wrong, nor that HUGSIM
is unsafe. It shows that the currently qualified trajectory-to-control
contract cannot execute these boundary-level maneuvers. Consequently,
strict-action-compatible closed-loop completion is `rejected` and no
boundary-level final outcome is available.

HUGSIM's NC/TTC/PDMS values from the separate state-only runs are excluded.
Those runs use the deterministic plan-pipe writer and HUGSIM's internal future
scorer; they are not SparseDrive closed-loop outcomes.

## Evidence decisions

| Claim | Decision | Evidence boundary |
|---|---|---|
| Source and preregistered geometry gate passed | `accepted` | one scene, three initial positions, exact source/future prefixes |
| The common reference spans the selected external boundary | `accepted` | exact `4/2/1 m` endpoint gaps |
| Same-mode SparseDrive longitudinal plan follows the expected direction | `accepted` | one reset, one handoff, endpoints `3.253/1.658/1.369 m` |
| Preregistered complete clearance-response gain is qualified | `rejected` | near/below lose the final same-lane gate under near-stop heading inference |
| All three strict-action closed loops complete | `rejected` | every condition exceeds the declared steering-rate bound |
| Overall boundary-response pilot | `down-weighted` | useful open-loop evidence, but no qualified complete clearance or final outcome |
| Response magnitude is realistic or proves safety | `rejected` | no matched real response or independent behavior range |

## Research consequence

Do not change the actor positions or add another receiver yet. The next bounded
step is to qualify two contracts exposed by this experiment:

1. define and test a near-zero-speed planned-heading rule using an explicit
   vehicle-motion convention, then rerun this fixed audit without changing the
   three stimuli;
2. decide and preregister the target vehicle's actuator contract—strict
   rejection, physically justified saturation, or a feasibility-aware tracking
   controller—before any diagnostic closed-loop rerun.

Only after those gates pass should the same frozen above/near/below scenarios
be repeated twice and compared with closed-loop repeat sensitivity.

## Inspectable artifacts

```text
artifacts/sparsedrive_cf_r_boundary/receiver-run001/
artifacts/sparsedrive_cf_r_boundary/{above,near,below}-run001.runner.log
artifacts/sparsedrive_cf_r_boundary/analysis-run002/cf_r_boundary_response_audit.json
artifacts/sparsedrive_cf_r_boundary/analysis-run002/cf_r_boundary_response_summary.png
```

`analysis-run001` is retained as the first calculation. `analysis-run002`
changes only the plot's vertical extent and is the reviewed result.
