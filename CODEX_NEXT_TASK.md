# Codex Next Task — Establish a Matched Real–Simulation Source Anchor

> Read this file first when resuming HUGSIM work.

## Project Objective

Develop a credibility-validation method for log-driven simulators.

This project uses the broad definition:

> A log-driven simulator constructs an interactive environment from real
> road-driving capture sequences and generates counterfactual closed-loop
> evolution. Exact log replay is not required.

HUGSIM is the first case study, not the final research target. It is a
real-driving-sequence reconstruction-based, counterfactual closed-loop neural
simulator.

Durable guiding questions:

> HUGSIM 提供给智驾系统的任务相关信息，是否与现实一致到足以产生可信的感知、决策和闭环结果？

> 同一个智驾模型面对现实数据和对应的仿真数据，是否形成相近的感知、风险排序、规划和控制行为？

The receiver may be an AD model/stack or a human driver in a
human-in-the-loop study. Use the receiver class that matches the intended test
domain; human and machine evidence are complementary rather than
interchangeable.

The long-term credibility metric is planned around a four-layer evidence
chain: log reproduction, sensor consistency, task-level consistency, and
closed-loop outcome credibility. That is a future metric-research structure,
not the current grading scheme.

## Read First

```text
docs/research_guiding_principles.md
docs/hugsim_matched_receiver_validation_plan.md
docs/hugsim_credibility_decision_rules.md
docs/hugsim_smoke_test_plan.md
docs/runs/hugsim_source_anchor_gate_001.md
docs/runs/hugsim_source_anchor_gate_001.json
docs/runs/hugsim_counterfactual_001.md
docs/runs/hugsim_horizon_factorial_001.md
docs/runs/hugsim_horizon_factorial_001_audit.json
docs/runs/hugsim_near_cut_in_001.md
docs/runs/hugsim_near_cut_in_001_audit.json
```

## Corrected State

The old 6-second lead-plus-cut-in run reported:

```text
TTC first failure: 4.75 s
NC first failure: 5.75 s
```

Those risk events are now `rejected`.

HUGSIM's saved scoring trajectory contains five future waypoints at 0.5-second
spacing, so each metric frame needs 2.5 seconds of future actor history. The
6-second run is valid only through 3.5 seconds. Its failures occur after that
point, where the scorer repeats the last actor box.

The 6-second run and a 9-second extension have an exact common
state/action/plan prefix, yet all old failures disappear in the extension.
This correction prevents an invalid metric interpretation. Keep it as a
run-level engineering validity note, not as a central theoretical finding.

## Corrected 2×2 Actor-Removal Result

Nine-second runs:

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s
artifacts/hugsim_contrast/scene-0383-lead-only-00-run002-9s
artifacts/hugsim_contrast/scene-0383-cut-in-only-00-run002-9s
artifacts/hugsim_contrast/scene-0383-multicar-cut-in-00-run002-9s
artifacts/hugsim_contrast/scene-0383-horizon-factorial-report-run002
```

Horizon-valid window, 0.25–6.5 seconds:

| Condition | NC | TTC | PDMS |
|---|---:|---:|---:|
| no actors | 1.000 | 1.000 | 1.000 |
| lead only | 1.000 | 1.000 | 1.000 |
| far cut-in only | 1.000 | 1.000 | 1.000 |
| lead + far cut-in | 1.000 | 1.000 | 1.000 |

The far cut-in crosses the centerline but retains about 4.195 meters of
minimum 2D oriented-footprint clearance. It is a negative control, not a
credible risk event.

## Near-Distance Single-Shot Result

Parameters were fixed before execution, but the scenario was not formally
committed or externally preregistered before the run. Describe it as
**pre-specified single-shot**, not formal preregistration.

```text
artifacts/hugsim_contrast/scene-0383-near-cut-in-00-run001-9s
artifacts/hugsim_contrast/scene-0383-near-cut-in-report-run001
artifacts/hugsim_contrast/scene-0383-near-cut-in-audit-run002
```

Horizon-valid result:

| Condition | NC | TTC | PDMS |
|---|---:|---:|---:|
| no actors | 1.000 | 1.000 | 1.000 |
| far cut-in control | 1.000 | 1.000 | 1.000 |
| near cut-in | 1.000 | 0.1154 | 0.3681 |

Event evidence:

```text
centerline crossing: 3.917 s
minimum 2D oriented-footprint clearance: 0.730 m at 5.5 s
horizon-valid TTC failures: 23 frames, first at 1.0 s
failed-event actor IDs: [0]
tail padding used: false
runtime collision: false
```

Accepted narrow subclaims:

- strict input/state/action/plan pairing;
- continuous actor0 motion and centerline crossing;
- positive-clearance 2D close pass;
- actor0-specific HUGSIM internal TTC surrogate response inside the
  complete-future-history window;
- internal RGB/semantic/depth co-movement.

The overall segment remains `down-weighted`. Actual collision, physical TTC
value, AD-agent response, and global HUGSIM credibility remain `rejected` or
unsupported. Real traffic validity and sensor truth remain down-weighted or
not established.

Read `rejected` at claim level. A rejected behavior/metric claim may coexist
with an accepted diagnostic finding. In the current audits:

- the old 6-second risk claim is rejected, while the tail-padding defect is
  retained as its technical invalidation reason;
- timestamp-zero/YAML equality is rejected, while the reset phase-offset
  finding is accepted;
- physical TTC interpretation is rejected, while the binary-surrogate
  construct finding is accepted;
- AD-agent and global claims are rejected because they were not tested or
  exceed scope, so they imply no HUGSIM capability failure.

## Runtime and Analysis Improvements

- The plan writer can use the same `--max-steps` value as the runner and still
  receive the final `Done` handshake.
- The runner returns success only when every requested step completes and
  scoring succeeds.
- Audit summaries record configuration and runtime script hashes.
- Pair analyzers fail closed on commit, config, step count, timestamps, plans,
  and selected report provenance.
- NC/TTC conclusions fail closed when the event uses incomplete future actor
  history.
- A fail-closed claim/finding semantics validator checks every rejected claim,
  diagnostic link, decision label, repository evidence file, and external
  reference syntax/commit alignment.
- Twenty-eight unit tests pass.

## Immediate Goal

Do not run another same-scene cut-in parameter adjustment. Independent design,
evidence, and reproducibility reviews agreed that the pre-specified stop
criterion was met and another treatment would be post-hoc result chasing.

The source-anchor availability gate is now implemented. For `scene-0383`, it
is blocked because the released minimized scene has 1080 calibration/pose
records but none of the referenced real RGB files or original nuScenes source
tokens. Existing closed-loop observations also use a non-identical camera
template and must not be called matched-pose renders.

The next material HUGSIM action should prioritize a matched real-versus-sim
receiver comparison. Practical steps are:

1. obtain the licensed nuScenes source images and the ASAP
   `interp_12Hz_trainval` mapping for `scene-0383`;
2. render split-derived test candidate poses using their exact metadata
   intrinsics and `camtoworld`, and verify checkpoint training provenance
   before calling them genuinely held out;
3. feed matched real/sim observations to the same AD receiver, or design a
   bounded human-in-the-loop comparison;
4. use distinct vehicle assets and more credible map-constrained or staged
   behavior for subsequent counterfactual interventions.

Do not independently install a full AD agent, run the full benchmark, expand
to OmniDreams/Cosmos, or design the final four-layer credibility metric.

## Guardrails

- Never accept NC/TTC from a rollout tail without a future actor state for
  every scored planned waypoint.
- Preserve old raw outputs but mark superseded interpretations explicitly.
- Treat HUGSIM TTC as a binary internal surrogate, not physical
  time-to-collision.
- Do not call a scripted ConstantPlanner diagonal a validated real merge.
- Do not treat one duplicated vehicle identity as actor diversity.
- Do not treat common-renderer RGB/semantic/depth agreement as real-sensor
  correctness.
- The deterministic plan writer is a loop enabler, not an AD agent.
- Use exactly `accepted`, `down-weighted`, and `rejected`.
- Never interpret `rejected` without its tested flag and rejection basis.
