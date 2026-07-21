# HUGSIM Cross-Receiver Task-Response Agreement 001

Date: 2026-07-21

## Purpose

Compare two frozen receivers on the same HUGSIM counterfactual rollouts:

```text
semantic/depth task proxy:
  simulator_internal_task_receiver_proxy_v0

RGB detector:
  torchvision_fasterrcnn_mobilenet_v3_large_320_fpn_coco_v1
```

The question is not whether either receiver is a full AD stack. The question
is narrower and more useful at this stage:

> Do different receivers preserve the same task-relevant causal direction for
> distance, lane relation, and multi-car merge interventions?

This is simulator-internal task-response agreement evidence. It is not
matched real-sim equivalence, planning/control evidence, or global HUGSIM
credibility.

## Input Artifacts

```text
semantic/depth proxy:
artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001

RGB detector:
artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001
```

Both receivers use the same five HUGSIM rollouts:

```text
no_actor
front_far
front_near
adjacent_near
multicar_merge
```

The aligned center-path signal is:

| Receiver | Center-path signal |
|---|---|
| semantic/depth proxy | `center_vehicle_area_fraction` |
| RGB detector | `center_top_risk_proxy` |

## Result

Artifacts:

```text
artifacts/hugsim_receiver_agreement/scene-0383-receiver-agreement-run002
```

Run-level center-path summary:

| Condition | Proxy peak center | Detector peak center | Proxy center frames | Detector center frames | Classification |
|---|---:|---:|---:|---:|---|
| no_actor | 0.000 | 0.000 | 0/37 | 0/37 | non-center/background signal |
| front_far | 0.022 | 3.540 | 37/37 | 37/37 | center-path signal |
| front_near | 0.056 | 3.815 | 37/37 | 37/37 | center-path signal |
| adjacent_near | 0.000 | 0.000 | 0/37 | 0/37 | non-center/background signal |
| multicar_merge | 0.079 | 4.034 | 37/37 | 37/37 | center-path signal |

Agreement checks:

| Check | Decision | Evidence |
|---|---|---|
| close-front > far-front | accepted | both receivers rank `front_near` above `front_far` on center-path signal |
| close-front > adjacent-near | accepted | both receivers rank `front_near` above `adjacent_near` |
| multicar-merge > far-front | accepted | both receivers rank `multicar_merge` above `front_far` |
| run-level center-path rank agreement | accepted | Spearman rank agreement = 1.0 |
| no-actor background divergence boundary | accepted | proxy has 0 visible frames; detector reports 4 no-actor detected frames |

Overall evidence:

```text
down-weighted
```

The evidence is accepted for narrow receiver-agreement subclaims, but the
overall experiment remains down-weighted because both receivers still consume
simulated HUGSIM observations only, no real source log is paired, and neither
receiver is a full AD stack with planning/control.

## Interpretation

Positive evidence:

- Two different receiver constructions agree on the causal direction of the
  tested task variables.
- The center-path ordering is stable at run level:

```text
no_actor / adjacent_near
< front_far
< front_near
< multicar_merge
```

- This supports using receiver-response agreement as a candidate task-level
  evidence pattern for future credibility metrics.

Boundary evidence:

- The RGB detector sees native/background or edge road objects in `no_actor`.
  A real receiver's input is therefore not identical to the intervention
  variable "no injected actor".
- The adjacent-lane vehicle is visible to both receiver families but remains
  zero on the center-path signal. This is exactly why confidence or visibility
  alone should not be treated as task risk.
- Cross-receiver agreement inside HUGSIM does not prove real-world fidelity.
  It only strengthens simulator-internal task-response evidence.

## Inspectable Artifacts

```text
artifacts/hugsim_receiver_agreement/scene-0383-receiver-agreement-run002/receiver_agreement.png
artifacts/hugsim_receiver_agreement/scene-0383-receiver-agreement-run002/receiver_agreement_summary.json
artifacts/hugsim_receiver_agreement/scene-0383-receiver-agreement-run002/receiver_agreement_by_run.csv
artifacts/hugsim_receiver_agreement/scene-0383-receiver-agreement-run002/receiver_agreement_timeseries.csv
```

## Reproduction

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/analyze_hugsim_receiver_agreement.py \
  --output artifacts/hugsim_receiver_agreement/scene-0383-receiver-agreement-run002
```

The script reads the two prior receiver result directories by default:

```text
artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001
artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001
```

## Next Step

Replace the generic COCO detector with a driving-domain camera-only perception
receiver when a suitable frozen model is available. Keep the same cross-
receiver agreement format so future experiments can compare:

```text
semantic/depth proxy
→ generic RGB detector
→ driving-domain RGB detector/AD perception receiver
→ matched real-sim receiver comparison once source anchors exist
```
