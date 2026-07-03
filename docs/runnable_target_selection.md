# Runnable Target Selection

> Purpose: choose the first runnable simulator target for the credibility-audit workflow.

## Decision

Phase 1 runnable target:

**HUGSIM**

Category:

**3DGS-based log-driven closed-loop simulator for autonomous driving**

OmniDreams / Cosmos are moved to future work because the full OmniDreams closed-loop platform is not confirmed public, and Cosmos Generator requires a much heavier model-runtime setup than the current Phase 1 should assume.

## Why HUGSIM First

HUGSIM is selected because it has:

- an available paper: https://arxiv.org/abs/2412.01718
- an official project page: https://xdimlab.github.io/HUGSIM/
- an official GitHub implementation: https://github.com/hyzhou404/HUGSIM
- a closed-loop simulation entry point: `closed_loop.py`
- released sample data / scenes / vehicles / scenarios referenced from the README
- support for several AD clients according to the README and project page
- a direct connection to the project's target setting: log-driven, photorealistic, sensor-level, closed-loop simulation

## Candidate Comparison

| Candidate | Public Code | Runtime Feasibility | Closed-Loop? | Sensor-Level? | Main Issue | Phase 1 Role |
|---|---|---|---|---|---|---|
| HUGSIM | Available | Medium | Yes | RGB / semantic / flow claims | Environment and AD-client setup may be complex | Main runnable target |
| NeuroNCAP | Available | Medium-low | Yes | Camera rendering through NeuRAD | Older NeRF-based route, less aligned with 3DGS priority | Backup / comparison |
| UniSim | Not confirmed public | Low | Yes in paper | Multi-sensor in paper | Reproducibility artifacts unclear | Historical comparison |
| AdvSim | Not confirmed public | Low | Scenario simulation in paper | LiDAR-oriented | Reproducibility artifacts unclear | Historical comparison |
| OmniDreams | Paper available, runtime not confirmed public | Low | Yes in paper | Generative video/world model | Full platform not confirmed public | Future work |
| Cosmos | Public foundation platform | High hardware burden | Not equivalent to OmniDreams closed-loop AV simulator | Generative world model | Heavy GPU and not OmniDreams-specific | Future proxy / smoke test only |

## Phase 1 Goal

The goal is not to reproduce the full HUGSIM benchmark immediately.

The goal is to run or design the smallest possible audit workflow:

```text
released scene / sample data
→ simulator observation
→ lightweight or debug AD client
→ command / waypoint
→ ego / actor state update
→ metric event
→ credibility audit log
```

## What Counts as Success

Phase 1 succeeds if the repository can document or run a minimal loop that records:

- source scene / scenario identifier;
- rendered observation metadata;
- ego state before and after each step;
- actor state before and after each step;
- AD command or waypoint;
- scenario event metadata;
- reconstruction or rendering confidence notes;
- whether evidence should be accepted, down-weighted, or rejected.

## What Does Not Count as Success

Phase 1 does not require:

- training a new 3DGS scene from scratch;
- running all HUGSIM benchmark scenarios;
- evaluating all AD agents;
- reproducing all paper tables;
- solving OmniDreams or Cosmos.

## Codex Role

Codex should only be used after the Research Commander provides verified source-grounded content.

Good Codex tasks for this phase:

- check Markdown structure;
- list TODO_SOURCE items;
- prepare a run checklist;
- help create a smoke-test script once the exact runtime path is confirmed;
- summarize diffs and PR scope.

Bad Codex tasks for this phase:

- independently decide simulator credibility;
- invent source claims;
- close issues without evidence;
- expand into a broad simulator survey.
