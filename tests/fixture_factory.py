"""Small, deterministic fixtures created entirely inside each test workspace."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def tiny_png() -> bytes:
    """Return a valid metadata-free 2 x 2 RGB PNG without third-party libraries."""
    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    rows = b"\x00\x20\x70\xd0\xd0\x80\x20" + b"\x00\xd0\x80\x20\x20\x70\xd0"
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(rows)) + _png_chunk(b"IEND", b"")


def _canonical_manifest(manifest: dict) -> bytes:
    clone = json.loads(json.dumps(manifest))
    clone.setdefault("integrity", {})["manifestSha256"] = ""
    return json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def create_target_workspace(root: Path, target_id: str = "target-01") -> tuple[Path, str]:
    original = root / "originals" / (target_id + ".png")
    normalized = root / "figures" / (target_id + ".png")
    payload = tiny_png()
    original.parent.mkdir(parents=True, exist_ok=True)
    normalized.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(payload)
    normalized.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    manifest = {
        "schemaVersion": "scirepro.targets/v1",
        "targetSetId": "test-target-set",
        "createdAt": "2026-08-12T00:00:00Z",
        "paper": None,
        "targetCount": 1,
        "targets": [
            {
                "targetId": target_id,
                "acquisitionMode": "images-only",
                "workflowMode": "image-derived-reconstruction",
                "identityStatus": "not-applicable",
                "requestedAs": "test image",
                "figureReference": None,
                "paperPage": None,
                "caption": None,
                "originalPath": original.relative_to(root).as_posix(),
                "normalizedPath": normalized.relative_to(root).as_posix(),
                "sourceFileName": original.name,
                "sourceSha256": digest,
                "normalizedSha256": digest,
                "targetSha256": digest,
                "mediaType": "image/png",
                "width": 2,
                "height": 2,
                "dpi": 300,
                "cropBoxPdfPoints": None,
                "captionIncluded": False,
                "qaStatus": "verified",
                "localAnalysisOnly": True,
                "notes": ["Synthetic offline test target."],
            }
        ],
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "json-sort-keys-v1",
            "manifestSha256": "",
        },
    }
    manifest["integrity"]["manifestSha256"] = hashlib.sha256(_canonical_manifest(manifest)).hexdigest()
    path = root / "manifest.json"
    write_json(path, manifest)
    return path, digest
