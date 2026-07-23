# HUGSIM official-sample matched-pose audit 001

## Outcome

The official HUGSIM sample archive yielded real six-camera `scene-0383`
images and source metadata. The current released reconstruction was rendered
at the corresponding camera intrinsics and poses for source frame indices 4,
9 and 14. This is the first inspectable factual real-image versus HUGSIM-render
comparison in this repository.

It is a narrow image-level anchor, not yet a real-versus-sim AD equivalence
experiment.

## Source identity

- archive:
  `hyzhou404/HUGSIM/sample_data/data.zip`;
- archive size: `2,375,358,963` bytes;
- immutable response ETag:
  `5e54c7c7e3782c2ead7fd507d406b3d0e4b064963455a96e93959be0e21c1e9c`;
- provider-declared archive SHA-256:
  `e3cc670fcfffcb573c65d3d228d419f13087f6fc2a7d72aec1447aebacd0ff7d`;
- access: ZIP central directory and selected members through HTTP ranges;
- every extracted member was checked with ZIP CRC and a locally recorded
  SHA-256. The provider's full-archive SHA-256 was not independently
  recomputed because the complete 2.38 GB archive was not downloaded.

The source archive's `meta_data.json` hash is
`dfe176b9757c235664c9aa2eefcb6c006722e5ec7ff770495971a605b909dedd`.
The metadata distributed with the current XDimLab checkpoint has hash
`8ef9561d9b1bf6e9f563891603a5360da421930c88252e74e9ce2615be59df5d`.
They are not byte-identical and their camera poses differ slightly.

## Comparison

For each selected timestamp, the same real source image was compared with two
renders of the current checkpoint:

1. camera pose from the metadata distributed with the current checkpoint;
2. camera pose from the older official sample archive.

Both variants use the recorded per-camera intrinsics and the checkpoint's
native dynamic object. Metrics are descriptive image differences over the six
cameras; they are not credibility thresholds.

| Source frame | Metadata variant | Mean PSNR (dB) | Mean SSIM | Mean MAE |
|---:|---|---:|---:|---:|
| 4 | current checkpoint metadata | 24.755 | 0.761 | 0.0378 |
| 4 | sample-archive metadata | 22.492 | 0.675 | 0.0480 |
| 9 | current checkpoint metadata | 24.025 | 0.740 | 0.0388 |
| 9 | sample-archive metadata | 20.342 | 0.624 | 0.0589 |
| 14 | current checkpoint metadata | 21.918 | 0.661 | 0.0496 |
| 14 | sample-archive metadata | 19.323 | 0.550 | 0.0690 |

Across all 18 camera observations, the current-checkpoint metadata gives:

- mean PSNR `23.566 dB`;
- mean SSIM `0.721`;
- mean MAE `0.0420`;
- better PSNR than the sample-archive metadata in `17/18` camera cases.

This indicates that release-matched or optimized metadata materially affects
the comparison. It does not establish which metadata is closer to the physical
sensor pose.

## Evidence decisions

| Claim or finding | Decision | Boundary |
|---|---|---|
| Selected source images and metadata are inspectable members of the identified official sample archive | `accepted` | member CRC/SHA and archive identity are recorded; full-archive hash is provider-declared only |
| Current-checkpoint metadata produces lower image error than the older sample metadata in this comparison | `accepted` | a within-checkpoint diagnostic over 3 timestamps and 18 cameras |
| The current reconstruction has useful factual image agreement at these poses | `down-weighted` | visible and numeric agreement exists, but release pairing, pose provenance and task effect are unresolved |
| Pixel agreement proves sensor or AD-task equivalence | `rejected` | scope exceeds the experiment; no matched receiver output, task label or acceptance bound was tested |

The `rejected` item rejects only the stronger claim. It does not discard the
matched-pose images as research evidence.

## Important limitations

- Original nuScenes sample tokens and an independently audited ASAP conversion
  mapping are absent.
- The checkpoint split and source-archive release pairing are not independently
  established.
- Camera poses may include reconstruction optimization rather than untouched
  physical calibration.
- Only three timestamps were tested.
- `CAM_BACK` source images are `800x410`, while the other cameras are
  `800x450`; a receiver comparison must freeze one explicit crop/pad rule.
- PSNR, SSIM and MAE measure pixels, not vehicles, lanes, risk ordering or
  planning behavior.

## Artifacts

- frame 4:
  `artifacts/hugsim_matched_pose/scene-0383-frame00004-pose-audit-run001`;
- frame 9:
  `artifacts/hugsim_matched_pose/scene-0383-frame00009-pose-audit-run001`;
- frame 14:
  `artifacts/hugsim_matched_pose/scene-0383-frame00014-pose-audit-run001`;
- source members:
  `artifacts/hugsim_source_anchor/scene-0383-official-sample-*`;
- fetcher: `scripts/fetch_hugsim_sample_anchor.py`;
- renderer: `scripts/render_hugsim_exact_source_pose.py`.

The most direct visual is each run's `real_vs_pose_variants.png`.
