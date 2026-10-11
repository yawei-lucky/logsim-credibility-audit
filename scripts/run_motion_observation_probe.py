#!/usr/bin/env python3
"""Qualify RGB marker measurements and probe HUGSIM motion-to-image transfer.

Run with the existing HUGSIM Python environment in a GPU-visible context.
All new products go to a new output directory; no HUGSIM source is modified.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import pickle
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def write_rgb(path, image):
    if not cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
        raise OSError(f"could not save {path}")


def measure_pair(bright, dim, cfg):
    """Read only RGB contrast; no truth coordinates, depth or semantic masks."""
    if bright.shape != dim.shape or bright.ndim != 3 or bright.shape[2] != 3:
        raise ValueError("paired RGB shape mismatch")
    weights = np.abs(bright.astype(np.float64) - dim.astype(np.float64)).mean(axis=2)
    mask = (weights > cfg["difference_threshold_u8"]).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    features = []
    for component in range(1, count):
        x, y, w, h, area = stats[component]
        if area < cfg["min_component_area_px"]:
            continue
        if x == 0 or y == 0 or x + w == mask.shape[1] or y + h == mask.shape[0]:
            raise ValueError("marker touches image boundary")
        yy, xx = np.nonzero(labels == component)
        mass = weights[yy, xx]
        features.append({"u": float(np.average(xx + 0.5, weights=mass)),
                         "v": float(np.average(yy + 0.5, weights=mass)),
                         "area_px": int(area)})
    if len(features) != 2:
        raise ValueError(f"expected exactly two visible markers, found {len(features)}")
    features.sort(key=lambda item: item["u"])
    width = features[1]["u"] - features[0]["u"]
    if not np.isfinite(width) or width <= 2 * cfg["width_error_bound_px"]:
        raise ValueError("invalid or unresolved marker separation")
    return {"width_px": width, "features": features}


def synthetic_pair(background, centres, sigma, opacity, levels):
    """Independent 2D image generator, without HUGSIM/gsplat projections."""
    yy, xx = np.indices(background.shape[:2], dtype=np.float64)
    alpha = np.zeros_like(xx)
    for u, v in centres:
        alpha += opacity * np.exp(-((xx + 0.5 - u) ** 2 + (yy + 0.5 - v) ** 2)
                                  / (2 * sigma**2))
    alpha = np.clip(alpha, 0, 1)[..., None]
    return [np.rint(background * (1 - alpha) + 255 * level * alpha).astype(np.uint8)
            for level in levels]


def qualify_measurement(cfg, background, output):
    q = cfg["qualification"]
    rows = []
    for bg_id, bg in [("black", np.zeros_like(background)), ("old_rgb", background)]:
        for width, phase, sigma, opacity in itertools.product(
                q["widths_px"], q["phases_px"], q["sigmas_px"], q["opacities"]):
            centres = [(350 + phase - width / 2, 220.3),
                       (350 + phase + width / 2, 220.3)]
            pair = synthetic_pair(bg, centres, sigma, opacity, cfg["contrast_levels"])
            measured = measure_pair(*pair, cfg)
            rows.append({"background": bg_id, "width_px": width, "phase_px": phase,
                         "sigma_px": sigma, "opacity": opacity,
                         "error_px": measured["width_px"] - width})
    negatives = {}
    for name, centres in {
        "missing": [(350, 220)],
        "clipped": [(0.5, 220), (350, 220)],
        "extra": [(300, 220), (350, 220), (400, 220)],
    }.items():
        pair = synthetic_pair(background, centres, 2, 0.9, cfg["contrast_levels"])
        try:
            measure_pair(*pair, cfg)
            negatives[name] = False
        except ValueError:
            negatives[name] = True
    max_error = max(abs(row["error_px"]) for row in rows)
    result = {"count": len(rows), "max_abs_width_error_px": max_error,
              "design_budget_px": cfg["width_error_bound_px"],
              "negative_controls_detected": negatives,
              "qualified": max_error <= cfg["width_error_bound_px"] and all(negatives.values()),
              "scope": "finite synthetic grid; not a universal or real-camera error bound",
              "rows": rows}
    save_json(output / "measurement_qualification.json", result)
    if not result["qualified"]:
        raise ValueError("RGB measurement qualification failed; GPU experiment not started")
    return result


def inspect_old_window(cfg, output):
    old = ROOT / cfg["old_run"]
    with (old / "infos.pkl").open("rb") as stream:
        infos = pickle.load(stream)
    with (old / "observations.pkl").open("rb") as stream:
        observations = pickle.load(stream)
    if len(observations) != len(infos):
        raise ValueError("old RGB/state count mismatch")
    selected = [i for i, info in enumerate(infos) if 0 <= info["timestamp"] <= 2]
    directory = output / "old_window"
    directory.mkdir()
    rows, frames = [], []
    for i in selected:
        info = infos[i]
        rgb = np.asarray(observations[i]["rgb"][cfg["camera"]])
        if rgb.dtype != np.uint8:
            raise ValueError(f"old RGB dtype is {rgb.dtype}; inspect conversion explicitly")
        path = directory / f"{i:03d}.png"
        write_rgb(path, rgb)
        frames.append(rgb.copy())
        actor, ego = np.asarray(info["obj_boxes"][0]), np.asarray(info["ego_box"])
        yaw = ego[6]
        rot = np.array([[np.cos(yaw), np.sin(yaw), 0],
                        [-np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
        centre_ego = rot @ (actor[:3] - ego[:3])
        camera = info["cam_params"][cfg["camera"]]
        centre_cam = (np.asarray(camera["v2c"]) @ np.r_[centre_ego, 1])[:3]
        rows.append({"index": i, "timestamp_s": float(info["timestamp"]),
                     "actor_centre_camera_m": centre_cam.tolist(),
                     "relative_yaw_rad": float(actor[6] - ego[6]),
                     "rgb_sha256": sha256(path)})
    del observations
    old_intrinsic = infos[0]["cam_params"][cfg["camera"]]["intrinsic"]
    report = {
        "input_hashes": {name: sha256(old / name) for name in ["infos.pkl", "observations.pkl"]},
        "camera": cfg["camera"], "intrinsic": old_intrinsic,
        "frame_count": len(rows), "rows": rows,
        "relative_yaw_span_rad": float(np.ptp([r["relative_yaw_rad"] for r in rows])),
        "time_steps_s": np.diff([r["timestamp_s"] for r in rows]).tolist(),
        "timestamp_scope": "logical simulation state time; no separate exposure/delivery stamps",
        "measurable_physical_width": False,
        "reason": "No independently surveyed 3D endpoints on the visible car; box dimensions are not RGB feature ground truth.",
        "decision": "down-weighted",
    }
    save_json(output / "old_window_audit.json", report)
    tiles = []
    for i, rgb in zip(selected, frames, strict=True):
        tile = cv2.resize(rgb, (400, 225))
        cv2.putText(tile, f"old CF-M  t={infos[i]['timestamp']:.2f}s", (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(tile)
    write_rgb(output / "old_window_contact.png", np.concatenate(
        [np.concatenate(tiles[i:i + 3], axis=1) for i in range(0, 9, 3)], axis=0))
    return report, frames[0]


def growth_interval(p0, p1, dt, error):
    if dt <= 0 or min(p0, p1) <= error:
        raise ValueError("growth requires increasing times and resolved positive widths")
    return [float(np.log((p1 - error) / (p0 + error)) / dt),
            float(np.log((p1 + error) / (p0 - error)) / dt)]


def identify_parameters(rows, cfg, focal_width):
    """Only the two identification trajectories enter this calculation."""
    values = []
    error = cfg["width_error_bound_px"]
    for trajectory in [t for t in cfg["trajectories"] if t["role"] == "identify"]:
        group = [r for r in rows if r["trajectory"] == trajectory["id"]
                 and r["condition"] == "combined" and r["repeat"] == 0]
        if len(group) != 9 or any(r["measurement"] is None for r in group):
            return {"identified": False, "reason": "missing identification measurements"}
        p = np.array([r["measurement"]["width_px"] for r in group])
        z = np.array([r["nominal_depth_m"] for r in group])
        d = focal_width / p - z
        lo = float(np.max(focal_width / (p + error) - z))
        hi = float(np.min(focal_width / (p - error) - z))
        values.append({"speed_mps": trajectory["closing_speed_mps"],
                       "d_m": float(np.median(d)), "interval_m": [lo, hi]})
    v0, v1 = [item["speed_mps"] for item in values]
    if v0 == v1:
        raise ValueError("two distinct speeds required")
    delay = (values[1]["d_m"] - values[0]["d_m"]) / (v1 - v0)
    bias = values[0]["d_m"] - v0 * delay
    vertices = []
    for d0, d1 in itertools.product(values[0]["interval_m"], values[1]["interval_m"]):
        delta = (d1 - d0) / (v1 - v0)
        vertices.append({"bias_m": d0 - v0 * delta, "delay_s": delta})
    return {"identified": all(x["interval_m"][0] <= x["interval_m"][1] for x in values),
            "bias_m": float(bias), "delay_s": float(delay),
            "speed_offsets": values, "parameter_vertices": vertices,
            "bias_interval_m": [min(v["bias_m"] for v in vertices), max(v["bias_m"] for v in vertices)],
            "delay_interval_s": [min(v["delay_s"] for v in vertices), max(v["delay_s"] for v in vertices)],
            "method": "median equivalent-depth offset per training speed; no heldout data or injected b/delta used"}


class HugsimProbe:
    def __init__(self, cfg, camera_record):
        import torch
        from omegaconf import OmegaConf
        sys.path.insert(0, cfg["hugsim_repo"])
        from gaussian_renderer import GaussianModel, render
        from scene.cameras import Camera

        self.torch, self.render, self.cfg = torch, render, cfg
        model_dir = Path(cfg["model_dir"])
        model_cfg = OmegaConf.load(model_dir / "cfg.yaml")
        self.scene = GaussianModel(model_cfg.model.sh_degree, affine=model_cfg.affine)
        params, _ = torch.load(model_dir / "scene.pth", map_location="cuda", weights_only=False)
        self.scene.restore(params, None)
        self.camera = Camera(width=camera_record["width"], height=camera_record["height"],
                             image=np.zeros((camera_record["height"], camera_record["width"], 3), np.float32),
                             K=np.array(camera_record["intrinsics"]),
                             c2w=np.array(camera_record["camtoworld"]), image_name="probe",
                             timestamp=0.0, dynamics={})
        dim = self.scene.get_3D_features.shape[1]

        def make_gaussians(n):
            pc = GaussianModel(model_cfg.model.sh_degree, affine=False)
            pc.active_sh_degree = self.scene.active_sh_degree
            pc._xyz = torch.zeros((n, 3), device="cuda")
            pc._features_dc = torch.zeros((n, 1, 3), device="cuda")
            pc._features_rest = torch.zeros((n, (model_cfg.model.sh_degree + 1)**2 - 1, 3), device="cuda")
            pc._feats3D = torch.zeros((n, dim), device="cuda")
            pc._scaling = torch.full((n, 3), float(np.log(cfg["marker_sigma_m"])), device="cuda")
            pc._rotation = torch.zeros((n, 4), device="cuda")
            pc._rotation[:, 0] = 1
            pc._opacity = torch.full((n, 1), float(np.log(cfg["marker_opacity"] / (1 - cfg["marker_opacity"]))), device="cuda")
            return pc

        self.isolated, self.marker = make_gaussians(0), make_gaussians(2)
        self.background = torch.zeros(3, device="cuda")
        self.c2w = np.array(camera_record["camtoworld"])

    def pair(self, context, depth, scale):
        torch = self.torch
        separation = self.cfg["marker_separation_m"] * scale
        self.marker._xyz[:, 0] = torch.tensor([-separation / 2, separation / 2], device="cuda")
        pose = self.c2w.copy()
        pose[:3, 3] += self.c2w[:3, :3] @ np.array([0, 0, depth])
        self.camera.dynamics = {"probe": torch.tensor(pose, dtype=torch.float32, device="cuda")}
        pc = self.isolated if context == "isolated" else self.scene
        images = []
        for level in self.cfg["contrast_levels"]:
            # SH degree-zero coefficients encode constant RGB; other terms remain zero.
            self.marker._features_dc.fill_((level - 0.5) / 0.28209479177387814)
            with torch.no_grad():
                package = self.render(self.camera, None, pc, {"probe": self.marker},
                                      None, self.background, render_optical=False)
            rgb = package["render"].detach()
            if not bool(torch.isfinite(rgb).all()):
                raise ValueError("non-finite HUGSIM RGB")
            images.append(np.rint(rgb.clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8))
        return images


def render_trajectory(probe, cfg, context, trajectory, output, focal_width, repeat=0):
    rows = []
    times = np.arange(round(cfg["duration_s"] / cfg["sample_dt_s"]) + 1) * cfg["sample_dt_s"]
    conditions = cfg["conditions"] if repeat == 0 else [cfg["conditions"][0]]
    for condition in conditions:
        directory = output / "rgb" / context / trajectory["id"] / f"{condition['id']}_r{repeat}"
        directory.mkdir(parents=True)
        for index, t in enumerate(times):
            capture = t - condition["delay_s"]
            nominal = trajectory["z0_m"] - trajectory["closing_speed_mps"] * t
            depth = trajectory["z0_m"] - trajectory["closing_speed_mps"] * capture + condition["bias_m"]
            scale = condition["scale"] * np.exp(condition["log_scale_amplitude"] * np.sin(cfg["log_scale_omega_rad_s"] * t))
            if depth <= 0:
                raise ValueError("nonpositive probe depth")
            predicted = focal_width * scale / depth
            images = probe.pair(context, depth, scale)
            paths = [directory / f"{index:03d}_{label}.png" for label in ["bright", "dim"]]
            for path, rgb in zip(paths, images, strict=True):
                write_rgb(path, rgb)
            try:
                measured, reason = measure_pair(*images, cfg), None
            except ValueError as error:
                measured, reason = None, str(error)
            rows.append({"context": context, "trajectory": trajectory["id"],
                         "condition": condition["id"], "repeat": repeat, "index": index,
                         "delivery_time_s": float(t), "target_capture_time_s": float(capture),
                         "nominal_depth_m": float(nominal), "rendered_depth_m": float(depth),
                         "scale": float(scale), "predicted_width_px": float(predicted),
                         "measurement": measured, "measurement_failure": reason,
                         "rgb": [str(path.relative_to(output)) for path in paths],
                         "rgb_sha256": [sha256(path) for path in paths]})
    return rows


def summarize(rows, cfg, frozen, focal_width, output):
    error = cfg["width_error_bound_px"]
    lag = round(cfg["difference_window_s"] / cfg["sample_dt_s"])
    groups, windows, heldout = [], [], []
    for context, trajectory, condition in itertools.product(
            cfg["contexts"], cfg["trajectories"], cfg["conditions"]):
        group = [r for r in rows if (r["context"], r["trajectory"], r["condition"], r["repeat"])
                 == (context, trajectory["id"], condition["id"], 0)]
        valid = [r for r in group if r["measurement"] is not None]
        residuals = [r["measurement"]["width_px"] - r["predicted_width_px"] for r in valid]
        inconsistent_zero = [abs(r["measurement"]["width_px"] - focal_width / r["nominal_depth_m"]) > error for r in valid]
        local_windows = []
        for before, after in zip(group[:-lag], group[lag:], strict=True):
            if before["measurement"] is None or after["measurement"] is None:
                continue
            p0, p1 = [r["measurement"]["width_px"] for r in [before, after]]
            dt = after["delivery_time_s"] - before["delivery_time_s"]
            predicted_g = float(np.log(after["predicted_width_px"] / before["predicted_width_px"]) / dt)
            interval = growth_interval(p0, p1, dt, error)
            measured_g = float(np.log(p1 / p0) / dt)
            zero_g = float(np.log(before["nominal_depth_m"] / after["nominal_depth_m"]) / dt)
            local_windows.append({"context": context, "trajectory": trajectory["id"],
                                  "condition": condition["id"], "time_s": before["delivery_time_s"],
                                  "measured_g_per_s": measured_g, "predicted_g_per_s": predicted_g,
                                  "zero_error_g_per_s": zero_g, "measurement_interval_per_s": interval,
                                  "prediction_covered": interval[0] <= predicted_g <= interval[1],
                                  "zero_model_excluded": not interval[0] <= zero_g <= interval[1]})
        windows.extend(local_windows)
        groups.append({"context": context, "trajectory": trajectory["id"], "condition": condition["id"],
                       "expected_frames": len(group), "measured_frames": len(valid),
                       "max_abs_width_error_px": max(map(abs, residuals)) if residuals else None,
                       "width_within_budget": len(valid) == len(group) == 9 and all(abs(x) <= error for x in residuals),
                       "expected_growth_windows": len(group) - lag,
                       "growth_windows": len(local_windows),
                       "growth_predictions_covered": sum(w["prediction_covered"] for w in local_windows),
                       "max_abs_growth_error_per_s": max((abs(w["measured_g_per_s"] - w["predicted_g_per_s"]) for w in local_windows), default=None),
                       "zero_model_width_excluded_frames": int(sum(inconsistent_zero)),
                       "zero_model_growth_excluded_windows": sum(w["zero_model_excluded"] for w in local_windows)})
        if trajectory["role"] == "heldout" and condition["id"] == "combined" and frozen[context]["identified"]:
            params = frozen[context]
            for row in valid:
                z, v = row["nominal_depth_m"], trajectory["closing_speed_mps"]
                centre = focal_width / (z + params["bias_m"] + v * params["delay_s"])
                predictions = [focal_width / (z + x["bias_m"] + v * x["delay_s"])
                               for x in params["parameter_vertices"]]
                interval = [min(predictions) - error, max(predictions) + error]
                measured = row["measurement"]["width_px"]
                heldout.append({"context": context, "time_s": row["delivery_time_s"],
                                "measured_px": measured, "prediction_px": float(centre),
                                "residual_px": float(measured - centre), "interval_px": interval,
                                "covered": interval[0] <= measured <= interval[1]})
    repeats = []
    for repeat in [r for r in rows if r["repeat"] == 1]:
        original = next(r for r in rows if (r["context"], r["trajectory"], r["condition"], r["index"], r["repeat"])
                        == (repeat["context"], repeat["trajectory"], repeat["condition"], repeat["index"], 0))
        pixel_delta = max(int(np.max(np.abs(cv2.imread(str(output / a)).astype(int)
                                           - cv2.imread(str(output / b)).astype(int))))
                          for a, b in zip(original["rgb"], repeat["rgb"], strict=True))
        repeats.append({"context": repeat["context"], "index": repeat["index"], "max_rgb_delta_u8": pixel_delta,
                        "same_png_hashes": original["rgb_sha256"] == repeat["rgb_sha256"]})
    save_json(output / "measurements.json", rows)
    save_json(output / "growth_windows.json", windows)
    save_json(output / "heldout_predictions.json", heldout)
    return {"pair_count": len(rows), "rgb_render_count": 2 * len(rows),
            "groups": groups, "identification": frozen, "heldout": heldout,
            "repeats": repeats,
            "all_width_predictions_within_budget": all(g["width_within_budget"] for g in groups),
            "all_growth_predictions_covered": all(g["growth_predictions_covered"] == g["expected_growth_windows"] for g in groups),
            "heldout_covered_count": sum(r["covered"] for r in heldout),
            "heldout_expected_count": 9 * len(cfg["contexts"]),
            "max_repeat_rgb_delta_u8": max(r["max_rgb_delta_u8"] for r in repeats)}


def make_plot(rows, summary, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for condition in ["baseline", "distance", "delay", "constant_scale", "varying_scale", "combined"]:
        group = [r for r in rows if (r["context"], r["trajectory"], r["condition"], r["repeat"])
                 == ("scene0383_static", "train_fast", condition, 0) and r["measurement"] is not None]
        times = [r["delivery_time_s"] for r in group]
        axes[0, 0].plot(times, [r["measurement"]["width_px"] for r in group], ".-", label=condition)
        axes[0, 1].plot(times, [r["measurement"]["width_px"] - r["predicted_width_px"] for r in group], ".-", label=condition)
    axes[0, 0].set(title="Known marker motion in reconstructed scene", ylabel="Measured separation (px)")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].axhspan(-0.5, 0.5, alpha=0.12, color="green")
    axes[0, 1].set(title="Independent projection prediction", ylabel="Measured - predicted (px)")
    windows = json.loads((output / "growth_windows.json").read_text())
    for condition in ["baseline", "constant_scale", "varying_scale"]:
        group = [w for w in windows if (w["context"], w["trajectory"], w["condition"])
                 == ("scene0383_static", "train_fast", condition)]
        axes[1, 0].plot([r["time_s"] + 0.25 for r in group], [r["measured_g_per_s"] for r in group], ".-", label=condition)
    axes[1, 0].set(title="Constant size bias vs changing size", ylabel="0.5 s log growth (1/s)")
    axes[1, 0].legend(fontsize=8)
    for context in ["isolated", "scene0383_static"]:
        group = [r for r in summary["heldout"] if r["context"] == context]
        if group:
            axes[1, 1].plot([r["time_s"] for r in group], [r["residual_px"] for r in group], ".-", label=context)
            axes[1, 1].fill_between([r["time_s"] for r in group],
                                    [r["interval_px"][0] - r["prediction_px"] for r in group],
                                    [r["interval_px"][1] - r["prediction_px"] for r in group], alpha=0.15)
    axes[1, 1].set(title="Held-out speed AND distance; no refit", ylabel="Measured - frozen prediction (px)")
    axes[1, 1].legend(fontsize=8)
    for ax in axes.flat:
        ax.set_xlabel("Delivery time (s)")
        ax.grid(alpha=0.2)
    fig.savefig(output / "mechanism_results.png", dpi=170)
    plt.close(fig)


def run(cfg, config_path, output, log):
    import torch
    model_dir = Path(cfg["model_dir"])
    required = [model_dir / x for x in ["cfg.yaml", "scene.pth", "meta_data.json"]]
    required += [ROOT / cfg["old_run"] / x for x in ["infos.pkl", "observations.pkl"]]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"required input missing: {path}")
    if not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; rerun in an approved GPU-visible context")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    env = {"started_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(),
           "role": "bounded motion-observation renderer probe", "cwd": str(Path.cwd()),
           "python": sys.executable, "torch": torch.__version__, "gpu": torch.cuda.get_device_name(0),
           "output": str(output), "argv": sys.argv,
           "audit_commit": git(ROOT, "rev-parse", "HEAD"), "audit_status": git(ROOT, "status", "--short"),
           "audit_branch": git(ROOT, "branch", "--show-current"), "audit_remote": git(ROOT, "remote", "-v"),
           "hugsim_commit": git(cfg["hugsim_repo"], "rev-parse", "HEAD"),
           "hugsim_status": git(cfg["hugsim_repo"], "status", "--short"),
           "hashes": {str(p): sha256(p) for p in required + [config_path, Path(__file__),
                      Path(cfg["hugsim_repo"]) / "gaussian_renderer/__init__.py",
                      Path(cfg["hugsim_repo"]) / "scene/cameras.py"]}}
    save_json(output / "environment.json", env)
    log(f"preflight healthy; host={env['host']}; GPU={env['gpu']}; output={output}")
    old_report, background = inspect_old_window(cfg, output)
    log(f"old window inspected: {old_report['frame_count']} RGB/state pairs; physical endpoints unqualified")
    qualification = qualify_measurement(cfg, background, output)
    log(f"CPU qualification passed: {qualification['count']} cases; max error={qualification['max_abs_width_error_px']:.6f}px")
    metadata = json.loads((model_dir / "meta_data.json").read_text())
    record = next(f for f in metadata["frames"] if
                  Path(f["rgb_path"]).parent.name == cfg["camera"] and
                  Path(f["rgb_path"]).stem == cfg["metadata_frame"])
    save_json(output / "camera_reference.json", record)
    focal_width = record["intrinsics"][0][0] * cfg["marker_separation_m"]
    probe = HugsimProbe(cfg, record)
    rows, frozen = [], {}
    for context in cfg["contexts"]:
        for trajectory in [t for t in cfg["trajectories"] if t["role"] == "identify"]:
            rows.extend(render_trajectory(probe, cfg, context, trajectory, output, focal_width))
            log(f"rendered {context}/{trajectory['id']}: 6 conditions x 9 paired frames")
        context_rows = [r for r in rows if r["context"] == context]
        frozen[context] = identify_parameters(context_rows, cfg, focal_width)
        # Save immutable training-only parameters before any heldout rendering.
        save_json(output / f"frozen_identification_{context}.json", frozen[context])
        log(f"parameters frozen before heldout: {context}, identified={frozen[context]['identified']}")
        for trajectory in [t for t in cfg["trajectories"] if t["role"] == "heldout"]:
            rows.extend(render_trajectory(probe, cfg, context, trajectory, output, focal_width))
        rows.extend(render_trajectory(probe, cfg, context, cfg["trajectories"][0], output, focal_width, repeat=1))
        save_json(output / "measurements_partial.json", rows)
        log(f"heldout and repeat completed: {context}")
    summary = summarize(rows, cfg, frozen, focal_width, output)
    summary.update({"experiment_id": cfg["experiment_id"], "hugsim_commit": env["hugsim_commit"],
                    "measurement_qualification": {k: v for k, v in qualification.items() if k != "rows"},
                    "old_window_decision": old_report["decision"],
                    "limitations": ["Finite designed grid, synthetic markers and paired contrast readout only",
                                    "Delay is an injected age of target state, not measured runtime latency",
                                    "No real camera, learned car geometry, AD or closed-loop task qualification"]})
    save_json(output / "summary.json", summary)
    make_plot(rows, summary, output)
    log(f"completed {summary['rgb_render_count']} RGB renders; width checks={summary['all_width_predictions_within_budget']}; heldout={summary['heldout_covered_count']}/{summary['heldout_expected_count']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    config_path, output = args.config.resolve(), args.output.resolve()
    cfg = json.loads(config_path.read_text())
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}; choose a new run directory")
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
