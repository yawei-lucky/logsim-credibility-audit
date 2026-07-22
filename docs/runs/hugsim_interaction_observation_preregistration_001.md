# CF-I-OBS-001 state-to-observation preregistration

## Purpose

Move the qualified CF-I planner state and causal timing one boundary forward:
into the six-camera rendered observation supplied to a receiver. This is not a
sensor-realism or AD-response experiment.

## Frozen window and controls

- Reuse the exact `CF-I-LOOP-001` aligned baseline and treatment traces.
- Render scene-0383 indices 6--11 and 14. These retain physical separation and
  independently project the responder into `CAM_BACK` only.
- Pair every actor render with an actor-free render at the same camera pose to
  isolate actor-caused RGB support.
- Treat the other five cameras as membership negatives.
- Add four synthetic instrument negatives: a one-step state association, a
  rotated camera label, a 200-pixel projection shift, and a two-frame-early
  observation timestamp label.
- Use neither HUGSIM semantic/depth nor an object detector for the decision.

The four indicators cover state-to-transform fidelity, camera membership,
projected RGB localization, and observation causal onset. Formal output stops
before an AD receiver if any indicator fails its frozen control discrimination.

Machine-readable preregistration:
`docs/runs/hugsim_interaction_observation_preregistration_001.json`.

## Claim boundary

At most this run can establish consistent transport from frozen HUGSIM planner
state into HUGSIM-rendered observations for one bounded rear-actor window. It
cannot establish real-camera equivalence, realistic traffic behavior, AD
response, or closed-loop credibility.
