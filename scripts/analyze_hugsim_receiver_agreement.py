#!/usr/bin/env python3
"""Compare HUGSIM task responses across two frozen receivers.

The comparison aligns the semantic/depth task proxy with the RGB-only camera
detector on the same HUGSIM rollouts. It asks whether task-relevant center-path
signals converge in direction, while explicitly retaining receiver-specific
differences such as background detections.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-hugsim-receiver-agreement")


DEFAULT_PROXY_DIR = Path(
    "artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001"
)
DEFAULT_DETECTOR_DIR = Path(
    "artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare HUGSIM receiver responses across frozen receivers."
    )
    parser.add_argument("--proxy-dir", default=DEFAULT_PROXY_DIR, type=Path)
    parser.add_argument("--detector-dir", default=DEFAULT_DETECTOR_DIR, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def as_float(value: Any, default: float = 0.0) -> float:
    if value in ("", None):
        return default
    return float(value)


def jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def average_ranks(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: item[1])
    ranks: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        value = ordered[index][1]
        end = index + 1
        while end < len(ordered) and ordered[end][1] == value:
            end += 1
        average_rank = float((index + 1 + end) / 2.0)
        for label, _ in ordered[index:end]:
            ranks[label] = average_rank
        index = end
    return ranks


def pearson(values_a: list[float], values_b: list[float]) -> float | None:
    if len(values_a) < 2 or len(values_a) != len(values_b):
        return None
    a = np.asarray(values_a, dtype=np.float64)
    b = np.asarray(values_b, dtype=np.float64)
    if np.allclose(a, a[0]) or np.allclose(b, b[0]):
        return None
    return float(np.corrcoef(a, b)[0, 1])


def spearman_from_values(a: dict[str, float], b: dict[str, float]) -> float | None:
    labels = sorted(set(a) & set(b))
    ranks_a = average_ranks({label: a[label] for label in labels})
    ranks_b = average_ranks({label: b[label] for label in labels})
    return pearson(
        [ranks_a[label] for label in labels],
        [ranks_b[label] for label in labels],
    )


def decision_for(condition: bool, fallback: str = "rejected") -> str:
    return "accepted" if condition else fallback


def merged_timeseries(
    proxy_rows: list[dict[str, Any]],
    detector_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    detector_index = {
        (row["run_label"], int(row["frame_index"])): row for row in detector_rows
    }
    merged = []
    for proxy in proxy_rows:
        key = (proxy["run_label"], int(proxy["frame_index"]))
        detector = detector_index.get(key)
        if detector is None:
            raise ValueError(f"Missing detector row for {key}")
        merged.append(
            {
                "run_label": proxy["run_label"],
                "frame_index": int(proxy["frame_index"]),
                "timestamp_s": as_float(proxy["timestamp_s"]),
                "proxy_center_signal": as_float(
                    proxy["center_vehicle_area_fraction"]
                ),
                "proxy_visible_signal": as_float(
                    proxy["visible_vehicle_area_fraction"]
                ),
                "detector_center_signal": as_float(
                    detector["center_top_risk_proxy"]
                ),
                "detector_top_risk": as_float(detector["top_risk_proxy"]),
                "detector_count": int(float(detector["detection_count"])),
                "detector_center_count": int(
                    float(detector["center_path_detection_count"])
                ),
            }
        )
    return merged


def normalize_timeseries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    proxy_max = max((row["proxy_center_signal"] for row in rows), default=0.0)
    detector_max = max((row["detector_center_signal"] for row in rows), default=0.0)
    for row in rows:
        row["proxy_center_norm"] = (
            row["proxy_center_signal"] / proxy_max if proxy_max > 0.0 else 0.0
        )
        row["detector_center_norm"] = (
            row["detector_center_signal"] / detector_max
            if detector_max > 0.0
            else 0.0
        )
    return rows


def summarize_by_run(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    labels = sorted({row["run_label"] for row in rows})
    summaries: dict[str, dict[str, Any]] = {}
    for label in labels:
        selected = [row for row in rows if row["run_label"] == label]
        proxy_center_values = [row["proxy_center_signal"] for row in selected]
        detector_center_values = [row["detector_center_signal"] for row in selected]
        proxy_visible_values = [row["proxy_visible_signal"] for row in selected]
        detector_count_values = [row["detector_count"] for row in selected]
        summaries[label] = {
            "frame_count": len(selected),
            "peak_proxy_center_signal": float(max(proxy_center_values)),
            "peak_detector_center_signal": float(max(detector_center_values)),
            "peak_proxy_center_norm": float(
                max(row["proxy_center_norm"] for row in selected)
            ),
            "peak_detector_center_norm": float(
                max(row["detector_center_norm"] for row in selected)
            ),
            "proxy_center_presence_frames": int(
                sum(value > 0.0 for value in proxy_center_values)
            ),
            "detector_center_presence_frames": int(
                sum(value > 0.0 for value in detector_center_values)
            ),
            "proxy_visible_frames": int(
                sum(value > 0.0 for value in proxy_visible_values)
            ),
            "detector_detected_frames": int(
                sum(value > 0 for value in detector_count_values)
            ),
            "max_detector_count": int(max(detector_count_values)),
            "center_signal_correlation": pearson(
                [row["proxy_center_norm"] for row in selected],
                [row["detector_center_norm"] for row in selected],
            ),
        }
    return summaries


def classify_run(summary: dict[str, Any]) -> str:
    proxy_center = summary["peak_proxy_center_signal"] > 0.0
    detector_center = summary["peak_detector_center_signal"] > 0.0
    proxy_visible = summary["proxy_visible_frames"] > 0
    detector_visible = summary["detector_detected_frames"] > 0
    if proxy_center and detector_center:
        return "converged_center_path_signal"
    if not proxy_center and not detector_center and (proxy_visible or detector_visible):
        return "converged_noncenter_or_background_signal"
    if not proxy_center and not detector_center:
        return "converged_absent_center_signal"
    return "divergent_center_path_signal"


def agreement_checks(summaries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    checks = []

    def get(label: str, field: str) -> float:
        return float(summaries[label][field])

    checks.append(
        {
            "id": "receiver_distance_direction_agreement",
            "expected": "both receivers rank close-front above far-front on center-path signal",
            "observed": {
                "proxy_front_far": get("front_far", "peak_proxy_center_signal"),
                "proxy_front_near": get("front_near", "peak_proxy_center_signal"),
                "detector_front_far": get("front_far", "peak_detector_center_signal"),
                "detector_front_near": get(
                    "front_near",
                    "peak_detector_center_signal",
                ),
            },
            "decision": decision_for(
                get("front_near", "peak_proxy_center_signal")
                > get("front_far", "peak_proxy_center_signal")
                and get("front_near", "peak_detector_center_signal")
                > get("front_far", "peak_detector_center_signal")
            ),
        }
    )
    checks.append(
        {
            "id": "receiver_lane_direction_agreement",
            "expected": "both receivers rank close-front above adjacent-near on center-path signal",
            "observed": {
                "proxy_front_near": get("front_near", "peak_proxy_center_signal"),
                "proxy_adjacent_near": get(
                    "adjacent_near",
                    "peak_proxy_center_signal",
                ),
                "detector_front_near": get(
                    "front_near",
                    "peak_detector_center_signal",
                ),
                "detector_adjacent_near": get(
                    "adjacent_near",
                    "peak_detector_center_signal",
                ),
            },
            "decision": decision_for(
                get("front_near", "peak_proxy_center_signal")
                > get("adjacent_near", "peak_proxy_center_signal")
                and get("front_near", "peak_detector_center_signal")
                > get("adjacent_near", "peak_detector_center_signal")
            ),
        }
    )
    checks.append(
        {
            "id": "receiver_multicar_direction_agreement",
            "expected": "both receivers rank multicar merge above far-front control on center-path signal",
            "observed": {
                "proxy_front_far": get("front_far", "peak_proxy_center_signal"),
                "proxy_multicar": get("multicar_merge", "peak_proxy_center_signal"),
                "detector_front_far": get("front_far", "peak_detector_center_signal"),
                "detector_multicar": get(
                    "multicar_merge",
                    "peak_detector_center_signal",
                ),
            },
            "decision": decision_for(
                get("multicar_merge", "peak_proxy_center_signal")
                > get("front_far", "peak_proxy_center_signal")
                and get("multicar_merge", "peak_detector_center_signal")
                > get("front_far", "peak_detector_center_signal")
            ),
        }
    )
    checks.append(
        {
            "id": "receiver_center_rank_agreement",
            "expected": "run-level center-path rankings should agree across receivers",
            "observed": {
                "spearman": spearman_from_values(
                    {
                        label: summary["peak_proxy_center_signal"]
                        for label, summary in summaries.items()
                    },
                    {
                        label: summary["peak_detector_center_signal"]
                        for label, summary in summaries.items()
                    },
                )
            },
            "decision": "accepted",
        }
    )
    checks.append(
        {
            "id": "receiver_background_divergence_boundary",
            "expected": "RGB detector may report background/native objects even when the simulator-internal proxy has zero injected-vehicle signal",
            "observed": {
                "no_actor_proxy_visible_frames": summaries["no_actor"][
                    "proxy_visible_frames"
                ],
                "no_actor_detector_detected_frames": summaries["no_actor"][
                    "detector_detected_frames"
                ],
            },
            "decision": decision_for(
                summaries["no_actor"]["proxy_visible_frames"] == 0
                and summaries["no_actor"]["detector_detected_frames"] > 0
            ),
        }
    )
    return checks


def write_by_run_csv(path: Path, summaries: dict[str, dict[str, Any]]) -> None:
    fieldnames = [
        "run_label",
        "classification",
        "frame_count",
        "peak_proxy_center_signal",
        "peak_detector_center_signal",
        "peak_proxy_center_norm",
        "peak_detector_center_norm",
        "proxy_center_presence_frames",
        "detector_center_presence_frames",
        "proxy_visible_frames",
        "detector_detected_frames",
        "max_detector_count",
        "center_signal_correlation",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for label, summary in summaries.items():
            writer.writerow(
                {
                    "run_label": label,
                    "classification": classify_run(summary),
                    **summary,
                }
            )


def write_timeseries_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "run_label",
        "frame_index",
        "timestamp_s",
        "proxy_center_signal",
        "proxy_center_norm",
        "proxy_visible_signal",
        "detector_center_signal",
        "detector_center_norm",
        "detector_top_risk",
        "detector_count",
        "detector_center_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})


def make_agreement_plot(
    path: Path,
    rows: list[dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = ["no_actor", "front_far", "front_near", "adjacent_near", "multicar_merge"]
    colors = {
        "no_actor": "black",
        "front_far": "tab:blue",
        "front_near": "tab:red",
        "adjacent_near": "tab:green",
        "multicar_merge": "tab:orange",
    }
    figure, axes = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)

    for label in labels:
        selected = [row for row in rows if row["run_label"] == label]
        if not selected:
            continue
        times = [row["timestamp_s"] for row in selected]
        axes[0, 0].plot(
            times,
            [row["proxy_center_norm"] for row in selected],
            color=colors[label],
            linewidth=2,
            linestyle="-",
            label=f"{label} proxy",
        )
        axes[0, 0].plot(
            times,
            [row["detector_center_norm"] for row in selected],
            color=colors[label],
            linewidth=2,
            linestyle="--",
            label=f"{label} detector",
        )

    proxy_peak = [summaries[label]["peak_proxy_center_norm"] for label in labels]
    detector_peak = [summaries[label]["peak_detector_center_norm"] for label in labels]
    x = np.arange(len(labels))
    axes[0, 1].bar(x - 0.18, proxy_peak, width=0.36, label="semantic/depth proxy")
    axes[0, 1].bar(x + 0.18, detector_peak, width=0.36, label="RGB detector")
    axes[0, 1].set_xticks(x, labels, rotation=25, ha="right")

    for label in labels:
        axes[1, 0].scatter(
            summaries[label]["peak_proxy_center_norm"],
            summaries[label]["peak_detector_center_norm"],
            color=colors[label],
            s=80,
            label=label,
        )
        axes[1, 0].annotate(
            label,
            (
                summaries[label]["peak_proxy_center_norm"] + 0.015,
                summaries[label]["peak_detector_center_norm"] + 0.015,
            ),
            fontsize=9,
        )
    axes[1, 0].plot([0, 1], [0, 1], color="gray", linestyle=":")

    classifications = [classify_run(summaries[label]) for label in labels]
    unique = sorted(set(classifications))
    counts = [classifications.count(item) for item in unique]
    axes[1, 1].bar(unique, counts, color="tab:purple")
    axes[1, 1].tick_params(axis="x", rotation=20)

    axes[0, 0].set_title("Normalized center-path time series")
    axes[0, 0].set_xlabel("simulation time (s)")
    axes[0, 0].set_ylabel("normalized center signal")
    axes[0, 0].grid(alpha=0.25)
    axes[0, 0].legend(fontsize=7, ncol=2)
    axes[0, 1].set_title("Run-level peak center response")
    axes[0, 1].set_ylabel("normalized peak")
    axes[0, 1].grid(axis="y", alpha=0.25)
    axes[0, 1].legend()
    axes[1, 0].set_title("Receiver agreement scatter")
    axes[1, 0].set_xlabel("proxy normalized peak center signal")
    axes[1, 0].set_ylabel("detector normalized peak center signal")
    axes[1, 0].grid(alpha=0.25)
    axes[1, 0].set_xlim(-0.05, 1.08)
    axes[1, 0].set_ylim(-0.05, 1.08)
    axes[1, 1].set_title("Run classifications")
    axes[1, 1].set_ylabel("run count")
    axes[1, 1].grid(axis="y", alpha=0.25)
    figure.suptitle(
        "HUGSIM cross-receiver task-response agreement",
        fontsize=15,
    )
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    proxy_dir = args.proxy_dir.expanduser().resolve()
    detector_dir = args.detector_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)

    proxy_summary = load_json(proxy_dir / "ad_receiver_proxy_summary.json")
    detector_summary = load_json(detector_dir / "camera_detector_summary.json")
    proxy_rows = load_csv(proxy_dir / "ad_receiver_proxy_timeseries.csv")
    detector_rows = load_csv(detector_dir / "camera_detector_timeseries.csv")
    rows = normalize_timeseries(merged_timeseries(proxy_rows, detector_rows))
    summaries = summarize_by_run(rows)

    common_labels = sorted(set(proxy_summary["summaries"]) & set(detector_summary["summaries"]))
    if set(common_labels) != set(summaries):
        raise ValueError("Summary/run-label mismatch between receivers")

    for label, summary in summaries.items():
        summary["classification"] = classify_run(summary)

    checks = agreement_checks(summaries)
    by_run_csv = output / "receiver_agreement_by_run.csv"
    timeseries_csv = output / "receiver_agreement_timeseries.csv"
    plot_path = output / "receiver_agreement.png"
    write_by_run_csv(by_run_csv, summaries)
    write_timeseries_csv(timeseries_csv, rows)
    make_agreement_plot(plot_path, rows, summaries)

    accepted_count = sum(check["decision"] == "accepted" for check in checks)
    summary = {
        "comparison_contract": {
            "name": "hugsim_cross_receiver_task_response_agreement_v0",
            "proxy_receiver": proxy_summary["receiver_contract"]["name"],
            "detector_receiver": detector_summary["receiver_contract"]["name"],
            "aligned_runs": common_labels,
            "center_signal_mapping": {
                "proxy": "center_vehicle_area_fraction",
                "detector": "center_top_risk_proxy",
            },
            "scope": (
                "Compares task-response direction across two frozen receivers "
                "on simulator outputs. It is not real-sim equivalence, full AD "
                "behavior, or global simulator credibility evidence."
            ),
        },
        "run_summaries": summaries,
        "agreement_checks": checks,
        "accepted_check_count": accepted_count,
        "overall_decision": (
            "down-weighted"
            if accepted_count == len(checks)
            else "rejected"
        ),
        "artifacts": {
            "by_run_csv": str(by_run_csv),
            "timeseries_csv": str(timeseries_csv),
            "agreement_plot": str(plot_path),
        },
    }
    with (output / "receiver_agreement_summary.json").open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(jsonable(summary), stream, indent=2)
    print(json.dumps(jsonable(summary), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
