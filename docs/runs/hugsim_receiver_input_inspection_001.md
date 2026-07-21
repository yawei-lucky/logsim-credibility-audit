# HUGSIM Receiver Input Inspection 001

Date: 2026-07-21

## Question

Does the human-inspectable HUGSIM image come from the same raw camera array consumed by the frozen RGB detector?

## Inspected Input

```text
source run: artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s
observation: observations.pkl[36]
timestamp: 9.0 s
camera: CAM_FRONT
shape: 450 x 800 x 3
dtype: uint8
```

The detector implementation reads this array and applies `torchvision.transforms.functional.to_tensor` before inference. The inspection PNG is saved directly from the same array without detection overlays.

## Artifacts

```text
artifacts/hugsim_receiver_input/scene-0383-camera-input-inspection-run001/no_actor_frame036_cam_front_raw.png
artifacts/hugsim_receiver_input/scene-0383-camera-input-inspection-run001/receiver_input_manifest.json
```

The manifest records the raw pixel-array SHA256. The PNG is a lossless encoding of the same pixel values.

## Interpretation

This establishes only the input-path identity for this frozen single-camera detector run: the displayed raw image and detector input originate from the same HUGSIM observation array. It does not establish that the RGB content is realistic, that semantic/depth outputs are correct, or that a six-camera/full AD receiver has the same input contract.
