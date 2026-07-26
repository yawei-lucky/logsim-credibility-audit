# HUGSIM CF-R complete-future conflict instrument 001

Date: 2026-07-26

Formula preregistration commit: `058153c`

## Outcome

The complete-future dynamic-conflict instrument is `accepted` for its narrow
simulator-internal use.

This analysis does not ask whether “less forward progress means safer.” It
separates two different questions at the shared `t=1.5 s` handoff:

1. **stimulus conflict** — with one common straight constant-speed ego path,
   does the slower lead actor create less future footprint clearance?
2. **target-AD mitigation** — relative to that same non-reactive path, does
   SparseDrive's own plan add clearance, and is the added response larger for
   the stronger conflict?

The already completed runs were fixed before this analysis. Formulas,
valid-time rules and decisions were committed before the new values were
calculated. This is therefore a prospective analysis of fixed retrospective
data, not a fresh independent replication.

## Complete-future gate

Each SparseDrive plan contains six waypoints at `0.5 s` spacing, hence requires
actor states through `t + 3.0 s`.

| Item | Result |
|---|---:|
| Plans produced per run | `9` |
| Fully supported plan timestamps | `1.5, 2.0, 2.5, 3.0 s` |
| Included plans per run | `4/9` |
| Excluded incomplete timestamps | `3.5–5.5 s` |
| Exact actor states per included plan | `6` |
| Total checked plan–future pairs | `96` |
| Tail fill, interpolation or extrapolation | none |
| Shared-handoff ego-box residual | `0 m` |

The validity gate is `accepted`. The five late plans are not used to support
the result.

## 1. Common-path stimulus conflict

The reference ego path holds heading and the common handoff speed
`1.915686 m/s` constant. The ego path is therefore identical across both
conditions and all resets; only the recorded actor future differs.

| Minimum 3 s footprint clearance | Reset 1 | Reset 2 |
|---|---:|---:|
| Stronger conflict, actor `0.5 m/s` | `8.788596 m` | `8.788596 m` |
| Weaker conflict, actor `1.5 m/s` | `13.538596 m` | `13.538596 m` |
| Weak minus strong | `4.750000 m` | `4.750000 m` |

Same-condition repeat range was `0 m`. The preregistered strict order passed
both pairings and the condition effect exceeded repeat sensitivity. This
construct is `accepted`.

Interpretation: under the common non-reactive ego continuation, the designed
actor-speed histories produce the intended dynamic geometric conflict order.
It does not yet measure AD response or realistic risk magnitude.

## 2. SparseDrive mitigation response

All four plans selected native SparseDrive mode `3`, so this comparison is not
caused by a planning-mode switch.

| Added minimum clearance over common path | Reset 1 | Reset 2 |
|---|---:|---:|
| Stronger conflict | `1.351000 m` | `1.350996 m` |
| Weaker conflict | `0.695955 m` | `0.695955 m` |
| Strong minus weak response | `0.655045 m` | `0.655041 m` |

Every SparseDrive plan increased minimum clearance relative to the common
constant-speed continuation. The stronger-conflict mitigation effect exceeded
the weaker one in both pairings. The minimum condition effect was
`0.655041 m`, versus a maximum same-condition reset range of
`0.000004312 m`. This construct is `accepted`.

At the boundary, the strong-condition minimum clearance moved from
`8.788596 m` to about `10.139594 m`; the weak condition moved from
`13.538596 m` to about `14.234551 m`. None of the complete-horizon plans
reached zero footprint clearance.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| The logged plans have a complete, time-aligned 3 s actor future | `accepted` | first `4/9` plan timestamps in each of four retained runs |
| The designed strong/weak intervention preserves the expected conflict order under one common ego path | `accepted` | one scene, two accumulated actor-speed histories, HUGSIM state boxes |
| SparseDrive adds clearance and adds more for the stronger conflict beyond reset sensitivity | `accepted` | shared handoff, same selected mode, two resets per condition |
| Late-plan risk values obtained by repeating the final actor box are usable | `rejected` | timestamps `3.5–5.5 s` lack a complete 3 s actor future |
| The values are physical TTC, calibrated risk or realistic response magnitude | `rejected` | no independent state truth or external behavior range |
| This proves HUGSIM or SparseDrive is generally credible or safe | `rejected` | claim exceeds one simulator-internal scenario and receiver |

Here `rejected` limits those specific stronger claims; it does not negate the
accepted internal instrument result.

## What this adds

The earlier CF-R closed-loop audit showed that stronger conflict led to less
final progress, lower speed and smaller final state clearance. The present
audit adds a more defensible risk-causality decomposition:

```text
designed actor intervention
  -> conflict order under a held-common ego path
  -> SparseDrive plan adds a condition-dependent clearance response
  -> closed-loop vehicle outcomes
```

This removes two earlier ambiguities:

- a planning-mode change cannot explain the boundary result;
- actor motion is matched to every future waypoint instead of using a current
  static box or a repeated tail state.

It still uses HUGSIM's declared ego and actor boxes. Independent geometry and
real response magnitude remain external-validity requirements.

## External-boundary follow-up

The subsequent UN R157 M1/N1 following-distance comparison found that all
`120/120` complete-future samples were applicable but remained above the
external comparator. The closest margin was still `6.789 m`, or `4.39×` the
boundary distance. Therefore “mitigation” here means a clearance-increasing
response to stronger relative closure; it does not establish behavior at a
safety-critical boundary. See
`docs/runs/hugsim_cf_r_external_following_boundary_001.md`.

## Inspectable artifacts

```text
artifacts/sparsedrive_cf_r_future_conflict/analysis-run003/cf_r_future_conflict_audit.json
artifacts/sparsedrive_cf_r_future_conflict/analysis-run003/cf_r_future_conflict_rows.csv
artifacts/sparsedrive_cf_r_future_conflict/analysis-run003/cf_r_future_conflict_summary.png
```

Runs 001 and 002 are retained as successful development calculations. Run 003
uses the reviewed decision branch and is the presentation version; the
reported numerical values are unchanged.
