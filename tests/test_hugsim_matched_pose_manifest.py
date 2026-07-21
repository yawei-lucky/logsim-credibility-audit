import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_hugsim_matched_pose_manifest import (  # noqa: E402
    build_manifest,
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


def write_scene(root: Path, *, with_images: bool, with_tokens: bool):
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
                frame["sample_data_token"] = f"{frame_index}-{camera}"
            frames.append(frame)
            if with_images:
                path = root / relative.removeprefix("./")
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (8, 6), color=(frame_index, 0, 0)).save(path)
    (root / "meta_data.json").write_text(
        json.dumps({"frames": frames, "verts": {}}), encoding="utf-8"
    )


class HugsimMatchedPoseManifestTest(unittest.TestCase):
    def test_missing_source_anchor_blocks_pairing_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_scene(root, with_images=False, with_tokens=False)

            manifest = build_manifest(root)
            gate = manifest["pairing_integrity_gate"]

            self.assertEqual(gate["status"], "blocked_source_anchor")
            self.assertFalse(gate["real_observation_ready"])
            self.assertFalse(gate["source_identity_ready_for_selected_frame"])
            self.assertFalse(gate["receiver_equivalence_tested"])
            self.assertEqual(manifest["selected_frame_index"], 4)
            self.assertTrue(manifest["selected_from_reader_test_candidate"])
            self.assertEqual(len(manifest["cameras"]), 6)
            self.assertTrue(all(not camera["real_rgb_exists"] for camera in manifest["cameras"]))

    def test_ready_source_anchor_waits_for_exact_sim_render(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_scene(root, with_images=True, with_tokens=True)

            manifest = build_manifest(root)
            gate = manifest["pairing_integrity_gate"]

            self.assertEqual(gate["status"], "ready_for_exact_matched_pose_render")
            self.assertTrue(gate["real_observation_ready"])
            self.assertTrue(gate["source_identity_ready_for_selected_frame"])
            self.assertFalse(gate["exact_sim_render_ready"])
            self.assertFalse(gate["exact_sim_render_provenance_verified"])
            self.assertFalse(gate["pairing_integrity_passed"])
            self.assertFalse(gate["receiver_equivalence_tested"])
            self.assertTrue(all(camera["real_rgb_sha256"] for camera in manifest["cameras"]))
            self.assertEqual(
                manifest["receiver_input_contract"]["contract_id"],
                "camera_only_rgb_single_frame_v0",
            )
            self.assertFalse(
                manifest["receiver_input_contract"]["temporal_claims_allowed"]
            )

    def test_existing_exact_render_files_become_pairing_candidate_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sim_root = root / "sim_exact"
            write_scene(root, with_images=True, with_tokens=True)
            for camera in CAMERAS:
                path = sim_root / "00004" / f"{camera}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (8, 6), color=(0, 4, 0)).save(path)

            manifest = build_manifest(root, sim_render_root=sim_root)
            gate = manifest["pairing_integrity_gate"]

            self.assertEqual(gate["status"], "pairing_integrity_candidate")
            self.assertTrue(gate["real_observation_ready"])
            self.assertTrue(gate["exact_sim_render_ready"])
            self.assertFalse(gate["exact_sim_render_provenance_verified"])
            self.assertFalse(gate["pairing_integrity_passed"])
            self.assertFalse(gate["receiver_equivalence_tested"])

    def test_markdown_states_no_new_rollout_or_render(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_scene(root, with_images=False, with_tokens=False)

            markdown = format_markdown(build_manifest(root))

            self.assertIn("did not generate a new HUGSIM scenario", markdown)
            self.assertIn("Pairing integrity passed: `False`", markdown)
            self.assertIn("Receiver equivalence tested: `False`", markdown)
            self.assertIn("| CAM_FRONT | no | no | no |", markdown)
            self.assertIn("camera_only_rgb_single_frame_v0", markdown)


if __name__ == "__main__":
    unittest.main()
