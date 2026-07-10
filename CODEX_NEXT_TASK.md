# Codex Next Task — HUGSIM Closed-Loop Evidence Pipeline

> Read this file first when resuming the HUGSIM smoke-test work.

## Current Context

This repository is not trying to prove HUGSIM is globally credible and is not trying to reproduce the full HUGSIM benchmark.

The current phase uses HUGSIM as an experimental carrier to build a **closed-loop evidence pipeline** for future simulation-credibility auditing.

Project-level question:

```text
Can a closed-loop simulator result be trusted as evidence for evaluating an end-to-end autonomous-driving model?
```

Current phase question:

```text
Can HUGSIM produce a complete closed-loop evidence record that can later be judged as accepted, down-weighted, or rejected?
```

## Method Route

The current method has four steps:

1. **Source Availability Gate**
   - Check whether paper, code, data, runtime, and evaluation scripts are available.

2. **Closed-loop Evidence Completeness**
   - Check whether one run produces observation, planner output, action, ego/actor state update, metrics, and output files.

3. **Segment-level Evidence Judgment**
   - Judge a segment as `accepted`, `down-weighted`, or `rejected`.
   - These labels are evidence-qualification labels, not the final project goal and not a final numeric metric.

4. **Future Credibility Metric**
   - Define a quantitative credibility metric only after multiple real runs and segments exist.

## Current Status

Completed:

- HUGSIM source availability gate.
- HUGSIM pipeline and closed-loop mechanism extraction.
- HUGSIM smoke-test plan.
- deterministic plan-pipe writer.
- accepted / down-weighted / rejected evidence rules.
- HUGSIM CUDA / pixi troubleshooting runbook.
- First run report: `docs/runs/hugsim_smoke_test_001.md`.
- Research Commander review of the first report: `docs/runs/hugsim_smoke_test_001_review.md`.

Important status:

```text
The first run did not produce closed-loop simulator evidence.
```

It was an environment bring-up report. It did **not** reach:

```text
env.reset
→ obs_pipe
→ plan_pipe
→ env.step
→ output files
→ credibility judgment
```

## Current Machine Notes

Known local paths from the first run:

```text
HUGSIM repo: /home/yawei/HUGSIM
Audit repo: /home/yawei/logsim-credibility-audit
```

Known storage constraint:

```text
/data is full. Do not use /data for this task.
```

Use these paths instead:

```text
/home/yawei/hugsim_assets
/home/yawei/hugsim_outputs
/home/yawei/hugsim_sample_data
```

Known environment fix:

- GPU: NVIDIA GeForce RTX 4090 D.
- compute capability: 8.9.
- use CUDA toolkit: `/usr/local/cuda-12.1`.
- avoid default `/usr/bin/nvcc` CUDA 11.5 for extension builds.
- HUGSIM pixi environment should use PyTorch `cu121`, not `cu118`.
- use `TORCH_CUDA_ARCH_LIST=8.9`.

Read this runbook before touching CUDA / pixi:

```text
docs/hugsim_cuda_pixi_runbook.md
```

## Files to Read Before Running Commands

Read these files first:

```text
README.md
PROJECT_STATE.md
docs/hugsim_audit.md
docs/hugsim_smoke_test_plan.md
docs/hugsim_credibility_decision_rules.md
docs/hugsim_cuda_pixi_runbook.md
docs/runs/hugsim_smoke_test_001.md
docs/runs/hugsim_smoke_test_001_review.md
scripts/check_hugsim_smoke_prereqs.py
scripts/hugsim_plan_pipe_writer.py
```

Also inspect these HUGSIM files:

```text
/home/yawei/HUGSIM/README.md
/home/yawei/HUGSIM/closed_loop.py
/home/yawei/HUGSIM/configs/sim/nuscenes_base.yaml
/home/yawei/HUGSIM/configs/sim/nuscenes_camera.yaml
/home/yawei/HUGSIM/configs/sim/kinematic.yaml
/home/yawei/HUGSIM/configs/benchmark/nuscenes/scene-0383-easy-00.yaml
/home/yawei/HUGSIM/sim/hugsim_env/envs/hug_sim.py
/home/yawei/HUGSIM/sim/utils/plan.py
/home/yawei/HUGSIM/sim/utils/sim_utils.py
/home/yawei/HUGSIM/sim/utils/score_calculator.py
```

## Do Not Do

Do not:

- use `/data` for downloads or outputs;
- rerun broad environment installation from scratch unless verification fails;
- train a new 3DGS scene;
- run the full HUGSIM benchmark;
- install or run UniAD / VAD / LTF unless absolutely necessary;
- claim HUGSIM is credible or non-credible globally;
- treat deterministic plan-pipe writer as an AD agent;
- close GitHub Issue #8;
- expand to OmniDreams / Cosmos;
- modify unrelated files.

## Immediate Goal

Move from:

```text
environment installed
```

to:

```text
first HUGSIM closed-loop evidence segment produced
```

The minimal target is to produce or clearly fail while trying to produce:

```text
data.pkl
video.mp4
infos.pkl
eval.json
ground.ply
scene.ply
```

## Step-by-Step Task

### Step 1 — Verify GPU-visible HUGSIM Environment

Run in a GPU-visible shell, not in a sandbox that cannot see `/dev/nvidia*`.

```bash
nvidia-smi

cd /home/yawei/HUGSIM

env PATH=/usr/local/cuda-12.1/bin:/home/yawei/.pixi/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CUDA_HOME=/usr/local/cuda-12.1 \
  TORCH_CUDA_ARCH_LIST=8.9 \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0)); print(torch.cuda.get_device_capability(0)); x=torch.ones(1, device='cuda'); print(x.item())"

env PATH=/usr/local/cuda-12.1/bin:/home/yawei/.pixi/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CUDA_HOME=/usr/local/cuda-12.1 \
  TORCH_CUDA_ARCH_LIST=8.9 \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python -c "import gsplat, tinycudann, pytorch3d, hugsim_env; print('imports_ok')"
```

If this fails, stop and record the exact error. Do not continue to data/runtime.

### Step 2 — Prepare Working Directories

```bash
mkdir -p /home/yawei/hugsim_assets
mkdir -p /home/yawei/hugsim_outputs
mkdir -p /home/yawei/hugsim_sample_data
```

Check space:

```bash
df -h /home/yawei /data
```

### Step 3 — Locate or Download Minimal Public Assets

First inspect whether sample data or released assets already exist locally:

```bash
find /home/yawei -maxdepth 6 -type f \( -name 'cfg.yaml' -o -name 'scene.pth' -o -name 'ground_param.pkl' \) 2>/dev/null
```

If none exist, download the smallest useful public data first.

Priority:

1. `hyzhou404/HUGSIM` sample_data.
2. Only if sample_data is insufficient, download the minimal public scene/scenario assets needed for `scene-0383` or another matching public scenario from `XDimLab/HUGSIM`.

Do not download the full released asset tree unless necessary.

After downloading, confirm whether these exist for the selected scene:

```text
cfg.yaml
scene.pth
ground_param.pkl
```

### Step 4 — Run Audit Preflight

From the audit repo:

```bash
cd /home/yawei/logsim-credibility-audit
python scripts/check_hugsim_smoke_prereqs.py \
  --hugsim-root /home/yawei/HUGSIM \
  --scenario configs/benchmark/nuscenes/scene-0383-easy-00.yaml \
  --base configs/sim/nuscenes_base.yaml \
  --camera configs/sim/nuscenes_camera.yaml \
  --kinematic configs/sim/kinematic.yaml
```

If assets are downloaded:

```bash
python scripts/check_hugsim_smoke_prereqs.py \
  --hugsim-root /home/yawei/HUGSIM \
  --assets-root /home/yawei/hugsim_assets \
  --find-scene
```

### Step 5 — Create Local Smoke-Test Config

Create a local HUGSIM base config if needed. Prefer not to edit the original tracked config directly unless necessary.

Goal: replace original author paths such as `/nas/users/hyzhou/...` with local paths under:

```text
/home/yawei/hugsim_assets
/home/yawei/hugsim_outputs
/home/yawei/hugsim_sample_data
```

Name suggestion:

```text
/home/yawei/HUGSIM/configs/sim/nuscenes_base_local.yaml
```

Record every config change in the run report.

### Step 6 — Attempt HUGSIM Runtime

The first runtime target is not full benchmark reproduction. It is to reach:

```text
env.reset
→ obs_pipe created
→ plan_pipe created
```

Use the debug path if possible. If HUGSIM blocks waiting for `plan_pipe`, use the deterministic plan writer in a second shell.

### Step 7 — Run Deterministic Plan-Pipe Writer if Needed

From the audit repo, after HUGSIM creates FIFO pipes:

```bash
cd /home/yawei/logsim-credibility-audit
python scripts/hugsim_plan_pipe_writer.py \
  --output /home/yawei/hugsim_outputs/<actual-output-dir> \
  --horizon 6 \
  --step-m 1.0 \
  --max-steps 50
```

This writer is not an AD model. It is only used to drive the simulator loop.

### Step 8 — Collect Outputs

Collect paths to any generated files:

```text
data.pkl
video.mp4
infos.pkl
eval.json
ground.ply
scene.ply
output.txt
terminal logs
```

If any file is missing, record why.

### Step 9 — Write Next Run Report

Create:

```text
docs/runs/hugsim_smoke_test_002.md
```

Required sections:

```text
# HUGSIM Smoke Test 002

## Status Summary
- closed-loop segment produced: yes/no
- env.reset reached: yes/no
- obs_pipe reached: yes/no
- plan_pipe reached: yes/no
- env.step reached: yes/no
- HUGSIM output files generated: yes/no
- preliminary evidence status: accepted / down-weighted / rejected / not enough evidence

## Machine

## Environment Verification

## Data / Assets

## Config Changes

## Commands Run

## Runtime Result

## Output Files

## Evidence Completeness

## Preliminary Evidence Judgment

## Remaining Blockers
```

For `Preliminary Evidence Judgment`, use:

```text
docs/hugsim_credibility_decision_rules.md
```

Do not overclaim. If no closed-loop segment is produced, the status remains:

```text
not enough evidence
```

## Success Criteria

Minimum success for this task:

```text
env.reset reached: yes
obs_pipe reached: yes
plan_pipe reached: yes
env.step reached: yes
```

Better success:

```text
video.mp4 generated
data.pkl generated
infos.pkl generated
eval.json generated
ground.ply / scene.ply generated
```

Research success:

```text
one closed-loop segment has enough evidence to be judged accepted, down-weighted, or rejected
```

## Final Reminder

This task is about producing the first HUGSIM closed-loop evidence segment.

Do not turn this into a benchmark reproduction or an AD-agent evaluation task.
