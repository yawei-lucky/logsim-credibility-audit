#!/usr/bin/env python3
"""Check prescribed timed motion and occlusion with a three-valued reference.

The renderer receives externally prescribed poses, not vehicle dynamics. Use the
existing HUGSIM Python and a new output directory; --qualify-only needs no GPU.
"""
from __future__ import annotations

import argparse
import itertools
import json
import platform
import resource
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from measure_credibility_marker_identity import measure_tagged_pair, synthetic_tagged_pair
from run_motion_observation_boundary_probe import BoundaryProbe
from run_motion_observation_probe import git, save_json, sha256, write_rgb
from run_physics_alphabet_probe import project
from run_physics_alphabet_variants import host_resources

ROOT = Path(__file__).resolve().parents[1]
IDS = ("left", "right")
PROGRAMS = ("full", "stale_target_0p2s", "stale_occluder_0p5s", "ignore_phase", "rear_as_front", "ignore_occlusion")
GSPLAT_SOURCE = Path("/home/yawei/HUGSIM/.pixi/envs/default/lib/python3.11/site-packages/gsplat/rendering.py")


def load_config(path):
    raw = json.loads(Path(path).read_text())
    base = ROOT / raw["base_config"]
    if sha256(base) != raw["base_config_sha256"]:
        raise ValueError("frozen camera and measurement configuration changed")
    cfg = json.loads(base.read_text())
    for key in ("experiment_id", "motion", "occlusion", "sampling", "cases", "qualification"):
        cfg[key] = raw[key]
    cfg["body_points_m"] = raw["body_points_m"]
    cfg["occluder_sigma_m"] = raw["occlusion"]["sigma_m"]
    return cfg, raw


def sample_times(cfg):
    return [round(i * cfg["sampling"]["dt_s"], 10) for i in range(cfg["sampling"]["steps"] + 1)]


def target_points(cfg, timestamp):
    motion = cfg["motion"]
    center = np.asarray(motion["center_at_zero_m"]) + timestamp * np.asarray(motion["velocity_mps"])
    theta = np.deg2rad(motion["yaw_at_zero_deg"] + motion["yaw_rate_degps"] * timestamp)
    return np.asarray([center + [np.cos(theta)*x + np.sin(theta)*z, y, -np.sin(theta)*x + np.cos(theta)*z]
                       for x, y, z in cfg["body_points_m"]])


def target_pose(cfg, timestamp):
    motion = cfg["motion"]
    theta = np.deg2rad(motion["yaw_at_zero_deg"] + motion["yaw_rate_degps"] * timestamp)
    result = np.eye(4)
    result[:3, :3] = [[np.cos(theta), 0, np.sin(theta)], [0, 1, 0], [-np.sin(theta), 0, np.cos(theta)]]
    result[:3, 3] = np.asarray(motion["center_at_zero_m"]) + timestamp*np.asarray(motion["velocity_mps"])
    return result


def occluder_point(cfg, case, timestamp):
    if case["kind"] == "none":
        return None
    target = target_points(cfg, timestamp)[0]
    depth = cfg["occlusion"]["front_depth_m" if case["kind"] == "front" else "rear_depth_m"]
    point = target * (depth / target[2])
    profile = np.asarray(cfg["occlusion"]["offset_profile_sigma"])
    offset = np.interp(timestamp-case["phase_s"], profile[:, 0], profile[:, 1])
    point[0] += offset * cfg["occlusion"]["sigma_m"]
    return point


def projected_sigma_bounds(cfg, point, sigma):
    # Isotropic 3D Gaussian, equal fx/fy pinhole, plus the installed gsplat eps2d.
    fx = cfg["suite"]["camera"]["intrinsics"][0][0]
    scale = fx * sigma / point[2]
    eps = cfg["occlusion"]["eps2d_px2"]
    return [float(np.sqrt(scale**2 + eps)),
            float(np.sqrt(scale**2 * (1 + np.sum(np.square(point[:2]/point[2]))) + eps))]


def reference(cfg, case, timestamp, program="full"):
    target_time = max(0, timestamp-.2) if program == "stale_target_0p2s" else timestamp
    points = target_points(cfg, target_time)
    occ_case = dict(case)
    if program == "ignore_phase":
        occ_case["phase_s"] = 0
    if program == "rear_as_front" and occ_case["kind"] == "rear":
        occ_case["kind"] = "front"
    occ_time = max(0, timestamp-.5) if program == "stale_occluder_0p5s" else timestamp
    occ = None if program == "ignore_occlusion" else occluder_point(cfg, occ_case, occ_time)
    uv = project(cfg, points)
    visibility, distances = {}, {}
    for index, identity in enumerate(IDS):
        if occ is None or occ[2] >= points[index, 2]:
            visibility[identity] = "clear"
            distances[identity] = None
            continue
        distance = float(np.linalg.norm(uv[index] - project(cfg, occ[None, :])[0]))
        occ_min, occ_max = projected_sigma_bounds(cfg, occ, cfg["occluder_sigma_m"])
        marker_max = projected_sigma_bounds(cfg, points[index], cfg["marker_sigma_m"])[1]
        clear_bound = cfg["occlusion"]["clear_sigma"]*occ_max + cfg["occlusion"]["marker_margin_sigma"]*marker_max
        hidden_bound = cfg["occlusion"]["hidden_core_sigma"]*occ_min
        visibility[identity] = "hidden" if distance <= hidden_bound else "clear" if distance >= clear_bound else "transition"
        distances[identity] = {"separation_px": distance, "hidden_bound_px": hidden_bound, "clear_bound_px": clear_bound}
    return {"uv": {identity: uv[i].tolist() for i, identity in enumerate(IDS)}, "visibility": visibility,
            "points_camera_m": points.tolist(), "occluder_camera_m": None if occ is None else occ.tolist(), "margins": distances}


def judge(observation, prediction, truth, cfg):
    actual = {f["identity"]: [f["u"], f["v"]] for f in observation["features"]}
    if not observation["identities_qualified"] or len(actual) != len(observation["features"]):
        return {"readout_qualified": False, "fully_decidable": False, "point_checks": [], "violations": [], "qualified_width_px": None}
    checks, violations = [], []
    for identity in IDS:
        true_state, expected = truth["visibility"][identity], prediction["visibility"][identity]
        if true_state == "transition" or expected == "transition":
            continue
        present = identity in actual
        record = {"identity": identity, "expected": expected, "observed_present": present, "position_error_px": None}
        if present != (expected == "clear"):
            violations.append({"identity": identity, "kind": "visibility_contradiction"})
        elif present and true_state == "clear":
            error = float(np.max(np.abs(np.asarray(actual[identity])-prediction["uv"][identity])))
            record["position_error_px"] = error
            if error > cfg["suite"]["measurement"]["position_error_bound_px"]:
                violations.append({"identity": identity, "kind": "position_contradiction", "error_px": error})
        checks.append(record)
    fully = len(checks) == 2
    both_clear = all(truth["visibility"][identity] == "clear" for identity in IDS)
    qualified_width = observation.get("width_px") if both_clear and set(actual) == set(IDS) else None
    return {"readout_qualified": True, "fully_decidable": fully, "point_checks": checks, "violations": violations,
            "qualified_width_px": qualified_width}


def synthetic_occluded_pair(cfg, background, centers, marker_sigma, occ_sigma, offset_sigma, front, mixing):
    yy, xx = np.indices(background.shape[:2], dtype=float)
    alpha_markers = [cfg["marker_opacity"]*np.exp(-((xx+.5-u)**2+(yy+.5-v)**2)/(2*marker_sigma**2)) for u, v in centers]
    occ_u, occ_v = centers[0] + np.array([offset_sigma*occ_sigma, 0])
    alpha_occ = cfg["occluder_opacity"]*np.exp(-((xx+.5-occ_u)**2+(yy+.5-occ_v)**2)/(2*occ_sigma**2))
    result = []
    for role in ("bright", "dim"):
        image = background.astype(float).copy()
        if not front:
            image = image*(1-alpha_occ[..., None]) + 255*cfg["occluder_level"]*alpha_occ[..., None]
        for identity, alpha in zip(IDS, alpha_markers, strict=True):
            colour = np.asarray(mixing) @ cfg["marker_codes"][identity][role]
            image = image*(1-alpha[..., None]) + 255*colour*alpha[..., None]
        if front:
            image = image*(1-alpha_occ[..., None]) + 255*cfg["occluder_level"]*alpha_occ[..., None]
        result.append(np.rint(image).clip(0, 255).astype(np.uint8))
    return result


def qualify(cfg, output):
    q = cfg["qualification"]
    camera = cfg["suite"]["camera"]
    yy, xx = np.indices((camera["height"], camera["width"]))
    texture = np.stack([35+xx%41, 55+yy%37, 45+(xx+yy)%43], axis=-1).astype(np.uint8)
    rows = []
    for sigma, occ_sigma, du, dv, background_id, front, offset, mix_id in itertools.product(
            q["marker_sigmas_px"], q["occluder_sigmas_px"], q["phases_px"], q["phases_px"], ("black", "texture"),
            (False, True), q["offsets_sigma"], range(len(q["mixes"]))):
        centers = np.asarray(q["centres_px"]) + [du, dv]
        pair = synthetic_occluded_pair(cfg, np.zeros_like(texture) if background_id == "black" else texture,
                                       centers, sigma, occ_sigma, offset, front, q["mixes"][mix_id])
        obs = measure_tagged_pair(*pair, cfg["suite"]["measurement"])
        expected_ids = ["right"] if front and abs(offset) <= cfg["occlusion"]["hidden_core_sigma"]+1e-12 else list(IDS)
        actual = {f["identity"]: [f["u"], f["v"]] for f in obs["features"]}
        valid = obs["identities_qualified"] and len(actual) == len(obs["features"]) and set(actual) == set(expected_ids)
        error = max((float(np.max(np.abs(np.asarray(actual[key])-centers[IDS.index(key)]))) for key in expected_ids), default=None) if valid else None
        width_error = None if len(expected_ids) == 1 else obs["width_px"] - float(centers[1, 0]-centers[0, 0]) if valid else None
        rows.append({"marker_sigma_px": sigma, "occluder_sigma_px": occ_sigma, "phase_px": [du, dv], "background": background_id,
                     "front": front, "offset_sigma": offset, "mix_id": mix_id, "expected_ids": expected_ids,
                     "valid_identity_and_count": valid, "position_error_px": error, "width_error_px": width_error,
                     "null_width_when_single": len(expected_ids) != 1 or obs["width_px"] is None})
    invalid = {}
    for name, centres, bright, dim in (
            ("ambiguous", [[469.75,228.25]], [[.9,.2,.9]], [[.1,.2,.1]]),
            ("unknown_green", [[469.75,228.25]], [[.2,.9,.2]], [[.2,.1,.2]]),
            ("boundary", [[.5,228.25]], [[.9,.2,.2]], [[.1,.2,.2]])):
        try:
            pair = synthetic_tagged_pair(texture, centres, bright, dim, 1.2, cfg["marker_opacity"])
            invalid[name] = not measure_tagged_pair(*pair, cfg["suite"]["measurement"])["identities_qualified"]
        except ValueError:
            invalid[name] = name == "boundary"
    boundaries = []
    for background_id, offset in itertools.product(("black", "texture"), (-.75, .75)):
        centers = np.asarray(q["centres_px"])
        pair = synthetic_occluded_pair(cfg, np.zeros_like(texture) if background_id == "black" else texture,
                                       centers, 1.25, 7.9, offset, True, np.eye(3))
        obs = measure_tagged_pair(*pair, cfg["suite"]["measurement"])
        actual = {f["identity"]: [f["u"], f["v"]] for f in obs["features"]}
        error = None if "left" not in actual else float(np.max(np.abs(np.asarray(actual["left"])-centers[0])))
        boundaries.append({"background": background_id, "offset_sigma": offset, "left_visible": "left" in actual,
                           "unoccluded_center_error_px": error, "raw_readout": obs})
    maximum = max((r["position_error_px"] for r in rows if r["position_error_px"] is not None), default=None)
    width_maximum = max((abs(r["width_error_px"]) for r in rows if r["width_error_px"] is not None), default=None)
    result = {"positive_pair_count": len(rows), "correct_identity_and_count_pairs": sum(r["valid_identity_and_count"] for r in rows),
              "max_position_error_px": maximum, "max_width_error_px": width_maximum, "invalid_controls_blocked": invalid,
              "partial_boundary_examples": boundaries,
              "qualified": all(r["valid_identity_and_count"] and r["null_width_when_single"] for r in rows)
                           and maximum is not None and maximum <= cfg["suite"]["measurement"]["position_error_bound_px"]
                           and width_maximum is not None and width_maximum <= cfg["suite"]["measurement"]["width_error_bound_px"] and all(invalid.values()),
              "scope": "Finite independent 2D alpha-profile instrument qualification; transition examples are diagnostics, not pass requirements or a real-opacity standard.", "rows": rows}
    save_json(output / "measurement_qualification.json", result)
    if not result["qualified"]:
        raise ValueError("stable visibility/readout qualification failed; GPU experiment blocked")
    return result


def preflight(cfg):
    times = sample_times(cfg)
    if len(times) != 45 or len(cfg["cases"]) != 4 or len({c["id"] for c in cfg["cases"]}) != 4:
        raise ValueError("expected four complete 45-sample sequences per background")
    body = np.column_stack([cfg["body_points_m"], np.ones(2)])
    counts, sigmas = {}, []
    for case in cfg["cases"]:
        counts[case["id"]] = {"fully_definite_frames": 0, "transition_point_count": 0}
        for timestamp in times:
            expected = reference(cfg, case, timestamp)
            points = np.asarray(expected["points_camera_m"])
            np.testing.assert_allclose((target_pose(cfg, timestamp) @ body.T).T[:, :3], points, atol=1e-12)
            uv = np.asarray(list(expected["uv"].values()))
            if np.min(points[:,2]) <= 1 or np.min(uv) < 10 or np.max(uv[:,0]) > 790 or np.max(uv[:,1]) > 440 or uv[1,0]-uv[0,0] < 50:
                raise ValueError("invalid or unresolved prescribed target input")
            counts[case["id"]]["fully_definite_frames"] += all(s != "transition" for s in expected["visibility"].values())
            counts[case["id"]]["transition_point_count"] += sum(s == "transition" for s in expected["visibility"].values())
            sigmas.extend(projected_sigma_bounds(cfg, point, cfg["marker_sigma_m"])[1] for point in points)
            if expected["visibility"]["right"] != "clear":
                raise ValueError("right marker must remain independently clear")
    if max(sigmas) > max(cfg["qualification"]["marker_sigmas_px"]):
        raise ValueError("marker profile size exceeds frozen qualification grid")
    return {"times_s": times, "primary_pair_count": 360, "new_RGB_count": 720, "per_case_reference_counts_per_background": counts,
            "marker_max_projected_sigma_px": max(sigmas), "meaning": "prescribed state sampling, not native dynamics or exposure timestamps"}


def render_pair(probe, cfg, case, timestamp, context):
    base, torch = probe.base, probe.torch
    world_body = base.c2w @ target_pose(cfg, timestamp)
    dynamics = {"probe": torch.tensor(world_body, device="cuda", dtype=torch.float32)}
    actors = {"probe": base.marker}
    occ = occluder_point(cfg, case, timestamp)
    if occ is not None:
        pose = np.eye(4)
        pose[:3,3] = occ
        dynamics["occluder"] = torch.tensor(base.c2w @ pose, device="cuda", dtype=torch.float32)
        actors["occluder"] = probe.occluder
    base.camera.dynamics = dynamics
    base.camera.timestamp = timestamp
    geometry, opacity = base.marker._xyz.clone(), base.marker._opacity.clone()
    occ_opacity = probe.occluder._opacity.clone()
    images = []
    for role in ("bright", "dim"):
        colours = [cfg["marker_codes"][key][role] for key in IDS]
        base.marker._features_dc[:] = ((torch.tensor(colours, device="cuda", dtype=torch.float32)-.5)/.28209479177387814)[:,None,:]
        with torch.no_grad():
            package = base.render(base.camera, None, base.isolated if context == "isolated" else base.scene, actors, None, base.background, render_optical=False)
        rgb = package["render"].detach()
        if not bool(torch.isfinite(rgb).all()):
            raise ValueError("nonfinite rendered RGB")
        images.append(np.rint(rgb.clamp(0,1).permute(1,2,0).cpu().numpy()*255).astype(np.uint8))
    if not torch.equal(geometry, base.marker._xyz) or not torch.equal(opacity, base.marker._opacity) or not torch.equal(occ_opacity, probe.occluder._opacity):
        raise ValueError("local geometry or opacity changed during RGB pair")
    return images, {"camera_timestamp_s": base.camera.timestamp, "camera_to_world_used_f32": base.camera.c2w.detach().cpu().tolist(),
                    "body_to_world_used_f32": dynamics["probe"].detach().cpu().tolist(),
                    "occluder_to_world_used_f32": None if occ is None else dynamics["occluder"].detach().cpu().tolist(), "geometry_and_opacity_preserved": True}


def summarize(rows):
    result = {}
    for program in PROGRAMS:
        judgements = [r["judgements"][program] for r in rows]
        checks = [c for j in judgements for c in j["point_checks"]]
        errors = [c["position_error_px"] for c in checks if c["position_error_px"] is not None]
        result[program] = {"readout_qualified_frames": sum(j["readout_qualified"] for j in judgements),
                           "fully_decidable_frames": sum(j["fully_decidable"] for j in judgements),
                           "fully_decidable_frames_passed": sum(j["fully_decidable"] and not j["violations"] for j in judgements),
                           "point_checks": len(checks), "violation_count": sum(len(j["violations"]) for j in judgements),
                           "frames_with_contradictions": sum(bool(j["violations"]) for j in judgements),
                           "max_qualified_clear_position_error_px": max(errors) if errors else None}
    return result


def event_brackets(cfg, rows):
    result = []
    for context in cfg["contexts"]:
        for case in cfg["cases"]:
            if case["kind"] != "front":
                continue
            sequence = [r for r in rows if r["context"] == context and r["case"] == case]
            hidden = [i for i,r in enumerate(sequence) if r["reference"]["visibility"]["left"] == "hidden"]
            first_hidden, last_hidden = hidden[0], hidden[-1]
            previous_clear = max(i for i in range(first_hidden) if sequence[i]["reference"]["visibility"]["left"] == "clear")
            next_clear = min(i for i in range(last_hidden+1,len(sequence)) if sequence[i]["reference"]["visibility"]["left"] == "clear")
            present = [any(f["identity"] == "left" for f in r["observation"]["features"]) if r["observation"]["identities_qualified"] else None for r in sequence]
            disappearance = next((sequence[i]["timestamp_s"] for i in range(previous_clear+1,first_hidden+1) if present[i] is False), None)
            reappearance = next((sequence[i]["timestamp_s"] for i in range(last_hidden+1,next_clear+1) if present[i] is True), None)
            result.append({"context": context, "case": case["id"], "independent_disappearance_bracket_s": [sequence[previous_clear]["timestamp_s"],sequence[first_hidden]["timestamp_s"]],
                           "independent_reappearance_bracket_s": [sequence[last_hidden]["timestamp_s"],sequence[next_clear]["timestamp_s"]],
                           "first_sampled_disappearance_in_bracket_s": disappearance, "first_sampled_reappearance_in_bracket_s": reappearance,
                           "scope": "operational coded-feature readout at sampled logical times, not exact physical opacity or real exposure time"})
    return result


def run(cfg, raw, config_path, output, qualify_only, log):
    started = time.monotonic()
    validity = preflight(cfg)
    model = Path(cfg["model_dir"])
    metadata = model / "meta_data.json"
    camera_record = next(r for r in json.loads(metadata.read_text())["frames"] if Path(r["rgb_path"]).stem == cfg["metadata_frame"] and Path(r["rgb_path"]).parent.name == cfg["camera"])
    if not np.array_equal(np.asarray(camera_record["intrinsics"])[:3,:3],cfg["suite"]["camera"]["intrinsics"]) or [camera_record["width"],camera_record["height"]] != [800,450]:
        raise ValueError("camera differs from frozen calibration")
    inputs = [config_path, ROOT/raw["base_config"], Path(__file__), metadata, model/"scene.pth", model/"cfg.yaml", GSPLAT_SOURCE,
              *(ROOT/"scripts"/name for name in ("measure_credibility_marker_identity.py","run_motion_observation_probe.py","run_motion_observation_boundary_probe.py","run_physics_alphabet_probe.py","run_physics_alphabet_variants.py")),
              Path(cfg["hugsim_repo"])/"gaussian_renderer/__init__.py"]
    env = {"started_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(), "cwd": str(Path.cwd()), "python": sys.executable,
           "role": "CPU motion-occlusion instrument qualification" if qualify_only else "HUGSIM prescribed motion and occlusion observation", "output": str(output), "argv": sys.argv,
           "audit_commit": git(ROOT,"rev-parse","HEAD"), "audit_status": git(ROOT,"status","--short"), "branch": git(ROOT,"branch","--show-current"), "remote": git(ROOT,"remote","-v"),
           "hugsim_commit": git(cfg["hugsim_repo"],"rev-parse","HEAD"), "hugsim_status": git(cfg["hugsim_repo"],"status","--short"),
           "input_hashes": {str(p):sha256(p) for p in inputs}, "resources_before": host_resources()}
    for name,value in (("environment",env),("config",cfg),("camera_record",camera_record),("input_validity",validity)):
        save_json(output/f"{name}.json",value)
    manifest = {case["id"]: {str(i): {p:reference(cfg,case,t,p) for p in PROGRAMS} for i,t in enumerate(sample_times(cfg))} for case in cfg["cases"]}
    save_json(output/"expectations_before_rgb.json",manifest)
    expected_hash = sha256(output/"expectations_before_rgb.json")
    log(f"preflight healthy; host={env['host']}; role={env['role']}; output={output}; expectations={expected_hash}")
    qualification = qualify(cfg,output)
    log(f"qualified {qualification['positive_pair_count']} independent stable 2D occlusion pairs; transition diagnostics retained")
    if qualify_only:
        return
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; use an approved GPU-visible context")
    if env["resources_before"]["disk_free_bytes"] < 2*1024**3:
        raise RuntimeError("less than 2 GiB for bounded sequence outputs")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.cuda.reset_peak_memory_stats()
    env.update({"torch":torch.__version__,"torch_cuda":torch.version.cuda,"gpu":torch.cuda.get_device_name(0)})
    save_json(output/"environment.json",env)
    probe = BoundaryProbe(cfg,camera_record)
    probe.base.marker._xyz[:] = torch.tensor(cfg["body_points_m"],device="cuda",dtype=torch.float32)
    rows = []
    for context in cfg["contexts"]:
        for case in cfg["cases"]:
            for frame,timestamp in enumerate(sample_times(cfg)):
                images,placement = render_pair(probe,cfg,case,timestamp,context)
                directory = output/"rgb"/context/case["id"]/f"{frame:03d}"
                directory.mkdir(parents=True)
                paths = [directory/"bright.png",directory/"dim.png"]
                for path,image in zip(paths,images,strict=True):
                    write_rgb(path,image)
                try:
                    obs = measure_tagged_pair(*images,cfg["suite"]["measurement"])
                except ValueError as error:
                    obs = {"features":[],"width_px":None,"identities_qualified":False,"readout_error":str(error)}
                expectations = manifest[case["id"]][str(frame)]
                truth = expectations["full"]
                row = {"context":context,"case":case,"frame":frame,"timestamp_s":timestamp,"placement":placement,"rgb":[str(p) for p in paths],"rgb_sha256":[sha256(p) for p in paths],
                       "observation":obs,"reference":truth,"predictions":expectations,"judgements":{p:judge(obs,expectations[p],truth,cfg) for p in PROGRAMS}}
                rows.append(row)
                save_json(directory/"record.json",row)
            log(f"{context}/{case['id']}: all 45 samples saved")
    save_json(output/"rows.json",rows)
    if sha256(output/"expectations_before_rgb.json") != expected_hash:
        raise ValueError("expectations changed after RGB")
    events = event_brackets(cfg,rows)
    save_json(output/"event_brackets.json",events)
    result = {"experiment_id":cfg["experiment_id"],"overall_evidence_label":"down-weighted","pair_count":len(rows),"new_RGB_count":2*len(rows),
              "statistics":summarize(rows),"reference_transition_frames":sum("transition" in r["reference"]["visibility"].values() for r in rows),
              "reference_transition_point_count":sum(sum(s=="transition" for s in r["reference"]["visibility"].values()) for r in rows),
              "events":events,"expectation_sha256_before_and_after":expected_hash,"new_RGB_used_for_fitting":False,
              "limitations":["Externally prescribed poses at logical timestamps; no native dynamics, exposure/delivery latency or AD test.",
                             "Gaussian coded-feature visibility bands qualified only on finite independent 2D alpha profiles; no physical-material opacity standard.",
                             "Transition-point positions and precise visibility onset remain unqualified; raw transition observations are diagnostics only.",
                             "One camera, two coded points, one scene and two backgrounds; no direct real-sim or complete mechanism alphabet claim."]}
    save_json(output/"summary.json",result)
    env.update({"elapsed_seconds":time.monotonic()-started,"peak_process_RSS_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                "peak_torch_GPU_reserved_bytes":torch.cuda.max_memory_reserved(),"resources_after":host_resources()})
    save_json(output/"environment.json",env)
    log(f"complete: {len(rows)} pairs; full statistics={result['statistics']['full']}; transition frames={result['reference_transition_frames']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--qualify-only",action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    save_json(output/"status.json",{"status":"running"})
    def log(message):
        line = f"{datetime.now(timezone.utc).isoformat()} {message}"
        print(line,flush=True)
        with (output/"run.log").open("a") as stream:
            stream.write(line+"\n")
    try:
        cfg,raw=load_config(args.config)
        run(cfg,raw,args.config.resolve(),output,args.qualify_only,log)
    except Exception as error:
        log(f"FAILED: {error}")
        (output/"failure.txt").write_text(traceback.format_exc())
        save_json(output/"status.json",{"status":"failed","error":str(error)})
        raise
    save_json(output/"status.json",{"status":"complete"})


if __name__ == "__main__":
    main()
