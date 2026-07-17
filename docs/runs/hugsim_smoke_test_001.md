# HUGSIM Smoke Test 001

Date: 2026-07-09

## Status Summary

This run did **not** complete a HUGSIM closed-loop smoke test.

It should be read as an **environment and dependency bring-up report**, not as a closed-loop simulation result.

Current result:

```text
closed-loop segment produced: no
env.reset reached: no
obs_pipe reached: no
plan_pipe reached: no
env.step reached: no
HUGSIM output files generated: no
preliminary evidence status: not enough evidence
```

The useful outcome of this run is that the HUGSIM CUDA / pixi environment problem was diagnosed and fixed.

## Purpose of This Run

The purpose was to start Issue #8: running a minimal HUGSIM closed-loop evidence pipeline smoke test.

The intended chain was:

```text
public scene / scenario
→ HUGSIM runtime
→ obs_pipe
→ deterministic plan-pipe writer
→ env.step
→ output files
→ closed-loop evidence judgment
```

The run stopped before HUGSIM runtime launch, so no simulator-side evidence was generated.

## Machine

- OS: Linux `stf-precision-3680`, Ubuntu 22.04 kernel line.
- GPU: NVIDIA GeForce RTX 4090 D, 24GB class.
- Working driver after fix: NVIDIA driver `580.95.05`.
- Working CUDA toolkit for extension builds: `/usr/local/cuda-12.1`.
- Problematic default CUDA toolkit: `/usr/bin/nvcc`, CUDA `11.5`.
- HUGSIM pixi Python: Python 3.11.
- Memory: 125Gi total, 111Gi available at inspection time.
- Storage note: `/data` was full; `/home/yawei` has enough working space and should be used for follow-up assets and outputs.

## Repository State

- HUGSIM path: `/home/yawei/HUGSIM`
- HUGSIM commit: `62c690d39fd90020e68a196bd8bcc1c4d4191f2e`
- Audit repo path: `/home/yawei/logsim-credibility-audit`
- Audit repo commit at first report: `42f400b18e0435ea3ea0a21d06783ee0437acae0`

Local HUGSIM changes during setup:

- `pixi.toml` was edited from PyTorch `cu118` wheels to `cu121` wheels.
- `pixi.lock` was updated by `pixi install`.
- These are local environment changes, not yet treated as upstream HUGSIM changes.

## Environment Problem Found

The first attempt failed because the default execution environment could not use the GPU correctly.

Observed symptoms:

```text
nvidia-smi failed in default Codex/tool shell
torch.cuda.is_available() == False
UserWarning: Can't initialize NVML
IndexError in torch.utils.cpp_extension._get_cuda_arch_flags
nvcc fatal: Unsupported gpu architecture 'compute_89'
```

Root cause was refined to two separate issues:

1. The default Codex/tool execution context could not see the GPU, while the user's normal shell could.
2. HUGSIM CUDA extension builds used an incompatible CUDA/PyTorch combination:
   - local default `nvcc`: CUDA 11.5;
   - original HUGSIM pixi PyTorch wheel: `cu118`;
   - GPU architecture: RTX 4090 D, compute capability 8.9;
   - CUDA 11.5 cannot compile `compute_89`.

## Environment Fix Applied

The working fix was:

```text
PyTorch wheel: cu121
CUDA_HOME: /usr/local/cuda-12.1
PATH first CUDA: /usr/local/cuda-12.1/bin
TORCH_CUDA_ARCH_LIST: 8.9
```

After this fix:

```text
torch 2.4.1+cu121
torch_cuda 12.1
cuda_available True
CUDA tensor allocation succeeded
imports succeeded: gsplat, tinycudann, pytorch3d, hugsim_env
```

The repeatable fix is documented in:

```text
docs/hugsim_cuda_pixi_runbook.md
```

## Data / Assets

No HUGSIM data or closed-loop assets were downloaded during this run.

The intended first scenario was:

```text
HUGSIM/configs/benchmark/nuscenes/scene-0383-easy-00.yaml
scene_name: scene-0383
mode: easy_00
load_HD_map: false
```

Local scan found no exported HUGSIM scene files for the intended scene:

```text
cfg.yaml: not found
scene.pth: not found
ground_param.pkl: not found
```

This means the next actual closed-loop attempt still needs a public HUGSIM asset path, either from sample data or from the released public HUGSIM assets.

## Runtime Result

HUGSIM runtime was not launched.

```text
reached env.reset? no
reached obs_pipe? no
reached plan_pipe? no
reached env.step? no
generated eval.json? no
```

Generated HUGSIM runtime files:

```text
none
```

Expected but not generated:

```text
data.pkl
video.mp4
infos.pkl
eval.json
ground.ply
scene.ply
output.txt
```

## Evidence Status

```text
not enough evidence
```

Reason:

No closed-loop segment was produced. The run did not reach `env.reset`, did not create FIFO pipes, did not consume a deterministic planned trajectory, and did not generate simulator outputs.

Therefore, no segment can yet be judged as:

```text
accepted
down-weighted
rejected
```

The current result is an environment bring-up result, not simulator evidence.

## Remaining Blockers

At the time of this first attempt, the remaining blockers were:

1. Use a GPU-visible shell for all GPU-dependent HUGSIM commands.
2. Keep the HUGSIM pixi environment aligned with CUDA 12.1 / PyTorch cu121 on this machine.
3. Use `/home/yawei` rather than full `/data` for HUGSIM assets and outputs.
4. Download or locate a minimal public HUGSIM scene/scenario asset set.
5. Create or edit a local smoke-test config so paths no longer point to original author paths such as `/nas/users/hyzhou/...`.
6. Launch the HUGSIM debug / closed-loop path only after scene assets are present.
7. Exercise `scripts/hugsim_plan_pipe_writer.py` only after `obs_pipe` and `plan_pipe` are created.

## Interpretation

This run made real progress, but at the environment layer.

It confirms that HUGSIM can now be installed on the local RTX 4090 D machine with the correct CUDA / PyTorch alignment. It does **not** yet confirm that HUGSIM can load a scene, render observations, execute a closed-loop step, or produce credibility-auditable evidence.

## Status Reconciliation — 2026-07-17

This report records the first attempt and preserves its failure diagnostics. Current project state is newer than the failure section:

- HUGSIM is now at upstream commit `adeca402cad4af8635e13d0a105e2fee6a14de85`, whose latest change adopts CUDA 12.1 PyTorch wheels.
- The environment installation is no longer a blocker.
- The scene asset, local path configuration, and first deterministic closed loop were subsequently completed.
- See `docs/runs/hugsim_smoke_test_002.md` for the first successful runtime output and segment-level credibility record.
