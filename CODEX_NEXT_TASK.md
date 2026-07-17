# Codex Next Task — Strengthen HUGSIM Evidence Quality

> Read this file first when resuming HUGSIM work.

## Current Context

The first HUGSIM closed-loop evidence pipeline is now operational.

Completed on 2026-07-17:

```text
public scene-0383 asset
→ local smoke config
→ HUGSIM env.reset
→ obs_pipe / plan_pipe
→ deterministic trajectory
→ env.step
→ RGB / semantic / depth observations
→ state and metric outputs
→ segment-level credibility judgment
```

The successful run is documented in:

```text
docs/runs/hugsim_smoke_test_002.md
docs/runs/hugsim_smoke_test_002_audit.json
```

The first segment is labeled:

```text
down-weighted
```

This label means the run is useful evidence that the closed-loop evidence
pipeline works, but it is not yet strong enough to support broader simulator
credibility claims.

## Project Purpose

HUGSIM is the current experimental carrier, not the final research goal.

The project-level question remains:

```text
Can a closed-loop simulator result be trusted as evidence for evaluating an
end-to-end autonomous-driving model?
```

The current method route remains:

1. Source Availability Gate.
2. Closed-loop Evidence Completeness.
3. Segment-level Evidence Judgment.
4. Future quantitative credibility metric after multiple real segments exist.

## Current Machine and Assets

```text
HUGSIM repo: /home/yawei/HUGSIM
Audit repo: /home/yawei/logsim-credibility-audit
Scene asset: /home/yawei/HUGSIM_assets/scenes/nuscenes/scene-0383
Local config: configs/hugsim/nuscenes_smoke_base.yaml
First output: artifacts/hugsim_smoke/scene-0383-easy-00-run001
```

Runtime:

```text
GPU: NVIDIA GeForce RTX 4090 D
compute capability: 8.9
PyTorch: 2.4.1+cu121
CUDA toolkit: /usr/local/cuda-12.1
TORCH_CUDA_ARCH_LIST: 8.9
```

The default Codex sandbox cannot see the GPU. GPU-dependent commands must run
in an approved GPU-visible context.

Do not use `/data`; it was full during the first run.

## Evidence Already Produced

The first successful run completed three deterministic steps from timestamp
0.0 to 0.75 seconds and generated:

```text
audit_steps.pkl
audit_summary.json
data.pkl
eval.json
ground.ply
infos.pkl
observations.pkl
scene.ply
video.mp4
```

HUGSIM metrics for the intentionally short run:

```text
NC: 1.0
DAC: 1.0
TTC: 1.0
Comfort: 1.0
PDMS: 1.0
Route completion: 0.02147620662371425
HDScore: 0.02147620662371425
```

These are smoke-run outputs, not benchmark results.

## Why the First Segment Is Down-Weighted

- The segment is only 0.75 seconds long.
- The scenario has no dynamic actor.
- Lateral RGB views contain visible reconstruction blur and smearing.
- Semantic and depth outputs passed numerical sanity checks but not pixel-level
  cross-modal validation.
- The normal no-collision segment cannot validate collision, near-miss,
  occlusion, or risk attribution.

## Immediate Goal

Strengthen the evidence quality on the already working `scene-0383`
deterministic loop before adding dynamic actors.

Target:

```text
synchronized RGB / semantic / depth evidence
→ cross-modal consistency checks
→ longer bounded normal rollout
→ state / rendering / metric stability review
→ updated credibility judgment
```

## Step-by-Step Task

### Step 1 — Export Cross-Modal Comparison Sheets

Use the existing:

```text
artifacts/hugsim_smoke/scene-0383-easy-00-run001/observations.pkl
```

Produce synchronized per-camera views for:

- RGB;
- semantic labels;
- depth;
- useful edge overlays if they can be generated deterministically.

Keep large generated images under `artifacts/`, which is ignored by Git.

### Step 2 — Check Cross-Modal Consistency

For each camera, inspect:

- road and sidewalk semantic boundaries;
- depth discontinuities at buildings, vegetation, poles, and road edges;
- whether RGB edges align with semantic/depth edges;
- whether the same relation remains stable across the four timestamps;
- obvious holes, floating regions, smearing, or view-boundary artifacts.

Record concrete observations. Do not reduce this to aesthetic quality.

### Step 3 — Run a Longer Bounded Normal Segment

Use:

```text
scripts/run_hugsim_debug_smoke.py
scripts/hugsim_plan_pipe_writer.py
```

Choose a bounded length that remains practical for manual inspection. Use a new
output directory; the runner refuses to overwrite an existing run.

Keep the deterministic planner interpretation clear:

```text
It enables the simulator loop. It is not an AD agent.
```

### Step 4 — Compare Stability

Check:

- ego state continuity;
- route-completion monotonicity;
- collision flags;
- camera-view temporal stability;
- semantic/depth temporal stability;
- metric stability;
- whether extrapolated-view artifacts increase as the ego moves.

### Step 5 — Update the Evidence Record

Create a new run report and compact JSON audit record.

Use exactly one of:

```text
accepted
down-weighted
rejected
```

Do not upgrade to `accepted` unless the evidence satisfies
`docs/hugsim_credibility_decision_rules.md`.

## Files to Read

```text
README.md
PROJECT_STATE.md
docs/hugsim_smoke_test_plan.md
docs/hugsim_credibility_decision_rules.md
docs/hugsim_cuda_pixi_runbook.md
docs/runs/hugsim_smoke_test_001.md
docs/runs/hugsim_smoke_test_001_review.md
docs/runs/hugsim_smoke_test_002.md
docs/runs/hugsim_smoke_test_002_audit.json
configs/hugsim/nuscenes_smoke_base.yaml
scripts/hugsim_plan_pipe_writer.py
scripts/run_hugsim_debug_smoke.py
```

## Do Not Do

Do not:

- repeat broad CUDA/Pixi installation unless verification fails;
- overwrite the first successful run;
- use `/data`;
- train a new 3DGS scene;
- run the full HUGSIM benchmark;
- install UniAD / VAD / LTF for this task;
- treat the deterministic writer as an AD model;
- add dynamic actors before the normal-scene evidence is reviewed;
- claim HUGSIM is globally credible or non-credible;
- expand to OmniDreams / Cosmos;
- define the final quantitative credibility metric from one run.

## Success Criteria

Minimum:

- synchronized RGB / semantic / depth evidence is inspectable;
- cross-modal findings are recorded;
- a longer bounded rollout completes or fails with a documented cause.

Research success:

- the new evidence supports a defensible segment-level qualification;
- the project can explain exactly which simulator evidence is strong, weak, or
  contradictory.
