# CF-I-LOOP-001 planner-loop indicator transport

## Result

The formal run used preregistration commit `8fe5a73` and executed all seven
24-transition controls through HUGSIM's actual `planner.plan_traj` entrypoint.
The frozen decisions of `CF-I-T1` through `CF-I-T4` all reproduced. Their
narrow planner-loop transport claims are `accepted`; overall evidence remains
`down-weighted` because this run stops before rendering and does not establish
realistic traffic response.

## Indicator decisions

| Indicator | Positive/control result | Known negative result | Transport |
|---|---|---|---|
| `CF-I-T1` indexed-time alignment | aligned maximum offset `0 s` | released maximum offset `2.75 s` | `accepted` |
| `CF-I-T2` causal response onset | declared stimulus at index 8; first divergence 8; pre-stimulus maximum L2 `0` | one-step-early control first diverged at 7 | `accepted` |
| `CF-I-T3` response existence | aligned AttackPlanner post-stimulus maximum L2 `2.0172` | ConstantPlanner post-stimulus maximum L2 `0` | `accepted` |
| `CF-I-T4` world-time continuity | aligned maximum position residual `2.46e-5 m` | released maximum position residual `1.3373 m` | `accepted` |

The result means that the four audit tools still detect the intended timing,
causal-order, online-response, and state-continuity failures after entering the
real HUGSIM planner loop. It does **not** mean that the released interaction is
valid: the released time grid remains `rejected` by `CF-I-T1` and `CF-I-T4`.

## Precision boundary found during review

The planner-loop AttackPlanner trajectories did not numerically reproduce the
earlier direct-harness trajectories. Maximum actor-state L2 differences ranged
from `0.8349` to `8.4714` across the paired AttackPlanner controls, although all
four indicator decisions remained unchanged.

A bounded follow-up replay isolated the implementation cause: HUGSIM writes
each returned state into the planner state tensor with `next_xyrv.float()`.
Repeating the direct harness with the same float32 writeback reproduced the
actual planner-loop traces exactly for the four paired baseline/treatment
conditions (maximum L2 difference `0`). Therefore:

- the indicator **decisions** are stable across this tested precision change;
- the concrete AttackPlanner trajectory is precision- and candidate-selection
  sensitive and must not be treated as numerically invariant;
- this is an implementation boundary, not evidence for or against real-world
  traffic realism.

## What this experiment established

- `CF-I-T1`--`T4` are qualified for their bounded internal use at the actual
  HUGSIM planner-loop boundary.
- The released planner timing remains negative evidence rather than a credible
  interaction sample.
- Independent ConstantPlanner motion is still not misclassified as online
  vehicle response.
- State-level control decisions, rather than exact trajectories, are the valid
  transported result.

## What it did not establish

- No RGB, semantic, depth, camera timing, or actor projection was tested.
- AttackPlanner response is adversarial internal behavior, not qualified
  merging, yielding, or ordinary traffic behavior.
- No AD receiver, planning action, safety outcome, or real-world equivalence
  was evaluated.
- The test does not establish HUGSIM's overall credibility as an AD test world.

## Inspectable outputs

```text
docs/runs/hugsim_interaction_planner_loop_indicators_001.json
artifacts/hugsim_interaction_planner_loop/analysis-run001/interaction_planner_loop_traces.json
artifacts/hugsim_interaction_planner_loop/analysis-run001/interaction_planner_loop_indicator_summary.png
```

## Next bounded step

Transport the qualified state and causal timing into a small rendered
observation audit. Freeze the same actor states, camera poses, timestamps, and
negative controls; independently project the actor box into the cameras and
check whether the rendered observation appears in the expected camera, place,
and causal order. This next step may qualify only state-to-observation
transport. It must not use common-renderer RGB/semantic/depth agreement as
proof of real-sensor correctness, and it must not add an AD receiver yet.
