# Repository Guidance

This file applies to the entire `logsim-credibility-audit` repository.
More specific `AGENTS.md` files in subdirectories may add or override rules for
their own scope.

## Working Principles

- Prefer the smallest reliable solution that satisfies the current task.
- Keep work bounded, reproducible, and easy to review.
- Match rigor and validation effort to the actual risk.
- Avoid premature abstraction, unnecessary configuration, and broad frameworks
  that are not required by the current project phase.
- If work is drifting into excessive scope, brittle automation, or unnecessary
  completeness, report the tradeoff and propose the lighter path.
- Preserve existing user work and do not perform destructive cleanup without
  explicit authorization.

## Execution Environment

- This checkout is operated directly in Linux at
  `/home/yawei/logsim-credibility-audit`.
- Run project commands directly in the active Linux shell. Do not add a
  Windows relay, WSL entry point, or SSH layer unless a task explicitly targets
  another machine.
- Before build, GPU, service, deployment, or Git publication operations,
  confirm the working directory, host, branch, status, and remote as relevant.
- The default Codex sandbox may not expose the GPU. GPU-dependent commands must
  use an approved GPU-visible context.
- Do not use `/data` for project outputs; it was full during the initial HUGSIM
  run.

## Project Direction

- HUGSIM is the current experimental carrier, not the final research goal.
- The long-term credibility metric is planned around a four-layer evidence
  chain: log reproduction, sensor consistency, task-level consistency, and
  closed-loop outcome credibility.
- The four layers are a future metric-research structure. Do not use them as
  current project stages or assign HUGSIM a per-layer score before metric
  design begins.
- "Log-driven" means that the simulator constructs its environment from real
  road-driving capture sequences and generates counterfactual closed-loop
  evolution; exact log replay is not required.
- The current HUGSIM goal is to collect bounded positive evidence, negative
  evidence, capability boundaries, and unresolved areas for a general
  credibility-validation framework. Prioritize task-relevant real-versus-sim
  receiver consistency over visual attractiveness alone.
- The current immediate route is metric audit and evidence mapping before new
  proxy metrics or receiver-response curves are added. Bounded normal scenes
  may be collected to cover materially different geometry, rendering, and
  perception conditions. A real source-log matched anchor remains a necessary
  later evidence upgrade before real-sim consistency claims, but its current
  absence is not a reason to stop the metric audit.
- Do not expand to OmniDreams / Cosmos, a full HUGSIM benchmark, installation of
  full AD agents, or a final quantitative credibility metric unless the user
  explicitly changes the project direction.
- Codex may implement scoped experiments, collect evidence, maintain
  documentation, and assist with Git. It must not independently redefine the
  research direction.

## Research and Evidence Rules

- Complete the Source Availability Gate before treating a simulator as
  externally auditable.
- Distinguish paper-reported claims from independently inspectable or
  reproducible evidence.
- Do not invent citations, paper claims, artifact availability, or experimental
  results.
- Use exactly these segment-level evidence labels:
  `accepted`, `down-weighted`, and `rejected`.
- Do not upgrade evidence to `accepted` unless it satisfies
  `docs/hugsim_credibility_decision_rules.md`.
- Treat HUGSIM metrics as AD-performance metrics under the simulator. Metric
  values alone do not establish simulator credibility.
- Do not accept NC/TTC events from a rollout tail unless every planned
  waypoint has its corresponding future actor state. If the scorer repeats a
  final actor box to fill missing history, treat resulting events as
  `rejected`.
- Prioritize task-relevant geometric, semantic, temporal, and relational
  consistency over visual attractiveness.
- Keep the deterministic plan-pipe writer clearly described as a simulator-loop
  enabler, not an AD agent.

## Current Sources of Truth

Read the following before substantive HUGSIM work:

1. `docs/research_guiding_principles.md`
2. `docs/hugsim_metric_evidence_map.md`
3. `CODEX_NEXT_TASK.md`
4. `PROJECT_STATE.md`
5. `docs/hugsim_matched_receiver_validation_plan.md`
6. `README.md`
7. `docs/hugsim_credibility_decision_rules.md`
8. `docs/hugsim_smoke_test_plan.md`
9. `docs/hugsim_cuda_pixi_runbook.md` when runtime or GPU work is involved

If an older workflow note conflicts with the current state, prefer the newer
project-state documents and report the conflict instead of silently combining
incompatible directions.

## Experiment and Artifact Safety

- Use deterministic, bounded runs that remain practical to inspect.
- Never overwrite an existing successful run; use a new output directory.
- Keep large generated images and run artifacts under `artifacts/`.
- Record commands, configs, inputs, outputs, failures, and evidence limitations
  needed to reproduce a judgment.
- Do not add dynamic actors before the normal-scene evidence has been reviewed,
  unless the user explicitly changes the task.
- Do not make global HUGSIM credibility claims from a smoke test or a single
  segment.

## Startup and Long-Running Scripts

When creating or modifying a startup or runner script:

- provide one clear command for the intended role;
- validate prerequisites early and fail with actionable errors;
- log the environment, host, role, working directory, important inputs, output
  location, and health status;
- surface early background-process failures;
- make reruns safe by detecting existing processes, occupied outputs, or stale
  state where relevant.

## Git Workflow

- Inspect `git status`, the current branch, the staged diff, and the remote
  before committing or pushing.
- Stage only files that belong to the current task; never include unrelated user
  changes.
- After an authorized change is complete and validated, commit it and push the
  current project branch unless the user explicitly says not to commit or push.
- Do not leave completed authorized work only as an uncommitted working-tree
  change without explaining a concrete blocker.
- Push third-party adaptations only to the user's writable fork, never to the
  official upstream repository.
- If authentication appears unavailable only inside the sandbox, verify it with
  a scoped approved check before changing credentials or repository settings.
