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
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


PLAN_SCHEMA = "scirepro.delivery-plan/v1"
MAX_PLAN_BYTES = 1024 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_TARGETS = 256
MAX_COPY_ARTIFACTS = 4096
MAX_ARCHIVE_MEMBERS = 4096
MAX_ARCHIVE_EXPANDED_BYTES = 512 * 1024 * 1024

DISTRIBUTIONS = {"local-private", "shareable"}
TARGET_KINDS = {"quantitative", "image-derived", "semantic-diagram", "other"}
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

SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
TARGET_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
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
LOCAL_TILDE = re.compile(r"(?:^|[=,;:\s'\"(@])~(?:[/\\]|$)")
PRIVATE_PATH = re.compile(
    r"(?i)(?:/Users/[^/\s]+|/home/[^/\s]+|[A-Z]:[\\/]+Users[\\/]+[^\\/\s]+)"
)
RESERVED_NAMES = {".ds_store", "desktop.ini", "thumbs.db", "readme.md", "manifest.json"}
WINDOWS_DEVICE = re.compile(r"(?i)^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)")
ARCHIVE_TEXT_SUFFIXES = {
    ".cfg", ".csv", ".html", ".htm", ".ini", ".js", ".json", ".md", ".mjs",
    ".properties", ".py", ".r", ".rels", ".tex", ".txt", ".xml", ".yaml", ".yml",
}


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


def _list_of_lines(value: object, label: str) -> List[str]:
    require(isinstance(value, list), f"{label} must be a list")
    require(len(value) <= 100, f"{label} contains too many entries")
    return [_human_line(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _human_line(value: object, label: str, limit: int = 2000) -> str:
    text = _single_line(value, label, limit)
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


def _scan_secret_stream(handle: object, label: str, digest: Optional[object] = None) -> None:
    overlap = b""
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        if digest is not None:
            digest.update(block)
        combined = overlap + block
        match = _secret_match(combined.decode("utf-8", errors="ignore"))
        require(match is None, f"{label} contains secret-shaped text ({match})")
        overlap = combined[-1024:]


def _scan_archive(path: Path, label: str) -> None:
    if not zipfile.is_zipfile(path):
        return
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            require(len(members) <= MAX_ARCHIVE_MEMBERS, f"{label} archive contains too many members")
            expanded = sum(item.file_size for item in members if not item.is_dir())
            require(
                expanded <= MAX_ARCHIVE_EXPANDED_BYTES,
                f"{label} archive exceeds the expanded scan limit",
            )
            for item in members:
                if item.is_dir():
                    continue
                require(not (item.flag_bits & 0x1), f"{label} archive contains encrypted content")
                member_label = f"{label} archive member {item.filename!r}"
                match = _secret_match(item.filename)
                require(match is None, f"{member_label} contains secret-shaped text ({match})")
                suffix = Path(item.filename).suffix.casefold()
                if suffix not in ARCHIVE_TEXT_SUFFIXES:
                    continue
                with archive.open(item, "r") as member:
                    _scan_secret_stream(member, member_label)
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise DeliveryError(f"{label} compressed package could not be safely inspected") from exc


def _inspect_file(path: Path, label: str) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        _scan_secret_stream(handle, label, digest)
    _scan_archive(path, label)
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
    require(resolved != plan_path.resolve(), "the internal delivery plan may not be copied")
    return resolved


def _parse_copy(
    value: object,
    *,
    plan_path: Path,
    destination_parent: Path,
    label: str,
    distribution: str,
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
    digest = _inspect_file(source, label)
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
) -> Tuple[Optional[CopyArtifact], Optional[str], str]:
    require(isinstance(value, dict), f"{label} must be an object")
    if "sharedRef" in value:
        _ensure_keys(value, {"sharedRef", "label"}, {"sharedRef"}, label)
        shared_name = _safe_output_name(value["sharedRef"], f"{label}.sharedRef")
        display = _human_line(value.get("label", shared_name), f"{label}.label", 200)
        return None, shared_name, display
    artifact = _parse_copy(
        value,
        plan_path=plan_path,
        destination_parent=destination_parent,
        label=label,
        distribution=distribution,
    )
    return artifact, None, artifact.label


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


def _markdown(value: str) -> str:
    escaped = html.escape(value, quote=False).replace("\\", "\\\\")
    return escaped.replace("[", "\\[").replace("]", "\\]").replace("|", "\\|")


def _link_text(link: ArtifactLink) -> str:
    return f"[{_markdown(link.label)}]({link.destination.as_posix()})"


def _artifact_list(label: str, links: Sequence[ArtifactLink]) -> Optional[str]:
    if not links:
        return None
    return f"- **{label}:** " + ", ".join(_link_text(link) for link in links)


def _build_readme(plan: dict, targets: List[dict], shared: List[CopyArtifact], licenses: List[CopyArtifact]) -> str:
    lines = [
        f"# {_markdown(plan['title'])}",
        "",
        f"> {_markdown(plan['conclusion'])}",
        "",
        f"**Distribution:** `{plan['distribution']}`",
        "",
        "## Results",
        "",
        "| Target | Type | Operational | Validation | Claim | Main result |",
        "|---|---|---|---|---|---|",
    ]
    for target in targets:
        lines.append(
            "| " + " | ".join((
                f"`{target['id']}` — {_markdown(target['title'])}",
                f"`{target['kind']}`",
                f"`{target['operationalStatus']}`",
                f"`{target['validationStatus']}`",
                f"`{target['claimStatus']}`",
                "No result" if target["mainLink"] is None else _link_text(target["mainLink"]),
            )) + " |"
        )

    for target in targets:
        lines.extend([
            "",
            f"## `{target['id']}` — {_markdown(target['title'])}",
            "",
            _markdown(target["conclusion"]),
            "",
            f"- **Operational:** `{target['operationalStatus']}`",
            f"- **Validation:** `{target['validationStatus']}`",
            f"- **Scientific claim:** `{target['claimStatus']}`",
        ])
        if target["mainLink"] is None:
            lines.append("- **Main result:** No result")
        else:
            lines.append(f"- **Main result:** {_link_text(target['mainLink'])}")
        if target["kind"] == "image-derived":
            lines.append(
                "- **Evidence boundary:** This reconstructs visible geometry, values, or appearance; "
                "it does not recover or validate the original data, method, experiment, or scientific conclusion."
            )
        elif target["kind"] == "semantic-diagram":
            lines.append(
                "- **Evidence boundary:** Validation concerns schematic fidelity and editability, "
                "not support for a scientific claim."
            )
        if target["referenceLink"] is not None:
            lines.append(f"- **Reference:** {_link_text(target['referenceLink'])}")
        for heading, key in (
            ("Implementation", "implementationLinks"),
            ("Parameters", "parameterLinks"),
            ("Evidence", "evidenceLinks"),
            ("Dependencies", "dependencyLinks"),
        ):
            rendered = _artifact_list(heading, target[key])
            if rendered:
                lines.append(rendered)
        if target["dependencyNote"]:
            lines.append(f"- **Dependency note:** {_markdown(target['dependencyNote'])}")
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
        lines.extend(["", "### Limits", ""])
        if target["limitations"]:
            lines.extend(f"- {_markdown(item)}" for item in target["limitations"])
        else:
            lines.append("- None declared.")
        lines.extend(["", "### Rights", "", _markdown(target["rights"])])

    if shared:
        lines.extend(["", "## Shared files", ""])
        lines.extend(
            f"- [{_markdown(item.label)}]({item.destination.as_posix()}) — `{item.rights}`"
            for item in shared
        )
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
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    mode = path.lstat().st_mode
    require(not stat.S_ISLNK(mode), f"output root may not be a symlink: {path}")
    require(stat.S_ISDIR(mode), f"output root must be a directory: {path}")
    return path.resolve()


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


def assemble(plan_path: Path, output_root: Path) -> Path:
    plan_path = plan_path.expanduser()
    if not plan_path.is_absolute():
        plan_path = Path.cwd() / plan_path
    plan = _read_plan(plan_path)
    _ensure_keys(
        plan,
        {"schemaVersion", "title", "slug", "distribution", "conclusion", "targets", "shared", "licenses"},
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
    shared: List[CopyArtifact] = []
    licenses: List[CopyArtifact] = []
    shared_names: Dict[str, CopyArtifact] = {}

    require(isinstance(plan.get("shared", []), list), "shared must be a list")
    require(isinstance(plan.get("licenses", []), list), "licenses must be a list")
    for index, value in enumerate(plan.get("shared", [])):
        artifact = _parse_copy(
            value,
            plan_path=plan_path,
            destination_parent=Path("shared"),
            label=f"shared[{index}]",
            distribution=distribution,
        )
        key = artifact.destination.name.casefold()
        require(key not in shared_names, f"duplicate shared name: {artifact.destination.name}")
        shared_names[key] = artifact
        shared.append(artifact)
        copies.append(artifact)

    for index, value in enumerate(plan.get("licenses", [])):
        artifact = _parse_copy(
            value,
            plan_path=plan_path,
            destination_parent=Path("LICENSES"),
            label=f"licenses[{index}]",
            distribution=distribution,
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
            destination_parent=Path("figures") / target["id"],
            label=label,
            distribution=distribution,
        )
        if artifact is not None:
            copies.append(artifact)
            return ArtifactLink(artifact.destination, artifact.label)
        pending_refs.append((target, field, shared_ref or "", display))
        return ArtifactLink(Path("shared") / (shared_ref or ""), display)

    for index, raw_target in enumerate(plan["targets"]):
        label = f"targets[{index}]"
        require(isinstance(raw_target, dict), f"{label} must be an object")
        _ensure_keys(
            raw_target,
            {
                "id", "title", "kind", "operationalStatus", "validationStatus",
                "claimStatus", "conclusion", "mainResult", "reference",
                "implementation", "parameters", "evidence", "dependencies",
                "dependencyNote", "rerunArgv", "limitations", "rights",
            },
            {
                "id", "title", "kind", "operationalStatus", "validationStatus",
                "claimStatus", "conclusion", "mainResult", "implementation",
                "parameters", "evidence", "dependencies", "limitations", "rights",
            },
            label,
        )
        target_id = _single_line(raw_target["id"], f"{label}.id", 128)
        require(TARGET_ID.fullmatch(target_id) is not None, f"unsafe target id: {target_id}")
        folded_id = target_id.casefold()
        require(folded_id not in target_ids, f"duplicate target id: {target_id}")
        target_ids.add(folded_id)
        target = {
            "id": target_id,
            "title": _human_line(raw_target["title"], f"{label}.title", 200),
            "kind": _single_line(raw_target["kind"], f"{label}.kind", 40),
            "operationalStatus": _single_line(raw_target["operationalStatus"], f"{label}.operationalStatus", 40),
            "validationStatus": _single_line(raw_target["validationStatus"], f"{label}.validationStatus", 40),
            "claimStatus": _single_line(raw_target["claimStatus"], f"{label}.claimStatus", 40),
            "conclusion": _human_line(raw_target["conclusion"], f"{label}.conclusion", 1000),
            "limitations": _list_of_lines(raw_target["limitations"], f"{label}.limitations"),
            "rights": _human_line(raw_target["rights"], f"{label}.rights", 1000),
            "dependencyNote": None,
        }
        require(target["kind"] in TARGET_KINDS, f"unsupported target kind: {target['kind']}")
        require(target["operationalStatus"] in OPERATIONAL_STATUSES, f"unsupported operational status for {target_id}")
        require(target["validationStatus"] in VALIDATION_STATUSES, f"unsupported validation status for {target_id}")
        require(target["claimStatus"] in CLAIM_STATUSES, f"unsupported claim status for {target_id}")
        _validate_statuses(target)
        target["mainLink"] = None
        if raw_target["mainResult"] is None:
            require(
                target["operationalStatus"] in {"blocked", "cancelled", "failed"},
                f"{target_id} may omit mainResult only when blocked, cancelled, or failed",
            )
        else:
            target["mainLink"] = parse_target_artifact(raw_target["mainResult"], target, "main-result", f"{label}.mainResult")
        target["referenceLink"] = None
        if raw_target.get("reference") is not None:
            target["referenceLink"] = parse_target_artifact(raw_target["reference"], target, "reference", f"{label}.reference")
        for field, output_key in (
            ("implementation", "implementationLinks"),
            ("parameters", "parameterLinks"),
            ("evidence", "evidenceLinks"),
            ("dependencies", "dependencyLinks"),
        ):
            raw_items = raw_target[field]
            require(isinstance(raw_items, list), f"{label}.{field} must be a list")
            require(len(raw_items) <= 64, f"{label}.{field} has too many entries")
            target[output_key] = [
                parse_target_artifact(item, target, field, f"{label}.{field}[{item_index}]")
                for item_index, item in enumerate(raw_items)
            ]
        rerun_raw = raw_target.get("rerunArgv")
        target["rerunArgv"] = [] if rerun_raw is None else _parse_rerun(rerun_raw, f"{label}.rerunArgv")
        if raw_target.get("dependencyNote") is not None:
            target["dependencyNote"] = _human_line(raw_target["dependencyNote"], f"{label}.dependencyNote", 500)
        require(
            bool(target["implementationLinks"]) == bool(target["rerunArgv"]),
            f"{target_id} must provide implementation and exactly one rerun argv together",
        )
        if target["implementationLinks"]:
            require(
                bool(target["dependencyLinks"]) or bool(target["dependencyNote"]),
                f"{target_id} executable target requires dependency artifacts or dependencyNote",
            )
        targets.append(target)

    for target, field, shared_ref, _display in pending_refs:
        shared_artifact = shared_names.get(shared_ref.casefold())
        require(shared_artifact is not None, f"{target['id']} {field} references missing shared artifact: {shared_ref}")
        require(
            shared_ref == shared_artifact.destination.name,
            f"{target['id']} {field} must match shared artifact case exactly: {shared_artifact.destination.name}",
        )

    require(len(copies) <= MAX_COPY_ARTIFACTS, "delivery contains too many copied artifacts")
    destinations: Dict[str, CopyArtifact] = {}
    digests: Dict[str, CopyArtifact] = {}
    for artifact in copies:
        destination_key = artifact.destination.as_posix().casefold()
        require(destination_key not in destinations, f"duplicate destination path: {artifact.destination}")
        destinations[destination_key] = artifact
        previous = digests.get(artifact.digest)
        require(
            previous is None,
            "duplicate file content must use one canonical shared entry: "
            f"{previous.destination if previous else ''} and {artifact.destination}",
        )
        digests[artifact.digest] = artifact
    require(sum(item.size for item in copies) <= MAX_TOTAL_BYTES, "delivery exceeds the total size limit")

    readme = _build_readme(plan, targets, shared, licenses)
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
