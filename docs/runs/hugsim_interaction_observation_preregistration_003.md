# CF-I-OBS-003 asset-envelope split preregistration

CF-I-OBS-002 permanently retains its rejected claim: HUGSIM `obj_boxes` plus
the frozen 16-pixel tolerance did not localize at least 90% of actor-caused RGB
support across the selected distance range.

This final first-round CF-I test asks a different question. It derives an
internal rendering envelope directly from the vehicle Gaussian asset:

- retain points with opacity at least `0.5`;
- use per-axis quantiles `0.005` and `0.995`;
- preserve the resulting local center offset;
- transform that envelope with the exact planner body-to-world matrix.

Every source state, frame, camera, RGB threshold, 16-pixel dilation, 90% gate,
and synthetic negative remains unchanged. A pass attributes the bounded O3
failure to metadata-box geometry; a failure indicates a deeper projection
problem or an unqualified asset-envelope definition. Neither result upgrades
the envelope to external real-vehicle truth.

After this run, first-round CF-I closes without further threshold or envelope
tuning.
