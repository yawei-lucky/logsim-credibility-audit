# HUGSIM CF-I interaction capability gate 001

## Question

Does the available HUGSIM code contain a controller in which one vehicle's
state or planned motion changes another vehicle's output? Two independently
scripted trajectories do not satisfy this definition.

## Method

The probe used HUGSIM revision `adeca402cad4af8635e13d0a105e2fee6a14de85`
and held each responder's initial state fixed.

- `IDM`: the same synthetic neighbor was moved from off the responder's route
  to 6 m ahead on the route.
- `AttackPlanner`: the attacked ego future started from the same lateral
  position, then either continued straight or progressively shifted 5 m
  laterally. No other neighbor was present.
- Controller interfaces and output states were recorded by
  `scripts/audit_hugsim_interaction_capability.py`.

This is a controller-level deterministic probe. It is not yet a rendered scene
experiment and does not use HUGSIM RGB, semantics, depth, or scores as truth.

## Results

| Mechanism | Fixed-output condition | Stimulated condition | Observed response | Narrow judgment |
|---|---:|---:|---|---|
| IDM | next speed `5.3997 m/s` with off-route neighbor | next speed `1.2095 m/s` with close lead | `-4.1902 m/s` | `accepted` |
| AttackPlanner | straight ego-plan output `[x=-0.0000, y=1.1462, yaw=0.0000, v=5.8889]` | lateral ego-plan output `[x=0.0587, y=1.1151, yaw=-0.0965, v=5.6138]` | state L2 difference `0.2990` | `accepted` |
| ConstantPlanner | interface is only `(state, dt)` | no vehicle stimulus input exists | cannot respond to another vehicle | interaction claim `rejected` |
| UnicyclePlanner | interface is only `(dt)` | no vehicle stimulus input exists | cannot respond to another vehicle | interaction claim `rejected` |

Machine-readable output:
`docs/runs/hugsim_interaction_capability_001.json`.

## Interpretation

The CF-I capability gate passes only for the narrow internal-mechanism claim:
HUGSIM contains controllers whose output changes when another vehicle's state
or future plan changes. Therefore a genuine stimulus-response experiment is
technically possible; earlier multi-car runs made only from independent
`ConstantPlanner` actors are not interaction experiments.

The two usable mechanisms have different boundaries:

- `IDM` is neighbor-responsive, but returns the unchanged state when no route
  is available. A scene-level IDM experiment therefore requires a qualified
  route/map path.
- `AttackPlanner` consumes the ego's predicted future and can generate a
  response without the HD map in the current implementation. Its objective is
  adversarial proximity, not ordinary human traffic behavior.
- In the complete HUGSIM planner loop, that predicted future is a
  constant-heading extrapolation of the current ego state, not the external
  AD's full future plan. The ordinary-neighbor input is also passed as
  `neighbors[1:]`; generic non-ego vehicle-to-vehicle response is therefore not
  qualified here.

Overall evidence is `down-weighted`. The probe establishes code-path
sensitivity, not behavioral realism. It does not yet establish causal timing
inside a complete HUGSIM rollout, realistic merging/yielding, physical
feasibility over time, sensor consistency, AD response, or real-world fitness.

## Next bounded experiment

Use one `AttackPlanner` responder with the locally available scene and vehicle
asset. Introduce one timed change in ego motion while holding the scene,
responder identity and initial state fixed. First verify that the changed ego
state is extrapolated and delivered through HUGSIM's planner loop, then check
response timing and state continuity. Describe the result as adversarial
ego-response capability; do not generalize it to realistic traffic interaction.
