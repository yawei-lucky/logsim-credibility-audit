#!/usr/bin/env python3
"""Inventory local HUGSIM assets for matched AD receiver validation readiness."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from audit_hugsim_source_anchor import audit_scene_anchor


def discover_scene_dirs(assets_root: Path) -> list[Path]:
    """Return scene directories that contain HUGSIM reconstruction metadata."""
    assets_root = assets_root.resolve()
    if (assets_root / "meta_data.json").is_file():
        return [assets_root]
    metadata_files = sorted(assets_root.rglob("meta_data.json"))
    return [path.parent for path in metadata_files]


def candidate_source_roots(scene_dir: Path, source_roots: list[Path]) -> list[Path]:
    if not source_roots:
        return [scene_dir]

    candidates: list[Path] = []
    for root in source_roots:
        root = root.resolve()
        candidates.extend(
            [
                root / scene_dir.name,
                root / f"{scene_dir.name}_0_180",
                root,
            ]
        )
    deduped = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            deduped.append(candidate)
            seen.add(key)
    return deduped


def best_anchor_result(
    scene_dir: Path,
    source_roots: list[Path],
    camera_yaml: Path | None,
    sim_run: Path | None,
    dataset_reader: Path | None,
    hugsim_repo: Path | None,
) -> dict[str, Any]:
    results = []
    for source_root in candidate_source_roots(scene_dir, source_roots):
        try:
            result = audit_scene_anchor(
                scene_dir=scene_dir,
                source_root=source_root,
                camera_yaml=camera_yaml,
                sim_run=sim_run if scene_dir.name in str(sim_run or "") else None,
                dataset_reader=dataset_reader,
                hugsim_repo=hugsim_repo,
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            result = {
                "scene_dir": str(scene_dir.resolve()),
                "source_root": str(source_root.resolve()),
                "metadata": {},
                "source_observations": {},
                "gate": {
                    "status": "blocked",
                    "reasons": [f"anchor audit failed: {error}"],
                    "permitted_claim": "no source-anchor claim",
                },
            }
        results.append(result)

    return max(
        results,
        key=lambda item: (
            int(item.get("gate", {}).get("status") == "ready"),
            int(item.get("source_observations", {}).get("valid_real_rgb_count") or 0),
            int(item.get("source_observations", {}).get("existing_real_rgb_count") or 0),
        ),
    )


def summarize_scene(anchor: dict[str, Any]) -> dict[str, Any]:
    metadata = anchor.get("metadata", {})
    observations = anchor.get("source_observations", {})
    gate = anchor.get("gate", {})
    first_candidate = (metadata.get("first_reader_test_candidates") or [None])[0]
    camera_comparison = anchor.get("standard_sim_camera_comparison", {})
    return {
        "scene": Path(str(anchor.get("scene_dir", ""))).name,
        "scene_dir": anchor.get("scene_dir"),
        "source_root": anchor.get("source_root"),
        "source_anchor_status": gate.get("status", "blocked"),
        "blocking_reasons": gate.get("reasons", []),
        "expected_real_rgb_count": observations.get("expected_real_rgb_count"),
        "existing_real_rgb_count": observations.get("existing_real_rgb_count"),
        "valid_real_rgb_count": observations.get("valid_real_rgb_count"),
        "source_identity_complete": observations.get("source_identity_complete"),
        "metadata_complete": bool(
            metadata.get("all_camera_geometry_valid")
            and metadata.get("timestamp_groups_complete")
            and metadata.get("rgb_paths_unique")
            and metadata.get("frame_indices_strictly_increasing")
            and metadata.get("frame_records_time_ordered")
            and metadata.get("native_dynamics_complete")
        ),
        "timestamp_count": metadata.get("timestamp_count"),
        "camera_counts": metadata.get("camera_counts"),
        "reader_test_candidate_timestamp_count": metadata.get(
            "reader_test_candidate_timestamp_count"
        ),
        "first_reader_test_candidate": first_candidate,
        "standard_sim_camera_matched_pose_decision": camera_comparison.get(
            "matched_pose_decision"
        ),
    }


def readiness_status(scene_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    ready_scenes = [
        scene
        for scene in scene_summaries
        if scene["source_anchor_status"] == "ready"
    ]
    reason_counts: Counter[str] = Counter()
    for scene in scene_summaries:
        for reason in scene.get("blocking_reasons", []):
            reason_counts[reason] += 1

    if not scene_summaries:
        status = "blocked"
        reasons = ["no local HUGSIM scene metadata was found"]
        permitted_claim = "no local source-anchor or AD receiver claim"
    elif not ready_scenes:
        status = "blocked"
        reasons = sorted(reason_counts) or ["no source-anchor-ready scene found"]
        permitted_claim = (
            "local assets support availability-gap diagnosis only; "
            "no real-vs-sim AD input comparison is established"
        )
    else:
        status = "pending_exact_matched_pose_render"
        reasons = [
            "at least one source anchor is ready, but an exact matched-pose "
            "HUGSIM render manifest and frozen AD receiver contract are still required"
        ]
        permitted_claim = (
            "source-anchor-ready candidate exists; receiver equivalence is not tested"
        )

    return {
        "status": status,
        "reasons": reasons,
        "blocking_reason_counts": dict(sorted(reason_counts.items())),
        "permitted_claim": permitted_claim,
        "ready_scene_names": [scene["scene"] for scene in ready_scenes],
    }


def build_readiness_audit(
    assets_root: Path,
    source_roots: list[Path] | None = None,
    camera_yaml: Path | None = None,
    sim_run: Path | None = None,
    dataset_reader: Path | None = None,
    hugsim_repo: Path | None = None,
) -> dict[str, Any]:
    source_roots = source_roots or []
    scene_dirs = discover_scene_dirs(assets_root)
    anchors = [
        best_anchor_result(
            scene_dir=scene_dir,
            source_roots=source_roots,
            camera_yaml=camera_yaml,
            sim_run=sim_run,
            dataset_reader=dataset_reader,
            hugsim_repo=hugsim_repo,
        )
        for scene_dir in scene_dirs
    ]
    scene_summaries = [summarize_scene(anchor) for anchor in anchors]
    total_expected = sum(
        int(scene.get("expected_real_rgb_count") or 0) for scene in scene_summaries
    )
    total_existing = sum(
        int(scene.get("existing_real_rgb_count") or 0) for scene in scene_summaries
    )
    total_valid = sum(
        int(scene.get("valid_real_rgb_count") or 0) for scene in scene_summaries
    )
    total_candidates = sum(
        int(scene.get("reader_test_candidate_timestamp_count") or 0)
        for scene in scene_summaries
    )

    ad_gate = readiness_status(scene_summaries)
    return {
        "audit_id": "hugsim_ad_receiver_readiness",
        "date": date.today().isoformat(),
        "scope": {
            "assets_root": str(assets_root.resolve()),
            "source_roots": [str(root.resolve()) for root in source_roots],
            "camera_yaml": str(camera_yaml.resolve()) if camera_yaml else None,
            "sim_run": str(sim_run.resolve()) if sim_run else None,
            "dataset_reader": str(dataset_reader.resolve()) if dataset_reader else None,
            "hugsim_repo": str(hugsim_repo.resolve()) if hugsim_repo else None,
        },
        "summary": {
            "local_scene_count": len(scene_summaries),
            "source_anchor_ready_scene_count": len(ad_gate["ready_scene_names"]),
            "source_anchor_blocked_scene_count": len(scene_summaries)
            - len(ad_gate["ready_scene_names"]),
            "total_expected_real_rgb_count": total_expected,
            "total_existing_real_rgb_count": total_existing,
            "total_valid_real_rgb_count": total_valid,
            "reader_test_candidate_timestamp_count": total_candidates,
            "new_hugsim_scenario_generated": False,
            "new_hugsim_rollout_run": False,
            "new_empirical_result_type": "local_asset_and_pairing_readiness_audit",
        },
        "ad_receiver_real_sim_comparison_gate": ad_gate,
        "next_action": (
            "Recover licensed real camera observations, immutable source identity, "
            "and ASAP mapping for a listed scene; then render exact metadata K and "
            "camtoworld poses before running a frozen camera-only AD receiver."
        ),
        "scenes": scene_summaries,
    }


def format_markdown(audit: dict[str, Any]) -> str:
    gate = audit["ad_receiver_real_sim_comparison_gate"]
    summary = audit["summary"]
    lines = [
        "# HUGSIM AD Receiver Readiness 001",
        "",
        f"Date: {audit['date']}",
        "",
        "## Result",
        "",
        f"Gate status: `{gate['status']}`",
        "",
        "This run did not generate a new HUGSIM scenario or rollout. It checks "
        "whether local HUGSIM assets are ready for the next research step: a "
        "matched real-versus-simulation input comparison using the same frozen "
        "AD receiver.",
        "",
        "Permitted claim:",
        "",
        f"> {gate['permitted_claim']}",
        "",
        "## Local Inventory",
        "",
        "| Item | Count |",
        "|---|---:|",
        f"| Local HUGSIM scenes | {summary['local_scene_count']} |",
        f"| Source-anchor-ready scenes | {summary['source_anchor_ready_scene_count']} |",
        f"| Blocked scenes | {summary['source_anchor_blocked_scene_count']} |",
        f"| Expected real RGB files | {summary['total_expected_real_rgb_count']} |",
        f"| Existing real RGB files | {summary['total_existing_real_rgb_count']} |",
        f"| Valid real RGB files | {summary['total_valid_real_rgb_count']} |",
        f"| Reader-derived test timestamp candidates | {summary['reader_test_candidate_timestamp_count']} |",
        "",
        "## Scene Summary",
        "",
        "| Scene | Gate | Real RGB | Source identity | Test candidates | Blocking reason |",
        "|---|---|---:|---|---:|---|",
    ]
    for scene in audit["scenes"]:
        reasons = "; ".join(scene.get("blocking_reasons") or ["none"])
        identity = "yes" if scene.get("source_identity_complete") else "no"
        lines.append(
            "| {scene} | `{gate}` | {valid}/{expected} | {identity} | {candidates} | {reasons} |".format(
                scene=scene["scene"],
                gate=scene["source_anchor_status"],
                valid=scene.get("valid_real_rgb_count"),
                expected=scene.get("expected_real_rgb_count"),
                identity=identity,
                candidates=scene.get("reader_test_candidate_timestamp_count"),
                reasons=reasons,
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The current machine still cannot run the core AD credibility test, "
            "because no local scene has a complete real RGB and immutable source "
            "identity anchor. The existing simulated rollout remains useful for "
            "simulator-internal geometry and metric-response tests, but it is "
            "not a real-sim pair for an AD receiver.",
            "",
            "The next material experiment is therefore not another same-scene "
            "counterfactual rollout. It is to recover the real source frames and "
            "source identity, render the exact metadata poses, and then feed the "
            "matched real and simulated observations to the same frozen camera-"
            "only AD receiver.",
            "",
            "## Next Action",
            "",
            audit["next_action"],
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-root", required=True, type=Path)
    parser.add_argument("--source-root", action="append", default=[], type=Path)
    parser.add_argument("--camera-yaml", type=Path)
    parser.add_argument("--sim-run", type=Path)
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
    audit = build_readiness_audit(
        assets_root=args.assets_root,
        source_roots=args.source_root,
        camera_yaml=args.camera_yaml,
        sim_run=args.sim_run,
        dataset_reader=args.dataset_reader,
        hugsim_repo=args.hugsim_repo,
    )
    payload = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    if args.output:
        write_new(args.output, payload)
    if args.markdown_output:
        write_new(args.markdown_output, format_markdown(audit))
    print(payload)
    return (
        0
        if audit["ad_receiver_real_sim_comparison_gate"]["status"]
        != "blocked"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
