# HUGSIM–SparseDrive Actuation Contract Qualification 001

Date: 2026-08-25

Preregistration commit: `3813016308db79e4615593fad33592a2971a0ce5`

Final analysis: `artifacts/sparsedrive_actuation_contract_001/analysis-run002/`

## Result in one paragraph

The actuation boundary is now mechanically auditable, but the bounded loop did
not preserve the preregistered response order. `strict_audit` correctly kept
the first out-of-range raw command and stopped before applying it. All six
`bounded_projection` runs completed 18/18 steps with every applied command
inside HUGSIM's declared action box and without fallback, plan repetition,
termination, or collision. Nevertheless, both progress and final-speed claims
were `rejected`: in both independent resets the `near` condition progressed
less and ended slower than the more severe `below` condition. The near runs
also ended at negative longitudinal speed, which HUGSIM's released kinematic
update permits. A valid action-box contract therefore does not by itself
qualify the resulting vehicle-state evolution.

## Qualified interface

HUGSIM source and configuration establish the following narrow interface:

| Command | Meaning | Unit | Qualified range |
|---|---|---|---:|
| `acc` | longitudinal acceleration | m/s² | `[-2, 2]` |
| `steer_rate` | steering-angle rate | rad/s | `[-0.2617993878, 0.2617993878]` |

The action space and state update are declared in
`/home/yawei/HUGSIM/sim/hugsim_env/envs/hug_sim.py`; the numeric bounds and
`dt=0.25 s` are in `/home/yawei/HUGSIM/configs/sim/kinematic.yaml`. The released
iLQR permits `steer_rate` up to `±0.4 rad/s`, so it can generate a command that
the environment itself declares out of range.

Two contracts were kept distinct:

- `strict_audit`: reject the complete raw command and do not call `env.step`;
- `bounded_projection`: retain the raw command and apply the closest point in
  the confirmed box, implemented as component-wise clipping.

`bounded_projection` is a diagnostic execution contract. It does not make the
raw SparseDrive–iLQR request feasible and is not a vehicle-dynamics model.

## Frozen experiment

The existing scene-0383 boundary stimuli were unchanged:

| Condition | Designed common-reference endpoint gap |
|---|---:|
| `above` | 4 m |
| `near` | 2 m |
| `below` | 1 m |

Actor asset, speed `0.5 m/s`, source history, SparseDrive checkpoint, camera
contract, six-step warm start, corrected coordinate adapter, 2 Hz planning,
two 0.25 s environment steps per plan, and 4.5 s live horizon were held fixed.
Each bounded condition used two newly created HUGSIM and SparseDrive processes.

## Contract mechanics

The strict regression reproduced the old failure location. After eight
successful environment steps, attempted step 8 produced:

```text
raw acc         = 0.2015109876 m/s²
raw steer_rate  = 0.4000000000 rad/s
qualified limit = 0.2617993878 rad/s
applied_control = null
```

The machine record contains nine attempts but only eight completed steps. This
is direct evidence that the rejected command was not silently clipped or sent
to the environment. The strict contract claim is `accepted`; the raw
SparseDrive–iLQR sequence remains infeasible under the declared HUGSIM action
box.

All six bounded runs recorded raw control, applied control, bounds, violation
amount, projection residual, and saturation state on every one of 18 steps.
All applied values passed the declared box. The bounded execution-mechanics
claim is `accepted`.

## Projection burden and outcomes

| Condition | Reset | Saturated steps | Fraction | First saturation (live s) | Cumulative residual L2 | Final progress (m) | Final speed (m/s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| below | 1 | 4/18 | 0.222 | 1.5 | 0.552802 | 1.573707 | 0.047166 |
| below | 2 | 4/18 | 0.222 | 1.5 | 0.552802 | 1.572213 | 0.064388 |
| near | 1 | 6/18 | 0.333 | 3.0 | 0.742103 | 1.220950 | -0.270178 |
| near | 2 | 6/18 | 0.333 | 3.0 | 0.567118 | 1.051750 | -0.337445 |
| above | 1 | 2/18 | 0.111 | 2.0 | 0.276401 | 2.079204 | 0.045688 |
| above | 2 | 4/18 | 0.222 | 2.0 | 0.552802 | 2.029471 | 0.007336 |

Only `steer_rate` saturated. Its maximum raw violation was
`0.1382006122 rad/s`; acceleration never violated its action bound. These
burden values are descriptive and have no post-hoc acceptance threshold.

The planned order was `below <= near <= above` for progress and final speed.
It failed in both resets:

- progress `near - below`: `-0.352757 m` and `-0.520462 m`;
- speed `near - below`: `-0.317344 m/s` and `-0.401833 m/s`.

The maximum same-condition repeat ranges were `0.169200 m` for progress and
`0.067267 m/s` for final speed. Because the direction itself reversed, the
effect-versus-repeat claim is `rejected`, not merely down-weighted.

The planning-mode sequences were stable across the two resets of each
condition. Below and near selected trajectory modes
`3,5,1,1,1,1,1,1,1`; above selected `3,3,5,5,1,1,1,1,1`. The near/below
reversal therefore cannot be dismissed as a between-reset mode mismatch.

## Negative diagnostic: bounded actions, unqualified states

The near trajectories crossed zero speed at approximately world time 5.0 s
and ended in reverse. HUGSIM updates velocity as `velo += acc * dt` and does
not enforce a non-negative forward-speed state or an explicit reverse-gear
contract. The commanded accelerations remained inside `[-2, 2] m/s²`, so the
action contract operated exactly as designed while the state became
task-questionable.

This supports an `accepted` diagnostic finding:

> Action admissibility and vehicle-state admissibility are different gates.

It does not establish what a real vehicle would do, and it does not by itself
assign the reversal to SparseDrive, iLQR, or HUGSIM individually.

## Evidence decisions

| Claim | Decision | Meaning |
|---|---|---|
| strict fail-closed behavior | `accepted` | raw violation retained; rejected attempt not applied |
| bounded contract mechanics and six-run execution | `accepted` | all applied actions in box; all runs completed |
| projection burden measurement | `accepted` | raw/applied and burden are reproducibly measurable; no acceptability threshold |
| bounded progress/speed direction beyond repeat | `rejected` | near/below order reversed in both resets |
| action admissibility implies state admissibility | `rejected` | near runs entered negative speed |
| near-stop clearance or physical collision | `rejected` | near-zero heading remains deliberately unqualified; no collision observed |
| real-world closed-loop credibility | `rejected` | no matched real outcome or qualified response magnitude |

The strongest allowed result is limited to this scene, fixed SparseDrive,
frozen 4/2/1 m intervention, and confirmed HUGSIM action box. It quantifies
whether bounded projection completes the loop and whether the internal
response order survives repeat variation. It does not qualify a real actuator,
physical TTC, collision probability, AD safety, or HUGSIM as a general test
domain.

## Reproducibility and artifacts

The implementation and preregistration were committed before live execution.
Direct tests were run with:

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python -m unittest \
  tests.test_hugsim_control_adapter tests.test_run_hugsim_case
```

Each live run used `scripts/run_hugsim_case.py` with `--max-steps 18`,
`--control-hold-steps 2`, the condition's frozen scenario/source/reference,
and either `--actuation-contract strict_audit` or
`--actuation-contract bounded_projection`.

Primary artifacts:

- preregistration:
  `docs/runs/hugsim_sparsedrive_actuation_contract_preregistration_001.json`;
- analysis erratum:
  `docs/runs/hugsim_sparsedrive_actuation_contract_preregistration_001_erratum.md`;
- machine audit:
  `artifacts/sparsedrive_actuation_contract_001/analysis-run002/actuation_contract_audit.json`;
- committed compact audit and run-output hashes:
  `docs/runs/hugsim_sparsedrive_actuation_contract_audit_001.json`;
- summary plot:
  `artifacts/sparsedrive_actuation_contract_001/analysis-run002/actuation_contract_summary.png`;
- generated concise report:
  `artifacts/sparsedrive_actuation_contract_001/analysis-run002/actuation_contract_report.md`;
- strict and six bounded run manifests, videos, native outputs, and logs:
  `artifacts/sparsedrive_actuation_contract_001/`.

The preregistered analysis initially stopped before reading results because of
one JSON field-path error. The committed erratum records the preregistered and
executed script hashes. The final analyzer also completes preregistered
provenance fields; no measurement or decision rule changed.

## Next gate

Do not add a new scene, receiver, or feasibility-aware tracker. The next
single gate is a **vehicle-state transition qualification**: establish whether
this forward-driving loop permits reverse motion, how zero speed is handled,
and which heading defines near-stop footprint geometry. Freeze those rules on
synthetic controls before deciding whether the unchanged 4/2/1 m loop merits a
corrective rerun.
