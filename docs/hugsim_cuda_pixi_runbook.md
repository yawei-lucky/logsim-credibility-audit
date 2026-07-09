# HUGSIM CUDA / Pixi Troubleshooting Runbook

Purpose: record the repeatable fix for HUGSIM install failures caused by GPU visibility and CUDA/PyTorch version mismatch.

## Symptom Pattern

Common failure signals:

```text
nvidia-smi failed in Codex/default shell
torch.cuda.is_available() == False
UserWarning: Can't initialize NVML
IndexError: list index out of range in torch.utils.cpp_extension._get_cuda_arch_flags
nvcc fatal: Unsupported gpu architecture 'compute_89'
RuntimeError: The detected CUDA version (...) mismatches the version that was used to compile PyTorch (...)
```

Do not immediately conclude the physical GPU or driver is broken. First separate:

- host GPU health;
- Codex/default sandbox GPU visibility;
- CUDA toolkit selected by `nvcc`;
- CUDA version used to build the PyTorch wheel.

## Diagnostic Order

Run normal shell checks:

```bash
nvidia-smi
ls -l /dev/nvidia* 2>/dev/null
cat /proc/driver/nvidia/version 2>/dev/null
which nvcc || true
nvcc --version || true
ls -ld /usr/local/cuda* 2>/dev/null
find /usr/local -maxdepth 3 -type f -name nvcc 2>/dev/null
```

Run PyTorch checks inside the HUGSIM pixi environment:

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.device_count()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'); print(torch.cuda.get_device_capability(0) if torch.cuda.is_available() else 'none')"
```

If the default Codex shell cannot see `/dev/nvidia*`, rerun GPU-dependent diagnostics or build commands outside the sandbox with approval. In this case, the host GPU was healthy but the default shell could not access GPU devices.

## Rule Of Thumb

For source-built CUDA extensions, align these three values:

- PyTorch wheel CUDA version: `torch.version.cuda`
- Selected toolkit: `CUDA_HOME` and first `nvcc` on `PATH`
- Target GPU architecture: `TORCH_CUDA_ARCH_LIST`

On this machine:

```text
GPU: NVIDIA GeForce RTX 4090 D
compute capability: 8.9
working driver: 580.95.05
working toolkit: /usr/local/cuda-12.1
bad default nvcc: /usr/bin/nvcc, CUDA 11.5
```

CUDA 11.5 cannot compile `compute_89`. PyTorch cu118 also mismatches CUDA 12.1 during extension builds.

## Working Fix Used Here

Change HUGSIM's `pixi.toml` PyTorch wheels from cu118 to cu121:

```toml
torch = { version = "==2.4.1", index = "https://download.pytorch.org/whl/cu121" }
torchvision = { version = "==0.19.1", index = "https://download.pytorch.org/whl/cu121"}
```

Install with CUDA 12.1 explicitly selected:

```bash
cd /home/yawei/HUGSIM
env PATH=/usr/local/cuda-12.1/bin:/home/yawei/.pixi/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CUDA_HOME=/usr/local/cuda-12.1 \
  TORCH_CUDA_ARCH_LIST=8.9 \
  pixi install
```

Verify:

```bash
env PATH=/usr/local/cuda-12.1/bin:/home/yawei/.pixi/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CUDA_HOME=/usr/local/cuda-12.1 \
  TORCH_CUDA_ARCH_LIST=8.9 \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0)); print(torch.cuda.get_device_capability(0)); x=torch.ones(1, device='cuda'); print(x.item())"
```

Expected successful output:

```text
torch 2.4.1+cu121
torch_cuda 12.1
cuda_available True
name NVIDIA GeForce RTX 4090 D
capability (8, 9)
cuda_tensor 1.0
```

Also verify HUGSIM source dependencies:

```bash
env PATH=/usr/local/cuda-12.1/bin:/home/yawei/.pixi/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CUDA_HOME=/usr/local/cuda-12.1 \
  TORCH_CUDA_ARCH_LIST=8.9 \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python -c "import gsplat, tinycudann, pytorch3d, hugsim_env; print('imports_ok')"
```

## Automatic Handling Checklist

When a future HUGSIM install or CUDA extension build fails:

1. Check whether the default shell can see GPU devices.
2. If not, rerun GPU checks/builds in the approved non-sandbox environment before diagnosing hardware failure.
3. Compare `torch.version.cuda` with the `nvcc --version` selected by `PATH` and `CUDA_HOME`.
4. For RTX 4090 D / compute 8.9, avoid CUDA 11.5 for extension builds.
5. Prefer matching the PyTorch wheel to an installed toolkit over changing system CUDA.
6. Set `CUDA_HOME`, put the matching toolkit's `bin` first on `PATH`, and set `TORCH_CUDA_ARCH_LIST=8.9`.
7. Only after the environment imports succeed should HUGSIM runtime/data smoke testing continue.
