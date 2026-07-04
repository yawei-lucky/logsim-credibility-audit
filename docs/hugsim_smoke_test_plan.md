# HUGSIM Smoke Test Plan

> Goal: define the smallest runnable path for testing the credibility-audit workflow on HUGSIM.

This plan is not a full reproduction of the HUGSIM benchmark. It is a minimal workflow to verify that we can collect closed-loop evidence and attach credibility annotations.

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

Expected output:

```text
source_availability_status: partial pass
public_assets_selected: TODO_SOURCE
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

Expected output:

```text
environment_status: TODO_RUN
required_gpu_count: at least simulator GPU; AD client may use separate GPU
required_cuda_version: TODO_SOURCE
required_ad_clients: UniAD_SIM / VAD_SIM / NAVSIM-LTF path depending on test mode
```

## Stage 2 — Minimal Runtime Path

Preferred first path:

```text
public released scene + public released scenario + debug simulation path
```

Avoid at first:

- training reconstruction from scratch;
- running all scenarios;
- evaluating multiple AD agents;
- editing new scenarios manually;
- reproducing all paper numbers.

Expected output:

```text
selected_scene: TODO_SOURCE
selected_scenario: TODO_SOURCE
selected_ad_client: debug / dummy / deterministic waypoint client / TODO_SOURCE
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

Open risk:

- `create_gym_env()` still waits for `plan_pipe`, so debug mode may require a minimal writer for `plan_pipe` unless the code is further modified.

Check whether one of the following is possible:

1. Use HUGSIM debug path to create the gym environment only.
2. Use an existing lightweight client.
3. Add a minimal local stand-in client that returns deterministic waypoints.
4. Use a replayed route or fixed command sequence.

Expected output:

```text
agent_strategy: deterministic_waypoint_client preferred if debug path blocks
agent_dependency_status: TODO_RUN
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

## Stage 7 — Non-Goals

This smoke test does not attempt to:

- reproduce full HD-Score tables;
- train new 3DGS scenes;
- evaluate all AD agents;
- claim HUGSIM is credible or non-credible globally;
- compare all simulator families.

## Next Automation Step

Once exact runnable assets are selected, create a small checklist or script that verifies:

```text
repo cloned
pixi environment available
sample assets present
config paths valid
closed_loop.py can enter env creation
output directory created
audit log template created
```

Possible future script:

```text
scripts/check_hugsim_smoke_prereqs.py
```
