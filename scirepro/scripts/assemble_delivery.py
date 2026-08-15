#!/usr/bin/env python3
"""Assemble one small, human-first SciRepro customer delivery.

The input plan is an internal whitelist.  It is validated but never copied.
Files are copied into a sibling staging directory and published atomically
without replacing an existing delivery.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import html
import json
import os
import re
import shlex
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from .safe_output import SafeOutputError, checked_directory_create_only
except ImportError:  # Direct script execution.
    from safe_output import SafeOutputError, checked_directory_create_only


PLAN_SCHEMA = "scirepro.delivery-plan/v4"
MAX_PLAN_BYTES = 1024 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_TARGETS = 256
MAX_COPY_ARTIFACTS = 4096
MAX_ARCHIVE_MEMBERS = 4096
MAX_ARCHIVE_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_TOTAL_MEMBERS = 4096
MAX_ARCHIVE_TOTAL_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 200

DISTRIBUTIONS = {"local-private", "shareable"}
TARGET_KINDS = {"quantitative", "image-derived", "semantic-diagram", "other"}
ROUTES = {
    "direct-recompute",
    "mechanism-reproduction",
    "alternative-validation",
    "image-derived-reconstruction",
    "original-case-blocked",
    "semantic-diagram-handoff",
}
OPERATIONAL_STATUSES = {"complete", "partial", "failed", "blocked", "cancelled"}
VALIDATION_STATUSES = {
    "passed", "partially-passed", "failed", "inconclusive", "not-run",
}
CLAIM_STATUSES = {
    "supported", "partially-supported", "unsupported", "inconclusive",
    "not-tested", "not-applicable",
}
RIGHTS_STATUSES = {
    "generated", "included-permitted", "public-domain", "local-only",
}
SHAREABLE_RIGHTS = {"generated", "included-permitted", "public-domain"}
EXTRA_PURPOSES = {"requested-output", "downstream-use"}
ROOT_RESERVED_NAMES = {"common", "licenses", "readme.md"}
DELIVERY_ROLE_FIELDS = (
    "sourceFiles", "configFiles", "inputFiles", "modelFiles",
    "environmentFiles", "requestedExtras",
)
PREVIEW_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
EDITABLE_RESULT_SUFFIXES = {
    ".pptx", ".svg", ".drawio", ".fig", ".ai", ".eps", ".odg",
}
ALWAYS_TRANSIENT_NAME = re.compile(
    r"(?i)(?:^|[._-])(?:delivery[-_]?plan|resource[-_]?usage|"
    r"qa[-_]?(?:report|overlay|check)|editability[-_]?check|"
    r"(?:baseline[-_]?)?v0|original[-_]?vs[-_]?v0|reference[-_]?crop)"
    r"(?:[._-]|$)"
)
PROCESS_RECORD_NAME = re.compile(
    r"(?i)(?:^|[._-])(?:"
    r"manifest|"
    r"(?:environment|runtime|installed|package)(?:[-_][a-z0-9]+)*"
    r"[-_](?:packages|inventory|snapshot)|"
    r"(?:runtime|environment|route|matlab|license|capability)[-_]?probe|"
    r"(?:source|environment|rights|capability)[-_]?audit|"
    r"iteration[-_]?trace|sensitivity[-_]?(?:summary|results|details|grid)"
    r")(?:[._-]|$)"
)
VALIDATION_RECORD_NAME = re.compile(r"(?i)(?:^|[._-])(?:validation|verify)(?:[._-]|$)")
CONFIGURATION_NAME = re.compile(r"(?i)(?:^|[._-])(?:config|criteria|parameters|settings)(?:[._-]|$)")
DATA_MODEL_NAME = re.compile(
    r"(?i)(?:^|[._-])(?:data|dataset|input|model|weights|checkpoint)(?:[._-]|$)"
)
INTERNAL_RECORD_SUFFIXES = {".csv", ".json", ".ndjson", ".tsv", ".txt", ".yaml", ".yml"}
SCIENTIFIC_DATA_MODEL_SUFFIXES = {
    ".bin", ".ckpt", ".csv", ".h5", ".hdf5", ".mat", ".model", ".npy",
    ".npz", ".onnx", ".parquet", ".pickle", ".pkl", ".pt", ".pth",
    ".safetensors", ".tsv",
}
SOURCE_CODE_SUFFIXES = {
    ".bash", ".c", ".cc", ".cpp", ".cu", ".cxx", ".f", ".f03", ".f08",
    ".f90", ".f95", ".for", ".go", ".h", ".hpp", ".hxx", ".ipynb", ".jl",
    ".js", ".m", ".mjs", ".mlx", ".p", ".py", ".pyx", ".r", ".rmd",
    ".rs", ".scala", ".sh", ".sql", ".stan", ".swift", ".ts", ".tsx",
}
SOURCE_BUILD_NAMES = {
    "cmakelists.txt", "cargo.toml", "makefile", "project.toml", "package.json",
}
INTERPRETER_ENTRYPOINT_SUFFIXES = {
    "python": {".py"}, "python3": {".py"}, "pypy": {".py"}, "pypy3": {".py"},
    "r": {".r"}, "rscript": {".r"}, "julia": {".jl"},
    "matlab": {".m", ".mlx", ".p"}, "matlab.exe": {".m", ".mlx", ".p"},
    "octave": {".m"}, "node": {".js", ".mjs"},
    "bash": {".bash", ".sh"}, "sh": {".sh"}, "zsh": {".sh"},
}
RERUN_PATH_SUFFIXES = {
    ".bash", ".cfg", ".csv", ".h5", ".hdf5", ".ini", ".ipynb", ".jl",
    ".js", ".json", ".m", ".mat", ".mjs", ".mlx", ".npy", ".npz", ".p",
    ".parquet", ".py", ".r", ".sh", ".slx", ".toml", ".tsv", ".txt",
    ".yaml", ".yml",
}
RERUN_FILE_FLAGS = {
    "--config", "--data", "--dataset", "--input", "--model", "--output",
    "--parameters", "--source", "--weights", "--checkpoint",
}
RERUN_FILE_FLAG = re.compile(
    r"(?i)^--?(?:checkpoint|config(?:uration)?|data(?:set)?|input(?:-file)?|"
    r"model|output(?:-file)?|parameters?|source|weights?)$"
)
PIPELINE_STAGES = {"input", "preprocessing", "method", "aggregation", "visualization"}
NATIVE_CAPABILITIES = {
    "not-applicable", "missing", "available-untested", "prerequisites-present",
    "verified", "authority-required", "unavailable", "inconclusive",
}
ENGINE_SELECTION_BASES = {
    "no-author-native", "author-native",
    "objective-portability", "objective-independent", "declared-fallback",
}

SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
TARGET_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
ENGINE_ID = re.compile(r"^[a-z][a-z0-9+._-]{0,63}$")
OUTPUT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
SENSITIVE_NAME = re.compile(
    r"(?i)^(?:\.env(?:\..*)?|id_[rd]sa(?:\.pub)?|credentials?(?:\..*)?|"
    r"secrets?(?:\..*)?|tokens?(?:\..*)?|.*private[_-]?key.*)$"
)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----")
ASSIGNED_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?key|authorization|bearer|client[_-]?secret|"
    r"cookie|credential|password|passwd|private[_-]?key|secret|session[_-]?token|"
    r"access[_-]?token|auth[_-]?token|refresh[_-]?token)\s*[=:]\s*"
    r"(?:[\"'][^\s\"']{8,}[\"']|[A-Za-z0-9_./+=-]{16,})"
)
SECRET_TOKEN = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)
SENSITIVE_ARG = re.compile(
    r"(?i)^--?(?:api[-_]?key|access[-_]?key|authorization|bearer|client[-_]?secret|"
    r"cookie|credential|password|passwd|private[-_]?key|secret|session|token)(?:=|$)"
)
WINDOWS_ABSOLUTE = re.compile(r"(?i)(?:^|[=,;:\s'\"(@])(?:[A-Z]:[\\/]|\\\\)")
LOCAL_ABSOLUTE = re.compile(r"(?:^|[=,;:\s'\"(@])/(?!/)")
PROSE_LOCAL_ABSOLUTE = re.compile(r"(?:^|[=,;:\s'\"(@])/(?!/)(?=[A-Za-z0-9._-])")
LOCAL_TILDE = re.compile(r"(?:^|[=,;:\s'\"(@])~(?:[/\\]|$)")
PRIVATE_PATH = re.compile(
    r"(?i)(?:/Users/[^/\s]+|/home/[^/\s]+|[A-Z]:[\\/]+Users[\\/]+[^\\/\s]+)"
)
FILE_URI = re.compile(r"(?i)(?:^|[=,;:\s'\"(@])file:/")
RESERVED_NAMES = {".ds_store", "desktop.ini", "thumbs.db", "readme.md", "manifest.json"}
WINDOWS_DEVICE = re.compile(r"(?i)^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)")
UNSUPPORTED_ARCHIVE_SUFFIXES = {
    ".7z", ".bz2", ".cab", ".gz", ".lz", ".lz4", ".lzma", ".rar", ".xz", ".z", ".zst",
}
NESTED_ARCHIVE_SUFFIXES = UNSUPPORTED_ARCHIVE_SUFFIXES | {
    ".tar", ".tbz", ".tbz2", ".tgz", ".txz", ".zip",
}
COMPRESSED_MAGIC = (
    b"\x1f\x8b",       # gzip
    b"BZh",             # bzip2
    b"\xfd7zXZ\x00",  # xz
    b"7z\xbc\xaf'\x1c",  # 7z
    b"Rar!\x1a\x07",   # rar
    b"\x28\xb5\x2f\xfd",  # zstd
)


class DeliveryError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DeliveryError(message)


@dataclass(frozen=True)
class CopyArtifact:
    source: Path
    destination: Path
    rights: str
    label: str
    digest: str
    size: int


@dataclass(frozen=True)
class ArtifactLink:
    destination: Path
    label: str
    rights: str
    purpose: Optional[str] = None
    source: Optional[Path] = None


@dataclass
class ArchiveScanBudget:
    members: int = 0
    expanded_bytes: int = 0

    def consume(self, *, members: int, expanded_bytes: int, compressed_bytes: int, label: str) -> None:
        require(members <= MAX_ARCHIVE_MEMBERS, f"{label} archive contains too many members")
        require(
            expanded_bytes <= MAX_ARCHIVE_EXPANDED_BYTES,
            f"{label} archive exceeds the expanded scan limit",
        )
        require(
            expanded_bytes <= max(64 * 1024 * 1024, compressed_bytes * MAX_ARCHIVE_COMPRESSION_RATIO),
            f"{label} archive exceeds the safe compression-ratio limit",
        )
        self.members += members
        self.expanded_bytes += expanded_bytes
        require(
            self.members <= MAX_ARCHIVE_TOTAL_MEMBERS,
            "delivery archives exceed the aggregate member scan limit",
        )
        require(
            self.expanded_bytes <= MAX_ARCHIVE_TOTAL_EXPANDED_BYTES,
            "delivery archives exceed the aggregate expanded scan limit",
        )


def _single_line(value: object, label: str, limit: int = 2000) -> str:
    require(isinstance(value, str), f"{label} must be a string")
    require(0 < len(value) <= limit, f"{label} must contain 1-{limit} characters")
    require(value == value.strip(), f"{label} may not have leading or trailing whitespace")
    require("\n" not in value and "\r" not in value, f"{label} must be one line")
    require(
        not any(ord(character) < 32 or ord(character) == 127 for character in value),
        f"{label} contains a control character",
    )
    return value


def _concise_list(value: object, label: str) -> List[str]:
    require(isinstance(value, list), f"{label} must be a list")
    require(len(value) <= 12, f"{label} contains too many entries")
    return [
        _human_line(item, f"{label}[{index}]", 500)
        for index, item in enumerate(value)
    ]


def _human_line(value: object, label: str, limit: int = 2000) -> str:
    text = _single_line(value, label, limit)
    require(FILE_URI.search(text) is None, f"{label} contains a local path")
    require(PROSE_LOCAL_ABSOLUTE.search(text) is None, f"{label} contains a local absolute path")
    require(LOCAL_TILDE.search(text) is None, f"{label} contains a local path")
    require(WINDOWS_ABSOLUTE.search(text) is None, f"{label} contains a local absolute path")
    require(PRIVATE_PATH.search(text) is None, f"{label} contains a private absolute path")
    return text


def _safe_output_name(value: object, label: str) -> str:
    name = _single_line(value, label, 128)
    require(OUTPUT_NAME.fullmatch(name) is not None, f"unsafe output name for {label}: {name}")
    require(not name.endswith("."), f"unsafe output name for {label}: {name}")
    require(WINDOWS_DEVICE.match(name) is None, f"reserved output name for {label}: {name}")
    require(name.casefold() not in RESERVED_NAMES, f"reserved output name for {label}: {name}")
    require(SENSITIVE_NAME.fullmatch(name) is None, f"sensitive output name for {label}: {name}")
    return name


def _regular_file(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise DeliveryError(f"missing {label}: {path}") from exc
    require(not stat.S_ISLNK(mode), f"{label} may not be a symlink: {path}")
    require(stat.S_ISREG(mode), f"{label} must be a regular file: {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _secret_match(text: str) -> Optional[str]:
    for name, pattern in (
        ("private-key header", PRIVATE_KEY),
        ("assigned credential", ASSIGNED_SECRET),
        ("high-confidence token", SECRET_TOKEN),
    ):
        if pattern.search(text):
            return name
    return None


def _decoded_text_views(data: bytes) -> List[str]:
    """Decode likely text without treating arbitrary binary as every encoding."""
    views = [data.decode("utf-8", errors="ignore")]
    nul_ratio = data.count(b"\x00") / max(1, len(data))
    if data.startswith((b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")) or nul_ratio >= 0.10:
        for encoding in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
            try:
                views.append(data.decode(encoding, errors="ignore"))
            except (LookupError, UnicodeError):
                pass
    return views


def _unsafe_text_match(data: bytes) -> Optional[str]:
    for text in _decoded_text_views(data):
        secret = _secret_match(text)
        if secret is not None:
            return f"secret-shaped text ({secret})"
        if PRIVATE_PATH.search(text):
            return "a private absolute path"
    return None


def _scan_secret_stream(
    handle: object,
    label: str,
    digest: Optional[object] = None,
    initial: bytes = b"",
) -> None:
    if digest is not None and initial:
        digest.update(initial)
    issue = _unsafe_text_match(initial)
    require(issue is None, f"{label} contains {issue}")
    overlap = initial[-2048:]
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        if digest is not None:
            digest.update(block)
        combined = overlap + block
        issue = _unsafe_text_match(combined)
        require(issue is None, f"{label} contains {issue}")
        overlap = combined[-2048:]


def _scan_archive_member_stream(handle: object, member_name: str, label: str) -> None:
    head = handle.read(512)
    suffixes = {suffix.casefold() for suffix in Path(member_name).suffixes}
    nested = (
        bool(suffixes & NESTED_ARCHIVE_SUFFIXES)
        or head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
        or any(head.startswith(prefix) for prefix in COMPRESSED_MAGIC)
        or (len(head) >= 262 and head[257:262] == b"ustar")
    )
    require(not nested, f"{label} contains a nested compressed package")
    _scan_secret_stream(handle, label, initial=head)


def _archive_member_key(name: str, label: str) -> str:
    """Validate one archive member path and return a normalized collision key."""
    require(bool(name), f"{label} has an empty member name")
    require("\\" not in name, f"{label} contains a backslash path")
    require(not name.startswith("/"), f"{label} contains an absolute path")
    require(re.match(r"(?i)^[A-Z]:", name) is None, f"{label} contains a drive path")
    parts = tuple(part for part in name.split("/") if part not in {"", "."})
    require(parts and ".." not in parts, f"{label} traverses outside the package")
    normalized = "/".join(parts)
    match = _secret_match(normalized)
    require(match is None, f"{label} contains secret-shaped text ({match})")
    require(PRIVATE_PATH.search(normalized) is None, f"{label} contains a private path")
    basename = parts[-1]
    require(
        SENSITIVE_NAME.fullmatch(basename) is None,
        f"{label} has a sensitive member name: {basename}",
    )
    return normalized.casefold()


def _scan_zip_archive(path: Path, label: str, budget: ArchiveScanBudget) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            expanded = sum(item.file_size for item in members if not item.is_dir())
            budget.consume(
                members=len(members),
                expanded_bytes=expanded,
                compressed_bytes=path.stat().st_size,
                label=label,
            )
            seen: set[str] = set()
            for item in members:
                member_label = f"{label} archive member {item.filename!r}"
                key = _archive_member_key(item.filename, member_label)
                require(key not in seen, f"{label} archive has duplicate normalized member: {item.filename}")
                seen.add(key)
                require(not (item.flag_bits & 0x1), f"{label} archive contains encrypted content")
                unix_mode = (item.external_attr >> 16) & 0xFFFF
                unix_type = stat.S_IFMT(unix_mode)
                require(unix_type != stat.S_IFLNK, f"{member_label} is a symlink")
                if item.is_dir():
                    continue
                require(
                    unix_type in {0, stat.S_IFREG},
                    f"{member_label} is not a regular file",
                )
                with archive.open(item, "r") as member:
                    _scan_archive_member_stream(member, item.filename, member_label)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, NotImplementedError, RuntimeError, OSError) as exc:
        raise DeliveryError(f"{label} compressed package could not be safely inspected") from exc


def _scan_tar_archive(path: Path, label: str, budget: ArchiveScanBudget) -> bool:
    try:
        archive = tarfile.open(path, mode="r:*")
    except (tarfile.TarError, EOFError, OSError):
        return False
    try:
        with archive:
            members = archive.getmembers()
            expanded = sum(item.size for item in members if item.isfile())
            budget.consume(
                members=len(members),
                expanded_bytes=expanded,
                compressed_bytes=path.stat().st_size,
                label=label,
            )
            seen: set[str] = set()
            for item in members:
                member_label = f"{label} archive member {item.name!r}"
                key = _archive_member_key(item.name, member_label)
                require(key not in seen, f"{label} archive has duplicate normalized member: {item.name}")
                seen.add(key)
                require(not (item.issym() or item.islnk()), f"{member_label} is a link")
                if item.isdir():
                    continue
                require(item.isfile(), f"{member_label} is not a regular file")
                member = archive.extractfile(item)
                require(member is not None, f"{member_label} could not be read")
                with member:
                    _scan_archive_member_stream(member, item.name, member_label)
    except (tarfile.TarError, EOFError, RuntimeError, OSError) as exc:
        raise DeliveryError(f"{label} compressed package could not be safely inspected") from exc
    return True


def _scan_archive(path: Path, label: str, budget: ArchiveScanBudget) -> None:
    if zipfile.is_zipfile(path):
        _scan_zip_archive(path, label, budget)
        return
    if _scan_tar_archive(path, label, budget):
        return
    suffixes = {suffix.casefold() for suffix in path.suffixes}
    with path.open("rb") as handle:
        magic = handle.read(8)
    archive_like = bool(suffixes & UNSUPPORTED_ARCHIVE_SUFFIXES) or any(
        magic.startswith(prefix) for prefix in COMPRESSED_MAGIC
    )
    require(
        not archive_like,
        f"{label} uses an unsupported compressed package format",
    )


def _inspect_file(path: Path, label: str, budget: ArchiveScanBudget) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        _scan_secret_stream(handle, label, digest)
    _scan_archive(path, label, budget)
    return digest.hexdigest()


def _read_plan(path: Path) -> dict:
    _regular_file(path, "delivery plan")
    require(path.stat().st_size <= MAX_PLAN_BYTES, "delivery plan exceeds the size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeliveryError(f"delivery plan is not valid UTF-8 JSON: {path}") from exc
    require(isinstance(value, dict), "delivery plan must contain a JSON object")
    return value


def _ensure_keys(value: dict, allowed: set, required: set, label: str) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    require(not unknown, f"{label} has unknown fields: {', '.join(unknown)}")
    require(not missing, f"{label} is missing fields: {', '.join(missing)}")


def _resolve_source(raw: object, plan_path: Path, label: str) -> Path:
    source = _single_line(raw, f"{label}.source", 4096)
    require(not source.startswith("~"), f"{label}.source may not use '~'")
    path = Path(source)
    if not path.is_absolute():
        path = plan_path.parent / path
    _regular_file(path, label)
    resolved = path.resolve()
    try:
        same_as_plan = os.path.samefile(resolved, plan_path)
    except OSError:
        same_as_plan = resolved == plan_path.resolve()
    require(not same_as_plan, "the internal delivery plan may not be copied")
    return resolved


def _parse_copy(
    value: object,
    *,
    plan_path: Path,
    destination_parent: Path,
    label: str,
    distribution: str,
    scan_budget: ArchiveScanBudget,
) -> CopyArtifact:
    require(isinstance(value, dict), f"{label} must be an object")
    _ensure_keys(
        value,
        {"source", "name", "rights", "label"},
        {"source", "name", "rights"},
        label,
    )
    name = _safe_output_name(value["name"], f"{label}.name")
    rights = _single_line(value["rights"], f"{label}.rights", 64)
    require(rights in RIGHTS_STATUSES, f"unsupported rights status for {label}: {rights}")
    if distribution == "shareable":
        require(
            rights in SHAREABLE_RIGHTS,
            f"shareable delivery requires explicit redistribution rights for {label}",
        )
    source = _resolve_source(value["source"], plan_path, label)
    size = source.stat().st_size
    require(size <= MAX_FILE_BYTES, f"{label} exceeds the per-file size limit")
    digest = _inspect_file(source, label, scan_budget)
    _regular_file(source, label)
    require(source.stat().st_size == size, f"{label} changed while being validated")
    artifact_label = _human_line(value.get("label", name), f"{label}.label", 200)
    return CopyArtifact(
        source=source,
        destination=destination_parent / name,
        rights=rights,
        label=artifact_label,
        digest=digest,
        size=size,
    )


def _parse_link(
    value: object,
    *,
    plan_path: Path,
    destination_parent: Path,
    label: str,
    distribution: str,
    scan_budget: ArchiveScanBudget,
) -> Tuple[Optional[CopyArtifact], Optional[str], str]:
    require(isinstance(value, dict), f"{label} must be an object")
    if "commonRef" in value:
        _ensure_keys(value, {"commonRef", "label"}, {"commonRef"}, label)
        common_name = _safe_output_name(value["commonRef"], f"{label}.commonRef")
        display = _human_line(value.get("label", common_name), f"{label}.label", 200)
        return None, common_name, display
    artifact = _parse_copy(
        value,
        plan_path=plan_path,
        destination_parent=destination_parent,
        label=label,
        distribution=distribution,
        scan_budget=scan_budget,
    )
    return artifact, None, artifact.label


def _parse_extra_link(
    value: object,
    *,
    plan_path: Path,
    destination_parent: Path,
    label: str,
    distribution: str,
    scan_budget: ArchiveScanBudget,
) -> Tuple[Optional[CopyArtifact], Optional[str], str, str]:
    require(isinstance(value, dict), f"{label} must be an object")
    purpose = _single_line(value.get("purpose"), f"{label}.purpose", 64)
    require(purpose in EXTRA_PURPOSES, f"unsupported customer purpose for {label}: {purpose}")
    artifact_value = {key: item for key, item in value.items() if key != "purpose"}
    artifact, shared_ref, display = _parse_link(
        artifact_value,
        plan_path=plan_path,
        destination_parent=destination_parent,
        label=label,
        distribution=distribution,
        scan_budget=scan_budget,
    )
    return artifact, shared_ref, display, purpose


def _portable_delivery_path(value: object, label: str) -> str:
    path = _single_line(value, label, 512).replace("\\", "/")
    require(not path.startswith("/"), f"{label} must be relative to the delivery root")
    require("//" not in path, f"{label} contains an empty path component")
    parts = Path(path).parts
    require(parts and all(part not in {"", ".", ".."} for part in parts), f"unsafe {label}: {path}")
    require(WINDOWS_ABSOLUTE.search(path) is None, f"{label} contains an absolute path")
    require(PRIVATE_PATH.search(path) is None, f"{label} contains a private path")
    return Path(*parts).as_posix()


def _reject_internal_process_artifact(link: ArtifactLink, role: str, label: str) -> None:
    """Keep transient process evidence out without rejecting legitimate validation code/data."""
    name = link.destination.name
    suffix = Path(name).suffix.casefold()
    always_transient = ALWAYS_TRANSIENT_NAME.search(name) is not None
    require(
        suffix != ".log" and not always_transient,
        f"{label} is internal process evidence and may not be delivered as {role}",
    )
    if role == "sourceFiles" and suffix in SOURCE_CODE_SUFFIXES:
        return
    validation_record = (
        suffix in INTERNAL_RECORD_SUFFIXES
        and VALIDATION_RECORD_NAME.search(name) is not None
        and not (role == "configFiles" and CONFIGURATION_NAME.search(name) is not None)
    )
    if role in {"inputFiles", "modelFiles"} and validation_record:
        validation_record = not (
            suffix in SCIENTIFIC_DATA_MODEL_SUFFIXES or DATA_MODEL_NAME.search(name) is not None
        )
    machine_process_record = (
        suffix in INTERNAL_RECORD_SUFFIXES
        and PROCESS_RECORD_NAME.search(name) is not None
        and not (
            role in {"inputFiles", "modelFiles"}
            and DATA_MODEL_NAME.search(name) is not None
        )
    )
    require(
        not validation_record
        and not machine_process_record,
        f"{label} is internal process evidence and may not be delivered as {role}",
    )


def _validate_environment_artifact(link: ArtifactLink, label: str) -> None:
    """Environment artifacts are dependency declarations, never probe/package snapshots."""
    name = link.destination.name.casefold()
    allowed = (
        re.fullmatch(r"requirements(?:[._-][a-z0-9._-]+)?\.(?:txt|in)", name) is not None
        or re.fullmatch(r"constraints(?:[._-][a-z0-9._-]+)?\.txt", name) is not None
        or re.fullmatch(
            r"(?:[a-z0-9._-]+[-_])?environment(?:[._-][a-z0-9._-]+)?\.(?:yml|yaml|txt)",
            name,
        ) is not None
        or re.fullmatch(r"conda-lock(?:[._-][a-z0-9._-]+)?\.(?:yml|yaml)", name) is not None
        or re.fullmatch(r"(?:docker|container)file(?:\.[a-z0-9._-]+)?", name) is not None
        or re.fullmatch(r"(?:docker-)?compose(?:\.[a-z0-9._-]+)?\.(?:yml|yaml)", name) is not None
        or name in {
            "pyproject.toml", "setup.cfg", "poetry.lock", "uv.lock", "pdm.lock",
            "pipfile", "pipfile.lock", "package.json", "package-lock.json",
            "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb", "project.toml",
            "manifest.toml", "pixi.toml", "pixi.lock", "cargo.toml", "cargo.lock",
            "go.mod", "go.sum", "go.work", "go.work.sum", "package.swift",
            "package.resolved", "gemfile", "gemfile.lock", "composer.json",
            "composer.lock", "vcpkg.json", "conanfile.txt", "spack.yaml",
            "spack.lock", "renv.lock", "description", "runtime.txt",
        }
    )
    require(allowed, f"{label} must be a minimal dependency/environment declaration")


def _validate_source_artifact(link: ArtifactLink, label: str) -> None:
    name = link.destination.name.casefold()
    suffix = link.destination.suffix.casefold()
    require(
        suffix in SOURCE_CODE_SUFFIXES or name in SOURCE_BUILD_NAMES,
        f"{label} must be final source code or a recognized build entrypoint",
    )
    require(link.source is not None, f"{label} source bytes could not be resolved")
    if suffix == ".mlx":
        require(zipfile.is_zipfile(link.source), f"{label} must be a valid MATLAB live script package")
    elif suffix == ".ipynb":
        try:
            notebook = json.loads(link.source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DeliveryError(f"{label} must be a valid UTF-8 notebook") from exc
        require(
            isinstance(notebook, dict) and isinstance(notebook.get("cells"), list),
            f"{label} must contain a valid notebook cell list",
        )
    elif suffix != ".p":
        try:
            with link.source.open("rb") as source_handle:
                sample = source_handle.read(1024 * 1024)
            require(b"\x00" not in sample, f"{label} appears to be binary rather than source code")
            sample.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise DeliveryError(f"{label} must be UTF-8 source text") from exc
        except OSError as exc:
            raise DeliveryError(f"{label} source bytes could not be read") from exc


def _parse_rerun(value: object, label: str) -> List[str]:
    require(isinstance(value, list), f"{label} must be a list")
    require(0 < len(value) <= 64, f"{label} must contain 1-64 arguments")
    argv = [_single_line(item, f"{label}[{index}]", 2048) for index, item in enumerate(value)]
    require(
        re.fullmatch(r"[A-Za-z0-9._+-]+", argv[0]) is not None,
        f"{label}[0] must be a portable executable name",
    )
    for index, argument in enumerate(argv):
        require(not SENSITIVE_ARG.match(argument), f"{label}[{index}] contains a secret-bearing flag")
        require(_secret_match(argument) is None, f"{label}[{index}] contains secret-shaped text")
        require("file:" not in argument.casefold(), f"{label}[{index}] contains a local path")
        require(not LOCAL_ABSOLUTE.search(argument), f"{label}[{index}] contains a local path")
        require(not LOCAL_TILDE.search(argument), f"{label}[{index}] contains a local path")
        require(not WINDOWS_ABSOLUTE.search(argument), f"{label}[{index}] contains a local path")
        require(PRIVATE_PATH.search(argument) is None, f"{label}[{index}] contains a private absolute path")
        if "/" in argument or "\\" in argument:
            normalized = argument.replace("\\", "/").split("=", 1)[-1]
            require(".." not in Path(normalized).parts, f"{label}[{index}] traverses outside delivery")
    require(sum(len(item) for item in argv) <= 8192, f"{label} is too long")
    return argv


def _validate_rerun_paths(target: dict) -> None:
    """Reject obvious rerun file arguments that are absent from the delivery whitelist."""
    argv = target["rerunArgv"]
    if not argv:
        return
    links = [link for role in DELIVERY_ROLE_FIELDS for link in target["roleLinks"][role]]
    if target["mainLink"] is not None:
        links.append(target["mainLink"])
    allowed = {link.destination.as_posix() for link in links}
    skip_next_expression = False
    expected_file_argument = False
    for index, argument in enumerate(argv):
        if expected_file_argument:
            expected_file_argument = False
            normalized = argument.replace("\\", "/")
            while normalized.startswith("./"):
                normalized = normalized[2:]
            require(
                normalized in allowed,
                f"{target['id']} rerunArgv[{index}] references a file absent from the delivery: {argument}",
            )
            continue
        if skip_next_expression:
            skip_next_expression = False
            continue
        if argument in RERUN_FILE_FLAGS or RERUN_FILE_FLAG.fullmatch(argument):
            expected_file_argument = True
            continue
        if argument in {"-c", "-e", "--eval", "-batch"}:
            skip_next_expression = True
            continue
        flag_name = argument.split("=", 1)[0]
        matched_file_flag = (
            flag_name
            if "=" in argument and (
                flag_name in RERUN_FILE_FLAGS or RERUN_FILE_FLAG.fullmatch(flag_name)
            )
            else None
        )
        if matched_file_flag is not None:
            candidate = argument.split("=", 1)[1]
            normalized = candidate.replace("\\", "/")
            while normalized.startswith("./"):
                normalized = normalized[2:]
            require(
                normalized in allowed,
                f"{target['id']} rerunArgv[{index}] references a file absent from the delivery: {candidate}",
            )
            continue
        candidate = argument.split("=", 1)[1] if argument.startswith("-") and "=" in argument else argument
        if not candidate or candidate.startswith("-") or "://" in candidate:
            continue
        normalized = candidate.replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        suffix = Path(normalized).suffix.casefold()
        generic_suffix = re.fullmatch(r"\.[a-z][a-z0-9_-]{0,31}", suffix) is not None
        looks_like_path = (
            "/" in normalized
            or suffix in RERUN_PATH_SUFFIXES
            or generic_suffix
            or SENSITIVE_NAME.fullmatch(Path(normalized).name) is not None
        )
        if looks_like_path:
            require(
                normalized in allowed,
                f"{target['id']} rerunArgv[{index}] references a file absent from the delivery: {candidate}",
            )
    require(not expected_file_argument, f"{target['id']} rerunArgv ends after a file-taking option")

    source_paths = {
        link.destination.as_posix() for link in target["roleLinks"]["sourceFiles"]
    }
    require(
        target["entrypoint"] in source_paths,
        f"{target['id']} entrypoint must resolve to a delivered sourceFiles artifact",
    )
    inline_eval = {"-c", "-e", "--eval"}.intersection(argv)
    require(
        not inline_eval,
        f"{target['id']} rerunArgv must invoke delivered source rather than inline evaluation",
    )
    entrypoint_invoked = False
    if "-batch" in argv:
        batch_index = argv.index("-batch")
        if batch_index + 1 < len(argv) and argv[0].casefold() in {"matlab", "matlab.exe"}:
            require(
                Path(target["entrypoint"]).suffix.casefold()
                in INTERPRETER_ENTRYPOINT_SUFFIXES[argv[0].casefold()],
                f"{target['id']} entrypoint type is incompatible with MATLAB",
            )
            escaped_entrypoint = re.escape(target["entrypoint"])
            entrypoint_invoked = re.fullmatch(
                rf"\s*run\(\s*(['\"])({escaped_entrypoint})\1\s*\)\s*;?\s*",
                argv[batch_index + 1],
            ) is not None
    elif argv[0].casefold() in {"make", "gmake"}:
        entrypoint_invoked = any(
            argv[index] == "-f" and index + 1 < len(argv) and argv[index + 1] == target["entrypoint"]
            for index in range(1, len(argv))
        )
    else:
        command = Path(argv[0]).name.casefold()
        if re.fullmatch(r"python\d+(?:\.\d+)*", command):
            command = "python3"
        elif re.fullmatch(r"pypy\d+(?:\.\d+)*", command):
            command = "pypy3"
        runtime_flags = {
            "python": {"-b", "-B", "-bb", "-d", "-E", "-i", "-I", "-O", "-OO", "-P", "-q", "-s", "-S", "-u", "-v"},
            "python3": {"-b", "-B", "-bb", "-d", "-E", "-i", "-I", "-O", "-OO", "-P", "-q", "-s", "-S", "-u", "-v"},
            "pypy": {"-b", "-B", "-bb", "-E", "-i", "-I", "-O", "-OO", "-s", "-S", "-u"},
            "pypy3": {"-b", "-B", "-bb", "-E", "-i", "-I", "-O", "-OO", "-s", "-S", "-u"},
            "r": {"--vanilla", "--no-echo", "--no-restore", "--no-save", "--slave"},
            "rscript": {"--vanilla", "--no-echo", "--no-restore", "--no-save"},
            "julia": {"--startup-file=no", "--history-file=no", "--project=@."},
            "octave": {"--no-gui", "--no-init-file", "--no-site-file", "--quiet"},
            "node": {"--no-warnings"},
            "bash": {"-e", "-u"}, "sh": {"-e", "-u"}, "zsh": {"-e", "-u"},
        }
        if command in runtime_flags:
            expected_suffixes = INTERPRETER_ENTRYPOINT_SUFFIXES.get(command)
            if expected_suffixes is not None:
                require(
                    Path(target["entrypoint"]).suffix.casefold() in expected_suffixes,
                    f"{target['id']} entrypoint type is incompatible with rerun interpreter {command}",
                )
            position = 1
            while position < len(argv):
                option = argv[position]
                if option in runtime_flags[command]:
                    position += 1
                    continue
                if command in {"python", "python3", "pypy", "pypy3"}:
                    if option in {"-W", "-X", "--check-hash-based-pycs"}:
                        position += 2
                        continue
                    if (option.startswith("-W") or option.startswith("-X")) and len(option) > 2:
                        position += 1
                        continue
                break
            entrypoint_invoked = position < len(argv) and argv[position] == target["entrypoint"]
        else:
            normalized_command = argv[0].replace("\\", "/")
            while normalized_command.startswith("./"):
                normalized_command = normalized_command[2:]
            entrypoint_invoked = (
                normalized_command == target["entrypoint"]
                or (len(argv) > 1 and argv[1] == target["entrypoint"])
            )
    require(entrypoint_invoked, f"{target['id']} rerunArgv must invoke the declared entrypoint")

    allowed_outputs = {target["mainLink"].destination.as_posix()} if target["mainLink"] else set()
    allowed_outputs.update(
        link.destination.as_posix() for link in target["roleLinks"]["requestedExtras"]
    )
    require(
        set(target["rerunOutputs"]).issubset(allowed_outputs),
        f"{target['id']} rerunOutputs may contain only the main result or explicitly requested extras",
    )
    if target["mainLink"] is not None:
        require(
            target["mainLink"].destination.as_posix() in target["rerunOutputs"],
            f"{target['id']} rerunOutputs must include the main result",
        )


def _markdown(value: str) -> str:
    escaped = html.escape(value, quote=False).replace("\\", "\\\\")
    return escaped.replace("[", "\\[").replace("]", "\\]").replace("|", "\\|")


def _link_text(link: ArtifactLink) -> str:
    return f"[{_markdown(link.label)}]({link.destination.as_posix()})"


def _result_text(link: ArtifactLink) -> List[str]:
    lines = [f"**Main result:** {_link_text(link)}"]
    if link.destination.suffix.casefold() in PREVIEW_SUFFIXES:
        lines.extend(["", f"![{_markdown(link.label)}]({link.destination.as_posix()})"])
    return lines


def _engine_label(engine: str) -> str:
    return {
        "matlab": "MATLAB",
        "python": "Python",
        "r": "R",
        "julia": "Julia",
        "octave": "Octave",
        "node": "Node.js",
    }.get(engine, engine)


def _stage_label(stage: str) -> str:
    return {
        "input": "input",
        "preprocessing": "preprocessing",
        "method": "method",
        "aggregation": "aggregation",
        "visualization": "visualization",
    }[stage]


def _deduplicated_lines(*groups: Sequence[str]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                result.append(value)
    return result


def _build_readme(plan: dict, targets: List[dict], licenses: List[CopyArtifact]) -> str:
    lines = [f"# {_markdown(plan['title'])}"]

    if len(targets) > 1:
        lines.extend([
            "",
            f"> {_markdown(plan['conclusion'])}",
            "",
            "## Results",
            "",
            "| Target | Main result |",
            "|---|---|",
        ])
        for target in targets:
            lines.append(
                "| " + " | ".join((
                    f"`{target['id']}` — {_markdown(target['title'])}",
                    "No result" if target["mainLink"] is None else _link_text(target["mainLink"]),
                )) + " |"
            )

    for target in targets:
        lines.extend([
            "",
            "## Result" if len(targets) == 1 else f"## `{target['id']}` — {_markdown(target['title'])}",
            "",
            _markdown(target["conclusion"]),
        ])
        material_substitutions = [
            decision
            for decision in target["stageDecisions"]
            if decision["materialToClaim"]
            and decision["authorNative"] is not None
            and decision["selected"] != decision["authorNative"]
        ]
        if material_substitutions:
            lines.extend(["", "### Implementation boundaries", ""])
            for decision in material_substitutions:
                summary = (
                    f"{_stage_label(decision['stage']).capitalize()}: "
                    f"{_engine_label(decision['selected'])} replaced author-native "
                    f"{_engine_label(decision['authorNative'])}. "
                    f"{decision['evidenceBoundary']} Reason: {decision['reason']}"
                )
                lines.append(f"- {_markdown(summary)}")
        if target["blocker"]:
            lines.extend(["", f"**Blocker:** {_markdown(target['blocker'])}"])
        if target["mainLink"] is None:
            lines.extend(["", "**Main result:** No result"])
        else:
            lines.append("")
            lines.extend(_result_text(target["mainLink"]))
        if target["route"] == "mechanism-reproduction":
            lines.extend(["", "**Scope:** mechanism-level reproduction."])
        elif target["route"] == "alternative-validation":
            lines.extend(["", "**Scope:** independent or alternative validation."])
        if target["kind"] == "image-derived":
            if target["mainLink"] is None:
                lines.extend(["", (
                    "**Scope:** No image-derived reconstruction was produced; "
                    "the supplied pixels did not identify the information required for the requested result."
                )])
            else:
                lines.extend(["", (
                    "**Scope:** image-derived reconstruction of visible geometry, values, or appearance; "
                    "it does not recover or validate the original data, method, experiment, or scientific conclusion."
                )])
        elif target["kind"] == "semantic-diagram":
            lines.extend(["", (
                "**Scope:** editable reconstruction of the supplied schematic; "
                "it does not test a scientific claim."
            )])
        if target["rerunArgv"]:
            lines.extend([
                "",
                "### Re-run",
                "",
                "Run from the delivery root:",
                "",
                "```sh",
                shlex.join(target["rerunArgv"]),
                "```",
            ])
            lines.append(f"Dependencies: {_markdown(target['dependencyNote'])}")
        role_labels = {
            "sourceFiles": "Code",
            "configFiles": "Configuration",
            "inputFiles": "Required input",
            "modelFiles": "Required models",
            "environmentFiles": "Environment",
            "requestedExtras": "Requested additional files",
        }
        material_roles = [role for role in DELIVERY_ROLE_FIELDS if target["roleLinks"][role]]
        if material_roles:
            lines.extend(["", "### Files", ""])
            for role in material_roles:
                links = ", ".join(_link_text(link) for link in target["roleLinks"][role])
                lines.append(f"- **{role_labels[role]}:** {links}")
        assumptions_and_limits = _deduplicated_lines(
            target["materialAssumptions"], target["limitations"]
        )
        if assumptions_and_limits:
            lines.extend(["", "### Assumptions and limits", ""])
            lines.extend(f"- {_markdown(item)}" for item in assumptions_and_limits)
        has_third_party = any(
            link.rights != "generated"
            for role in DELIVERY_ROLE_FIELDS
            for link in target["roleLinks"][role]
        ) or (target["mainLink"] is not None and target["mainLink"].rights != "generated")
        if has_third_party:
            lines.extend(["", "### Third-party materials", "", _markdown(target["rights"])])

    if licenses:
        lines.extend(["", "## Licenses", ""])
        lines.extend(
            f"- [{_markdown(item.label)}]({item.destination.as_posix()})"
            for item in licenses
        )
    lines.append("")
    return "\n".join(lines)


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _rename_no_replace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        function = libc.renamex_np
        function.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        function.restype = ctypes.c_int
        result = function(source_bytes, destination_bytes, 0x00000004)
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        function = libc.renameat2
        function.argtypes = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        result = function(-100, source_bytes, -100, destination_bytes, 0x00000001)
    else:
        raise DeliveryError("atomic create-only publication is unavailable on this platform")
    if result != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise DeliveryError(f"destination already exists: {destination}")
        raise DeliveryError(f"atomic publication failed: {os.strerror(code)}")


def _atomic_publish(staging: Path, destination: Path) -> None:
    lock = destination.parent / f".{destination.name}.publish.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise DeliveryError(f"publish lock already exists: {lock}") from exc
    try:
        require(not _lexists(destination), f"destination already exists: {destination}")
        _rename_no_replace(staging, destination)
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _checked_output_root(path: Path) -> Path:
    try:
        return checked_directory_create_only(path)
    except SafeOutputError as exc:
        raise DeliveryError(str(exc)) from exc


def _validate_statuses(target: dict) -> None:
    kind = target["kind"]
    operational = target["operationalStatus"]
    validation = target["validationStatus"]
    claim = target["claimStatus"]
    if kind in {"image-derived", "semantic-diagram"}:
        require(claim == "not-applicable", f"{target['id']} {kind} claim must be not-applicable")
        allowed = {
            "passed": {"complete"},
            "partially-passed": {"complete", "partial"},
            "failed": {"complete", "partial", "failed"},
            "inconclusive": {"complete", "partial", "failed"},
            "not-run": {"blocked", "cancelled", "failed"},
        }
        require(
            operational in allowed[validation],
            f"{target['id']} {validation} validation is incompatible with {operational} execution",
        )
        return
    if claim == "supported":
        require(
            operational == "complete" and validation == "passed",
            f"{target['id']} supported requires complete execution and passed validation",
        )
    elif claim == "partially-supported":
        require(
            operational in {"complete", "partial"} and validation == "partially-passed",
            f"{target['id']} partially-supported requires complete/partial execution and partially-passed validation",
        )
    elif claim == "unsupported":
        require(
            operational == "complete" and validation == "failed",
            f"{target['id']} unsupported requires complete execution and failed validation",
        )
    elif claim == "inconclusive":
        require(
            operational in {"complete", "partial", "failed"} and validation == "inconclusive",
            f"{target['id']} inconclusive requires attempted execution and inconclusive validation",
        )
    elif claim == "not-tested":
        require(validation == "not-run", f"{target['id']} not-tested requires validation not-run")
    else:
        raise DeliveryError(f"{target['id']} scientific target may not use claim {claim}")
    require(
        (validation == "not-run") == (claim == "not-tested"),
        f"{target['id']} not-run validation and not-tested claim must occur together",
    )


def _validate_route(target: dict) -> None:
    kind = target["kind"]
    route = target["route"]
    operational = target["operationalStatus"]
    if kind == "semantic-diagram":
        require(
            route == "semantic-diagram-handoff",
            f"{target['id']} semantic-diagram requires semantic-diagram-handoff",
        )
    elif kind == "image-derived":
        require(
            route in {"image-derived-reconstruction", "original-case-blocked"},
            f"{target['id']} image-derived target has an incompatible route: {route}",
        )
    else:
        require(
            route in {
                "direct-recompute",
                "mechanism-reproduction",
                "alternative-validation",
                "original-case-blocked",
            },
            f"{target['id']} scientific target has an incompatible route: {route}",
        )
    if route == "original-case-blocked":
        require(
            operational == "blocked" and target["validationStatus"] == "not-run",
            f"{target['id']} original-case-blocked requires blocked execution and validation not-run",
        )


def _validate_stage_decisions(raw: object, target: dict, label: str) -> List[dict]:
    scientific_execution = (
        target["kind"] in {"quantitative", "other"}
        and target["route"] != "original-case-blocked"
    )
    require(isinstance(raw, list), f"{label} must be a list")
    require(len(raw) <= len(PIPELINE_STAGES), f"{label} contains too many stages")
    if scientific_execution:
        require(raw, f"{target['id']} scientific execution requires stageDecisions")
    else:
        require(not raw, f"{target['id']} may not declare execution stages without scientific execution")

    decisions: List[dict] = []
    seen: set[str] = set()
    for index, value in enumerate(raw):
        item_label = f"{label}[{index}]"
        require(isinstance(value, dict), f"{item_label} must be an object")
        _ensure_keys(
            value,
            {
                "stage", "materialToClaim", "authorNative", "selected",
                "nativeCapability", "selectionBasis", "reason", "evidenceBoundary",
            },
            {
                "stage", "materialToClaim", "authorNative", "selected",
                "nativeCapability", "selectionBasis", "reason", "evidenceBoundary",
            },
            item_label,
        )
        stage = _single_line(value["stage"], f"{item_label}.stage", 32)
        require(stage in PIPELINE_STAGES, f"unsupported pipeline stage for {target['id']}: {stage}")
        require(stage not in seen, f"{target['id']} has duplicate stage decision: {stage}")
        seen.add(stage)
        material = value["materialToClaim"]
        require(isinstance(material, bool), f"{item_label}.materialToClaim must be a boolean")
        selected = _single_line(value["selected"], f"{item_label}.selected", 64)
        require(ENGINE_ID.fullmatch(selected) is not None, f"invalid selected engine: {selected}")
        author_native = value["authorNative"]
        if author_native is not None:
            author_native = _single_line(author_native, f"{item_label}.authorNative", 64)
            require(
                ENGINE_ID.fullmatch(author_native) is not None,
                f"invalid author-native engine: {author_native}",
            )
        capability = _single_line(value["nativeCapability"], f"{item_label}.nativeCapability", 40)
        basis = _single_line(value["selectionBasis"], f"{item_label}.selectionBasis", 40)
        reason = _human_line(value["reason"], f"{item_label}.reason", 500)
        boundary_raw = value["evidenceBoundary"]
        evidence_boundary = None
        if boundary_raw is not None:
            evidence_boundary = _human_line(
                boundary_raw, f"{item_label}.evidenceBoundary", 500
            )
        require(
            capability in NATIVE_CAPABILITIES,
            f"unsupported native capability for {target['id']} {stage}: {capability}",
        )
        require(
            basis in ENGINE_SELECTION_BASES,
            f"unsupported engine selection basis for {target['id']} {stage}: {basis}",
        )

        substituted = author_native is not None and selected != author_native
        if author_native is None:
            require(
                capability == "not-applicable",
                f"{target['id']} {stage} without author-native evidence must use not-applicable capability",
            )
            require(
                basis == "no-author-native",
                f"{target['id']} {stage} without author-native evidence must use no-author-native basis",
            )
        else:
            require(
                capability != "not-applicable",
                f"{target['id']} author-native {stage} stage may not use not-applicable capability",
            )
            if not substituted:
                require(
                    basis == "author-native",
                    f"{target['id']} native-selected {stage} stage must use author-native basis",
                )
                require(
                    capability == "verified",
                    f"{target['id']} native-selected {stage} stage requires a verified smoke test",
                )
            elif material:
                objective_basis = basis in {"objective-portability", "objective-independent"}
                if capability in {"available-untested", "prerequisites-present", "verified"}:
                    require(
                        objective_basis,
                        f"{target['id']} may not substitute a claim-relevant {stage} stage while "
                        f"author-native capability is {capability}",
                    )
                else:
                    require(
                        objective_basis or basis == "declared-fallback",
                        f"{target['id']} claim-relevant {stage} substitute requires an objective reason or declared fallback",
                    )
                require(
                    bool(evidence_boundary),
                    f"{target['id']} claim-relevant {stage} substitute requires evidenceBoundary",
                )
            else:
                require(
                    basis in {"objective-portability", "objective-independent", "declared-fallback"},
                    f"{target['id']} non-material {stage} substitute needs a valid selection basis",
                )
        if not (material and substituted):
            require(
                evidence_boundary is None,
                f"{target['id']} {stage} may declare evidenceBoundary only for a claim-relevant substitution",
            )
        decisions.append({
            "stage": stage,
            "materialToClaim": material,
            "authorNative": author_native,
            "selected": selected,
            "nativeCapability": capability,
            "selectionBasis": basis,
            "reason": reason,
            "evidenceBoundary": evidence_boundary,
        })
    if scientific_execution:
        require(
            any(decision["materialToClaim"] for decision in decisions),
            f"{target['id']} scientific execution requires at least one claim-relevant stage",
        )
    return decisions


def assemble(plan_path: Path, output_root: Path) -> Path:
    plan_path = plan_path.expanduser()
    if not plan_path.is_absolute():
        plan_path = Path.cwd() / plan_path
    plan = _read_plan(plan_path)
    _ensure_keys(
        plan,
        {"schemaVersion", "title", "slug", "distribution", "conclusion", "targets", "common", "licenses"},
        {"schemaVersion", "title", "slug", "distribution", "conclusion", "targets"},
        "delivery plan",
    )
    require(plan["schemaVersion"] == PLAN_SCHEMA, f"unsupported plan schema: {plan['schemaVersion']}")
    plan["title"] = _human_line(plan["title"], "title", 200)
    plan["conclusion"] = _human_line(plan["conclusion"], "conclusion", 1000)
    slug = _single_line(plan["slug"], "slug", 64)
    require(SLUG.fullmatch(slug) is not None, "slug must use lowercase letters, digits, and hyphens")
    distribution = _single_line(plan["distribution"], "distribution", 32)
    require(distribution in DISTRIBUTIONS, f"unsupported distribution: {distribution}")
    require(isinstance(plan["targets"], list), "targets must be a list")
    require(1 <= len(plan["targets"]) <= MAX_TARGETS, f"targets must contain 1-{MAX_TARGETS} entries")

    copies: List[CopyArtifact] = []
    common: List[CopyArtifact] = []
    licenses: List[CopyArtifact] = []
    common_names: Dict[str, CopyArtifact] = {}
    scan_budget = ArchiveScanBudget()

    require(isinstance(plan.get("common", []), list), "common must be a list")
    require(isinstance(plan.get("licenses", []), list), "licenses must be a list")
    require(
        len(plan["targets"]) > 1 or not plan.get("common", []),
        "single-target deliveries are flat and may not declare common artifacts",
    )
    for index, value in enumerate(plan.get("common", [])):
        artifact = _parse_copy(
            value,
            plan_path=plan_path,
            destination_parent=Path("common"),
            label=f"common[{index}]",
            distribution=distribution,
            scan_budget=scan_budget,
        )
        key = artifact.destination.name.casefold()
        require(key not in common_names, f"duplicate common name: {artifact.destination.name}")
        common_names[key] = artifact
        common.append(artifact)
        copies.append(artifact)

    for index, value in enumerate(plan.get("licenses", [])):
        artifact = _parse_copy(
            value,
            plan_path=plan_path,
            destination_parent=Path("LICENSES"),
            label=f"licenses[{index}]",
            distribution=distribution,
            scan_budget=scan_budget,
        )
        licenses.append(artifact)
        copies.append(artifact)

    target_ids = set()
    targets: List[dict] = []
    pending_refs: List[Tuple[dict, str, str, str]] = []

    def parse_target_artifact(
        raw: object, target: dict, field: str, label: str
    ) -> ArtifactLink:
        artifact, shared_ref, display = _parse_link(
            raw,
            plan_path=plan_path,
            destination_parent=target["destinationParent"],
            label=label,
            distribution=distribution,
            scan_budget=scan_budget,
        )
        require(
            not (field == "main-result" and shared_ref is not None),
            f"{label} must be target-specific and may not reference common mutable output",
        )
        if artifact is not None:
            copies.append(artifact)
            return ArtifactLink(
                artifact.destination, artifact.label, artifact.rights, source=artifact.source
            )
        pending_refs.append((target, field, shared_ref or "", display))
        common_artifact = common_names.get((shared_ref or "").casefold())
        rights = common_artifact.rights if common_artifact is not None else "generated"
        return ArtifactLink(
            Path("common") / (shared_ref or ""),
            display,
            rights,
            source=common_artifact.source if common_artifact is not None else None,
        )

    def parse_target_extra(
        raw: object, target: dict, label: str
    ) -> ArtifactLink:
        artifact, shared_ref, display, purpose = _parse_extra_link(
            raw,
            plan_path=plan_path,
            destination_parent=target["destinationParent"],
            label=label,
            distribution=distribution,
            scan_budget=scan_budget,
        )
        if artifact is not None:
            copies.append(artifact)
            return ArtifactLink(
                artifact.destination,
                artifact.label,
                artifact.rights,
                purpose,
                artifact.source,
            )
        pending_refs.append((target, "requested-extra", shared_ref or "", display))
        common_artifact = common_names.get((shared_ref or "").casefold())
        rights = common_artifact.rights if common_artifact is not None else "generated"
        return ArtifactLink(
            Path("common") / (shared_ref or ""),
            display,
            rights,
            purpose,
            common_artifact.source if common_artifact is not None else None,
        )

    for index, raw_target in enumerate(plan["targets"]):
        label = f"targets[{index}]"
        require(isinstance(raw_target, dict), f"{label} must be an object")
        _ensure_keys(
            raw_target,
            {
                "id", "title", "kind", "operationalStatus", "validationStatus",
                "claimStatus", "route", "stageDecisions", "validationBasis", "materialAssumptions",
                "blocker", "conclusion", "mainResult",
                *DELIVERY_ROLE_FIELDS,
                "entrypoint", "rerunOutputs", "dependencyNote", "rerunArgv", "limitations", "rights",
            },
            {
                "id", "title", "kind", "operationalStatus", "validationStatus",
                "claimStatus", "route", "stageDecisions", "validationBasis", "materialAssumptions",
                "conclusion", "mainResult", *DELIVERY_ROLE_FIELDS,
                "limitations", "rights",
            },
            label,
        )
        target_id = _single_line(raw_target["id"], f"{label}.id", 128)
        require(TARGET_ID.fullmatch(target_id) is not None, f"unsafe target id: {target_id}")
        folded_id = target_id.casefold()
        require(
            folded_id not in ROOT_RESERVED_NAMES,
            f"target id conflicts with a reserved delivery-root name: {target_id}",
        )
        require(folded_id not in target_ids, f"duplicate target id: {target_id}")
        target_ids.add(folded_id)
        target = {
            "id": target_id,
            "title": _human_line(raw_target["title"], f"{label}.title", 200),
            "kind": _single_line(raw_target["kind"], f"{label}.kind", 40),
            "route": _single_line(raw_target["route"], f"{label}.route", 64),
            "operationalStatus": _single_line(raw_target["operationalStatus"], f"{label}.operationalStatus", 40),
            "validationStatus": _single_line(raw_target["validationStatus"], f"{label}.validationStatus", 40),
            "claimStatus": _single_line(raw_target["claimStatus"], f"{label}.claimStatus", 40),
            "conclusion": _human_line(raw_target["conclusion"], f"{label}.conclusion", 1000),
            "validationBasis": _concise_list(
                raw_target["validationBasis"], f"{label}.validationBasis"
            ),
            "materialAssumptions": _concise_list(
                raw_target["materialAssumptions"], f"{label}.materialAssumptions"
            ),
            "limitations": _concise_list(raw_target["limitations"], f"{label}.limitations"),
            "rights": _human_line(raw_target["rights"], f"{label}.rights", 1000),
            "dependencyNote": None,
            "blocker": None,
            "destinationParent": (
                Path() if len(plan["targets"]) == 1 else Path(target_id)
            ),
        }
        require(target["kind"] in TARGET_KINDS, f"unsupported target kind: {target['kind']}")
        require(target["route"] in ROUTES, f"unsupported route for {target_id}: {target['route']}")
        require(target["operationalStatus"] in OPERATIONAL_STATUSES, f"unsupported operational status for {target_id}")
        require(target["validationStatus"] in VALIDATION_STATUSES, f"unsupported validation status for {target_id}")
        require(target["claimStatus"] in CLAIM_STATUSES, f"unsupported claim status for {target_id}")
        _validate_statuses(target)
        _validate_route(target)
        target["stageDecisions"] = _validate_stage_decisions(
            raw_target["stageDecisions"], target, f"{label}.stageDecisions"
        )
        if raw_target.get("blocker") is not None:
            target["blocker"] = _human_line(raw_target["blocker"], f"{label}.blocker", 500)
        if target["validationStatus"] == "not-run":
            require(
                bool(target["blocker"]),
                f"{target_id} validation not-run requires a concise blocker",
            )
        else:
            require(
                bool(target["validationBasis"]),
                f"{target_id} {target['validationStatus']} validation requires validationBasis",
            )
        target["mainLink"] = None
        if raw_target["mainResult"] is None:
            require(
                target["operationalStatus"] in {"blocked", "cancelled", "failed"},
                f"{target_id} may omit mainResult only when blocked, cancelled, or failed",
            )
        else:
            target["mainLink"] = parse_target_artifact(raw_target["mainResult"], target, "main-result", f"{label}.mainResult")
            _reject_internal_process_artifact(
                target["mainLink"], "mainResult", f"{label}.mainResult"
            )
        target["roleLinks"] = {}
        for role in DELIVERY_ROLE_FIELDS:
            items = raw_target[role]
            require(isinstance(items, list), f"{label}.{role} must be a list")
            limit = 16 if role == "requestedExtras" else 64
            require(len(items) <= limit, f"{label}.{role} has too many entries")
            if role == "requestedExtras":
                links = [
                    parse_target_extra(item, target, f"{label}.{role}[{item_index}]")
                    for item_index, item in enumerate(items)
                ]
                for item_index, link in enumerate(links):
                    _reject_internal_process_artifact(
                        link, role, f"{label}.{role}[{item_index}]"
                    )
            else:
                links = [
                    parse_target_artifact(item, target, role, f"{label}.{role}[{item_index}]")
                    for item_index, item in enumerate(items)
                ]
                if role in {
                    "sourceFiles", "configFiles", "inputFiles", "modelFiles", "environmentFiles",
                }:
                    for item_index, link in enumerate(links):
                        artifact_label = f"{label}.{role}[{item_index}]"
                        _reject_internal_process_artifact(link, role, artifact_label)
                        if role == "sourceFiles":
                            _validate_source_artifact(link, artifact_label)
                        if role == "environmentFiles":
                            _validate_environment_artifact(link, artifact_label)
            target["roleLinks"][role] = links
        rerun_raw = raw_target.get("rerunArgv")
        target["rerunArgv"] = [] if rerun_raw is None else _parse_rerun(rerun_raw, f"{label}.rerunArgv")
        entrypoint_raw = raw_target.get("entrypoint")
        target["entrypoint"] = None if entrypoint_raw is None else _portable_delivery_path(
            entrypoint_raw, f"{label}.entrypoint"
        )
        outputs_raw = raw_target.get("rerunOutputs")
        if outputs_raw is None:
            target["rerunOutputs"] = []
        else:
            require(isinstance(outputs_raw, list), f"{label}.rerunOutputs must be a list")
            require(1 <= len(outputs_raw) <= 16, f"{label}.rerunOutputs must contain 1-16 paths")
            target["rerunOutputs"] = [
                _portable_delivery_path(item, f"{label}.rerunOutputs[{item_index}]")
                for item_index, item in enumerate(outputs_raw)
            ]
            require(
                len(set(target["rerunOutputs"])) == len(target["rerunOutputs"]),
                f"{label}.rerunOutputs contains duplicates",
            )
            require(
                all(not output.casefold().startswith("common/") for output in target["rerunOutputs"]),
                f"{label}.rerunOutputs must be target-specific and may not overwrite common artifacts",
            )
        if raw_target.get("dependencyNote") is not None:
            target["dependencyNote"] = _human_line(raw_target["dependencyNote"], f"{label}.dependencyNote", 500)
        require(
            bool(target["rerunArgv"]) == bool(target["entrypoint"]) == bool(target["rerunOutputs"]),
            f"{target_id} must provide rerunArgv, entrypoint, and rerunOutputs together",
        )
        if target["rerunArgv"]:
            require(
                bool(target["dependencyNote"]),
                f"{target_id} executable target requires one concise dependencyNote",
            )
        else:
            require(
                target["dependencyNote"] is None,
                f"{target_id} may not declare dependencies without rerun files",
            )

        successful_scientific = (
            target["kind"] in {"quantitative", "other"}
            and target["operationalStatus"] in {"complete", "partial"}
            and target["route"] != "original-case-blocked"
        )
        if successful_scientific:
            require(
                bool(target["roleLinks"]["sourceFiles"]),
                f"{target_id} completed scientific work requires final sourceFiles",
            )
            require(
                bool(target["rerunArgv"]),
                f"{target_id} completed scientific work requires a runnable final entrypoint",
            )
        successful_reconstruction = (
            target["kind"] in {"image-derived", "semantic-diagram"}
            and target["operationalStatus"] in {"complete", "partial"}
            and target["mainLink"] is not None
        )
        if successful_reconstruction and not target["rerunArgv"]:
            require(
                target["mainLink"].destination.suffix.casefold() in EDITABLE_RESULT_SUFFIXES,
                f"{target_id} reconstruction without sourceFiles must deliver an editable main result",
            )
        _validate_rerun_paths(target)
        targets.append(target)

    if len(targets) == 1:
        only_target = targets[0]
        has_durable_artifact = only_target["mainLink"] is not None or any(
            only_target["roleLinks"][role] for role in DELIVERY_ROLE_FIELDS
        )
        require(
            has_durable_artifact,
            "single-target work with no durable result or production material should be returned in chat",
        )

    referenced_common = {shared_ref.casefold() for _, _, shared_ref, _ in pending_refs}
    common_target_refs: Dict[str, set[str]] = {}
    for target, field, shared_ref, _display in pending_refs:
        shared_artifact = common_names.get(shared_ref.casefold())
        require(shared_artifact is not None, f"{target['id']} {field} references missing common artifact: {shared_ref}")
        require(
            shared_ref == shared_artifact.destination.name,
            f"{target['id']} {field} must match common artifact case exactly: {shared_artifact.destination.name}",
        )
        common_target_refs.setdefault(shared_ref.casefold(), set()).add(target["id"])
    unused_common = sorted(
        artifact.destination.name
        for key, artifact in common_names.items()
        if key not in referenced_common
    )
    require(
        not unused_common,
        "top-level common artifacts must be referenced by at least one target: "
        + ", ".join(unused_common),
    )
    underused_common = sorted(
        artifact.destination.name
        for key, artifact in common_names.items()
        if len(common_target_refs.get(key, set())) < 2
    )
    require(
        not underused_common,
        "common artifacts must be used by at least two distinct targets: "
        + ", ".join(underused_common),
    )

    if licenses:
        license_destinations = {item.destination.as_posix() for item in licenses}
        has_third_party_material = any(
            item.destination.as_posix() not in license_destinations and item.rights != "generated"
            for item in copies
        )
        require(
            has_third_party_material,
            "LICENSES may be delivered only for included third-party material",
        )

    require(len(copies) <= MAX_COPY_ARTIFACTS, "delivery contains too many copied artifacts")
    plan_digest = _sha256(plan_path)
    require(
        all(item.digest != plan_digest for item in copies),
        "the internal delivery plan content may not be copied",
    )
    destinations: Dict[str, CopyArtifact] = {}
    digests: Dict[str, CopyArtifact] = {}
    for artifact in copies:
        destination_key = artifact.destination.as_posix().casefold()
        require(destination_key not in destinations, f"duplicate destination path: {artifact.destination}")
        destinations[destination_key] = artifact
        previous = digests.get(artifact.digest)
        require(
            previous is None,
            "duplicate file content must use one canonical common entry: "
            f"{previous.destination if previous else ''} and {artifact.destination}",
        )
        digests[artifact.digest] = artifact
    require(sum(item.size for item in copies) <= MAX_TOTAL_BYTES, "delivery exceeds the total size limit")

    readme = _build_readme(plan, targets, licenses)
    require(_secret_match(readme) is None, "generated README contains secret-shaped text")

    output_root = _checked_output_root(output_root)
    destination = output_root / f"{slug}-reproduction"
    require(not _lexists(destination), f"destination already exists: {destination}")
    staging = Path(tempfile.mkdtemp(prefix=f".{slug}-reproduction.staging-", dir=output_root))
    try:
        (staging / "README.md").write_text(readme, encoding="utf-8")
        os.chmod(staging / "README.md", 0o644)
        for artifact in sorted(copies, key=lambda item: item.destination.as_posix().casefold()):
            output = staging / artifact.destination
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact.source, output)
            require(
                output.stat().st_size == artifact.size and _sha256(output) == artifact.digest,
                f"source changed while copying: {artifact.source}",
            )
            os.chmod(output, 0o644)
        empty = [path for path in staging.rglob("*") if path.is_dir() and not any(path.iterdir())]
        require(not empty, f"delivery contains empty directories: {empty}")
        _atomic_publish(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return destination


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="internal delivery plan JSON")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        path = assemble(arguments.plan, arguments.output_root)
    except (DeliveryError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if arguments.json:
        print(json.dumps({"path": str(path)}, ensure_ascii=False, sort_keys=True))
    else:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
