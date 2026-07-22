# HUGSIM Ordinal Metamorphic Test Preregistration 001

Date: 2026-07-22

Status: `preregistered_not_run`

## Purpose and Scope

Prospectively test whether a controlled vehicle's task relation changes in the
expected direction when only longitudinal placement or lateral/corridor
placement changes. This is the first executable use of the task boundary in
`docs/hugsim_metric_evidence_map.md` section 12.

This is a prospective run manifest, not a blind preregistration: related 7 m,
12 m, 24 m, and 4 m-offset runs were already inspected before this design. The
new 16 m combinations, equal actor speed, full 2x2 matrix, exact hashes, and
decision rules below are frozen before any `ordinal_*_001` output is rendered.

The experiment targets **designed-range ordinal causal consistency**. It does
not estimate a real-world distribution or establish a calibrated danger
threshold.

## Frozen Inputs

- HUGSIM scene: `scene-0383`;
- HUGSIM commit: `adeca402cad4af8635e13d0a105e2fee6a14de85`;
- actor asset: `2024_07_05_15_57_10`, always `plan_list[0]`;
- actor controller: `ConstantPlanner`, yaw `0`, speed `1.0 m/s`;
- deterministic plan writer: horizon 6, step 1 m, 36 simulator steps;
- corrected control convention;
- receiver: frozen official Sparse4Dv3 R50, no HUGSIM fine-tuning;
- receiver commit: `249ffbb695f4e9db628d953e2bf6d36de04bbb69`;
- receiver score threshold: the previously frozen `0.2`;
- receiver input: HUGSIM six-camera RGB/intrinsics/extrinsics only; semantic and
  depth remain excluded.

Machine-readable paths, SHA-256 values, output directories, and rules are in
`docs/runs/hugsim_ordinal_metamorphic_preregistration_001.json`.

## Frozen 2x2 Design

The distances are **test-design levels**, not qualified safety margins.

| Condition | Right offset | Forward offset | Expected factor relation |
|---|---:|---:|---|
| `center_near` | 0 m | 16 m | closer and corridor-centred |
| `center_far` | 0 m | 24 m | farther and corridor-centred |
| `adjacent_near` | 4 m | 16 m | closer and right-adjacent |
| `adjacent_far` | 4 m | 24 m | farther and right-adjacent |

A new no-actor run is paired with the matrix to expose native/nuisance receiver
responses. No condition may reuse or overwrite an earlier output directory.

## Frozen Partial Order

Threat direction is defined only for this design as coordinate-wise movement
toward the ego and toward its deterministic swept-plan corridor. Before any
receiver result is considered, actual HUGSIM actor states must be independently
recomputed into oriented footprints and checked against the ego footprint and
swept candidate corridor.

Expected relations:

```text
center_near > center_far
center_near > adjacent_near
center_far > adjacent_far
adjacent_near > adjacent_far

center_far ? adjacent_near   # deliberately incomparable
```

The incomparable pair must remain unresolved; no weights may be introduced to
force a total order. Configured offsets are hypotheses, not evidence. If the
recorded trajectories do not preserve a contrast's intended longitudinal or
lateral relation, that contrast fails its geometry gate and receiver outputs
must not be used to rescue it.

## Frozen Receiver Checks

Sparse4Dv3 remains a supporting probe, not a truth source. Use the same class
set, frame stride, transform, and nearest-XY association procedure as the
existing receiver baseline, and report every association distance without a
new cutoff.

For every common receiver timestamp in the complete-future window:

- near versus far at fixed lateral placement should yield a smaller associated
  forward `x` for the near condition;
- centred versus adjacent at fixed forward placement should yield a smaller
  absolute lateral `y` for the centred condition;
- the no-actor run is reported separately and never associated with the
  injected actor;
- missing or ambiguous association is `unavailable`, not silently imputed;
- every opposite-sign comparison is a `reversal` and is retained.

The primary summary is the count of `expected`, `reversal`, and `unavailable`
paired timestamps for each predeclared contrast. Median relations may be shown
only as secondary summaries.

## Gates and Decision Rules

All five runs must finish 36/36 steps, preserve exact timestamp/ego/plan/action
pairing, and be evaluated only where every planned waypoint has a corresponding
future actor state. The horizon gate is fail-closed.

For each specific claim:

- `accepted`: geometry gate passes, every planned receiver timestamp is
  available, and the stated ordinal relation has zero reversals;
- `down-weighted`: geometry is valid and aggregate direction is expected, but
  one or more receiver timestamps are unavailable or reversed; preserve those
  frames as receiver/simulator-interface boundary evidence;
- `rejected`: the claimed relation is contradicted by the independently
  recomputed geometry, the aggregate receiver direction reverses, or the run
  identity/horizon gate fails.

A failure does not identify HUGSIM or Sparse4Dv3 as the sole cause. The result
must be localized to geometry/state, rendered observation, receiver response,
or unresolved shared dependence.

## Explicit Exclusion: Occlusion

Audit 001 does not manipulate occlusion. A synthetic pixel mask would test the
receiver preprocessing rather than HUGSIM, while a second vehicle would change
actor count and interaction structure. Natural visibility differences are
reported but cannot be called causal occlusion evidence. Occlusion becomes a
later factor only after an independently auditable intervention is specified.

## Stop Rules

- Do not inspect partial outputs and then alter positions, speed, threshold,
  frame range, association rule, or expected order.
- Stop after one complete five-run matrix, regardless of result.
- If a run terminates early, retain it as failed evidence and do not replace it
  under the same audit ID.
- If the manifest or configs change after publication, create audit 002 with
  new paths and hashes.

## Allowed and Forbidden Claims

Strongest allowed claim after a successful run:

> Within the declared 2x2 design range and complete-future window, the HUGSIM
> state intervention satisfies the independently recomputed geometric order,
> and the frozen Sparse4Dv3 probe preserves the predeclared longitudinal and
> lateral ordinal relations without reversal.

Still forbidden:

- 16 m, 24 m, or 4 m is a real-world safe/unsafe boundary;
- the actor motion is a realistic traffic policy;
- Sparse4Dv3 output is independent 3D truth;
- HUGSIM RGB is real-sensor equivalent;
- the result proves real AD action, collision risk, real-sim equivalence, or
  general HUGSIM fitness as an AD test domain.
