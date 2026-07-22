# HUGSIM CF-R risk-causality design 001

Date: 2026-07-22

Status: `superseded_by_preregistration`

## Question

When current geometry is held fixed but future conflict evolution is changed,
does HUGSIM preserve the expected risk-information direction from declared
world state, through six-camera observation, to a qualified supporting
receiver?

The prior ordinal 2x2 audit changed distance and lateral placement. It already
tested static near/far and same/adjacent ordering, so CF-R must not repeat that
matrix. The genuinely new factor is **relative motion and time-to-conflict**.

## Smallest informative experiment

Reuse the completed CF-M sequences. They use one scene, one vehicle asset, one
fixed configured initial same-lane placement, the same deterministic ego plan,
and three actor motion conditions:

1. `slow` actor (0.5 m/s), producing the highest ego-closure rate;
2. `nominal` actor (1.0 m/s), producing medium closure;
3. `fast` actor (1.5 m/s), producing the lowest closure.

CF-M already established complete runs and strictly separated state clearance.
The RGB sequences therefore need not be rendered again. The new prospective
part is the frozen Sparse4Dv3 receiver output and CF-R analysis. Existing state
results have already been seen, so this is not a blind preregistration. The
levels remain test-design coverage, not real traffic or safety thresholds.

## Held-fixed conditions

- HUGSIM scene and checkpoint;
- actor asset, initial pose, size, and yaw;
- ego initial state and deterministic candidate plan;
- camera trajectory, render settings, duration, and valid future horizon;
- Sparse4Dv3 commit, checkpoint, preprocessing, score threshold, and frame
  cadence;
- analysis and association rules.

Only actor longitudinal motion changes. If a dry run reveals that another
quantity changes by configuration rather than causal evolution, the design
must be revised before preregistration.

## Three separated observation layers

### R1 — declared-state conflict evolution

Independently recompute from logged ego/actor footprints and the fixed ego
candidate corridor:

- positive net clearance over time;
- first corridor-conflict time, if present;
- closing/non-closing sign;
- valid future coverage.

Expected partial order is `closing_fast > closing_slow > receding_or_nonclosing`
only where all relevant quantities agree. Conflicting relations remain
unresolved; no weighted risk score is introduced.

### R2 — rendered observability

Check that the causal actor is present in the expected cameras and that missing
receiver output is not caused by an absent render. HUGSIM semantic/depth may be
used only for internal diagnosis, never as the risk judge. The rejected
RGB-versus-box localization tool is not reused.

### R3 — supporting-receiver transport

Run the frozen qualified Sparse4Dv3 contract and report:

- valid associated observations and unavailable observations;
- temporal instance continuity;
- receiver-derived longitudinal trend and closing/non-closing direction;
- whether every available comparison preserves the R1 partial order.

Sparse4Dv3 confidence is not treated as risk. Its metric distance and velocity
are diagnostics because absolute receiver geometry remains down-weighted.

## Decisions

For each relation:

- `accepted`: R1 validates the intended intervention; rendered actor support is
  present; every planned receiver observation is available; and the receiver
  direction has zero reversals;
- `down-weighted`: R1 is valid and aggregate receiver direction is expected,
  but observations are unavailable or the metric trend is too uncertain for
  every-timestamp acceptance;
- `rejected`: the logged intervention does not create the declared conflict
  order, the aggregate receiver direction reverses, or identity/horizon gates
  fail.

Missing observations are never counted as safe. HUGSIM NC/TTC/PDMS are shown
only as internal diagnostics and cannot rescue or reject the external relation.

## Allowed conclusion

> Within the frozen motion range, HUGSIM state produces the declared
> time-to-conflict order, and the qualified supporting receiver preserves (or
> fails to preserve) the corresponding risk-information direction in available
> six-camera observations.

This is not yet an AD risk judgment. A target risk/planning module is needed
before claiming that the system ranks a critical target or chooses braking or
avoidance correctly.

## Stop point and next gate

After one preregistered three-condition run, stop regardless of result. Do not
add scenes or tune receiver thresholds to turn a relation green.

If CF-R passes, the next experiment is a bounded target planning/control
direction test. If it fails, localize the failure to state intervention,
rendered observability, receiver transport, or unresolved shared dependence
before any closed-loop run. Closed-loop outcome validation remains required,
but is deliberately after this gate.
