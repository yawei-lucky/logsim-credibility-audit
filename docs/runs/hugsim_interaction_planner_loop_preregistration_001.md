# CF-I-LOOP-001 planner-loop indicator transport preregistration

## Purpose

Move the already validated CF-I-T1 through CF-I-T4 indicators from the direct
state harness into HUGSIM's actual `planner.plan_traj` loop without changing
their controls or thresholds.

A single prerequisite call confirmed that the planner and local assets load;
that call is not formal output. This preregistration freezes the full 24-step
transport run before its outputs are generated.

## Fixed design

- One responder and the locally available scene-0383 ground/vehicle assets.
- `AttackPlanner`, `best_k=1`, `ATTACK_FREQ=1`; no rendering.
- Released planner interval `0.25 s` is the known temporal negative.
- Planner interval `2/19≈0.1053 s` is the explicitly modified aligned control.
- Ego stops at declared transition 8; one control applies it at transition 7.
- ConstantPlanner remains the no-online-response negative.
- All T1--T4 tolerances are copied unchanged from CF-I-STATE-001.

Transport succeeds only if all four indicators reproduce their prior control
decisions. Otherwise work stops before rendering and records the transport gap.

Machine-readable preregistration:
`docs/runs/hugsim_interaction_planner_loop_preregistration_001.json`.
