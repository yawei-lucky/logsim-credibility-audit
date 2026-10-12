#!/usr/bin/env python3
"""Qualify absolute marker positions, then render one new HUGSIM screening case.

Run in the existing HUGSIM environment with a new output directory. The optional
--qualify-only stage needs no GPU. Deliberately displaced inputs qualify the
screener; they are not evidence that HUGSIM itself has a placement defect.
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
from run_motion_observation_probe import (
    HugsimProbe, git, measure_pair, save_json, sha256, synthetic_pair, write_rgb,
)

ROOT = Path(__file__).resolve().parents[1]


def qualify(cfg, output):
    """Measure directly specified 2D centres, independent of HUGSIM projection."""
    suite, q = cfg["suite"], cfg["qualification"]
    height, width = suite["camera"]["height"], suite["camera"]["width"]
    yy, xx = np.indices((height, width))
    texture = np.stack([35 + xx % 41, 55 + yy % 37, 45 + (xx + yy) % 43], axis=-1).astype(np.uint8)
    rows = []
    for anchor, du, dv, sigma, bg_id in itertools.product(
        range(len(q["centres_uv_px"])), q["phases_u_px"], q["phases_v_px"],
        q["sigmas_px"], ("black", "texture"),
    ):
        centres = np.asarray(q["centres_uv_px"][anchor], dtype=np.float64) + [du, dv]
        background = np.zeros_like(texture) if bg_id == "black" else texture
        pair = synthetic_pair(background, centres, sigma, cfg["marker_opacity"], cfg["contrast_levels"])
        measurement = measure_pair(*pair, suite["measurement"])
        measured = np.asarray([[feature["u"], feature["v"]] for feature in measurement["features"]])
        residual = measured - centres
        rows.append({"anchor": anchor, "phase_u_px": du, "phase_v_px": dv,
                     "sigma_px": sigma, "background": bg_id,
                     "expected_uv_px": centres.tolist(), "measured_uv_px": measured.tolist(),
                     "position_residual_px": residual.tolist(),
                     "max_abs_position_error_px": float(np.max(np.abs(residual))),
                     "width_error_px": measurement["width_px"] - float(centres[1, 0] - centres[0, 0])})
    maximum = max(row["max_abs_position_error_px"] for row in rows)
    width_maximum = max(abs(row["width_error_px"]) for row in rows)
    position_budget = suite["measurement"]["position_error_bound_px"]
    width_budget = suite["measurement"]["width_error_bound_px"]
    result = {"count": len(rows), "max_abs_position_error_px": maximum,
              "max_abs_width_error_px": width_maximum, "position_budget_px": position_budget,
              "width_budget_px": width_budget,
              "qualified": maximum <= position_budget and width_maximum <= width_budget,
              "reference": "Direct 2D centres; no HUGSIM, camera state, depth or fitted corrections.",
              "scope": "Finite phase/size/position/background grid; not a universal or real-camera bound.",
              "rows": rows}
    save_json(output / "measurement_qualification.json", result)
    if not result["qualified"]:
        raise ValueError("absolute position measurement qualification failed; HUGSIM rendering blocked")
    return result


def render_pair(probe, context, camera_xyz, cfg):
    torch = probe.torch
    probe.marker._xyz[:] = torch.tensor(camera_xyz, dtype=torch.float32, device="cuda")
    probe.camera.dynamics = {"probe": torch.tensor(probe.c2w, dtype=torch.float32, device="cuda")}
    scene = probe.isolated if context == "isolated" else probe.scene
    images = []
    for level in cfg["contrast_levels"]:
        probe.marker._features_dc.fill_((level - 0.5) / 0.28209479177387814)
        with torch.no_grad():
            package = probe.render(probe.camera, None, scene, {"probe": probe.marker},
                                   None, probe.background, render_optical=False)
        rgb = package["render"].detach()
        if not bool(torch.isfinite(rgb).all()):
            raise ValueError("nonfinite HUGSIM RGB")
        images.append(np.rint(rgb.clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8))
    return images


def make_figure(rows, output):
    import cv2
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    contexts = list(dict.fromkeys(row["context"] for row in rows))
    figure, axes = plt.subplots(len(contexts), 3, figsize=(12, 6), squeeze=False)
    for axis, row in zip(axes.flat, rows, strict=True):
        image = cv2.cvtColor(cv2.imread(row["rgb"][0]), cv2.COLOR_BGR2RGB)
        expected = np.asarray(row["nominal_frame"]["expected_uv_px"])
        measured = np.asarray(row["nominal_frame"]["measured_uv_px"])
        # imshow's data coordinates follow the declared half-pixel convention.
        axis.imshow(image, extent=(0, image.shape[1], image.shape[0], 0))
        axis.scatter(expected[:, 0], expected[:, 1], marker="+", s=95, color="lime", label="prescribed")
        axis.scatter(measured[:, 0], measured[:, 1], marker="x", s=65, color="tomato", label="measured")
        axis.set_xlim(390, 520)
        axis.set_ylim(270, 200)
        frame = row["nominal_frame"]
        axis.set_title(f"{row['context']} / {row['condition']}\n"
                       f"width error {frame['width_residual_px']:.3f}px; "
                       f"position error {frame['max_abs_position_residual_px']:.3f}px",
                       fontsize=10)
        axis.set_xlabel("u (px)")
        axis.set_ylabel("v (px)")
    axes[0, 0].legend(loc="upper left", fontsize=8)
    figure.suptitle("Absolute position screening: same separation can hide a common displacement")
    figure.tight_layout()
    figure.savefig(output / "position_screening.png", dpi=150)
    plt.close(figure)


def run(cfg, config_path, output, qualify_only, log):
    suite = cfg["suite"]
    validate_suite(suite)
    if len(suite["cases"]) != 1 or len(suite["cases"][0]["frames"]) != 1:
        raise ValueError("this runner supports exactly one two-marker case/frame")
    if cfg["contexts"] != ["isolated", "scene0383_static"]:
        raise ValueError("this bounded runner requires the two declared contexts")
    conditions = cfg["conditions"]
    if [row["id"] for row in conditions] != ["nominal", "wrong_u", "wrong_v"]:
        raise ValueError("expected nominal, horizontal and vertical displacement controls")
    for row in conditions:
        delta = np.asarray(row["translation_camera_m"], dtype=np.float64)
        if delta.shape != (3,) or not np.isfinite(delta).all() or delta[2] != 0:
            raise ValueError("controls must be finite width-preserving in-plane translations")
        if row["expect_nominal_pass"] != bool(np.all(delta == 0)):
            raise ValueError("control expectation contradicts its displacement")
    model = Path(cfg["model_dir"])
    required = [config_path, Path(__file__), ROOT / "scripts/evaluate_credibility_screening.py",
                ROOT / "scripts/run_motion_observation_probe.py",
                model / "meta_data.json", model / "cfg.yaml", model / "scene.pth",
                Path(cfg["hugsim_repo"]) / "gaussian_renderer/__init__.py",
                Path(cfg["hugsim_repo"]) / "scene/cameras.py"]
    gsplat = importlib.util.find_spec("gsplat")
    if gsplat is None:
        raise RuntimeError("gsplat unavailable; use the existing HUGSIM Python environment")
    kernel = Path(gsplat.origin).parent / "cuda/csrc/rasterize_to_pixels_fwd.cu"
    required.append(kernel)
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"required input missing: {path}")
    record = next(row for row in json.loads((model / "meta_data.json").read_text())["frames"]
                  if Path(row["rgb_path"]).parent.name == cfg["camera"]
                  and Path(row["rgb_path"]).stem == cfg["metadata_frame"])
    if (record["width"], record["height"]) != (suite["camera"]["width"], suite["camera"]["height"]):
        raise ValueError("camera size differs from the frozen suite")
    if not np.array_equal(np.asarray(record["intrinsics"])[:3, :3], suite["camera"]["intrinsics"]):
        raise ValueError("camera intrinsics differ from the frozen suite")
    environment = {"started_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(),
                   "role": "CPU absolute-position qualification" if qualify_only else "bounded HUGSIM absolute-position screening",
                   "cwd": str(Path.cwd()), "pid": os.getpid(), "python": sys.executable,
                   "output": str(output), "argv": sys.argv,
                   "audit_commit": git(ROOT, "rev-parse", "HEAD"),
                   "audit_branch": git(ROOT, "branch", "--show-current"),
                   "audit_status": git(ROOT, "status", "--short"), "audit_remote": git(ROOT, "remote", "-v"),
                   "hugsim_commit": git(cfg["hugsim_repo"], "rev-parse", "HEAD"),
                   "hugsim_status": git(cfg["hugsim_repo"], "status", "--short"),
                   "hashes": {str(path): sha256(path) for path in required}}
    save_json(output / "environment.json", environment)
    save_json(output / "camera_reference.json", record)
    save_json(output / "suite.json", suite)
    log(f"input preflight healthy; host={platform.node()}; role={environment['role']}; output={output}")
    qualification = qualify(cfg, output)
    log(f"position measurement qualified: {qualification['count']} pairs, "
        f"max error={qualification['max_abs_position_error_px']:.6f}px")
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
    probe = HugsimProbe(cfg, record)
    nominal = np.asarray(suite["cases"][0]["frames"][0]["marker_camera_xyz_m"])
    rows = []
    for context, condition in itertools.product(cfg["contexts"], conditions):
        name = f"{context}_{condition['id']}"
        actual = nominal + condition["translation_camera_m"]
        world = (probe.c2w @ np.column_stack([actual, np.ones(2)]).T).T
        camera = (np.linalg.inv(probe.c2w) @ world.T).T
        transform_error = float(np.max(np.abs(camera[:, :3] / camera[:, 3:4] - actual)))
        if transform_error > 1e-5:
            raise ValueError("camera/world placement roundtrip exceeds 1e-5 m")
        images = render_pair(probe, context, actual, cfg)
        directory = output / "rgb" / name
        directory.mkdir(parents=True)
        rgb_paths = [directory / "bright.png", directory / "dim.png"]
        for path, image in zip(rgb_paths, images, strict=True):
            write_rgb(path, image)
        submission = {"schema_version": 1, "suite_id": suite["suite_id"],
                      "simulator": {"name": "HUGSIM prescribed-state screening", "version": environment["hugsim_commit"]},
                      "cases": [{"id": suite["cases"][0]["id"], "frames": [{
                          "id": "frame000", "capture_time_s": 0.0,
                          "bright": str(rgb_paths[0]), "dim": str(rgb_paths[1])}]}]}
        save_json(directory / "submission.json", submission)
        report = evaluate_submission(suite, submission, directory)
        actual_suite = copy.deepcopy(suite)
        actual_suite["cases"][0]["frames"][0]["marker_camera_xyz_m"] = actual.tolist()
        save_json(directory / "actual_state_suite.json", actual_suite)
        actual_report = evaluate_submission(actual_suite, submission, directory)
        width_suite = copy.deepcopy(suite)
        del width_suite["measurement"]["position_error_bound_px"]
        width_report = evaluate_submission(width_suite, submission, directory)
        for filename, value in (("nominal_report.json", report), ("actual_state_report.json", actual_report),
                                ("width_only_report.json", width_report)):
            save_json(directory / filename, value)
        frame = report["cases"][0]["frames"][0]
        row = {"context": context, "condition": condition["id"],
               "translation_camera_m": condition["translation_camera_m"],
               "actual_camera_xyz_m": actual.tolist(), "transform_max_error_m": transform_error,
               "rgb": [str(path) for path in rgb_paths], "rgb_sha256": [sha256(path) for path in rgb_paths],
               "expected_nominal_pass": condition["expect_nominal_pass"],
               "nominal_contract_passed": report["screening_contract_satisfied"],
               "actual_state_contract_passed": actual_report["screening_contract_satisfied"],
               "width_only_contract_passed": width_report["screening_contract_satisfied"],
               "nominal_frame": frame,
               "actual_state_frame": actual_report["cases"][0]["frames"][0]}
        rows.append(row)
        save_json(output / "rows.json", rows)
        log(f"{name}: nominal_pass={row['nominal_contract_passed']}; "
            f"actual_state_pass={row['actual_state_contract_passed']}; width_only_pass={row['width_only_contract_passed']}")
    positives = [row for row in rows if row["expected_nominal_pass"]]
    controls = [row for row in rows if not row["expected_nominal_pass"]]
    checks = {
        "position_measurement_qualified": qualification["qualified"],
        "nominal_positions_pass": all(row["nominal_contract_passed"] for row in positives),
        "all_rendered_positions_match_actual_commands": all(row["actual_state_contract_passed"] for row in rows),
        "width_only_misses_both_displacement_axes": all(row["width_only_contract_passed"] for row in rows),
        "displacements_rejected_as_measured_position_contradictions": all(
            not row["nominal_contract_passed"] and row["nominal_frame"]["tested"]
            and row["nominal_frame"]["failure_kind"] == "contradiction"
            and row["nominal_frame"]["width_within_budget"]
            and not row["nominal_frame"]["position_within_budget"] for row in controls),
        "placement_roundtrips_valid": all(row["transform_max_error_m"] <= 1e-5 for row in rows),
    }
    summary = {"experiment_id": cfg["experiment_id"], "overall_evidence_label": "down-weighted",
               "qualification_pair_count": qualification["count"], "rgb_render_count": 2 * len(rows),
               "nominal_pair_count": len(positives), "displaced_control_pair_count": len(controls),
               "max_nominal_position_error_px": max(row["nominal_frame"]["max_abs_position_residual_px"] for row in positives),
               "max_actual_state_position_error_px": max(row["actual_state_frame"]["max_abs_position_residual_px"] for row in rows),
               "max_abs_width_error_px": max(abs(row["nominal_frame"]["width_residual_px"]) for row in rows),
               "checks": checks, "all_preregistered_checks_passed": all(checks.values()),
               "limitations": ["One new placement, two contexts, one camera; no population generalization.",
                               "Deliberate common displacements qualify the screener, not a newly discovered HUGSIM defect.",
                               "Image left/right correspondence does not establish semantic marker identity.",
                               "No natural vehicle, real camera, AD response or driving-task equivalence was tested."]}
    save_json(output / "summary.json", summary)
    # Preserve all results before attempting the presentation figure.
    if all(row["nominal_frame"].get("measured_uv_px") for row in rows):
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
