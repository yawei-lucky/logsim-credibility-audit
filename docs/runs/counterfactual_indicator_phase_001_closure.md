# Counterfactual law and indicator phase 001 — closure

Date: 2026-07-22

## Closure decision

The first **simulator-internal causal-law and indicator pilot** is closed. This
means that the project now has a falsifiable skeleton, representative controls,
and explicit evidence boundaries. It does not mean that all indicators have
real-world external validity, that HUGSIM is credible as an AD test domain, or
that risk, planning, control, and closed-loop behavior have been validated.

## What is now covered

| Law family | Executed evidence | Current result |
|---|---|---|
| Geometry and projection | independently recomputed footprint/corridor relations and state-to-camera transport | useful for declared-state intervention validity; precise RGB spatial truth remains unqualified |
| Motion and dynamics | CF-M constant-speed controls | narrow continuity and relative-motion relations accepted; behavior realism not tested |
| Visibility and observability | CF-O controlled two-endpoint occlusion | obvious visibility direction detected; continuous and real-sensor visibility not established |
| Multi-actor interaction | CF-I capability, state, planner-loop, and observation audits | narrow stimulus-response and timing paths established; released timing defect and observation-boundary evidence retained |
| Risk causality | task-boundary audit and ordinal 2x2 experiment | static designed-range near/far and lane-direction order established; dynamic conflict, AD risk judgment, and action remain open |

The supporting records are:

- `docs/runs/hugsim_motion_metamorphic_001.md`;
- `docs/runs/hugsim_occlusion_metamorphic_002.md`;
- `docs/runs/hugsim_interaction_capability_001.md`;
- `docs/runs/hugsim_interaction_state_indicators_001.md`;
- `docs/runs/hugsim_interaction_planner_loop_indicators_001.md`;
- `docs/runs/hugsim_interaction_observation_indicators_002.md` and `003`;
- `docs/runs/hugsim_ordinal_metamorphic_001.md`.

## What the phase produced

The output is not one credibility score. It is a reusable indicator pattern:

1. state the intervention and held-fixed conditions;
2. state an independently motivated hard constraint or conditional order;
3. report valid coverage, violations/reversals, and unavailable observations;
4. separate simulator state, rendered observation, receiver response, and
   downstream outcome;
5. retain positive evidence, negative evidence, and capability boundaries
   without forcing them into one pass/fail verdict.

The failed RGB-localization gate is part of this output: projected metadata
boxes and a centre-only Gaussian envelope are not qualified as precise pixel
support truth. No further threshold, dilation, or Gaussian-quantile tuning is
part of this phase.

## Boundary between the closed phase and the next phase

The first phase establishes whether candidate laws and indicators can detect
known causal directions and known counterexamples inside the experimental
carrier. The next phase asks whether task information reaches a qualified AD
receiver and eventually changes risk ranking and action in the correct
direction.

The sequence is:

```text
supporting-receiver qualification
  -> dynamic risk-information causality (CF-R)
  -> target planning/control response
  -> bounded closed-loop outcome stability
```

Risk and closed-loop work are therefore still required. They are intentionally
not folded into this closure or inferred from HUGSIM's internal TTC/PDMS.
