# Codex Next Task — Vehicle-State Transition Qualification 001

> This is the only current milestone. Read older run files only when a result
> is directly reused.

## Objective

Qualify the vehicle-state transition immediately downstream of the now-audited
HUGSIM–SparseDrive actuation contract. Determine whether the current
forward-driving loop permits reverse motion, how zero speed is represented,
and which heading is valid for near-stop footprint geometry.

HUGSIM remains the first experimental carrier, not the research result to
prove. The durable question remains whether task-relevant simulator input and
evolution are equivalent enough to reality to produce credible AD perception,
planning, control, and closed-loop consequences.

## Why this is next

Actuation Contract Qualification 001 is closed:

- `strict_audit` fail-closed behavior: `accepted`;
- six `bounded_projection` executions: `accepted` mechanically;
- final progress/speed order `below <= near <= above`: `rejected` in both
  resets because `near < below`;
- near final speed: `-0.270/-0.337 m/s`;
- real-world closed-loop credibility: `rejected`.

The bounded actions were all inside HUGSIM's declared box, yet the released
state update allowed the ego to cross zero and move backward. Therefore action
admissibility cannot qualify state admissibility or near-stop geometry.

Primary result:

```text
docs/runs/hugsim_sparsedrive_actuation_contract_qualification_001.md
```

## Single gate

Create a bounded, preregistered **state-transition contract audit** before any
new 4/2/1 m live rerun.

First establish from source and model intent:

1. whether `ego_velo` is signed longitudinal speed or forward-only speed;
2. whether reverse motion is an intentional supported mode with a gear state;
3. whether the released update must clamp at zero for this scenario contract;
4. how pose/yaw and steering evolve at zero or negative speed;
5. which heading, if any, is admissible for oriented-footprint clearance when
   motion is near zero.

If the intended semantics cannot be established, finish with
`blocked_state_transition_semantics`; do not invent a clamp or heading rule.

## Bounded work

Use frozen synthetic state/control sequences before a live rerun. At minimum,
cover:

- positive speed under braking without crossing zero;
- braking that mathematically crosses zero;
- exactly zero speed;
- negative speed only if an explicit reverse contract is supported;
- straight and non-zero steering cases;
- repeat and timestep consistency.

For each case record raw state, raw action, next state, qualified admissible
state, any projection or rejection, and the reason. Keep action-contract and
state-contract decisions separate.

Do not yet:

- add a new scene, actor condition, receiver, or AD model;
- implement a feasibility-aware trajectory tracker;
- tune the existing 4/2/1 m stimuli;
- use HUGSIM NC/TTC/PDMS as a state-truth judge;
- claim a real-vehicle response or repair the rejected closed-loop result.

## Decision after the gate

- If signed reverse is explicitly supported and task-valid, qualify its gear,
  heading, and clearance semantics before interpreting the existing reversal.
- If the scenario is forward-only and a zero-speed boundary is independently
  justified, preregister a minimal state projection and rerun the unchanged
  4/2/1 m conditions twice.
- If neither contract can be justified, retain the current bounded loop as
  negative evidence and move to an execution model with qualified dynamics;
  do not patch HUGSIM merely to obtain the expected order.

## Required outputs

- source-backed state-semantics audit;
- preregistration before any corrective experiment;
- isolated implementation and direct tests if a contract is justified;
- machine-readable synthetic-control audit and concise plot/table;
- evidence decisions using only `accepted`, `down-weighted`, `rejected`;
- update this file to the next single gate only after the milestone closes.

## Sources to read

Start with:

```text
docs/runs/hugsim_sparsedrive_actuation_contract_qualification_001.md
scripts/hugsim_control_adapter.py
/home/yawei/HUGSIM/sim/hugsim_env/envs/hug_sim.py
/home/yawei/HUGSIM/configs/sim/kinematic.yaml
```

Use only as needed:

```text
docs/counterfactual_credibility_constraints.md
docs/hugsim_metric_evidence_map.md
docs/hugsim_credibility_decision_rules.md
```

## Stable guardrails

- A `rejected` claim is useful negative evidence, not an experiment failure.
- HUGSIM-declared state is not independent reality truth.
- Bounded projection does not make the raw plan feasible or physically real.
- Near-zero heading and complete-clearance claims remain unqualified.
- Do not define a general HUGSIM credibility score from this milestone.
