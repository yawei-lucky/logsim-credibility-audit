#!/usr/bin/env python3
"""Read-only integrity inventory of the two existing official-sample RGB anchors."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import platform
import sys
import zlib


REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path):
    path = Path(path)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_frozen(path, expected_sha256):
    path = resolve(path)
    observed = sha256(path)
    if observed != expected_sha256:
        raise ValueError(f"frozen input SHA-256 mismatch: {path}")
    return json.loads(path.read_text()), {"path": str(path), "sha256": observed}


def inventory(config, image_module):
    metadata, metadata_input = load_frozen(config["metadata"], config["metadata_sha256"])
    metadata_manifest, metadata_manifest_input = load_frozen(
        config["metadata_manifest"], config["metadata_manifest_sha256"]
    )
    metadata_members = [
        member for member in metadata_manifest["members"]
        if member["output_relative_path"] == "meta_data_init.json"
    ]
    if len(metadata_members) != 1 or metadata_members[0]["sha256"] != metadata_input["sha256"]:
        raise ValueError("metadata does not match its declared archive member")
    cameras = config["cameras"]
    if not cameras or len(cameras) != len(set(cameras)) or not config["windows"]:
        raise ValueError("inventory requires unique cameras and at least one window")
    if len({window["id"] for window in config["windows"]}) != len(config["windows"]):
        raise ValueError("duplicate window id in inventory config")
    metadata_by_path = {}
    for frame in metadata["frames"]:
        key = str(PurePosixPath(frame["rgb_path"]))
        if key in metadata_by_path:
            raise ValueError(f"duplicate metadata image path: {key}")
        metadata_by_path[key] = frame
    archives = [metadata_manifest["archive"]]
    rows, windows, errors = [], [], []
    unique_members, unique_paths = set(), set()
    for window in config["windows"]:
        root = resolve(window["root"])
        manifest, manifest_input = load_frozen(window["manifest"], window["manifest_sha256"])
        archives.append(manifest["archive"])
        expected = {
            f"images/{camera}/{frame:05d}.jpg"
            for camera in cameras for frame in window["frames"]
        }
        if not expected or len(expected) != len(cameras) * len(window["frames"]):
            raise ValueError(f"empty or duplicate frame in window {window['id']}")
        members = [m for m in manifest["members"] if m["output_relative_path"].startswith("images/")]
        member_paths = [m["output_relative_path"] for m in members]
        if len(member_paths) != len(set(member_paths)) or set(member_paths) != expected:
            raise ValueError(f"manifest camera/frame set differs from window {window['id']}")
        window_rows = []
        for member in members:
            relative = member["output_relative_path"]
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError(f"archive member escapes source root: {relative}")
            camera = PurePosixPath(relative).parts[1]
            frame_index = int(PurePosixPath(relative).stem)
            declared = metadata_by_path.get(relative)
            checks = {"exists": path.is_file()}
            row = {
                "scene": window["scene"], "window": window["id"],
                "camera": camera, "frame_index": frame_index,
                "path": str(path), "archive_member": member["name"],
                "checks": checks,
            }
            if declared is None:
                checks["metadata_record"] = False
            else:
                checks["metadata_record"] = True
                row["timestamp_s"] = declared["timestamp"]
                checks["finite_timestamp"] = math.isfinite(declared["timestamp"])
            if checks["exists"]:
                raw = path.read_bytes()
                row.update(sha256=hashlib.sha256(raw).hexdigest(), crc32=zlib.crc32(raw) & 0xffffffff, size_bytes=len(raw))
                checks.update(
                    sha256=row["sha256"] == member["sha256"],
                    crc32=row["crc32"] == member["crc32"],
                    size=row["size_bytes"] == member["uncompressed_size"],
                )
                try:
                    with image_module.open(path) as image:
                        image.load()
                        row.update(width=image.width, height=image.height, image_format=image.format)
                        checks["decode"] = True
                        checks["jpeg_format"] = image.format == "JPEG"
                        checks["declared_dimensions"] = declared is not None and image.size == (declared["width"], declared["height"])
                except Exception as exc:
                    checks["decode"] = False
                    row["decode_error"] = f"{type(exc).__name__}: {exc}"
            member_identity = (manifest["archive"]["url"], member["name"])
            checks["unique_archive_member"] = member_identity not in unique_members
            checks["unique_local_path"] = path not in unique_paths
            unique_members.add(member_identity)
            unique_paths.add(path)
            row["integrity_passed"] = all(checks.values())
            if not row["integrity_passed"]:
                errors.append({"path": str(path), "failed_checks": [key for key, value in checks.items() if not value]})
            rows.append(row)
            window_rows.append(row)
        windows.append({
            "id": window["id"], "scene": window["scene"], "root": str(root),
            "manifest": manifest_input, "frames": window["frames"],
            "image_count": len(window_rows),
            "camera_counts": dict(Counter(row["camera"] for row in window_rows)),
            "dimension_counts": dict(Counter(f"{row['width']}x{row['height']}" for row in window_rows if row["checks"].get("decode"))),
            "integrity_passed": all(row["integrity_passed"] for row in window_rows),
        })
    archive_identity_keys = ("url", "etag", "size_bytes", "provider_declared_sha256")
    archive_identity_consistent = all(
        all(archive.get(key) == archives[0].get(key) for key in archive_identity_keys)
        for archive in archives
    )
    if not archive_identity_consistent:
        errors.append({"failed_checks": ["archive_identity_consistent"]})
    passed = not errors
    return {
        "inventory_id": config["inventory_id"],
        "purpose": config["purpose"],
        "metadata": metadata_input,
        "metadata_manifest": metadata_manifest_input,
        "archive": archives[0],
        "archive_identity_consistent": archive_identity_consistent,
        "summary": {
            "scene_count": len({window["scene"] for window in windows}),
            "window_count": len(windows), "image_count": len(rows),
            "unique_archive_member_count": len(unique_members),
            "integrity_passed_image_count": sum(row["integrity_passed"] for row in rows),
            "all_selected_member_checks_passed": passed,
        },
        "windows": windows, "images": rows, "errors": errors,
        "evidence_decision": "down-weighted" if passed else "rejected",
        "member_integrity_decision": "accepted" if passed else "rejected",
        "source_availability_gate_passed": False,
        "provenance_gaps": config["provenance_gaps"],
        "boundary": "Only the declared real RGB members and metadata identity are inventoried. Passing verifies local agreement with frozen extraction manifests; it does not verify original nuScenes identity/split, independent physical calibration, or reality equivalence.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/credibility_real_anchors_001.json")
    parser.add_argument("--output", required=True, help="New JSON file; existing files are never overwritten")
    args = parser.parse_args()
    output = resolve(args.output)
    if output.exists():
        parser.error(f"output already exists: {output}; choose a new path")
    try:
        from PIL import Image
    except ImportError:
        parser.error("Pillow is required; use /home/yawei/HUGSIM/.pixi/envs/default/bin/python")
    config_path = resolve(args.config)
    try:
        config = json.loads(config_path.read_text())
        report = inventory(config, Image)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(f"inventory prerequisite failed: {exc}")
    report["execution"] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(), "cwd": str(Path.cwd()),
        "python": sys.executable, "script_sha256": sha256(Path(__file__)),
        "config": {"path": str(config_path), "sha256": sha256(config_path)},
        "output": str(output),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(output), **report["summary"], "evidence_decision": report["evidence_decision"]}))
    return 0 if report["summary"]["all_selected_member_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
