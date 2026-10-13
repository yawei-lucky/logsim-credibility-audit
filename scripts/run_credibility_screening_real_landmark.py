#!/usr/bin/env python3
"""Render a frozen three-frame CAM_FRONT landmark diagnostic, without scoring it.

Use the existing HUGSIM environment in a GPU-visible context. The output must
be a new directory. Source-image candidate intervals are validated as inputs;
the runner neither annotates rendered RGB nor establishes strict real/sim pairs.
"""

from __future__ import annotations

import argparse
import binascii
import contextlib
import copy
import hashlib
import importlib.util
import json
import math
import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from render_hugsim_exact_source_pose import (
    CAMERAS,
    frame_camera,
    render_variants,
    select_camera_records,
)

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def resolve(path):
    path = Path(path).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


def git(repo, *args):
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Git inspection failed for {repo}: {result.stderr.strip()}")
    return result.stdout.strip()


def rigid_matrix(value, label):
    matrix = np.asarray(value, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError(f"{label}: expected a finite 4x4 transform")
    if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-7, rtol=0):
        raise ValueError(f"{label}: invalid homogeneous transform row")
    rotation = matrix[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5, rtol=0) or not np.isclose(np.linalg.det(rotation), 1, atol=1e-5, rtol=0):
        raise ValueError(f"{label}: transform rotation is not rigid")
    return matrix


def preflight(cfg):
    """CPU-only validation; no outputs, torch imports or renderer invocation."""

    import imageio.v2 as imageio

    indices = cfg["frame_indices"]
    if cfg["camera"] != "CAM_FRONT" or len(indices) != 3 or len(set(indices)) != 3 or any(type(index) is not int or index < 0 for index in indices):
        raise ValueError("this bounded runner requires three unique CAM_FRONT frame indices")
    if set(cfg["metadata"]) != {"released", "source_init"} or cfg["expected_render_count"] != 9:
        raise ValueError("expected exactly released/source_init plus wrong_yaw: nine renders")
    if cfg["strict_source_pair_gate_passed"] is not False:
        raise ValueError("this experiment cannot claim the strict source-pair gate passed")
    yaw = float(cfg["wrong_camera_yaw_degrees"])
    if not math.isfinite(yaw) or yaw != -5.0:
        raise ValueError("the frozen wrong-camera yaw intervention must be -5 degrees")
    reference_path = resolve(cfg["reference"])
    if sha256(reference_path) != cfg["reference_sha256"]:
        raise ValueError("frozen source-only reference SHA-256 mismatch")
    reference = json.loads(reference_path.read_text())
    if reference["reference_created_before_new_sim_outputs"] is not True:
        raise ValueError("reference must explicitly precede the new simulation outputs")
    real_root = resolve(cfg["real_root"])
    manifest_path = resolve(cfg["source_archive_manifest"])
    if resolve(reference["real_source_root"]) != real_root or resolve(reference["source_archive_manifest"]) != manifest_path:
        raise ValueError("config/reference source paths differ")
    if sha256(manifest_path) != reference["source_archive_manifest_sha256"]:
        raise ValueError("source archive manifest SHA-256 mismatch")
    selection_path = resolve(reference["selection_record"])
    if sha256(selection_path) != reference["selection_record_sha256"]:
        raise ValueError("frozen raw-window selection SHA-256 mismatch")
    manifest = json.loads(manifest_path.read_text())
    members = manifest["members"]
    if len(members) != 3 or manifest["member_count"] != 3 or len({member["name"] for member in members}) != 3:
        raise ValueError("source manifest must contain exactly three distinct raw RGB members")
    member_by_name = {member["name"]: member for member in members}
    reference_frames = reference["frames"]
    if len(reference_frames) != 3 or [frame["frame_index"] for frame in reference_frames] != indices:
        raise ValueError("source-reference frames must match the frozen declared order")
    band = np.asarray(reference["band_y_px"], dtype=float)
    if band.shape != (2,) or not np.isfinite(band).all() or not (0 <= band[0] < band[1] <= 450):
        raise ValueError("invalid source-reference vertical band")
    hashes = {str(reference_path): sha256(reference_path), str(manifest_path): sha256(manifest_path), str(selection_path): sha256(selection_path)}
    source_rows = []
    for frame in reference_frames:
        index = frame["frame_index"]
        name = f"data/scene-0383/images/CAM_FRONT/{index:05d}.jpg"
        member = member_by_name.get(name)
        if member is None:
            raise ValueError(f"raw RGB archive member absent: {name}")
        raw_path = resolve(frame["rgb_path"])
        expected_path = real_root / f"images/CAM_FRONT/{index:05d}.jpg"
        if raw_path != expected_path or member["output_relative_path"] != str(expected_path.relative_to(real_root)):
            raise ValueError(f"raw RGB path/member mismatch for frame {index}")
        payload = raw_path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        crc = binascii.crc32(payload) & 0xFFFFFFFF
        if digest != frame["rgb_sha256"] or digest != member["sha256"] or crc != member["crc32"] or len(payload) != member["uncompressed_size"]:
            raise ValueError(f"raw RGB SHA-256/CRC/size mismatch for frame {index}")
        rgb = imageio.imread(raw_path)
        if rgb.shape != (450, 800, 3) or rgb.dtype != np.uint8:
            raise ValueError(f"raw CAM_FRONT RGB must decode to uint8 800x450: {raw_path}")
        interval = np.asarray(frame["u_interval_px"], dtype=float)
        if frame["visibility"] != "visible" or interval.shape != (2,) or not np.isfinite(interval).all() or not (0 <= interval[0] <= interval[1] < 800):
            raise ValueError(f"invalid frozen visible landmark interval for frame {index}")
        if not math.isfinite(float(frame["timestamp_s"])):
            raise ValueError(f"invalid frozen reference timestamp for frame {index}")
        hashes[str(raw_path)] = digest
        source_rows.append({"frame_index": index, "rgb_path": str(raw_path), "rgb_sha256": digest, "archive_member": name, "crc32": crc, "size_bytes": len(payload), "decoded_size": [800, 450], "u_interval_px": frame["u_interval_px"]})
    metadata_paths = {label: resolve(path) for label, path in cfg["metadata"].items()}
    metadata = {label: json.loads(path.read_text()) for label, path in metadata_paths.items()}
    native_ids = set()
    for label, content in metadata.items():
        hashes[str(metadata_paths[label])] = sha256(metadata_paths[label])
        for frame in reference_frames:
            records = select_camera_records(content, frame["frame_index"])
            if list(records) != list(CAMERAS):
                raise ValueError("full six-camera metadata group validation failed")
            for camera, record in records.items():
                if float(record["timestamp"]) != frame["timestamp_s"]:
                    raise ValueError(f"{label}/{camera}: source-reference timestamp mismatch")
                rigid_matrix(record["camtoworld"], f"{label}/{camera}/camtoworld")
                intrinsics = np.asarray(record["intrinsics"], dtype=float)
                if intrinsics.shape not in ((3, 3), (4, 4)) or not np.isfinite(intrinsics).all() or intrinsics[0, 0] <= 0 or intrinsics[1, 1] <= 0:
                    raise ValueError(f"{label}/{camera}: invalid camera intrinsics")
                if camera == "CAM_FRONT" and (record["width"], record["height"]) != (800, 450):
                    raise ValueError(f"{label}: CAM_FRONT dimensions differ from raw RGB")
                for actor_id, pose in record.get("dynamics", {}).items():
                    rigid_matrix(pose, f"{label}/{camera}/dynamic/{actor_id}")
                    native_ids.add(actor_id)
    model_dir = resolve(cfg["model_dir"])
    for name in ["cfg.yaml", "scene.pth", "meta_data.json", *(f"dynamic_{actor_id}.pth" for actor_id in sorted(native_ids))]:
        path = model_dir / name
        if not path.is_file() or not path.stat().st_size:
            raise FileNotFoundError(f"required HUGSIM model input absent or empty: {path}")
        hashes[str(path)] = sha256(path)
    hugsim_repo = resolve(cfg["hugsim_repo"])
    if not (hugsim_repo / "gaussian_renderer/__init__.py").is_file():
        raise FileNotFoundError(f"HUGSIM renderer unavailable at {hugsim_repo}")
    return {"reference": reference, "reference_path": reference_path, "metadata": metadata, "metadata_paths": metadata_paths, "source_rows": source_rows, "source_hashes": hashes, "native_dynamic_ids": sorted(native_ids), "real_root": real_root, "manifest_path": manifest_path, "model_dir": model_dir, "hugsim_repo": hugsim_repo}


def wrong_yaw_metadata(released, indices, yaw_degrees):
    """Rotate only selected CAM_FRONT c2w rotations about camera-local Y."""

    result = copy.deepcopy(released)
    angle = math.radians(yaw_degrees)
    yaw = np.array([[math.cos(angle), 0, math.sin(angle)], [0, 1, 0], [-math.sin(angle), 0, math.cos(angle)]])
    rows = []
    for source, changed in zip(released["frames"], result["frames"], strict=True):
        index = int(Path(source["rgb_path"]).stem)
        if index not in indices or frame_camera(source) != "CAM_FRONT":
            if source != changed:
                raise ValueError("unselected metadata record changed")
            continue
        before = rigid_matrix(source["camtoworld"], f"frame {index} before yaw")
        after = before.copy()
        after[:3, :3] = before[:3, :3] @ yaw
        changed["camtoworld"] = after.tolist()
        rigid_matrix(after, f"frame {index} after yaw")
        untouched = [key for key in source if key != "camtoworld"]
        if any(source[key] != changed[key] for key in untouched) or not np.array_equal(before[:3, 3], after[:3, 3]):
            raise ValueError("wrong-yaw intervention altered nonrotation inputs")
        rows.append({"frame_index": index, "camera": "CAM_FRONT", "yaw_degrees": yaw_degrees, "axis": "camera-local Y", "composition": "R_after = R_released @ R_y", "camtoworld_before": before.tolist(), "camtoworld_after": after.tolist(), "translation_unchanged": True, "intrinsics_timestamp_and_dynamics_unchanged": True})
    if len(rows) != 3:
        raise ValueError("wrong-yaw intervention must modify exactly three front-camera records")
    return result, rows


class Tee:
    def __init__(self, original, log):
        self.original, self.log = original, log

    def write(self, text):
        self.original.write(text)
        self.log.write(text)
        self.log.flush()
        return len(text)

    def flush(self):
        self.original.flush()
        self.log.flush()


def execute(cfg, config_path, output):
    def log(message):
        print(f"{datetime.now(timezone.utc).isoformat()} {message}", flush=True)

    status_path = output / "execution_status.json"
    environment = {"started_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(), "role": "frozen real-image landmark render diagnostic; no automated landmark scoring", "cwd": os.getcwd(), "output": str(output), "python": sys.executable, "argv": sys.argv, "audit_commit": git(ROOT, "rev-parse", "HEAD"), "audit_branch": git(ROOT, "branch", "--show-current"), "audit_status": git(ROOT, "status", "--short"), "audit_remotes": git(ROOT, "remote", "-v"), "config_path": str(config_path), "config_sha256": sha256(config_path), "runner_sha256": sha256(__file__)}
    save_json(output / "environment.json", environment)
    save_json(status_path, {"status": "preflight", "role": environment["role"], "host": environment["host"], "output": str(output)})
    log(f"starting; host={environment['host']}; cwd={environment['cwd']}; output={output}")
    inputs = preflight(cfg)
    environment.update({"source_hashes": inputs["source_hashes"], "hugsim_commit": git(inputs["hugsim_repo"], "rev-parse", "HEAD"), "hugsim_branch": git(inputs["hugsim_repo"], "branch", "--show-current"), "hugsim_status": git(inputs["hugsim_repo"], "status", "--short"), "hugsim_remotes": git(inputs["hugsim_repo"], "remote", "-v"), "renderer_script_sha256": sha256(ROOT / "scripts/render_hugsim_exact_source_pose.py")})
    save_json(output / "environment.json", environment)
    save_json(output / "input_preflight.json", {"healthy": True, "reference_sha256": cfg["reference_sha256"], "source_rows": inputs["source_rows"], "full_six_camera_groups_validated": True, "native_dynamic_ids": inputs["native_dynamic_ids"], "strict_source_pair_gate_passed": False})
    log("CPU input preflight healthy; raw image SHA-256/CRC/size/decode and complete metadata groups verified")
    if importlib.util.find_spec("gsplat") is None:
        raise RuntimeError("gsplat is unavailable; run with /home/yawei/HUGSIM/.pixi/envs/default/bin/python")
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; run in an approved GPU-visible context with the existing HUGSIM environment")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    np.random.seed(0)
    environment.update({"torch_version": torch.__version__, "cuda_version": torch.version.cuda, "gpu": torch.cuda.get_device_name(0), "seed": 0})
    save_json(output / "environment.json", environment)
    log(f"GPU preflight healthy; device={environment['gpu']}")
    altered, interventions = wrong_yaw_metadata(inputs["metadata"]["released"], cfg["frame_indices"], cfg["wrong_camera_yaw_degrees"])
    metadata_dir = output / "metadata"
    metadata_dir.mkdir()
    wrong_path = metadata_dir / "wrong_yaw.json"
    save_json(wrong_path, altered)
    save_json(output / "intervention_record.json", {"reference_metadata_path": str(inputs["metadata_paths"]["released"]), "reference_metadata_sha256": sha256(inputs["metadata_paths"]["released"]), "wrong_metadata_path": str(wrong_path), "wrong_metadata_sha256": sha256(wrong_path), "modified_records": interventions, "all_other_metadata_records_unchanged": True, "claim": "Deliberately commanded wrong-camera condition, not a discovered HUGSIM defect."})
    metadata_paths = {"released": inputs["metadata_paths"]["released"], "source_init": inputs["metadata_paths"]["source_init"], "wrong_yaw": wrong_path}
    frame_dir = output / "frames"
    frame_dir.mkdir()
    images, frame_runs = [], []
    for index in cfg["frame_indices"]:
        destination = frame_dir / f"frame_{index:05d}"
        save_json(status_path, {"status": "rendering", "frame_index": index, "completed_rgb_count": len(images), "expected_rgb_count": 9, "output": str(output)})
        log(f"rendering frame {index:05d}; camera=CAM_FRONT; variants=released/source_init/wrong_yaw; native dynamics retained")
        args = argparse.Namespace(hugsim_repo=inputs["hugsim_repo"], model_dir=inputs["model_dir"], real_root=inputs["real_root"], metadata=[f"{label}={path}" for label, path in metadata_paths.items()], omit_dynamics=[], dynamic_checkpoint=[], frame_index=index, source_archive_manifest=inputs["manifest_path"], output=destination, camera=["CAM_FRONT"])
        report = render_variants(args)
        if report["camera_order"] != ["CAM_FRONT"] or set(report["variants"]) != set(metadata_paths):
            raise ValueError("renderer returned an unexpected camera or variant set")
        for label, variant in report["variants"].items():
            if list(variant["camera_results"]) != ["CAM_FRONT"] or variant["native_dynamics_omitted"]:
                raise ValueError("renderer omitted native dynamics or rendered unexpected cameras")
            row = variant["camera_results"]["CAM_FRONT"]
            record = select_camera_records(altered if label == "wrong_yaw" else inputs["metadata"][label], index, ["CAM_FRONT"])["CAM_FRONT"]
            if row["native_dynamic_ids"] != sorted(record.get("dynamics", {})):
                raise ValueError("rendered native dynamic IDs differ from declared metadata")
            if sha256(row["render_path"]) != row["render_sha256"]:
                raise ValueError("rendered RGB SHA-256 mismatch")
            images.append({"frame_index": index, "variant": label, "camera": "CAM_FRONT", "timestamp_s": row["timestamp_s"], "render_path": row["render_path"], "render_sha256": row["render_sha256"], "real_path": row["real_path"], "real_sha256": row["real_sha256"], "intrinsics": record["intrinsics"], "camtoworld": record["camtoworld"], "dynamics": record.get("dynamics", {}), "native_dynamic_ids": row["native_dynamic_ids"], "full_metadata_camera_group_validated": True, "landmark_annotation": None, "position_decision": "unmeasured_pending_frozen_image_reading"})
        manifest_path = destination / "exact_pose_render.json"
        frame_runs.append({"frame_index": index, "manifest_path": str(manifest_path), "manifest_sha256": sha256(manifest_path), "healthy": True, "rgb_count": 3})
        save_json(output / "render_progress.json", {"images": images, "frame_runs": frame_runs})
        log(f"frame {index:05d} healthy; 3/3 RGB written; landmark result remains unmeasured")
    if len(images) != cfg["expected_render_count"]:
        raise ValueError("render count differs from the frozen nine-image design")
    summary = {"experiment_id": cfg["experiment_id"], "execution_status": "complete", "rendering_complete": True, "render_count": len(images), "expected_render_count": 9, "camera": "CAM_FRONT", "frame_indices": cfg["frame_indices"], "reference_path": str(inputs["reference_path"]), "reference_sha256": cfg["reference_sha256"], "strict_source_pair_gate_passed": False, "automatic_landmark_scoring": False, "position_comparison_performed": False, "vehicle_question": inputs["reference"]["vehicle_question"], "images": images, "frame_runs": frame_runs, "claim_boundary": "Nine RGB outputs under three declared metadata variants. The frozen raw-RGB landmark intervals are Codex candidate readings, not human ground truth or qualified camera uncertainty. No physical equivalence, simulator pass rate, AD result or strict matched real-sim claim is made."}
    save_json(output / "summary.json", summary)
    save_json(status_path, {"status": "complete", "healthy": True, "completed_rgb_count": len(images), "output": str(output), "finished_utc": datetime.now(timezone.utc).isoformat(), "landmark_scoring_performed": False})
    log("complete; 9/9 prescribed RGB outputs available; this is an execution count, not a simulator pass rate")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config_path, output = args.config.resolve(), args.output.resolve()
    if output.exists():
        parser.error(f"refusing to overwrite existing output: {output}")
    output.mkdir(parents=True)
    with (output / "run.log").open("w") as stream:
        with contextlib.redirect_stdout(Tee(sys.stdout, stream)), contextlib.redirect_stderr(Tee(sys.stderr, stream)):
            try:
                cfg = json.loads(config_path.read_text())
                execute(cfg, config_path, output)
            except Exception as error:
                failure = traceback.format_exc()
                (output / "failure.txt").write_text(failure)
                save_json(output / "execution_status.json", {"status": "failed", "healthy": False, "error": str(error), "output": str(output), "finished_utc": datetime.now(timezone.utc).isoformat()})
                print(failure, file=sys.stderr, flush=True)
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
