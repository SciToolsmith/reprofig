#!/usr/bin/env python3
"""Create a non-executing, path-redacted inventory for a local artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import stat
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

try:
    from .safe_output import SafeOutputError, checked_directory_create_only, write_text_create_only
except ImportError:  # Direct script execution.
    from safe_output import SafeOutputError, checked_directory_create_only, write_text_create_only


LICENSE_NAMES = {
    "license", "license.txt", "license.md", "copying", "copying.txt",
    "notice", "notice.txt", "copyright", "copyright.txt",
}
UNIX_USER_PATH = re.compile(r"/(?:Users|home)/[^/\s\"']+")
WINDOWS_USER_PATH = re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"']+")
SENSITIVE_NAME = re.compile(
    r"(?i)^(?:\.env(?:\..*)?|id_[rd]sa(?:\.pub)?|credentials?(?:\..*)?|"
    r"secrets?(?:\..*)?|tokens?(?:\..*)?|.*private[_-]?key.*)$"
)
ASSIGNED_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?key|authorization|bearer|client[_-]?secret|"
    r"cookie|credential|password|passwd|private[_-]?key|secret|session[_-]?token|"
    r"access[_-]?token|auth[_-]?token|refresh[_-]?token)\s*[=:]"
)
SECRET_TOKEN = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)


def sha256_handle(handle: object) -> str:
    digest = hashlib.sha256()
    handle.seek(0)  # type: ignore[attr-defined]
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):  # type: ignore[attr-defined]
        digest.update(chunk)
    handle.seek(0)  # type: ignore[attr-defined]
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


def sensitive_entry_name(name: str) -> bool:
    basename = PurePosixPath(name.replace("\\", "/")).name
    return bool(
        SENSITIVE_NAME.fullmatch(basename)
        or ASSIGNED_SECRET.search(name)
        or SECRET_TOKEN.search(name)
    )


def display_entry_name(name: str) -> str:
    return "$REDACTED_SENSITIVE_NAME" if sensitive_entry_name(name) else redact_text(name)


def zip_inventory(source: object, limit: int) -> dict:
    entries = []
    suspicious = []
    license_candidates = []
    source.seek(0)  # type: ignore[attr-defined]
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        suspicious_count = 0
        for index, info in enumerate(infos):
            mode = (info.external_attr >> 16) & 0xFFFF
            is_link = stat.S_ISLNK(mode)
            file_type = stat.S_IFMT(mode)
            special = file_type not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}
            sensitive = sensitive_entry_name(info.filename)
            display_name = display_entry_name(info.filename)
            record = {
                "name": display_name,
                "sizeBytes": info.file_size,
                "compressedBytes": info.compress_size,
                "directory": info.is_dir(),
                "symlink": is_link,
                "special": special,
                "encrypted": bool(info.flag_bits & 0x1),
                "sensitiveName": sensitive,
            }
            if index < limit:
                entries.append(record)
            unsafe = (
                suspicious_name(info.filename) or is_link or special
                or sensitive or bool(info.flag_bits & 0x1)
            )
            if unsafe:
                suspicious_count += 1
                if len(suspicious) < limit:
                    suspicious.append(record)
            if (
                len(license_candidates) < limit
                and PurePosixPath(info.filename.lower()).name in LICENSE_NAMES
            ):
                license_candidates.append(display_name)
    return {
        "format": "zip",
        "entryCount": len(infos),
        "truncated": len(infos) > limit,
        "entries": entries,
        "suspiciousEntries": suspicious,
        "suspiciousEntryCount": suspicious_count,
        "licenseCandidates": license_candidates,
    }


def tar_inventory(source: object, limit: int) -> dict:
    entries = []
    suspicious = []
    license_candidates = []
    source.seek(0)  # type: ignore[attr-defined]
    with tarfile.open(fileobj=source, mode="r:*") as archive:
        members = archive.getmembers()
        suspicious_count = 0
        for index, member in enumerate(members):
            sensitive = sensitive_entry_name(member.name)
            display_name = display_entry_name(member.name)
            record = {
                "name": display_name,
                "sizeBytes": member.size,
                "directory": member.isdir(),
                "symlink": member.issym() or member.islnk(),
                "device": member.isdev(),
                "special": not (member.isfile() or member.isdir() or member.issym() or member.islnk()),
                "sensitiveName": sensitive,
            }
            if index < limit:
                entries.append(record)
            unsafe = (
                suspicious_name(member.name) or record["symlink"] or record["device"]
                or record["special"] or sensitive
            )
            if unsafe:
                suspicious_count += 1
                if len(suspicious) < limit:
                    suspicious.append(record)
            if (
                len(license_candidates) < limit
                and PurePosixPath(member.name.lower()).name in LICENSE_NAMES
            ):
                license_candidates.append(display_name)
    return {
        "format": "tar",
        "entryCount": len(members),
        "truncated": len(members) > limit,
        "entries": entries,
        "suspiciousEntries": suspicious,
        "suspiciousEntryCount": suspicious_count,
        "licenseCandidates": license_candidates,
    }


def special_type(mode: int) -> str:
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode):
        return "character-device"
    if stat.S_ISBLK(mode):
        return "block-device"
    return "special"


def directory_inventory(path: Path, limit: int) -> dict:
    entries = []
    license_candidates = []
    suspicious = []
    count = 0
    suspicious_count = 0

    def add_suspicious(record: dict) -> None:
        nonlocal suspicious_count
        suspicious_count += 1
        if len(suspicious) < limit:
            suspicious.append(record)

    def walk_error(error: OSError) -> None:
        raw_name = Path(error.filename).name if error.filename else "$ARTIFACT"
        add_suspicious({"name": display_entry_name(raw_name), "unreadable": True})

    for current, directory_names, file_names in os.walk(
        path, followlinks=False, onerror=walk_error
    ):
        directory_names.sort()
        file_names.sort()
        current_path = Path(current)
        retained_directories = []
        for name in directory_names:
            item = current_path / name
            relative = item.relative_to(path).as_posix()
            display_relative = display_entry_name(relative)
            sensitive = sensitive_entry_name(relative)
            try:
                item_stat = item.lstat()
            except OSError:
                add_suspicious({"name": display_relative, "unreadable": True})
                continue
            if stat.S_ISLNK(item_stat.st_mode):
                add_suspicious({"name": display_relative, "symlink": True})
            elif stat.S_ISDIR(item_stat.st_mode):
                if sensitive:
                    add_suspicious({"name": display_relative, "sensitiveName": True})
                else:
                    retained_directories.append(name)
            else:
                add_suspicious({"name": display_relative, "specialType": special_type(item_stat.st_mode)})
        directory_names[:] = retained_directories

        for name in file_names:
            item = current_path / name
            relative = item.relative_to(path).as_posix()
            display_relative = display_entry_name(relative)
            sensitive = sensitive_entry_name(relative)
            try:
                item_stat = item.lstat()
            except OSError:
                add_suspicious({"name": display_relative, "unreadable": True})
                continue
            if stat.S_ISLNK(item_stat.st_mode):
                add_suspicious({"name": display_relative, "symlink": True})
                continue
            if not stat.S_ISREG(item_stat.st_mode):
                add_suspicious({"name": display_relative, "specialType": special_type(item_stat.st_mode)})
                continue
            if sensitive:
                add_suspicious({"name": display_relative, "sensitiveName": True})
            count += 1
            if len(entries) < limit:
                entries.append({"name": display_relative, "sizeBytes": item_stat.st_size, "symlink": False})
            if len(license_candidates) < limit and item.name.lower() in LICENSE_NAMES:
                license_candidates.append(display_relative)
    return {
        "format": "directory",
        "entryCount": count,
        "truncated": count > limit,
        "entries": entries,
        "suspiciousEntries": suspicious,
        "suspiciousEntryCount": suspicious_count,
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
    path = Path(os.path.abspath(os.fspath(supplied)))
    if not os.path.lexists(path):
        parser.error(f"artifact does not exist: {supplied.name or '$ARTIFACT'}")
    try:
        safe_parent = checked_directory_create_only(path.parent)
    except SafeOutputError as exc:
        parser.error(str(exc))
    path = safe_parent / path.name

    try:
        root_stat = path.lstat()
    except OSError as exc:
        parser.error(f"artifact is not readable: {redact_text(str(exc), path)}")
    root_is_symlink = stat.S_ISLNK(root_stat.st_mode)
    root_is_file = stat.S_ISREG(root_stat.st_mode)
    root_is_directory = stat.S_ISDIR(root_stat.st_mode)
    root_sensitive = sensitive_entry_name(path.name)

    report = {
        "schemaVersion": "scirepro.artifact/v2",
        "path": "$ARTIFACT",
        "name": display_entry_name(path.name),
        "type": (
            "symlink" if root_is_symlink else
            "directory" if root_is_directory else
            "file" if root_is_file else
            "special"
        ),
        "symlink": root_is_symlink,
        "sensitiveName": root_sensitive,
        "privacy": {"absolutePathRedacted": True},
    }
    if root_is_symlink:
        report["inventory"] = {
            "format": "symlink",
            "entryCount": 0,
            "truncated": False,
            "entries": [],
            "suspiciousEntries": [{"name": display_entry_name(path.name), "symlink": True}],
            "licenseCandidates": [],
        }
    elif root_is_file:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            parser.error(f"artifact could not be opened safely: {redact_text(str(exc), path)}")
        with os.fdopen(descriptor, "rb") as handle:
            opened_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened_stat.st_mode) or (
                opened_stat.st_dev,
                opened_stat.st_ino,
            ) != (root_stat.st_dev, root_stat.st_ino):
                parser.error("artifact changed while it was being opened")
            report.update({
                "sizeBytes": opened_stat.st_size,
                "sha256": sha256_handle(handle),
                "mediaType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            })
            try:
                if zipfile.is_zipfile(handle):
                    report["inventory"] = zip_inventory(handle, args.max_entries)
                else:
                    try:
                        report["inventory"] = tar_inventory(handle, args.max_entries)
                    except tarfile.ReadError:
                        pass
            except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
                report["inventoryError"] = redact_text(str(exc), path)
                report["inspectionFailed"] = True
            final_stat = os.fstat(handle.fileno())
            if (final_stat.st_size, final_stat.st_mtime_ns) != (
                opened_stat.st_size,
                opened_stat.st_mtime_ns,
            ):
                report["inventoryError"] = "artifact changed while it was being inspected"
                report["inspectionFailed"] = True
    elif root_is_directory:
        report["inventory"] = directory_inventory(path, args.max_entries)
    else:
        report["inventory"] = {
            "format": "special",
            "entryCount": 0,
            "truncated": False,
            "entries": [],
            "suspiciousEntries": [{
                "name": display_entry_name(path.name),
                "specialType": special_type(root_stat.st_mode),
            }],
            "licenseCandidates": [],
        }

    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            write_text_create_only(args.output, payload)
        except SafeOutputError as exc:
            parser.error(str(exc))
    else:
        sys.stdout.write(payload)
    return 2 if (
        report.get("sensitiveName")
        or
        report.get("inspectionFailed")
        or report.get("inventory", {}).get("suspiciousEntries")
        or report.get("inventory", {}).get("suspiciousEntryCount", 0)
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
