#!/usr/bin/env python3
"""Assemble exact-pose HUGSIM renders into a source-metadata image window."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from render_hugsim_exact_source_pose import CAMERAS, sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument(
        "--render",
        action="append",
        required=True,
        metavar="FRAME=PATH",
        help="Exact-pose render directory; repeat for each source frame.",
    )
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def parse_render_specs(values: list[str]) -> dict[int, Path]:
    parsed = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--render must use FRAME=PATH")
        raw_frame, raw_path = value.split("=", 1)
        frame_index = int(raw_frame)
        path = Path(raw_path).expanduser().resolve()
        if frame_index in parsed:
            raise ValueError(f"duplicate render frame: {frame_index}")
        if not (path / "exact_pose_render.json").is_file():
            raise FileNotFoundError(path / "exact_pose_render.json")
        parsed[frame_index] = path
    if not parsed:
        raise ValueError("at least one render is required")
    return dict(sorted(parsed.items()))


def assemble(
    metadata_path: Path,
    render_dirs: dict[int, Path],
    variant: str,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    with metadata_path.open("r", encoding="utf-8") as stream:
        metadata = json.load(stream)

    reports = {}
    for frame_index, render_dir in render_dirs.items():
        report_path = render_dir / "exact_pose_render.json"
        with report_path.open("r", encoding="utf-8") as stream:
            report = json.load(stream)
        if int(report["frame_index"]) != frame_index:
            raise ValueError(f"{report_path}: frame index mismatch")
        if variant not in report["variants"]:
            raise KeyError(f"{report_path}: missing variant {variant!r}")
        camera_results = report["variants"][variant]["camera_results"]
        if set(camera_results) != set(CAMERAS):
            raise ValueError(f"{report_path}: incomplete camera set")
        reports[frame_index] = (report_path, report)

    output.mkdir(parents=True)
    copied = []
    path_by_frame_camera = {}
    for frame_index, (report_path, report) in reports.items():
        camera_results = report["variants"][variant]["camera_results"]
        for camera in CAMERAS:
            source = Path(camera_results[camera]["render_path"]).resolve()
            if sha256_file(source) != camera_results[camera]["render_sha256"]:
                raise ValueError(f"{source}: render hash mismatch")
            relative = Path("images") / camera / f"{frame_index:05d}.png"
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            path_by_frame_camera[(frame_index, camera)] = relative
            copied.append(
                {
                    "frame_index": frame_index,
                    "camera": camera,
                    "source": str(source),
                    "source_sha256": sha256_file(source),
                    "destination": str(destination),
                    "destination_sha256": sha256_file(destination),
                    "render_report": str(report_path),
                    "render_report_sha256": sha256_file(report_path),
                }
            )

    matched_records = set()
    for frame in metadata.get("frames", []):
        path = PurePosixPath(frame["rgb_path"])
        frame_index = int(path.stem)
        camera = path.parent.name
        key = (frame_index, camera)
        if key not in path_by_frame_camera:
            continue
        frame["rgb_path"] = f"./{path_by_frame_camera[key].as_posix()}"
        matched_records.add(key)
    expected_records = set(path_by_frame_camera)
    if matched_records != expected_records:
        missing = sorted(expected_records - matched_records)
        raise ValueError(f"metadata is missing selected camera records: {missing}")

    output_metadata = output / "metadata_exact_pose_window.json"
    output_metadata.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "audit_id": "hugsim_exact_pose_window_assembly",
        "date": date.today().isoformat(),
        "metadata_source": str(metadata_path),
        "metadata_source_sha256": sha256_file(metadata_path),
        "output_metadata": str(output_metadata),
        "output_metadata_sha256": sha256_file(output_metadata),
        "variant": variant,
        "frame_indices": list(render_dirs),
        "camera_order": list(CAMERAS),
        "copied_image_count": len(copied),
        "images": copied,
        "boundary": (
            "This is a lossless file assembly of declared exact-pose HUGSIM "
            "PNG renders. It does not alter poses, intrinsics or RGB values."
        ),
    }
    manifest_path = output / "assembled_render_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    args = parse_args()
    manifest = assemble(
        args.metadata.expanduser().resolve(),
        parse_render_specs(args.render),
        args.variant,
        args.output.expanduser().resolve(),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
