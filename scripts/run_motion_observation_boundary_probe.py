#!/usr/bin/env python3
"""Probe where the equal-depth image-width model stops being applicable."""

from __future__ import annotations

import argparse
import itertools
import json
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from run_motion_observation_probe import (
    HugsimProbe,
    git,
    measure_pair,
    save_json,
    sha256,
    synthetic_pair,
    write_rgb,
)

ROOT = Path(__file__).resolve().parents[1]
SH_C0 = 0.28209479177387814


def marker_points(condition, separation_m):
    half = separation_m / 2
    kind = condition["kind"]
    if kind in {"equal_depth", "missing", "occlusion"}:
        return np.array([[-half, 0, 0], [half, 0, 0]], dtype=np.float64)
    if kind == "rigid_yaw":
        angle = np.deg2rad(condition["yaw_deg"])
        source_x = np.array([-half, half])
        points = np.column_stack(
            [source_x * np.cos(angle), np.zeros(2), -source_x * np.sin(angle)]
        )
        points[:, 0] += condition.get("center_x_m", 0.0)
        return points
    if kind == "depth_skew":
        skew = condition["half_depth_skew_m"]
        return np.array([[-half, 0, -skew], [half, 0, skew]], dtype=np.float64)
    raise ValueError(f"unknown condition kind: {kind}")


def project_width(points, center_depth_m, intrinsics):
    camera = np.asarray(points, dtype=np.float64) + np.array([0, 0, center_depth_m])
    if np.any(camera[:, 2] <= 0):
        raise ValueError("marker is behind the camera")
    matrix = np.asarray(intrinsics, dtype=np.float64)[:3, :3]
    image = (matrix @ camera.T).T
    uv = image[:, :2] / image[:, 2:3]
    return float(abs(uv[1, 0] - uv[0, 0])), uv


def common_depth_width(points, center_depth_m, intrinsics):
    """Project horizontal endpoint separation while forcing a common depth."""
    fx = np.asarray(intrinsics, dtype=np.float64)[0, 0]
    return float(fx * abs(points[1, 0] - points[0, 0]) / center_depth_m)


def roundtrip_render_camera_points(points, center_depth_m, c2w):
    """Independently reconstruct camera coordinates produced by the B2W pose."""
    c2w = np.asarray(c2w, dtype=np.float64)
    pose = c2w.copy()
    pose[:3, 3] += c2w[:3, :3] @ np.array([0, 0, center_depth_m])
    local = np.column_stack([np.asarray(points), np.ones(len(points))])
    world = (pose @ local.T).T
    camera = (np.linalg.inv(c2w) @ world.T).T
    return camera[:, :3] / camera[:, 3:4]


def is_single_marker_failure(message):
    return message == "expected exactly two visible markers, found 1"


def occluder_point(points, center_depth_m, condition):
    offset = condition["occluder_depth_offset_m"]
    target = np.asarray(points[0], dtype=np.float64) + np.array([0, 0, center_depth_m])
    occluder_z = target[2] + offset
    if occluder_z <= 0 or offset == 0:
        raise ValueError("occluder must be in front of the camera and offset from target")
    scale = occluder_z / target[2]
    camera = np.array([target[0] * scale, target[1] * scale, occluder_z])
    return camera - np.array([0, 0, center_depth_m])


def synthetic_pair_variable_sigma(background, centres, sigmas, opacity, levels):
    yy, xx = np.indices(background.shape[:2], dtype=np.float64)
    alpha = np.zeros_like(xx)
    for (u, v), sigma in zip(centres, sigmas, strict=True):
        alpha += opacity * np.exp(
            -((xx + 0.5 - u) ** 2 + (yy + 0.5 - v) ** 2) / (2 * sigma**2)
        )
    alpha = np.clip(alpha, 0, 1)[..., None]
    return [
        np.rint(background * (1 - alpha) + 255 * level * alpha).astype(np.uint8)
        for level in levels
    ]


def qualify_measurement(cfg, output, camera_record):
    height, width = camera_record["height"], camera_record["width"]
    yy, xx = np.indices((height, width))
    texture = np.stack(
        [35 + (xx % 41), 55 + (yy % 37), 45 + ((xx + yy) % 43)], axis=-1
    ).astype(np.uint8)
    black = np.zeros_like(texture)
    rows = []
    q = cfg["qualification"]
    for bg_id, background in [("black", black), ("texture", texture)]:
        for marker_width, phase, sigma, opacity in itertools.product(
            q["widths_px"], q["phases_px"], q["sigmas_px"], q["opacities"]
        ):
            centres = [
                (400 + phase - marker_width / 2, 225.3),
                (400 + phase + marker_width / 2, 225.3),
            ]
            pair = synthetic_pair(
                background, centres, sigma, opacity, cfg["contrast_levels"]
            )
            measured = measure_pair(*pair, cfg)
            rows.append(
                {
                    "background": bg_id,
                    "width_px": marker_width,
                    "phase_px": phase,
                    "sigma_px": sigma,
                    "opacity": opacity,
                    "error_px": measured["width_px"] - marker_width,
                }
            )
    negatives = {}
    negative_failures = {}
    for name, centres in {
        "single_marker": [(400, 225)],
        "three_markers": [(360, 225), (400, 225), (440, 225)],
        "boundary_marker": [(0.5, 225), (400, 225)],
    }.items():
        pair = synthetic_pair(texture, centres, 1.2, 0.9, cfg["contrast_levels"])
        try:
            measure_pair(*pair, cfg)
            negatives[name] = False
            negative_failures[name] = None
        except ValueError as error:
            negative_failures[name] = str(error)
            if name == "single_marker":
                negatives[name] = is_single_marker_failure(str(error))
            elif name == "three_markers":
                negatives[name] = str(error) == (
                    "expected exactly two visible markers, found 3"
                )
            else:
                negatives[name] = str(error) == "marker touches image boundary"
    geometry_rows = []
    intrinsics = camera_record["intrinsics"]
    fx = intrinsics[0][0]
    for bg_id, background in [("black", black), ("texture", texture)]:
        for condition, center_depth in itertools.product(
            [
                row
                for row in cfg["conditions"]
                if row["kind"] in {"equal_depth", "rigid_yaw", "depth_skew"}
            ],
            cfg["center_depths_m"],
        ):
            points = marker_points(condition, cfg["marker_separation_m"])
            predicted, uv = project_width(points, center_depth, intrinsics)
            sigmas = [
                fx * cfg["marker_sigma_m"] / (center_depth + point[2])
                for point in points
            ]
            pair = synthetic_pair_variable_sigma(
                background,
                uv,
                sigmas,
                cfg["marker_opacity"],
                cfg["contrast_levels"],
            )
            measured = measure_pair(*pair, cfg)
            geometry_rows.append(
                {
                    "background": bg_id,
                    "condition": condition["id"],
                    "center_depth_m": center_depth,
                    "projected_sigma_px": sigmas,
                    "predicted_width_px": predicted,
                    "error_px": measured["width_px"] - predicted,
                }
            )
    maximum = max(
        abs(row["error_px"]) for row in rows + geometry_rows
    )
    result = {
        "case_count": len(rows) + len(geometry_rows),
        "generic_case_count": len(rows),
        "geometry_case_count": len(geometry_rows),
        "max_abs_width_error_px": maximum,
        "design_budget_px": cfg["width_error_bound_px"],
        "negative_controls_detected": negatives,
        "negative_control_failures": negative_failures,
        "qualified": maximum <= cfg["width_error_bound_px"] and all(negatives.values()),
        "scope": "finite synthetic grid spanning the projected marker sizes in this experiment",
        "rows": rows,
        "geometry_rows": geometry_rows,
    }
    save_json(output / "measurement_qualification.json", result)
    if not result["qualified"]:
        raise ValueError("measurement qualification failed before GPU rendering")
    return result


class BoundaryProbe:
    def __init__(self, cfg, camera_record):
        self.base = HugsimProbe(cfg, camera_record)
        import torch

        self.cfg = cfg
        self.torch = torch
        dimension = self.base.scene.get_3D_features.shape[1]
        sh_degree = self.base.scene.max_sh_degree
        GaussianModel = type(self.base.scene)
        occluder = GaussianModel(sh_degree, affine=False)
        occluder.active_sh_degree = self.base.scene.active_sh_degree
        occluder._xyz = torch.zeros((1, 3), device="cuda")
        occluder._features_dc = torch.full(
            (1, 1, 3), (cfg["occluder_level"] - 0.5) / SH_C0, device="cuda"
        )
        occluder._features_rest = torch.zeros(
            (1, (sh_degree + 1) ** 2 - 1, 3), device="cuda"
        )
        occluder._feats3D = torch.zeros((1, dimension), device="cuda")
        occluder._scaling = torch.full(
            (1, 3), float(np.log(cfg["occluder_sigma_m"])), device="cuda"
        )
        occluder._rotation = torch.zeros((1, 4), device="cuda")
        occluder._rotation[:, 0] = 1
        opacity = cfg["occluder_opacity"]
        occluder._opacity = torch.full(
            (1, 1), float(np.log(opacity / (1 - opacity))), device="cuda"
        )
        self.occluder = occluder

    def render_pair(
        self, context, center_depth_m, points, occluder=None, missing_index=None
    ):
        torch = self.torch
        self.base.marker._xyz[:] = torch.tensor(points, dtype=torch.float32, device="cuda")
        pose = self.base.c2w.copy()
        pose[:3, 3] += self.base.c2w[:3, :3] @ np.array([0, 0, center_depth_m])
        pose_tensor = torch.tensor(pose, dtype=torch.float32, device="cuda")
        dynamics = {"probe": pose_tensor}
        gaussians = {"probe": self.base.marker}
        if occluder is not None:
            self.occluder._xyz[:] = torch.tensor(
                occluder, dtype=torch.float32, device="cuda"
            )
            dynamics["occluder"] = pose_tensor
            gaussians["occluder"] = self.occluder
        original_opacity = self.base.marker._opacity.detach().clone()
        try:
            if missing_index is not None:
                opacity = self.cfg["missing_marker_opacity"]
                self.base.marker._opacity[missing_index] = float(
                    np.log(opacity / (1 - opacity))
                )
            self.base.camera.dynamics = dynamics
            scene = self.base.isolated if context == "isolated" else self.base.scene
            images = []
            for level in self.cfg["contrast_levels"]:
                self.base.marker._features_dc.fill_((level - 0.5) / SH_C0)
                with torch.no_grad():
                    package = self.base.render(
                        self.base.camera,
                        None,
                        scene,
                        gaussians,
                        None,
                        self.base.background,
                        render_optical=False,
                    )
                rgb = package["render"].detach()
                if not bool(torch.isfinite(rgb).all()):
                    raise ValueError("non-finite HUGSIM RGB")
                images.append(
                    np.rint(
                        rgb.clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255
                    ).astype(np.uint8)
                )
        finally:
            self.base.marker._opacity.copy_(original_opacity)
        return images


def render_grid(probe, cfg, intrinsics, output, log):
    rows = []
    baseline_images = {}
    error = cfg["width_error_bound_px"]
    fx = intrinsics[0][0]
    for context, center_depth, condition in itertools.product(
        cfg["contexts"], cfg["center_depths_m"], cfg["conditions"]
    ):
        points = marker_points(condition, cfg["marker_separation_m"])
        render_camera = roundtrip_render_camera_points(
            points, center_depth, probe.base.c2w
        )
        designed_camera = points + np.array([0, 0, center_depth])
        transform_residual = float(np.max(np.abs(render_camera - designed_camera)))
        if transform_residual > 1e-5:
            raise ValueError("B2W camera-coordinate roundtrip exceeds 1e-5 m")
        full_width, marker_uv = project_width(points, center_depth, intrinsics)
        simple_width = fx * cfg["marker_separation_m"] / center_depth
        common_width = common_depth_width(points, center_depth, intrinsics)
        occluder = None
        occlusion_geometry = None
        if condition["kind"] == "occlusion":
            occluder = occluder_point(points, center_depth, condition)
            _, occ_uv = project_width(
                np.stack([occluder, occluder]), center_depth, intrinsics
            )
            alignment = float(np.linalg.norm(occ_uv[0] - marker_uv[0]))
            expected_front = condition["expected_occluded"]
            is_front = center_depth + occluder[2] < center_depth + points[0, 2]
            occlusion_geometry = {
                "occluder_local_xyz_m": occluder.tolist(),
                "target_camera_depth_m": float(center_depth + points[0, 2]),
                "occluder_camera_depth_m": float(center_depth + occluder[2]),
                "projection_alignment_px": alignment,
                "expected_relation": "front" if expected_front else "behind",
                "actual_relation": "front" if is_front else "behind",
                "valid": alignment <= 1e-9 and is_front == expected_front,
            }
            if not occlusion_geometry["valid"]:
                raise ValueError("invalid occluder geometry")
        directory = output / "rgb" / context / f"depth_{center_depth:g}m" / condition["id"]
        directory.mkdir(parents=True)
        missing_index = condition.get("missing_index")
        images = probe.render_pair(
            context, center_depth, points, occluder, missing_index=missing_index
        )
        paths = [directory / f"{name}.png" for name in ("bright", "dim")]
        for path, image in zip(paths, images, strict=True):
            write_rgb(path, image)
        try:
            measurement, failure = measure_pair(*images, cfg), None
        except ValueError as caught:
            measurement, failure = None, str(caught)
        unavailable = condition["kind"] == "missing" or condition.get(
            "expected_occluded", False
        )
        full_residual = (
            None if measurement is None else measurement["width_px"] - full_width
        )
        interval = (
            None
            if measurement is None
            else [
                measurement["width_px"] - error,
                measurement["width_px"] + error,
            ]
        )
        state_restore_check = None
        baseline_key = (context, center_depth)
        if condition["kind"] == "equal_depth":
            baseline_images[baseline_key] = [image.copy() for image in images]
        elif condition["kind"] == "missing":
            if baseline_key not in baseline_images:
                raise ValueError("missing control must run after its equal-depth baseline")
            restored = probe.render_pair(context, center_depth, points)
            restore_dir = directory / "state_restore"
            restore_dir.mkdir()
            restore_paths = [restore_dir / f"{name}.png" for name in ("bright", "dim")]
            for path, image in zip(restore_paths, restored, strict=True):
                write_rgb(path, image)
            state_restore_check = {
                "pixel_exact": all(
                    np.array_equal(before, after)
                    for before, after in zip(
                        baseline_images[baseline_key], restored, strict=True
                    )
                ),
                "rgb": [str(path.relative_to(output)) for path in restore_paths],
                "rgb_sha256": [sha256(path) for path in restore_paths],
            }
        rows.append(
            {
                "context": context,
                "center_depth_m": center_depth,
                "condition": condition["id"],
                "kind": condition["kind"],
                "marker_local_xyz_m": points.tolist(),
                "marker_render_camera_xyz_m": render_camera.tolist(),
                "transform_roundtrip_max_abs_m": transform_residual,
                "marker_projected_uv_px": marker_uv.tolist(),
                "full_prediction_px": full_width,
                "common_depth_prediction_px": common_width,
                "simple_prediction_px": simple_width,
                "measurement": measurement,
                "measurement_failure": failure,
                "full_residual_px": full_residual,
                "full_prediction_within_budget": full_residual is not None
                and abs(full_residual) <= error,
                "simple_prediction_excluded": interval is not None
                and not interval[0] <= simple_width <= interval[1],
                "common_depth_prediction_excluded": interval is not None
                and not interval[0] <= common_width <= interval[1],
                "expected_available": not unavailable,
                "availability_correct": (
                    measurement is not None
                    if not unavailable
                    else is_single_marker_failure(failure)
                ),
                "occlusion_geometry": occlusion_geometry,
                "state_restore_check": state_restore_check,
                "rgb": [str(path.relative_to(output)) for path in paths],
                "rgb_sha256": [sha256(path) for path in paths],
            }
        )
        log(f"rendered {context}/{center_depth:g}m/{condition['id']}")
    save_json(output / "measurements.json", rows)
    return rows


def summarize(rows, cfg, qualification):
    visible = [row for row in rows if row["expected_available"]]
    equal = [
        row
        for row in visible
        if row["kind"] == "equal_depth"
        or row["condition"] == "left_marker_occluder_behind"
    ]
    boundary = [
        row
        for row in visible
        if row["condition"]
        in {
            "yaw_45deg_center",
            "yaw_plus45_offset3m",
            "yaw_minus45_offset3m",
            "depth_skew_12m",
        }
    ]
    missing = [row for row in rows if row["kind"] == "missing"]
    occlusion_rows = [row for row in rows if row["kind"] == "occlusion"]
    occluded = [row for row in occlusion_rows if not row["expected_available"]]
    occluder_behind = [row for row in occlusion_rows if row["expected_available"]]
    unavailable = missing + occluded
    oriented_common_depth = [
        row for row in visible if row["condition"] == "yaw_45deg_center"
    ]
    unequal_depth = [
        row
        for row in visible
        if row["condition"]
        in {"yaw_plus45_offset3m", "yaw_minus45_offset3m", "depth_skew_12m"}
    ]
    restore_rgb_count = 2 * len(missing)
    return {
        "experiment_id": cfg["experiment_id"],
        "pair_count": len(rows),
        "main_rgb_render_count": 2 * len(rows),
        "state_restore_rgb_render_count": restore_rgb_count,
        "rgb_render_count": 2 * len(rows) + restore_rgb_count,
        "measurement_qualification": {
            key: value
            for key, value in qualification.items()
            if key not in {"rows", "geometry_rows"}
        },
        "visible_expected_count": len(visible),
        "visible_measured_count": sum(row["measurement"] is not None for row in visible),
        "max_transform_roundtrip_abs_m": max(
            row["transform_roundtrip_max_abs_m"] for row in rows
        ),
        "full_prediction_within_budget_count": sum(
            row["full_prediction_within_budget"] for row in visible
        ),
        "max_abs_full_residual_px": max(
            abs(row["full_residual_px"])
            for row in visible
            if row["full_residual_px"] is not None
        ),
        "equal_geometry_simple_prediction_covered_count": sum(
            not row["simple_prediction_excluded"] for row in equal
        ),
        "equal_geometry_expected_count": len(equal),
        "boundary_simple_prediction_excluded_count": sum(
            row["simple_prediction_excluded"] for row in boundary
        ),
        "boundary_expected_count": len(boundary),
        "oriented_common_depth_prediction_covered_count": sum(
            not row["common_depth_prediction_excluded"]
            for row in oriented_common_depth
        ),
        "oriented_common_depth_expected_count": len(oriented_common_depth),
        "unequal_depth_common_prediction_excluded_count": sum(
            row["common_depth_prediction_excluded"] for row in unequal_depth
        ),
        "unequal_depth_expected_count": len(unequal_depth),
        "missing_unavailable_count": sum(
            is_single_marker_failure(row["measurement_failure"]) for row in missing
        ),
        "missing_expected_count": len(missing),
        "occlusion_unavailable_count": sum(
            is_single_marker_failure(row["measurement_failure"]) for row in occluded
        ),
        "occlusion_expected_count": len(occluded),
        "occluder_behind_visible_count": sum(
            row["measurement"] is not None for row in occluder_behind
        ),
        "occluder_behind_expected_count": len(occluder_behind),
        "occlusion_geometry_valid_count": sum(
            row["occlusion_geometry"]["valid"] for row in occlusion_rows
        ),
        "occlusion_geometry_expected_count": len(occlusion_rows),
        "state_restore_exact_count": sum(
            row["state_restore_check"]["pixel_exact"] for row in missing
        ),
        "state_restore_expected_count": len(missing),
        "all_availability_decisions_correct": all(
            row["availability_correct"] for row in rows
        ),
        "all_preregistered_checks_passed": all(
            [
                len(visible) == 36,
                all(row["transform_roundtrip_max_abs_m"] <= 1e-5 for row in rows),
                all(row["full_prediction_within_budget"] for row in visible),
                all(not row["simple_prediction_excluded"] for row in equal),
                all(row["simple_prediction_excluded"] for row in boundary),
                all(
                    not row["common_depth_prediction_excluded"]
                    for row in oriented_common_depth
                ),
                all(row["common_depth_prediction_excluded"] for row in unequal_depth),
                all(is_single_marker_failure(row["measurement_failure"]) for row in unavailable),
                all(row["occlusion_geometry"]["valid"] for row in occlusion_rows),
                all(row["state_restore_check"]["pixel_exact"] for row in missing),
            ]
        ),
        "limitations": [
            "Known Gaussian marker centres and paired-contrast readout only",
            "Occluder is a controlled Gaussian, not a qualified real vehicle or material",
            "Missing-marker control qualifies rejection logic but is not physical occlusion",
            "Same camera, GPU, renderer, driver and host for both process repeats",
            "No AD, real camera, learned vehicle geometry, or task boundary is qualified",
        ],
    }


def make_figure(rows, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    visible = [row for row in rows if row["expected_available"]]
    figure, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    names = [condition for condition in sorted({row["condition"] for row in visible})]
    for name in names:
        group = [
            row
            for row in visible
            if row["context"] == "scene0383_static"
            and row["condition"] == name
            and row["measurement"] is not None
        ]
        if not group:
            continue
        axes[0].plot(
            [row["center_depth_m"] for row in group],
            [row["measurement"]["width_px"] for row in group],
            ".-",
            label=name,
        )
        axes[1].plot(
            [row["center_depth_m"] for row in group],
            [row["measurement"]["width_px"] - row["simple_prediction_px"] for row in group],
            ".-",
            label=name,
        )
    axes[0].set(title="Measured marker separation", ylabel="Pixels")
    axes[1].axhspan(-0.5, 0.5, color="green", alpha=0.12)
    axes[1].set(title="Residual against equal-depth formula", ylabel="Measured - simple (px)")
    for axis in axes:
        axis.set_xlabel("Centre depth (m)")
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    figure.savefig(output / "boundary_results.png", dpi=170)
    plt.close(figure)


def run(cfg, config_path, output, log):
    import torch

    model_dir = Path(cfg["model_dir"])
    required = [model_dir / name for name in ["cfg.yaml", "scene.pth", "meta_data.json"]]
    required += [
        config_path,
        Path(__file__),
        ROOT / "scripts/run_motion_observation_probe.py",
        Path(cfg["hugsim_repo"]) / "gaussian_renderer/__init__.py",
        Path(cfg["hugsim_repo"]) / "scene/cameras.py",
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    if not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; use an approved GPU-visible context")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    environment = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "role": "bounded motion-observation applicability probe",
        "cwd": str(Path.cwd()),
        "python": sys.executable,
        "torch": torch.__version__,
        "gpu": torch.cuda.get_device_name(0),
        "output": str(output),
        "argv": sys.argv,
        "audit_commit": git(ROOT, "rev-parse", "HEAD"),
        "audit_status": git(ROOT, "status", "--short"),
        "audit_branch": git(ROOT, "branch", "--show-current"),
        "audit_remote": git(ROOT, "remote", "-v"),
        "hugsim_commit": git(cfg["hugsim_repo"], "rev-parse", "HEAD"),
        "hugsim_status": git(cfg["hugsim_repo"], "status", "--short"),
        "hashes": {str(path): sha256(path) for path in required},
    }
    save_json(output / "environment.json", environment)
    log(f"preflight healthy; GPU={environment['gpu']}; output={output}")
    metadata = json.loads((model_dir / "meta_data.json").read_text())
    record = next(
        frame
        for frame in metadata["frames"]
        if Path(frame["rgb_path"]).parent.name == cfg["camera"]
        and Path(frame["rgb_path"]).stem == cfg["metadata_frame"]
    )
    save_json(output / "camera_reference.json", record)
    qualification = qualify_measurement(cfg, output, record)
    log(
        "measurement qualification passed: "
        f"{qualification['case_count']} cases, "
        f"max error={qualification['max_abs_width_error_px']:.6f}px"
    )
    probe = BoundaryProbe(cfg, record)
    rows = render_grid(probe, cfg, record["intrinsics"], output, log)
    summary = summarize(rows, cfg, qualification)
    summary["hugsim_commit"] = environment["hugsim_commit"]
    save_json(output / "summary.json", summary)
    make_figure(rows, output)
    log(
        f"completed {summary['rgb_render_count']} RGB renders; "
        f"checks_passed={summary['all_preregistered_checks_passed']}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    config_path, output = args.config.resolve(), args.output.resolve()
    cfg = json.loads(config_path.read_text())
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    output.mkdir(parents=True)
    save_json(output / "config.json", cfg)

    def log(message):
        line = f"{datetime.now(timezone.utc).isoformat()} {message}"
        print(line, flush=True)
        with (output / "run.log").open("a") as stream:
            stream.write(line + "\n")

    save_json(output / "status.json", {"status": "running"})
    try:
        run(cfg, config_path, output, log)
    except Exception as error:
        log(f"FAILED: {error}")
        (output / "failure.txt").write_text(traceback.format_exc())
        save_json(output / "status.json", {"status": "failed", "reason": str(error)})
        raise
    save_json(output / "status.json", {"status": "complete"})


if __name__ == "__main__":
    main()
