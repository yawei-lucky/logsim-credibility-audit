import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from fetch_hugsim_sample_anchor import (  # noqa: E402
    BytesRangeReader,
    ZipMember,
    extract_member,
    fetch_members,
    load_central_directory,
    safe_relative_member,
)


def build_zip() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data/scene-0383/meta_data.json", '{"frames": []}')
        archive.writestr(
            "data/scene-0383/images/CAM_FRONT/00004.jpg", b"jpeg payload"
        )
    return stream.getvalue()


class HugsimSampleAnchorFetchTest(unittest.TestCase):
    def test_reads_directory_and_validates_member(self):
        reader = BytesRangeReader(build_zip())
        members = load_central_directory(reader)

        self.assertEqual(
            set(members),
            {
                "data/scene-0383/meta_data.json",
                "data/scene-0383/images/CAM_FRONT/00004.jpg",
            },
        )
        self.assertEqual(
            extract_member(reader, members["data/scene-0383/meta_data.json"]),
            b'{"frames": []}',
        )

    def test_fetches_only_declared_members_and_refuses_overwrite(self):
        reader = BytesRangeReader(build_zip())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "anchor"
            manifest = fetch_members(
                reader,
                ["data/scene-0383/images/CAM_FRONT/00004.jpg"],
                output,
                strip_prefix="data/scene-0383",
                archive_url="https://example.invalid/data.zip",
                provider_sha256="provider-value",
            )

            self.assertEqual(
                (output / "images/CAM_FRONT/00004.jpg").read_bytes(),
                b"jpeg payload",
            )
            self.assertEqual(manifest["member_count"], 1)
            self.assertFalse(
                manifest["archive"][
                    "provider_declared_sha256_locally_verified"
                ]
            )
            with self.assertRaises(FileExistsError):
                fetch_members(
                    reader,
                    ["data/scene-0383/meta_data.json"],
                    output,
                    strip_prefix="data/scene-0383",
                )

    def test_crc_failure_is_rejected(self):
        reader = BytesRangeReader(build_zip())
        member = load_central_directory(reader)[
            "data/scene-0383/meta_data.json"
        ]
        corrupt = ZipMember(
            name=member.name,
            compression_method=member.compression_method,
            flags=member.flags,
            crc32=member.crc32 ^ 1,
            compressed_size=member.compressed_size,
            uncompressed_size=member.uncompressed_size,
            local_header_offset=member.local_header_offset,
        )
        with self.assertRaisesRegex(ValueError, "CRC mismatch"):
            extract_member(reader, corrupt)

    def test_unsafe_and_outside_prefix_paths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsafe"):
            safe_relative_member("../secret", "")
        with self.assertRaisesRegex(ValueError, "outside strip prefix"):
            safe_relative_member("other/file", "data/scene-0383")


if __name__ == "__main__":
    unittest.main()
