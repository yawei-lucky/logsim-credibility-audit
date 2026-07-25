#!/usr/bin/env python3
"""Compare fully warmed matched real-HUGSIM SparseDrive windows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from statistics import fmean
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window",
        action="append",
        required=True,
        metavar="LABEL=AUDIT_JSON",
        help="Matched factual audit to compare; repeat for each window.",
    )
    parser.add_argument("--preregistration", type=Path, required=True)
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


def parse_window_spec(spec: str) -> tuple[str, Path]:
    label, separator, raw_path = spec.partition("=")
    if not separator or not label.strip() or not raw_path.strip():
        raise ValueError(f"expected LABEL=AUDIT_JSON, got {spec!r}")
    return label.strip(), Path(raw_path).expanduser().resolve()


def receiver_identity(audit: dict[str, Any]) -> dict[str, str]:
    report_path = Path(audit["inputs"]["real_report"])
    report = load_json(report_path)
    return {
        "checkpoint_sha256": report["model"]["checkpoint_sha256"],
        "config_sha256": report["model"]["config_sha256"],
        "adapter_sha256": report["adapter"]["sha256"],
    }


def summarize_window(
    label: str,
    audit_path: Path,
    audit: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not all(bool(value) for value in audit["held_fixed_gate"].values()):
        raise ValueError(f"{label}: within-window held-fixed gate did not pass")
    rows = [
        row
        for row in audit["plan_domain_rows"]
        if row["fully_warmed_four_frame_history"]
    ]
    if not rows:
        raise ValueError(f"{label}: no fully warmed rows")

    pixel_metrics = audit["pixel_metrics_by_frame"]
    flattened = []
    for ordinal, row in enumerate(rows, start=1):
        frame = int(row["source_frame_index"])
        pixel = pixel_metrics[str(frame)]
        flattened.append(
            {
                "window": label,
                "warmed_ordinal": ordinal,
                "source_frame_index": frame,
                "timestamp_s": float(row["timestamp_s"]),
                "domain_ade_m": float(row["plan_domain_ade_m"]),
                "domain_fde_m": float(row["plan_domain_fde_m"]),
                "sim_minus_real_final_right_m": float(
                    row["final_right_delta_sim_minus_real_m"]
                ),
                "sim_minus_real_final_forward_m": float(
                    row["final_forward_delta_sim_minus_real_m"]
                ),
                "real_mode": int(row["real_selected_mode"]),
                "sim_mode": int(row["sim_selected_mode"]),
                "mode_equal": bool(row["mode_equal"]),
                "real_reference_ade_m": float(
                    row["real_reference_error"]["ade_m"]
                ),
                "sim_reference_ade_m": float(
                    row["sim_reference_error"]["ade_m"]
                ),
                "real_reference_fde_m": float(
                    row["real_reference_error"]["fde_m"]
                ),
                "sim_reference_fde_m": float(
                    row["sim_reference_error"]["fde_m"]
                ),
                "pixel_ssim": float(pixel["ssim"]),
                "pixel_psnr_db": float(pixel["psnr_db"]),
                "pixel_mae": float(pixel["mae"]),
            }
        )

    def values(key: str) -> list[float]:
        return [float(row[key]) for row in flattened]

    forward = values("sim_minus_real_final_forward_m")
    right = values("sim_minus_real_final_right_m")
    real_reference_ade = values("real_reference_ade_m")
    sim_reference_ade = values("sim_reference_ade_m")
    real_reference_fde = values("real_reference_fde_m")
    sim_reference_fde = values("sim_reference_fde_m")
    summary = {
        "label": label,
        "audit": str(audit_path),
        "audit_sha256": sha256_file(audit_path),
        "receiver_identity": receiver_identity(audit),
        "fully_warmed_frames": [
            row["source_frame_index"] for row in flattened
        ],
        "fully_warmed_count": len(flattened),
        "repeat_envelope_m": float(audit["summary"]["repeat_envelope_m"]),
        "domain_ade_m": {
            "mean": fmean(values("domain_ade_m")),
            "min": min(values("domain_ade_m")),
            "max": max(values("domain_ade_m")),
        },
        "domain_fde_m": {
            "mean": fmean(values("domain_fde_m")),
            "min": min(values("domain_fde_m")),
            "max": max(values("domain_fde_m")),
        },
        "final_forward_delta_sim_minus_real_m": {
            "mean": fmean(forward),
            "min": min(forward),
            "max": max(forward),
            "positive_count": sum(value > 0.0 for value in forward),
            "negative_count": sum(value < 0.0 for value in forward),
        },
        "final_right_delta_sim_minus_real_m": {
            "mean": fmean(right),
            "min": min(right),
            "max": max(right),
            "positive_count": sum(value > 0.0 for value in right),
            "negative_count": sum(value < 0.0 for value in right),
        },
        "mode_equal_count": sum(row["mode_equal"] for row in flattened),
        "all_modes_equal": all(row["mode_equal"] for row in flattened),
        "reference_diagnostic": {
            "real_plan_ade_m_mean": fmean(real_reference_ade),
            "sim_plan_ade_m_mean": fmean(sim_reference_ade),
            "sim_minus_real_ade_m_mean": (
                fmean(sim_reference_ade) - fmean(real_reference_ade)
            ),
            "real_plan_fde_m_mean": fmean(real_reference_fde),
            "sim_plan_fde_m_mean": fmean(sim_reference_fde),
            "sim_minus_real_fde_m_mean": (
                fmean(sim_reference_fde) - fmean(real_reference_fde)
            ),
            "boundary": (
                "The recorded camera-rig path is a reality-derived diagnostic, "
                "not the unique correct plan or a SparseDrive correctness score."
            ),
        },
        "pixel_descriptive": {
            "warmed_ssim_mean": fmean(values("pixel_ssim")),
            "warmed_psnr_db_mean": fmean(values("pixel_psnr_db")),
            "warmed_mae_mean": fmean(values("pixel_mae")),
            "boundary": "Pixel metrics are not an AD-task equivalence test.",
        },
    }
    return summary, flattened


def compare_windows(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    if len(summaries) < 2:
        raise ValueError("at least two windows are required")
    reference = summaries[0]
    comparisons = []
    for candidate in summaries[1:]:
        comparisons.append(
            {
                "reference_window": reference["label"],
                "candidate_window": candidate["label"],
                "mean_domain_ade_ratio": (
                    candidate["domain_ade_m"]["mean"]
                    / reference["domain_ade_m"]["mean"]
                ),
                "mean_domain_fde_ratio": (
                    candidate["domain_fde_m"]["mean"]
                    / reference["domain_fde_m"]["mean"]
                ),
                "mean_forward_delta_change_m": (
                    candidate[
                        "final_forward_delta_sim_minus_real_m"
                    ]["mean"]
                    - reference[
                        "final_forward_delta_sim_minus_real_m"
                    ]["mean"]
                ),
                "mean_right_delta_change_m": (
                    candidate["final_right_delta_sim_minus_real_m"]["mean"]
                    - reference["final_right_delta_sim_minus_real_m"]["mean"]
                ),
                "reference_fde_diagnostic_change_m": (
                    candidate["reference_diagnostic"][
                        "sim_minus_real_fde_m_mean"
                    ]
                    - reference["reference_diagnostic"][
                        "sim_minus_real_fde_m_mean"
                    ]
                ),
            }
        )
    return {
        "relative_to_first_window": comparisons,
        "pooled_observed_only": {
            "maximum_domain_fde_m": max(
                item["domain_fde_m"]["max"] for item in summaries
            ),
            "maximum_abs_final_forward_delta_m": max(
                max(
                    abs(item["final_forward_delta_sim_minus_real_m"]["min"]),
                    abs(item["final_forward_delta_sim_minus_real_m"]["max"]),
                )
                for item in summaries
            ),
            "maximum_abs_final_right_delta_m": max(
                max(
                    abs(item["final_right_delta_sim_minus_real_m"]["min"]),
                    abs(item["final_right_delta_sim_minus_real_m"]["max"]),
                )
                for item in summaries
            ),
            "boundary": (
                "These are empirical maxima from two windows in one "
                "reconstruction, not acceptance thresholds."
            ),
        },
    }


def save_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_visualization(rows: list[dict[str, Any]], output: Path) -> Path:
    import matplotlib.pyplot as plt

    labels = list(dict.fromkeys(row["window"] for row in rows))
    colors = dict(zip(labels, ("#1f77b4", "#d62728", "#2ca02c"), strict=False))
    figure, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)

    for label in labels:
        selected = [row for row in rows if row["window"] == label]
        ordinal = [row["warmed_ordinal"] for row in selected]
        axes[0, 0].plot(
            ordinal,
            [row["domain_ade_m"] for row in selected],
            marker="o",
            color=colors[label],
            label=f"{label}: ADE",
        )
        axes[0, 0].plot(
            ordinal,
            [row["domain_fde_m"] for row in selected],
            marker="s",
            linestyle="--",
            color=colors[label],
            label=f"{label}: FDE",
        )
        axes[0, 1].scatter(
            [row["sim_minus_real_final_right_m"] for row in selected],
            [row["sim_minus_real_final_forward_m"] for row in selected],
            s=65,
            color=colors[label],
            label=label,
        )
        for row in selected:
            axes[0, 1].annotate(
                str(row["source_frame_index"]),
                (
                    row["sim_minus_real_final_right_m"],
                    row["sim_minus_real_final_forward_m"],
                ),
                fontsize=8,
                xytext=(4, 4),
                textcoords="offset points",
            )
        axes[1, 0].plot(
            ordinal,
            [row["real_reference_fde_m"] for row in selected],
            marker="o",
            color=colors[label],
            label=f"{label}: real RGB",
        )
        axes[1, 0].plot(
            ordinal,
            [row["sim_reference_fde_m"] for row in selected],
            marker="s",
            linestyle="--",
            color=colors[label],
            label=f"{label}: HUGSIM RGB",
        )
        axes[1, 1].scatter(
            [row["pixel_ssim"] for row in selected],
            [row["domain_fde_m"] for row in selected],
            s=65,
            color=colors[label],
            label=label,
        )

    axes[0, 0].set_title("Matched AD-response domain difference")
    axes[0, 0].set_xlabel("fully warmed sample within window")
    axes[0, 0].set_ylabel("plan difference (m)")
    axes[0, 0].legend(fontsize=8)
    axes[0, 0].grid(alpha=0.3)

    axes[0, 1].axhline(0.0, color="black", linewidth=0.8)
    axes[0, 1].axvline(0.0, color="black", linewidth=0.8)
    axes[0, 1].set_title("Signed 3 s endpoint shift: HUGSIM − real")
    axes[0, 1].set_xlabel("right (+) / left (−), m")
    axes[0, 1].set_ylabel("forward (+) / shorter (−), m")
    axes[0, 1].legend(fontsize=8)
    axes[0, 1].grid(alpha=0.3)

    axes[1, 0].set_title("Plan vs recorded camera-rig path (diagnostic)")
    axes[1, 0].set_xlabel("fully warmed sample within window")
    axes[1, 0].set_ylabel("3 s endpoint error (m)")
    axes[1, 0].legend(fontsize=8)
    axes[1, 0].grid(alpha=0.3)

    axes[1, 1].set_title("Pixel similarity does not set task equivalence")
    axes[1, 1].set_xlabel("six-camera mean SSIM")
    axes[1, 1].set_ylabel("plan endpoint difference (m)")
    axes[1, 1].legend(fontsize=8)
    axes[1, 1].grid(alpha=0.3)

    figure.suptitle(
        "Two matched real–HUGSIM windows, one scene\n"
        "Descriptive domain variation; no equivalence threshold",
        fontsize=15,
    )
    path = output / "sparsedrive_real_sim_window_comparison.png"
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def main() -> int:
    args = parse_args()
    preregistration = args.preregistration.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not preregistration.is_file():
        raise FileNotFoundError(preregistration)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")

    specs = [parse_window_spec(spec) for spec in args.window]
    labels = [label for label, _ in specs]
    if len(set(labels)) != len(labels):
        raise ValueError("window labels must be unique")
    for _, path in specs:
        if not path.is_file():
            raise FileNotFoundError(path)

    summaries = []
    rows = []
    for label, path in specs:
        summary, flattened = summarize_window(label, path, load_json(path))
        summaries.append(summary)
        rows.extend(flattened)
    identities = {
        json.dumps(item["receiver_identity"], sort_keys=True)
        for item in summaries
    }
    if len(identities) != 1:
        raise ValueError("receiver checkpoint, config or adapter differs across windows")

    output.mkdir(parents=True)
    csv_path = output / "sparsedrive_real_sim_warmed_rows.csv"
    save_csv(rows, csv_path)
    visual_path = save_visualization(rows, output)
    result = {
        "audit_id": "sparsedrive_real_sim_cross_window_001",
        "date": date.today().isoformat(),
        "preregistration": {
            "path": str(preregistration),
            "sha256": sha256_file(preregistration),
        },
        "windows": summaries,
        "cross_window": compare_windows(summaries),
        "evidence_decision": {
            "overall": "down-weighted",
            "accepted": [
                "both matched windows produced measurable fully warmed SparseDrive response differences beyond their local repeat envelopes",
                "the turning-window mean domain ADE and FDE were descriptively larger than in the prior window under the same receiver identity",
            ],
            "down-weighted": [
                "only two short windows from one source scene and one receiver were observed",
                "the recorded camera-rig path is not the unique correct plan and no externally qualified equivalence boundary exists",
            ],
            "rejected": [
                "the first-window factual domain maximum is a general acceptance threshold",
                "a HUGSIM-input plan closer to the recorded path proves HUGSIM is more realistic or SparseDrive more correct",
                "these two windows establish HUGSIM, SparseDrive or AD safety",
            ],
        },
        "artifacts": {
            "warmed_rows_csv": str(csv_path),
            "warmed_rows_csv_sha256": sha256_file(csv_path),
            "visualization": str(visual_path),
            "visualization_sha256": sha256_file(visual_path),
        },
    }
    result_path = output / "sparsedrive_real_sim_cross_window_audit.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
