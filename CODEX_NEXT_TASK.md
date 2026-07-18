# Codex Next Task — Map the HUGSIM Relation Boundary

> Read this file first when resuming HUGSIM work.

## Current Result

The project has moved beyond a smoke test.

Completed on 2026-07-18:

```text
released HUGSIM control conversion
→ confounded background collision identified
→ corrected and unit-tested coordinate adapter
→ 5-second synchronized no-actor baseline
→ 5-second same-lane stationary-actor treatment
→ 5-second adjacent-lane actor negative control
→ RGB / semantic / depth counterfactual analysis
→ relation-specific credibility judgment
```

Primary record:

```text
docs/runs/hugsim_counterfactual_001.md
docs/runs/hugsim_counterfactual_001_audit.json
```

Narrow judgment:

```text
accepted
```

Accepted claim:

> In this scene and segment, the same-lane stationary actor is consistently
> supported by RGB, semantic, depth, internal geometry, and temporal evidence,
> and HUGSIM's planned-path TTC/NC metrics respond to that relation. The same
> actor at 3.5 m lateral offset does not trigger those failures.

Not accepted:

- an actual collision occurred;
- an AD agent responded credibly;
- HUGSIM is globally credible.

## Important Control Finding

HUGSIM commit `adeca402cad4af8635e13d0a105e2fee6a14de85` swaps
`[right, forward]` planner positions to `[forward, lateral]` for iLQR but
calculates heading using the pre-swap axes.

For the deterministic straight plan this creates an approximately 90° heading
target, saturated steering, and a background collision. No-actor and actor
runs fail identically, so that earlier pair is `rejected` as actor-event
evidence.

Use:

```text
scripts/hugsim_control_adapter.py
--control-convention corrected
```

Keep `--control-convention upstream` only for reproduction and regression
comparison.

## Current Assets and Outputs

```text
HUGSIM repo: /home/yawei/HUGSIM
HUGSIM commit: adeca402cad4af8635e13d0a105e2fee6a14de85
scene: /home/yawei/HUGSIM_assets/scenes/nuscenes/scene-0383
vehicle: /home/yawei/HUGSIM_assets/3DRealCar/2024_07_05_15_57_10
```

Successful paired outputs:

```text
artifacts/hugsim_contrast/scene-0383-easy-00-run003-corrected
artifacts/hugsim_contrast/scene-0383-medium-00-run002-corrected
artifacts/hugsim_contrast/scene-0383-adjacent-static-00-run001-corrected
artifacts/hugsim_contrast/scene-0383-counterfactual-report-run002
```

## Next Material Experiment

Map a small, bounded **relation boundary**.

Keep fixed:

- scene and vehicle asset;
- ego initial state;
- corrected deterministic ego plan;
- 20-step duration;
- actor controller and orientation.

Vary only a small set of actor placements:

```text
lateral offset: selected values between same-lane 0.0 m and safe 3.5 m
longitudinal distance: one nearer and one farther value around 15.0 m
```

Questions:

1. At what geometry does TTC first change?
2. At what geometry does NC first change?
3. Are transition times monotonic with longitudinal distance?
4. Does the lateral boundary agree with actual box/path intersection?
5. Do RGB, semantic, depth, and geometry stay consistent near the boundary?
6. Is any metric transition caused by reconstruction support or control
   artifacts rather than the intended relation?

This is not a full benchmark sweep. Select only enough placements to test the
boundary and monotonicity.

## Required Outputs

- one table of placement, actual clearance, first TTC failure, first NC
  failure, PDMS, and HDScore;
- one geometry-versus-metric transition plot;
- synchronized event-region RGB / semantic / depth evidence for at least one
  safe and one unsafe near-boundary placement;
- one compact audit JSON;
- per-segment `accepted`, `down-weighted`, or `rejected` labels.

## Guardrails

Do not:

- return to an unpaired “just run longer” experiment;
- use the released control convention as the primary result;
- report planned-path NC/TTC failure as an actual collision;
- install UniAD / VAD / LTF without explicit direction;
- run the full HUGSIM benchmark;
- expand to OmniDreams / Cosmos;
- define a final credibility score from this one scene;
- overwrite any successful output.

## Success Criterion

The next experiment is successful if it can explain whether HUGSIM's risk
transition follows the intended spatial relation and where that statement
stops being credible. A larger number of unevaluated runs is not success.
