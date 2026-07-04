#!/usr/bin/env python3
"""Check local prerequisites for a minimal HUGSIM smoke test.

This script does not run HUGSIM. It only checks whether a local clone and
selected paths look ready for a Phase 1 smoke test.

Example:
    python scripts/check_hugsim_smoke_prereqs.py \
        --hugsim-root /path/to/HUGSIM \
        --scenario configs/benchmark/nuscenes/scene-0383-easy-00.yaml \
        --base configs/sim/nuscenes_base.yaml \
        --camera configs/sim/nuscenes_camera.yaml \
        --kinematic configs/sim/kinematic.yaml \
        --assets-root /path/to/downloaded/XDimLab_HUGSIM \
        --find-scene
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any


def rel(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def exists_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
    }


def read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def extract_yaml_scalar(text: str, key: str) -> str | None:
    # Lightweight extraction avoids requiring PyYAML for this preflight script.
    pattern = rf"^\s*{re.escape(key)}\s*:\s*([^#\n]+)"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip().strip('"\'')


def scan_scene_asset(assets_root: Path, scene_name: str | None) -> dict[str, Any]:
    if not assets_root:
        return {"checked": False, "reason": "assets_root not provided"}
    if not assets_root.exists():
        return {"checked": True, "assets_root_exists": False, "matches": []}
    if not scene_name:
        return {"checked": True, "assets_root_exists": True, "reason": "scene_name not found in scenario", "matches": []}

    matches: list[str] = []
    # Keep scan bounded enough for large asset trees.
    max_matches = 20
    for current_root, dirs, files in os.walk(assets_root):
        current = Path(current_root)
        if scene_name in current.name:
            matches.append(str(current))
        for filename in files:
            if scene_name in filename:
                matches.append(str(current / filename))
        if len(matches) >= max_matches:
            break
    return {"checked": True, "assets_root_exists": True, "scene_name": scene_name, "matches": matches[:max_matches]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight checks for HUGSIM smoke-test setup.")
    parser.add_argument("--hugsim-root", required=True, help="Path to a local HUGSIM clone.")
    parser.add_argument("--scenario", default="configs/benchmark/nuscenes/scene-0383-easy-00.yaml")
    parser.add_argument("--base", default="configs/sim/nuscenes_base.yaml")
    parser.add_argument("--camera", default="configs/sim/nuscenes_camera.yaml")
    parser.add_argument("--kinematic", default="configs/sim/kinematic.yaml")
    parser.add_argument("--assets-root", default=None, help="Optional downloaded HUGSIM asset root.")
    parser.add_argument("--find-scene", action="store_true", help="Search assets-root for the scenario scene name.")
    args = parser.parse_args()

    root = Path(args.hugsim_root).expanduser().resolve()
    assets_root = Path(args.assets_root).expanduser().resolve() if args.assets_root else None

    critical_relpaths = [
        "README.md",
        "LICENSE",
        "pixi.toml",
        "closed_loop.py",
        "sim/hugsim_env/envs/hug_sim.py",
        "sim/utils/plan.py",
        "sim/utils/agent_controller.py",
        "sim/utils/sim_utils.py",
        "sim/utils/score_calculator.py",
        "sim/utils/launch_ad.py",
    ]

    config_paths = {
        "scenario": rel(root, args.scenario),
        "base": rel(root, args.base),
        "camera": rel(root, args.camera),
        "kinematic": rel(root, args.kinematic),
    }

    scenario_text = read_text_safe(config_paths["scenario"])
    scene_name = extract_yaml_scalar(scenario_text, "scene_name")
    mode = extract_yaml_scalar(scenario_text, "mode")
    load_hd_map = extract_yaml_scalar(scenario_text, "load_HD_map")

    report: dict[str, Any] = {
        "hugsim_root": str(root),
        "root_exists": root.exists(),
        "tooling": {
            "pixi": shutil.which("pixi"),
            "python": sys.executable,
            "huggingface_cli": shutil.which("huggingface-cli"),
            "git": shutil.which("git"),
        },
        "critical_files": {p: exists_record(root / p) for p in critical_relpaths},
        "configs": {name: exists_record(path) for name, path in config_paths.items()},
        "scenario_summary": {
            "scene_name": scene_name,
            "mode": mode,
            "load_HD_map": load_hd_map,
            "contains_plan_list": "plan_list" in scenario_text,
            "contains_attack_planner": "AttackPlanner" in scenario_text,
            "contains_constant_planner": "ConstantPlanner" in scenario_text,
        },
        "asset_scan": scan_scene_asset(assets_root, scene_name) if args.find_scene else {"checked": False},
    }

    missing_critical = [p for p, record in report["critical_files"].items() if not record["exists"]]
    missing_configs = [name for name, record in report["configs"].items() if not record["exists"]]

    report["result"] = {
        "ready_for_manual_runtime_attempt": not missing_critical and not missing_configs,
        "missing_critical_files": missing_critical,
        "missing_configs": missing_configs,
        "recommended_next_step": "fix missing files/configs first" if (missing_critical or missing_configs) else "inspect config paths and run HUGSIM debug path or deterministic plan-pipe test",
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["result"]["ready_for_manual_runtime_attempt"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
