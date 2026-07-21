#!/usr/bin/env python3
"""Run a frozen Sparse4Dv3 receiver on recorded HUGSIM six-camera frames.

This adapter deliberately consumes RGB and camera calibration only. HUGSIM
semantic and depth outputs are not passed to the receiver and are not treated
as ground truth. The default two-frame stride converts the 4 Hz HUGSIM record
to the 2 Hz temporal interval used by the released Sparse4Dv3 model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import platform
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


CAMERA_ORDER = (
    "CAM_FRONT",
    "CAM_FRONT_RIGHT",
    "CAM_FRONT_LEFT",
    "CAM_BACK",
    "CAM_BACK_LEFT",
    "CAM_BACK_RIGHT",
)
CLASS_NAMES = (
    "car",
    "truck",
    "construction_vehicle",
    "bus",
    "trailer",
    "barrier",
    "motorcycle",
    "bicycle",
    "pedestrian",
    "traffic_cone",
)
VEHICLE_LABELS = frozenset(range(5))
IMAGE_MEAN = np.asarray([123.675, 116.28, 103.53], dtype=np.float32)
IMAGE_STD = np.asarray([58.395, 57.12, 57.375], dtype=np.float32)
FINAL_HEIGHT = 256
FINAL_WIDTH = 704


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sparse4d-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        metavar="LABEL=PATH",
        help="Recorded HUGSIM run; repeat for multiple runs.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--frame-stride",
        type=int,
        default=2,
        help="Default 2 converts HUGSIM 4 Hz to Sparse4D's 2 Hz interval.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Optional per-run smoke-test limit.",
    )
    parser.add_argument("--score-threshold", type=float, default=0.2)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_runs(values: list[str]) -> list[tuple[str, Path]]:
    parsed = []
    labels = set()
    for value in values:
        if "=" not in value:
            raise ValueError(f"--run must be LABEL=PATH, got: {value}")
        label, raw_path = value.split("=", 1)
        if not label or label in labels:
            raise ValueError(f"run labels must be non-empty and unique: {label}")
        path = Path(raw_path).expanduser().resolve()
        for required in ("observations.pkl", "infos.pkl"):
            if not (path / required).is_file():
                raise FileNotFoundError(path / required)
        labels.add(label)
        parsed.append((label, path))
    return parsed


def load_pickle(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


def intrinsic_matrix(intrinsic: dict[str, Any]) -> np.ndarray:
    width = float(intrinsic["W"])
    height = float(intrinsic["H"])
    fx = 0.5 * width / math.tan(0.5 * float(intrinsic["fovx"]))
    fy = 0.5 * height / math.tan(0.5 * float(intrinsic["fovy"]))
    matrix = np.eye(4, dtype=np.float32)
    matrix[0, 0] = fx
    matrix[1, 1] = fy
    matrix[0, 2] = float(intrinsic["cx"])
    matrix[1, 2] = float(intrinsic["cy"])
    return matrix


def resize_crop_rgb(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    height, width = rgb.shape[:2]
    resize = max(FINAL_HEIGHT / height, FINAL_WIDTH / width)
    new_width = int(width * resize)
    new_height = int(height * resize)
    crop_x = max(0, new_width - FINAL_WIDTH) // 2
    crop_y = new_height - FINAL_HEIGHT
    crop = (crop_x, crop_y, crop_x + FINAL_WIDTH, crop_y + FINAL_HEIGHT)
    image = Image.fromarray(rgb).resize((new_width, new_height), Image.Resampling.BILINEAR)
    transformed = np.asarray(image.crop(crop), dtype=np.float32)
    if transformed.shape != (FINAL_HEIGHT, FINAL_WIDTH, 3):
        raise ValueError(f"unexpected transformed image shape: {transformed.shape}")

    augmentation = np.eye(4, dtype=np.float32)
    augmentation[0, 0] = resize
    augmentation[1, 1] = resize
    augmentation[0, 2] = -crop_x
    augmentation[1, 2] = -crop_y
    contract = {
        "source_height": height,
        "source_width": width,
        "resize": resize,
        "resized_height": new_height,
        "resized_width": new_width,
        "crop_xyxy": list(crop),
        "final_height": FINAL_HEIGHT,
        "final_width": FINAL_WIDTH,
    }
    return transformed, augmentation, contract


def ego_to_global(info: dict[str, Any]) -> np.ndarray:
    box = np.asarray(info["ego_box"], dtype=np.float64)
    yaw = float(box[6])
    cosine, sine = math.cos(yaw), math.sin(yaw)
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = np.asarray(
        [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]]
    )
    transform[:3, 3] = box[:3]
    return transform


def prepare_frame(observation: dict[str, Any], info: dict[str, Any], torch: Any) -> dict[str, Any]:
    tensors = []
    projections = []
    contracts = []
    for camera in CAMERA_ORDER:
        rgb = np.asarray(observation["rgb"][camera])
        params = info["cam_params"][camera]
        intrinsic = params["intrinsic"]
        if rgb.shape[:2] != (int(intrinsic["H"]), int(intrinsic["W"])):
            raise ValueError(f"{camera}: RGB dimensions disagree with calibration")
        transformed, augmentation, contract = resize_crop_rgb(rgb)
        normalized = (transformed - IMAGE_MEAN) / IMAGE_STD
        tensors.append(np.ascontiguousarray(normalized.transpose(2, 0, 1)))
        vehicle_to_camera = np.asarray(params["v2c"], dtype=np.float32)
        projections.append(augmentation @ intrinsic_matrix(intrinsic) @ vehicle_to_camera)
        contracts.append({"camera": camera, **contract})

    t_global = ego_to_global(info)
    return {
        "img": torch.from_numpy(np.stack(tensors)).unsqueeze(0).cuda(),
        "timestamp": torch.tensor([float(info["timestamp"])], dtype=torch.float32, device="cuda"),
        "projection_mat": torch.from_numpy(np.stack(projections)).unsqueeze(0).cuda(),
        "image_wh": torch.tensor(
            [[[FINAL_WIDTH, FINAL_HEIGHT]] * len(CAMERA_ORDER)],
            dtype=torch.float32,
            device="cuda",
        ),
        "img_metas": [
            {
                "T_global": t_global,
                "T_global_inv": np.linalg.inv(t_global),
                "timestamp": float(info["timestamp"]),
            }
        ],
        "input_contract": contracts,
    }


def actor_references(info: dict[str, Any]) -> list[dict[str, Any]]:
    transform = np.linalg.inv(ego_to_global(info))
    ego_yaw = float(np.asarray(info["ego_box"])[6])
    references = []
    for actor_index, raw_box in enumerate(info.get("obj_boxes", [])):
        box = np.asarray(raw_box, dtype=np.float64)
        local = transform @ np.asarray([box[0], box[1], box[2], 1.0])
        references.append(
            {
                "actor_index": actor_index,
                "center_vehicle_xyz": local[:3].tolist(),
                "dimensions_wlh": box[3:6].tolist(),
                "yaw_vehicle_rad": float(box[6] - ego_yaw),
            }
        )
    return references


def serialize_predictions(result: dict[str, Any]) -> list[dict[str, Any]]:
    boxes = result["boxes_3d"].numpy()
    scores = result["scores_3d"].numpy()
    labels = result["labels_3d"].numpy()
    instance_ids = result.get("instance_ids")
    if instance_ids is not None:
        instance_ids = instance_ids.cpu().numpy()
    predictions = []
    for index, (box, score, label) in enumerate(zip(boxes, scores, labels, strict=True)):
        row = {
            "rank": index,
            "label_id": int(label),
            "class_name": CLASS_NAMES[int(label)],
            "score": float(score),
            "box_xyz_wlh_yaw_vxyz": box.astype(float).tolist(),
        }
        if instance_ids is not None:
            row["instance_id"] = int(instance_ids[index])
        predictions.append(row)
    return predictions


def match_actors(
    actor_refs: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    score_threshold: float,
) -> list[dict[str, Any]]:
    vehicles = [item for item in predictions if item["label_id"] in VEHICLE_LABELS]
    qualified = [item for item in vehicles if item["score"] >= score_threshold]
    matches = []
    for actor in actor_refs:
        center = np.asarray(actor["center_vehicle_xyz"][:2], dtype=np.float64)
        row: dict[str, Any] = {"actor_index": actor["actor_index"]}
        for key, candidates in (("all", vehicles), ("qualified", qualified)):
            distances = []
            for prediction in candidates:
                pred_center = np.asarray(prediction["box_xyz_wlh_yaw_vxyz"][:2])
                distances.append((float(np.linalg.norm(pred_center - center)), prediction))
            if not distances:
                row[f"nearest_{key}"] = None
                continue
            distance, prediction = min(distances, key=lambda item: item[0])
            row[f"nearest_{key}"] = {
                "center_xy_error_m": distance,
                "prediction_rank": prediction["rank"],
                "prediction_class": prediction["class_name"],
                "prediction_score": prediction["score"],
                "prediction_center_vehicle_xy": prediction["box_xyz_wlh_yaw_vxyz"][:2],
            }
        qualified_error = (
            row["nearest_qualified"]["center_xy_error_m"]
            if row["nearest_qualified"] is not None
            else None
        )
        row["qualified_within_2m"] = bool(qualified_error is not None and qualified_error <= 2.0)
        row["qualified_within_4m"] = bool(qualified_error is not None and qualified_error <= 4.0)
        matches.append(row)
    return matches


def build_model(root: Path, checkpoint: Path) -> tuple[Any, Any, dict[str, Any]]:
    os.chdir(root)
    sys.path.insert(0, str(root))
    import torch
    from mmcv import Config
    from mmcv.runner import load_checkpoint
    from mmdet.models import build_detector

    import projects.mmdet3d_plugin  # noqa: F401

    config_path = root / "projects/configs/sparse4dv3_temporal_r50_1x8_bs6_256x704.py"
    anchor_path = root / "nuscenes_kmeans900.npy"
    if not anchor_path.is_file():
        raise FileNotFoundError(
            f"missing {anchor_path}; extract state_dict['head.instance_bank.anchor'] "
            "from the official checkpoint"
        )
    cfg = Config.fromfile(str(config_path))
    cfg.model["use_deformable_func"] = False
    cfg.model["head"]["deformable_model"]["use_deformable_func"] = False
    cfg.model["head"]["instance_bank"]["anchor"] = str(anchor_path)
    cfg.model["img_backbone"]["pretrained"] = None
    model = build_detector(cfg.model)
    load_checkpoint(model, str(checkpoint), map_location="cpu")
    model.cuda().eval()
    provenance = {
        "sparse4d_root": str(root),
        "config": str(config_path),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256_file(checkpoint),
        "torch_version": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "custom_deformable_cuda_enabled": False,
        "model_parameter_count": sum(parameter.numel() for parameter in model.parameters()),
    }
    return model, torch, provenance


def summarize_run(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    above = [
        prediction
        for row in rows
        for prediction in row["predictions"]
        if prediction["score"] >= threshold
    ]
    counts = Counter(prediction["class_name"] for prediction in above)
    actor_matches = [match for row in rows for match in row["actor_matches"]]
    qualified_errors = [
        match["nearest_qualified"]["center_xy_error_m"]
        for match in actor_matches
        if match["nearest_qualified"] is not None
    ]
    return {
        "processed_frame_count": len(rows),
        "score_threshold": threshold,
        "detections_above_threshold": len(above),
        "detections_per_frame": len(above) / max(1, len(rows)),
        "class_counts": dict(sorted(counts.items())),
        "actor_reference_count": len(actor_matches),
        "actor_qualified_within_2m_count": sum(match["qualified_within_2m"] for match in actor_matches),
        "actor_qualified_within_4m_count": sum(match["qualified_within_4m"] for match in actor_matches),
        "actor_qualified_within_4m_rate": (
            sum(match["qualified_within_4m"] for match in actor_matches) / len(actor_matches)
            if actor_matches
            else None
        ),
        "median_nearest_qualified_xy_error_m": (
            float(np.median(qualified_errors)) if qualified_errors else None
        ),
        "median_nearest_qualified_score": (
            float(
                np.median(
                    [
                        match["nearest_qualified"]["prediction_score"]
                        for match in actor_matches
                        if match["nearest_qualified"] is not None
                    ]
                )
            )
            if qualified_errors
            else None
        ),
    }


def main() -> int:
    args = parse_args()
    if args.frame_stride < 1:
        raise ValueError("--frame-stride must be at least 1")
    sparse4d_root = args.sparse4d_root.expanduser().resolve()
    checkpoint = args.checkpoint.expanduser().resolve()
    runs = parse_runs(args.run)
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)

    model, torch, model_provenance = build_model(sparse4d_root, checkpoint)
    manifest: dict[str, Any] = {
        "created_unix_s": time.time(),
        "host": platform.node(),
        "model": model_provenance,
        "receiver_input": {
            "modalities": ["HUGSIM RGB", "HUGSIM camera intrinsics", "HUGSIM camera extrinsics"],
            "explicitly_excluded": ["HUGSIM semantic", "HUGSIM depth"],
            "camera_order": list(CAMERA_ORDER),
            "source_rate_hz": 4.0,
            "frame_stride": args.frame_stride,
            "receiver_rate_hz": 4.0 / args.frame_stride,
            "normalization": {"mean_rgb": IMAGE_MEAN.tolist(), "std_rgb": IMAGE_STD.tolist()},
        },
        "runs": {},
    }

    for label, run_path in runs:
        observations = load_pickle(run_path / "observations.pkl")
        infos = load_pickle(run_path / "infos.pkl")
        if len(observations) != len(infos):
            raise ValueError(f"{label}: observation/info length mismatch")
        indices = list(range(0, len(observations), args.frame_stride))
        if args.max_frames is not None:
            indices = indices[: args.max_frames]
        model.head.instance_bank.reset()
        rows = []
        for frame_index in indices:
            prepared = prepare_frame(observations[frame_index], infos[frame_index], torch)
            input_contract = prepared.pop("input_contract")
            torch.cuda.synchronize()
            started = time.perf_counter()
            with torch.no_grad():
                result = model(**prepared)[0]["img_bbox"]
            torch.cuda.synchronize()
            predictions = serialize_predictions(result)
            actors = actor_references(infos[frame_index])
            rows.append(
                {
                    "run_label": label,
                    "frame_index": frame_index,
                    "timestamp_s": float(infos[frame_index]["timestamp"]),
                    "inference_seconds": time.perf_counter() - started,
                    "actor_references": actors,
                    "actor_matches": match_actors(actors, predictions, args.score_threshold),
                    "predictions": predictions,
                }
            )
            if len(rows) == 1:
                manifest["runs"][label] = {
                    "source": str(run_path),
                    "source_frame_count": len(observations),
                    "processed_frame_indices": indices,
                    "input_contract": input_contract,
                }

        prediction_path = output / f"{label}_predictions.json"
        prediction_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        manifest["runs"][label]["predictions"] = prediction_path.name
        manifest["runs"][label]["summary"] = summarize_run(rows, args.score_threshold)

    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({label: item["summary"] for label, item in manifest["runs"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
