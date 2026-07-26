# SparseDrive static-control qualification 001

Date: 2026-07-26

## Outcome

The natural-actor experiment mechanically removed HUGSIM's native dynamic
render path, but that does not mean the target AD received an actor-absence
input. This post-hoc qualification audit checked SparseDrive's own explicit
perception output at the fully warmed frame `44`.

The current static control is `rejected` for the specific claim
“selected-actor absence for SparseDrive.” A rank-2 pedestrian hypothesis
persists near the source-declared actor locus in both factual and static
conditions, with nearly identical position and score.

This rejects the control, not HUGSIM as a whole. The complete audit remains
`down-weighted` because the association uses source/HUGSIM-declared geometry,
only the ten retained highest-scoring detections, one actor and one endpoint,
and was designed after observing the planning result.

## Receiver-space result

The source-declared actor center was transformed through the same provisional
model-to-camera calibration used by the frozen receiver:

```text
model xyz = [-5.739, 2.244, -0.765] m
```

SparseDrive label `8` is `pedestrian` in the pinned Stage2 config.

| RGB condition | nearest pedestrian rank | score | XY distance to declared actor |
|---|---:|---:|---:|
| real source | `2` | `0.7247` | `0.612 m` |
| HUGSIM factual | `2` | `0.6401` | `1.703 m` |
| HUGSIM static control | `2` | `0.6396` | `1.736 m` |

Across all `2 × 2` factual/static reset pairings:

- pedestrian-center separation: `0.048571–0.048573 m`;
- absolute score difference: `0.000508–0.000509`;
- the largest same-condition reset position variation was
  `2.57 × 10⁻⁶ m`;
- the largest same-condition score variation was `1.19 × 10⁻⁶`.

The factual and static hypotheses are therefore distinct beyond numerical
repeat, but both conditions retain the same high-ranking explicit pedestrian
response at essentially the same locus. This is not an
appearance-versus-disappearance intervention.

Meanwhile the factual/static final-plan ADE was `0.0947 m`. SparseDrive's plan
changed even though its explicit nearby pedestrian hypothesis did not appear
or disappear. The planning response may use latent visual features or other
scene outputs; it cannot be attributed to a new explicit pedestrian detection.

## Asset-availability gate

The paired `scene-0383` source metadata contains:

- `180` six-camera timestamps;
- only one native dynamic identity;
- that identity in all six cameras for `175` timestamps;
- five empty-dynamic tail timestamps, `175–179`.

The empty tail changes time and camera pose and is not a matched same-pose
background reference. The other local reconstructions, `scene-0041` and
`scene-0138`, contain dynamic checkpoints but no paired source RGB. The
current assets therefore do not provide a second matched object or a clean
same-pose actor-free source observation.

The clean-control generality branch is unavailable with current data. This is
an availability boundary, not a reason to manufacture a result from nearby
frames.

## Evidence decisions

| Claim | Decision | Boundary |
|---|---|---|
| A high-ranking pedestrian output persists in factual and static inputs near the declared locus | `accepted` | rank `2` in both resets; one endpoint and provisional geometry |
| The static-control target response is repeat-stable | `accepted` | position/score repeat variations at micro-scale |
| The static input qualifies as selected-actor absence for SparseDrive | `rejected` | the same explicit pedestrian-class response persists |
| The plan effect is caused by appearance/disappearance of a new explicit pedestrian detection | `rejected` | no explicit target appearance/disappearance occurred |
| This identifies a general HUGSIM renderer defect or proves SparseDrive correct | `rejected` | causal mechanism and external truth remain unresolved |

## Artifacts

```text
scripts/audit_sparsedrive_static_control.py
artifacts/sparsedrive_static_control_qualification/scene-0383-frame00044-run002
```

Primary inspection files:

- `sparsedrive_static_control_qualification.png`: real/factual/static crops,
  source-mask outline, nearest pedestrian positions and scores;
- `sparsedrive_static_control_qualification.json`: both resets, association
  margins, asset inventory and evidence boundaries.

## Research consequence

The prior natural-actor bridge keeps its narrow positive result: the native
dynamic contribution reaches the target AD and changes its plan beyond repeat
sensitivity. It cannot be interpreted as a clean actor-removal causal effect,
because the negative control did not isolate actor absence.

Do not continue this branch by selecting nearby timestamps. The next reusable
instrument should instead enforce complete time-aligned ego and actor futures
before computing path conflict, future footprint clearance or risk ordering.
