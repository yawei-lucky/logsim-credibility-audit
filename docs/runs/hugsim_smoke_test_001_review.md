# HUGSIM Smoke Test 001 — Research Commander Review

Date: 2026-07-10

## Review Purpose

This file clarifies the interpretation of `docs/runs/hugsim_smoke_test_001.md`.

The original run report is useful as an engineering log, but several terms need to be interpreted carefully so that the project does not confuse environment setup with closed-loop credibility evidence.

## Correct Interpretation

### 1. This was not a successful closed-loop smoke test

The run did **not** reach:

```text
env.reset
obs_pipe
plan_pipe
env.step
output files
credibility judgment
```

Therefore the correct evidence status is:

```text
not enough closed-loop evidence
```

This is more precise than simply saying `not enough evidence`, because the run did produce useful environment evidence, but no closed-loop simulator segment.

### 2. The main successful result was environment diagnosis and repair

The run identified and partially resolved the HUGSIM CUDA / pixi installation problem.

The important engineering outcome is:

```text
RTX 4090 D / compute capability 8.9
+ CUDA 12.1 toolkit
+ PyTorch cu121 wheels
+ TORCH_CUDA_ARCH_LIST=8.9
```

This combination allowed the HUGSIM pixi environment to install and import key dependencies such as `gsplat`, `tinycudann`, `pytorch3d`, and `hugsim_env`.

This is a prerequisite for the smoke test, not the smoke test itself.

### 3. Deterministic plan-pipe writer is not an AD agent

The deterministic plan-pipe writer should be interpreted as a loop-enabling dummy planner.

It is only intended to test:

```text
obs_pipe / plan_pipe
→ trajectory-to-control
→ env.step
→ state update
→ output generation
```

It must not be used to make claims about AD-agent performance.

If a collision or off-road event occurs under this dummy planner, it should be interpreted as simulator-loop evidence or metric-path evidence, not as an AD-model failure.

### 4. accepted / down-weighted / rejected are evidence labels

The labels:

```text
accepted
down-weighted
rejected
```

are not the project goal and are not the final simulator credibility metric.

They are current-stage evidence qualification labels. They can be used to screen individual closed-loop segments and can later support a quantitative credibility metric, but they are not yet a complete numerical score.

### 5. Storage interpretation should be corrected

The original run report recorded `/data` as full. The user later clarified that `/home/yawei` has about 300GB available.

Next runs should therefore place assets and outputs under `/home/yawei`, for example:

```text
/home/yawei/hugsim_sample_data
/home/yawei/hugsim_assets
/home/yawei/hugsim_outputs
```

Avoid using `/data` unless space has been cleared.

## Current Remaining Requirements

Before a real closed-loop audit can begin, the next run must produce at least one closed-loop segment with:

- public scene / scenario source;
- local HUGSIM base config paths;
- successful `env.reset`;
- working `obs_pipe` and `plan_pipe`;
- at least one `env.step`;
- output files such as `data.pkl`, `video.mp4`, `infos.pkl`, `eval.json`, `ground.ply`, and `scene.ply`;
- one event-level credibility record.

## Research Judgment

The current experiment design remains valid.

Its purpose is not to prove HUGSIM credible. Its purpose is to build a HUGSIM-based closed-loop evidence pipeline so that the project can later define credible simulator evidence conditions and quantitative credibility metrics.
