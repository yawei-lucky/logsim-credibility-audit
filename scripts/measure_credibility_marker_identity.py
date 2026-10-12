"""Read controlled marker identity from RGB contrast, without truth locations."""

from __future__ import annotations

import cv2
import numpy as np


def measure_tagged_pair(bright, dim, cfg):
    if bright.shape != dim.shape or bright.ndim != 3 or bright.shape[2] != 3:
        raise ValueError("paired RGB shape mismatch")
    delta = np.abs(bright.astype(np.float64) - dim.astype(np.float64))
    weights = delta.mean(axis=2)
    mask = (weights > cfg["difference_threshold_u8"]).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    features = []
    for component in range(1, count):
        x, y, width, height, area = stats[component]
        if area < cfg["min_component_area_px"]:
            continue
        if x == 0 or y == 0 or x + width == mask.shape[1] or y + height == mask.shape[0]:
            raise ValueError("marker touches image boundary")
        yy, xx = np.nonzero(labels == component)
        mass = weights[yy, xx]
        channel_mass = delta[yy, xx].sum(axis=0)
        fractions = channel_mass / channel_mass.sum()
        candidates = [identity for identity, channel in cfg["identity_channels"].items()
                      if fractions[channel] >= cfg["identity_min_channel_fraction"]]
        identity = candidates[0] if len(candidates) == 1 else None
        features.append({"u": float(np.average(xx + 0.5, weights=mass)),
                         "v": float(np.average(yy + 0.5, weights=mass)),
                         "area_px": int(area), "identity": identity,
                         "channel_fractions_rgb": fractions.tolist()})
    features.sort(key=lambda feature: feature["u"])
    width_px = None
    if len(features) == 2:
        width_px = features[1]["u"] - features[0]["u"]
        if not np.isfinite(width_px) or width_px <= 2 * cfg["width_error_bound_px"]:
            raise ValueError("invalid or unresolved marker separation")
    return {"features": features, "visible_marker_count": len(features), "width_px": width_px,
            "identities_qualified": all(feature["identity"] is not None for feature in features)}


def synthetic_tagged_pair(background, centres, bright_colours, dim_colours,
                          sigma, opacity, mixing=None):
    """Independent 2D rasterization from literal centres and RGB values."""
    yy, xx = np.indices(background.shape[:2], dtype=np.float64)
    images = []
    for colours in (bright_colours, dim_colours):
        image = background.astype(np.float64).copy()
        for (u, v), colour in zip(centres, colours, strict=True):
            alpha = opacity * np.exp(-((xx + 0.5 - u)**2 + (yy + 0.5 - v)**2) / (2 * sigma**2))
            colour = np.asarray(colour, dtype=np.float64)
            if mixing is not None:
                colour = np.asarray(mixing) @ colour
            image = image * (1 - alpha[..., None]) + 255 * colour * alpha[..., None]
        images.append(np.rint(image).clip(0, 255).astype(np.uint8))
    return images
