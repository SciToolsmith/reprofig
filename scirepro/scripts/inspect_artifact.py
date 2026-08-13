#!/usr/bin/env python3
"""Create a non-executing, path-redacted inventory for a local artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import stat
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


LICENSE_NAMES = {
    "license", "license.txt", "license.md", "copying", "copying.txt",
    "notice", "notice.txt", "copyright", "copyright.txt",
}
UNIX_USER_PATH = re.compile(r"/(?:Users|home)/[^/\s\"']+")
WINDOWS_USER_PATH = re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"']+")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_text(value: str, artifact: Path | None = None) -> str:
    result = value
    if artifact is not None:
        raw = str(artifact)
        result = result.replace(raw, "$ARTIFACT")
        result = result.replace(json.dumps(raw)[1:-1], "$ARTIFACT")
    result = UNIX_USER_PATH.sub("/$USER", result)
    result = WINDOWS_USER_PATH.sub(r"C:\\Users\\$USER", result)
    return result


def suspicious_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    has_windows_drive = bool(re.match(r"(?i)^[A-Z]:/", normalized))
    return pure.is_absolute() or has_windows_drive or ".." in pure.parts or normalized.startswith("~")


def zip_inventory(path: Path, limit: int) -> dict:
    entries = []
    suspicious = []
    license_candidates = []
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        for info in infos[:limit]:
            mode = (info.external_attr >> 16) & 0xFFFF
            is_link = stat.S_ISLNK(mode)
            display_name = redact_text(info.filename)
            record = {
                "name": display_name,
                "sizeBytes": info.file_size,
                "compressedBytes": info.compress_size,
                "directory": info.is_dir(),
                "symlink": is_link,
            }
            entries.append(record)
            if suspicious_name(info.filename) or is_link:
                suspicious.append(record)
            if PurePosixPath(info.filename.lower()).name in LICENSE_NAMES:
                license_candidates.append(display_name)
    return {
        "format": "zip",
        "entryCount": len(infos),
        "truncated": len(infos) > limit,
        "entries": entries,
        "suspiciousEntries": suspicious,
        "licenseCandidates": license_candidates,
    }


def tar_inventory(path: Path, limit: int) -> dict:
    entries = []
    suspicious = []
    license_candidates = []
    with tarfile.open(path, "r:*") as archive:
        members = archive.getmembers()
        for member in members[:limit]:
            display_name = redact_text(member.name)
            record = {
                "name": display_name,
                "sizeBytes": member.size,
                "directory": member.isdir(),
                "symlink": member.issym() or member.islnk(),
                "device": member.isdev(),
            }
            entries.append(record)
            if suspicious_name(member.name) or record["symlink"] or record["device"]:
                suspicious.append(record)
            if PurePosixPath(member.name.lower()).name in LICENSE_NAMES:
                license_candidates.append(display_name)
    return {
        "format": "tar",
        "entryCount": len(members),
        "truncated": len(members) > limit,
        "entries": entries,
        "suspiciousEntries": suspicious,
        "licenseCandidates": license_candidates,
    }


def directory_inventory(path: Path, limit: int) -> dict:
    entries = []
    license_candidates = []
    suspicious = []
    for item in sorted(path.rglob("*")):
        relative = item.relative_to(path).as_posix()
        if item.is_symlink():
            suspicious.append({"name": relative, "symlink": True})
        if item.is_file() and len(entries) < limit:
            record = {"name": relative, "sizeBytes": item.stat().st_size, "symlink": item.is_symlink()}
            entries.append(record)
            if item.name.lower() in LICENSE_NAMES:
                license_candidates.append(relative)
    count = sum(1 for item in path.rglob("*") if item.is_file())
    return {
        "format": "directory",
        "entryCount": count,
        "truncated": count > limit,
        "entries": entries,
        "suspiciousEntries": suspicious,
        "licenseCandidates": license_candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-entries", type=int, default=1000)
    args = parser.parse_args()

    if args.max_entries <= 0:
        parser.error("--max-entries must be positive")
    supplied = args.artifact.expanduser()
    root_is_symlink = supplied.is_symlink()
    path = supplied.resolve()
    if not path.exists():
        parser.error(f"artifact does not exist: {supplied.name or '$ARTIFACT'}")

    report = {
        "schemaVersion": "scirepro.artifact/v2",
        "path": "$ARTIFACT",
        "name": path.name,
        "type": "directory" if path.is_dir() else "file",
        "symlink": root_is_symlink,
        "privacy": {"absolutePathRedacted": True},
    }
    if path.is_file():
        report.update({
            "sizeBytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "mediaType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        })
        try:
            if zipfile.is_zipfile(path):
                report["inventory"] = zip_inventory(path, args.max_entries)
            elif tarfile.is_tarfile(path):
                report["inventory"] = tar_inventory(path, args.max_entries)
        except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
            report["inventoryError"] = redact_text(str(exc), path)
    else:
        report["inventory"] = directory_inventory(path, args.max_entries)

    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 2 if report.get("inventory", {}).get("suspiciousEntries") else 0


if __name__ == "__main__":
    raise SystemExit(main())
