#!/usr/bin/env python3
"""Qualify whether a HUGSIM static render isolates native-actor absence."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
from PIL import Image

from analyze_hugsim_source_dynamic_visibility import crop_bounds
from render_hugsim_exact_source_pose import select_camera_records


CONDITIONS = ("real", "factual", "static_control")
RUNS = ("baseline", "baseline_repeat")
PEDESTRIAN_LABEL_ID = 8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-audit", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--calibration-reference-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def endpoint_frame(
    report: dict[str, Any], run: str, endpoint: int
) -> dict[str, Any]:
    matches = [
        frame
        for frame in report[run]["frames"]
        if int(frame["source_frame_index"]) == endpoint
    ]
    if len(matches) != 1:
        raise ValueError(f"{run}: expected exactly one frame {endpoint}")
    return matches[0]


def actor_center_in_model(
    metadata: dict[str, Any],
    frame_index: int,
    front_l2c: np.ndarray,
) -> tuple[str, np.ndarray]:
    front = select_camera_records(metadata, frame_index)["CAM_FRONT"]
    dynamics = front.get("dynamics", {})
    if len(dynamics) != 1:
        raise ValueError("expected exactly one native dynamic at endpoint")
    dynamic_id, dynamic_transform = next(iter(dynamics.items()))
    model_to_world = (
        np.asarray(front["camtoworld"], dtype=np.float64)
        @ np.asarray(front_l2c, dtype=np.float64)
    )
    object_to_world = np.asarray(dynamic_transform, dtype=np.float64)
    if model_to_world.shape != (4, 4) or object_to_world.shape != (4, 4):
        raise ValueError("invalid model or dynamic transform")
    center = (
        np.linalg.inv(model_to_world)
        @ np.concatenate((object_to_world[:3, 3], [1.0]))
    )[:3]
    return dynamic_id, center


def nearest_class_detection(
    frame: dict[str, Any],
    target_xy: np.ndarray,
    label_id: int,
) -> dict[str, Any]:
    candidates = [
        row
        for row in frame["native"]["top_detections"]
        if int(row["label_id"]) == label_id
    ]
    if not candidates:
        raise ValueError(f"no label {label_id} in retained top detections")
    ranked = sorted(
        (
            float(
                np.linalg.norm(
                    np.asarray(row["box"][:2], dtype=np.float64) - target_xy
                )
            ),
            row,
        )
        for row in candidates
    )
    distance, row = ranked[0]
    second_distance = ranked[1][0] if len(ranked) > 1 else None
    return {
        "rank": int(row["rank"]),
        "label_id": int(row["label_id"]),
        "score": float(row["score"]),
        "box": row["box"],
        "center_xy_m": [float(value) for value in row["box"][:2]],
        "distance_to_declared_actor_xy_m": distance,
        "second_nearest_same_class_distance_m": second_distance,
        "association_margin_m": (
            second_distance - distance if second_distance is not None else None
        ),
    }


def pairwise_detection_differences(
    first: list[dict[str, Any]],
    second: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    for first_index, left in enumerate(first):
        for second_index, right in enumerate(second):
            rows.append(
                {
                    "first_reset": first_index + 1,
                    "second_reset": second_index + 1,
                    "center_xy_distance_m": float(
                        np.linalg.norm(
                            np.asarray(left["center_xy_m"])
                            - np.asarray(right["center_xy_m"])
                        )
                    ),
                    "absolute_score_difference": abs(
                        float(left["score"]) - float(right["score"])
                    ),
                }
            )
    return {
        "pairings": rows,
        "center_xy_distance_m": {
            "min": min(row["center_xy_distance_m"] for row in rows),
            "max": max(row["center_xy_distance_m"] for row in rows),
            "mean": float(
                np.mean([row["center_xy_distance_m"] for row in rows])
            ),
        },
        "absolute_score_difference": {
            "min": min(row["absolute_score_difference"] for row in rows),
            "max": max(row["absolute_score_difference"] for row in rows),
            "mean": float(
                np.mean([row["absolute_score_difference"] for row in rows])
            ),
        },
    }


def dynamic_inventory(metadata: dict[str, Any]) -> dict[str, Any]:
    dynamic_ids = set()
    by_frame: dict[int, list[bool]] = {}
    for frame in metadata.get("frames", []):
        dynamic_ids.update(frame.get("dynamics", {}))
        index = int(PurePosixPath(frame["rgb_path"]).stem)
        by_frame.setdefault(index, []).append(bool(frame.get("dynamics")))
    if any(len(values) != 6 for values in by_frame.values()):
        raise ValueError("metadata does not contain six records per frame")
    return {
        "dynamic_ids": sorted(dynamic_ids),
        "frame_count": len(by_frame),
        "all_six_cameras_dynamic_frame_count": sum(
            all(values) for values in by_frame.values()
        ),
        "all_six_cameras_empty_frame_count": sum(
            not any(values) for values in by_frame.values()
        ),
        "mixed_camera_membership_frame_count": sum(
            any(values) and not all(values) for values in by_frame.values()
        ),
        "empty_dynamic_frame_indices": sorted(
            index for index, values in by_frame.items() if not any(values)
        ),
    }


def camera_image_path(frame: dict[str, Any], camera: str) -> Path:
    paths = [
        Path(item["image_path"])
        for item in frame["input_contract"]["camera_inputs"]
        if item["camera"] == camera
    ]
    if len(paths) != 1:
        raise ValueError(f"expected one {camera} input")
    return paths[0]


def save_visualization(
    endpoint: int,
    frames: dict[str, dict[str, Any]],
    detections: dict[str, list[dict[str, Any]]],
    actor_center: np.ndarray,
    support_row: dict[str, Any],
    bridge: dict[str, Any],
    output: Path,
) -> Path:
    import matplotlib.pyplot as plt

    camera = support_row["camera"]
    mask = ~np.load(Path(support_row["source_mask_path"])).astype(bool)
    x0, y0, x1, y1 = crop_bounds(mask)
    local_mask = mask[y0:y1, x0:x1]
    images = {
        condition: np.asarray(
            Image.open(camera_image_path(frame, camera)).convert("RGB")
        )[y0:y1, x0:x1]
        for condition, frame in frames.items()
    }

    figure = plt.figure(figsize=(16, 8.5), constrained_layout=True)
    grid = figure.add_gridspec(2, 4, height_ratios=(1, 1.05))
    titles = {
        "real": "Real source RGB",
        "factual": "HUGSIM factual",
        "static_control": "HUGSIM native dynamic omitted",
    }
    for column, condition in enumerate(CONDITIONS):
        axis = figure.add_subplot(grid[0, column])
        axis.imshow(images[condition])
        axis.contour(
            local_mask.astype(float),
            levels=[0.5],
            colors=["cyan"],
            linewidths=1.3,
        )
        axis.set_title(titles[condition])
        axis.axis("off")
    note_axis = figure.add_subplot(grid[0, 3])
    note_axis.axis("off")
    note_axis.text(
        0.02,
        0.95,
        "Control qualification",
        fontsize=15,
        weight="bold",
        va="top",
    )
    note_axis.text(
        0.02,
        0.78,
        "Selected-actor absence:\nrejected",
        fontsize=12,
        weight="bold",
        linespacing=1.25,
    )
    note_axis.text(
        0.02,
        0.48,
        "Static still yields a rank-2\npedestrian hypothesis at the\nsame declared actor locus.",
        fontsize=11,
        linespacing=1.35,
    )
    note_axis.text(
        0.02,
        0.18,
        "This rejects the control,\nnot HUGSIM as a whole.",
        fontsize=11,
        linespacing=1.35,
    )

    xy_axis = figure.add_subplot(grid[1, :2])
    xy_axis.scatter(
        actor_center[0],
        actor_center[1],
        marker="*",
        s=260,
        color="black",
        label="declared native actor center",
        zorder=5,
    )
    colors = {
        "real": "#2ca02c",
        "factual": "#d62728",
        "static_control": "#1f77b4",
    }
    for condition in CONDITIONS:
        row = detections[condition][0]
        xy_axis.scatter(
            row["center_xy_m"][0],
            row["center_xy_m"][1],
            s=100,
            color=colors[condition],
            label=(
                f"{titles[condition]} pedestrian "
                f"(score {row['score']:.3f})"
            ),
        )
    xy_axis.set(
        title="Nearest SparseDrive pedestrian output in model coordinates",
        xlabel="model x, metres",
        ylabel="model y, metres",
    )
    xy_axis.axis("equal")
    xy_axis.grid(alpha=0.3)
    xy_axis.legend(fontsize=8)

    metric_axis = figure.add_subplot(grid[1, 2])
    labels = list(CONDITIONS)
    scores = [detections[name][0]["score"] for name in labels]
    errors = [
        detections[name][0]["distance_to_declared_actor_xy_m"]
        for name in labels
    ]
    x = np.arange(len(labels))
    score_bars = metric_axis.bar(
        x - 0.18,
        scores,
        width=0.36,
        label="score",
        color=[colors[name] for name in labels],
    )
    error_axis = metric_axis.twinx()
    error_axis.bar(
        x + 0.18,
        errors,
        width=0.36,
        label="actor-center distance",
        color="#9e9e9e",
        alpha=0.7,
    )
    metric_axis.set_xticks(x, ["real", "factual", "static"])
    metric_axis.set_ylabel("pedestrian score")
    error_axis.set_ylabel("distance to declared actor, metres")
    metric_axis.set_title("Same explicit class response persists")
    metric_axis.grid(axis="y", alpha=0.25)
    metric_axis.legend([score_bars], ["score"], loc="upper left")

    result_axis = figure.add_subplot(grid[1, 3])
    result_axis.axis("off")
    factual_static = pairwise_detection_differences(
        detections["factual"], detections["static_control"]
    )
    result_axis.text(
        0.02,
        0.95,
        "Observed receiver boundary",
        fontsize=14,
        weight="bold",
        va="top",
    )
    result_axis.text(
        0.02,
        0.76,
        "Factual↔static nearest\npedestrian center:",
        fontsize=10.5,
    )
    result_axis.text(
        0.02,
        0.61,
        f"{factual_static['center_xy_distance_m']['mean']:.4f} m",
        fontsize=15,
        weight="bold",
    )
    result_axis.text(
        0.02,
        0.45,
        "Factual↔static plan ADE:",
        fontsize=10.5,
    )
    result_axis.text(
        0.02,
        0.34,
        f"{bridge['cross_condition_plan_distances']['factual_static']['ade_m']['mean']:.4f} m",
        fontsize=15,
        weight="bold",
    )
    result_axis.text(
        0.02,
        0.14,
        "Planning changed without\na target appearance/disappearance.",
        fontsize=10.5,
        linespacing=1.35,
    )
    figure.suptitle(
        f"Static-control qualification · scene-0383 · frame {endpoint}\n"
        "Omitting the native render path does not isolate selected-actor absence for SparseDrive",
        fontsize=16,
    )
    path = output / "sparsedrive_static_control_qualification.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    bridge_path = args.bridge_audit.expanduser().resolve()
    metadata_path = args.metadata.expanduser().resolve()
    calibration_run = args.calibration_reference_run.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (
        bridge_path,
        metadata_path,
        calibration_run / "infos.pkl",
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    output.mkdir(parents=True)

    bridge = load_json(bridge_path)
    if bridge["audit_id"] != "sparsedrive_natural_actor_bridge_001":
        raise ValueError("unexpected bridge audit")
    endpoint = int(bridge["evaluated_endpoint_frame"])
    report_paths = {
        condition: Path(bridge["inputs"][condition]["path"])
        for condition in CONDITIONS
    }
    reports = {
        condition: load_json(path)
        for condition, path in report_paths.items()
    }
    frames = {
        condition: endpoint_frame(report, "baseline", endpoint)
        for condition, report in reports.items()
    }
    metadata = load_json(metadata_path)
    with (calibration_run / "infos.pkl").open("rb") as stream:
        front_l2c = np.asarray(
            pickle.load(stream)[0]["cam_params"]["CAM_FRONT"]["l2c"],
            dtype=np.float64,
        )
    dynamic_id, actor_center = actor_center_in_model(
        metadata, endpoint, front_l2c
    )
    detections = {
        condition: [
            nearest_class_detection(
                endpoint_frame(report, run, endpoint),
                actor_center[:2],
                PEDESTRIAN_LABEL_ID,
            )
            for run in RUNS
        ]
        for condition, report in reports.items()
    }
    repeat = {
        condition: pairwise_detection_differences(
            [rows[0]], [rows[1]]
        )
        for condition, rows in detections.items()
    }
    factual_static = pairwise_detection_differences(
        detections["factual"], detections["static_control"]
    )

    support_path = Path(bridge["inputs"]["source_support"]["path"])
    support = load_json(support_path)
    matches = [
        row
        for row in support["rows"]
        if int(row["frame_index"]) == endpoint
        and row["camera"] == "CAM_FRONT_LEFT"
    ]
    if len(matches) != 1:
        raise ValueError("missing source-support row")
    support_row = matches[0]
    visual_path = save_visualization(
        endpoint,
        frames,
        detections,
        actor_center,
        support_row,
        bridge,
        output,
    )
    inventory = dynamic_inventory(metadata)
    result = {
        "audit_id": "sparsedrive_static_control_qualification_001",
        "date": date.today().isoformat(),
        "status": "post-hoc control qualification; not preregistered",
        "inputs": {
            "bridge_audit": {
                "path": str(bridge_path),
                "sha256": sha256_file(bridge_path),
            },
            "metadata": {
                "path": str(metadata_path),
                "sha256": sha256_file(metadata_path),
            },
            "calibration_reference_infos": {
                "path": str(calibration_run / "infos.pkl"),
                "sha256": sha256_file(calibration_run / "infos.pkl"),
            },
        },
        "analysis_script": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "endpoint_frame": endpoint,
        "native_dynamic_id": dynamic_id,
        "declared_actor_center_model_xyz_m": actor_center.astype(float).tolist(),
        "class_mapping": {
            "label_id": PEDESTRIAN_LABEL_ID,
            "name": "pedestrian",
            "basis": "pinned SparseDrive stage2 config",
        },
        "nearest_pedestrian_by_condition_and_reset": detections,
        "within_condition_repeat_differences": repeat,
        "factual_static_detection_differences": factual_static,
        "bridge_plan_effect_ade_m": bridge[
            "cross_condition_plan_distances"
        ]["factual_static"]["ade_m"],
        "source_asset_inventory": inventory,
        "evidence_decision": {
            "overall": "down-weighted",
            "accepted": [
                "the same high-ranking pedestrian-class output persists in factual and static-control inputs near the declared source actor locus",
                "the static-control target response is stable across independent receiver resets",
            ],
            "down-weighted": [
                "association uses HUGSIM/source-declared geometry and only the ten retained highest-scoring detections",
                "the diagnostic was designed after the plan-level negative result was observed",
            ],
            "rejected": [
                "the current static-control input qualifies as selected-actor absence for SparseDrive",
                "the factual-static plan effect can be attributed to appearance versus disappearance of a new explicit pedestrian detection",
                "this control failure proves a general HUGSIM renderer defect or SparseDrive correctness",
            ],
        },
        "interpretation": (
            "Omitting the native dynamic render path does not create a clean "
            "selected-actor-absence contrast for the target AD. Factual and "
            "static inputs retain nearly the same explicit pedestrian output "
            "at the declared locus, while their plans still differ. This "
            "qualifies the control as unsuitable for actor-removal claims; it "
            "does not identify whether static leakage, nearby people, latent "
            "features or receiver domain sensitivity causes the plan effect."
        ),
        "visualization": str(visual_path),
        "visualization_sha256": sha256_file(visual_path),
    }
    result_path = output / "sparsedrive_static_control_qualification.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
