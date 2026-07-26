# CF-R external following-boundary audit 001

Date: 2026-07-26

Formula preregistration commit: `7ee7ca3`

## Outcome

The external-boundary audit is overall `down-weighted`.

The external comparator is applicable to all `120/120` sampled planned states,
and every sampled longitudinal gap exceeds it. However, the current experiment
never reaches or crosses that boundary. It therefore supports a relative
response-direction claim, not a near-boundary safety-response claim.

This materially narrows the interpretation of CF-R:

> “stronger conflict” and “weaker conflict” are ordinal condition names. In
> the current run they do not mean unsafe versus safe under the selected
> external following-distance comparator.

## External reference and role

The comparator is [UN Regulation No. 157, Amendment
3](https://unece.org/sites/default/files/2023-02/R157am3e.pdf), clause
`5.2.3.3`, for M1/N1 Automated Lane Keeping Systems:

```text
d_min = v_ALKS × t_front
```

For speeds below `2 m/s`, the stated minimum following distance is never less
than `2 m`. Intermediate table values use linear interpolation.

This is an independently published regulatory engineering boundary. It is not
a universal criticality threshold, physical collision truth or a complete UN
R157 compliance test. The [criticality-metrics
review](https://doi.org/10.1007/s11831-022-09788-7) likewise cautions that
metric validity and pass/fail targets depend on the scenario, prediction model
and higher-level safety goal.

## Measurement

The prior complete-future audit was frozen and hashed before this analysis.
For every included future waypoint, the new audit independently recomputed:

- planned ego segment speed;
- ego and actor oriented footprints;
- lateral footprint overlap and whether the actor remains ahead;
- longitudinal bumper-to-bumper gap along planned ego heading;
- the corresponding UN R157 M1/N1 minimum following distance;
- `gap − minimum following distance`.

Euclidean footprint clearance was used only as a numerical cross-check. No
incomplete tail state, interpolation or actor-state repetition was added.

| Sample group | Count | Applicable | Minimum margin above comparator |
|---|---:|---:|---:|
| Shared constant-speed reference | `24` | `24` | `6.788596 m` |
| SparseDrive target-AD plans | `96` | `96` | `8.037772 m` |
| Total | `120` | `120` | `6.788596 m` |

Additional applicability checks:

- maximum planned segment speed: `1.975400 m/s`;
- minimum lateral footprint overlap: `0.878099 m`;
- maximum ego–actor heading difference: `3.036°`;
- minimum gap-to-boundary ratio: `4.394×`.

All samples were same-lane, actor-ahead and below `2 m/s`, so the comparator
was `2 m` throughout.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| The external formula is applicable to the fixed samples | `accepted` | `120/120` same-lane, actor-ahead samples inside the published speed range |
| Every sampled planned gap exceeds this comparator | `accepted` | minimum margin `6.788596 m`; no non-positive sample |
| The current experiment spans both sides of the external boundary | `rejected` | all `120` samples remain above the comparator |
| The current SparseDrive clearance increase validates near-boundary safety response | `rejected` | no near-boundary or below-boundary state was exercised |
| The result proves real-world safety or UN R157 compliance | `rejected` | one comparator and one simulated scenario are insufficient |

The overall audit is `down-weighted`: a useful external comparison was
successfully added, but it exposes a coverage gap rather than upgrading the
closed-loop result to safety-critical validity.

## Research consequence

The prior accepted result remains valid in its narrow form:

```text
stronger relative closure
  -> smaller held-path clearance
  -> larger SparseDrive clearance-increasing response
  -> different closed-loop outcome
```

The word “mitigation” must not be read as “required safety intervention.” The
sampled states were already far above the selected external following-distance
boundary.

The next CF-R experiment should be designed from an external boundary, not by
arbitrarily adding another actor speed:

1. choose one above-boundary, one near-boundary and one below-boundary initial
   gap under the same low-speed comparator;
2. keep scene, receiver, actor asset, horizon and control contract fixed;
3. first verify the intended bumper-gap relation and complete-future coverage;
4. then ask whether target-AD response ordering, mode and closed-loop outcome
   change across the boundary;
5. preserve the current far-boundary runs as a normal-response control.

That design can test whether the indicator detects a meaningful task boundary.
It still will not prove that UN R157 is the only correct real-world boundary.

## Inspectable artifacts

```text
artifacts/sparsedrive_cf_r_external_following_boundary/analysis-run002/cf_r_external_following_boundary_audit.json
artifacts/sparsedrive_cf_r_external_following_boundary/analysis-run002/cf_r_external_following_boundary_rows.csv
artifacts/sparsedrive_cf_r_external_following_boundary/analysis-run002/cf_r_external_following_boundary.png
```

Run 001 is retained as the first successful calculation. Run 002 changes only
the presentation layout and is the reviewed result.
