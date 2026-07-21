import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from audit_hugsim_ad_receiver_readiness import (  # noqa: E402
    build_readiness_audit,
    discover_scene_dirs,
    format_markdown,
)


CAMERAS = (
    "CAM_BACK",
    "CAM_BACK_LEFT",
    "CAM_BACK_RIGHT",
    "CAM_FRONT",
    "CAM_FRONT_LEFT",
    "CAM_FRONT_RIGHT",
)


def identity(size):
    return [
        [1.0 if row == column else 0.0 for column in range(size)]
        for row in range(size)
    ]


def write_scene(root: Path, scene_name: str, *, with_images: bool, with_tokens: bool):
    scene = root / scene_name
    scene.mkdir(parents=True)
    frames = []
    for frame_index in range(5):
        for camera in CAMERAS:
            relative = f"./images/{camera}/{frame_index:05d}.jpg"
            frame = {
                "rgb_path": relative,
                "timestamp": frame_index * 0.1,
                "camtoworld": identity(4),
                "intrinsics": identity(3),
                "width": 8,
                "height": 6,
                "dynamics": {},
            }
            if with_tokens:
                frame["sample_data_token"] = f"{scene_name}-{frame_index}-{camera}"
            frames.append(frame)
            if with_images:
                path = scene / relative.removeprefix("./")
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (8, 6), color=(frame_index, 0, 0)).save(path)
    (scene / "meta_data.json").write_text(
        json.dumps({"frames": frames, "verts": {}}), encoding="utf-8"
    )
    return scene


class HugsimAdReceiverReadinessTest(unittest.TestCase):
    def test_discover_scene_dirs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scene = write_scene(root, "scene-0001", with_images=False, with_tokens=False)

            self.assertEqual(discover_scene_dirs(root), [scene.resolve()])
            self.assertEqual(discover_scene_dirs(scene), [scene.resolve()])

    def test_blocked_when_all_source_anchors_are_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_scene(root, "scene-0001", with_images=False, with_tokens=False)

            audit = build_readiness_audit(root)
            gate = audit["ad_receiver_real_sim_comparison_gate"]

            self.assertEqual(gate["status"], "blocked")
            self.assertEqual(audit["summary"]["local_scene_count"], 1)
            self.assertEqual(audit["summary"]["source_anchor_ready_scene_count"], 0)
            self.assertEqual(audit["summary"]["total_existing_real_rgb_count"], 0)
            self.assertEqual(audit["summary"]["reader_test_candidate_timestamp_count"], 1)
            self.assertIn("availability-gap diagnosis", gate["permitted_claim"])

    def test_ready_anchor_still_requires_exact_render_and_receiver_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_scene(root, "scene-0001", with_images=True, with_tokens=True)

            audit = build_readiness_audit(root)
            gate = audit["ad_receiver_real_sim_comparison_gate"]

            self.assertEqual(gate["status"], "pending_exact_matched_pose_render")
            self.assertEqual(audit["summary"]["source_anchor_ready_scene_count"], 1)
            self.assertEqual(audit["summary"]["total_valid_real_rgb_count"], 30)
            self.assertIn("receiver equivalence is not tested", gate["permitted_claim"])

    def test_markdown_reports_no_new_rollout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_scene(root, "scene-0001", with_images=False, with_tokens=False)
            audit = build_readiness_audit(root)

            markdown = format_markdown(audit)

            self.assertIn("did not generate a new HUGSIM scenario or rollout", markdown)
            self.assertIn("| scene-0001 | `blocked` | 0/30 | no | 1 |", markdown)


if __name__ == "__main__":
    unittest.main()
