#!/usr/bin/env python3
"""Create and verify one compact, report-free SciRepro result folder.

``init`` creates a private staging directory.  Safe local reproduction may
start immediately; this command does not require an execution contract, gate,
approval receipt, or webpage.  ``finalize`` validates the scientific trace,
inventories every file, and atomically publishes ``scirepro-run-<run-id>``.
"""

from __future__ import annotations

import argparse
import copy
import ctypes
import errno
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from materialize_target_figures import TargetError
from materialize_target_figures import validate_manifest as validate_target_manifest


BUNDLE_SCHEMA = "scirepro.run-bundle/v3"
STAGING_SCHEMA = "scirepro.run-bundle-staging/v3"
TARGET_SCHEMA = "scirepro.target-result/v3"
RESOURCE_SCHEMA = "scirepro.resource-usage/v2"
ENVIRONMENT_SCHEMA = "scirepro.environment/v2"

RUN_STATUSES = {"complete", "partial", "failed", "blocked", "cancelled"}
OPERATIONAL_STATUSES = RUN_STATUSES | {"pending"}
VALIDATION_STATUSES = {"passed", "partially-passed", "failed", "inconclusive", "not-run"}
CLAIM_STATUSES = {
    "supported", "partially-supported", "unsupported", "inconclusive",
    "not-tested", "not-applicable",
}
SCIENTIFIC_STATUS_MATRIX = {
    "supported": ({"complete"}, "passed", True),
    "partially-supported": ({"complete", "partial"}, "partially-passed", True),
    "unsupported": ({"complete"}, "failed", True),
    "inconclusive": ({"complete", "partial", "failed"}, "inconclusive", True),
    "not-tested": (RUN_STATUSES, "not-run", False),
}
WORKFLOW_MODES = {"scientific-reproduction", "image-derived-reconstruction"}
DISTRIBUTIONS = {"local-private", "shareable"}
ARTIFACT_ROLES = {"source", "input", "code", "config", "environment"}
RIGHTS_STATUSES = {"generated", "included-permitted", "local-only", "omitted-restricted"}
ACCEPTANCE_RESULTS = VALIDATION_STATUSES
ROUTE_KINDS = {
    "direct-recompute", "mechanism-reproduction", "alternative-validation",
    "image-derived-reconstruction",
}

RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TARGET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_NAME = re.compile(
    r"(?i)^(?:\.env(?:\..*)?|id_[rd]sa(?:\.pub)?|credentials?(?:\..*)?|"
    r"secrets?(?:\..*)?|tokens?(?:\..*)?|.*private[_-]?key.*)$"
)
SENSITIVE_VALUE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|cookie|credential|password|private[_-]?key|"
    r"secret|session|token)\s*[=:]\s*[\"']?[^\s\"']{8,}"
)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----")
SENSITIVE_ARG_FLAG = re.compile(
    r"(?i)^-{0,2}(?:api[-_]?key|access[-_]?key|authorization|bearer|client[-_]?secret|"
    r"cookie|credential|password|passwd|private[-_]?key|secret|session|token)(?:=|$)"
)
SECRET_TOKEN = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)
WINDOWS_ABSOLUTE = re.compile(r"(?i)(?:^|[=,;:\s'\"(@])(?:[A-Z]:[\\/]|\\\\)")
POSIX_ABSOLUTE = re.compile(r"(?:^|[=,;:\s'\"(@])/(?!/)")
TILDE_PATH = re.compile(r"(?:^|[=,;:\s'\"(@])~(?:[/\\]|$)")
LOCAL_FILE_URI = re.compile(r"(?i)file:(?://)?[/\\]")
FORMAL_EXTERNAL_LOCATOR = re.compile(
    r"(?i)^(?:https?://|s3://|gs://|doi:|urn:|zenodo:|osf:)\S+$"
)
TEXT_SUFFIXES = {
    ".css", ".csv", ".html", ".ini", ".js", ".json", ".jsonl", ".log",
    ".m", ".md", ".py", ".r", ".sh", ".svg", ".toml", ".tsv", ".txt",
    ".yaml", ".yml",
}
IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".svg", ".webp", ".pdf"}
ALLOWED_TOP_LEVEL = {"README.md", "manifest.json", "shared", "targets"}


class BundleError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleError(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "%" in value:
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and not value.startswith(("/", "~"))
        and re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value) is None
        and ".." not in path.parts
        and all(part not in {"", "."} for part in path.parts)
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(document: dict, field: str) -> str:
    clone = copy.deepcopy(document)
    clone.setdefault("integrity", {})[field] = ""
    payload = json.dumps(
        clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")


def read_json(path: Path, label: str) -> dict:
    require_regular(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    require(isinstance(value, dict), f"{label} must contain a JSON object")
    return value


def require_regular(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise BundleError(f"missing {label}: {path}") from exc
    require(stat.S_ISREG(mode), f"{label} must be a regular file: {path}")


def checked_directory(path: Path, label: str, *, create: bool = False) -> Path:
    absolute = path.expanduser()
    if not absolute.is_absolute():
        absolute = Path.cwd() / absolute
    if create:
        absolute.mkdir(parents=True, exist_ok=True)
    try:
        mode = absolute.lstat().st_mode
    except FileNotFoundError as exc:
        raise BundleError(f"missing {label}: {absolute}") from exc
    require(not stat.S_ISLNK(mode), f"{label} may not be a symlink: {absolute}")
    require(stat.S_ISDIR(mode), f"{label} must be a directory: {absolute}")
    return absolute.resolve()


def atomic_publish(source: Path, destination: Path) -> None:
    """Atomically publish without replacing an existing path."""
    lock = destination.parent / f"{destination.name}.publish.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise BundleError(f"publish lock already exists: {lock}") from exc
    try:
        require(not destination.exists(), f"destination already exists: {destination}")
        _rename_no_replace(source, destination)
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


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
        raise BundleError(
            "atomic create-only publication is unavailable on this platform; "
            "leave the validated staging directory in place"
        )
    if result != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise BundleError(f"destination already exists: {destination}")
        raise OSError(code, os.strerror(code), str(destination))


def parse_target_spec(raw: str, default_mode: str) -> tuple[str, str]:
    if "=" in raw:
        target_id, mode = raw.split("=", 1)
    else:
        target_id, mode = raw, default_mode
    require(bool(TARGET_ID.fullmatch(target_id)), f"invalid target ID: {target_id!r}")
    require(mode in WORKFLOW_MODES, f"invalid workflow mode: {mode!r}")
    return target_id, mode


def load_target_context(manifest_path: Path | None) -> tuple[dict | None, dict[str, dict]]:
    if manifest_path is None:
        return None, {}
    path = manifest_path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    require_regular(path, "verified target manifest")
    manifest = read_json(path, "verified target manifest")
    try:
        targets = validate_target_manifest(manifest, root=path.parent, require_verified=True)
    except TargetError as exc:
        raise BundleError(f"invalid target manifest: {exc}") from exc
    return {"path": path.resolve(), "document": manifest}, targets


def select_targets(args: argparse.Namespace, available: dict[str, dict]) -> list[dict]:
    raw_targets = args.target or list(available)
    require(raw_targets, "provide --target at least once or supply --target-manifest")
    selected: list[dict] = []
    seen: set[str] = set()
    for raw in raw_targets:
        explicit_mode = "=" in raw
        raw_id = raw.split("=", 1)[0]
        fallback = available.get(raw_id, {}).get("workflowMode", args.default_mode)
        target_id, mode = parse_target_spec(raw, fallback)
        require(target_id not in seen, f"duplicate target ID: {target_id}")
        if available:
            require(target_id in available, f"target is absent from the verified manifest: {target_id}")
            if explicit_mode:
                require(
                    mode == available[target_id]["workflowMode"],
                    f"{target_id}: workflow mode differs from the verified manifest",
                )
            mode = available[target_id]["workflowMode"]
        selected.append({
            "targetId": target_id,
            "workflowMode": mode,
            "targetSha256": available.get(target_id, {}).get("targetSha256"),
        })
        seen.add(target_id)
    return selected


def initial_target_result(target: dict) -> dict:
    mode = target["workflowMode"]
    return {
        "schemaVersion": TARGET_SCHEMA,
        "targetId": target["targetId"],
        "workflowMode": mode,
        "identity": {
            "targetSha256": target.get("targetSha256"),
            "referencePath": None,
            "rightsStatus": None,
        },
        "route": None,
        "execution": None,
        "operationalStatus": "pending",
        "validationStatus": "not-run",
        "claimStatus": "not-tested" if mode == "scientific-reproduction" else "not-applicable",
        "summary": "The target has not reached a terminal state.",
        "baselineV0": None,
        "selectedOutput": None,
        "outputs": [],
        "blocker": None,
        "acceptance": {"overallStatus": "not-run", "criteria": []},
        "calibration": None,
        "visualQA": None,
        "warnings": [],
        "errors": [],
        "assumptions": [],
        "remainingDiscrepancies": [],
    }


def initial_environment() -> dict:
    return {
        "schemaVersion": ENVIRONMENT_SCHEMA,
        "captureStatus": "not-recorded",
        "engines": [],
        "packages": [],
        "hardware": {},
        "notes": [],
    }


def initial_resources() -> dict:
    return {
        "schemaVersion": RESOURCE_SCHEMA,
        "caps": [],
        "measurements": [],
        "notes": [],
    }


def copy_target_material(
    root: Path,
    context: dict | None,
    available: dict[str, dict],
    selected: list[dict],
    distribution: str,
) -> None:
    if context is None:
        return
    plan_path = root / "shared/targets/manifest.json"
    write_json(plan_path, context["document"])
    for record in selected:
        target_id = record["targetId"]
        target = available[target_id]
        result_path = root / f"targets/{target_id}/result.json"
        result = read_json(result_path, f"{target_id} initial result")
        include = distribution == "local-private" or target.get("localAnalysisOnly") is False
        if include:
            source = context["path"].parent / target["normalizedPath"]
            require_regular(source, f"{target_id} normalized target")
            destination_relative = f"targets/{target_id}/reference/target.png"
            destination = root / destination_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            require(
                sha256_file(destination) == target["targetSha256"],
                f"{target_id}: copied target hash mismatch",
            )
            result["identity"].update({
                "referencePath": destination_relative,
                "rightsStatus": "local-only" if distribution == "local-private" else "included-permitted",
            })
        else:
            result["identity"]["rightsStatus"] = "omitted-restricted"
        write_json(result_path, result)


def initialize_bundle(args: argparse.Namespace) -> Path:
    require(bool(RUN_ID.fullmatch(args.run_id)), "run ID must be path-safe and at most 64 characters")
    require(args.distribution in DISTRIBUTIONS, "invalid distribution class")
    parent = checked_directory(args.parent, "output parent", create=True)
    context, available = load_target_context(args.target_manifest)
    selected = select_targets(args, available)
    staging = parent / f".scirepro-run-{args.run_id}.staging"
    final = parent / f"scirepro-run-{args.run_id}"
    require(not staging.exists(), f"staging directory already exists: {staging}")
    require(not final.exists(), f"final directory already exists: {final}")

    temporary = Path(tempfile.mkdtemp(prefix=f".scirepro-run-{args.run_id}.init-", dir=parent))
    try:
        state = {
            "schemaVersion": STAGING_SCHEMA,
            "runId": args.run_id,
            "createdAt": now_iso(),
            "distributionClass": args.distribution,
            "targets": selected,
            "targetManifestSha256": (
                context["document"].get("integrity", {}).get("manifestSha256")
                if context else None
            ),
        }
        write_json(temporary / ".scirepro-staging.json", state)
        write_json(temporary / "shared/environment/environment.json", initial_environment())
        write_json(temporary / "shared/execution/resource-usage.json", initial_resources())
        for target in selected:
            write_json(
                temporary / "targets" / target["targetId"] / "result.json",
                initial_target_result(target),
            )
        copy_target_material(temporary, context, available, selected, args.distribution)
        atomic_publish(temporary, staging)
    except Exception:
        if temporary.exists():
            for child in sorted(temporary.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            temporary.rmdir()
        raise
    return staging


def walk_regular_files(root: Path, *, include_manifest: bool = False) -> list[Path]:
    files: list[Path] = []
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in list(directories):
            path = current_path / name
            mode = path.lstat().st_mode
            require(not stat.S_ISLNK(mode), f"symlink directories are forbidden: {path}")
            require(stat.S_ISDIR(mode), f"special directories are forbidden: {path}")
        for name in names:
            path = current_path / name
            mode = path.lstat().st_mode
            require(not stat.S_ISLNK(mode), f"symlinks are forbidden: {path}")
            require(stat.S_ISREG(mode), f"special files are forbidden: {path}")
            relative = path.relative_to(root).as_posix()
            if not include_manifest and relative in {"manifest.json", ".scirepro-staging.json"}:
                continue
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def scan_sensitive_content(root: Path) -> None:
    for path in walk_regular_files(root, include_manifest=True):
        relative = path.relative_to(root)
        require(
            not any(SENSITIVE_NAME.fullmatch(part) for part in relative.parts),
            f"sensitive filename is forbidden: {relative.as_posix()}",
        )
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 4 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        require(not PRIVATE_KEY.search(text), f"private key material is forbidden: {relative}")
        require(not SENSITIVE_VALUE.search(text), f"secret-like assignment is forbidden: {relative}")


def artifact_path(root: Path, value: object, label: str) -> Path:
    require(safe_relative(value), f"{label} path is unsafe")
    path = root / str(value)
    require_regular(path, label)
    return path


def relative_parts(value: str) -> tuple[str, ...]:
    return PurePosixPath(value).parts


def require_scoped_path(value: object, prefixes: tuple[tuple[str, ...], ...], label: str) -> None:
    require(safe_relative(value), f"{label} path is unsafe")
    parts = relative_parts(str(value))
    require(
        any(parts[: len(prefix)] == prefix for prefix in prefixes),
        f"{label} is outside its permitted bundle domain",
    )


def validate_argv(target_id: str, argv: object) -> list[str]:
    require(
        isinstance(argv, list) and argv and all(isinstance(item, str) and item for item in argv),
        f"{target_id}: exact command argv is required",
    )
    require(
        len(argv) <= 256 and all(len(item) <= 4096 for item in argv),
        f"{target_id}: command argv is unreasonably large",
    )
    for index, item in enumerate(argv):
        require(
            not (
                POSIX_ABSOLUTE.search(item)
                or WINDOWS_ABSOLUTE.search(item)
                or TILDE_PATH.search(item)
                or LOCAL_FILE_URI.search(item)
            ),
            f"{target_id}: argv may not persist an absolute or home-relative local path",
        )
        require(
            not (SENSITIVE_ARG_FLAG.search(item) or SENSITIVE_VALUE.search(item) or SECRET_TOKEN.search(item)),
            f"{target_id}: argv contains a secret-bearing flag or value",
        )
        if item.casefold() == "bearer":
            require(index + 1 >= len(argv), f"{target_id}: argv contains a bearer credential")
    return argv


def validate_identity(root: Path, target_id: str, identity: object, distribution: str) -> str:
    require(isinstance(identity, dict), f"{target_id}: identity must be an object")
    target_hash = identity.get("targetSha256")
    require(isinstance(target_hash, str) and SHA256.fullmatch(target_hash), f"{target_id}: target SHA-256 is required")
    rights = identity.get("rightsStatus")
    require(rights in RIGHTS_STATUSES, f"{target_id}: invalid target rights status")
    relative = identity.get("referencePath")
    if relative is None:
        require(rights == "omitted-restricted", f"{target_id}: missing target pixels require omitted-restricted rights")
    else:
        require_scoped_path(
            relative,
            (("targets", target_id, "reference"),),
            f"{target_id} target reference",
        )
        path = artifact_path(root, relative, f"{target_id} target reference")
        require(sha256_file(path) == target_hash, f"{target_id}: target reference hash mismatch")
        if distribution == "shareable":
            require(rights in {"generated", "included-permitted"}, f"{target_id}: local-only target cannot enter a shareable bundle")
    return target_hash


def validate_route(target_id: str, route: object) -> tuple[str, dict]:
    require(isinstance(route, dict), f"{target_id}: route is required after execution")
    route_id = route.get("routeId")
    require(isinstance(route_id, str) and TARGET_ID.fullmatch(route_id), f"{target_id}: invalid route ID")
    engine = route.get("engine")
    require(isinstance(engine, dict), f"{target_id}: route engine is required")
    name = engine.get("name")
    require(isinstance(name, str) and name.strip(), f"{target_id}: engine name is required")
    require(isinstance(engine.get("version"), str) and engine["version"].strip(), f"{target_id}: engine version is required")
    require(type(engine.get("native")) is bool, f"{target_id}: engine native flag must be boolean")
    require(route.get("kind") in ROUTE_KINDS, f"{target_id}: invalid route kind")
    tests = route.get("tests")
    require(
        isinstance(tests, str) and tests.strip() and len(tests) <= 500,
        f"{target_id}: route tests must be a non-empty short statement",
    )
    unsupported = route.get("doesNotSupport")
    require(
        isinstance(unsupported, list)
        and all(isinstance(item, str) and item.strip() for item in unsupported),
        f"{target_id}: route doesNotSupport must be a string array",
    )
    return route_id, {"name": name, "version": engine["version"], "native": engine["native"]}


def validate_frozen_artifact(
    root: Path,
    target_id: str,
    item: object,
    distribution: str,
    *,
    aliased: bool = False,
) -> dict:
    require(isinstance(item, dict), f"{target_id}: frozen artifact must be an object")
    role = item.get("role")
    require(role in ARTIFACT_ROLES, f"{target_id}: invalid frozen artifact role")
    digest = item.get("sha256")
    require(isinstance(digest, str) and SHA256.fullmatch(digest), f"{target_id}: frozen artifact SHA-256 is invalid")
    rights = item.get("rightsStatus")
    require(rights in RIGHTS_STATUSES, f"{target_id}: frozen artifact rights status is invalid")
    if role == "source":
        provenance = item.get("provenance")
        require(isinstance(provenance, dict), f"{target_id}: source provenance is required")
        for field in ("authority", "version", "license", "rights"):
            value = provenance.get(field)
            require(
                isinstance(value, str) and value.strip(),
                f"{target_id}: source provenance {field} is required",
            )
    relative = item.get("includedPath")
    if relative is None:
        require(rights == "omitted-restricted", f"{target_id}: omitted artifact must be marked omitted-restricted")
        reason = item.get("reason")
        require(isinstance(reason, str) and reason.strip(), f"{target_id}: omitted {role} artifact requires a reason")
        locator = item.get("locator")
        require(
            isinstance(locator, str) and FORMAL_EXTERNAL_LOCATOR.fullmatch(locator),
            f"{target_id}: omitted artifact requires a formal external locator",
        )
        require(
            not (SENSITIVE_VALUE.search(locator) or SECRET_TOKEN.search(locator)),
            f"{target_id}: omitted artifact locator may not contain credentials",
        )
        artifact_key = f"locator:{locator}"
    else:
        role_domains = {
            # The verified published target may itself be the only preserved
            # source artifact in an image-derived or paper-fixture route.
            "source": (
                ("targets", target_id, "sources"),
                ("targets", target_id, "reference"),
                ("shared", "sources"),
            ),
            "input": (("targets", target_id, "inputs"), ("shared", "inputs")),
            "code": (("targets", target_id, "code"), ("shared", "code")),
            "config": (("targets", target_id, "config"), ("shared", "config")),
            # Every executed target must bind its own environment snapshot.  The
            # shared environment is a separate aggregate consistency record.
            "environment": (("targets", target_id, "environment"),),
        }
        if not aliased:
            require_scoped_path(relative, role_domains[str(role)], f"{target_id} {role} artifact")
        else:
            require(safe_relative(relative), f"{target_id} {role} artifact path is unsafe")
        path = artifact_path(root, relative, f"{target_id} {role} artifact")
        require(sha256_file(path) == digest, f"{target_id}: frozen {role} artifact hash mismatch")
        if distribution == "shareable":
            require(rights in {"generated", "included-permitted"}, f"{target_id}: {role} artifact is not shareable")
        artifact_key = f"path:{relative}"
    return {
        "role": str(role),
        "sha256": digest,
        "artifactKey": artifact_key,
        "includedPath": relative,
        "roleAlias": item.get("roleAlias"),
    }


def validate_environment_record(path: Path, label: str, required_engine: dict | None = None) -> dict:
    environment = read_json(path, label)
    require(environment.get("schemaVersion") == ENVIRONMENT_SCHEMA, f"{label}: unsupported environment schema")
    status = environment.get("captureStatus")
    require(status in {"not-recorded", "recorded", "partial"}, f"{label}: invalid captureStatus")
    engines = environment.get("engines")
    require(isinstance(engines, list), f"{label}: engines must be an array")
    normalized: list[tuple[str, str]] = []
    for engine in engines:
        require(isinstance(engine, dict), f"{label}: engine record must be an object")
        name = engine.get("name")
        version = engine.get("version")
        require(isinstance(name, str) and name.strip(), f"{label}: engine name is required")
        require(isinstance(version, str) and version.strip(), f"{label}: engine version is required")
        normalized.append((name.strip().casefold(), version.strip()))
    if required_engine is not None:
        require(status in {"recorded", "partial"}, f"{label}: executed route requires a captured environment")
        expected = (required_engine["name"].strip().casefold(), required_engine["version"].strip())
        require(expected in normalized, f"{label}: route engine/version is absent or inconsistent")
    return environment


def validate_execution(
    root: Path,
    target_id: str,
    execution: object,
    distribution: str,
    route_engine: dict,
) -> None:
    require(isinstance(execution, dict), f"{target_id}: execution record is required")
    validate_argv(target_id, execution.get("argv"))
    working = execution.get("workingDirectory")
    require(working == "." or safe_relative(working), f"{target_id}: working directory must be bundle-relative")
    artifacts = execution.get("frozenArtifacts")
    require(isinstance(artifacts, list) and artifacts, f"{target_id}: frozen execution artifacts are required")
    raw_roles: list[str] = []
    for item in artifacts:
        require(isinstance(item, dict), f"{target_id}: frozen artifact must be an object")
        role = item.get("role")
        require(role in ARTIFACT_ROLES, f"{target_id}: invalid frozen artifact role")
        raw_roles.append(str(role))
    require(len(raw_roles) == len(set(raw_roles)), f"{target_id}: duplicate frozen artifact role")
    raw_by_role = {str(item["role"]): item for item in artifacts}
    records: list[dict] = []
    for item in artifacts:
        role = str(item["role"])
        alias = item.get("roleAlias")
        if alias is not None:
            require(role in {"source", "input", "config"}, f"{target_id}: {role} may not be a roleAlias")
            require(alias in ARTIFACT_ROLES and alias != role, f"{target_id}: invalid roleAlias for {role}")
            require(alias in raw_by_role, f"{target_id}: roleAlias for {role} names an absent role")
            require(raw_by_role[alias].get("roleAlias") is None, f"{target_id}: roleAlias chains are forbidden")
            justification = item.get("justification")
            require(
                isinstance(justification, str) and justification.strip(),
                f"{target_id}: aliased {role} artifact requires a justification",
            )
        records.append(
            validate_frozen_artifact(root, target_id, item, distribution, aliased=alias is not None)
        )
    roles = [record["role"] for record in records]
    missing_required = {"code", "environment"} - set(roles)
    require(
        not missing_required,
        f"{target_id}: frozen execution trace is missing required roles: {', '.join(sorted(missing_required))}",
    )
    dispositions = execution.get("roleDispositions", {})
    require(isinstance(dispositions, dict), f"{target_id}: roleDispositions must be an object")
    optional_missing = {"source", "input", "config"} - set(roles)
    require(
        set(dispositions) == optional_missing,
        f"{target_id}: every absent optional role needs exactly one roleDisposition",
    )
    for role in optional_missing:
        disposition = dispositions[role]
        require(isinstance(disposition, dict), f"{target_id}: {role} roleDisposition must be an object")
        require(
            disposition.get("status") == "not-applicable",
            f"{target_id}: absent {role} role must be declared not-applicable",
        )
        for field in ("reason", "binding"):
            value = disposition.get(field)
            require(
                isinstance(value, str) and value.strip(),
                f"{target_id}: absent {role} role requires a non-empty {field}",
            )
    by_role = {record["role"]: record for record in records}
    for record in records:
        alias = record["roleAlias"]
        if alias is not None:
            canonical = by_role[alias]
            require(
                record["artifactKey"] == canonical["artifactKey"]
                and record["sha256"] == canonical["sha256"],
                f"{target_id}: aliased {record['role']} artifact must bind the same artifact as {alias}",
            )
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            if left["artifactKey"] == right["artifactKey"] or left["sha256"] == right["sha256"]:
                aliases_pair = (
                    left["roleAlias"] == right["role"]
                    or right["roleAlias"] == left["role"]
                )
                require(
                    aliases_pair
                    and left["artifactKey"] == right["artifactKey"]
                    and left["sha256"] == right["sha256"],
                    f"{target_id}: shared artifact across roles requires an explicit roleAlias",
                )
    code_record = next(record for record in records if record["role"] == "code")
    require(code_record["includedPath"] is not None, f"{target_id}: executable code/implementation must be included")
    environment_record = next(record for record in records if record["role"] == "environment")
    require(environment_record["includedPath"] is not None, f"{target_id}: environment snapshot must be included")
    validate_environment_record(
        root / environment_record["includedPath"],
        f"{target_id} target environment",
        route_engine,
    )


def validate_acceptance(root: Path, target_id: str, acceptance: object, status: str) -> None:
    require(isinstance(acceptance, dict), f"{target_id}: acceptance result must be an object")
    require(acceptance.get("overallStatus") == status, f"{target_id}: acceptance overall status must match validationStatus")
    criteria = acceptance.get("criteria")
    require(isinstance(criteria, list), f"{target_id}: acceptance criteria must be an array")
    if status != "not-run":
        require(criteria, f"{target_id}: executed validation requires at least one acceptance criterion")
    identifiers: set[str] = set()
    criterion_statuses: list[str] = []
    for criterion in criteria:
        require(isinstance(criterion, dict), f"{target_id}: acceptance criterion must be an object")
        criterion_id = criterion.get("criterionId")
        require(isinstance(criterion_id, str) and TARGET_ID.fullmatch(criterion_id), f"{target_id}: invalid criterion ID")
        require(criterion_id not in identifiers, f"{target_id}: duplicate criterion ID")
        identifiers.add(criterion_id)
        require(criterion.get("status") in ACCEPTANCE_RESULTS, f"{target_id}: invalid criterion status")
        criterion_statuses.append(criterion["status"])
        statement = criterion.get("statement")
        require(isinstance(statement, str) and statement.strip(), f"{target_id}: criterion statement is required")
        evidence = criterion.get("evidencePaths", [])
        require(isinstance(evidence, list), f"{target_id}: criterion evidencePaths must be an array")
        for relative in evidence:
            artifact_path(root, relative, f"{target_id} acceptance evidence")
    if status == "passed":
        require(all(item == "passed" for item in criterion_statuses), f"{target_id}: passed acceptance requires every criterion passed")
    elif status == "partially-passed":
        require("passed" in criterion_statuses and any(item != "passed" for item in criterion_statuses), f"{target_id}: partially-passed acceptance requires mixed criterion outcomes")
    elif status == "failed":
        require("failed" in criterion_statuses, f"{target_id}: failed acceptance requires a failed criterion")
    elif status == "inconclusive":
        require("inconclusive" in criterion_statuses, f"{target_id}: inconclusive acceptance requires an inconclusive criterion")


def validate_scientific_statuses(
    target_id: str,
    operational: str,
    validation: str,
    claim: str,
    *,
    executed: bool,
) -> None:
    require(
        claim in SCIENTIFIC_STATUS_MATRIX,
        f"{target_id}: scientific reproduction cannot use claimStatus {claim}",
    )
    allowed_operations, required_validation, requires_execution = SCIENTIFIC_STATUS_MATRIX[claim]
    require(
        operational in allowed_operations and validation == required_validation,
        f"{target_id}: claimStatus {claim} is incompatible with "
        f"operationalStatus {operational} and validationStatus {validation}",
    )
    if requires_execution:
        require(executed, f"{target_id}: claimStatus {claim} requires an executed scientific test")


def validate_optional_visuals(root: Path, target_id: str, result: dict) -> None:
    calibration = result.get("calibration")
    if calibration is not None:
        require(isinstance(calibration, dict), f"{target_id}: calibration must be an object")
        for key in ("v1", "v2"):
            relative = calibration.get(key)
            if relative is not None:
                artifact_path(root, relative, f"{target_id} {key} output")
        comparisons = calibration.get("comparisonArtifacts", [])
        require(isinstance(comparisons, list), f"{target_id}: comparisonArtifacts must be an array")
        for relative in comparisons:
            artifact_path(root, relative, f"{target_id} comparison artifact")
        stop_reason = calibration.get("stopReason")
        require(isinstance(stop_reason, str) and stop_reason.strip(), f"{target_id}: calibration stopReason is required")
    visual = result.get("visualQA")
    if visual is not None:
        require(isinstance(visual, dict), f"{target_id}: visualQA must be an object")
        require(visual.get("status") in {"passed", "issues-remain", "not-run"}, f"{target_id}: invalid visualQA status")
        require(isinstance(visual.get("issues", []), list), f"{target_id}: visualQA issues must be an array")
        artifacts = visual.get("artifactPaths", [])
        require(isinstance(artifacts, list), f"{target_id}: visualQA artifactPaths must be an array")
        for relative in artifacts:
            artifact_path(root, relative, f"{target_id} visual-QA artifact")


def validate_target(root: Path, expected: dict, distribution: str) -> dict:
    target_id = expected["targetId"]
    path = root / "targets" / target_id / "result.json"
    result = read_json(path, f"{target_id} result")
    require(result.get("schemaVersion") == TARGET_SCHEMA, f"{target_id}: unsupported result schema")
    require(result.get("targetId") == target_id, f"{target_id}: result target ID mismatch")
    require(result.get("workflowMode") == expected["workflowMode"], f"{target_id}: workflow mode changed")
    target_hash = validate_identity(root, target_id, result.get("identity"), distribution)
    if expected.get("targetSha256") is not None:
        require(target_hash == expected["targetSha256"], f"{target_id}: target hash changed from initialization")

    operational = result.get("operationalStatus")
    validation = result.get("validationStatus")
    claim = result.get("claimStatus")
    require(operational in RUN_STATUSES, f"{target_id}: target is not terminal")
    require(validation in VALIDATION_STATUSES, f"{target_id}: invalid validationStatus")
    require(claim in CLAIM_STATUSES, f"{target_id}: invalid claimStatus")
    if result["workflowMode"] == "image-derived-reconstruction":
        require(claim == "not-applicable", f"{target_id}: image-derived reconstruction cannot support a paper claim")

    baseline = result.get("baselineV0")
    blocker = result.get("blocker")
    executed = result.get("execution") is not None
    if result["workflowMode"] == "scientific-reproduction":
        validate_scientific_statuses(
            target_id,
            operational,
            validation,
            claim,
            executed=executed,
        )
    if operational in {"complete", "partial"}:
        require(baseline is not None, f"{target_id}: complete/partial target requires baselineV0")
        require(blocker is None, f"{target_id}: successful target may not carry a terminal blocker")
        require(executed, f"{target_id}: complete/partial target requires an execution trace")
    elif baseline is None:
        require(isinstance(blocker, dict), f"{target_id}: terminal target requires V0 or a blocker")
        require(isinstance(blocker.get("code"), str) and blocker["code"].strip(), f"{target_id}: blocker code is required")
        require(isinstance(blocker.get("detail"), str) and blocker["detail"].strip(), f"{target_id}: blocker detail is required")
    if baseline is not None:
        require_scoped_path(
            baseline,
            (("targets", target_id, "outputs"),),
            f"{target_id} baseline V0",
        )
        baseline_path = artifact_path(root, baseline, f"{target_id} baseline V0")
        require(baseline_path.suffix.lower() in IMAGE_SUFFIXES, f"{target_id}: baselineV0 must be a figure artifact")
        if result["workflowMode"] == "scientific-reproduction":
            require(sha256_file(baseline_path) != target_hash, f"{target_id}: baselineV0 may not duplicate target pixels")
        require(executed, f"{target_id}: a generated V0 requires an execution trace")
    if executed:
        _, route_engine = validate_route(target_id, result.get("route"))
        validate_execution(root, target_id, result["execution"], distribution, route_engine)
    else:
        require(result.get("route") is None, f"{target_id}: an unexecuted target may not claim a route")
        require(validation == "not-run", f"{target_id}: an unexecuted target cannot claim validation")

    outputs = result.get("outputs")
    require(isinstance(outputs, list) and len(outputs) == len(set(outputs)), f"{target_id}: outputs must be unique paths")
    for relative in outputs:
        require_scoped_path(relative, (("targets", target_id, "outputs"),), f"{target_id} output")
        output_path = artifact_path(root, relative, f"{target_id} output")
        if result["workflowMode"] == "scientific-reproduction":
            require(sha256_file(output_path) != target_hash, f"{target_id}: output may not duplicate target pixels")
    if baseline is not None:
        require(baseline in outputs, f"{target_id}: baselineV0 must appear in outputs")
    selected = result.get("selectedOutput")
    if selected is not None:
        require(selected in outputs, f"{target_id}: selectedOutput must appear in outputs")
    validate_acceptance(root, target_id, result.get("acceptance"), validation)
    validate_optional_visuals(root, target_id, result)
    summary = result.get("summary")
    require(isinstance(summary, str) and summary.strip(), f"{target_id}: summary is required")
    for key in ("warnings", "errors"):
        require(isinstance(result.get(key), list) and all(isinstance(item, str) for item in result[key]), f"{target_id}: {key} must be strings")
    for key in ("assumptions", "remainingDiscrepancies"):
        require(
            isinstance(result.get(key), list)
            and all(isinstance(item, str) and item.strip() for item in result[key]),
            f"{target_id}: {key} must be non-empty strings",
        )
    route_id = result.get("route", {}).get("routeId") if isinstance(result.get("route"), dict) else None
    engine = result.get("route", {}).get("engine") if isinstance(result.get("route"), dict) else None
    return {
        "targetId": target_id,
        "workflowMode": result["workflowMode"],
        "targetSha256": target_hash,
        "routeId": route_id,
        "engine": engine,
        "operationalStatus": operational,
        "validationStatus": validation,
        "claimStatus": claim,
        "baselineV0": baseline,
        "selectedOutput": selected,
        "resultSha256": sha256_file(path),
    }


def validate_resources(root: Path, require_measurement: bool) -> None:
    resources = read_json(root / "shared/execution/resource-usage.json", "resource usage")
    require(resources.get("schemaVersion") == RESOURCE_SCHEMA, "unsupported resource-usage schema")
    caps = resources.get("caps")
    measurements = resources.get("measurements")
    require(isinstance(caps, list), "resource caps must be an array")
    require(isinstance(measurements, list), "resource measurements must be an array")
    for cap in caps:
        require(isinstance(cap, dict), "resource cap must be an object")
        require(isinstance(cap.get("resource"), str) and cap["resource"].strip(), "resource cap name is required")
        require(isinstance(cap.get("limit"), (int, float)) and cap["limit"] >= 0, "resource cap limit is invalid")
        require(isinstance(cap.get("unit"), str) and cap["unit"].strip(), "resource cap unit is required")
        enforcement = cap.get("enforcement")
        require(enforcement in {"declared-only", "technically-enforced"}, "resource cap enforcement must be honest")
        mechanism = cap.get("mechanism")
        if enforcement == "technically-enforced":
            require(isinstance(mechanism, str) and mechanism.strip(), "enforced resource cap requires its mechanism")
        else:
            require(mechanism in {None, ""}, "declared-only cap may not claim an enforcement mechanism")
    for measurement in measurements:
        require(isinstance(measurement, dict), "resource measurement must be an object")
        require(isinstance(measurement.get("resource"), str) and measurement["resource"].strip(), "resource measurement name is required")
        require(isinstance(measurement.get("value"), (int, float)) and measurement["value"] >= 0, "resource measurement value is invalid")
        require(isinstance(measurement.get("unit"), str) and measurement["unit"].strip(), "resource measurement unit is required")
        require(isinstance(measurement.get("method"), str) and measurement["method"].strip(), "resource measurement method is required")
    if require_measurement:
        require(measurements, "executed result requires at least one measured resource value")


def validate_environment(root: Path, require_recorded: bool, route_engines: list[dict] | None = None) -> None:
    environment = validate_environment_record(
        root / "shared/environment/environment.json", "shared environment record"
    )
    status = environment["captureStatus"]
    if require_recorded:
        require(status in {"recorded", "partial"}, "executed result requires a captured environment")
    if route_engines:
        available = {
            (engine["name"].strip().casefold(), engine["version"].strip())
            for engine in environment["engines"]
        }
        for engine in route_engines:
            expected = (engine["name"].strip().casefold(), engine["version"].strip())
            require(expected in available, "shared environment record: route engine/version is absent or inconsistent")


def validate_aggregate(status: str, targets: list[dict]) -> None:
    operations = [target["operationalStatus"] for target in targets]
    if status == "complete":
        require(all(item == "complete" for item in operations), "complete run requires every target complete")
    elif status == "partial":
        require(any(item in {"complete", "partial"} for item in operations), "partial run requires at least one useful target")
        require(not all(item == "complete" for item in operations), "all-complete targets require complete run status")
    elif status == "blocked":
        require(all(item == "blocked" for item in operations), "blocked run requires every target blocked")
    elif status == "failed":
        require(all(item in {"failed", "blocked"} for item in operations), "failed run may contain only failed/blocked targets")
        require(any(item == "failed" for item in operations), "failed run requires at least one failed target")
    elif status == "cancelled":
        require(all(item in {"cancelled", "blocked"} for item in operations), "cancelled run may contain only cancelled/blocked targets")
        require(any(item == "cancelled" for item in operations), "cancelled run requires a cancelled target")


def build_inventory(root: Path) -> list[dict]:
    inventory: list[dict] = []
    for path in walk_regular_files(root):
        relative = path.relative_to(root).as_posix()
        inventory.append({
            "path": relative,
            "sha256": sha256_file(path),
            "sizeBytes": path.stat().st_size,
        })
    return inventory


def validate_archived_target_manifest(root: Path, expected_hash: object) -> None:
    path = root / "shared/targets/manifest.json"
    if expected_hash is None:
        require(not path.exists(), "an unbound target manifest appeared after initialization")
        return
    require(isinstance(expected_hash, str) and SHA256.fullmatch(expected_hash), "invalid bound target-manifest hash")
    archived = read_json(path, "archived target manifest")
    integrity = archived.get("integrity")
    require(isinstance(integrity, dict), "archived target manifest integrity is missing")
    require(integrity.get("manifestSha256") == expected_hash, "archived target-manifest binding changed")
    require(
        canonical_hash(archived, "manifestSha256") == expected_hash,
        "archived target-manifest canonical hash mismatch",
    )


def render_readme(state: dict, status: str, targets: list[dict]) -> str:
    rows = [
        "| Target | Route / engine | Operational | Validation | Claim |",
        "|---|---|---|---|---|",
    ]
    for target in targets:
        engine = target.get("engine") or {}
        route = target.get("routeId") or "not executed"
        engine_text = engine.get("name", "—")
        rows.append(
            f"| `{target['targetId']}` | `{route}` / `{engine_text}` | "
            f"`{target['operationalStatus']}` | `{target['validationStatus']}` | "
            f"`{target['claimStatus']}` |"
        )
    return f"""# SciRepro run `{state['runId']}`

**Run status:** `{status}`

**Distribution:** `{state['distributionClass']}`

**Created:** {state['createdAt']}

**Finalized:** {now_iso()}

## Target outcomes

{chr(10).join(rows)}

## Re-run evidence

Each `targets/<target-id>/result.json` binds the target identity, selected route and
engine, exact command argv, frozen source/input/code/config/environment hashes,
acceptance result, and independent operational/validation/claim statuses. Resource
caps state whether they were merely declared or technically enforced.

## Scope

Generated V0, calibrated variants, comparisons, and visual-QA files appear only when
they are relevant. An image-derived reconstruction does not test a paper claim.
"""


def build_manifest(root: Path, state: dict, status: str, targets: list[dict]) -> dict:
    manifest = {
        "schemaVersion": BUNDLE_SCHEMA,
        "runId": state["runId"],
        "bundleId": f"scirepro-run-{state['runId']}",
        "createdAt": state["createdAt"],
        "finalizedAt": now_iso(),
        "status": status,
        "distributionClass": state["distributionClass"],
        "targetManifestSha256": state.get("targetManifestSha256"),
        "targetCount": len(targets),
        "targets": targets,
        "resourceUsage": "shared/execution/resource-usage.json",
        "environment": "shared/environment/environment.json",
        "inventory": build_inventory(root),
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "json-sort-keys-v1",
            "manifestSha256": "",
        },
    }
    manifest["integrity"]["manifestSha256"] = canonical_hash(manifest, "manifestSha256")
    return manifest


def read_staging_state(root: Path) -> dict:
    state = read_json(root / ".scirepro-staging.json", "staging state")
    require(state.get("schemaVersion") == STAGING_SCHEMA, "unsupported staging schema")
    run_id = state.get("runId")
    require(isinstance(run_id, str) and RUN_ID.fullmatch(run_id), "invalid staging run ID")
    require(root.name == f".scirepro-run-{run_id}.staging", "staging directory name does not match run ID")
    require(state.get("distributionClass") in DISTRIBUTIONS, "invalid staging distribution")
    targets = state.get("targets")
    require(isinstance(targets, list) and targets, "staging state has no targets")
    return state


def finalize_bundle(args: argparse.Namespace) -> Path:
    root = checked_directory(args.bundle, "staging bundle")
    state = read_staging_state(root)
    require(args.status in RUN_STATUSES, "invalid run status")
    top_level = {path.name for path in root.iterdir()}
    require(top_level <= (ALLOWED_TOP_LEVEL | {".scirepro-staging.json"}), "unexpected top-level content")
    targets = [
        validate_target(root, expected, state["distributionClass"])
        for expected in state["targets"]
    ]
    validate_archived_target_manifest(root, state.get("targetManifestSha256"))
    validate_aggregate(args.status, targets)
    executed = any(target.get("routeId") is not None for target in targets)
    validate_environment(
        root,
        executed,
        [target["engine"] for target in targets if target.get("engine") is not None],
    )
    validate_resources(root, executed)
    scan_sensitive_content(root)

    (root / "README.md").write_text(render_readme(state, args.status, targets), encoding="utf-8")
    (root / ".scirepro-staging.json").unlink()
    manifest = build_manifest(root, state, args.status, targets)
    write_json(root / "manifest.json", manifest)
    validate_final(root, allow_staging=True)
    final = root.parent / f"scirepro-run-{state['runId']}"
    atomic_publish(root, final)
    return final


def validate_inventory(root: Path, manifest: dict) -> None:
    expected = manifest.get("inventory")
    require(isinstance(expected, list), "manifest inventory must be an array")
    actual = build_inventory(root)
    require(actual == expected, "bundle inventory or a file hash has changed")


def validate_manifest_document(root: Path, manifest: dict, *, allow_staging: bool = False) -> None:
    require(manifest.get("schemaVersion") == BUNDLE_SCHEMA, "unsupported run-bundle schema")
    run_id = manifest.get("runId")
    require(isinstance(run_id, str) and RUN_ID.fullmatch(run_id), "invalid run ID")
    final_name = f"scirepro-run-{run_id}"
    allowed_names = {final_name}
    if allow_staging:
        allowed_names.add(f".{final_name}.staging")
    require(root.name in allowed_names, "final directory name does not match run ID")
    require(manifest.get("bundleId") == final_name, "bundle ID mismatch")
    require(manifest.get("status") in RUN_STATUSES, "invalid run status")
    require(manifest.get("distributionClass") in DISTRIBUTIONS, "invalid distribution")
    integrity = manifest.get("integrity")
    require(isinstance(integrity, dict), "manifest integrity is missing")
    require(integrity.get("algorithm") == "sha256", "manifest hash algorithm is invalid")
    require(integrity.get("canonicalization") == "json-sort-keys-v1", "manifest canonicalization is invalid")
    require(
        integrity.get("manifestSha256") == canonical_hash(manifest, "manifestSha256"),
        "manifest canonical hash mismatch",
    )
    targets = manifest.get("targets")
    require(isinstance(targets, list) and targets, "manifest has no targets")
    require(manifest.get("targetCount") == len(targets), "targetCount mismatch")
    validate_archived_target_manifest(root, manifest.get("targetManifestSha256"))
    scan_sensitive_content(root)
    validate_environment(
        root,
        any(item.get("routeId") is not None for item in targets),
        [item["engine"] for item in targets if item.get("engine") is not None],
    )
    validate_resources(root, any(item.get("routeId") is not None for item in targets))
    rebuilt = []
    for summary in targets:
        expected = {
            "targetId": summary.get("targetId"),
            "workflowMode": summary.get("workflowMode"),
            "targetSha256": summary.get("targetSha256"),
        }
        rebuilt.append(validate_target(root, expected, manifest["distributionClass"]))
    require(rebuilt == targets, "manifest target summaries differ from result records")
    validate_aggregate(manifest["status"], rebuilt)
    validate_inventory(root, manifest)


def validate_final(root: Path, *, allow_staging: bool = False) -> None:
    top_level = {path.name for path in root.iterdir()}
    require(top_level <= ALLOWED_TOP_LEVEL, "unexpected top-level content")
    require(".scirepro-staging.json" not in top_level, "staging state leaked into final bundle")
    manifest = read_json(root / "manifest.json", "run manifest")
    validate_manifest_document(root, manifest, allow_staging=allow_staging)


def validate_bundle(args: argparse.Namespace) -> Path:
    root = checked_directory(args.bundle, "run bundle")
    validate_final(root)
    return root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="create a report-free staging result folder")
    initialize.add_argument(
        "--parent", "--output-root", dest="parent", type=Path, default=Path.cwd(),
        help="parent for the single scirepro-run-<run-id> folder",
    )
    initialize.add_argument("--run-id", required=True)
    initialize.add_argument("--target", action="append", default=[], metavar="ID[=MODE]")
    initialize.add_argument("--default-mode", choices=sorted(WORKFLOW_MODES), default="scientific-reproduction")
    initialize.add_argument("--distribution", choices=sorted(DISTRIBUTIONS), default="local-private")
    initialize.add_argument("--target-manifest", type=Path)
    initialize.add_argument("--json", action="store_true")

    finalize = commands.add_parser("finalize", help="validate and atomically publish the final folder")
    finalize.add_argument("--bundle", type=Path, required=True)
    finalize.add_argument("--status", choices=sorted(RUN_STATUSES), required=True)
    finalize.add_argument("--json", action="store_true")

    validate = commands.add_parser("validate", help="verify hashes, traceability, rights, and inventory")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--json", action="store_true")
    return parser


def emit(path: Path, status: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"path": str(path), "status": status}, ensure_ascii=False, sort_keys=True))
    else:
        print(path)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "init":
            emit(initialize_bundle(args), "staging", args.json)
        elif args.command == "finalize":
            emit(finalize_bundle(args), args.status, args.json)
        else:
            emit(validate_bundle(args), "valid", args.json)
    except (BundleError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
