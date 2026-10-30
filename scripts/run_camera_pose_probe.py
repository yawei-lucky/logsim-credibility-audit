#!/usr/bin/env python3
"""Move HUGSIM cameras around fixed world markers; predict before rendering.

Use the existing HUGSIM Python and a fresh output directory. --qualify-only
checks independent 2D readout qualification without requiring a GPU.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from measure_credibility_marker_identity import measure_tagged_pair
from run_credibility_screening_identity import qualify
from run_motion_observation_probe import HugsimProbe, git, save_json, sha256, write_rgb
from run_physics_alphabet_probe import camera_points, judge, project
from run_physics_alphabet_variants import host_resources

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ("inverse_camera_pose", "ignore_camera_translation", "ignore_camera_rotation",
            "forward_instead_of_inverse", "target_attached_to_camera")


def load_config(path):
    raw = json.loads(Path(path).read_text())
    source = ROOT / raw["base_config"]
    if sha256(source) != raw["base_config_sha256"]:
        raise ValueError("base camera/measurement configuration changed")
    cfg = json.loads(source.read_text())
    if sha256(ROOT / cfg["reference_rule_source"]) != cfg["reference_rule_sha256"]:
        raise ValueError("previous geometry rule source changed")
    for name in ("experiment_id", "objects", "camera_poses", "qualification"):
        cfg[name] = raw[name]
    return cfg, raw


def relative_camera_pose(case):
    """Homogeneous camera placement: Rz(roll) Ry(yaw) Rx(pitch), t in initial-camera axes."""
    pitch, yaw, roll = np.deg2rad(case["pitch_yaw_roll_deg"])
    rx = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
    ry = np.array([[np.cos(yaw), 0, np.sin(yaw)], [0, 1, 0], [-np.sin(yaw), 0, np.cos(yaw)]])
    rz = np.array([[np.cos(roll), -np.sin(roll), 0], [np.sin(roll), np.cos(roll), 0], [0, 0, 1]])
    result = np.eye(4)
    result[:3, :3] = rz @ ry @ rx
    result[:3, 3] = case["translation_m"]
    return result


def object_pose(cfg, fixture):
    angle = np.deg2rad(fixture["angle_deg"])
    result = np.eye(4)
    result[:3, :3] = [[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]]
    result[:3, 3] = np.asarray(cfg["base_center_camera_m"]) + fixture["translation_m"]
    return result


def camera_reference_points(cfg, fixture, case, program="inverse_camera_pose"):
    """Independent scalar inverse; does not use inv(camera placement matrix)."""
    local = dict(cfg, body_points_m=fixture["body_points_m"])
    points = camera_points(local, {"angle": fixture["angle_deg"], "translation": fixture["translation_m"]})
    if program == "target_attached_to_camera":
        return points
    angles = [0, 0, 0] if program == "ignore_camera_rotation" else case["pitch_yaw_roll_deg"]
    pitch, yaw, roll = np.deg2rad(angles)
    translation = np.zeros(3) if program == "ignore_camera_translation" else np.asarray(case["translation_m"])
    result = []
    for point in points:
        if program == "forward_instead_of_inverse":
            x, y, z = point
            y, z = np.cos(pitch)*y - np.sin(pitch)*z, np.sin(pitch)*y + np.cos(pitch)*z
            x, z = np.cos(yaw)*x + np.sin(yaw)*z, -np.sin(yaw)*x + np.cos(yaw)*z
            x, y = np.cos(roll)*x - np.sin(roll)*y, np.sin(roll)*x + np.cos(roll)*y
            result.append(np.array([x, y, z]) + translation)
        else:
            x, y, z = point - translation
            x, y = np.cos(roll)*x + np.sin(roll)*y, -np.sin(roll)*x + np.cos(roll)*y
            x, z = np.cos(yaw)*x - np.sin(yaw)*z, np.sin(yaw)*x + np.cos(yaw)*z
            y, z = np.cos(pitch)*y + np.sin(pitch)*z, -np.sin(pitch)*y + np.cos(pitch)*z
            result.append([x, y, z])
    return np.asarray(result)


def predictions(cfg, fixture, case):
    return {program: {key: uv.tolist() for key, uv in zip(("left", "right"),
            project(cfg, camera_reference_points(cfg, fixture, case, program)), strict=True)} for program in PROGRAMS}


def preflight(cfg):
    if len(cfg["objects"]) != 2 or len(cfg["camera_poses"]) != 11 or len({c["id"] for c in cfg["camera_poses"]}) != 11:
        raise ValueError("expected two fixtures and eleven distinct camera poses")
    if cfg["contexts"] != ["isolated", "scene0383_static"]:
        raise ValueError("unexpected background contexts")
    values, largest_difference = [], 0.0
    for fixture in cfg["objects"].values():
        body = np.column_stack([fixture["body_points_m"], np.ones(2)])
        for case in cfg["camera_poses"]:
            xyz = camera_reference_points(cfg, fixture, case)
            homogeneous = (np.linalg.inv(relative_camera_pose(case)) @ object_pose(cfg, fixture) @ body.T).T[:, :3]
            largest_difference = max(largest_difference, float(np.max(np.abs(xyz - homogeneous))))
            uv = project(cfg, xyz)
            if np.min(xyz[:, 2]) <= 1 or uv[1, 0] - uv[0, 0] < 10 or np.min(uv) < 10 or np.max(uv[:, 0]) >= 790 or np.max(uv[:, 1]) >= 440:
                raise ValueError("invalid, clipped or unresolved marker input")
            values.extend(uv.tolist())
    if largest_difference > 1e-10:
        raise ValueError("scalar inverse disagrees with independent homogeneous transform")
    return {"primary_pairs": 44, "equivalent_object_route_pairs": 4, "total_rgb": 96,
            "projected_min_uv_px": np.min(values, axis=0).tolist(), "projected_max_uv_px": np.max(values, axis=0).tolist(),
            "scalar_vs_homogeneous_max_difference_m": largest_difference}


def render_coded_pair(base, cfg, camera_world, body_world):
    torch = base.torch
    base.camera.c2w = torch.tensor(camera_world, device="cuda", dtype=torch.float32)
    base.camera.dynamics = {"probe": body_world}
    saved_body = body_world.clone()
    saved_xyz, saved_opacity = base.marker._xyz.clone(), base.marker._opacity.clone()
    images = []
    for role in ("bright", "dim"):
        colours = [cfg["marker_codes"][key][role] for key in ("left", "right")]
        base.marker._features_dc[:] = ((torch.tensor(colours, device="cuda", dtype=torch.float32) - .5) / .28209479177387814)[:, None, :]
        with torch.no_grad():
            package = base.render(base.camera, None, base.isolated if cfg["active_context"] == "isolated" else base.scene,
                                  {"probe": base.marker}, None, base.background, render_optical=False)
        rgb = package["render"].detach()
        if not bool(torch.isfinite(rgb).all()):
            raise ValueError("nonfinite rendered RGB")
        images.append(np.rint(rgb.clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8))
    if not torch.equal(saved_body, base.camera.dynamics["probe"]) or not torch.equal(saved_xyz, base.marker._xyz) or not torch.equal(saved_opacity, base.marker._opacity):
        raise ValueError("world pose, local geometry, or opacity changed during the pair")
    actual = body_world.detach().cpu().numpy()
    return images, {"camera_to_world_intended": camera_world.tolist(), "camera_to_world_used_f32": base.camera.c2w.detach().cpu().tolist(),
                    "body_to_world_used_f32": actual.tolist(), "body_pose_tensor_sha256": hashlib.sha256(actual.tobytes()).hexdigest(),
                    "body_and_geometry_preserved_within_pair": True}


def read_pair(images, cfg):
    try:
        observation = measure_tagged_pair(*images, cfg["suite"]["measurement"])
    except ValueError as error:
        return {"features": [], "width_px": None, "identities_qualified": False, "qualification_reason": str(error)}
    if {f["identity"] for f in observation["features"]} != {"left", "right"} or len(observation["features"]) != 2:
        observation["identities_qualified"] = False
        observation["qualification_reason"] = "both coded points required; background occlusion or readout loss unresolved"
    return observation


def run(cfg, raw, config_path, output, qualify_only, log):
    start = time.monotonic()
    validity = preflight(cfg)
    model = Path(cfg["model_dir"])
    metadata = model / "meta_data.json"
    record = next(r for r in json.loads(metadata.read_text())["frames"] if Path(r["rgb_path"]).stem == cfg["metadata_frame"] and Path(r["rgb_path"]).parent.name == cfg["camera"])
    if [record["width"], record["height"]] != [cfg["suite"]["camera"]["width"], cfg["suite"]["camera"]["height"]] or not np.array_equal(np.asarray(record["intrinsics"])[:3, :3], cfg["suite"]["camera"]["intrinsics"]):
        raise ValueError("camera calibration differs from frozen base")
    inputs = [config_path, ROOT / raw["base_config"], Path(__file__), metadata, model / "scene.pth", model / "cfg.yaml",
              *(ROOT / "scripts" / name for name in ("run_physics_alphabet_probe.py", "run_physics_alphabet_variants.py", "run_motion_observation_probe.py",
                  "run_credibility_screening_identity.py", "measure_credibility_marker_identity.py")),
              Path(cfg["hugsim_repo"]) / "scene/cameras.py", Path(cfg["hugsim_repo"]) / "gaussian_renderer/__init__.py"]
    env = {"started_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(), "cwd": str(Path.cwd()), "python": sys.executable,
           "role": "CPU camera probe instrument qualification" if qualify_only else "HUGSIM fixed-world camera pose probe", "output": str(output), "argv": sys.argv,
           "audit_commit": git(ROOT, "rev-parse", "HEAD"), "audit_status": git(ROOT, "status", "--short"), "branch": git(ROOT, "branch", "--show-current"), "remote": git(ROOT, "remote", "-v"),
           "hugsim_commit": git(cfg["hugsim_repo"], "rev-parse", "HEAD"), "hugsim_status": git(cfg["hugsim_repo"], "status", "--short"),
           "input_hashes": {str(p): sha256(p) for p in inputs}, "resources_before": host_resources()}
    for name, value in (("environment", env), ("config", cfg), ("camera_record", record), ("input_validity", validity)):
        save_json(output / f"{name}.json", value)
    manifest = {key: {case["id"]: predictions(cfg, fixture, case) for case in cfg["camera_poses"]} for key, fixture in cfg["objects"].items()}
    save_json(output / "predictions_before_rgb.json", manifest)
    prediction_hash = sha256(output / "predictions_before_rgb.json")
    log(f"preflight healthy; host={env['host']}; role={env['role']}; output={output}; prediction_sha256={prediction_hash}")
    qualification = qualify(cfg, output)
    log(f"qualified {qualification['count']} independent 2D pairs")
    if qualify_only:
        return
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; use an approved GPU-visible context")
    if env["resources_before"]["disk_free_bytes"] < 1024**3:
        raise RuntimeError("less than 1 GiB output space available")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.cuda.reset_peak_memory_stats()
    env.update({"gpu": torch.cuda.get_device_name(0), "torch": torch.__version__, "torch_cuda": torch.version.cuda})
    save_json(output / "environment.json", env)
    base = HugsimProbe(cfg, record)
    origin = np.asarray(record["camtoworld"])
    budget = cfg["suite"]["measurement"]["position_error_bound_px"]
    rows, equivalences = [], []
    for fixture_id, fixture in cfg["objects"].items():
        base.marker._xyz[:] = torch.tensor(fixture["body_points_m"], device="cuda", dtype=torch.float32)
        fixed_body = torch.tensor(origin @ object_pose(cfg, fixture), device="cuda", dtype=torch.float32)
        original_body = fixed_body.clone()
        for context in cfg["contexts"]:
            for case in cfg["camera_poses"]:
                active = dict(cfg, active_context=context)
                images, placement = render_coded_pair(base, active, origin @ relative_camera_pose(case), fixed_body)
                if not torch.equal(fixed_body, original_body):
                    raise ValueError("primary world pose changed between camera conditions")
                directory = output / "rgb" / context / fixture_id / case["id"]
                directory.mkdir(parents=True)
                paths = [directory / "bright.png", directory / "dim.png"]
                for path, image in zip(paths, images, strict=True):
                    write_rgb(path, image)
                observation = read_pair(images, cfg)
                prediction = manifest[fixture_id][case["id"]]
                row = {"fixture": fixture_id, "context": context, "case": case, "placement": placement,
                       "rgb": [str(p) for p in paths], "rgb_sha256": [sha256(p) for p in paths], "observation": observation,
                       "predictions": prediction, "judgements": {name: judge(observation, prediction[name], budget) for name in PROGRAMS}}
                rows.append(row)
                save_json(directory / "record.json", row)
                log(f"{context}/{fixture_id}/{case['id']}: qualified={observation['identities_qualified']}; full={row['judgements']['inverse_camera_pose']['contract_passed']}")
                if context == "isolated" and case["family"] == "combined":
                    equivalent_body = torch.tensor(origin @ np.linalg.inv(relative_camera_pose(case)) @ object_pose(cfg, fixture), device="cuda", dtype=torch.float32)
                    pair, equivalent_placement = render_coded_pair(base, active, origin, equivalent_body)
                    eq_directory = output / "rgb_equivalent_object_route" / fixture_id / case["id"]
                    eq_directory.mkdir(parents=True)
                    eq_paths = [eq_directory / "bright.png", eq_directory / "dim.png"]
                    for path, image in zip(eq_paths, pair, strict=True):
                        write_rgb(path, image)
                    eq_observation = read_pair(pair, cfg)
                    measured = {f["identity"]: [f["u"], f["v"]] for f in observation["features"]}
                    comparison = judge(eq_observation, measured, 2 * budget) if observation["identities_qualified"] else {"tested": False, "contract_passed": False, "failure_kind": "first_route_unqualified"}
                    equivalence = {"fixture": fixture_id, "case": case, "placement": equivalent_placement, "rgb": [str(p) for p in eq_paths],
                                   "rgb_sha256": [sha256(p) for p in eq_paths], "observation": eq_observation, "comparison": comparison,
                                   "absolute_reference": judge(eq_observation, prediction["inverse_camera_pose"], budget),
                                   "scope": "isolated background, different execution route, not a second independent physical reference"}
                    equivalences.append(equivalence)
                    save_json(eq_directory / "record.json", equivalence)
    save_json(output / "rows.json", rows)
    save_json(output / "equivalences.json", equivalences)
    if sha256(output / "predictions_before_rgb.json") != prediction_hash:
        raise ValueError("predictions changed after RGB")
    statistics = {}
    for program in PROGRAMS:
        statistics[program] = {}
        for family in ("all", "baseline", "translation", "rotation", "combined"):
            subset = [r["judgements"][program] for r in rows if family == "all" or r["case"]["family"] == family]
            errors = [r["max_position_error_px"] for r in subset if r.get("max_position_error_px") is not None]
            statistics[program][family] = {"count": len(subset), "tested": sum(r["tested"] for r in subset), "passed": sum(r["contract_passed"] for r in subset),
                                            "max_position_error_px": max(errors) if errors else None}
    summary = {"experiment_id": cfg["experiment_id"], "overall_evidence_label": "down-weighted", "primary_pairs": len(rows), "equivalence_pairs": len(equivalences),
               "new_RGB_count": 2*(len(rows)+len(equivalences)), "qualification_pairs": qualification["count"], "statistics": statistics,
               "equivalence_tested": sum(r["comparison"]["tested"] for r in equivalences), "equivalence_passed": sum(r["comparison"]["contract_passed"] for r in equivalences),
               "equivalence_max_position_difference_px": max((r["comparison"]["max_position_error_px"] for r in equivalences
                   if r["comparison"].get("max_position_error_px") is not None), default=None),
               "fixed_world_body_hashes_per_fixture": {key: sorted({r["placement"]["body_pose_tensor_sha256"] for r in rows if r["fixture"] == key}) for key in cfg["objects"]},
               "prediction_sha256_before_and_after": prediction_hash, "new_RGB_used_for_fitting": False,
               "limitations": ["Static camera-pose snapshots, not continuous motion, timing or ego dynamics.", "Only two coded marker fixtures, one intrinsic calibration and two contexts; no ordinary vehicle or real-AD validation.",
                               "Equivalence applies only in isolated background; affine appearance and scene visibility can depend on viewpoint.", "No direct real-sim, world-frame external calibration, complete alphabet, or driving-task claim."]}
    save_json(output / "summary.json", summary)
    env.update({"elapsed_seconds": time.monotonic() - start, "peak_process_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                "peak_torch_GPU_reserved_bytes": torch.cuda.max_memory_reserved(), "resources_after": host_resources()})
    save_json(output / "environment.json", env)
    log(f"complete: {len(rows)} primary pairs, {len(equivalences)} equivalent pairs; full={statistics['inverse_camera_pose']['all']['passed']}/{len(rows)}")


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
        cfg, raw = load_config(args.config)
        run(cfg, raw, args.config.resolve(), output, args.qualify_only, log)
    except Exception as error:
        log(f"FAILED: {error}")
        (output / "failure.txt").write_text(traceback.format_exc())
        save_json(output / "status.json", {"status": "failed", "error": str(error)})
        raise
    save_json(output / "status.json", {"status": "complete"})


if __name__ == "__main__":
    main()
