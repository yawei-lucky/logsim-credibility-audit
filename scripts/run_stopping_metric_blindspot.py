#!/usr/bin/env python3
"""Finite-class qualification of stopping-task instruments, not a driving AD.

The analytical auditor and event-stepped reference share a declared *synthetic*
contract, but have separate control/dynamics implementations. No HUGSIM output
is treated as truth. No stochastic traffic probabilities are estimated.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def confirmation_index(missing: tuple[bool, ...], required: int = 2) -> int:
    if required < 1:
        raise ValueError("confirmation_frames must be positive")
    for end in range(required - 1, len(missing)):
        if not any(missing[end - required + 1:end + 1]):
            return end
    raise ValueError("No complete confirmation in the observation window")


def longest_missing(missing: tuple[bool, ...]) -> int:
    return max((len(list(group)) for value, group in itertools.groupby(missing)
                if value), default=0)


def mask_from_indices(n: int, indices) -> tuple[bool, ...]:
    indices = tuple(indices)
    if len(set(indices)) != len(indices) or any(i < 0 or i >= n for i in indices):
        raise ValueError("Missing indices must be unique and in range")
    return tuple(i in indices for i in range(n))


def validate_plant(speed: float, decel: float, delay: float) -> None:
    if not all(math.isfinite(x) for x in (speed, decel, delay)):
        raise ValueError("Non-finite plant parameters")
    if speed <= 0 or decel <= 0 or delay < 0:
        raise ValueError("Require positive speed/deceleration and nonnegative delay")


def stopping_boundary(speed: float, decel: float, confirmation_s: float,
                      delay: float) -> float:
    validate_plant(speed, decel, delay)
    if not math.isfinite(confirmation_s) or confirmation_s < 0:
        raise ValueError("Invalid confirmation time")
    return speed * (confirmation_s + delay) + speed * speed / (2 * decel)


def boundary_interval(speed: float, decel: float, measured_confirmation_s: float,
                      timing_error_s: float, delay_interval_s) -> tuple[float, float]:
    low, high = delay_interval_s
    if timing_error_s < 0 or low < 0 or high < low:
        raise ValueError("Invalid uncertainty interval")
    return (
        stopping_boundary(speed, decel, max(0.0, measured_confirmation_s - timing_error_s), low),
        stopping_boundary(speed, decel, measured_confirmation_s + timing_error_s, high),
    )


def outcome(gap: float, distance: float, tol: float = 1e-8) -> str:
    if gap > distance + tol:
        return "clear"
    if gap < distance - tol:
        return "crossing"
    return "boundary"


def interval_verdict(gap: float, interval, tol: float = 1e-8) -> str:
    if gap > interval[1] + tol:
        return "clear"
    if gap < interval[0] - tol:
        return "crossing"
    return "unresolved"


def simulate_reference(missing: tuple[bool, ...], speed: float, decel: float,
                       delay: float, observation_dt: float = 0.1,
                       integration_dt: float = 0.01, required: int = 2,
                       record: bool = False) -> dict:
    """Integrate x'=v, v'=a with separate, causal, latching control.

    Does NOT call confirmation_index(), stopping_boundary(), or boundary_interval().
    Integrator steps are split at observations, actuation onset, and zero speed.
    The obstacle does not exert a force: this is a free-stop/plane-crossing test.
    """
    validate_plant(speed, decel, delay)
    if observation_dt <= 0 or integration_dt <= 0 or required < 1 or not missing:
        raise ValueError("Invalid clock/controller configuration")
    t, x, v = 0.0, 0.0, speed
    next_obs, streak = 0, 0
    command = brake = None
    states = []
    deadline = len(missing) * observation_dt + delay + speed / decel + 1.0
    while v > 1e-12:
        if t > deadline:
            raise RuntimeError("Reference failed to stop within its finite bound")
        if next_obs < len(missing) and next_obs * observation_dt <= t + 1e-11:
            streak = 0 if missing[next_obs] else streak + 1
            if streak >= required and command is None:
                command = next_obs * observation_dt
                brake = command + delay
            next_obs += 1
        if next_obs == len(missing) and command is None:
            raise ValueError("No confirmed target; no silent tail fill permitted")
        a = -decel if brake is not None and t >= brake - 1e-11 else 0.0
        if record:
            states.append({"t_s": t, "x_m": x, "v_mps": v, "a_mps2": a,
                           "command_latched": command is not None,
                           "last_observation_index": next_obs - 1})
        h = integration_dt
        if next_obs < len(missing):
            h = min(h, next_obs * observation_dt - t)
        if brake is not None and brake > t + 1e-11:
            h = min(h, brake - t)
        if a < 0:
            h = min(h, v / decel)
        if h <= 1e-12:
            raise RuntimeError("Reference clock made no progress")
        x += v * h + 0.5 * a * h * h
        v = max(0.0, v + a * h)
        t += h
    if record:
        states.append({"t_s": t, "x_m": x, "v_mps": 0.0, "a_mps2": 0.0,
                       "command_latched": True, "last_observation_index": next_obs - 1})
    return {"free_stop_distance_m": x, "stop_time_s": t,
            "command_time_s": command, "brake_onset_s": brake, "states": states}


def dump_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def dump_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(row: dict, panel: str):
    base = (row["observation_count"], row["missing_count"])
    if panel == "V0_marginal":
        return base
    if panel == "V1_longest_gap":
        return base + (row["longest_missing_frames"],)
    if panel == "V2_confirmation":
        return base + (row["confirmation_index"],)
    raise ValueError(panel)


def panel_audit(rows: list[dict], reference: dict, tolerance: float, gap: float) -> dict:
    result = {}
    for panel in ("V0_marginal", "V1_longest_gap", "V2_confirmation"):
        matched = [r for r in rows if signature(r, panel) == signature(reference, panel)]
        ref_distance = reference["numeric_boundary_m"]
        compatible = [r["numeric_boundary_m"] for r in matched]
        result[panel] = {
            "matched_patterns_including_reference": len(matched),
            "hidden_boundary_difference_gt_tolerance": sum(
                abs(x - ref_distance) > tolerance for x in compatible),
            "opposite_outcome_at_design_gap": sum(
                outcome(gap, x) != outcome(gap, ref_distance) for x in compatible),
            "compatible_boundary_interval_m": [min(compatible), max(compatible)],
            "remaining_boundary_diameter_m": max(compatible) - min(compatible),
            "sound_outcome_given_only_panel": interval_verdict(gap, (min(compatible), max(compatible))),
        }
    return result


def make_visuals(out: Path, cfg: dict, design: list[dict], rows: list[dict],
                 summary: dict, video: bool) -> None:
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter
    from matplotlib.patches import Rectangle

    plt.rcParams.update({"font.family": "Noto Sans CJK JP", "axes.unicode_minus": False,
                         "font.size": 11})
    names = ["normal", "dispersed", "early_burst", "alternating", "late_burst"]
    labels = {"normal": "正常无缺失", "dispersed": "分散缺失", "early_burst": "前段连续缺失",
              "alternating": "交替打断确认", "late_burst": "制动请求后缺失",
              "late_dispersed": "请求后分散缺失", "middle_burst": "中段连续缺失"}
    by_name = {r["name"]: r for r in design}
    colors = ["#555e70", "#168b79", "#e08934", "#ba4757", "#517cc0"]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), height_ratios=[1, 1.3], layout="constrained")
    obs = np.array([[not x for x in by_name[name]["missing_mask"]] for name in names])
    axes[0].imshow(obs, aspect="auto", cmap=matplotlib.colors.ListedColormap(["#e7a5a7", "#92cdbc"]),
                   vmin=0, vmax=1, extent=(-0.05, 1.15, 4.5, -0.5))
    for i, name in enumerate(names):
        axes[0].plot(by_name[name]["confirmation_s"], i, marker="*", color="#111111", ms=13)
    axes[0].set(yticks=range(len(names)), yticklabels=[labels[n] for n in names],
                xticks=np.arange(0, 1.2, 0.1), xlabel="观测时间 (s)",
                title="绿=信息可用；红=缺失；星号=连续两帧确认完成（冻结控制规则）")
    for name, color in zip(names, colors):
        r = by_name[name]
        states = r["states"]
        axes[1].plot([s["t_s"] for s in states], [s["x_m"] for s in states], color=color,
                     label=f'{labels[name]}：停车边界 {r["numeric_boundary_m"]:.1f} m')
        axes[1].scatter([r["brake_onset_s"]],
                        [cfg["design"]["speed_mps"] * r["brake_onset_s"]], color=color)
    gap = cfg["design"]["obstacle_gap_m"]
    axes[1].axhline(gap, ls="--", color="black", label=f"障碍平面 {gap:g} m")
    axes[1].set(xlabel="时间 (s)", ylabel="自由停车过程的前进距离 (m)",
                title="同为 4/12 帧缺失，停车边界仍不同；超过虚线是几何越界，不模拟撞击")
    axes[1].legend(ncol=2, fontsize=10)
    axes[1].grid(alpha=0.2)
    fig.suptitle("指标盲区 001 | 合成参考系统，不是 HUGSIM / SparseDrive / 真实道路实验", fontsize=14)
    fig.savefig(out / "temporal_mechanism.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    ref = summary["panel_audit"]
    for i, (panel, label, color) in enumerate(zip(ref, ["V0 缺失比例", "V1 再加最长缺失", "V2 再加确认时间"], colors[1:4])):
        lower, upper = ref[panel]["compatible_boundary_interval_m"]
        axes[0].plot([lower, upper], [i, i], lw=12, color=color, solid_capstyle="round")
        axes[0].scatter([lower, upper], [i, i], color=color, s=100, zorder=3)
        axes[0].text(upper + 0.2, i, f"{lower:.1f}–{upper:.1f} m", va="center")
    axes[0].axvline(gap, ls="--", color="black")
    axes[0].set(yticks=range(3), yticklabels=["缺失比例", "+最长缺失段", "+确认时间"],
                xlabel="与 dispersed 面板相同的可能停车边界 (m)", xlim=(10.5, 22),
                title="证据能排除哪些错误世界？\n495 个有限人工模式，无现实概率含义")
    axes[0].invert_yaxis()
    speeds = np.linspace(5, 16, 100)
    for name, color in zip(names[:4], colors[:4]):
        r = by_name[name]
        bounds = [stopping_boundary(v, cfg["design"]["deceleration_mps2"], r["confirmation_s"],
                                    cfg["design"]["actuation_delay_s"]) for v in speeds]
        axes[1].plot(speeds, bounds, color=color, label=labels[name])
    axes[1].scatter([10], [gap], color="black", marker="x", s=60, label="设计点")
    axes[1].set(xlabel="初始速度 (m/s)", ylabel="避免越界所需间距边界 (m)",
                title="曲线上方可停住，曲线下方越界\n只适用于本轮一维锁存制动合同")
    axes[1].legend(fontsize=10)
    axes[1].grid(alpha=0.2)
    fig.savefig(out / "boundary_and_evidence.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
    xs = [r["longest_missing_frames"] for r in rows]
    ys = [r["numeric_boundary_m"] for r in rows]
    axes[0].scatter(xs, ys, alpha=0.15, color="#b54c5b")
    axes[0].set(xlabel="最长连续缺失帧数", ylabel="停车边界 (m)",
                title="最长缺失仍不足：相同值对应多个边界")
    axes[1].scatter([r["confirmation_s"] for r in rows], ys, alpha=0.15, color="#168b79")
    axes[1].set(xlabel="首次连续两帧确认时间 (s)", ylabel="停车边界 (m)",
                title="固定车辆与控制合同后，确认时间确定边界")
    fig.savefig(out / "metric_blindspots.png", dpi=150)
    plt.close(fig)

    if not video:
        return
    fig, axes = plt.subplots(4, 1, figsize=(12, 7), layout="constrained")
    cars, info = [], []
    for ax, name, color in zip(axes, names[:4], colors[:4]):
        ax.set(xlim=(-2, 22), ylim=(-1, 1), yticks=[], xlabel="前保险杠距起点 (m)")
        ax.axhline(0, color="#dddddd", lw=3)
        ax.axvline(gap, color="black", lw=3)
        ax.set_title(labels[name], loc="left", fontsize=12)
        patch = Rectangle((-1.6, -0.24), 1.6, 0.48, color=color)
        ax.add_patch(patch)
        cars.append(patch)
        info.append(ax.text(0.99, 0.92, "", transform=ax.transAxes, ha="right", va="top", fontsize=10))
    title = fig.suptitle("合成参考系统示意：不是相机画面，不是 HUGSIM / SparseDrive", fontsize=14)
    writer = FFMpegWriter(fps=20, codec="libx264", extra_args=["-pix_fmt", "yuv420p", "-crf", "20"])
    with writer.saving(fig, str(out / "stopping_comparison.mp4"), dpi=100):
        # 10 s viewing time: 0..3.3 s world time plus a final hold.
        for frame in range(200):
            t = min(3.3, frame / 50)
            title.set_text(f"合成参考系统示意 | 世界时间 {t:.2f} s | 固定障碍 {gap:g} m\n不是 HUGSIM / SparseDrive；红色越界标记不代表碰撞力学")
            for ax, name, car, text_obj in zip(axes, names[:4], cars, info):
                r = by_name[name]
                times = [s["t_s"] for s in r["states"]]
                x = float(np.interp(t, times, [s["x_m"] for s in r["states"]]))
                v = float(np.interp(t, times, [s["v_mps"] for s in r["states"]]))
                car.set_x(min(x, gap) - 1.6)
                car.set_hatch("xx" if x >= gap else None)
                status = "几何接触，车图在此停止" if x >= gap else ("停住" if v < 1e-6 else "行进")
                oi = min(int(t / cfg["observation_dt_s"] + 1e-9), cfg["observation_count"] - 1)
                observed = "窗口结束" if t > 1.1 else ("缺失" if r["missing_mask"][oi] else "可用")
                text_obj.set_text(f"观测 {observed} | {status} | 确认 {r['confirmation_s']:.1f}s → 制动 {r['brake_onset_s']:.1f}s\n自由停车边界 {r['numeric_boundary_m']:.1f}m；净余量 {gap-r['numeric_boundary_m']:+.1f}m")
            writer.grab_frame()
    fig.savefig(out / "comparison_end.png", dpi=150)
    plt.close(fig)


def run(config_path: Path, out: Path, video: bool = True) -> dict:
    cfg = json.loads(config_path.read_text())
    n, m = cfg["observation_count"], cfg["missing_count"]
    if not 0 <= m < n <= 20 or math.comb(n, m) > 20000:
        raise ValueError("Enumeration is outside the bounded experiment budget")
    if out.exists():
        raise FileExistsError(f"Output already exists; use a new run directory: {out}")
    out.mkdir(parents=True)
    dt, k = cfg["observation_dt_s"], cfg["confirmation_frames"]
    d = cfg["design"]
    env = {"started_utc": datetime.now(timezone.utc).isoformat(), "host": socket.gethostname(),
           "role": "synthetic_reference_metric_qualification", "cwd": str(Path.cwd()),
           "python": sys.executable, "python_version": platform.python_version(),
           "command": sys.argv, "config": str(config_path.resolve()), "output": str(out.resolve()),
           "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
           "git_status": subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True),
           "source_sha256": sha256(Path(__file__)), "config_sha256": sha256(config_path),
           "preregistration_sha256": sha256(ROOT / "docs/runs/stopping_metric_blindspot_preregistration_001.md")}
    dump_json(out / "manifest.json", env)
    dump_json(out / "frozen_config.json", cfg)
    dump_json(out / "run_status.json", {"health": "started", "started_utc": env["started_utc"]})
    print(json.dumps({"health": "started", **env}, ensure_ascii=False), flush=True)
    design_masks = {tuple(v) for v in d["patterns"].values()}
    rows = []
    for indices in itertools.combinations(range(n), m):
        mask = mask_from_indices(n, indices)
        ci = confirmation_index(mask, k)
        ref = simulate_reference(mask, d["speed_mps"], d["deceleration_mps2"], d["actuation_delay_s"],
                                 dt, cfg["integration_dt_s"], k)
        analytic = stopping_boundary(d["speed_mps"], d["deceleration_mps2"], ci * dt, d["actuation_delay_s"])
        rows.append({"pattern_id": "".join("1" if x else "0" for x in mask),
                     "missing_indices": ",".join(map(str, indices)),
                     "split": "design" if indices in design_masks else "heldout",
                     "observation_count": n, "missing_count": m,
                     "available_fraction": (n - m) / n,
                     "longest_missing_frames": longest_missing(mask),
                     "confirmation_index": ci, "confirmation_s": ci * dt,
                     "analytic_boundary_m": analytic, "numeric_boundary_m": ref["free_stop_distance_m"],
                     "numeric_error_m": abs(analytic - ref["free_stop_distance_m"]),
                     "command_error_s": abs(ci * dt - ref["command_time_s"]),
                     "outcome_at_design_gap": outcome(d["obstacle_gap_m"], ref["free_stop_distance_m"])})
    dump_csv(out / "all_patterns.csv", rows)
    design = []
    for name, indices in {"normal": [], **d["patterns"]}.items():
        mask = mask_from_indices(n, indices)
        numeric = simulate_reference(mask, d["speed_mps"], d["deceleration_mps2"], d["actuation_delay_s"],
                                     dt, cfg["integration_dt_s"], k, record=True)
        item = {"name": name, "missing_indices": indices, "missing_mask": mask,
                "confirmation_s": confirmation_index(mask, k) * dt,
                "numeric_boundary_m": numeric["free_stop_distance_m"],
                "clearance_m": d["obstacle_gap_m"] - numeric["free_stop_distance_m"], **numeric}
        design.append(item)
        dump_csv(out / f"states_{name}.csv", numeric["states"])
    dump_json(out / "design_cases.json", design)
    selected = "".join("1" if x else "0" for x in mask_from_indices(n, d["patterns"][d["reference_name"]]))
    reference_row = next(r for r in rows if r["pattern_id"] == selected)
    audit = panel_audit(rows, reference_row, cfg["illustrative_boundary_equivalence_tolerance_m"],
                        d["obstacle_gap_m"])
    # No thresholds are fitted to design output. The heldout split is fixed in the config.
    held = cfg["heldout"]
    held_rows = []
    counts = {"clear": 0, "crossing": 0, "unresolved": 0, "wrong_resolved_verdicts": 0}
    params = list(itertools.product(held["speeds_mps"], held["decelerations_mps2"], held["actuation_delays_s"]))
    for row in rows:
        if row["split"] != "heldout":
            continue
        mask = tuple(x == "1" for x in row["pattern_id"])
        for pi, (v, b, delay) in enumerate(params):
            numeric = simulate_reference(mask, v, b, delay, dt, cfg["integration_dt_s"], k)
            analytic = stopping_boundary(v, b, row["confirmation_s"], delay)
            eta = held["timestamp_error_bound_s"]
            error = (-eta, 0.0, eta)[(int(row["pattern_id"], 2) + pi) % 3]
            measured = row["confirmation_s"] + error
            interval = boundary_interval(v, b, measured, eta, [delay, delay])
            wrong = 0
            for offset in held["boundary_offsets_m"]:
                gap = numeric["free_stop_distance_m"] + offset
                verdict = interval_verdict(gap, interval)
                truth = outcome(gap, numeric["free_stop_distance_m"])
                counts[verdict] += 1
                if verdict != "unresolved" and verdict != truth:
                    counts["wrong_resolved_verdicts"] += 1
                    wrong += 1
            held_rows.append({"pattern_id": row["pattern_id"], "speed_mps": v, "deceleration_mps2": b,
                              "actuation_delay_s": delay, "analytic_boundary_m": analytic,
                              "numeric_boundary_m": numeric["free_stop_distance_m"],
                              "numeric_error_m": abs(analytic - numeric["free_stop_distance_m"]),
                              "confirmation_measurement_error_s": error,
                              "interval_lower_m": interval[0], "interval_upper_m": interval[1],
                              "interval_covers_truth": interval[0] - 1e-8 <= numeric["free_stop_distance_m"] <= interval[1] + 1e-8,
                              "wrong_resolved_verdicts": wrong})
    dump_csv(out / "heldout_cases.csv", held_rows)
    mask = mask_from_indices(n, d["patterns"][d["reference_name"]])
    c = confirmation_index(mask, k) * dt
    challenge = cfg["actuation_scope_challenge"]
    actual = simulate_reference(mask, d["speed_mps"], d["deceleration_mps2"], challenge["actual_delay_s"], dt)
    assumed = stopping_boundary(d["speed_mps"], d["deceleration_mps2"], c, challenge["assumed_delay_s"])
    challenged_interval = boundary_interval(d["speed_mps"], d["deceleration_mps2"], c, 0,
                                            challenge["qualified_delay_interval_s"])
    challenge_gap = (assumed + actual["free_stop_distance_m"]) / 2
    convergence = []
    for name, indices in d["patterns"].items():
        mask = mask_from_indices(n, indices)
        predicted = stopping_boundary(d["speed_mps"], d["deceleration_mps2"], confirmation_index(mask, k) * dt,
                                       d["actuation_delay_s"])
        for step in cfg["integration_check_steps_s"]:
            sim = simulate_reference(mask, d["speed_mps"], d["deceleration_mps2"], d["actuation_delay_s"], dt, step, k)
            convergence.append({"name": name, "integration_dt_s": step,
                                "numeric_boundary_m": sim["free_stop_distance_m"],
                                "error_m": abs(predicted - sim["free_stop_distance_m"])})
    dump_csv(out / "integration_crosscheck.csv", convergence)
    summary = {
        "experiment_id": cfg["experiment_id"], "scope": cfg["scope"],
        "model_class": "1D stationary obstacle, correct available observations, 2-frame confirmation, latching brake, constant deceleration",
        "counts": {"all_patterns": len(rows), "design_patterns": len(design_masks),
                   "heldout_patterns": sum(r["split"] == "heldout" for r in rows),
                   "normal_controls_outside_enumeration": 1, "heldout_parameter_combinations": len(params),
                   "heldout_cases": len(held_rows), "heldout_gap_verdicts": len(held_rows) * len(held["boundary_offsets_m"])},
        "panel_audit": audit,
        "design_cases": [{key: value for key, value in r.items() if key not in ("states", "missing_mask")}
                         for r in design],
        "heldout": {"max_numeric_error_m": max(r["numeric_error_m"] for r in held_rows),
                    "interval_coverage_count": sum(r["interval_covers_truth"] for r in held_rows),
                    "verdict_counts": counts, "distribution": "finite designed grid, not a real-world probability sample"},
        "design_max_numeric_error_m": max(r["numeric_error_m"] for r in rows),
        "crosscheck_max_numeric_error_m": max(r["error_m"] for r in convergence),
        "actuation_scope_challenge": {"confirmation_s": c, "assumed_boundary_m": assumed,
                                      "actual_numeric_boundary_m": actual["free_stop_distance_m"],
                                      "boundary_error_m": actual["free_stop_distance_m"] - assumed,
                                      "gap_m": challenge_gap,
                                      "point_prediction": outcome(challenge_gap, assumed),
                                      "reference_outcome": outcome(challenge_gap, actual["free_stop_distance_m"]),
                                      "qualified_boundary_interval_m": challenged_interval,
                                      "interval_verdict": interval_verdict(challenge_gap, challenged_interval)},
        "limitations": ["Not HUGSIM, SparseDrive, real camera, learned model, or physical collision dynamics",
                        "Marginal panel is a restricted abstraction, not the complete historical audit",
                        "Both reference implementations share synthetic model assumptions",
                        "Heldout means disjoint patterns/parameters within the same specified contract",
                        "No real-world frequency, general sensitivity, or universal completeness estimate"],
    }
    checks = [summary["design_max_numeric_error_m"], summary["heldout"]["max_numeric_error_m"],
              summary["crosscheck_max_numeric_error_m"]]
    summary["numerical_verification_passed"] = max(checks) <= cfg["numerical_tolerance_m"]
    dump_json(out / "summary.json", summary)
    if not summary["numerical_verification_passed"]:
        raise RuntimeError("Numerical/reference check failed; results retained, do not accept")
    print(json.dumps({"health": "numerical_checks_passed", "counts": summary["counts"],
                      "panel_audit": audit, "heldout": summary["heldout"]}, ensure_ascii=False), flush=True)
    make_visuals(out, cfg, design, rows, summary, video)
    dump_json(out / "run_status.json", {"health": "complete", "started_utc": env["started_utc"],
                                         "completed_utc": datetime.now(timezone.utc).isoformat()})
    artifact_hashes = {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size}
                       for p in sorted(out.iterdir()) if p.is_file()}
    dump_json(out / "artifact_hashes.json", artifact_hashes)
    print(json.dumps({"health": "complete", "output": str(out.resolve())}), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/stopping_metric_blindspot_001.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--no-video", action="store_true")
    args = parser.parse_args()
    try:
        run(args.config, args.output_dir, video=not args.no_video)
    except Exception as exc:
        print(json.dumps({"health": "failed", "error": repr(exc)}, ensure_ascii=False), file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    main()
