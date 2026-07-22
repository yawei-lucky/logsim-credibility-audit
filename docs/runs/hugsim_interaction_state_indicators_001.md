# CF-I-STATE-001 state-level indicator validation

## Result

The formal run used preregistration commit `ad1832c` and completed all 24
transitions in seven deterministic control traces. All four indicators
distinguished their frozen positive and negative controls. Their narrow
control-discrimination claims are `accepted`; overall evidence remains
`down-weighted` because this is a direct controller harness, not a rendered
HUGSIM scene or real behavior sample.

## Indicator decisions

| Indicator | Positive/control result | Known negative result | Discrimination |
|---|---|---|---|
| `CF-I-T1` indexed-time alignment | aligned maximum offset `0 s` | released maximum offset `2.75 s` | `accepted` |
| `CF-I-T2` causal response onset | declared stimulus at index 8; first divergence 8; pre-stimulus maximum L2 `0` | early-stimulus control first diverged at 7; pre-stimulus maximum L2 `0.2460` | `accepted` |
| `CF-I-T3` post-stimulus response existence | aligned AttackPlanner response latency `0` steps; post-stimulus maximum L2 `5.4111` | ConstantPlanner paired maximum L2 `0` | `accepted` |
| `CF-I-T4` world-time state continuity | aligned maximum position residual `2.53e-5 m`; acceleration remained in `[-6, 5] m/s²` | released maximum position residual `1.7566 m` | `accepted` |

Every indicator reports full coverage for its selected trace. No missing state
is interpreted as a pass.

## What the experiment established

The result validates four audit tools for this bounded state-level use:

- `CF-I-T1` detects futures that are compared at unequal timestamps.
- `CF-I-T2` detects a constructed result-before-declared-cause trace.
- `CF-I-T3` does not mistake independent ConstantPlanner motion for online
  response.
- `CF-I-T4` detects that an internally generated short actor step is being
  advanced on an incompatible world clock.

This is useful negative as well as positive evidence. In the released local
configuration, the AttackPlanner candidate index interval is about `0.1053 s`
while the world/planner interval is `0.25 s`. The same state step is therefore
treated as if it spans substantially more world time. This run produced a
maximum displacement-versus-speed residual of `1.7566 m`.

## What it did not establish

- The aligned trace is a constructed positive control, not proof that released
  HUGSIM interaction is credible.
- `best_k=1` and replanning every transition remove stochastic and scheduling
  ambiguity for indicator validation; they are not a claim about the released
  extreme scenario's behavior.
- A zero-step controller response is an internal mechanism result, not a
  qualified human/traffic reaction delay.
- The growing difference between baseline and treatment does not show that the
  attack behavior is realistic, safe or representative.
- Rendering, sensor consistency, an AD receiver and complete closed-loop
  outcomes were not tested.

## Inspectable outputs

```text
docs/runs/hugsim_interaction_state_indicators_001.json
artifacts/hugsim_interaction_state/analysis-run001/interaction_state_traces.json
artifacts/hugsim_interaction_state/analysis-run001/interaction_state_indicator_summary.png
```

The summary figure plots the time-grid offset, normal versus anticipatory
response onset, aligned responder speed and released-versus-aligned continuity
residual.

## Next bounded step

Transport the same four indicators into the actual one-responder HUGSIM planner
loop. First log its actor/ego states and effective timestamps without using RGB
as evidence. The released grid remains the negative case and the aligned
configuration remains an explicitly modified positive control. Render only
after the state logs reproduce the expected indicator discrimination.
