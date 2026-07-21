# HUGSIM Frozen Camera Detector Stress Test 001

Date: 2026-07-21

## Purpose

Upgrade the previous semantic/depth receiver proxy to a real frozen RGB
detection model, while keeping the experiment bounded and avoiding full AD
stack claims.

Receiver:

```text
torchvision_fasterrcnn_mobilenet_v3_large_320_fpn_coco_v1
input: CAM_FRONT RGB only
road-object classes: bicycle, car, motorcycle, bus, truck
score threshold: 0.25
```

This receiver reports image-plane detections, confidence, simple tracking
continuity, and risk-ordering proxies based on box scale and center-path
overlap. It is not planning, control, closed-loop AD behavior, real-sensor
consistency, or global HUGSIM credibility evidence.

## Input Runs

The detector reuses the five equal-length runs from the AD receiver proxy
stress test:

```text
no_actor:
artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s

front_far:
artifacts/hugsim_contrast/scene-0383-ad-receiver-front-far-00-run001-9s

front_near:
artifacts/hugsim_contrast/scene-0383-ad-receiver-front-close-00-run001-9s

adjacent_near:
artifacts/hugsim_contrast/scene-0383-ad-receiver-adjacent-near-00-run001-9s

multicar_merge:
artifacts/hugsim_contrast/scene-0383-ad-receiver-multicar-merge-00-run001-9s
```

The detector weight was downloaded from torchvision and cached locally:

```text
url: https://download.pytorch.org/models/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth
sha256: 907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5
```

## Main Result

Artifacts:

```text
artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001
```

Summary:

| Condition | Detected frames | Center-path frames | Peak center risk | Peak center box area | Max detections | Mean center IoU |
|---|---:|---:|---:|---:|---:|---:|
| no_actor | 4/37 | 0/37 | 0.000 | 0.000 | 1 | n/a |
| front_far | 37/37 | 37/37 | 3.540 | 0.028 | 3 | 0.897 |
| front_near | 37/37 | 37/37 | 3.815 | 0.133 | 2 | 0.950 |
| adjacent_near | 13/37 | 0/37 | 0.000 | 0.000 | 1 | n/a |
| multicar_merge | 37/37 | 37/37 | 4.034 | 0.338 | 6 | 0.767 |

Causal checks:

| Check | Decision | Evidence |
|---|---|---|
| closer same-lane vehicle increases detector center-path risk and box scale | accepted | front_near center risk 3.815 > front_far 3.540; box area 0.133 > 0.028 |
| same-lane near vehicle outranks adjacent-lane vehicle on center-path risk | accepted | front_near center risk 3.815; adjacent_near center risk 0.000 |
| multi-car merge increases detector count and center-path risk | accepted | multicar risk 4.034 > front_far 3.540; max detections 6 > 3 |
| no-actor baseline still contains background/native detections | accepted | no_actor has 4 detected frames but 0 center-path frames |

Overall evidence:

```text
down-weighted
```

The detector supports the same causal directions as the semantic/depth proxy,
but through RGB-only model outputs. The separation is less dramatic than the
semantic/depth proxy, which is expected: a real detector sees background,
partial actors, confidence variation, and image-plane ambiguity.

## Key Findings

Positive evidence:

- HUGSIM's inserted vehicles are recognizable by an off-the-shelf frozen RGB
  detector.
- Near same-lane placement increases detected box scale and center-path risk
  compared with the far same-lane control.
- Adjacent-lane vehicles can be detected with high confidence, but they do not
  create center-path risk in this receiver mapping.
- The multi-car merge increases both detection count and center-path risk.

Boundary evidence:

- The no-actor baseline is not a zero-perception input: the detector finds
  native/background or edge road objects in 4/37 frames.
- Confidence alone is not a risk ordering. The adjacent-lane car can have high
  confidence while its center-path risk remains zero.
- This is a single-front-camera detector. It does not validate six-camera
  fusion, tracking across cameras, planning, control, or real-sim equivalence.

## Inspectable Artifacts

```text
artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001/camera_detector_response.png
artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001/camera_detector_front_contact_sheet.png
artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001/camera_detector_front_grid.mp4
artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001/camera_detector_timeseries.csv
artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001/camera_detector_summary.json
```

## Reproduction

If the weight is not already cached, allow network access once to download the
torchvision checkpoint, then run:

```bash
TORCH_HOME=/home/yawei/logsim-credibility-audit/artifacts/model_cache/torch \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/analyze_hugsim_camera_detector.py \
  --run no_actor=artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s \
  --run front_far=artifacts/hugsim_contrast/scene-0383-ad-receiver-front-far-00-run001-9s \
  --run front_near=artifacts/hugsim_contrast/scene-0383-ad-receiver-front-close-00-run001-9s \
  --run adjacent_near=artifacts/hugsim_contrast/scene-0383-ad-receiver-adjacent-near-00-run001-9s \
  --run multicar_merge=artifacts/hugsim_contrast/scene-0383-ad-receiver-multicar-merge-00-run001-9s \
  --output artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001 \
  --score-threshold 0.25
```

## Next Step

Use the same output schema with a driving-domain camera-only model when one is
available. The next upgrade should test whether detector boxes, confidence,
tracking stability, and risk ranking remain consistent under a receiver closer
to the target AD stack, then move toward matched real-sim input only after the
source anchor gate is unblocked.
