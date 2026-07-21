# HUGSIM Source-Anchor Availability Gate 001

Date: 2026-07-21

## Purpose

Determine whether the currently released and locally available `scene-0383`
assets can support the first strict real-log versus HUGSIM matched-pose
comparison.

This is an availability and pairing gate. It does not score HUGSIM image
quality or simulator credibility.

## Result

```text
gate status: blocked
available: calibration/pose/timestamp skeleton and reconstructed assets
missing: real RGB and immutable source sample identity
permitted claim: metadata-only frame-index candidates exist
not permitted: a real-sim observation pair has been established
```

The released scene metadata contains:

- 180 timestamps from `0.0` to `14.9158` seconds;
- six cameras and 1080 total frame records;
- per-frame intrinsics and camera-to-world poses;
- one native dynamic vehicle ID and timestamp-specific poses;
- 36 test-candidate timestamp groups inferred from the current local
  `dataset_readers.py` rule (`idx % 30 >= 24`).

However, all 1080 referenced real RGB files are absent locally. The released
zip contains only the minimized scene, native dynamic model, scene config,
ground parameters, and metadata. It does not contain the referenced `images/`
tree. The metadata also does not retain original nuScenes `sample` or
`sample_data` tokens.

The official HUGSIM data preparation instructions require nuScenes sweep data
to be converted through ASAP into `interp_12Hz_trainval`; that converted
source metadata is also absent locally. See the official
[HUGSIM data preparation document](https://github.com/hyzhou404/HUGSIM/blob/main/data/README.md)
and the official
[released scene directory](https://huggingface.co/datasets/XDimLab/HUGSIM/tree/main/scenes/nuscenes).

The released checkpoint does not identify the exact training commit or split
provenance. Therefore these 36 groups are test candidates under the inspected
reader logic, not independently confirmed held-out views for that checkpoint.

## Why Existing Rollout Frames Are Not Matched Poses

The existing no-actor simulation output is complete and contains six-camera
RGB, semantic, and depth observations, but its standard camera template is not
identical to the reconstruction-source cameras.

At metadata timestamp zero, the automated comparison reports:

| Quantity | Maximum difference |
|---|---:|
| combined relative translation | 0.310 m |
| relative rotation | 3.412° |
| focal length | 7.368 px |
| principal point | 21.690 px |

The simulation template also applies a `0.3 m` camera-rect translation, and
`CAM_BACK` uses `800×450` while the released source metadata records
`800×410`.

Therefore the current closed-loop reset image must not be presented as a
strict matched-pose reconstruction. The first factual comparison must render
with each selected metadata frame's exact `K` and `camtoworld`.

## Reader-Derived Test Candidates

HUGSIM's nuScenes reader assigns each fifth timestamp group to its test split.
Under the inspected local commit, there are 36 six-camera test candidates:

```text
frame indices: 4, 9, 14, ..., 179
first candidate: frame 00004 at t=0.333595 s
```

Frame `00004` is only a frame-index candidate until its original nuScenes
identity and six real images are recovered. When rendering a timestamp with a
native dynamic object, the released dynamic model and metadata pose must also
be loaded; otherwise a missing real actor would confound the comparison.

## Required Next Action

1. Obtain the licensed official nuScenes camera blobs.
2. Obtain or reproduce the ASAP `interp_12Hz_trainval` metadata used by
   HUGSIM.
3. Recover and record scene/frame/camera tokens and native timestamps.
4. Verify the processed images against the released relative paths and
   calibration.
5. Verify checkpoint training/split provenance, then render test candidates
   using exact metadata intrinsics and poses.
6. Freeze a receiver interface and begin receiver-internal real-versus-sim
   comparison.

Until these conditions pass, this work supports source-anchor feasibility and
gap identification only. It does not support sensor-consistency or receiver-
behavior conclusions.

## Reproduction

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/audit_hugsim_source_anchor.py \
  --scene-dir /home/yawei/HUGSIM_assets/scenes/nuscenes/scene-0383 \
  --camera-yaml /home/yawei/HUGSIM/configs/sim/nuscenes_camera.yaml \
  --sim-run artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s \
  --dataset-reader /home/yawei/HUGSIM/scene/dataset_readers.py \
  --hugsim-repo /home/yawei/HUGSIM \
  --output NEW_OUTPUT_DIRECTORY/source_anchor_gate.json
```

The command intentionally exits nonzero while the gate is blocked and refuses
to overwrite an existing output.

## Inspectable Records

```text
docs/runs/hugsim_source_anchor_gate_001.json
artifacts/hugsim_source_anchor/scene-0383-source-anchor-gate-run003/source_anchor_gate.json
```

The hardened gate also fails closed on corrupt or wrong-size images,
incomplete per-frame source identities, incomplete six-camera timestamp
groups, repeated image paths/frame indices, invalid nuScenes token grouping,
invalid camera/dynamic transforms, and missing native dynamic models.
The raw record includes hashes for this audit script and the inspected HUGSIM
reader, plus the HUGSIM commit.
