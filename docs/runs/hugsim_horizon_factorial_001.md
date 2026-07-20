# HUGSIM Rollout-Horizon and Actor-Removal Audit 001

Date: 2026-07-20

## Purpose

Independently test two weaknesses in the original 6-second multi-actor result:

1. whether the lead vehicle or cut-in vehicle caused the reported metric
   change;
2. whether the reported TTC/NC failures depended on missing future actor
   history at the end of the rollout.

The resulting 2×2 experiment contains:

| Condition | Lead | Far cut-in |
|---|---:|---:|
| no actors | no | no |
| lead only | yes | no |
| cut-in only | no | yes |
| lead + cut-in | yes | yes |

All four runs use the same scene, 9-second duration, deterministic plan,
corrected control convention, and HUGSIM commit.

## Runs

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s
artifacts/hugsim_contrast/scene-0383-lead-only-00-run002-9s
artifacts/hugsim_contrast/scene-0383-cut-in-only-00-run002-9s
artifacts/hugsim_contrast/scene-0383-multicar-cut-in-00-run002-9s
artifacts/hugsim_contrast/scene-0383-horizon-factorial-report-run002
```

Every run completed 36/36 steps. The writer sent 36 plans, received `Done`,
and no scoring error occurred.

## Finite-Rollout Finding

The saved scoring trajectory contains five future waypoints at 0.5-second
spacing. HUGSIM therefore needs 2.5 seconds of future actor states for each
metric frame.

```text
6-second run: horizon-valid through 3.5 s
9-second run: horizon-valid through 6.5 s
```

The original failures were outside the valid window:

```text
first TTC failure: 4.75 s
first NC failure: 5.75 s
```

The old 6-second combined run and the new 9-second combined run have exact
zero-difference prefixes through 6 seconds:

```text
timestamp: 0.0
ego box: 0.0
actor boxes: 0.0
plan: 0.0
action: 0.0
```

In the old run, every failed check uses a repeated final actor state and hits
actor0, the cut-in vehicle. With complete future history in the 9-second run,
the same frames all pass NC and TTC.

This is an accepted audit finding:

> The original 6-second NC/TTC decrease is a finite-rollout tail-padding
> artifact, not credible dynamic-risk evidence.

## Corrected Four-Condition Result

Horizon-valid window, 0.25–6.5 seconds:

| Condition | NC | TTC | PDMS |
|---|---:|---:|---:|
| no actors | 1.000 | 1.000 | 1.000 |
| lead only | 1.000 | 1.000 | 1.000 |
| far cut-in only | 1.000 | 1.000 | 1.000 |
| lead + far cut-in | 1.000 | 1.000 | 1.000 |

The four conditions have zero ego/action/plan differences. Actor0 follows the
same trajectory with or without the lead vehicle, and the lead follows the
same trajectory with or without actor0.

The far cut-in's minimum actual 2D oriented-footprint clearance is about
4.195 meters. It crosses the centerline visually but does not satisfy the
pre-specified near-distance treatment; no real-world near-miss threshold is
evaluated here.

## Credibility Judgment

`accepted`:

- exact short/extended common-prefix equivalence;
- identification of the old tail-padding artifact;
- strict four-condition input pairing;
- independent actor-state invariance across actor-removal conditions;
- multi-instance rendering and continuous state evolution.

`down-weighted`:

- full 9-second aggregate metrics, because frames after 6.5 seconds still lack
  complete future actor history;
- traffic realism of the scripted diagonal;
- real-world near-miss classification, because no independent threshold is
  defined;
- RGB/semantic/depth as real-sensor evidence.

`rejected`:

- the old 6-second TTC/NC decrease as dynamic-risk evidence;
- an actual collision in the far-cut-in scenario;
- AD-agent response or global HUGSIM credibility.

### How to Read `rejected`

`rejected` applies to the named claim, not to the value of the experiment.

| Rejected claim | Tested? | Basis | What the experiment establishes instead |
|---|---:|---|---|
| Timestamp zero equals the YAML actor initial state | yes | `invalidated_by_diagnostic` | `accepted`: reset advances the actor once before the first recorded state. |
| Old 6-second decrease is dynamic risk | yes | `invalidated_by_diagnostic` | `accepted`: missing future history and last-box padding create the apparent failure. |
| Far cut-in is an actual collision | yes | `contradicted_by_evidence` | `accepted`: collision remains false with about 4.195 m clearance. |
| AD-agent response | no | `not_tested` | No AD-agent capability conclusion. |
| Global HUGSIM credibility | no | `scope_exceeds_evidence` | No global capability conclusion. |

Thus this run rejects incorrect risk/collision interpretations and accepts two
HUGSIM implementation/measurement findings. Three task-local independent
Codex reviewer roles (experimental design, evidence, and reproducibility)
checked this separation; this is not an immutable external human-review
record. The machine-readable audit is also checked by the fail-closed
semantics validator.

## Reproduction

For each scenario, run the simulator in a GPU-visible shell:

```bash
env \
  PATH=/usr/local/cuda-12.1/bin:/home/yawei/.pixi/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CUDA_HOME=/usr/local/cuda-12.1 \
  TORCH_CUDA_ARCH_LIST=8.9 \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/run_hugsim_debug_smoke.py \
  --scenario SCENARIO_YAML \
  --max-steps 36 \
  --control-convention corrected \
  --output NEW_OUTPUT_DIRECTORY
```

Run the deterministic writer with the same step limit:

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/hugsim_plan_pipe_writer.py \
  --output NEW_OUTPUT_DIRECTORY \
  --horizon 6 \
  --step-m 1.0 \
  --max-steps 36
```

Generate the fail-closed horizon report:

```bash
MPLCONFIGDIR=/tmp/matplotlib-hugsim-horizon \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/analyze_hugsim_horizon_factorial.py \
  --no-actor artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s \
  --lead-only artifacts/hugsim_contrast/scene-0383-lead-only-00-run002-9s \
  --cut-in-only artifacts/hugsim_contrast/scene-0383-cut-in-only-00-run002-9s \
  --lead-and-cut-in artifacts/hugsim_contrast/scene-0383-multicar-cut-in-00-run002-9s \
  --short-lead-and-cut-in artifacts/hugsim_contrast/scene-0383-multicar-cut-in-00-run001 \
  --output artifacts/hugsim_contrast/scene-0383-horizon-factorial-report-run002
```

Validate the claim/finding semantics:

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/validate_hugsim_audit_semantics.py \
  docs/runs/hugsim_horizon_factorial_001_audit.json
```

## Inspectable Artifacts

```text
artifacts/hugsim_contrast/scene-0383-horizon-factorial-report-run002/horizon_sensitivity_and_clearance.png
artifacts/hugsim_contrast/scene-0383-horizon-factorial-report-run002/factorial_contact_sheet.png
artifacts/hugsim_contrast/scene-0383-horizon-factorial-report-run002/factorial_front_comparison.mp4
artifacts/hugsim_contrast/scene-0383-horizon-factorial-report-run002/horizon_factorial_summary.json
```
