# CF-I-OBS-003 asset-envelope attribution result

## Result

The final first-round CF-I localization split retained the same states, frames,
RGB pairs, 16-pixel dilation, 90% gate, and synthetic negatives. It replaced
only the `obj_boxes` projection with an independently derived Gaussian-asset
envelope and origin.

`CF-I-O3` remains `rejected`. Minimum RGB-support coverage improved from
`0.479` with the metadata box to `0.662` with the asset envelope, but did not
reach the frozen `0.90` gate. State-to-transform, camera membership, and causal
onset again remained `accepted`.

| Indicator | Decision | Main result |
|---|---|---|
| `CF-I-O1` state to transform | `accepted` | state and position error `0`; yaw error below `9e-16 rad` |
| `CF-I-O2` camera membership | `accepted` | 84/84 frame-camera rows matched; rotated-camera control rejected |
| `CF-I-O3` asset-envelope localization | `rejected` | minimum support coverage `0.662`; shifted-envelope maximum `0.308` |
| `CF-I-O4` causal observation onset | `accepted` | state cause at 8, qualified RGB divergence at 9; early label rejected at 6 |

Overall evidence remains `down-weighted` and the complete observation-transport
claim remains unqualified.

## Metadata box versus asset envelope

The asset envelope changes the pattern but does not make it uniformly valid:

| Frame | 6 | 7 | 8 | 9 | 10 | 11 | 14 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Metadata-box coverage | 0.983 | 0.961 | 0.920 | 0.874 | 0.824 | 0.770 | 0.479 |
| Asset-envelope coverage | 0.926 | 0.919 | 0.910 | 0.898 | 0.891 | 0.883 | 0.662 |

The asset envelope improves close-range coverage substantially, supporting the
finding that HUGSIM metadata dimensions and origin contribute to the mismatch.
It is slightly worse in the farther frames and still degrades with proximity,
so metadata geometry is not the only explanation.

The new envelope bounds Gaussian **centres** after an opacity and quantile
filter. Rendered Gaussian splats have spatial scale and covariance, and paired
RGB support can include their full rasterized footprint. Therefore this run
cannot distinguish a deeper renderer-projection inconsistency from an
insufficient centre-envelope definition. It does establish that neither the
released metadata box nor this simple asset-derived envelope qualifies as a
90%-coverage spatial truth instrument across the tested range.

No further opacity, quantile, dilation, or threshold tuning is performed in
this phase.

## First-round CF-I closure

CF-I now retains a bounded evidence set:

- positive evidence: exact state-to-transform transport, correct six-camera
  membership, and no rendered response before the declared state cause;
- negative evidence: released time-grid inconsistency, shared camera-state
  contamination in the original paired control, and failed precise RGB
  localization for both metadata and simple asset envelopes;
- capability boundaries: adversarial AttackPlanner behavior is not ordinary
  traffic behavior, RGB remains simulator-internal, spatial ground truth is
  unresolved, and no AD or real-world response has been tested.

This is enough to close the first internal CF-I audit without making every
indicator green. It does not qualify HUGSIM as an AD test world.

## Inspectable outputs

```text
docs/runs/hugsim_interaction_observation_indicators_003.json
artifacts/hugsim_interaction_observation/analysis-run003/interaction_observation_measurements.json
artifacts/hugsim_interaction_observation/analysis-run003/interaction_observation_summary.png
artifacts/hugsim_interaction_observation/analysis-run003/interaction_observation_cam_back_contact_sheet.png
```

## Next phase

Move to a bounded supporting-receiver qualification gate rather than adding
more CF-I scenes or tuning O3. Before using a camera-only AD receiver as a
credibility ruler, record its real-data qualification basis, input/calibration
compatibility, output semantics, failure modes, and strongest allowed claim.
The unresolved spatial-localization boundary must remain attached to any later
HUGSIM receiver result.
