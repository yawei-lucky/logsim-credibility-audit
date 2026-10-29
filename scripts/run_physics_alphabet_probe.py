#!/usr/bin/env python3
"""Test a finite physical operator vocabulary against new HUGSIM RGB pairs.

Single-operator calibration precedes combined cases. Candidate rules are fixed
physics hypotheses, not learned laws. Only image-additive effects use calibration
RGB. Reuses the qualified contrast-code instrument; no AD or real-sim pairing.
"""
from __future__ import annotations

import argparse
import itertools
import json
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from measure_credibility_marker_identity import measure_tagged_pair
from run_credibility_screening_identity import qualify
from run_motion_observation_boundary_probe import BoundaryProbe
from run_motion_observation_probe import git, save_json, sha256, write_rgb

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ("R_T_P_V", "T_R_P_V", "image_additive", "without_R", "without_T", "fixed_depth_P", "without_V")


def cases(cfg):
    rows = [{"id": "base", "split": "single", "angle": 0, "translation": [0, 0, 0], "occlusion": "none"}]
    for angle in cfg["angles_deg"]:
        rows.append({"id": f"R{angle}", "split": "single", "angle": angle, "translation": [0, 0, 0], "occlusion": "none"})
    for index, translation in enumerate(cfg["translations_m"]):
        rows.append({"id": f"T{index}", "split": "single", "angle": 0, "translation": translation, "occlusion": "none"})
    for occlusion in cfg["occlusion_conditions"]:
        if occlusion != "none":
            rows.append({"id": f"V_{occlusion}", "split": "single", "angle": 0, "translation": [0, 0, 0], "occlusion": occlusion})
    for angle, index, occlusion in itertools.product(cfg["angles_deg"], range(len(cfg["translations_m"])), cfg["occlusion_conditions"]):
        rows.append({"id": f"R{angle}_T{index}_{occlusion}", "split": "combination", "angle": angle, "translation": cfg["translations_m"][index], "occlusion": occlusion})
    return rows


def camera_points(cfg, case, program="R_T_P_V"):
    """Scalar reference, separate from renderer's homogeneous object transform."""
    angle = np.deg2rad(0 if program == "without_R" else case["angle"])
    co, si = np.cos(angle), np.sin(angle)
    dx, dy, dz = [0, 0, 0] if program == "without_T" else case["translation"]
    center = np.asarray(cfg["base_center_camera_m"])
    result = []
    for x, y, z in cfg["body_points_m"]:
        if program == "T_R_P_V":
            x, y, z = x + dx, y + dy, z + dz
            result.append(center + [co*x + si*z, y, -si*x + co*z])
        else:
            result.append(center + [co*x + si*z + dx, y + dy, -si*x + co*z + dz])
    return np.asarray(result)


def project(cfg, points, fixed_depth=False):
    k = np.asarray(cfg["suite"]["camera"]["intrinsics"])
    depth = cfg["base_center_camera_m"][2] if fixed_depth else points[:, 2]
    return np.stack([k[0, 0] * points[:, 0] / depth + k[0, 2],
                     k[1, 1] * points[:, 1] / depth + k[1, 2]], axis=1)


def visible_ids(case, program):
    if program == "without_V" or not case["occlusion"].startswith("front_"):
        return ["left", "right"]
    return ["right"] if case["occlusion"] == "front_left" else ["left"]


def predict(cfg, case, program, atoms=None):
    if program == "image_additive":
        if atoms is None:
            raise ValueError("image_additive needs single-operator RGB calibration")
        r = "base" if case["angle"] == 0 else f"R{case['angle']}"
        t = "base" if case["translation"] == [0, 0, 0] else f"T{cfg['translations_m'].index(case['translation'])}"
        uv = atoms[r] + atoms[t] - atoms["base"]
    else:
        uv = project(cfg, camera_points(cfg, case, program), program == "fixed_depth_P")
    return {key: uv[index].tolist() for index, key in enumerate(["left", "right"]) if key in visible_ids(case, program)}


def judge(observation, prediction, budget):
    if not observation["identities_qualified"]:
        return {"tested": False, "failure_kind": "measurement_unqualified", "contract_passed": False}
    actual = {f["identity"]: [f["u"], f["v"]] for f in observation["features"]}
    if len(actual) != len(observation["features"]):
        return {"tested": False, "failure_kind": "measurement_unqualified", "contract_passed": False}
    if set(actual) != set(prediction):
        return {"tested": True, "failure_kind": "visible_identity_contradiction", "contract_passed": False, "max_position_error_px": None}
    if not actual:
        return {"tested": False, "failure_kind": "measurement_unqualified", "contract_passed": False}
    maximum = max(float(np.max(np.abs(np.asarray(actual[key]) - prediction[key]))) for key in actual)
    return {"tested": True, "failure_kind": None if maximum <= budget else "position_contradiction",
            "contract_passed": maximum <= budget, "max_position_error_px": maximum}


def render_pair(probe, cfg, case, context):
    """Keep body geometry fixed; HUGSIM applies the actual R,T object pose."""
    base, torch = probe.base, probe.torch
    body = np.asarray(cfg["body_points_m"])
    base.marker._xyz[:] = torch.tensor(body, device="cuda", dtype=torch.float32)
    theta = np.deg2rad(case["angle"])
    pose = np.eye(4)
    pose[:3, :3] = [[np.cos(theta), 0, np.sin(theta)], [0, 1, 0], [-np.sin(theta), 0, np.cos(theta)]]
    pose[:3, 3] = np.asarray(cfg["base_center_camera_m"]) + case["translation"]
    world_pose = base.c2w @ pose
    base.camera.dynamics = {"probe": torch.tensor(world_pose, device="cuda", dtype=torch.float32)}
    gaussians = {"probe": base.marker}
    hom = np.column_stack([body, np.ones(2)])
    rendered_camera_points = (np.linalg.inv(base.c2w) @ world_pose @ hom.T).T[:, :3]
    error = float(np.max(np.abs(rendered_camera_points - camera_points(cfg, case))))
    if error > 1e-9:
        raise ValueError("independent scalar/homogeneous placement mismatch")
    occlusion = None
    if case["occlusion"] != "none":
        index = 1 if case["occlusion"].endswith("right") else 0
        target = rendered_camera_points[index]
        gap = cfg["occluder_depth_gap_m"] * (1 if case["occlusion"].startswith("behind") else -1)
        depth = target[2] + gap
        if depth <= 0:
            raise ValueError("occluder behind camera")
        point = target * (depth / target[2])
        probe.occluder._xyz[:] = torch.tensor(point[None, :], device="cuda", dtype=torch.float32)
        base.camera.dynamics["occluder"] = torch.tensor(base.c2w, device="cuda", dtype=torch.float32)
        gaussians["occluder"] = probe.occluder
        alignment = float(np.max(np.abs(project(cfg, point[None, :]) - project(cfg, target[None, :]))))
        occlusion = {"target_index": index, "target_camera_m": target.tolist(), "occluder_camera_m": point.tolist(),
                     "depth_gap_m": float(gap), "ray_alignment_error_px": alignment}
        if alignment > 1e-9:
            raise ValueError("occluder ray mismatch")
    scene = base.isolated if context == "isolated" else base.scene
    opacity = base.marker._opacity.detach().clone()
    images = []
    for role in ["bright", "dim"]:
        colours = [cfg["marker_codes"][key][role] for key in ["left", "right"]]
        base.marker._features_dc[:] = ((torch.tensor(colours, device="cuda", dtype=torch.float32) - .5) / .28209479177387814)[:, None, :]
        with torch.no_grad():
            package = base.render(base.camera, None, scene, gaussians, None, base.background, render_optical=False)
        rgb = package["render"].detach()
        if not bool(torch.isfinite(rgb).all()):
            raise ValueError("nonfinite RGB")
        images.append(np.rint(rgb.clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8))
    if not torch.equal(opacity, base.marker._opacity):
        raise ValueError("marker opacity changed")
    return images, {"body_to_world": world_pose.tolist(), "body_geometry_unchanged": True,
                    "camera_points_m": rendered_camera_points.tolist(), "scalar_matrix_error_m": error,
                    "occlusion": occlusion, "marker_opacity_unchanged": True}


def run(cfg, config_path, output, qualify_only, log):
    if cfg["contexts"] != ["isolated", "scene0383_static"]:
        raise ValueError("this frozen probe requires exactly the two declared contexts")
    model = Path(cfg["model_dir"])
    metadata_path = model / "meta_data.json"
    record = next(r for r in json.loads(metadata_path.read_text())["frames"]
                  if Path(r["rgb_path"]).stem == cfg["metadata_frame"] and Path(r["rgb_path"]).parent.name == cfg["camera"])
    camera = cfg["suite"]["camera"]
    if [record["width"], record["height"]] != [camera["width"], camera["height"]] or not np.array_equal(np.asarray(record["intrinsics"])[:3, :3], camera["intrinsics"]):
        raise ValueError("camera differs from frozen calibration")
    inputs = [config_path, Path(__file__), ROOT / "scripts/measure_credibility_marker_identity.py",
              ROOT / "scripts/run_credibility_screening_identity.py", ROOT / "scripts/run_motion_observation_probe.py",
              ROOT / "scripts/run_motion_observation_boundary_probe.py", metadata_path, model / "scene.pth", model / "cfg.yaml",
              Path(cfg["hugsim_repo"]) / "gaussian_renderer/__init__.py"]
    environment = {"started_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(),
                   "role": "CPU coded measurement qualification" if qualify_only else "HUGSIM physical operator vocabulary test",
                   "cwd": str(Path.cwd()), "python": sys.executable, "output": str(output), "argv": sys.argv,
                   "audit_commit": git(ROOT, "rev-parse", "HEAD"), "audit_status": git(ROOT, "status", "--short"),
                   "branch": git(ROOT, "branch", "--show-current"), "remote": git(ROOT, "remote", "-v"),
                   "hugsim_commit": git(cfg["hugsim_repo"], "rev-parse", "HEAD"), "hugsim_status": git(cfg["hugsim_repo"], "status", "--short"),
                   "input_hashes": {str(p): sha256(p) for p in inputs}}
    save_json(output / "environment.json", environment)
    save_json(output / "config.json", cfg)
    save_json(output / "camera_record.json", record)
    all_cases = cases(cfg)
    if len(all_cases) != 24 or len({c["id"] for c in all_cases}) != 24 or sum(c["split"] == "single" for c in all_cases) != 8:
        raise ValueError("this frozen experiment requires 8 single and 16 combination cases")
    save_json(output / "cases.json", all_cases)
    log(f"input preflight healthy; role={environment['role']}; host={environment['host']}; output={output}")
    qualification = qualify(cfg, output)
    log(f"measurement qualified: {qualification['count']} independent 2D pairs")
    if qualify_only:
        return
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; use an approved GPU-visible context")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    environment.update({"torch": torch.__version__, "gpu": torch.cuda.get_device_name(0)})
    save_json(output / "environment.json", environment)
    probe = BoundaryProbe(cfg, record)
    budget = cfg["suite"]["measurement"]["position_error_bound_px"]
    rows = []
    for context in cfg["contexts"]:
        atoms = {}
        for case in all_cases:
            if case["split"] == "combination" and not atoms:
                raise ValueError("combined outputs cannot precede single-operator calibration")
            images, placement = render_pair(probe, cfg, case, context)
            directory = output / "rgb" / context / case["id"]
            directory.mkdir(parents=True)
            paths = [directory / "bright.png", directory / "dim.png"]
            for path, image in zip(paths, images, strict=True):
                write_rgb(path, image)
            observation = measure_tagged_pair(*images, cfg["suite"]["measurement"])
            if case["split"] == "single" and case["occlusion"] == "none":
                if not observation["identities_qualified"] or [f["identity"] for f in observation["features"]] != ["left", "right"]:
                    raise ValueError("single-operator readout unqualified; composition inference blocked")
                atoms[case["id"]] = np.asarray([[f["u"], f["v"]] for f in observation["features"]])
            predictions = {name: predict(cfg, case, name, atoms) for name in PROGRAMS}
            judgements = {name: judge(observation, prediction, budget) for name, prediction in predictions.items()}
            row = {"context": context, "case": case, "placement": placement, "rgb": [str(p) for p in paths],
                   "rgb_sha256": [sha256(p) for p in paths], "observation": observation,
                   "predictions": predictions, "judgements": judgements}
            rows.append(row)
            save_json(directory / "record.json", row)
            if case["split"] == "single" and case["id"] == "V_behind_left":
                save_json(output / f"{context}_single_image_effects.json", {key: value.tolist() for key, value in atoms.items()})
            log(f"{context}/{case['id']}: visible={[f['identity'] for f in observation['features']]}; full={judgements['R_T_P_V']['contract_passed']}")
    save_json(output / "rows.json", rows)
    statistics = {}
    for name in PROGRAMS:
        statistics[name] = {}
        for split in ["single", "combination"]:
            subset = [r["judgements"][name] for r in rows if r["case"]["split"] == split]
            errors = [r["max_position_error_px"] for r in subset if r.get("max_position_error_px") is not None]
            statistics[name][split] = {"count": len(subset), "tested": sum(r["tested"] for r in subset),
                                       "passed": sum(r["contract_passed"] for r in subset),
                                       "max_position_error_px": max(errors) if errors else None}
    compatible_single = [name for name in PROGRAMS if statistics[name]["single"]["passed"] == 16]
    compatible_all = [name for name in PROGRAMS if all(r["judgements"][name]["contract_passed"] for r in rows)]
    summary = {"experiment_id": cfg["experiment_id"], "overall_evidence_label": "down-weighted",
               "single_pair_count": 16, "combination_pair_count": 32, "rgb_count": len(rows)*2,
               "qualification_pairs": qualification["count"], "statistics": statistics,
               "compatible_on_single_cases": compatible_single, "compatible_on_all_cases": compatible_all,
               "full_program_all_pass": all(r["judgements"]["R_T_P_V"]["contract_passed"] for r in rows),
               "only_full_program_compatible": compatible_all == ["R_T_P_V"],
               "limitations": ["Candidate physical operators and grammar are researcher-specified; no law discovered from scratch.",
                               "Only two coded Gaussian markers, one camera and two contexts; no dynamics or real AD.",
                               "Image-additive coefficients use single-operator images only; all other programs use frozen geometry and camera.",
                               "Finite candidate discrimination does not establish a unique minimal or complete alphabet of world simulation."]}
    save_json(output / "summary.json", summary)
    log(f"complete: {len(rows)*2} RGB; single-compatible={compatible_single}; all-compatible={compatible_all}")


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
        cfg = json.loads(args.config.read_text())
        run(cfg, args.config.resolve(), output, args.qualify_only, log)
    except Exception as error:
        log(f"FAILED: {error}")
        (output / "failure.txt").write_text(traceback.format_exc())
        save_json(output / "status.json", {"status": "failed", "error": str(error)})
        raise
    save_json(output / "status.json", {"status": "complete"})


if __name__ == "__main__":
    main()
