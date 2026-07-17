# HUGSIM Smoke Test 002 — First Successful Closed Loop

Date: 2026-07-17

## Outcome

The Phase 1 minimum runtime milestone succeeded.

HUGSIM completed three deterministic closed-loop steps on the public nuScenes `scene-0383` release without launching UniAD, VAD, or LTF. The run exercised:

```text
six-camera RGB / semantic / depth observation
→ obs_pipe
→ deterministic local trajectory
→ plan_pipe
→ traj2control
→ ego kinematic update
→ next rendered observation
→ HUGSIM metric evaluation
```

The first segment-level credibility decision is:

```text
down-weighted
```

The run is valid evidence that the minimum loop and audit logging work. It is not yet strong evidence for HUGSIM's credibility in dynamic or safety-critical counterfactual scenarios.

## Source Identity

- HUGSIM repository: `/home/yawei/HUGSIM`
- HUGSIM commit: `adeca402cad4af8635e13d0a105e2fee6a14de85`
- Public dataset: `XDimLab/HUGSIM`
- Scene archive: `scenes/nuscenes/scene-0383.zip`
- Published archive size: approximately 628 MB
- Downloaded archive SHA-256: `cbd99a927316f7f795904c59350b7fced4b8f32a14506891720962e3e30e7f15`
- Scenario: `configs/benchmark/nuscenes/scene-0383-easy-00.yaml`
- Scenario SHA-256: `8bb03b7b41f1d1b6a7c7cf0ba49a5f868729339b4621907fc8f9f149679152f8`
- Scenario `plan_list`: empty
- HD map: disabled

Because `plan_list` is empty, this run did not require the full 3DRealCar release.

## Local Runtime Configuration

- Scene root: `/home/yawei/HUGSIM_assets/scenes/nuscenes/scene-0383`
- Local base config: `configs/hugsim/nuscenes_smoke_base.yaml`
- Output: `artifacts/hugsim_smoke/scene-0383-easy-00-run001`
- PyTorch: 2.4.1+cu121
- CUDA toolkit selected for source extensions: `/usr/local/cuda-12.1`
- GPU target: RTX 4090 D, compute capability 8.9

The released scene's `cfg.yaml` contains the original author's absolute `model_path`. The bounded runner explicitly overrides it with the extracted local scene path without modifying the released artifact.

## Commands

GPU-visible runner:

```bash
env \
  PATH=/usr/local/cuda-12.1/bin:/home/yawei/.pixi/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CUDA_HOME=/usr/local/cuda-12.1 \
  TORCH_CUDA_ARCH_LIST=8.9 \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/run_hugsim_debug_smoke.py \
  --max-steps 3 \
  --output artifacts/hugsim_smoke/scene-0383-easy-00-run001
```

Deterministic planner:

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/hugsim_plan_pipe_writer.py \
  --output artifacts/hugsim_smoke/scene-0383-easy-00-run001 \
  --horizon 6 \
  --step-m 1.0 \
  --max-steps 4
```

## Closed-Loop Trace

| Step | Time before → after | Velocity before → after | Steering before → after | Acceleration | Steer rate | Route completion | Collision |
|---|---:|---:|---:|---:|---:|---:|---|
| 0 | 0.00 → 0.25 s | 1.0000 → 1.4739 | 0.0 → -0.1 | 1.8957 | -0.4 | 0.006782 | false |
| 1 | 0.25 → 0.50 s | 1.4739 → 1.8087 | -0.1 → -0.2 | 1.3390 | -0.4 | 0.013564 | false |
| 2 | 0.50 → 0.75 s | 1.8087 → 2.0404 | -0.2 → -0.3 | 0.9268 | -0.4 | 0.021476 | false |

The before/after states are continuous and match the configured 0.25-second kinematic step.

## Observation Evidence

- Four observation timestamps were saved: the initial observation plus three post-step observations.
- Modalities: RGB, semantic, depth.
- Cameras: front, front-left, front-right, back, back-left, back-right.
- Resolution: 450 × 800 per camera.
- All six depth arrays were finite in the initial frame.
- Initial depth ranges were approximately 2.43–164.19 m across the six cameras.
- Semantic outputs were non-empty and contained multiple labels in every camera.
- RGB montage inspection showed a stable forward road/lane layout across the short rollout.
- Visible blur/smearing remains in lateral and boundary regions.

No dynamic actor was present, so actor scale, orientation, occlusion, and interaction credibility were not tested.

## Metric Output

```json
{
  "nc": 1.0,
  "dac": 1.0,
  "ttc": 1.0,
  "c": 1.0,
  "pdms": 1.0,
  "rc": 0.02147620662371425,
  "hdscore": 0.02147620662371425
}
```

These values only describe the three-step deterministic run under HUGSIM's internal state and geometry. The low HDScore reflects the intentionally tiny route completion and is not a benchmark result.

## Generated Files

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

The output directory is deliberately ignored by Git because the observation and point-cloud artifacts are large. The compact audit decision is recorded separately in `docs/runs/hugsim_smoke_test_002_audit.json`.

## Credibility Decision

Decision: `down-weighted`.

Evidence supporting use:

- Public scene and scenario are identified and hashed.
- HUGSIM commit and runtime configuration are recorded.
- Ego state before and after every step is available.
- Planned trajectory and resulting control action are available.
- RGB, semantic, and depth observations are saved.
- Internal ground and scene geometry were exported.
- Metric computation completed without errors.
- No temporal discontinuity or front-view road/lane contradiction was observed in this short run.

Reasons for down-weighting:

- The segment is only 0.75 seconds long.
- The scenario contains no dynamic actor or counterfactual interaction.
- Lateral views contain visible reconstruction blur/smearing.
- Semantic and depth outputs passed numerical sanity checks but have not undergone pixel-level alignment validation against RGB.
- A normal no-collision transition cannot validate collision, near-miss, occlusion, or risk attribution.

## Next Evidence Gate

Before upgrading similar evidence to `accepted`:

1. Render synchronized RGB / semantic / depth comparison sheets.
2. Check road boundaries, semantic edges, depth discontinuities, and occlusion consistency.
3. Run a longer bounded normal segment and inspect state/render stability.
4. Then introduce the smallest public dynamic-actor scenario.
