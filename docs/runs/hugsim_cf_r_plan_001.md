# HUGSIM CF-R planning-response audit 001

Date: 2026-07-23

Preregistration commit: `1f8d1b2`

## Outcome

The preregistered narrow planning-direction claim is `accepted`.
As evidence of real-world simulator validity, the overall result remains
`down-weighted`: direction is established, but realistic response magnitude is
not.

The same frozen SparseDrive receiver saw three HUGSIM sequences in which only
the lead actor's ConstantPlanner speed changed:

- `slow = 0.5 m/s`: strongest ego closure;
- `nominal = 1.0 m/s`: intermediate ego closure;
- `fast = 1.5 m/s`: weakest ego closure.

After equal four-frame warm-up, all ten analyzed timestamps from `1.5–6.0 s`
strictly satisfied:

```text
slow 3 s forward plan endpoint
  < nominal 3 s forward plan endpoint
  < fast 3 s forward plan endpoint
```

All 30 preregistered pairwise comparisons had the expected direction, with no
tie or reversal.

## Main result

| Condition | Median 3 s forward endpoint |
|---|---:|
| slow / strongest closure | 3.171 m |
| nominal | 4.172 m |
| fast / weakest closure | 4.441 m |

The minimum adjacent pairwise margin was `0.0868 m`, compared with the frozen
receiver reset numerical envelope of `0.0001 m`. The response is therefore not
explained by the observed numerical reset variation.

The selected native planning mode remained mode `3` in every condition and
timestamp. Final lateral displacement stayed below `0.08 m`. Thus the primary
result is a graded longitudinal-plan response within one mode, not a mode flip
or a large lane-change response. Median first-step speeds also followed the
same diagnostic direction: `1.769 / 1.940 / 1.966 m/s`.

## What this establishes

The experiment completes one bounded internal causal transport chain:

```text
declared actor-speed intervention
  -> ordered HUGSIM state and six-camera observation
  -> frozen AD receiver
  -> ordered native open-loop longitudinal plan
```

It is positive evidence that the tested HUGSIM counterfactual preserved enough
task-relevant information for this frozen AD receiver to respond in the
predeclared direction. It also demonstrates that the conditional-monotonic
indicator can discriminate a strong three-level planning response.

## What it does not establish

The magnitude has no matched real-world acceptance bound. The experiment does
not show whether SparseDrive slowed by the correct amount, whether another AD
architecture would agree, or whether the resulting vehicle would avoid a
collision in closed loop.

| Claim | Decision | Boundary |
|---|---|---|
| The frozen input and state gates passed | `accepted` | exact inputs, equal ego state/command, independent reset and complete warm-up |
| The declared conflict order reached SparseDrive's 3 s longitudinal planning direction | `accepted` | one scene, three designed actor speeds, one frozen receiver |
| This response magnitude is realistic or externally calibrated | `down-weighted` | no matched real plan/control or qualified behavioral range |
| This is brake/steer control, physical TTC or a closed-loop safety result | `rejected` | SparseDrive produces an open-loop trajectory |
| This proves general HUGSIM credibility | `rejected` | the claim exceeds this bounded designed-counterfactual result |

Here `rejected` means that this experiment is not allowed to support the
stronger claim; it does not mean that HUGSIM was shown to fail that capability.

## Inspectable artifacts

```text
artifacts/sparsedrive_cf_r_plan/receiver-run001/runtime_smoke.json
artifacts/sparsedrive_cf_r_plan/receiver-run001/{slow,nominal,fast}_runtime_smoke.png
artifacts/sparsedrive_cf_r_plan/analysis-run001/cf_r_plan_audit.json
artifacts/sparsedrive_cf_r_plan/analysis-run001/cf_r_plan_summary.png
```

## Next boundary

Do not add another actor-speed curve. The next causal link is a small
plan-to-simulator-loop qualification: verify that the SparseDrive trajectory
can be converted into the HUGSIM plan interface without changing axes, timing
or intent. Only after that gate should a bounded closed-loop outcome experiment
be preregistered. Such a result would still be simulator-internal until an
external or matched-real outcome basis is added.
