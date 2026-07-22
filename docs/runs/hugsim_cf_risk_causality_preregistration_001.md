# HUGSIM CF-R risk-causality preregistration 001

Date: 2026-07-22

Status: `preregistered_receiver_not_run`

## Scope

Test whether a dynamic conflict relation already established in saved HUGSIM
state survives transport through recorded six-camera RGB to the now-qualified
Sparse4Dv3 supporting receiver.

This reuses the completed CF-M `slow / nominal / fast` sequences. Their state
and rendered outputs have already been inspected, so the experiment is not
blind. What is prospective is the frozen Sparse4Dv3 run and the analysis of its
outputs. Exact input hashes and analysis rules are in the adjacent JSON file.

## Why this is new

The earlier 2x2 ordinal audit changed static longitudinal and lateral placement.
This audit instead holds the configured starting scene fixed and changes actor
speed. Because the deterministic ego closes faster on a slower lead actor, the
predeclared conflict-information order is:

```text
slow actor / highest closure
  > nominal actor / medium closure
  > fast actor / lowest closure
```

Here `>` means stronger relative conflict information in this designed range,
not a calibrated danger probability.

## Frozen checks

Only timestamps in `(0, 6.5] s` are valid. Timestamp zero is excluded because
the saved reset observation already contains the first speed-dependent actor
update.

State gate:

- actor forward distance: `slow < nominal < fast` at every valid timestamp;
- ego–actor footprint clearance: `slow < nominal < fast` at every valid
  timestamp.

Receiver checks:

- pairwise associated longitudinal order for `slow < nominal`,
  `nominal < fast`, and `slow < fast`;
- unavailable associations reported without imputation;
- within-run longitudinal closing steps, instance continuity, and fitted
  longitudinal slope;
- slope order `slow < nominal < fast`, where a more negative receiver slope
  indicates faster observed closure.

The receiver is the official Sparse4Dv3 R50 checkpoint at the frozen source
commit, using six RGB cameras and calibration only. HUGSIM semantic/depth and
HUGSIM NC/TTC/PDMS do not decide this experiment.

## Decision boundary

- `accepted`: the state gate passes, all planned receiver observations are
  available, and the relation has no reversal or tie;
- `down-weighted`: state is valid and aggregate receiver direction is expected,
  but observations are missing or individual reversals remain;
- `rejected`: state order, aggregate receiver direction, or an identity/horizon
  gate fails.

The metric receiver distance and slope are directional diagnostics, not
qualified physical distance or velocity. The strongest allowed conclusion is
limited to transport of dynamic ordinal task information. Planning, braking,
collision risk, real-sim equivalence, and closed-loop credibility remain
untested.
