# HUGSIM Smoke Test Plan

> Goal: define the smallest runnable path for testing the credibility-audit workflow on HUGSIM.

This plan is not a full reproduction of the HUGSIM benchmark. It is a minimal workflow to verify that we can collect closed-loop evidence and attach credibility annotations.

## Stage 0 — Source and Artifact Check

Required checks:

- Confirm repository clone works: https://github.com/hyzhou404/HUGSIM
- Confirm HUGSIM license.
- Confirm sample data link from README.
- Confirm released 3DRealCar / scene / scenario assets from README.
- Confirm which released scenarios are public and which are competition-private.
- Confirm whether the smoke test can run without training a new scene.

Expected output:

```text
source_availability_status: pass / partial / fail
public_assets_selected: <scene/scenario identifiers>
blocking_artifacts: <list>
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

Expected output:

```text
environment_status: pass / partial / fail
required_gpu_count: TODO_SOURCE
required_cuda_version: TODO_SOURCE
required_ad_clients: TODO_SOURCE
```

## Stage 2 — Minimal Runtime Path

Preferred first path:

```text
released scene + released scenario + debug simulation path
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
selected_ad_client: debug / dummy / uniad / vad / navsim / TODO_SOURCE
runtime_entrypoint: closed_loop.py
```

## Stage 3 — Debug / Lightweight Agent Strategy

The audit workflow should not depend on a heavy AD model at the beginning.

Check whether one of the following is possible:

1. Use HUGSIM debug path to create the gym environment only.
2. Use an existing lightweight client.
3. Add a minimal local stand-in client that returns deterministic waypoints.
4. Use a replayed route or fixed command sequence.

The purpose is to verify the simulator loop and audit logging before measuring any real AD-agent performance.

Expected output:

```text
agent_strategy: debug_env_only / lightweight_client / deterministic_waypoint_client / replay
agent_dependency_status: TODO_SOURCE
```

## Stage 4 — Audit Logging Requirements

For each step, record:

- scenario id;
- frame / step id;
- ego pose before update;
- actor poses before update;
- rendered observation metadata;
- AD command or waypoint;
- ego pose after update;
- actor poses after update;
- metric events;
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
closed_loop.py can enter debug env creation
output directory created
audit log template created
```
