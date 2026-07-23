# HUGSIM × SparseDrive plan-to-loop capability 001

Date: 2026-07-23

## Outcome

The narrow frozen-plan interface capability is `accepted`.

One fully warmed native SparseDrive plan was passed through HUGSIM's real FIFO,
corrected iLQR adapter and kinematic environment. The run was repeated from a
fresh environment reset. Both complete audit summaries and both writer
summaries were byte-identical across the two runs.

This is not yet a live AD closed loop: the writer replayed one retained plan
and did not infer again from the returned observation.

## Interface contract

SparseDrive and HUGSIM's plan pipe both define points as `[right, forward]` in
metres. The spatial conversion is therefore a checked identity mapping:

- exactly six native waypoints are required;
- no axis swap is applied at the FIFO boundary;
- no interpolation, truncation, padding or final-plan repetition is allowed;
- the existing corrected control adapter converts `[right, forward]` into
  iLQR `[forward, lateral, yaw]` only after the FIFO boundary.

SparseDrive and HUGSIM iLQR use `0.5 s` plan steps, while the HUGSIM vehicle
environment advances at `0.25 s`. One iLQR action was consequently held for
exactly two environment substeps. The old ego-local plan was not sent a second
time.

## Controlled capability run

- source plan:
  `artifacts/sparsedrive_receiver/scene-0383-runtime-smoke-l2c-calibrated-run001/no_actor_native_outputs.pt`,
  native index `3`, source time `1.5 s`;
- source state:
  `artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s/infos.pkl`,
  frame `6`;
- initial-state maximum absolute residual: `0`;
- plan endpoint: `right=0.0858 m`, `forward=4.7178 m` at `3 s`;
- iLQR action: acceleration `-0.4093 m/s²`, steering rate
  `0.01934 rad/s`;
- HUGSIM speed: `1.9157 → 1.8134 → 1.7111 m/s` over `0.5 s`;
- velocity and steering update residuals: `0`;
- termination/collision: none in the two-substep capability window;
- HUGSIM NC/TTC/PDMS evaluation: deliberately skipped.

Both writers sent exactly one plan, received the final `Done` handshake and
reported no exhaustion or repetition.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| A fully warmed SparseDrive plan can cross the audited FIFO/controller interface unchanged and produce the declared HUGSIM state update | `accepted` | one no-actor start state, one frozen plan and two 0.25 s substeps |
| The time-grid adapter avoids silent 4 Hz plan repetition | `accepted` | one 0.5 s action is explicitly held for two environment steps |
| The capability run is exactly reset-reproducible | `accepted` | two local runs; complete audit and writer summaries are byte-identical |
| SparseDrive reacts to new HUGSIM observations in closed loop | `rejected` | the replay writer ignores returned observation content |
| The resulting behavior is realistic or safe | `rejected` | no live feedback, matched real outcome or externally qualified behavior range |

Here `rejected` limits what this experiment may claim; it does not show that
the untested live capability fails.

## Inspectable artifacts

```text
artifacts/sparsedrive_plan_to_loop/capability-run001
artifacts/sparsedrive_plan_to_loop/capability-run002
artifacts/sparsedrive_plan_to_loop/analysis-run001/plan_to_loop_audit.json
artifacts/sparsedrive_plan_to_loop/analysis-run001/plan_to_loop_capability.png
```

## Next gate

Replace the replay writer with the frozen SparseDrive receiver:

1. independently reset and pre-warm it with the exact recorded `0.0, 0.5,
   1.0 s` history;
2. start HUGSIM from the matching `1.5 s` state;
3. infer from each newly returned six-camera observation every `0.5 s`;
4. keep the same two-substep control hold and fail on missing or repeated plans;
5. first run a short no-actor capability sequence without interpreting safety.

Only after this live normal-scene gate should the stronger/weaker conflict
closed-loop comparison be preregistered.
