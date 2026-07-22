# CF-I-OBS-002 corrective preregistration

CF-I-OBS-001 correctly stopped because its paired actor-free RGB control was
not actor-free. HUGSIM `Camera` instances share the mutable default
`dynamics={}`, and the renderer writes planned actors into that dictionary in
place. After an actor render, the following nominal no-actor render therefore
retained the vehicle and produced zero paired difference.

This is a measurement-chain failure, not evidence that the visible vehicle was
missing: the saved raw `CAM_BACK` inputs visibly contain it.

CF-I-OBS-002 changes only one operation: clear that shared camera-dynamics
dictionary immediately before each member of the paired render. It retains the
same source states, frame indices, camera expectations, RGB thresholds,
synthetic negatives, and claim boundary. Run001 remains preserved as negative
method evidence and is not overwritten.

Machine-readable preregistration:
`docs/runs/hugsim_interaction_observation_preregistration_002.json`.
