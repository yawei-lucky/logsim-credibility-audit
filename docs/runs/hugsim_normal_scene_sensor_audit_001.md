# HUGSIM Normal-Scene Sensor and Receiver Audit — Run 001

## Question

Do the two newly collected normal scenes expose materially different sensor
and receiver conditions, and are the existing diagnostics robust enough to
enter the metric evidence map?

This run audits metrics. It does not use HUGSIM semantic/depth as truth and does
not claim real-sensor or cross-camera 3D consistency.

## Inputs

| Scene | Run | Condition |
|---|---|---|
| `scene-0041` | `artifacts/hugsim_scene_collection/scene-0041-easy-00-run001-9s` | signalized intersection, no injected actor |
| `scene-0138` | `artifacts/hugsim_scene_collection/scene-0138-easy-00-run001-9s` | curved school-zone/occlusion road, no injected actor |

Both runs contain 37 observations (initial observation plus 36 completed
steps), six cameras, and synchronized RGB, semantic, and depth arrays.

## Measurements

### Array and calibration contract

For every frame and camera, the audit checks:

- RGB/semantic/depth shape agreement and expected data types;
- finite, positive depth values;
- image size and principal point against `cam_params`;
- `v2c` rotation orthonormality and determinant;
- calibration constancy over all 37 observations.

This establishes an internal receiver contract, not calibration against a real
rig.

### Cross-modal boundary diagnostics

Two deliberately diagnostic measurements are used:

1. fraction of semantic-boundary pixels lying within one pixel of a HUGSIM
   depth discontinuity greater than both 0.5 m and 5% relative depth;
2. mean RGB gradient on semantic boundaries divided by mean gradient away from
   those boundaries.

The thresholds are not credibility thresholds. They only make differences
between scenes and cameras inspectable.

### Frozen RGB receiver

The same frozen COCO Faster R-CNN MobileNetV3 receiver processes all 37
`CAM_FRONT` RGB arrays in both scenes at score threshold 0.25. This remains a
generic camera detector, not a full driving stack.

## Results

| Result | `scene-0041` | `scene-0138` |
|---|---:|---:|
| Array/calibration contract | accepted | accepted |
| Non-finite or non-positive depth pixels | 0 | 0 |
| Semantic boundary near depth edge, six-camera mean | 0.756 | 0.461 |
| Same measure, weakest camera | 0.684 (`BACK_LEFT`) | 0.162 (`FRONT_LEFT`) |
| RGB semantic-boundary gradient ratio, six-camera mean | 4.19 | 1.79 |
| Maximum frame-to-frame semantic-distribution L1 | 0.105 | 0.150 |
| Detector frames containing road-class output | 16/37 | 2/37 |
| Detector frames with center-path output | 16/37 | 0/37 |

The intersection scene has substantially stronger renderer-internal boundary
co-variation. The school/occlusion scene is harder, especially in the lateral
views affected by vegetation, blur, and reconstruction smearing. This is a
reproducible triage signal, not evidence that the first scene is realistic or
that the second is invalid.

## Material receiver finding

The detector output changes the interpretation materially:

- `scene-0041`: the visible native truck is detected increasingly confidently
  later in the sequence, but the largest box and peak center-path risk come
  earlier from the lower image / ego hood being classified as a nearby car.
- `scene-0138`: the only two car detections are low-confidence boxes on roadside
  vegetation/sign regions, not visible cars; neither overlaps the center path.

Therefore the accepted diagnostic is that the receiver and risk proxy are
sensitive to background/reconstruction nuisance. The claim that the current
center-path risk proxy is robust across these scenes is `rejected`. This is a
negative metric result, not a global HUGSIM failure.

## Evidence decisions

- `accepted`: bounded six-camera array/calibration contract and depth numerical
  validity.
- `down-weighted`: RGB/semantic/depth boundary co-variation, because all three
  are produced by HUGSIM and lack an independent reference.
- `rejected`: cross-scene robustness of the current center-path risk proxy.
- `rejected` with `tested=false`: real-sensor and cross-camera 3D consistency
  claims exceed this evidence. This does not mean those HUGSIM capabilities
  failed; they were not tested here.

## Artifacts

```text
artifacts/hugsim_normal_scene_sensor_audit/run001/normal_scene_sensor_diagnostics.png
artifacts/hugsim_normal_scene_sensor_audit/run001/normal_scene_receiver_arrays.png
artifacts/hugsim_normal_scene_sensor_audit/run001/normal_scene_sensor_audit.json
artifacts/hugsim_normal_scene_sensor_audit/run001/normal_scene_sensor_timeseries.csv
artifacts/hugsim_normal_scene_receiver/scene-0041-run001/
artifacts/hugsim_normal_scene_receiver/scene-0138-run001/
artifacts/hugsim_normal_scene_receiver/audit_examples/normal_scene_detection_examples.png
```

The receiver-input manifest in the raw JSON records frame, timestamp, camera,
shape, dtype, and SHA-256 for all six RGB arrays at the first, middle, and last
observations. The displayed arrays come from those same analyzed objects.

## Reproduction

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/audit_hugsim_normal_scene_sensors.py \
  --run intersection=artifacts/hugsim_scene_collection/scene-0041-easy-00-run001-9s \
  --run occlusion_school=artifacts/hugsim_scene_collection/scene-0138-easy-00-run001-9s \
  --output artifacts/hugsim_normal_scene_sensor_audit/run001
```

The frozen detector commands are the standard
`scripts/analyze_hugsim_camera_detector.py` invocation with each scene supplied
as `no_actor`, `CAM_FRONT`, score threshold 0.25, and the cached COCO weights.

## Next decision

Do not add a new aggregate credibility score. First separate factual visible
vehicles from ego-hood/roadside false positives in the receiver baseline and
replace the current risk proxy's raw maximum with a nuisance-audited receiver
contract. In parallel, treat `scene-0138` lateral cameras as the first targeted
case for internal projection/occlusion diagnostics. Controlled actors should
still wait until these normal-scene baselines are fixed.
