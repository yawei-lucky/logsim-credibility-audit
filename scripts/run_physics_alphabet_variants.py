#!/usr/bin/env python3
"""Predict new HUGSIM marker layouts with the unchanged operator rules.

Use the existing HUGSIM Python and a fresh output directory. All predictions
are saved before the first render. There is no image calibration or fitting.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from measure_credibility_marker_identity import measure_tagged_pair
from run_credibility_screening_identity import qualify
from run_motion_observation_boundary_probe import BoundaryProbe
from run_motion_observation_probe import git, save_json, sha256, write_rgb
from run_physics_alphabet_probe import camera_points, judge, predict, project, render_pair

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ("R_T_P_V", "T_R_P_V", "without_R", "without_T", "fixed_depth_P", "without_V")


def validate_frozen_rules(cfg):
    reference = json.loads((ROOT / cfg["reference_config"]).read_text())
    if sha256(ROOT / cfg["reference_rule_source"]) != cfg["reference_rule_sha256"]:
        raise ValueError("original operator implementation changed; frozen-rule experiment blocked")
    keys = ("hugsim_repo", "model_dir", "camera", "metadata_frame", "contexts", "suite",
            "marker_sigma_m", "marker_opacity", "marker_codes", "occluder_sigma_m",
            "occluder_opacity", "occluder_level", "occluder_depth_gap_m", "occlusion_conditions",
            "base_center_camera_m", "body_points_m", "translations_m")
    if any(cfg[key] != reference[key] for key in keys):
        raise ValueError("frozen camera, instrument, rendering or reference geometry changed")
    return reference


def geometries(cfg):
    common = {"angle": cfg["reference_angle_deg"],
              "base_depth_m": cfg["base_center_camera_m"][2], "layout": "reference"}
    result = []
    for angle in cfg["angles_deg"]:
        result.append(dict(common, id=f"angle_{angle}", family="angle", angle=angle))
    for depth in cfg["variant_base_depths_m"]:
        result.append(dict(common, id=f"depth_{depth}", family="depth", base_depth_m=depth))
    for name in cfg["variant_body_layouts_m"]:
        result.append(dict(common, id=f"layout_{name}", family="layout", layout=name))
    for angle, depth, name in itertools.product(cfg["angles_deg"], cfg["variant_base_depths_m"], cfg["variant_body_layouts_m"]):
        result.append({"id": f"joint_{angle}_{depth}_{name}", "family": "joint", "angle": angle,
                       "base_depth_m": depth, "layout": name})
    return result


def cases(cfg):
    return [dict(geometry, id=f"{geometry['id']}_{occlusion}", geometry_id=geometry["id"],
                 translation=cfg["translations_m"][cfg["translation_index"]], occlusion=occlusion)
            for geometry, occlusion in itertools.product(geometries(cfg), cfg["occlusion_conditions"])]


def geometry_config(cfg, case):
    result = dict(cfg)
    result["base_center_camera_m"] = [*cfg["base_center_camera_m"][:2], case["base_depth_m"]]
    result["body_points_m"] = (cfg["body_points_m"] if case["layout"] == "reference"
                               else cfg["variant_body_layouts_m"][case["layout"]])
    return result


def preflight(cfg, all_cases):
    reference = validate_frozen_rules(cfg)
    if len(geometries(cfg)) != 14 or len(all_cases) != 56 or len({c["id"] for c in all_cases}) != 56:
        raise ValueError("expected 14 geometries and 56 distinct conditions per context")
    if any(angle in reference["angles_deg"] for angle in cfg["angles_deg"]):
        raise ValueError("new angles overlap original angles")
    if any(depth == reference["base_center_camera_m"][2] for depth in cfg["variant_base_depths_m"]):
        raise ValueError("new base depths overlap reference")
    if any(points == reference["body_points_m"] for points in cfg["variant_body_layouts_m"].values()):
        raise ValueError("new layouts overlap reference")
    camera = cfg["suite"]["camera"]
    projected, sigmas = [], []
    for case in all_cases:
        local = geometry_config(cfg, case)
        xyz = camera_points(local, case)
        uv = project(local, xyz)
        if np.min(xyz[:, 2]) <= cfg["occluder_depth_gap_m"]:
            raise ValueError("invalid front occluder depth")
        if (uv[:, 0].min() < 10 or uv[:, 0].max() > camera["width"] - 10
                or uv[:, 1].min() < 10 or uv[:, 1].max() > camera["height"] - 10
                or uv[1, 0] - uv[0, 0] < 10):
            raise ValueError("designed markers clipped, reversed, or unresolved")
        projected.extend(uv.tolist())
        sigmas.extend((np.asarray(camera["intrinsics"])[0, 0] * cfg["marker_sigma_m"] / xyz[:, 2]).tolist())
    return {"geometry_count": 14, "conditions_per_context": 56, "pair_count": 112,
            "projected_min_uv_px": np.min(projected, axis=0).tolist(),
            "projected_max_uv_px": np.max(projected, axis=0).tolist(),
            "point_sigma_range_px": [min(sigmas), max(sigmas)],
            "meaning": "analytical input validity, not observed RGB or a universal measurement bound"}


def host_resources():
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in ("MemTotal", "MemAvailable"):
            memory[key + "_bytes"] = int(value.strip().split()[0]) * 1024
    disk = shutil.disk_usage(ROOT)
    return {"host": platform.node(), "memory": memory, "disk_free_bytes": disk.free,
            "load_average": list(os.getloadavg()),
            "scope": "execution host only; not the Windows laptop running the desktop app"}


def statistics(rows):
    result = {}
    for program in PROGRAMS:
        result[program] = {}
        for family in ("all", "angle", "depth", "layout", "joint"):
            subset = [r["judgements"][program] for r in rows if family == "all" or r["case"]["family"] == family]
            errors = [r["max_position_error_px"] for r in subset if r.get("max_position_error_px") is not None]
            result[program][family] = {"count": len(subset), "tested": sum(r["tested"] for r in subset),
                                        "passed": sum(r["contract_passed"] for r in subset),
                                        "max_position_error_px": max(errors) if errors else None}
    return result


def run(cfg, config_path, output, qualify_only, log):
    started = time.monotonic()
    all_cases = cases(cfg)
    validity = preflight(cfg, all_cases)
    model = Path(cfg["model_dir"])
    metadata_path = model / "meta_data.json"
    record = next(r for r in json.loads(metadata_path.read_text())["frames"]
                  if Path(r["rgb_path"]).stem == cfg["metadata_frame"] and Path(r["rgb_path"]).parent.name == cfg["camera"])
    camera = cfg["suite"]["camera"]
    if [record["width"], record["height"]] != [camera["width"], camera["height"]] or not np.array_equal(np.asarray(record["intrinsics"])[:3, :3], camera["intrinsics"]):
        raise ValueError("camera metadata differs from frozen calibration")
    inputs = [config_path, Path(__file__), ROOT / cfg["reference_config"], ROOT / cfg["reference_rule_source"],
              *(ROOT / "scripts" / name for name in ("measure_credibility_marker_identity.py", "run_credibility_screening_identity.py",
                 "run_motion_observation_probe.py", "run_motion_observation_boundary_probe.py")),
              metadata_path, model / "scene.pth", model / "cfg.yaml", Path(cfg["hugsim_repo"]) / "gaussian_renderer/__init__.py"]
    environment = {"started_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(),
                   "role": "CPU instrument qualification" if qualify_only else "HUGSIM frozen operator variant prediction",
                   "cwd": str(Path.cwd()), "python": sys.executable, "output": str(output), "argv": sys.argv,
                   "audit_commit": git(ROOT, "rev-parse", "HEAD"), "audit_status": git(ROOT, "status", "--short"),
                   "branch": git(ROOT, "branch", "--show-current"), "remote": git(ROOT, "remote", "-v"),
                   "hugsim_commit": git(cfg["hugsim_repo"], "rev-parse", "HEAD"), "hugsim_status": git(cfg["hugsim_repo"], "status", "--short"),
                   "input_hashes": {str(p): sha256(p) for p in inputs}, "resources_before": host_resources()}
    save_json(output / "environment.json", environment)
    save_json(output / "config.json", cfg)
    save_json(output / "camera_record.json", record)
    save_json(output / "input_validity.json", validity)
    save_json(output / "cases.json", all_cases)
    predictions = {case["id"]: {name: predict(geometry_config(cfg, case), case, name) for name in PROGRAMS} for case in all_cases}
    save_json(output / "predictions_before_rgb.json", predictions)
    prediction_hash = sha256(output / "predictions_before_rgb.json")
    log(f"preflight healthy; host={environment['host']}; role={environment['role']}; output={output}; predictions frozen={prediction_hash}")
    qualification = qualify(cfg, output)
    log(f"instrument qualified on {qualification['count']} independent 2D pairs")
    if qualify_only:
        return
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; use an approved GPU-visible context")
    if environment["resources_before"]["disk_free_bytes"] < 1024**3:
        raise RuntimeError("less than 1 GiB free for bounded experiment outputs")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.cuda.reset_peak_memory_stats()
    environment.update({"torch": torch.__version__, "torch_cuda": torch.version.cuda,
                        "gpu": torch.cuda.get_device_name(0), "gpu_free_total_before_bytes": list(torch.cuda.mem_get_info())})
    save_json(output / "environment.json", environment)
    nvidia = subprocess.run(["nvidia-smi"], capture_output=True, text=True, check=False)
    (output / "nvidia_smi_before.txt").write_text(nvidia.stdout + nvidia.stderr)
    probe = BoundaryProbe(cfg, record)
    rows = []
    for context in cfg["contexts"]:
        for case in all_cases:
            images, placement = render_pair(probe, geometry_config(cfg, case), case, context)
            directory = output / "rgb" / context / case["id"]
            directory.mkdir(parents=True)
            paths = [directory / "bright.png", directory / "dim.png"]
            for path, image in zip(paths, images, strict=True):
                write_rgb(path, image)
            try:
                observation = measure_tagged_pair(*images, cfg["suite"]["measurement"])
            except ValueError as error:
                observation = {"identities_qualified": False, "features": [], "width_px": None,
                               "measurement_error": str(error)}
            prediction = predictions[case["id"]]
            judgements = {name: judge(observation, prediction[name], cfg["suite"]["measurement"]["position_error_bound_px"]) for name in PROGRAMS}
            row = {"context": context, "case": case, "body_points_m": geometry_config(cfg, case)["body_points_m"],
                   "placement": placement, "rgb": [str(p) for p in paths], "rgb_sha256": [sha256(p) for p in paths],
                   "observation": observation, "predictions": prediction, "judgements": judgements}
            rows.append(row)
            save_json(directory / "record.json", row)
            log(f"{context}/{case['id']}: qualified={observation['identities_qualified']}; full={judgements['R_T_P_V']['contract_passed']}")
    save_json(output / "rows.json", rows)
    if sha256(output / "predictions_before_rgb.json") != prediction_hash:
        raise ValueError("pre-render predictions were modified")
    summary = {"experiment_id": cfg["experiment_id"], "overall_evidence_label": "down-weighted",
               "pair_count": len(rows), "rgb_count": len(rows)*2, "geometry_count": 14,
               "qualification_pairs": qualification["count"], "statistics": statistics(rows),
               "full_program_all_pass": all(r["judgements"]["R_T_P_V"]["contract_passed"] for r in rows),
               "unqualified_pair_count": sum(not r["judgements"]["R_T_P_V"]["tested"] for r in rows),
               "prediction_sha256_before_and_after": prediction_hash, "new_RGB_used_for_fitting": False,
               "limitations": ["Parameter and coded two-point layout reuse of supplied rules, not learned or discovered physics.",
                               "Layout variations are not ordinary vehicle meshes or surface-shape qualification.",
                               "Same camera, scene, marker profiles and two backgrounds; no real-AD or real-sim equivalence.",
                               "Counts are designed related conditions, not independent statistical samples."]}
    save_json(output / "summary.json", summary)
    environment.update({"elapsed_seconds": time.monotonic() - started,
                        "peak_process_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                        "peak_torch_GPU_allocated_bytes": torch.cuda.max_memory_allocated(),
                        "peak_torch_GPU_reserved_bytes": torch.cuda.max_memory_reserved(), "resources_after": host_resources()})
    save_json(output / "environment.json", environment)
    log(f"complete: {len(rows)} pairs, {len(rows)*2} RGB; full={summary['full_program_all_pass']}; unqualified={summary['unqualified_pair_count']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qualify-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "status.json", {"status": "running"})
    def log(message):
        line = f"{datetime.now(timezone.utc).isoformat()} {message}"
        print(line, flush=True)
        with (output / "run.log").open("a") as stream:
            stream.write(line + "\n")
    try:
        run(json.loads(args.config.read_text()), args.config.resolve(), output, args.qualify_only, log)
    except Exception as error:
        log(f"FAILED: {error}")
        (output / "failure.txt").write_text(traceback.format_exc())
        save_json(output / "status.json", {"status": "failed", "error": str(error)})
        raise
    save_json(output / "status.json", {"status": "complete"})


if __name__ == "__main__":
    main()
