# CF-I-OBS-001 state-to-observation result

## Formal result

The preregistered run preserved all 14 selected raw `CAM_BACK` inputs and
triggered its stop rule. Two indicators were `accepted` and two were
`rejected`:

| Indicator | Result | Meaning |
|---|---|---|
| `CF-I-O1` state to render transform | `accepted` | planner state replay, rendered position, and yaw matched; the shifted-state negative failed |
| `CF-I-O2` camera membership | `rejected` | all 14 expected `CAM_BACK` actor/no-actor pairs reported zero RGB support |
| `CF-I-O3` projected localization | `rejected` | zero paired RGB support made localization unavailable |
| `CF-I-O4` causal observation onset | `accepted` | actual observation first diverged at index 9 after the index-8 state cause; the two-frame-early label diverged at index 6 and was rejected |

The raw receiver-facing images visibly contain the rear vehicle. Therefore the
O2/O3 result is not evidence that HUGSIM failed to render it.

## Diagnosed measurement failure

HUGSIM `Camera.__init__` uses a shared mutable default `dynamics={}`. The
renderer assigns planned actors into `viewpoint.dynamics` in place. In this
run, rendering the actor first contaminated the following nominal no-actor
render: both images contained the same actor, so their RGB difference was zero.

This is useful negative method evidence. It shows that a nominal no-actor
control must be checked at the actual receiver input rather than trusted from
the requested condition name.

The unconditional `strongest_allowed_claim` text emitted in the run001 JSON
must not be used: it conflicts with the recorded O2/O3 rejections and
`stop_rule_triggered=true`. The claim decisions and stop rule are authoritative.
The generator is corrected for the follow-up run.

## Preserved outputs

```text
docs/runs/hugsim_interaction_observation_indicators_001.json
artifacts/hugsim_interaction_observation/analysis-run001/interaction_observation_measurements.json
artifacts/hugsim_interaction_observation/analysis-run001/interaction_observation_summary.png
artifacts/hugsim_interaction_observation/analysis-run001/interaction_observation_cam_back_contact_sheet.png
```

## Corrective repeat

CF-I-OBS-002 clears the shared camera-dynamics dictionary immediately before
both members of every paired render. It changes no source state, frame, camera,
threshold, negative control, or claim boundary.
