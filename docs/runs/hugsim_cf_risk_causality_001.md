# HUGSIM CF-R risk-causality audit 001

Date: 2026-07-22

Preregistration commit: `12f7f19`

## Outcome

Overall segment: `down-weighted`.

The experiment establishes a bounded positive result: the relative-conflict
order in HUGSIM state is clear, and the frozen Sparse4Dv3 receiver preserves
the aggregate dynamic order. It also establishes a useful boundary: the
receiver is not perfectly monotonic at every 0.5-second observation and cannot
resolve the smallest early contrast under the frozen zero-reversal rule.

## State gate

Only the complete-future window `(0, 6.5] s` is used. Both independently
recomputed orders pass at all 26 simulator timestamps:

| State relation | Expected | Reversal/tie | Minimum adjacent margin | Decision |
|---|---:|---:|---:|---|
| actor forward: `slow < nominal < fast` | 26 | 0 | 0.25 m | `accepted` |
| ego–actor footprint clearance: `slow < nominal < fast` | 26 | 0 | 0.25 m | `accepted` |

In this design, a slower lead actor produces faster ego closure. Therefore the
declared risk-information order is `slow > nominal > fast`. This is a designed
relative-conflict order, not a real danger threshold.

## Supporting receiver result

The frozen nearest-qualified association rule produced an available match at
all 13 valid receiver timestamps in all three conditions. This rule uses
HUGSIM actor state to select the nearest receiver prediction; it does not show
that an AD system autonomously selected the critical object. No missing result
was imputed.

| Receiver relation | Expected | Reversal/tie | Unavailable | Minimum margin | Decision |
|---|---:|---:|---:|---:|---|
| `slow > nominal` | 12 | 1 | 0 | -0.0216 m | `down-weighted` |
| `nominal > fast` | 13 | 0 | 0 | 0.2994 m | `accepted` |
| `slow > fast` | 13 | 0 | 0 | 0.2778 m | `accepted` |

The only pairwise reversal occurs at `t=0.5 s`: Sparse4Dv3 places `slow` about
2.16 cm farther forward than `nominal`, despite the state order. The frozen
rule has no tolerance, so this result remains a reversal. It is not assigned to
HUGSIM alone: receiver jitter, rendering/domain shift, and calibration
adaptation remain shared explanations.

The fitted receiver longitudinal slopes are:

| Condition | Receiver x slope | Closing steps | Non-closing steps | Dominant instance fraction |
|---|---:|---:|---:|---:|
| `slow` | -1.474 m/s | 11 | 1 | 1.00 |
| `nominal` | -0.793 m/s | 10 | 2 | 1.00 |
| `fast` | -0.204 m/s | 8 | 4 | 1.00 |

The `1.00` identity fraction applies within each independent run only; it does
not establish cross-run identity equivalence.

Thus the aggregate fitted ego-frame x-trend order `slow < nominal < fast` is
`accepted` as a narrow directional diagnostic. It is computed from the same
receiver positions as the pairwise order, so it is not independent evidence
and does not show that Sparse4Dv3 estimated physical actor speed correctly.
The stronger claim that every receiver step
faithfully reports closing is `rejected`: all three traces contain at least one
non-closing step while state clearance decreases. This is receiver-transport
boundary evidence, not proof of a HUGSIM defect or a calibrated velocity error.

The rejected every-step claim has rejection basis
`contradicted_by_evidence`. Its linked diagnostic finding `CF-R-D1` is
`down-weighted`: the receiver-transport component was exercised; monotonic
state closure was expected to remain directionally visible, but 1/2/4
non-closing receiver steps were observed. The mismatch is real in this output,
while attribution among receiver jitter, rendering/domain shift, and calibration
adaptation remains unresolved.

## What this adds to the research

The prior 2x2 audit established static near/far and lane ordering. CF-R 001
adds temporal conflict evolution:

```text
HUGSIM state: stronger closure relation
  -> six-camera RGB: frozen association remains available
  -> supporting receiver: aggregate closure hierarchy retained
  -> frame-level receiver metric: small reversals remain
```

The resulting candidate indicator should therefore report both:

1. persistent/aggregate risk-information direction; and
2. per-timestamp reversals and unavailable coverage.

It must not silently average away reversals, but a single tiny reversal also
must not be mislabeled as global simulator failure. No numerical tolerance is
derived from this HUGSIM run.

## Strongest supported statement

> Within the reused 0.5/1.0/1.5 m/s design range and complete-future window,
> HUGSIM state preserves the declared relative-conflict order; the frozen
> Sparse4Dv3 supporting receiver preserves the aggregate longitudinal closure
> hierarchy and 38/39 paired receiver comparisons, while one early small-margin
> reversal and several within-trace steps expose a receiver-transport stability
> boundary.

Not established: physical TTC, calibrated risk, braking need, target AD
planning/control response, real-sim equivalence, closed-loop credibility, or
general HUGSIM fitness as an AD test domain.

## Inspectable artifacts

```text
artifacts/hugsim_cf_risk_causality/sparse4d-run001/manifest.json
artifacts/hugsim_cf_risk_causality/analysis-run001/cf_risk_causality_audit.json
artifacts/hugsim_cf_risk_causality/analysis-run001/cf_risk_causality_summary.png
artifacts/hugsim_cf_risk_causality/analysis-run001/cf_risk_receiver_contact_sheet.png
artifacts/hugsim_cf_risk_causality/analysis-run001/cf_risk_receiver_comparison.mp4
```

The summary plot contrasts exact state clearance with receiver longitudinal
response. The contact sheet and video show the raw `CAM_FRONT` arrays supplied
to Sparse4Dv3 and only the associated receiver box.

## Stop rule and next boundary

The preregistered three-condition audit stops here. No threshold, speed, frame
window, or association rule is tuned to remove the reversal.

Independent post-run review found two automation gaps: the frozen analysis did
not automatically fail on a missing whole receiver timestamp and did not check
every recorded receiver-contract field. Manual review confirmed that the
current three runs contain the complete 13-timestamp sets and match the frozen
runner, source, checkpoint, threshold, camera order, modalities, and source
paths, so the result is unchanged. The analysis and receiver code are hardened
for future audits; this historical run remains tied to preregistration commit
`12f7f19` and is not recomputed under revised rules.

The next stage is not another Sparse4Dv3 curve. It is to qualify a target
risk/planning/control receiver whose outputs actually include critical-object
ranking or action, then test whether the retained conflict direction changes
that output. Closed-loop outcome validation follows only after that gate.
