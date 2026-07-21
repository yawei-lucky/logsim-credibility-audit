# HUGSIM AD Receiver Proxy Stress Test 001

Date: 2026-07-21

## Purpose

Move beyond visually similar videos by creating large, controlled HUGSIM
counterfactuals and testing whether a frozen task receiver sees the expected
causal direction in task-relevant information.

This is not a real AD-agent experiment. The local machine has no installed
camera-only AD detector/stack weights, and `scene-0383` still lacks real RGB
source anchors. Therefore this run uses a deliberately narrow receiver:

```text
simulator_internal_task_receiver_proxy_v0
input: CAM_FRONT semantic + depth
outputs: vehicle visibility, center-path occupancy, depth, hazard proxy
```

It is useful as simulator-internal causal-response evidence. It cannot
establish real AD model response, real-sensor consistency, or global HUGSIM
credibility.

## Scenarios

New scenario configs:

```text
configs/hugsim/scenarios/scene-0383-ad-receiver-front-far-00.yaml
configs/hugsim/scenarios/scene-0383-ad-receiver-front-close-00.yaml
configs/hugsim/scenarios/scene-0383-ad-receiver-front-near-00.yaml
configs/hugsim/scenarios/scene-0383-ad-receiver-adjacent-near-00.yaml
configs/hugsim/scenarios/scene-0383-ad-receiver-multicar-merge-00.yaml
```

Main complete runs:

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

Boundary run:

```text
artifacts/hugsim_contrast/scene-0383-ad-receiver-front-near-00-run001-9s
```

The boundary run placed a same-lane vehicle too close. It terminated after
10/36 steps with runtime collision at 2.5 seconds and raw NC/TTC/PDMS all
zero. This is retained as a negative/boundary case, not included in the
equal-length receiver-proxy comparison.

## Receiver-Proxy Results

Main artifact:

```text
artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001
```

Summary:

| Condition | Peak hazard proxy | Peak vehicle area | Peak center-path area | Min top depth | Max components |
|---|---:|---:|---:|---:|---:|
| no_actor | 0.000 | 0.000 | 0.000 | n/a | 0 |
| front_far | 5.608 | 0.022 | 0.022 | 9.241 m | 1 |
| front_near | 14.230 | 0.109 | 0.056 | 3.705 m | 1 |
| adjacent_near | 6.501 | 0.048 | 0.000 | 5.015 m | 1 |
| multicar_merge | 31.889 | 0.318 | 0.079 | 2.039 m | 4 |

Causal checks:

| Check | Decision | Evidence |
|---|---|---|
| closer same-lane vehicle increases hazard and reduces depth | accepted | front_near peak hazard 14.230 > front_far 5.608; min depth 3.705 m < 9.241 m |
| same-lane near vehicle outranks adjacent-lane near vehicle | accepted | front_near peak hazard 14.230 > adjacent_near 6.501; adjacent center-path area remains 0 |
| multi-car merge is more prominent than far-front control | accepted | multicar peak hazard 31.889 > front_far 5.608; max components 4 > 1 |

Overall receiver-proxy evidence:

```text
down-weighted
```

The directionality is informative and supports a narrow internal causal
response claim. The evidence remains down-weighted because the receiver uses
HUGSIM semantic/depth outputs rather than a real AD perception model, all
actors reuse the same vehicle asset, and no matched real source observation is
available.

## HUGSIM Metric Cross-Check

The metric horizon is complete through 6.5 seconds. In that valid window:

| Condition | NC | TTC | PDMS |
|---|---:|---:|---:|
| front_far | 1.000 | 1.000 | 1.000 |
| front_near | 1.000 | 1.000 | 1.000 |
| adjacent_near | 1.000 | 1.000 | 1.000 |
| multicar_merge | 1.000 | 0.115 | 0.368 |

The front_near run's raw late NC/TTC failures begin after 6.5 seconds and are
not used as valid risk evidence. The multicar_merge TTC response begins at
1.0 seconds, inside the complete-history window.

## Inspectable Artifacts

```text
artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001/ad_receiver_proxy_response.png
artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001/ad_receiver_proxy_front_contact_sheet.png
artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001/ad_receiver_proxy_front_grid.mp4
artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001/ad_receiver_proxy_timeseries.csv
artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001/ad_receiver_proxy_summary.json
```

## Reproduction

Run each new HUGSIM case in a GPU-visible shell:

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/run_hugsim_case.py \
  --scenario configs/hugsim/scenarios/scene-0383-ad-receiver-front-far-00.yaml \
  --output artifacts/hugsim_contrast/scene-0383-ad-receiver-front-far-00-run001-9s \
  --max-steps 36
```

Repeat with the other scenario/output pairs listed above. The wrapper launches
`scripts/run_hugsim_debug_smoke.py` and `scripts/hugsim_plan_pipe_writer.py`
with the CUDA 12.1 environment variables from the runbook.

Then regenerate the receiver-proxy report:

```bash
MPLCONFIGDIR=/tmp/matplotlib-hugsim-ad-receiver-proxy \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/analyze_hugsim_ad_receiver_proxy.py \
  --run no_actor=artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s \
  --run front_far=artifacts/hugsim_contrast/scene-0383-ad-receiver-front-far-00-run001-9s \
  --run front_near=artifacts/hugsim_contrast/scene-0383-ad-receiver-front-close-00-run001-9s \
  --run adjacent_near=artifacts/hugsim_contrast/scene-0383-ad-receiver-adjacent-near-00-run001-9s \
  --run multicar_merge=artifacts/hugsim_contrast/scene-0383-ad-receiver-multicar-merge-00-run001-9s \
  --output artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001
```

## Interpretation

This is the first AD-oriented bridge experiment in the repository. It does not
yet answer "will a real AD model behave the same in reality and simulation?"
It does show that large HUGSIM interventions can be converted into a frozen,
task-level receiver contract and checked for causal direction before a heavy AD
stack is installed.

Useful evidence retained:

- positive: distance, lane relation, and multi-actor intervention directions
  are visible in task-relevant semantic/depth signals;
- negative/boundary: an overly close same-lane placement forces a runtime
  collision and cannot be used for equal-length receiver comparison;
- boundary: HUGSIM's own late NC/TTC outputs still require complete-future
  filtering; receiver-proxy evidence and simulator metrics must be interpreted
  separately.

Next material step: plug in a frozen camera-only AD perception model when
weights are available, using the same scenario set and output schema, then
compare detector boxes/confidence/tracking/risk ranking against this proxy
baseline.
