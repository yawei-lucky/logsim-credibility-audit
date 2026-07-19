# Codex Next Task — Build Level 3 Evidence with a Real-Log Anchor

> Read this file first when resuming HUGSIM work.

## Project Objective

Develop a credibility-validation method for log-driven simulators.

This project uses the broad definition:

> A log-driven simulator constructs an interactive environment from real
> road-driving capture sequences and generates counterfactual closed-loop
> evolution. Exact log replay is not required.

HUGSIM is the first case study, not the final research target. It is classified
as a real-driving-sequence reconstruction-based, counterfactual closed-loop
neural simulator.

## Four-Level Method

```text
Level 1 — Source Availability and Provenance
Level 2 — Closed-Loop Evidence Completeness
Level 3 — Segment-Level Credibility Judgment
Level 4 — Cross-Segment Simulator Credibility
```

Current HUGSIM status:

| Level | Status |
|---|---|
| Level 1 | Phase 1 complete |
| Level 2 | Simulator-side chain complete |
| Level 3 | `down-weighted` overall; narrow internal-geometry subclaims `accepted` |
| Level 4 | Not started |

Read:

```text
docs/log_driven_simulator_credibility_framework.md
docs/hugsim_four_level_status.json
docs/hugsim_credibility_decision_rules.md
```

## Corrected Baseline

Third-party review found a one-step mismatch between the metric frame and its
planned-trajectory anchor. The runner now anchors timestamp, ego/actor state,
and global plan at the same post-step state and includes a regression test.

Aligned outputs:

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run004-aligned
artifacts/hugsim_contrast/scene-0383-medium-00-run003-aligned
artifacts/hugsim_contrast/scene-0383-adjacent-static-00-run002-aligned
artifacts/hugsim_contrast/scene-0383-counterfactual-report-run003-aligned
```

Aligned internal metrics:

| Actor placement | NC | TTC | PDMS | HDScore |
|---|---:|---:|---:|---:|
| none | 1.000 | 1.000 | 1.000 | 0.150333 |
| lateral 0.0 m, forward 15.0 m | 0.700 | 0.500 | 0.557 | 0.083757 |
| lateral 3.5 m, forward 15.0 m | 1.000 | 1.000 | 1.000 | 0.150333 |

These results establish a narrow internal-geometry response, not sensor-level
E2E evaluation credibility.

## Immediate Goal

Strengthen Level 3 with evidence grounded in the real source sequence.

First determine whether the exact real camera observations and capture
metadata behind released `scene-0383` are locally available or can be obtained
from the identified public dataset sequence.

Target evidence chain:

```text
real source-log observation at a captured pose
→ HUGSIM reconstruction rendered at the matched pose
→ measurable and inspectable fidelity gap
→ controlled deviation / counterfactual intervention
→ segment-level accepted / down-weighted / rejected judgment
```

## Required Questions

1. Can the released scene be traced to exact source frames and camera poses?
2. At captured poses, does reconstruction preserve task-relevant road,
   vehicle, boundary, depth, and semantic evidence?
3. As ego deviates from the captured trajectory, where does evidence quality
   become unsupported?
4. Can the simulator expose that support boundary so downstream evidence is
   down-weighted or rejected?
5. Does a counterfactual event remain credible after separating source
   fidelity, rendering consistency, internal geometry, and metric response?

## Near-Term Outputs

- a source-frame / reconstruction provenance record;
- matched-pose real-versus-rendered comparison when source frames are
  available;
- an explicit record of unavailable source evidence when they are not;
- a support-region interpretation for the existing rollout;
- Level 3 evidence records with claim-specific decisions;
- no Level 4 aggregate metric yet.

## Guardrails

Do not:

- treat real-log origin as proof of counterfactual credibility;
- equate RGB/semantic/depth agreement from one renderer with real-world
  agreement;
- report internal NC/TTC response as sensor-input AD-agent validity;
- expand a two-position test into a general lane-relation claim;
- install full AD agents before source and simulator evidence are understood;
- run a full benchmark or define the final credibility metric;
- expand to OmniDreams / Cosmos during this task;
- overwrite successful outputs.

## Success Criterion

The next step succeeds when it makes the gap between **real source evidence**
and **simulated counterfactual evidence** explicit and auditable. More HUGSIM
runs without that distinction are not progress toward the final objective.
