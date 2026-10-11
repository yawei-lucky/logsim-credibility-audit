#!/usr/bin/env python3
"""Re-render frozen six-camera trajectories in one fresh process per frame."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CAMERAS = (
    "CAM_BACK",
    "CAM_BACK_LEFT",
    "CAM_BACK_RIGHT",
    "CAM_FRONT",
    "CAM_FRONT_LEFT",
    "CAM_FRONT_RIGHT",
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def resolve(path):
    path = Path(path).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True
    ).strip()


def validate_rigid_transform(value, label):
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError(f"{label}: transform must be a finite 4x4 matrix")
    if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-6):
        raise ValueError(f"{label}: invalid homogeneous last row")
    rotation = matrix[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5):
        raise ValueError(f"{label}: rotation is not orthonormal")
    if not np.isclose(np.linalg.det(rotation), 1.0, atol=1e-5):
        raise ValueError(f"{label}: rotation determinant is not one")
    return matrix


def preflight_trajectory(cfg, metadata_path):
    metadata = json.loads(metadata_path.read_text())
    selected_frames = [frame for window in cfg["windows"] for frame in window["frames"]]
    if len(selected_frames) != len(set(selected_frames)):
        raise ValueError("configured frames must be unique across windows")
    expected_dynamic = set(cfg["expected_native_dynamic_ids"])
    details, expected_by_frame = [], {}
    for window in cfg["windows"]:
        if window["frames"] != sorted(set(window["frames"])):
            raise ValueError(f"{window['id']}: frames must be unique and increasing")
        timestamps, camera_pose_signatures, dynamic_pose_signatures = [], [], []
        for frame_index in window["frames"]:
            records = {}
            for record in metadata.get("frames", []):
                path = PurePosixPath(record["rgb_path"])
                if int(path.stem) != frame_index:
                    continue
                camera = path.parent.name
                if camera in records:
                    raise ValueError(f"{window['id']}/{frame_index}: duplicate {camera}")
                records[camera] = record
            if set(records) != set(CAMERAS):
                raise ValueError(f"{window['id']}/{frame_index}: incomplete camera group")
            frame_timestamps = {float(record["timestamp"]) for record in records.values()}
            if len(frame_timestamps) != 1:
                raise ValueError(f"{window['id']}/{frame_index}: timestamps differ")
            timestamp = frame_timestamps.pop()
            timestamps.append(timestamp)
            camera_details = {}
            dynamic_ids = set()
            for camera in CAMERAS:
                record = records[camera]
                intrinsics = np.asarray(record["intrinsics"], dtype=np.float64)
                if intrinsics.shape not in {(3, 3), (4, 4)} or not np.isfinite(intrinsics).all():
                    raise ValueError(f"{window['id']}/{frame_index}/{camera}: invalid K")
                c2w = validate_rigid_transform(
                    record["camtoworld"], f"{window['id']}/{frame_index}/{camera}/c2w"
                )
                camera_pose_signatures.append(c2w.tobytes())
                dynamics = {}
                for dynamic_id, matrix in record.get("dynamics", {}).items():
                    dynamic = validate_rigid_transform(
                        matrix,
                        f"{window['id']}/{frame_index}/{camera}/dynamic/{dynamic_id}",
                    )
                    dynamic_ids.add(dynamic_id)
                    dynamic_pose_signatures.append(dynamic.tobytes())
                    dynamics[dynamic_id] = dynamic.tolist()
                camera_details[camera] = {
                    "width": int(record["width"]),
                    "height": int(record["height"]),
                    "dynamic_ids": sorted(dynamics),
                }
            if dynamic_ids != expected_dynamic:
                raise ValueError(
                    f"{window['id']}/{frame_index}: native dynamic ids differ from config"
                )
            expected_by_frame[frame_index] = {
                "timestamp_s": timestamp,
                "cameras": camera_details,
                "native_dynamic_ids": sorted(dynamic_ids),
            }
            details.append(
                {
                    "window": window["id"],
                    "frame_index": frame_index,
                    "timestamp_s": timestamp,
                    "native_dynamic_ids": sorted(dynamic_ids),
                }
            )
        if any(second <= first for first, second in zip(timestamps, timestamps[1:])):
            raise ValueError(f"{window['id']}: timestamps must be strictly increasing")
        if len(set(camera_pose_signatures)) <= len(CAMERAS):
            raise ValueError(f"{window['id']}: camera trajectory does not vary")
        if len(set(dynamic_pose_signatures)) <= 1:
            raise ValueError(f"{window['id']}: native dynamic trajectory does not vary")
    return {
        "frame_count": len(selected_frames),
        "camera_record_count": len(selected_frames) * len(CAMERAS),
        "details": details,
        "expected_by_frame": expected_by_frame,
    }


def load_golden_window(window, metadata_path):
    manifest_path = resolve(window["golden_manifest"])
    manifest = json.loads(manifest_path.read_text())
    expected_frames = list(window["frames"])
    if manifest["variant"] != "factual":
        raise ValueError(f"{manifest_path}: golden variant is not factual")
    if manifest["frame_indices"] != expected_frames:
        raise ValueError(f"{manifest_path}: frame list differs from config")
    if manifest["camera_order"] != list(CAMERAS):
        raise ValueError(f"{manifest_path}: camera order differs from frozen set")
    if manifest["copied_image_count"] != len(expected_frames) * len(CAMERAS):
        raise ValueError(f"{manifest_path}: incomplete golden image count")
    if manifest["metadata_source_sha256"] != sha256(metadata_path):
        raise ValueError(f"{manifest_path}: metadata hash mismatch")

    golden_root = manifest_path.parent
    report_cache = {}
    images = []
    seen = set()
    contract = {
        "hugsim_commits": set(),
        "scene_checkpoint_sha256": set(),
        "cfg_sha256": set(),
        "driver_sha256": set(),
        "native_dynamic_sha256": {},
        "render_report_sha256": set(),
    }
    for item in manifest["images"]:
        frame, camera = int(item["frame_index"]), item["camera"]
        key = (frame, camera)
        if key in seen:
            raise ValueError(f"{manifest_path}: duplicate golden key {key}")
        seen.add(key)
        path = golden_root / "images" / camera / f"{frame:05d}.png"
        actual_hash = sha256(path)
        if actual_hash != item["destination_sha256"]:
            raise ValueError(f"{path}: golden PNG hash mismatch")
        report_path = Path(item["render_report"]).resolve()
        if sha256(report_path) != item["render_report_sha256"]:
            raise ValueError(f"{report_path}: historical report hash mismatch")
        if report_path not in report_cache:
            report_cache[report_path] = json.loads(report_path.read_text())
        report = report_cache[report_path]
        if int(report["frame_index"]) != frame:
            raise ValueError(f"{report_path}: historical frame mismatch")
        camera_result = report["variants"]["factual"]["camera_results"][camera]
        if camera_result["render_sha256"] != item["source_sha256"]:
            raise ValueError(f"{report_path}: historical source hash mismatch")
        contract["hugsim_commits"].add(report["hugsim"]["commit"])
        contract["scene_checkpoint_sha256"].add(
            report["hugsim"]["scene_checkpoint_sha256"]
        )
        contract["cfg_sha256"].add(report["hugsim"]["cfg_sha256"])
        contract["driver_sha256"].add(report["script_sha256"])
        contract["render_report_sha256"].add(item["render_report_sha256"])
        for dynamic_id in camera_result["native_dynamic_ids"]:
            values = contract["native_dynamic_sha256"].setdefault(dynamic_id, set())
            values.add(report["hugsim"]["dynamic_checkpoint_sha256"][dynamic_id])
        images.append(
            {
                "window": window["id"],
                "frame_index": frame,
                "camera": camera,
                "path": str(path),
                "sha256": actual_hash,
                "historical_report": str(report_path),
                "historical_driver_sha256": report["script_sha256"],
            }
        )
    expected = {(frame, camera) for frame in expected_frames for camera in CAMERAS}
    if seen != expected:
        raise ValueError(f"{manifest_path}: golden key set is incomplete")
    normalized_contract = {
        key: sorted(value) if isinstance(value, set) else value
        for key, value in contract.items()
    }
    normalized_contract["native_dynamic_sha256"] = {
        key: sorted(value)
        for key, value in contract["native_dynamic_sha256"].items()
    }
    return {
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "images": images,
        "contract": normalized_contract,
    }


def verify_current_assets(cfg, golden_windows):
    hugsim_repo = resolve(cfg["hugsim_repo"])
    model_dir = resolve(cfg["model_dir"])
    current = {
        "hugsim_commit": git(hugsim_repo, "rev-parse", "HEAD"),
        "scene_checkpoint_sha256": sha256(model_dir / "scene.pth"),
        "cfg_sha256": sha256(model_dir / "cfg.yaml"),
        "native_dynamic_sha256": {},
    }
    expected_commits = set()
    expected_scene = set()
    expected_cfg = set()
    expected_dynamic = {}
    for window in golden_windows:
        contract = window["contract"]
        expected_commits.update(contract["hugsim_commits"])
        expected_scene.update(contract["scene_checkpoint_sha256"])
        expected_cfg.update(contract["cfg_sha256"])
        for dynamic_id, hashes in contract["native_dynamic_sha256"].items():
            expected_dynamic.setdefault(dynamic_id, set()).update(hashes)
    if expected_commits != {current["hugsim_commit"]}:
        raise ValueError("current HUGSIM commit differs from golden contract")
    if expected_scene != {current["scene_checkpoint_sha256"]}:
        raise ValueError("current scene checkpoint differs from golden contract")
    if expected_cfg != {current["cfg_sha256"]}:
        raise ValueError("current scene config differs from golden contract")
    for dynamic_id, hashes in expected_dynamic.items():
        path = model_dir / f"dynamic_{dynamic_id}.pth"
        current_hash = sha256(path)
        current["native_dynamic_sha256"][dynamic_id] = current_hash
        if hashes != {current_hash}:
            raise ValueError(f"current dynamic checkpoint differs for {dynamic_id}")
    return current


def validate_child_report(
    report_path,
    frame_index,
    driver_hash,
    metadata_hash,
    current_assets,
    expected,
):
    report = json.loads(report_path.read_text())
    if int(report["frame_index"]) != frame_index:
        raise ValueError(f"{report_path}: output frame mismatch")
    if list(report["variants"]) != ["factual"]:
        raise ValueError(f"{report_path}: expected only factual variant")
    if report["script_sha256"] != driver_hash:
        raise ValueError(f"{report_path}: driver hash drift")
    if report["hugsim"]["commit"] != current_assets["hugsim_commit"]:
        raise ValueError(f"{report_path}: HUGSIM commit drift")
    if report["hugsim"]["scene_checkpoint_sha256"] != current_assets["scene_checkpoint_sha256"]:
        raise ValueError(f"{report_path}: scene checkpoint drift")
    if report["hugsim"]["cfg_sha256"] != current_assets["cfg_sha256"]:
        raise ValueError(f"{report_path}: cfg drift")
    if not np.isclose(report["timestamp_s"], expected["timestamp_s"], atol=1e-9):
        raise ValueError(f"{report_path}: timestamp drift")
    if report["source"]["real_reference_available"]:
        raise ValueError(f"{report_path}: regression child unexpectedly used real RGB")
    if report["camera_order"] != list(CAMERAS):
        raise ValueError(f"{report_path}: camera order drift")
    variant = report["variants"]["factual"]
    if variant["metadata_sha256"] != metadata_hash:
        raise ValueError(f"{report_path}: metadata hash drift")
    if variant["native_dynamics_omitted"]:
        raise ValueError(f"{report_path}: native dynamics were unexpectedly omitted")
    if set(report["hugsim"]["dynamic_checkpoint_sha256"]) != set(
        current_assets["native_dynamic_sha256"]
    ):
        raise ValueError(f"{report_path}: dynamic checkpoint key set drift")
    results = variant["camera_results"]
    if set(results) != set(CAMERAS):
        raise ValueError(f"{report_path}: incomplete camera result")
    for camera, result in results.items():
        camera_expected = expected["cameras"][camera]
        if result["width"] != camera_expected["width"] or result["height"] != camera_expected["height"]:
            raise ValueError(f"{report_path}: {camera} dimensions drift")
        if not np.isclose(result["timestamp_s"], expected["timestamp_s"], atol=1e-9):
            raise ValueError(f"{report_path}: {camera} timestamp drift")
        if result["native_dynamic_ids"] != expected["native_dynamic_ids"]:
            raise ValueError(f"{report_path}: {camera} native dynamic ids drift")
        for dynamic_id in result["native_dynamic_ids"]:
            if report["hugsim"]["dynamic_checkpoint_sha256"][dynamic_id] != current_assets["native_dynamic_sha256"][dynamic_id]:
                raise ValueError(f"{report_path}: {dynamic_id} checkpoint drift")
    return report


def build_child_command(python, driver, hugsim_repo, model_dir, metadata, frame_index, output):
    return [
        str(Path(python).resolve()),
        str(Path(driver).resolve()),
        "--hugsim-repo",
        str(Path(hugsim_repo).resolve()),
        "--model-dir",
        str(Path(model_dir).resolve()),
        "--no-real-reference",
        "--metadata",
        f"factual={Path(metadata).resolve()}",
        "--frame-index",
        str(frame_index),
        "--output",
        str(Path(output).resolve()),
    ]


def run(cfg, config_path, output, log):
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; use an approved GPU-visible context")
    driver = resolve(cfg["render_driver"])
    metadata = resolve(cfg["metadata"])
    hugsim_repo = resolve(cfg["hugsim_repo"])
    model_dir = resolve(cfg["model_dir"])
    required = [
        config_path,
        Path(__file__).resolve(),
        driver,
        resolve(cfg["comparison_script"]),
        resolve(cfg["preregistration"]),
        metadata,
        model_dir / "cfg.yaml",
        model_dir / "scene.pth",
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    if sha256(driver) != cfg["expected_current_driver_sha256"]:
        raise ValueError("current render driver hash differs from frozen config")
    golden_windows = [load_golden_window(window, metadata) for window in cfg["windows"]]
    current_assets = verify_current_assets(cfg, golden_windows)
    trajectory = preflight_trajectory(cfg, metadata)
    metadata_hash = sha256(metadata)
    import imageio
    import imageio.v2 as imageio_v2
    import gsplat
    import cv2
    import skimage
    environment = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "role": "fixed-trajectory six-camera render regression",
        "cwd": str(Path.cwd()),
        "python": sys.executable,
        "python_hash_seed_for_children": cfg["python_hash_seed"],
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "numpy": np.__version__,
        "imageio": imageio.__version__,
        "gsplat": gsplat.__version__,
        "opencv": cv2.__version__,
        "scikit_image": skimage.__version__,
        "gpu": torch.cuda.get_device_name(0),
        "gpu_driver": subprocess.check_output(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            text=True,
        ).splitlines()[0],
        "audit_commit": git(ROOT, "rev-parse", "HEAD"),
        "audit_branch": git(ROOT, "branch", "--show-current"),
        "audit_status": git(ROOT, "status", "--short"),
        "audit_remote": git(ROOT, "remote", "-v"),
        "hugsim_status": git(hugsim_repo, "status", "--short"),
        "current_assets": current_assets,
        "child_environment": {
            "PYTHONHASHSEED": cfg["python_hash_seed"],
            "MPLBACKEND": "Agg",
            "CUDA_HOME": os.environ.get("CUDA_HOME"),
            "TORCH_CUDA_ARCH_LIST": os.environ.get("TORCH_CUDA_ARCH_LIST"),
            "PATH": os.environ.get("PATH"),
        },
        "hashes": {str(path): sha256(path) for path in required},
        "historical_contracts": [window["contract"] for window in golden_windows],
    }
    save_json(output / "environment.json", environment)
    save_json(output / "golden_preflight.json", golden_windows)
    save_json(output / "trajectory_preflight.json", trajectory)
    log(
        "preflight healthy; golden PNGs=96; "
        f"current_driver={sha256(driver)[:12]}; GPU={environment['gpu']}"
    )

    child_env = os.environ.copy()
    child_env["PYTHONHASHSEED"] = cfg["python_hash_seed"]
    child_env["MPLBACKEND"] = "Agg"
    processes, images = [], []
    golden_by_key = {
        (image["window"], image["frame_index"], image["camera"]): image
        for window in golden_windows
        for image in window["images"]
    }
    for window in cfg["windows"]:
        for frame_index in window["frames"]:
            frame_output = output / "renders" / window["id"] / f"frame_{frame_index:05d}"
            frame_output.parent.mkdir(parents=True, exist_ok=True)
            child_log = output / "child_logs" / window["id"] / f"frame_{frame_index:05d}.log"
            child_log.parent.mkdir(parents=True, exist_ok=True)
            command = build_child_command(
                sys.executable,
                driver,
                hugsim_repo,
                model_dir,
                metadata,
                frame_index,
                frame_output,
            )
            started = time.monotonic()
            started_utc = datetime.now(timezone.utc).isoformat()
            timed_out = False
            with child_log.open("w") as stream:
                try:
                    result = subprocess.run(
                        command,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        env=child_env,
                        timeout=cfg["child_timeout_s"],
                        check=False,
                    )
                    returncode = result.returncode
                except subprocess.TimeoutExpired:
                    timed_out, returncode = True, None
                    stream.write("\nORCHESTRATOR TIMEOUT\n")
            process = {
                "window": window["id"],
                "frame_index": frame_index,
                "command": command,
                "cwd": str(Path.cwd()),
                "started_utc": started_utc,
                "finished_utc": datetime.now(timezone.utc).isoformat(),
                "child_log": str(child_log.relative_to(output)),
                "duration_s": time.monotonic() - started,
                "returncode": returncode,
                "timed_out": timed_out,
                "completed": False,
                "failure": None,
            }
            try:
                if timed_out or returncode != 0:
                    raise RuntimeError(
                        "child timed out" if timed_out else f"child exit {returncode}"
                    )
                report_path = frame_output / "exact_pose_render.json"
                report = validate_child_report(
                    report_path,
                    frame_index,
                    sha256(driver),
                    metadata_hash,
                    current_assets,
                    trajectory["expected_by_frame"][frame_index],
                )
                process["report"] = str(report_path.relative_to(output))
                process["report_sha256"] = sha256(report_path)
                for camera in CAMERAS:
                    path = frame_output / "factual" / f"{camera}.png"
                    result = report["variants"]["factual"]["camera_results"][camera]
                    image_hash = sha256(path)
                    if image_hash != result["render_sha256"]:
                        raise ValueError(f"{path}: child report hash mismatch")
                    decoded = imageio_v2.imread(path)
                    expected_shape = (
                        trajectory["expected_by_frame"][frame_index]["cameras"][camera]["height"],
                        trajectory["expected_by_frame"][frame_index]["cameras"][camera]["width"],
                        3,
                    )
                    if decoded.shape != expected_shape or decoded.dtype != np.uint8:
                        raise ValueError(f"{path}: decoded RGB contract mismatch")
                    if not np.isfinite(decoded).all():
                        raise ValueError(f"{path}: decoded RGB is non-finite")
                    key = (window["id"], frame_index, camera)
                    golden = golden_by_key[key]
                    images.append(
                        {
                            "window": window["id"],
                            "frame_index": frame_index,
                            "camera": camera,
                            "path": str(path.relative_to(output)),
                            "sha256": image_hash,
                            "shape": list(decoded.shape),
                            "dtype": str(decoded.dtype),
                            "golden_path": golden["path"],
                            "golden_sha256": golden["sha256"],
                        }
                    )
                process["completed"] = True
            except Exception as error:
                process["failure"] = str(error)
            processes.append(process)
            log(
                f"{window['id']}/{frame_index:05d}: "
                f"{'complete' if process['completed'] else 'failed'} "
                f"in {process['duration_s']:.2f}s"
            )
    failed = [process for process in processes if not process["completed"]]
    unique_by_window_camera = {}
    for window in cfg["windows"]:
        for camera in CAMERAS:
            values = {
                image["sha256"]
                for image in images
                if image["window"] == window["id"] and image["camera"] == camera
            }
            unique_by_window_camera[f"{window['id']}/{camera}"] = len(values)
    manifest = {
        "experiment_id": cfg["experiment_id"],
        "process_count": len(processes),
        "completed_process_count": len(processes) - len(failed),
        "failed_process_count": len(failed),
        "expected_image_count": 96,
        "image_count": len(images),
        "unique_png_hash_count_by_window_camera": unique_by_window_camera,
        "trajectory_output_varies": all(value > 1 for value in unique_by_window_camera.values()),
        "processes": processes,
        "images": images,
    }
    save_json(output / "render_manifest.json", manifest)
    if failed:
        raise RuntimeError(f"{len(failed)} child render processes failed")
    if len(images) != 96:
        raise RuntimeError(f"expected 96 images, found {len(images)}")
    if not manifest["trajectory_output_varies"]:
        raise RuntimeError("at least one window/camera produced constant RGB across frames")
    log("completed 16 child processes and 96 six-camera RGB renders")


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
