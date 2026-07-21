# HUGSIM Supplementary Scene Collection — Run 001

## Purpose

Collect two complementary normal-scene carriers for the current metric-audit
and evidence-map route. This is scene coverage, not a benchmark and not a
real-sim credibility comparison.

## Selection

The official public HUGSIM nuScenes asset directory exposed 19 scene archives
at collection time. Their released `meta_data.json` files were inspected before
full download to avoid choosing only by filename.

| Scene | Selection signal | Visual classification after rollout review | Intended audit use |
|---|---|---|---|
| `scene-0041` | about 86 degrees net reference-camera heading change; four released dynamic-model IDs | signalized intersection / cross street | intersection geometry, lane and signal semantics, cross-camera consistency |
| `scene-0138` | six released dynamic-model IDs and non-straight reference path | curved school-zone road with roadside objects, pedestrians, vegetation, and occlusion | small/roadside objects, occlusion boundaries, road semantics, rendering-artifact sensitivity |

The metadata count did **not** justify calling `scene-0138` a multi-car
interaction scene. The bounded receiver view does not show such an interaction,
and the current scenario has no injected actor plan.

## Asset integrity

| Scene | Local archive | SHA-256 |
|---|---|---|
| `scene-0041` | `/home/yawei/HUGSIM_assets/scenes/nuscenes/scene-0041.zip` | `8d066a3594ad5dc0f43944cff7ec1a5aa364011792236551e4802c483d0550fe` |
| `scene-0138` | `/home/yawei/HUGSIM_assets/scenes/nuscenes/scene-0138.zip` | `610853cf828787cbee5573ca4b30662100f1abcdd6c57833da1106b071ae7060` |

Both hashes match the official Hugging Face LFS object identifiers. Extracted
assets are under `/home/yawei/HUGSIM_assets/scenes/nuscenes/`.

## Bounded runs

Configs:

- `configs/hugsim/scenarios/scene-0041-easy-00.yaml`
- `configs/hugsim/scenarios/scene-0138-easy-00.yaml`

Outputs:

- `artifacts/hugsim_scene_collection/scene-0041-easy-00-run001-9s`
- `artifacts/hugsim_scene_collection/scene-0138-easy-00-run001-9s`

| Field | `scene-0041` | `scene-0138` |
|---|---:|---:|
| Completed steps | 36 | 36 |
| Duration | 9 s | 9 s |
| Receiver modalities | six-camera RGB / semantic / depth | six-camera RGB / semantic / depth |
| Injected actor boxes | 0 | 0 |
| Reported collision | false | false |
| HUGSIM NC / DAC / TTC / comfort / PDMS | 1.0 | 1.0 |
| HUGSIM RC / HDScore | 0.159509 | 0.181124 |

The HUGSIM scores only show that each bounded normal pipeline run completed
under the simulator's own scoring contract. They are not simulator-credibility
scores and are not reference evidence for RGB, semantic, or depth correctness.

## Direct visual findings

- `scene-0041` visibly approaches a signalized crossroad and therefore adds a
  material geometry/semantic condition absent from the original road segment.
- `scene-0138` visibly adds a curved road, school-zone markings, roadside
  people/objects, vegetation, and partial occlusion. Its value is not actor
  count but the different information demands placed on a camera receiver.
- Both scenes contain lateral-view blur, smearing, or reconstruction artifacts,
  especially around near-field vegetation and roadside regions. These are
  candidate negative/boundary evidence only after their task effect is tested;
  visual unattractiveness alone is not a credibility failure.

## Evidence judgment and limits

- `accepted`: official-asset integrity and reproducible completion of the two
  bounded normal runs.
- `down-weighted`: any inference about sensor or task realism, because all
  modalities come from HUGSIM and no independent real reference is available.
- No multi-car interaction, real-sim consistency, AD response, or global HUGSIM
  credibility claim is supported by these runs.

Each released package references 1080 RGB paths in metadata but does not include
the corresponding real RGB files or immutable nuScenes sample identity. The
Source Availability Gate therefore remains blocked for both scenes.

## Next use

Keep both scenes actor-free for the first audit pass:

1. On `scene-0041`, audit intersection geometry, traffic-signal/road semantics,
   and cross-camera consistency.
2. On `scene-0138`, audit occlusion boundaries, roadside/small-object behavior,
   school-zone road semantics, and whether vegetation artifacts alter a frozen
   receiver's output.
3. Add controlled actors only after the normal-scene measurements and claim
   boundaries are fixed.
