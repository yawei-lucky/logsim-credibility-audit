#!/usr/bin/env python3
"""Build a fail-closed manifest for HUGSIM exact matched-pose rendering."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from audit_hugsim_source_anchor import (
    NUSCENES_CAMERAS,
    audit_scene_anchor,
    frame_camera,
    require_intrinsics,
    require_matrix,
    resolve_frame_path,
    sha256_file,
)


def load_frames(scene_dir: Path) -> list[dict[str, Any]]:
    metadata_path = scene_dir / "meta_data.json"
    with metadata_path.open("r", encoding="utf-8") as stream:
        metadata = json.load(stream)
    frames = metadata.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("meta_data.frames must be a non-empty list")
    return frames


def reader_candidate_groups(
    frames: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_timestamp: defaultdict[float, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, frame in enumerate(frames):
        by_timestamp[float(frame["timestamp"])].append((index, frame))

    candidates = []
    for timestamp in sorted(by_timestamp):
        group = by_timestamp[timestamp]
        if not group or not all(index % 30 >= 24 for index, _ in group):
            continue
        frame_indices = {
            int(PurePosixPath(frame["rgb_path"]).stem) for _, frame in group
        }
        if len(frame_indices) != 1:
            continue
        cameras = [frame_camera(frame) for _, frame in group]
        if set(cameras) != set(NUSCENES_CAMERAS):
            continue
        candidates.append(
            {
                "timestamp_s": timestamp,
                "frame_index": next(iter(frame_indices)),
                "metadata_indices": [index for index, _ in group],
            }
        )
    return candidates


def select_group(
    frames: list[dict[str, Any]], frame_index: int | None
) -> tuple[int, float, list[dict[str, Any]], bool]:
    by_index: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for frame in frames:
        by_index[int(PurePosixPath(frame["rgb_path"]).stem)].append(frame)

    selected_from_reader_candidate = False
    if frame_index is None:
        candidates = reader_candidate_groups(frames)
        if candidates:
            frame_index = candidates[0]["frame_index"]
            selected_from_reader_candidate = True
        else:
            frame_index = min(by_index)

    group = by_index[frame_index]
    if len(group) != len(NUSCENES_CAMERAS):
        raise ValueError(
            f"frame {frame_index:05d} has {len(group)} camera records, "
            f"expected {len(NUSCENES_CAMERAS)}"
        )
    by_camera = {frame_camera(frame): frame for frame in group}
    if set(by_camera) != set(NUSCENES_CAMERAS):
        raise ValueError(f"frame {frame_index:05d} does not contain all six cameras")
    timestamps = {float(frame["timestamp"]) for frame in group}
    if len(timestamps) != 1:
        raise ValueError(f"frame {frame_index:05d} has inconsistent timestamps")
    if not selected_from_reader_candidate:
        selected_from_reader_candidate = any(
            candidate["frame_index"] == frame_index
            for candidate in reader_candidate_groups(frames)
        )
    return (
        frame_index,
        next(iter(timestamps)),
        [by_camera[camera] for camera in NUSCENES_CAMERAS],
        selected_from_reader_candidate,
    )


def camera_entry(
    frame: dict[str, Any],
    source_root: Path,
    sim_render_root: Path | None,
    frame_index: int,
) -> dict[str, Any]:
    camera = frame_camera(frame)
    real_path = resolve_frame_path(source_root, frame["rgb_path"])
    sim_path = (
        sim_render_root / f"{frame_index:05d}" / f"{camera}.png"
        if sim_render_root is not None
        else None
    )
    real_exists = real_path.is_file()
    sim_exists = sim_path.is_file() if sim_path is not None else False
    intrinsics = require_intrinsics(frame["intrinsics"], f"{camera}.intrinsics")
    camtoworld = require_matrix(frame["camtoworld"], (4, 4), f"{camera}.camtoworld")
    sample_data_token = frame.get("sample_data_token")
    sample_token = frame.get("sample_token")
    return {
        "camera": camera,
        "timestamp_s": float(frame["timestamp"]),
        "metadata_rgb_path": frame["rgb_path"],
        "real_rgb_path": str(real_path),
        "real_rgb_exists": real_exists,
        "real_rgb_sha256": sha256_file(real_path) if real_exists else None,
        "sample_data_token": sample_data_token,
        "sample_token": sample_token,
        "width": int(frame["width"]),
        "height": int(frame["height"]),
        "intrinsics_3x3": intrinsics.tolist(),
        "camtoworld_4x4": camtoworld.tolist(),
        "native_dynamic_ids": sorted(frame.get("dynamics", {}).keys()),
        "sim_render_path": str(sim_path) if sim_path is not None else None,
        "sim_render_exists": sim_exists,
        "sim_render_sha256": sha256_file(sim_path) if sim_exists else None,
    }


def receiver_contract_stub(camera_order: list[str]) -> dict[str, Any]:
    return {
        "contract_id": "camera_only_rgb_single_frame_v0",
        "receiver_scope": "bounded camera-only AD receiver",
        "modalities": ["rgb"],
        "camera_order": camera_order,
        "frame_history": 1,
        "required_calibration": ["intrinsics_3x3", "camtoworld_4x4"],
        "preprocessing_must_be_frozen_before_receiver_run": True,
        "temporal_claims_allowed": False,
        "planning_or_control_claims_allowed": False,
        "permitted_initial_endpoints": [
            "per-frame perception",
            "critical-object discovery",
            "lane/drivable relation",
            "single-frame risk ordering",
        ],
    }


def build_manifest(
    scene_dir: Path,
    source_root: Path | None = None,
    frame_index: int | None = None,
    sim_render_root: Path | None = None,
    dataset_reader: Path | None = None,
    hugsim_repo: Path | None = None,
) -> dict[str, Any]:
    scene_dir = scene_dir.resolve()
    source_root = (source_root or scene_dir).resolve()
    frames = load_frames(scene_dir)
    selected_index, timestamp, group, from_reader_candidate = select_group(
        frames, frame_index
    )
    anchor = audit_scene_anchor(
        scene_dir=scene_dir,
        source_root=source_root,
        dataset_reader=dataset_reader,
        hugsim_repo=hugsim_repo,
    )
    cameras = [
        camera_entry(frame, source_root, sim_render_root, selected_index)
        for frame in group
    ]
    real_ready = (
        anchor["gate"]["status"] == "ready"
        and all(camera["real_rgb_exists"] for camera in cameras)
        and all(camera["real_rgb_sha256"] for camera in cameras)
    )
    sim_ready = (
        sim_render_root is not None
        and all(camera["sim_render_exists"] for camera in cameras)
        and all(camera["sim_render_sha256"] for camera in cameras)
    )
    source_tokens_ready = all(
        camera.get("sample_data_token") or camera.get("sample_token")
        for camera in cameras
    )

    if not real_ready:
        status = "blocked_source_anchor"
        permitted_claim = (
            "selected metadata pose can be listed, but no real-sim image pair "
            "or AD receiver comparison is established"
        )
    elif not sim_ready:
        status = "ready_for_exact_matched_pose_render"
        permitted_claim = (
            "source observation anchor is ready; exact-pose simulation render "
            "and receiver comparison are still not tested"
        )
    else:
        status = "pairing_integrity_candidate"
        permitted_claim = (
            "real and simulation image files exist with hashes for a selected "
            "metadata pose; exact-render provenance and receiver equivalence "
            "are still not tested"
        )

    return {
        "audit_id": "hugsim_matched_pose_manifest",
        "date": date.today().isoformat(),
        "scene": scene_dir.name,
        "scene_dir": str(scene_dir),
        "source_root": str(source_root),
        "selected_frame_index": selected_index,
        "selected_timestamp_s": timestamp,
        "selected_from_reader_test_candidate": from_reader_candidate,
        "source_anchor_status": anchor["gate"]["status"],
        "source_anchor_reasons": anchor["gate"]["reasons"],
        "pairing_integrity_gate": {
            "status": status,
            "permitted_claim": permitted_claim,
            "real_observation_ready": real_ready,
            "source_identity_ready_for_selected_frame": source_tokens_ready,
            "exact_sim_render_ready": sim_ready,
            "exact_sim_render_provenance_verified": False,
            "pairing_integrity_passed": False,
            "receiver_equivalence_tested": False,
        },
        "camera_order": list(NUSCENES_CAMERAS),
        "receiver_input_contract": receiver_contract_stub(list(NUSCENES_CAMERAS)),
        "cameras": cameras,
        "native_dynamic_policy": (
            "preserve timestamp-specific native dynamic objects from metadata; "
            "do not remove native actors when comparing to real source images"
        ),
        "next_action": (
            "Recover the selected frame's six real RGB files and immutable "
            "source identity, render each camera using the listed exact metadata "
            "intrinsics and camtoworld pose, then run the frozen camera-only AD "
            "receiver on the matched real/sim observations."
        ),
    }


def format_markdown(manifest: dict[str, Any]) -> str:
    gate = manifest["pairing_integrity_gate"]
    lines = [
        "# HUGSIM Matched-Pose Manifest 001",
        "",
        f"Date: {manifest['date']}",
        "",
        "## Result",
        "",
        f"Gate status: `{gate['status']}`",
        "",
        f"Pairing integrity passed: `{gate['pairing_integrity_passed']}`",
        "",
        f"Receiver equivalence tested: `{gate['receiver_equivalence_tested']}`",
        "",
        f"Permitted claim: {gate['permitted_claim']}",
        "",
        "This run did not generate a new HUGSIM scenario, rollout, or rendered "
        "simulation image. It prepares the exact metadata pose that should be "
        "used once the real source observations are recovered.",
        "",
        "## Selected Pose",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| Scene | {manifest['scene']} |",
        f"| Frame index | {manifest['selected_frame_index']:05d} |",
        f"| Timestamp | {manifest['selected_timestamp_s']:.6f} s |",
        f"| Reader-derived test candidate | {manifest['selected_from_reader_test_candidate']} |",
        "",
        "## Six-Camera Pairing Status",
        "",
        "| Camera | Real RGB | Sim exact render | Source identity |",
        "|---|---|---|---|",
    ]
    for camera in manifest["cameras"]:
        real = "yes" if camera["real_rgb_exists"] else "no"
        sim = "yes" if camera["sim_render_exists"] else "no"
        identity = "yes" if camera.get("sample_data_token") or camera.get("sample_token") else "no"
        lines.append(f"| {camera['camera']} | {real} | {sim} | {identity} |")
    lines.extend(
        [
            "",
            "## Receiver Scope",
            "",
            "The attached receiver contract is `camera_only_rgb_single_frame_v0`. "
            "It can only support per-frame perception, visibility, lane/drivable "
            "relation, critical-object discovery, and single-frame risk ordering. "
            "It cannot support temporal, planning, control, or closed-loop "
            "claims until a matched temporal clip and full receiver input "
            "contract are available.",
            "",
            "## Next Action",
            "",
            manifest["next_action"],
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-dir", required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--frame-index", type=int)
    parser.add_argument("--sim-render-root", type=Path)
    parser.add_argument("--dataset-reader", type=Path)
    parser.add_argument("--hugsim-repo", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args()


def write_new(path: Path, payload: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def main() -> int:
    args = parse_args()
    manifest = build_manifest(
        scene_dir=args.scene_dir,
        source_root=args.source_root,
        frame_index=args.frame_index,
        sim_render_root=args.sim_render_root,
        dataset_reader=args.dataset_reader,
        hugsim_repo=args.hugsim_repo,
    )
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        write_new(args.output, payload)
    if args.markdown_output:
        write_new(args.markdown_output, format_markdown(manifest))
    print(payload)
    return (
        0
        if manifest["pairing_integrity_gate"]["status"]
        != "blocked_source_anchor"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
