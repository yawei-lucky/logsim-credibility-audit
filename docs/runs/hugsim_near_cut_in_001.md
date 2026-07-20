# HUGSIM Near-Distance Cut-In Stress Test 001

Date: 2026-07-20

## Purpose

After rejecting the old far-cut-in risk result as a finite-rollout artifact,
run one visibly stronger, single-shot treatment that distinguishes:

```text
centerline crossing without risk
vs
positive-clearance close pass with an internal TTC response
```

The parameters and stop criteria were fixed before execution by an independent
design review. The scenario was not committed or externally registered before
the run, so this is **pre-specified**, not a formal immutable preregistration.
No post-run parameter tuning or repeat treatment was performed.

## Configuration

```text
configs/hugsim/scenarios/scene-0383-near-cut-in-00.yaml
```

| Actor | Right | Forward | Yaw | Speed | Role |
|---|---:|---:|---:|---:|---|
| 0 | 4.0 m | 6.5 m | 0.60 rad | 1.7 m/s | near-distance diagonal cut-in |
| 1 | 0.0 m | 24.0 m | 0.0 rad | 0.5 m/s | far lead negative control |

Both actors reuse vehicle asset `2024_07_05_15_57_10` and use
`ConstantPlanner`. This remains a scripted renderer/geometry/metric stress
test, not a validated lane-change policy.

## Pre-Specified Stop Criteria

- complete 36/36 steps and receive `Done`;
- preserve exact ego/action/plan/timestamp pairing;
- actor0 crosses the ego centerline no later than 4.25 seconds;
- minimum positive 2D oriented-footprint clearance is at most 1 meter between
  4 and 6 seconds;
- NC remains 1, runtime collision remains false;
- TTC changes inside the complete-future-history window and hits only actor0;
- stop after this treatment, whether it passes or fails.

## Runs

```text
baseline:
artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s

far-cut-in control:
artifacts/hugsim_contrast/scene-0383-multicar-cut-in-00-run002-9s

near-cut-in treatment:
artifacts/hugsim_contrast/scene-0383-near-cut-in-00-run001-9s

cross-modal report:
artifacts/hugsim_contrast/scene-0383-near-cut-in-report-run001

horizon-valid audit:
artifacts/hugsim_contrast/scene-0383-near-cut-in-audit-run002
```

The treatment completed 36/36 steps, the writer completed the same-value
`Done` handshake, and scoring completed without error.

## Main Result

Horizon-valid window, 0.25–6.5 seconds:

| Condition | NC | TTC | PDMS |
|---|---:|---:|---:|
| no actors | 1.000 | 1.000 | 1.000 |
| far cut-in control | 1.000 | 1.000 | 1.000 |
| near cut-in treatment | 1.000 | 0.1154 | 0.3681 |

The full 9-second treatment reports TTC `0.3611` and PDMS `0.5437`, but that
aggregate includes the incomplete-history tail after 6.5 seconds and is only
auxiliary. The main result is the filtered window above.

Exact event evidence:

```text
centerline crossing: 3.917 s
minimum 2D oriented-footprint clearance: 0.730 m at 5.5 s
first TTC failure: 1.0 s
TTC failures in valid window: 23 frames
failed-event actor IDs: [0]
failed events using tail padding: none
NC failure: none
runtime collision: false
```

The baseline, far-control, and near-treatment runs have zero differences in
timestamp, plan, ego box, and action. The far lead never contributes to a
failed TTC check.

## Sensor-Side Internal Evidence

Across the horizon-valid observations, injected-car semantic pixels are
supported by RGB differences for approximately 89.8%–98.4% of pixels and by
depth differences for 100%.

This supports internal RGB/semantic/depth co-movement. It does not establish
real-sensor correctness because all modalities come from the same renderer,
the actors reuse one asset, and the vehicle/background appearance mismatch
remains visible.

## Credibility Judgment

Overall segment:

```text
down-weighted
```

`accepted` narrow subclaims:

- exact experimental pairing;
- continuous actor0 motion and centerline crossing;
- a positive-clearance 2D close pass;
- an actor0-specific HUGSIM internal TTC surrogate response inside the
  complete-future-history window, with no padding;
- internal RGB/semantic/depth co-movement.

`down-weighted`:

- the unfiltered 9-second aggregate;
- calling the event a real-world near miss without an independently defined
  real-world threshold;
- scripted merge realism;
- rendered observations as E2E sensor evidence.

`rejected`:

- an actual collision;
- interpreting HUGSIM's binary TTC surrogate as physical time-to-collision;
- an AD-agent response;
- real traffic validity or global HUGSIM credibility.

Three independent reviews agreed that the pre-specified stop criteria were met
and that another parameter adjustment would become post-hoc result chasing.
This experiment therefore stops here.

## Reproduction

GPU-visible runner:

```bash
env \
  PATH=/usr/local/cuda-12.1/bin:/home/yawei/.pixi/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CUDA_HOME=/usr/local/cuda-12.1 \
  TORCH_CUDA_ARCH_LIST=8.9 \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/run_hugsim_debug_smoke.py \
  --scenario configs/hugsim/scenarios/scene-0383-near-cut-in-00.yaml \
  --max-steps 36 \
  --control-convention corrected \
  --output artifacts/hugsim_contrast/scene-0383-near-cut-in-00-run001-9s
```

Writer:

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/hugsim_plan_pipe_writer.py \
  --output artifacts/hugsim_contrast/scene-0383-near-cut-in-00-run001-9s \
  --horizon 6 \
  --step-m 1.0 \
  --max-steps 36
```

Cross-modal analysis, including the exact non-default frame selection:

```bash
MPLCONFIGDIR=/tmp/matplotlib-hugsim-near \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/analyze_hugsim_multicar.py \
  --baseline artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s \
  --treatment artifacts/hugsim_contrast/scene-0383-near-cut-in-00-run001-9s \
  --output artifacts/hugsim_contrast/scene-0383-near-cut-in-report-run001 \
  --frames 0,12,16,22,26,36
```

Fail-closed horizon-valid analysis:

```bash
MPLCONFIGDIR=/tmp/matplotlib-hugsim-near-audit \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/analyze_hugsim_near_cutin.py \
  --baseline artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s \
  --far-cut-in-control artifacts/hugsim_contrast/scene-0383-multicar-cut-in-00-run002-9s \
  --near-cut-in artifacts/hugsim_contrast/scene-0383-near-cut-in-00-run001-9s \
  --cross-modal-report artifacts/hugsim_contrast/scene-0383-near-cut-in-report-run001 \
  --output artifacts/hugsim_contrast/scene-0383-near-cut-in-audit-run002
```

## Inspectable Artifacts

```text
artifacts/hugsim_contrast/scene-0383-near-cut-in-report-run001/front_multicar_comparison.mp4
artifacts/hugsim_contrast/scene-0383-near-cut-in-report-run001/front_multicar_contact_sheet.png
artifacts/hugsim_contrast/scene-0383-near-cut-in-audit-run002/near_cutin_risk_and_clearance.png
artifacts/hugsim_contrast/scene-0383-near-cut-in-audit-run002/near_cutin_summary.json
```
