import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_sparsedrive_real_sim_windows import (  # noqa: E402
    compare_windows,
    parse_window_spec,
    summarize_window,
)


def audit_fixture(report_path: Path, domain_fde: float) -> dict:
    rows = []
    pixels = {}
    for index in range(5):
        frame = 30 + index * 6
        rows.append(
            {
                "source_frame_index": frame,
                "timestamp_s": 2.5 + index * 0.5,
                "fully_warmed_four_frame_history": True,
                "plan_domain_ade_m": domain_fde / 2.0,
                "plan_domain_fde_m": domain_fde,
                "final_right_delta_sim_minus_real_m": -domain_fde / 4.0,
                "final_forward_delta_sim_minus_real_m": domain_fde,
                "real_selected_mode": 2,
                "sim_selected_mode": 2,
                "mode_equal": True,
                "real_reference_error": {
                    "ade_m": 1.0,
                    "fde_m": 2.0,
                },
                "sim_reference_error": {
                    "ade_m": 0.8,
                    "fde_m": 1.5,
                },
            }
        )
        pixels[str(frame)] = {
            "ssim": 0.4,
            "psnr_db": 16.0,
            "mae": 0.1,
        }
    return {
        "inputs": {"real_report": str(report_path)},
        "held_fixed_gate": {
            "checkpoint_equal": True,
            "config_equal": True,
            "adapter_equal": True,
            "state_equal": True,
        },
        "plan_domain_rows": rows,
        "pixel_metrics_by_frame": pixels,
        "summary": {"repeat_envelope_m": 1e-5},
    }


class SparseDriveRealSimWindowsTest(unittest.TestCase):
    def test_parse_window_spec(self):
        label, path = parse_window_spec("turn=/tmp/audit.json")
        self.assertEqual(label, "turn")
        self.assertEqual(path, Path("/tmp/audit.json"))
        with self.assertRaises(ValueError):
            parse_window_spec("/tmp/audit.json")

    def test_summarizes_only_fully_warmed_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "model": {
                            "checkpoint_sha256": "checkpoint",
                            "config_sha256": "config",
                        },
                        "adapter": {"sha256": "adapter"},
                    }
                ),
                encoding="utf-8",
            )
            audit = audit_fixture(report_path, 0.8)
            audit_path = root / "audit.json"
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            summary, rows = summarize_window(
                "turn",
                audit_path,
                audit,
            )
            self.assertEqual(summary["fully_warmed_count"], 5)
            self.assertAlmostEqual(summary["domain_fde_m"]["mean"], 0.8)
            self.assertAlmostEqual(
                summary["reference_diagnostic"]["sim_minus_real_fde_m_mean"],
                -0.5,
            )
            self.assertEqual(len(rows), 5)

    def test_cross_window_ratio_is_descriptive(self):
        base = {
            "label": "base",
            "domain_ade_m": {"mean": 0.2},
            "domain_fde_m": {"mean": 0.4, "max": 0.6},
            "final_forward_delta_sim_minus_real_m": {
                "mean": -0.1,
                "min": -0.6,
                "max": 0.3,
            },
            "final_right_delta_sim_minus_real_m": {
                "mean": 0.0,
                "min": -0.1,
                "max": 0.1,
            },
            "reference_diagnostic": {"sim_minus_real_fde_m_mean": 0.1},
        }
        turn = {
            "label": "turn",
            "domain_ade_m": {"mean": 0.4},
            "domain_fde_m": {"mean": 0.8, "max": 1.0},
            "final_forward_delta_sim_minus_real_m": {
                "mean": 0.7,
                "min": 0.4,
                "max": 0.9,
            },
            "final_right_delta_sim_minus_real_m": {
                "mean": -0.3,
                "min": -0.5,
                "max": -0.1,
            },
            "reference_diagnostic": {"sim_minus_real_fde_m_mean": -0.7},
        }
        comparison = compare_windows([base, turn])
        relative = comparison["relative_to_first_window"][0]
        self.assertAlmostEqual(relative["mean_domain_ade_ratio"], 2.0)
        self.assertAlmostEqual(relative["mean_domain_fde_ratio"], 2.0)
        self.assertIn(
            "not acceptance thresholds",
            comparison["pooled_observed_only"]["boundary"],
        )


if __name__ == "__main__":
    unittest.main()
