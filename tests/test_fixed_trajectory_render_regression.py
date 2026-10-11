import json
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compare_fixed_trajectory_render_regression import image_metrics, load_run
from compare_fixed_trajectory_render_regression import (
    compare_runs,
    regression_succeeded,
    sha256,
)
from run_fixed_trajectory_render_regression import (
    CAMERAS,
    build_child_command,
    validate_rigid_transform,
)


class FixedTrajectoryRegressionTests(unittest.TestCase):
    def make_complete_run(
        self,
        parent,
        name,
        golden_root,
        *,
        metadata_contract="frozen",
        changed_key=None,
    ):
        root = Path(parent) / name
        root.mkdir()
        windows = [
            {"id": "straight", "frames": list(range(8))},
            {"id": "turn", "frames": list(range(8, 16))},
        ]
        config = {"experiment_id": "fixed-test", "windows": windows}
        (root / "config.json").write_text(json.dumps(config))
        (root / "status.json").write_text(json.dumps({"status": "complete"}))
        (root / "environment.json").write_text(
            json.dumps(
                {
                    "started_utc": f"time-{name}",
                    "hashes": {"metadata": metadata_contract},
                    "current_assets": {"scene": "same"},
                }
            )
        )
        (root / "golden_preflight.json").write_text(json.dumps({"qualified": True}))
        (root / "trajectory_preflight.json").write_text(
            json.dumps({"frames": list(range(16))})
        )
        processes, images = [], []
        for window in windows:
            for frame in window["frames"]:
                frame_root = root / "renders" / window["id"] / f"frame_{frame:05d}"
                frame_root.mkdir(parents=True)
                report = frame_root / "exact_pose_render.json"
                report.write_text(json.dumps({"frame": frame}))
                processes.append(
                    {
                        "window": window["id"],
                        "frame_index": frame,
                        "command": [
                            "/usr/bin/python3",
                            "/fixed/driver.py",
                            "--frame-index",
                            str(frame),
                            "--output",
                            str(frame_root),
                        ],
                        "cwd": str(ROOT),
                        "returncode": 0,
                        "timed_out": False,
                        "completed": True,
                        "failure": None,
                        "report": str(report.relative_to(root)),
                        "report_sha256": sha256(report),
                    }
                )
                for camera_index, camera in enumerate(CAMERAS):
                    golden = golden_root / window["id"] / f"{frame:05d}_{camera}.png"
                    golden.parent.mkdir(parents=True, exist_ok=True)
                    baseline = np.full(
                        (8, 8, 3), frame * 7 + camera_index, dtype=np.uint8
                    )
                    if not golden.exists():
                        self.assertTrue(cv2.imwrite(str(golden), baseline))
                    current = baseline.copy()
                    if changed_key == (window["id"], frame, camera):
                        current[0, 0, 0] += 1
                    image_path = frame_root / f"{camera}.png"
                    self.assertTrue(cv2.imwrite(str(image_path), current))
                    images.append(
                        {
                            "window": window["id"],
                            "frame_index": frame,
                            "camera": camera,
                            "path": str(image_path.relative_to(root)),
                            "sha256": sha256(image_path),
                            "golden_path": str(golden),
                            "golden_sha256": sha256(golden),
                        }
                    )
        manifest = {
            "experiment_id": "fixed-test",
            "process_count": 16,
            "completed_process_count": 16,
            "failed_process_count": 0,
            "expected_image_count": 96,
            "image_count": 96,
            "trajectory_output_varies": True,
            "processes": processes,
            "images": images,
        }
        (root / "render_manifest.json").write_text(json.dumps(manifest))
        return root

    def test_image_metrics_separate_exact_and_pixel_change(self):
        baseline = np.zeros((12, 16, 3), dtype=np.uint8)
        exact = image_metrics(baseline, baseline.copy())
        self.assertTrue(exact["pixel_exact"])
        self.assertEqual(exact["max_abs_uint8"], 0)
        self.assertTrue(exact["psnr_infinite"])
        changed = baseline.copy()
        changed[5, 7, 1] = 3
        result = image_metrics(baseline, changed)
        self.assertFalse(result["pixel_exact"])
        self.assertEqual(result["max_abs_uint8"], 3)
        self.assertGreater(result["mae_uint8"], 0)
        self.assertFalse(result["psnr_infinite"])
        self.assertEqual(result["changed_channel_count"], 1)
        self.assertEqual(result["changed_pixel_count"], 1)
        self.assertEqual(result["first_changed_yxc"], [5, 7, 1])
        self.assertEqual(result["changed_bbox_xyxy"], [7, 5, 7, 5])

    def test_child_command_freezes_absolute_paths_and_unique_output(self):
        command = build_child_command(
            "/usr/bin/python3",
            ROOT / "scripts/render_hugsim_exact_source_pose.py",
            "/home/yawei/HUGSIM",
            "/home/yawei/HUGSIM_assets/scenes/nuscenes/scene-0383",
            ROOT / "metadata.json",
            12,
            ROOT / "artifacts/test/frame_00012",
        )
        self.assertTrue(Path(command[0]).is_absolute())
        self.assertEqual(command[command.index("--frame-index") + 1], "12")
        self.assertTrue(Path(command[command.index("--output") + 1]).is_absolute())

    def test_rigid_transform_gate_rejects_scale(self):
        valid = np.eye(4)
        np.testing.assert_array_equal(validate_rigid_transform(valid, "valid"), valid)
        scaled = valid.copy()
        scaled[0, 0] = 2
        with self.assertRaisesRegex(ValueError, "orthonormal"):
            validate_rigid_transform(scaled, "scaled")

    def test_run_loader_rejects_incomplete_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "status.json").write_text(json.dumps({"status": "complete"}))
            (root / "render_manifest.json").write_text(
                json.dumps(
                    {
                        "failed_process_count": 1,
                        "image_count": 0,
                        "images": [],
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "incomplete render manifest"):
                load_run(root)

    def test_comparator_rejects_same_run_directory(self):
        with self.assertRaisesRegex(ValueError, "distinct run directories"):
            compare_runs("/tmp/same-run", "/tmp/same-run")

    def test_comparator_rejects_frozen_contract_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            golden = root / "golden"
            left = self.make_complete_run(root, "left", golden)
            right = self.make_complete_run(
                root, "right", golden, metadata_contract="changed"
            )
            with self.assertRaisesRegex(ValueError, "frozen run contracts differ"):
                compare_runs(left, right)

    def test_one_pixel_regression_produces_failure_exit_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            golden = root / "golden"
            left = self.make_complete_run(root, "left", golden)
            right = self.make_complete_run(
                root,
                "right",
                golden,
                changed_key=("turn", 15, "CAM_FRONT"),
            )
            result = compare_runs(left, right)
            self.assertFalse(result["all_current_repeat_checks_passed"])
            self.assertFalse(result["all_golden_regression_checks_passed"])
            self.assertEqual(0 if regression_succeeded(result) else 1, 1)

    def test_png_roundtrip_preserves_exact_pixels(self):
        image = np.arange(20 * 30 * 3, dtype=np.uint8).reshape(20, 30, 3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            self.assertTrue(cv2.imwrite(str(path), image))
            decoded = cv2.imread(str(path), cv2.IMREAD_COLOR)
            self.assertTrue(image_metrics(image, decoded)["pixel_exact"])


if __name__ == "__main__":
    unittest.main()
