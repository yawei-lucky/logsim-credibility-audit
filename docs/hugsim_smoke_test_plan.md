# HUGSIM Smoke Test Plan

> Goal: define the smallest runnable path for testing the credibility-audit workflow on HUGSIM.

This plan is not a full reproduction of the HUGSIM benchmark. It is a minimal workflow to verify that we can collect closed-loop evidence and attach credibility annotations.

## Current Decision

The Phase 1 smoke test should use the smallest public artifacts first:

```text
1. Use HUGSIM sample_data for installation / artifact sanity checks.
2. Use XDimLab/HUGSIM released assets only when closed-loop scene assets are required.
3. Use an existing simple benchmark YAML such as `configs/benchmark/nuscenes/scene-0383-easy-00.yaml` or another public released scenario that matches downloaded assets.
4. Avoid heavy AD clients first; prefer deterministic plan-pipe writer or debug path.
```

Rationale:

- `hyzhou404/HUGSIM` sample_data is publicly listed at about 2.38 GB.
- `XDimLab/HUGSIM` released assets are publicly listed at about 60.7 GB.
- HUGSIM README says some competition scenarios are private, so the smoke test must rely only on public assets.

## Stage 0 — Source and Artifact Check

Current status: **partial pass**.

Confirmed public sources:

- Official repository: https://github.com/hyzhou404/HUGSIM
- Official project page: https://xdimlab.github.io/HUGSIM/
- Paper: https://arxiv.org/abs/2412.01718
- Sample data: https://huggingface.co/datasets/hyzhou404/HUGSIM/tree/main/sample_data
- Released vehicles / scenes / scenarios: https://huggingface.co/datasets/XDimLab/HUGSIM

Known constraints:

- Some RealADSim competition scenarios are private.
- Full dataset conversion requires external dataset access and licenses.
- AD clients are separate dependencies.
- Runtime has not been tested locally yet.
- The released asset tree may be large; do not download full assets unless needed.

Expected output:

```text
source_availability_status: partial pass
public_assets_selected: sample_data first; released scene/scenario second
blocking_artifacts: private competition scenarios, external dataset licenses, AD-client dependencies
```

## Stage 1 — Environment Inspection

Do not start with a full benchmark run.

First inspect:

- `pixi.toml`
- `requirements.txt`
- CUDA / PyTorch assumptions
- `closed_loop.py`
- `configs/sim/*_base.yaml`
- `configs/sim/*_camera.yaml`
- `configs/sim/kinematic.yaml`
- `configs/benchmark/*`

Confirmed from README:

- HUGSIM uses `pixi`.
- Some packages are installed from source and rely on PyTorch/CUDA compilation.
- `apex` is required by InverseForm.
- Paths in `configs/sim/*_base.yaml` must be updated for the local machine.

Repository helper:

```bash
python scripts/check_hugsim_smoke_prereqs.py \
  --hugsim-root /path/to/HUGSIM \
  --scenario configs/benchmark/nuscenes/scene-0383-easy-00.yaml \
  --base configs/sim/nuscenes_base.yaml \
  --camera configs/sim/nuscenes_camera.yaml \
  --kinematic configs/sim/kinematic.yaml
```

If released assets have been downloaded:

```bash
python scripts/check_hugsim_smoke_prereqs.py \
  --hugsim-root /path/to/HUGSIM \
  --assets-root /path/to/XDimLab_HUGSIM_assets \
  --find-scene
```

Expected output:

```text
environment_status: installed and verified in GPU-visible non-sandbox environment
required_gpu_count: one simulator GPU for deterministic smoke test
selected_runtime: PyTorch 2.4.1+cu121, CUDA toolkit 12.1, compute capability 8.9
required_ad_clients: avoid first if using deterministic plan-pipe writer
```

Current machine result:

- HUGSIM clone exists at `/home/yawei/HUGSIM`.
- Pixi installation completed successfully.
- CUDA tensor allocation and imports for `gsplat`, `tinycudann`, `pytorch3d`, and `hugsim_env` succeeded in a GPU-visible non-sandbox execution context.
- The default Codex sandbox does not expose the GPU and must not be used to judge CUDA runtime health.

## Stage 2 — Minimal Runtime Path

Preferred first path:

```text
public sample/released asset
+ existing benchmark YAML
+ debug or no-heavy-AD path
+ deterministic plan-pipe writer
```

Avoid at first:

- training reconstruction from scratch;
- running all scenarios;
- evaluating multiple AD agents;
- editing new scenarios manually;
- reproducing all paper numbers.

Expected output:

```text
selected_scene: scene-0383 or another public released scene matching available assets
selected_scenario: easiest matching public scenario first, e.g. scene-0383-easy-00.yaml if assets exist
selected_ad_client: deterministic waypoint / plan-pipe writer
runtime_entrypoint: closed_loop.py
```

## Stage 3 — Debug / Lightweight Agent Strategy

The audit workflow should not depend on a heavy AD model at the beginning.

Confirmed implementation facts:

- `closed_loop.py` writes `(obs, info)` to `obs_pipe`.
- It reads `plan_traj` from `plan_pipe`.
- It converts `plan_traj` to acceleration and steer-rate using `traj2control`.
- It calls `env.step(action)`.
- README provides a debug note to bypass AD process launch and call `create_gym_env(cfg, output)` directly.

Resolved risk:

- Upstream `create_gym_env()` still waits for `plan_pipe` and has no bounded debug-step option.
- `scripts/run_hugsim_debug_smoke.py` now preserves the FIFO boundary while adding a bounded step count, local released-scene path override, and audit-oriented outputs.

Repository helper:

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/hugsim_plan_pipe_writer.py \
  --output /path/to/hugsim/output/scene-mode \
  --horizon 6 \
  --step-m 1.0 \
  --max-steps 50
```

Run this helper in a second shell after `closed_loop.py` creates `obs_pipe` and `plan_pipe` under the output directory.

Expected output:

```text
agent_strategy: deterministic_waypoint_client preferred if debug path blocks
agent_dependency_status: no UniAD/VAD/LTF required for first smoke-loop test, if plan-pipe writer works
```

## Stage 4 — Audit Logging Requirements

For each step, record:

- scenario id;
- frame / step id;
- ego pose before update;
- actor poses before update;
- rendered observation metadata;
- AD command or waypoint;
- acceleration and steer-rate action;
- ego pose after update;
- actor poses after update;
- metric events;
- collision status;
- route completion;
- rendering notes;
- relation-consistency notes;
- audit decision: accepted / down-weighted / rejected.

Suggested first audit-log object:

```json
{
  "scenario_id": "TODO",
  "step_id": 0,
  "source_assets": {
    "scene": "TODO",
    "scenario_yaml": "TODO",
    "vehicle_assets": "TODO"
  },
  "sim_state": {
    "ego_before": "TODO",
    "actors_before": "TODO",
    "ego_after": "TODO",
    "actors_after": "TODO"
  },
  "agent_io": {
    "observation_modalities": ["rgb", "semantic", "depth"],
    "plan_traj": "TODO",
    "action": "TODO"
  },
  "metrics": {
    "collision": "TODO",
    "route_completion": "TODO",
    "nc": "TODO",
    "dac": "TODO",
    "ttc": "TODO"
  },
  "credibility": {
    "decision": "accepted | down-weighted | rejected",
    "reason": "TODO"
  }
}
```

## Stage 5 — Credibility Checklist

For each generated closed-loop segment, check:

- Are lane and drivable-area relations stable?
- Are front / rear / left / right relations stable?
- Are actor scale and orientation consistent across views?
- Are occlusion relations stable?
- Are extrapolated views showing obvious artifacts?
- Are actor trajectories plausible within the scenario context?
- Are metric events supported by scene geometry and temporal evidence?

## Stage 6 — Minimal Success Criteria

A smoke test is successful if it produces one documented closed-loop sequence with:

- public source assets;
- reproducible command path;
- logged simulator states;
- logged rendered observation metadata;
- at least one metric event or normal step transition;
- credibility notes attached to each relevant step.

Expected generated files from `closed_loop.py` path:

- `data.pkl`
- `video.mp4`
- `infos.pkl`
- `eval.json`
- `ground.ply`
- `scene.ply`

### First execution result — 2026-07-17

The minimum success criteria have been met for `scene-0383-easy-00`:

- Three deterministic closed-loop steps completed.
- FIFO observation and plan exchange completed.
- Ego state advanced continuously from timestamp 0.0 to 0.75 seconds.
- Six RGB cameras plus semantic and depth observations were saved.
- `data.pkl`, `video.mp4`, `infos.pkl`, `eval.json`, `ground.ply`, `scene.ply`, `observations.pkl`, and audit-specific records were generated.
- HUGSIM scoring completed with NC, DAC, TTC, comfort, and PDMS equal to 1.0; route completion and HDScore were approximately 0.02148 for this intentionally short run.
- The first credibility decision is `down-weighted`, not `accepted`, because the run is short, has no dynamic actor, contains visible lateral-view blur/smearing, and has not yet undergone pixel-level RGB/semantic/depth consistency validation.

See `docs/runs/hugsim_smoke_test_002.md`.

## Stage 7 — Non-Goals

This smoke test does not attempt to:

- reproduce full HD-Score tables;
- train new 3DGS scenes;
- evaluate all AD agents;
- claim HUGSIM is credible or non-credible globally;
- compare all simulator families.

## Stage 8 — Next Runtime Step

The first runtime gate has been completed. The next gate is evidence-quality validation on top of the working loop.

Current asset decision:

- Download only `scenes/nuscenes/scene-0383.zip` first; the published file is about 628 MB.
- Use `configs/benchmark/nuscenes/scene-0383-easy-00.yaml`.
- The selected scenario has an empty `plan_list`, so the first smoke test does not require the full 3DRealCar release.

Next evidence-quality checklist:

```text
render RGB / semantic / depth comparison sheets
check cross-modal road, depth-edge, semantic-edge, and occlusion consistency
run a longer bounded normal segment
compare state continuity and metric stability
update the first down-weighted record or create a stronger accepted record
```
