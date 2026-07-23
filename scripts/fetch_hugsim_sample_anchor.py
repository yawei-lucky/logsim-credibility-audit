#!/usr/bin/env python3
"""Fetch selected files from the official HUGSIM sample ZIP with HTTP ranges.

The full sample archive is about 2.38 GB.  A matched-pose audit only needs the
metadata and a small, declared set of camera images, so this tool reads the ZIP
central directory and selected members without downloading the whole archive.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import os
import shutil
import struct
import tempfile
import urllib.request
import zlib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Protocol


EOCD_SIGNATURE = b"PK\x05\x06"
CENTRAL_SIGNATURE = b"PK\x01\x02"
LOCAL_SIGNATURE = b"PK\x03\x04"


class RangeReader(Protocol):
    size: int

    def read_range(self, start: int, end: int) -> bytes:
        """Read the inclusive byte range [start, end]."""


class HttpRangeReader:
    def __init__(self, url: str, timeout_s: int = 60):
        self.url = url
        self.timeout_s = timeout_s
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            size = response.headers.get("Content-Length")
            if size is None:
                raise RuntimeError("remote server did not provide Content-Length")
            self.size = int(size)
            self.final_url = response.geturl()
            self.etag = response.headers.get("ETag")

    def read_range(self, start: int, end: int) -> bytes:
        if start < 0 or end < start or end >= self.size:
            raise ValueError(f"invalid byte range {start}-{end} for size {self.size}")
        request = urllib.request.Request(
            self.url, headers={"Range": f"bytes={start}-{end}"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            if response.status != 206:
                raise RuntimeError(
                    f"server ignored range request {start}-{end}: "
                    f"HTTP {response.status}"
                )
            content_range = response.headers.get("Content-Range")
            expected = f"bytes {start}-{end}/{self.size}"
            if content_range != expected:
                raise RuntimeError(
                    f"unexpected Content-Range {content_range!r}, expected {expected!r}"
                )
            payload = response.read()
        expected_size = end - start + 1
        if len(payload) != expected_size:
            raise RuntimeError(
                f"short range read: got {len(payload)}, expected {expected_size}"
            )
        return payload


class BytesRangeReader:
    """In-memory reader used by unit tests."""

    def __init__(self, payload: bytes):
        self.payload = payload
        self.size = len(payload)

    def read_range(self, start: int, end: int) -> bytes:
        if start < 0 or end < start or end >= self.size:
            raise ValueError(f"invalid byte range {start}-{end} for size {self.size}")
        return self.payload[start : end + 1]


@dataclass(frozen=True)
class ZipMember:
    name: str
    compression_method: int
    flags: int
    crc32: int
    compressed_size: int
    uncompressed_size: int
    local_header_offset: int


def load_central_directory(
    reader: RangeReader, tail_bytes: int = 1024 * 1024
) -> dict[str, ZipMember]:
    tail_size = min(reader.size, tail_bytes)
    tail_start = reader.size - tail_size
    tail = reader.read_range(tail_start, reader.size - 1)
    eocd_offset = tail.rfind(EOCD_SIGNATURE)
    if eocd_offset < 0:
        raise ValueError("ZIP end-of-central-directory record not found in tail")
    if eocd_offset + 22 > len(tail):
        raise ValueError("truncated ZIP end-of-central-directory record")

    (
        _,
        disk_number,
        central_disk,
        entries_on_disk,
        total_entries,
        central_size,
        central_offset,
        comment_length,
    ) = struct.unpack_from("<4s4H2LH", tail, eocd_offset)
    if disk_number != 0 or central_disk != 0 or entries_on_disk != total_entries:
        raise ValueError("multi-disk ZIP archives are not supported")
    if total_entries == 0xFFFF or central_size == 0xFFFFFFFF:
        raise ValueError("ZIP64 archives are not supported")
    if eocd_offset + 22 + comment_length != len(tail):
        raise ValueError("unexpected bytes after ZIP end-of-central-directory record")

    central_start_in_tail = central_offset - tail_start
    central_end_in_tail = central_start_in_tail + central_size
    if central_start_in_tail < 0 or central_end_in_tail > eocd_offset:
        raise ValueError(
            "ZIP central directory is not fully available; increase --tail-bytes"
        )

    members: dict[str, ZipMember] = {}
    position = central_start_in_tail
    for _ in range(total_entries):
        if tail[position : position + 4] != CENTRAL_SIGNATURE:
            raise ValueError("invalid ZIP central-directory signature")
        header = struct.unpack_from("<4s6H3L5H2L", tail, position)
        filename_length = header[10]
        extra_length = header[11]
        comment_length = header[12]
        record_end = position + 46 + filename_length + extra_length + comment_length
        if record_end > central_end_in_tail:
            raise ValueError("truncated ZIP central-directory member")
        name = tail[position + 46 : position + 46 + filename_length].decode(
            "utf-8"
        )
        if name in members:
            raise ValueError(f"duplicate ZIP member: {name}")
        members[name] = ZipMember(
            name=name,
            compression_method=header[4],
            flags=header[3],
            crc32=header[7],
            compressed_size=header[8],
            uncompressed_size=header[9],
            local_header_offset=header[16],
        )
        position = record_end
    if position != central_end_in_tail:
        raise ValueError("ZIP central-directory size does not match parsed entries")
    return members


def extract_member(reader: RangeReader, member: ZipMember) -> bytes:
    if member.flags & 0x1:
        raise ValueError(f"encrypted ZIP member is unsupported: {member.name}")
    if member.compression_method not in (0, 8):
        raise ValueError(
            f"unsupported compression method {member.compression_method}: "
            f"{member.name}"
        )

    local = reader.read_range(
        member.local_header_offset, member.local_header_offset + 29
    )
    header = struct.unpack("<4s5H3L2H", local)
    if header[0] != LOCAL_SIGNATURE:
        raise ValueError(f"invalid local ZIP header: {member.name}")
    if header[3] != member.compression_method:
        raise ValueError(f"compression mismatch in local header: {member.name}")
    filename_length = header[9]
    extra_length = header[10]
    data_start = member.local_header_offset + 30 + filename_length + extra_length
    data_end = data_start + member.compressed_size - 1
    compressed = (
        reader.read_range(data_start, data_end) if member.compressed_size else b""
    )

    if member.compression_method == 0:
        payload = compressed
    else:
        payload = zlib.decompress(compressed, -zlib.MAX_WBITS)
    if len(payload) != member.uncompressed_size:
        raise ValueError(
            f"uncompressed size mismatch for {member.name}: "
            f"{len(payload)} != {member.uncompressed_size}"
        )
    crc32 = binascii.crc32(payload) & 0xFFFFFFFF
    if crc32 != member.crc32:
        raise ValueError(
            f"CRC mismatch for {member.name}: {crc32:08x} != {member.crc32:08x}"
        )
    return payload


def safe_relative_member(name: str, strip_prefix: str) -> Path:
    member = PurePosixPath(name)
    if member.is_absolute() or ".." in member.parts:
        raise ValueError(f"unsafe ZIP member path: {name}")
    prefix = PurePosixPath(strip_prefix) if strip_prefix else PurePosixPath()
    if prefix.parts:
        try:
            member = member.relative_to(prefix)
        except ValueError as error:
            raise ValueError(
                f"ZIP member {name!r} is outside strip prefix {strip_prefix!r}"
            ) from error
    if not member.parts or member.name == "":
        raise ValueError(f"ZIP member resolves to an empty output path: {name}")
    return Path(*member.parts)


def fetch_members(
    reader: RangeReader,
    member_names: list[str],
    output: Path,
    strip_prefix: str = "",
    archive_url: str | None = None,
    provider_sha256: str | None = None,
    archive_etag: str | None = None,
    tail_bytes: int = 1024 * 1024,
) -> dict:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    members = load_central_directory(reader, tail_bytes=tail_bytes)
    missing = sorted(set(member_names) - set(members))
    if missing:
        raise KeyError(f"requested ZIP members do not exist: {missing}")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.partial-", dir=output.parent)
    )
    records = []
    try:
        for name in member_names:
            member = members[name]
            payload = extract_member(reader, member)
            relative = safe_relative_member(name, strip_prefix)
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            records.append(
                {
                    **asdict(member),
                    "output_relative_path": relative.as_posix(),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )

        manifest = {
            "audit_id": "hugsim_official_sample_anchor_fetch",
            "date": date.today().isoformat(),
            "archive": {
                "url": archive_url,
                "size_bytes": reader.size,
                "provider_declared_sha256": provider_sha256,
                "provider_declared_sha256_locally_verified": False,
                "etag": archive_etag,
                "access": "HTTP byte ranges; full archive not downloaded",
            },
            "strip_prefix": strip_prefix,
            "member_count": len(records),
            "members": records,
        }
        (temporary / "source_archive_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.rename(temporary, output)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--member", action="append", required=True, dest="members")
    parser.add_argument("--strip-prefix", default="")
    parser.add_argument("--provider-sha256")
    parser.add_argument("--tail-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reader = HttpRangeReader(args.url, timeout_s=args.timeout_seconds)
    manifest = fetch_members(
        reader=reader,
        member_names=args.members,
        output=args.output.resolve(),
        strip_prefix=args.strip_prefix,
        archive_url=args.url,
        provider_sha256=args.provider_sha256,
        archive_etag=reader.etag,
        tail_bytes=args.tail_bytes,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
