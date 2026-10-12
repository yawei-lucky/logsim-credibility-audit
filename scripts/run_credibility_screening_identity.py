#!/usr/bin/env python3
"""Qualify coded marker identity, then test left/right HUGSIM occlusion.

Use the existing HUGSIM Python environment and a new output directory.
--qualify-only is CPU-only. Swapped codes are deliberate test inputs, not
newly discovered HUGSIM defects.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import itertools
import json
import os
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from evaluate_credibility_screening import evaluate_submission, validate_suite
from measure_credibility_marker_identity import measure_tagged_pair, synthetic_tagged_pair
from run_motion_observation_boundary_probe import BoundaryProbe
from run_motion_observation_probe import git, save_json, sha256, write_rgb

ROOT = Path(__file__).resolve().parents[1]


def qualify(cfg, output):
    q, suite = cfg["qualification"], cfg["suite"]
    yy, xx = np.indices((suite["camera"]["height"], suite["camera"]["width"]))
    texture = np.stack([35 + xx % 41, 55 + yy % 37, 45 + (xx + yy) % 43], axis=-1).astype(np.uint8)
    rows = []
    for template_id, du, dv, sigma, bg_id, mix_id in itertools.product(
        range(len(q["templates"])), q["phases_u_px"], q["phases_v_px"], q["sigmas_px"],
        ("black", "texture"), range(len(q["mixes"])),
    ):
        template = q["templates"][template_id]
        centres = np.asarray(template["centres"]) + [du, dv]
        bright = [cfg["marker_codes"][identity]["bright"] for identity in template["ids"]]
        dim = [cfg["marker_codes"][identity]["dim"] for identity in template["ids"]]
        background = np.zeros_like(texture) if bg_id == "black" else texture
        pair = synthetic_tagged_pair(background, centres, bright, dim, sigma, cfg["marker_opacity"], q["mixes"][mix_id])
        observation = measure_tagged_pair(*pair, suite["measurement"])
        measured = np.asarray([[feature["u"], feature["v"]] for feature in observation["features"]])
        observed_ids = [feature["identity"] for feature in observation["features"]]
        if measured.shape != centres.shape:
            raise ValueError("qualification component count mismatch")
        width_error = None if len(centres) == 1 else observation["width_px"] - float(centres[1, 0] - centres[0, 0])
        rows.append({"template": template_id, "phase_u_px": du, "phase_v_px": dv,
                     "sigma_px": sigma, "background": bg_id, "mix_id": mix_id,
                     "expected_ids": template["ids"], "observed_ids": observed_ids,
                     "identity_correct": observed_ids == template["ids"],
                     "max_abs_position_error_px": float(np.max(np.abs(measured - centres))),
                     "width_error_px": width_error,
                     "minimum_code_fraction": min(feature["channel_fractions_rgb"][suite["measurement"]["identity_channels"][identity]]
                                                   for feature, identity in zip(observation["features"], template["ids"], strict=True))})
    negatives = {}
    for name, centres, bright, dim in [
        ("ambiguous", [[469.75, 228.25]], [[0.9, 0.2, 0.9]], [[0.1, 0.2, 0.1]]),
        ("unknown_green", [[469.75, 228.25]], [[0.2, 0.9, 0.2]], [[0.2, 0.1, 0.2]]),
        ("boundary", [[0.5, 228.25]], [[0.9, 0.2, 0.2]], [[0.1, 0.2, 0.2]]),
    ]:
        pair = synthetic_tagged_pair(texture, centres, bright, dim, 1.2, cfg["marker_opacity"])
        try:
            observation = measure_tagged_pair(*pair, suite["measurement"])
            negatives[name] = {"blocked": not observation["identities_qualified"],
                               "observed_ids": [feature["identity"] for feature in observation["features"]]}
        except ValueError as error:
            negatives[name] = {"blocked": name == "boundary", "reason": str(error)}
    maximum = max(row["max_abs_position_error_px"] for row in rows)
    width_maximum = max(abs(row["width_error_px"]) for row in rows if row["width_error_px"] is not None)
    result = {"count": len(rows), "correct_identity_pair_count": sum(row["identity_correct"] for row in rows),
              "max_abs_position_error_px": maximum, "max_abs_width_error_px": width_maximum,
              "minimum_code_fraction": min(row["minimum_code_fraction"] for row in rows),
              "position_budget_px": suite["measurement"]["position_error_bound_px"],
              "width_budget_px": suite["measurement"]["width_error_bound_px"],
              "identity_min_channel_fraction": suite["measurement"]["identity_min_channel_fraction"],
              "negative_controls": negatives,
              "qualified": all(row["identity_correct"] for row in rows)
                           and maximum <= suite["measurement"]["position_error_bound_px"]
                           and width_maximum <= suite["measurement"]["width_error_bound_px"]
                           and all(row["blocked"] for row in negatives.values()),
              "scope": "Finite independent 2D code/phase/size/background/mixing grid; not natural object identity or a real-camera bound.",
              "rows": rows}
    save_json(output / "measurement_qualification.json", result)
    if not result["qualified"]:
        raise ValueError("identity measurement qualification failed; HUGSIM rendering blocked")
    return result


def render_tagged_pair(probe, context, points, ids, occluder, cfg):
    base, torch = probe.base, probe.torch
    base.marker._xyz[:] = torch.tensor(points, dtype=torch.float32, device="cuda")
    pose = torch.tensor(base.c2w, dtype=torch.float32, device="cuda")
    base.camera.dynamics = {"probe": pose}
    gaussians = {"probe": base.marker}
    if occluder is not None:
        probe.occluder._xyz[:] = torch.tensor([occluder], dtype=torch.float32, device="cuda")
        base.camera.dynamics["occluder"] = pose
        gaussians["occluder"] = probe.occluder
    scene = base.isolated if context == "isolated" else base.scene
    original_opacity = base.marker._opacity.detach().clone()
    images = []
    for role in ("bright", "dim"):
        colours = torch.tensor([cfg["marker_codes"][identity][role] for identity in ids], dtype=torch.float32, device="cuda")
        base.marker._features_dc[:] = ((colours - 0.5) / 0.28209479177387814)[:, None, :]
        with torch.no_grad():
            package = base.render(base.camera, None, scene, gaussians, None, base.background, render_optical=False)
        rgb = package["render"].detach()
        if not bool(torch.isfinite(rgb).all()):
            raise ValueError("nonfinite HUGSIM RGB")
        images.append(np.rint(rgb.clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8))
    if not torch.equal(base.marker._opacity, original_opacity):
        raise ValueError("marker opacity changed; this must be an occluder experiment, not explicit removal")
    return images


def make_figure(rows, output):
    import cv2
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(2, 5, figsize=(16, 6), squeeze=False)
    for axis, row in zip(axes.flat, rows, strict=True):
        frame = row["nominal_frame"]
        image = cv2.cvtColor(cv2.imread(row["rgb"][0]), cv2.COLOR_BGR2RGB)
        axis.imshow(image, extent=(0, image.shape[1], image.shape[0], 0))
        for feature in frame["measurement"]["features"]:
            axis.scatter(feature["u"], feature["v"], marker="x", color="lime", s=50)
            axis.text(feature["u"] + 3, feature["v"] - 4, str(feature["identity"]), color="lime", fontsize=9)
        axis.set_xlim(405, 493)
        axis.set_ylim(250, 210)
        outcome = "PASS" if row["nominal_contract_passed"] else "REJECT"
        axis.set_title(f"{row['context']}\n{row['condition']}\n"
                       f"expected: {frame['expected_visible_ids']} / {outcome}", fontsize=9)
        axis.set_xlabel("u (px)")
        axis.set_ylabel("v (px)")
    figure.suptitle("Occlusion identity screening: a correct count and location can still hide a wrong code")
    figure.tight_layout()
    figure.savefig(output / "identity_screening.png", dpi=150)
    plt.close(figure)


def run(cfg, config_path, output, qualify_only, log):
    suite = cfg["suite"]
    validate_suite(suite)
    if [case["id"] for case in suite["cases"]] != ["both_visible", "occlude_left", "occlude_right"]:
        raise ValueError("expected the three frozen baseline cases")
    if cfg["contexts"] != ["isolated", "scene0383_static"] or len(cfg["conditions"]) != 5:
        raise ValueError("expected two contexts and five render conditions")
    planned_conditions = [
        ("both_visible", "both_visible", None, False),
        ("occlude_left", "occlude_left", 0, False),
        ("occlude_right", "occlude_right", 1, False),
        ("wrong_right_identity", "occlude_left", 0, True),
        ("wrong_left_identity", "occlude_right", 1, True),
    ]
    if [(row["id"], row["case_id"], row["occluded_index"], row["swap_codes"]) for row in cfg["conditions"]] != planned_conditions:
        raise ValueError("render conditions differ from the bounded baseline and identity controls")
    baseline_points = suite["cases"][0]["frames"][0]["marker_camera_xyz_m"]
    for case, visible in zip(suite["cases"], (["left", "right"], ["right"], ["left"]), strict=True):
        if len(case["frames"]) != 1:
            raise ValueError("this runner supports one frame per case")
        frame = case["frames"][0]
        if frame["id"] != "frame000" or frame["capture_time_s"] != 0 or frame["marker_ids"] != ["left", "right"]:
            raise ValueError("case frame metadata differs from the frozen runner contract")
        if frame["marker_camera_xyz_m"] != baseline_points or frame["expected_visible_ids"] != visible:
            raise ValueError("baseline positions or independently planned survivor IDs are inconsistent")
    if cfg["occluder_depth_offset_m"] >= 0:
        raise ValueError("identity occlusion requires a front occluder")
    model = Path(cfg["model_dir"])
    required = [config_path, Path(__file__), ROOT / "scripts/evaluate_credibility_screening.py",
                ROOT / "scripts/measure_credibility_marker_identity.py",
                ROOT / "scripts/run_motion_observation_probe.py", ROOT / "scripts/run_motion_observation_boundary_probe.py",
                model / "meta_data.json", model / "cfg.yaml", model / "scene.pth",
                Path(cfg["hugsim_repo"]) / "gaussian_renderer/__init__.py", Path(cfg["hugsim_repo"]) / "scene/cameras.py"]
    spec = importlib.util.find_spec("gsplat")
    if spec is None:
        raise RuntimeError("gsplat unavailable; use the existing HUGSIM environment")
    required.append(Path(spec.origin).parent / "cuda/csrc/rasterize_to_pixels_fwd.cu")
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"required input missing: {path}")
    record = next(row for row in json.loads((model / "meta_data.json").read_text())["frames"]
                  if Path(row["rgb_path"]).parent.name == cfg["camera"] and Path(row["rgb_path"]).stem == cfg["metadata_frame"])
    if (record["width"], record["height"]) != (suite["camera"]["width"], suite["camera"]["height"]) or not np.array_equal(
        np.asarray(record["intrinsics"])[:3, :3], suite["camera"]["intrinsics"]
    ):
        raise ValueError("camera differs from frozen intrinsics/size")
    environment = {"started_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(),
                   "role": "CPU coded-identity qualification" if qualify_only else "bounded HUGSIM occlusion-identity screening",
                   "cwd": str(Path.cwd()), "pid": os.getpid(), "python": sys.executable, "output": str(output), "argv": sys.argv,
                   "audit_commit": git(ROOT, "rev-parse", "HEAD"), "audit_status": git(ROOT, "status", "--short"),
                   "audit_branch": git(ROOT, "branch", "--show-current"), "audit_remote": git(ROOT, "remote", "-v"),
                   "hugsim_commit": git(cfg["hugsim_repo"], "rev-parse", "HEAD"), "hugsim_status": git(cfg["hugsim_repo"], "status", "--short"),
                   "hashes": {str(path): sha256(path) for path in required}}
    save_json(output / "environment.json", environment)
    save_json(output / "camera_reference.json", record)
    save_json(output / "suite.json", suite)
    log(f"input preflight healthy; host={platform.node()}; role={environment['role']}; output={output}")
    qualification = qualify(cfg, output)
    log(f"identity qualified: {qualification['count']} pairs; max position error={qualification['max_abs_position_error_px']:.6f}px")
    if qualify_only:
        return
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; use an approved GPU-visible context")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    environment.update({"torch": torch.__version__, "gpu": torch.cuda.get_device_name(0)})
    save_json(output / "environment.json", environment)
    log(f"GPU preflight healthy: {environment['gpu']}")
    probe = BoundaryProbe(cfg, record)
    cases = {case["id"]: case for case in suite["cases"]}
    k = np.asarray(suite["camera"]["intrinsics"])
    rows = []
    for context, condition in itertools.product(cfg["contexts"], cfg["conditions"]):
        case = cases[condition["case_id"]]
        points = np.asarray(case["frames"][0]["marker_camera_xyz_m"])
        ids = ["right", "left"] if condition["swap_codes"] else ["left", "right"]
        index = condition["occluded_index"]
        occluder, geometry = None, None
        if index is not None:
            target = points[index]
            depth = target[2] + cfg["occluder_depth_offset_m"]
            if not 0 < depth < target[2]:
                raise ValueError("occluder is not between camera and target")
            occluder = target * (depth / target[2])
            a, b = k @ target, k @ occluder
            alignment = float(np.max(np.abs(a[:2] / a[2] - b[:2] / b[2])))
            if alignment > 1e-9:
                raise ValueError("occluder does not align with the intended target")
            geometry = {"target_index": index, "target_camera_xyz_m": target.tolist(),
                        "occluder_camera_xyz_m": occluder.tolist(), "ray_alignment_error_px": alignment,
                        "front_depth_gap_m": float(target[2] - depth), "marker_opacity_unchanged": True}
        images = render_tagged_pair(probe, context, points, ids, occluder, cfg)
        directory = output / "rgb" / f"{context}_{condition['id']}"
        directory.mkdir(parents=True)
        paths = [directory / "bright.png", directory / "dim.png"]
        for path, image in zip(paths, images, strict=True):
            write_rgb(path, image)
        submitted_case = {"id": case["id"], "frames": [{"id": "frame000", "capture_time_s": 0.0,
                                                       "bright": str(paths[0]), "dim": str(paths[1])}]}
        row = {"context": context, "condition": condition["id"], "case_id": case["id"],
               "swap_codes": condition["swap_codes"], "actual_marker_ids": ids,
               "occluded_index": index, "occlusion_geometry": geometry,
               "rgb": [str(path) for path in paths], "rgb_sha256": [sha256(path) for path in paths],
               "submitted_case": submitted_case}
        rows.append(row)
        save_json(output / "rows.json", rows)
        log(f"rendered {context}/{condition['id']}")
    simulator = {"name": "HUGSIM controlled coded-marker occlusion", "version": environment["hugsim_commit"]}
    for context in cfg["contexts"]:
        baseline_cases = [row["submitted_case"] for row in rows if row["context"] == context and not row["swap_codes"]]
        for row in [item for item in rows if item["context"] == context]:
            submission = {"schema_version": 1, "suite_id": suite["suite_id"], "simulator": simulator, "cases": copy.deepcopy(baseline_cases)}
            if row["swap_codes"]:
                submission["cases"] = [row["submitted_case"] if case["id"] == row["case_id"] else case for case in submission["cases"]]
            actual_suite = copy.deepcopy(suite)
            actual_case = next(case for case in actual_suite["cases"] if case["id"] == row["case_id"])
            actual_case["frames"][0]["marker_ids"] = row["actual_marker_ids"]
            actual_case["frames"][0]["expected_visible_ids"] = row["actual_marker_ids"] if row["occluded_index"] is None else [row["actual_marker_ids"][1 - row["occluded_index"]]]
            count_suite = copy.deepcopy(suite)
            for key in ("identity_channels", "identity_min_channel_fraction", "position_error_bound_px"):
                del count_suite["measurement"][key]
            directory = output / "rgb" / f"{context}_{row['condition']}"
            reports = {}
            for name, reference in (("nominal", suite), ("actual_state", actual_suite), ("count_only", count_suite)):
                report = evaluate_submission(reference, submission, directory)
                save_json(directory / f"{name}_report.json", report)
                reports[name] = report
            save_json(directory / "submission.json", submission)
            save_json(directory / "actual_state_suite.json", actual_suite)
            frame = next(case for case in reports["nominal"]["cases"] if case["id"] == row["case_id"])["frames"][0]
            actual_frame = next(case for case in reports["actual_state"]["cases"] if case["id"] == row["case_id"])["frames"][0]
            row.update({"nominal_contract_passed": reports["nominal"]["screening_contract_satisfied"],
                        "actual_state_contract_passed": reports["actual_state"]["screening_contract_satisfied"],
                        "count_only_contract_passed": reports["count_only"]["screening_contract_satisfied"],
                        "nominal_frame": frame, "actual_state_frame": actual_frame})
            log(f"{context}/{row['condition']}: observed={frame.get('observed_visible_ids')}; nominal_pass={row['nominal_contract_passed']}")
    save_json(output / "rows.json", rows)
    good = [row for row in rows if not row["swap_codes"]]
    faults = [row for row in rows if row["swap_codes"]]
    singles = [row for row in rows if row["occluded_index"] is not None]
    checks = {"measurement_qualified": qualification["qualified"],
              "all_baseline_cases_pass": all(row["nominal_contract_passed"] for row in good),
              "all_actual_coded_states_pass": all(row["actual_state_contract_passed"] for row in rows),
              "count_only_misses_swapped_survivor_codes": all(row["count_only_contract_passed"] for row in faults),
              "wrong_survivor_ids_are_measured_contradictions": all(
                  not row["nominal_contract_passed"] and row["nominal_frame"]["tested"]
                  and row["nominal_frame"]["failure_kind"] == "contradiction"
                  and row["nominal_frame"].get("unlabelled_position_within_budget")
                  and row["nominal_frame"].get("identity_within_contract") is False for row in faults),
              "single_marker_never_invents_full_width": all(row["nominal_frame"].get("measured_width_px") is None for row in singles)}
    known_errors = [row["actual_state_frame"]["max_abs_identity_position_residual_px"] for row in rows
                    if row["actual_state_frame"].get("max_abs_identity_position_residual_px") is not None]
    summary = {"experiment_id": cfg["experiment_id"], "overall_evidence_label": "down-weighted",
               "qualification_pair_count": qualification["count"], "rendered_pair_count": len(rows), "rgb_render_count": 2 * len(rows),
               "baseline_pair_count": len(good), "swapped_code_control_pair_count": len(faults),
               "max_actual_identity_position_error_px": max(known_errors) if known_errors else None,
               "checks": checks, "all_preregistered_checks_passed": all(checks.values()),
               "limitations": ["Two controlled RGB codes, one camera, one placement and two backgrounds only.",
                               "Swapped-code controls qualify the screener; they are not newly discovered HUGSIM identity defects.",
                               "Gaussian occlusion and coded identity do not qualify ordinary vehicles, real-camera identity or AD equivalence."]}
    save_json(output / "summary.json", summary)
    if all(row["nominal_frame"].get("measurement") for row in rows):
        make_figure(rows, output)
    log(f"completed {summary['rgb_render_count']} RGB renders; checks_passed={summary['all_preregistered_checks_passed']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--qualify-only", action="store_true")
    args = parser.parse_args()
    config_path, output = args.config.resolve(), args.output.resolve()
    cfg = json.loads(config_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "config.json", cfg)
    save_json(output / "status.json", {"status": "running", "pid": os.getpid()})

    def log(message):
        line = f"{datetime.now(timezone.utc).isoformat()} {message}"
        print(line, flush=True)
        with (output / "run.log").open("a") as stream:
            stream.write(line + "\n")

    try:
        run(cfg, config_path, output, args.qualify_only, log)
    except Exception as error:
        log(f"FAILED: {error}")
        (output / "failure.txt").write_text(traceback.format_exc())
        save_json(output / "status.json", {"status": "failed", "reason": str(error)})
        raise
    save_json(output / "status.json", {"status": "complete"})


if __name__ == "__main__":
    main()
