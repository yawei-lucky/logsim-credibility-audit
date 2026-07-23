# HUGSIM × SparseDrive Stage2 runtime smoke 001

## Outcome

SparseDrive-S Stage2 is now locally runnable on HUGSIM six-camera RGB. The
official checkpoint loaded with `strict=True`, four temporal frames completed,
all declared native tensors were finite, and an explicit reset reproduced the
first-frame outputs within a `1e-4` absolute GPU numerical tolerance.

This closes the narrow runtime gate. It does **not** yet qualify the planning
trajectory as a credibility indicator.

## Frozen receiver

- official SparseDrive source commit:
  `ec0225d4b7a2dd7e6ce10179a2b7660dcb74b2f1`;
- official Stage2 checkpoint SHA-256:
  `a9786bd3398907666ef436b287b465d6de8c424467413648e4614e0b884db7ad`;
- checkpoint size: `1,033,678,905` bytes;
- config SHA-256:
  `812414bb981eadca1365654575eeb799c91252de756a1d5b573e0a284cc88f11`;
- model parameters: `86,142,365`;
- runtime: PyTorch `2.0.1+cu118`, RTX 4090 D;
- input: HUGSIM RGB and camera calibration only; HUGSIM semantic and depth are
  excluded.

The compatibility patch is tracked at
`third_party_patches/sparsedrive_pytorch_fallback.patch`. It:

1. uses the model's existing PyTorch feature-sampling path instead of the
   optional custom deformable CUDA operator;
2. substitutes checkpoint-compatible PyTorch multi-head attention when
   `flash_attn` is unavailable;
3. lets the motion/planning queue consume the unflattened feature maps used by
   that fallback.

The unchanged official checkpoint loads strictly under this path. The patch
removes an installation blocker, but it may introduce small numerical
differences from the authors' accelerated runtime and does not reproduce their
nuScenes benchmark by itself.

## Smoke sequence

- HUGSIM input:
  `artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s`;
- condition: no injected actor;
- selected simulator frames: `0, 2, 4, 6`;
- timestamps: `0.0, 0.5, 1.0, 1.5 s`;
- camera order:
  `FRONT, FRONT_RIGHT, FRONT_LEFT, BACK, BACK_LEFT, BACK_RIGHT`;
- output:
  `artifacts/sparsedrive_receiver/scene-0383-runtime-smoke-run006`.
- visual:
  `artifacts/sparsedrive_receiver/scene-0383-runtime-smoke-run006/no_actor_runtime_smoke.png`.

Per frame, SparseDrive emitted:

| Native output | Shape |
|---|---:|
| 3D boxes | `300 x 10` |
| agent trajectories | `300 x 6 x 12 x 2` |
| agent trajectory scores | `300 x 6` |
| planning scores | `3 x 6` |
| candidate ego plans | `3 x 6 x 6 x 2` |
| final ego plan | `6 x 2` |

The first frame took about `0.322 s`; warmed frames took about `0.11 s`.
Reset maximum absolute differences were:

- detection score: `1.14e-6`;
- planning score: `1.19e-7`;
- final plan: `1.91e-5`.

Reproduce the bounded run after applying the tracked patch to the pinned
SparseDrive checkout and installing `prettytable==3.7.0` plus `einops==0.6.1`
into the declared `--runtime-deps` directory:

```bash
PYTHONPATH=artifacts/sparsedrive_receiver/runtime-deps-v1 \
MPLCONFIGDIR=/tmp/mpl-sparsedrive \
/home/yawei/miniforge3/envs/sparse4d-audit/bin/python \
  scripts/run_sparsedrive_hugsim_receiver.py \
  --sparsedrive-root /home/yawei/SparseDrive \
  --checkpoint artifacts/sparsedrive_receiver/official-v1.0/sparsedrive_stage2.pth \
  --runtime-deps artifacts/sparsedrive_receiver/runtime-deps-v1 \
  --anchor-dir artifacts/sparsedrive_receiver/official-v1.0/anchors \
  --run no_actor=artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s \
  --output artifacts/sparsedrive_receiver/scene-0383-runtime-smoke-rerun001 \
  --frame-stride 2 \
  --max-frames 4
```

## Input-contract boundary

The runtime adapter currently declares a virtual LiDAR frame coincident with
the HUGSIM vehicle frame used by the existing Sparse4D adapter. The 10-D
`ego_status` maps available longitudinal acceleration and speed, derives yaw
rate from consecutive headings, carries steering angle, and sets unavailable
components to zero. HUGSIM's `0/1/2` right/left/straight command is converted
to the matching one-hot order.

These choices are explicit and reproducible, but still provisional. They need
an independent coordinate/calibration check and an ego-status sensitivity
audit before planning direction is interpreted.

The cold first frame planned much farther than the three history-conditioned
frames even in this no-actor run. That is evidence that temporal warm-up
materially affects the native plan. Future paired experiments must compare the
same time indices with independently reset conditions and must not compare a
cold frame against a warmed frame.

## Evidence decisions

| Claim or finding | Decision | Boundary |
|---|---|---|
| The pinned official SparseDrive checkpoint can run on bounded HUGSIM RGB and expose native planning/motion outputs | `accepted` | engineering/runtime claim only |
| Temporal state reset is reproducible | `accepted` | tested first-frame outputs within `1e-4` absolute tolerance |
| The current virtual-frame and 10-D ego-status mapping is qualified for planning interpretation | `down-weighted` | explicit and internally coherent, but not externally anchored |
| Current SparseDrive output shows that HUGSIM planning behavior is credible | `rejected` | not tested; runtime success and finite tensors are not task-validity evidence |

## Next gate

Before any slow/nominal/fast planning claim:

1. freeze and independently check the virtual LiDAR/ego axes, origin and
   projection mapping;
2. audit whether plausible alternatives for the unavailable ego-status
   components change the plan conclusion;
3. compare only equally warmed, independently reset paired sequences;
4. preregister the expected planning direction and unavailable-output rule.

After that, run one bounded paired counterfactual. Do not add another receiver
or infer safety from this smoke result.
