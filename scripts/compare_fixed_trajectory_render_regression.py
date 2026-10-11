#!/usr/bin/env python3
"""Compare two current fixed-trajectory runs with each other and goldens."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from pathlib import Path

import cv2
import numpy as np
import skimage


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_metrics(first, second):
    if first is None or second is None or first.shape != second.shape:
        raise ValueError("decoded image shape mismatch")
    if first.dtype != np.uint8 or second.dtype != np.uint8:
        raise ValueError("decoded images must be uint8")
    delta = first.astype(np.int16) - second.astype(np.int16)
    absolute = np.abs(delta)
    mse = float(np.mean(delta.astype(np.float64) ** 2))
    try:
        from skimage.metrics import structural_similarity

        ssim = float(
            structural_similarity(first, second, channel_axis=-1, data_range=255)
        )
    except ImportError:
        ssim = None
    changed = np.argwhere(np.any(delta != 0, axis=2))
    return {
        "pixel_exact": bool(np.array_equal(first, second)),
        "max_abs_uint8": int(absolute.max()),
        "mae_uint8": float(absolute.mean()),
        "mse_uint8": mse,
        "psnr_db": None if mse == 0 else float(20 * math.log10(255 / math.sqrt(mse))),
        "psnr_infinite": mse == 0,
        "ssim": ssim,
        "changed_channel_count": int(np.count_nonzero(delta)),
        "changed_pixel_count": int(np.count_nonzero(np.any(delta != 0, axis=2))),
        "first_changed_yxc": (
            None
            if not np.any(delta)
            else [int(value) for value in np.argwhere(delta != 0)[0]]
        ),
        "changed_bbox_xyxy": (
            None
            if not len(changed)
            else [
                int(changed[:, 1].min()),
                int(changed[:, 0].min()),
                int(changed[:, 1].max()),
                int(changed[:, 0].max()),
            ]
        ),
    }


def load_run(root):
    root = Path(root).resolve()
    status = json.loads((root / "status.json").read_text())
    if status["status"] != "complete":
        raise ValueError(f"{root}: run is not complete")
    manifest = json.loads((root / "render_manifest.json").read_text())
    if (
        manifest.get("process_count") != 16
        or manifest.get("completed_process_count") != 16
        or manifest.get("failed_process_count") != 0
        or manifest.get("expected_image_count") != 96
        or manifest.get("image_count") != 96
        or not manifest.get("trajectory_output_varies")
    ):
        raise ValueError(f"{root}: incomplete render manifest")
    config_path = root / "config.json"
    config = json.loads(config_path.read_text())
    if manifest["experiment_id"] != config["experiment_id"]:
        raise ValueError(f"{root}: experiment id differs between config and manifest")
    expected_processes = {
        (window["id"], int(frame))
        for window in config["windows"]
        for frame in window["frames"]
    }
    if len(expected_processes) != 16:
        raise ValueError(f"{root}: config does not declare 16 unique frames")
    processes = {}
    normalized_commands = []
    for process in manifest["processes"]:
        key = (process["window"], int(process["frame_index"]))
        if key in processes:
            raise ValueError(f"{root}: duplicate child process key {key}")
        if (
            not process["completed"]
            or process["returncode"] != 0
            or process["timed_out"]
            or process["failure"] is not None
        ):
            raise ValueError(f"{root}: child process is not healthy for {key}")
        command = list(process["command"])
        if command.count("--output") != 1:
            raise ValueError(f"{root}: child output argument is invalid for {key}")
        output_index = command.index("--output") + 1
        expected_output = root / "renders" / key[0] / f"frame_{key[1]:05d}"
        if Path(command[output_index]).resolve() != expected_output:
            raise ValueError(f"{root}: child output path drift for {key}")
        command[output_index] = "<RUN_OUTPUT>"
        normalized_commands.append({"key": list(key), "command": command, "cwd": process["cwd"]})
        report_path = root / process["report"]
        if sha256(report_path) != process["report_sha256"]:
            raise ValueError(f"{root}: child report hash mismatch for {key}")
        processes[key] = process
    if set(processes) != expected_processes:
        raise ValueError(f"{root}: child process key set differs from config")
    indexed = {}
    for row in manifest["images"]:
        key = (row["window"], int(row["frame_index"]), row["camera"])
        if key in indexed:
            raise ValueError(f"{root}: duplicate image key {key}")
        path = root / row["path"]
        if sha256(path) != row["sha256"]:
            raise ValueError(f"{path}: current PNG hash mismatch")
        golden = Path(row["golden_path"])
        if sha256(golden) != row["golden_sha256"]:
            raise ValueError(f"{golden}: golden PNG hash mismatch")
        indexed[key] = {**row, "resolved_path": path, "resolved_golden": golden}
    expected_images = {
        (window["id"], int(frame), camera)
        for window in config["windows"]
        for frame in window["frames"]
        for camera in (
            "CAM_BACK",
            "CAM_BACK_LEFT",
            "CAM_BACK_RIGHT",
            "CAM_FRONT",
            "CAM_FRONT_LEFT",
            "CAM_FRONT_RIGHT",
        )
    }
    if set(indexed) != expected_images:
        raise ValueError(f"{root}: image key set differs from config")
    environment_path = root / "environment.json"
    environment = json.loads(environment_path.read_text())
    environment.pop("started_utc", None)
    contract = {
        "experiment_id": manifest["experiment_id"],
        "config_sha256": sha256(config_path),
        "config": config,
        "environment": environment,
        "golden_preflight_sha256": sha256(root / "golden_preflight.json"),
        "trajectory_preflight_sha256": sha256(root / "trajectory_preflight.json"),
        "normalized_process_commands": sorted(
            normalized_commands, key=lambda item: tuple(item["key"])
        ),
    }
    return root, manifest, indexed, contract


def comparison(first_path, second_path):
    first = cv2.imread(str(first_path), cv2.IMREAD_COLOR)
    second = cv2.imread(str(second_path), cv2.IMREAD_COLOR)
    metrics = image_metrics(first, second)
    metrics["png_byte_exact"] = sha256(first_path) == sha256(second_path)
    return metrics


def aggregate(rows, field):
    group = [row[field] for row in rows]
    ssims = [item["ssim"] for item in group if item["ssim"] is not None]
    return {
        "png_byte_exact_count": sum(item["png_byte_exact"] for item in group),
        "pixel_exact_count": sum(item["pixel_exact"] for item in group),
        "max_abs_uint8": max(item["max_abs_uint8"] for item in group),
        "max_mae_uint8": max(item["mae_uint8"] for item in group),
        "max_changed_channel_count": max(
            item["changed_channel_count"] for item in group
        ),
        "max_changed_pixel_count": max(item["changed_pixel_count"] for item in group),
        "min_ssim": min(ssims) if ssims else None,
    }


def compare_runs(left_root, right_root):
    if Path(left_root).resolve() == Path(right_root).resolve():
        raise ValueError("left and right must be distinct run directories")
    left_root, left_manifest, left, left_contract = load_run(left_root)
    right_root, right_manifest, right, right_contract = load_run(right_root)
    if left_contract != right_contract:
        raise ValueError("left and right frozen run contracts differ")
    if set(left) != set(right) or len(left) != 96:
        raise ValueError("run image key sets differ from the expected 96")
    rows = []
    for key in sorted(left):
        first, second = left[key], right[key]
        if first["golden_sha256"] != second["golden_sha256"]:
            raise ValueError(f"{key}: runs reference different goldens")
        rows.append(
            {
                "window": key[0],
                "frame_index": key[1],
                "camera": key[2],
                "run_to_run": comparison(first["resolved_path"], second["resolved_path"]),
                "left_to_golden": comparison(
                    first["resolved_path"], first["resolved_golden"]
                ),
                "right_to_golden": comparison(
                    second["resolved_path"], second["resolved_golden"]
                ),
                "left_sha256": first["sha256"],
                "right_sha256": second["sha256"],
                "golden_sha256": first["golden_sha256"],
                "left_path": str(first["resolved_path"]),
                "right_path": str(second["resolved_path"]),
                "golden_path": str(first["resolved_golden"]),
            }
        )
    result = {
        "experiment_id": left_manifest["experiment_id"],
        "comparison_environment": {
            "host": platform.node(),
            "python": sys.executable,
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "scikit_image": skimage.__version__,
            "comparison_script_sha256": sha256(Path(__file__).resolve()),
            "left_manifest_sha256": sha256(left_root / "render_manifest.json"),
            "right_manifest_sha256": sha256(right_root / "render_manifest.json"),
        },
        "left": str(left_root),
        "right": str(right_root),
        "image_count": len(rows),
        "run_to_run": aggregate(rows, "run_to_run"),
        "left_to_golden": aggregate(rows, "left_to_golden"),
        "right_to_golden": aggregate(rows, "right_to_golden"),
        "all_current_repeat_checks_passed": all(
            row["run_to_run"]["png_byte_exact"]
            and row["run_to_run"]["pixel_exact"]
            for row in rows
        ),
        "all_golden_regression_checks_passed": all(
            row[side]["png_byte_exact"] and row[side]["pixel_exact"]
            for row in rows
            for side in ("left_to_golden", "right_to_golden")
        ),
        "rows": rows,
    }
    return result


def write_difference_images(result, output_path):
    directory = Path(output_path).parent / f"{Path(output_path).stem}_differences"
    for row in result["rows"]:
        comparisons = {
            "run_to_run": (row["left_path"], row["right_path"]),
            "left_to_golden": (row["left_path"], row["golden_path"]),
            "right_to_golden": (row["right_path"], row["golden_path"]),
        }
        for name, paths in comparisons.items():
            if row[name]["pixel_exact"]:
                row[name]["difference_image"] = None
                continue
            first = cv2.imread(paths[0], cv2.IMREAD_COLOR)
            second = cv2.imread(paths[1], cv2.IMREAD_COLOR)
            difference = np.abs(first.astype(np.int16) - second.astype(np.int16))
            visual = np.clip(difference * 8, 0, 255).astype(np.uint8)
            path = (
                directory
                / name
                / row["window"]
                / f"{row['frame_index']:05d}_{row['camera']}.png"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(path), visual):
                raise OSError(f"could not save {path}")
            row[name]["difference_image"] = str(path)


def regression_succeeded(result):
    return (
        result["all_current_repeat_checks_passed"]
        and result["all_golden_regression_checks_passed"]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    difference_directory = args.output.parent / f"{args.output.stem}_differences"
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {args.output}")
    if difference_directory.exists():
        raise FileExistsError(
            f"refusing to reuse existing difference directory: {difference_directory}"
        )
    result = compare_runs(args.left, args.right)
    write_difference_images(result, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "rows"},
            indent=2,
        )
    )
    return 0 if regression_succeeded(result) else 1


if __name__ == "__main__":
    raise SystemExit(main())
