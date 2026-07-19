# Codex Next Task — Establish the HUGSIM Log-Reproduction Anchor

> Read this file first when resuming HUGSIM work.

## Project Objective

Develop a four-layer credibility evidence chain for log-driven simulators:

```text
Layer 1 — Log Reproduction
Layer 2 — Sensor Consistency
Layer 3 — Task-Level Consistency
Layer 4 — Closed-Loop Outcome Credibility
```

“Log-driven” means that the simulator constructs its environment from real
road-driving capture sequences and generates counterfactual closed-loop
evolution. Exact log replay is not required.

HUGSIM is the first experimental carrier, not the final research target. It is
a real-driving-sequence reconstruction-based, counterfactual closed-loop neural
simulator.

Read:

```text
docs/log_driven_simulator_four_layer_evidence_chain.md
docs/hugsim_four_layer_evidence_status.json
docs/hugsim_credibility_decision_rules.md
```

## Current HUGSIM Evidence

| Evidence layer | Current decision | Main reason |
|---|---|---|
| Log reproduction | `down-weighted` | Real-data origin is known, but exact source frames and matched reconstruction comparisons are missing |
| Sensor consistency | `down-weighted` | Internal RGB/semantic/depth evidence exists, but visible artifacts and no real-sensor anchor remain |
| Task-level consistency | `down-weighted` overall | A narrow internal geometry response is `accepted`, but intervention coverage is limited |
| Closed-loop outcome credibility | `rejected` for AD-evaluation claims | The deterministic planner is a loop enabler, not a sensor-input AD agent |

Source Availability Gate and simulator-side evidence completeness are supporting
checks, not two of the four evidence layers.

## Corrected Experimental Baseline

A third-party review found a one-step mismatch between the metric frame and its
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

These results support a narrow Layer 3 internal-geometry response. They do not
establish Layer 2 real-sensor consistency or Layer 4 AD-evaluation credibility.

## Immediate Goal

Establish Layer 1 log reproduction for released `scene-0383`.

First determine whether the exact real camera observations and capture metadata
behind the released reconstruction are locally available or can be obtained
from the identified public dataset sequence.

Target evidence chain:

```text
exact source-log frame, timestamp, calibration, and pose
→ HUGSIM reconstruction rendered at the matched pose
→ measurable and inspectable reproduction gap
→ RGB / semantic / depth sensor-consistency judgment
→ controlled task-level counterfactual
→ accepted / down-weighted / rejected claim
```

## Required Questions

1. Can the released scene be traced to exact source frames, timestamps, camera
   calibration, and poses?
2. At captured poses, does the reconstruction reproduce task-relevant road,
   vehicle, boundary, depth, and semantic evidence?
3. Are RGB, semantic, depth, multi-camera, and temporal outputs mutually
   consistent and consistent with the real capture?
4. As ego deviates from the captured trajectory, where does sensor evidence
   become unsupported?
5. Under a controlled intervention, do task-level relations remain consistent
   across sensor evidence, internal geometry, state, and metrics?
6. What additional evidence would be required before any closed-loop result
   could support an AD-system evaluation claim?

## Near-Term Outputs

- an exact source-frame and reconstruction provenance record;
- a matched-pose real-versus-rendered comparison when source frames exist;
- an explicit unavailable-evidence record when they do not;
- a Layer 1 log-reproduction decision;
- a Layer 2 sensor-consistency decision grounded in the real source;
- updated Layer 3 claim-specific decisions;
- no Layer 4 AD-performance claim.

## Guardrails

Do not:

- treat source availability as proof of log reproduction;
- treat real-log origin as proof of counterfactual credibility;
- equate cross-modal outputs from one renderer with real-sensor agreement;
- report internal NC/TTC response as sensor-input AD-agent validity;
- expand a two-position test into a general lane-relation claim;
- install full AD agents before the lower evidence layers are understood;
- run a full benchmark or define a final credibility metric;
- expand to OmniDreams / Cosmos during this task;
- overwrite successful outputs.

## Success Criterion

The next step succeeds when the gap between the real source log and the
reconstructed scene is explicit and auditable. More counterfactual HUGSIM runs
without that Layer 1 anchor are not material progress toward the four-layer
evidence chain.
