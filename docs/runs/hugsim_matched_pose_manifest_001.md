# HUGSIM Matched-Pose Manifest 001

Date: 2026-07-21

## Result

Gate status: `blocked_source_anchor`

Pairing integrity passed: `False`

Receiver equivalence tested: `False`

Permitted claim: selected metadata pose can be listed, but no real-sim image pair or AD receiver comparison is established

This run did not generate a new HUGSIM scenario, rollout, or rendered simulation image. It prepares the exact metadata pose that should be used once the real source observations are recovered.

## Selected Pose

| Field | Value |
|---|---:|
| Scene | scene-0383 |
| Frame index | 00004 |
| Timestamp | 0.333595 s |
| Reader-derived test candidate | True |

## Six-Camera Pairing Status

| Camera | Real RGB | Sim exact render | Source identity |
|---|---|---|---|
| CAM_BACK | no | no | no |
| CAM_BACK_LEFT | no | no | no |
| CAM_BACK_RIGHT | no | no | no |
| CAM_FRONT | no | no | no |
| CAM_FRONT_LEFT | no | no | no |
| CAM_FRONT_RIGHT | no | no | no |

## Receiver Scope

The attached receiver contract is `camera_only_rgb_single_frame_v0`. It can only support per-frame perception, visibility, lane/drivable relation, critical-object discovery, and single-frame risk ordering. It cannot support temporal, planning, control, or closed-loop claims until a matched temporal clip and full receiver input contract are available.

## Next Action

Recover the selected frame's six real RGB files and immutable source identity, render each camera using the listed exact metadata intrinsics and camtoworld pose, then run the frozen camera-only AD receiver on the matched real/sim observations.
