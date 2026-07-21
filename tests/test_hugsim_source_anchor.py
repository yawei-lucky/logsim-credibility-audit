import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from audit_hugsim_source_anchor import audit_scene_anchor  # noqa: E402


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


def write_fixture(root: Path, *, with_images: bool, with_tokens: bool):
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


class HugsimSourceAnchorTest(unittest.TestCase):
    def test_missing_rgb_and_tokens_block_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(root, with_images=False, with_tokens=False)

            result = audit_scene_anchor(root)

            self.assertEqual(result["gate"]["status"], "blocked")
            self.assertEqual(
                result["source_observations"]["existing_real_rgb_count"], 0
            )
            self.assertEqual(
                result["metadata"]["reader_test_candidate_timestamp_count"], 1
            )
            candidate = result["metadata"]["first_reader_test_candidates"][0]
            self.assertEqual(candidate["frame_index"], 4)
            self.assertFalse(candidate["all_real_rgb_present"])

    def test_complete_source_pair_passes_availability_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(root, with_images=True, with_tokens=True)

            result = audit_scene_anchor(root)

            self.assertEqual(result["gate"]["status"], "ready")
            self.assertEqual(
                result["source_observations"]["existing_real_rgb_count"], 30
            )
            self.assertEqual(
                result["source_observations"]["valid_real_rgb_count"], 30
            )
            self.assertEqual(
                result["source_observations"]["provenance_fields"],
                ["sample_data_token"],
            )
            self.assertTrue(
                result["source_observations"]["source_identity_complete"]
            )
            self.assertTrue(result["metadata"]["timestamp_groups_complete"])

    def test_null_tokens_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(root, with_images=True, with_tokens=True)
            metadata_path = root / "meta_data.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["frames"][0]["sample_data_token"] = None
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            result = audit_scene_anchor(root)

            self.assertEqual(result["gate"]["status"], "blocked")
            self.assertEqual(
                result["source_observations"]["missing_source_identity_count"], 1
            )

    def test_corrupt_rgb_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(root, with_images=True, with_tokens=True)
            (root / "images" / "CAM_FRONT" / "00000.jpg").write_bytes(b"rgb")

            result = audit_scene_anchor(root)

            self.assertEqual(result["gate"]["status"], "blocked")
            self.assertEqual(
                result["source_observations"]["valid_real_rgb_count"], 29
            )

    def test_incomplete_timestamp_groups_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(root, with_images=True, with_tokens=True)
            metadata_path = root / "meta_data.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for index, frame in enumerate(metadata["frames"]):
                frame["timestamp"] = index * 0.01
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            result = audit_scene_anchor(root)

            self.assertEqual(result["gate"]["status"], "blocked")
            self.assertFalse(result["metadata"]["timestamp_groups_complete"])

    def test_reused_rgb_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(root, with_images=True, with_tokens=True)
            metadata_path = root / "meta_data.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for frame in metadata["frames"]:
                camera = Path(frame["rgb_path"]).parent.name
                frame["rgb_path"] = f"./images/{camera}/00000.jpg"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            result = audit_scene_anchor(root)

            self.assertEqual(result["gate"]["status"], "blocked")
            self.assertFalse(result["metadata"]["rgb_paths_unique"])
            self.assertFalse(
                result["metadata"]["frame_indices_strictly_increasing"]
            )

    def test_reused_sample_data_tokens_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(root, with_images=True, with_tokens=True)
            metadata_path = root / "meta_data.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for frame in metadata["frames"]:
                frame_index = Path(frame["rgb_path"]).stem
                frame["sample_data_token"] = f"sample-{frame_index}"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            result = audit_scene_anchor(root)

            self.assertEqual(result["gate"]["status"], "blocked")
            self.assertFalse(
                result["source_observations"]["sample_data_identity_complete"]
            )

    def test_grouped_sample_tokens_are_accepted_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(root, with_images=True, with_tokens=True)
            metadata_path = root / "meta_data.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for frame in metadata["frames"]:
                frame_index = Path(frame["rgb_path"]).stem
                frame.pop("sample_data_token")
                frame["sample_token"] = f"sample-{frame_index}"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            result = audit_scene_anchor(root)

            self.assertEqual(result["gate"]["status"], "ready")
            self.assertTrue(
                result["source_observations"]["sample_identity_complete"]
            )


if __name__ == "__main__":
    unittest.main()
