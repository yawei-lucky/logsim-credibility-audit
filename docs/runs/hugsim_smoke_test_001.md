# HUGSIM Smoke Test 001

Date: 2026-07-09

## Machine

- OS: Linux stf-precision-3680 6.8.0-124-generic, Ubuntu 22.04 kernel line
- GPU: NVIDIA PCI device present at `01:00.0` (`10de:2685`), but `nvidia-smi` failed to communicate with the NVIDIA driver
- CUDA: `/usr/bin/nvcc` reports CUDA compilation tools 11.5, V11.5.119; PyTorch in the HUGSIM pixi env is 2.4.1+cu118 and reports CUDA 11.8
- Python: system/default `python` is Python 3.13.12 at `/home/yawei/miniforge3/bin/python`; HUGSIM pixi env uses Python 3.11
- Disk: `/` has 331G available of 1.9T; `/data` has 11G available of 1.9T and is 100% used
- Memory: 125Gi total, 111Gi available at inspection time
- pixi: `/home/yawei/.pixi/bin/pixi`

Post-run user shell update:

- At 2026-07-09 11:25:59, the user's interactive shell reported a healthy `nvidia-smi` result:
  - NVIDIA-SMI 580.95.05
  - Driver Version 580.95.05
  - CUDA Version 13.0
  - GPU: NVIDIA GeForce RTX 4090 D
  - GPU memory: 1399MiB / 24564MiB in use
- The Codex tool execution environment still reported `nvidia-smi` failure after this update, and the HUGSIM pixi Python still reported `torch.cuda.is_available() == False`. This suggests a runtime visibility difference between the user's interactive shell and the tool execution environment, or that the repaired driver state was not visible inside this process context.

Environment command outputs:

```text
$ uname -a
Linux stf-precision-3680 6.8.0-124-generic #124~22.04.1-Ubuntu SMP PREEMPT_DYNAMIC Tue May 26 21:05:19 UTC  x86_64 x86_64 x86_64 GNU/Linux

$ nvidia-smi
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver. Make sure that the latest NVIDIA driver is installed and running.

$ nvcc --version || true
nvcc: NVIDIA (R) Cuda compiler driver
Cuda compilation tools, release 11.5, V11.5.119

$ python --version
Python 3.13.12

$ which python
/home/yawei/miniforge3/bin/python

$ df -h
/dev/nvme1n1p2  1.9T  1.5T  331G  82% /
/dev/nvme0n1p2  1.9T  1.8T   11G 100% /data

$ free -h
Mem: 125Gi total, 12Gi used, 84Gi free, 111Gi available
Swap: 15Gi total, 0B used

$ which git
/usr/bin/git

$ which pixi || true
/home/yawei/.pixi/bin/pixi
```

Additional GPU diagnostics:

```text
$ lspci -nn | rg -i 'nvidia|vga|3d|display'
00:02.0 Display controller [0380]: Intel Corporation Device [8086:a780] (rev 04)
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2685] (rev a1)
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22ba] (rev a1)

$ /home/yawei/HUGSIM/.pixi/envs/default/bin/python -c "import torch; ..."
torch 2.4.1+cu118
torch_cuda 11.8
cuda_available False
device_count 0
```

## Repositories

- HUGSIM path: `/home/yawei/HUGSIM`
- HUGSIM commit: `62c690d39fd90020e68a196bd8bcc1c4d4191f2e`
- HUGSIM working tree notes: `pixi.toml`, `pixi.lock`, and `pixi.toml.smoke-backup` were already present as local changes before/while installing; `pixi install` updated `pixi.lock`
- logsim-credibility-audit path: `/home/yawei/logsim-credibility-audit`
- logsim-credibility-audit commit: `42f400b18e0435ea3ea0a21d06783ee0437acae0`
- logsim-credibility-audit working tree notes: `docs/runs/` contains this new run report

## Commands Run

```bash
uname -a
nvidia-smi
nvcc --version || true
python --version
which python
df -h
free -h
which git
which pixi || true
find /home/yawei -maxdepth 2 -type d -name 'logsim-credibility-audit' -o -name 'HUGSIM'
sed -n '1,240p' docs/hugsim_audit.md
sed -n '1,260p' docs/hugsim_smoke_test_plan.md
sed -n '1,260p' docs/hugsim_credibility_decision_rules.md
sed -n '1,260p' scripts/check_hugsim_smoke_prereqs.py
sed -n '1,260p' scripts/hugsim_plan_pipe_writer.py
sed -n '1,260p' README.md
sed -n '1,260p' closed_loop.py
sed -n '1,560p' sim/hugsim_env/envs/hug_sim.py
sed -n '1,260p' sim/utils/plan.py
sed -n '1,260p' sim/utils/sim_utils.py
sed -n '1,260p' sim/utils/score_calculator.py
sed -n '1,220p' configs/sim/nuscenes_base.yaml
sed -n '1,220p' configs/sim/nuscenes_camera.yaml
sed -n '1,220p' configs/sim/kinematic.yaml
sed -n '1,220p' configs/benchmark/nuscenes/scene-0383-easy-00.yaml
git rev-parse HEAD
git status --short
git diff -- pixi.toml
find /home/yawei -maxdepth 5 -type f -name 'cfg.yaml' -o -type f -name 'scene.pth' -o -type f -name 'ground_param.pkl'
python scripts/check_hugsim_smoke_prereqs.py --hugsim-root /home/yawei/HUGSIM --scenario configs/benchmark/nuscenes/scene-0383-easy-00.yaml --base configs/sim/nuscenes_base.yaml --camera configs/sim/nuscenes_camera.yaml --kinematic configs/sim/kinematic.yaml
pixi install
pixi install
env TORCH_CUDA_ARCH_LIST=8.9 pixi install
/home/yawei/HUGSIM/.pixi/envs/default/bin/python -c "import torch; print(...)"
lspci -nn | rg -i 'nvidia|vga|3d|display'
env TORCH_CUDA_ARCH_LIST=8.9 ninja -v -j 1
```

## Data / Assets

- downloaded data: none
- reason sample_data was not downloaded: the HUGSIM environment did not finish installing, CUDA runtime was unavailable, and no matching local exported scene assets were found; downloading sample data would not have enabled closed-loop execution in this machine state
- selected scene: intended first scenario was `scene-0383`
- selected scenario: `HUGSIM/configs/benchmark/nuscenes/scene-0383-easy-00.yaml`
- asset paths: none found locally for `scene-0383` exported scene files

Local asset scan:

```text
$ find /home/yawei -maxdepth 5 -type f -name 'cfg.yaml' -o -type f -name 'scene.pth' -o -type f -name 'ground_param.pkl'
<no matches>
```

## Configuration Changes

- `HUGSIM/pixi.toml` was in the README step-1 state with source-code dependencies commented.
- For README step 2, the source-code dependency block in `HUGSIM/pixi.toml` was uncommented.
- No HUGSIM base YAML paths were changed because runtime could not proceed to asset-backed execution.
- No `closed_loop.py` debug-path patch was made because installation/GPU blockers occurred before launch.

## Runtime Result

- result: failed before HUGSIM runtime launch
- reached env.reset? no
- reached obs_pipe? no
- reached plan_pipe? no
- reached env.step? no
- generated eval.json? no

Preflight result:

```text
ready_for_manual_runtime_attempt: true
scenario_summary:
  scene_name: scene-0383
  mode: easy_00
  load_HD_map: false
  contains_plan_list: true
  contains_attack_planner: false
  contains_constant_planner: false
recommended_next_step: inspect config paths and run HUGSIM debug path or deterministic plan-pipe test
```

Note: preflight only confirms repository/config presence. It does not validate installed CUDA extensions, GPU driver health, or scene asset availability.

## Output Files

Generated HUGSIM runtime files: none.

Expected files not generated:

```text
data.pkl
video.mp4
infos.pkl
eval.json
ground.ply
scene.ply
output.txt
```

Generated audit file:

```text
/home/yawei/logsim-credibility-audit/docs/runs/hugsim_smoke_test_001.md
```

## Errors

Initial second-stage `pixi install` failed on GitHub/network access in sandbox:

```text
Failed to download and build `tinycudann @ git+https://github.com/NVlabs/tiny-cuda-nn@master#subdirectory=bindings/torch`
fatal: unable to access 'https://github.com/NVlabs/tiny-cuda-nn/':
Couldn't connect to server
```

After running with network escalation, dependency resolution proceeded but `gsplat` failed to build:

```text
Failed to build `gsplat @ git+https://github.com/hyzhou404/HUGSIM_splat.git?rev=main#88f2a40c4e2f6bafde2beeaba6c43bbb0ccb1f5f`
UserWarning: The detected CUDA version (11.5) has a minor version mismatch with the version that was used to compile PyTorch (11.8).
UserWarning: TORCH_CUDA_ARCH_LIST is not set, all archs for visible cards are included for compilation.
UserWarning: Can't initialize NVML
IndexError: list index out of range
```

Interpretation: because the NVIDIA driver/NVML was unavailable, PyTorch could not see any GPU and could not infer a CUDA architecture list.

After the user reported a healthy interactive-shell `nvidia-smi`, the Codex tool environment was checked again and still showed:

```text
$ nvidia-smi
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.

$ /home/yawei/HUGSIM/.pixi/envs/default/bin/python -c "import torch; ..."
torch 2.4.1+cu118
torch_cuda 11.8
cuda_available False
device_count 0
```

With explicit `TORCH_CUDA_ARCH_LIST=8.9`, the empty-architecture error was bypassed, but local CUDA 11.5 `nvcc` does not support Ada architecture 8.9:

```text
$ env TORCH_CUDA_ARCH_LIST=8.9 ninja -v -j 1
nvcc fatal   : Unsupported gpu architecture 'compute_89'
ninja: build stopped: subcommand failed.
```

## Preliminary Evidence Status

not enough evidence

Reason: no closed-loop segment was produced. The run did not reach `env.reset`, did not create FIFO pipes, did not consume a deterministic plan trajectory, and did not generate simulator outputs. Under `docs/hugsim_credibility_decision_rules.md`, no segment-level evidence can be accepted, down-weighted, or rejected because the necessary simulator-side evidence is absent.

## Remaining Blockers

- NVIDIA driver/NVML is functioning in the user's interactive shell as of 2026-07-09 11:25:59, but not inside the Codex tool execution environment used for this run; PyTorch in the HUGSIM pixi env still reports `cuda_available False` and `device_count 0` there.
- CUDA toolkit mismatch: local `nvcc` is 11.5 while the pixi-installed PyTorch wheel is cu118; CUDA 11.5 cannot compile `compute_89`.
- HUGSIM source dependency `gsplat` did not build.
- No local exported `scene-0383` assets were found (`cfg.yaml`, `scene.pth`, `ground_param.pkl` absent).
- HUGSIM base config paths still point to the original author's `/nas/users/hyzhou/...` paths and need local asset paths after assets are available.
- Deterministic plan-pipe writer was not exercised because `closed_loop.py` could not be launched.

Suggested next engineering steps:

1. Fix NVIDIA driver/runtime first, until `nvidia-smi` works and PyTorch reports at least one CUDA device.
2. Install a CUDA toolkit compatible with the target GPU and PyTorch cu118 build, or use a PyTorch/CUDA combination whose `nvcc` supports the local GPU architecture.
3. Re-run `pixi install` with source dependencies enabled.
4. Download only the minimal public HUGSIM sample data or required public `scene-0383` release assets after the environment can run.
5. Update `configs/sim/nuscenes_base.yaml` paths locally or create a smoke-test-specific local config.
6. Launch the debug path and run `scripts/hugsim_plan_pipe_writer.py` only after the environment and scene assets are present.
