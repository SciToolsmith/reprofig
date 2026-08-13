#!/usr/bin/env python3
"""Create, finalize, and validate one portable SciRepro run bundle.

The command owns the outer bundle directory and its machine-readable manifest.
Reproduction code may write only inside the staging directory returned by
``init``.  ``finalize`` inventories the result, validates it, then atomically
renames the staging directory to its terminal ``scirepro-run-<run-id>`` name.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import html
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from build_report import ReportError as PhaseOneReportError
from build_report import canonical_payload as canonical_report_payload
from build_report import require_secret_free
from build_report import validate_report as validate_phase_one_report
from materialize_target_figures import TargetError as PhaseZeroTargetError
from materialize_target_figures import validate_manifest as validate_phase_zero_manifest


BUNDLE_SCHEMA = "scirepro.run-bundle/v2"
STAGING_SCHEMA = "scirepro.run-bundle-staging/v2"
TARGET_RESULT_SCHEMA = "scirepro.target-result/v2"
VALIDATION_SCHEMA = "scirepro.validation-summary/v2"
SOURCES_SCHEMA = "scirepro.sources/v1"
ENVIRONMENT_SCHEMA = "scirepro.environment/v1"
RESOURCE_SCHEMA = "scirepro.resource-usage/v1"
OMISSIONS_SCHEMA = "scirepro.omissions/v1"
RESULT_REPORT_SCHEMA = "scirepro.result-report/v2"
ADJUSTMENTS_SCHEMA = "scirepro.adjustments/v2"
DIFFERENCE_SUMMARY_SCHEMA = "scirepro.difference-summary/v2"
VISUAL_QUALITY_SCHEMA = "scirepro.visual-quality-check/v2"
CALIBRATION_APPROVAL_SCHEMA = "scirepro.calibration-approval/v2"

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RUN_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
RUN_STATUSES = {"complete", "partial", "failed", "blocked", "cancelled"}
TARGET_STATUSES = RUN_STATUSES | {"pending"}
VALIDATION_STATUSES = {
    "passed",
    "partially-passed",
    "failed",
    "inconclusive",
    "not-run",
}
CLAIM_STATUSES = {
    "supported",
    "partially-supported",
    "unsupported",
    "inconclusive",
    "not-tested",
    "not-applicable",
}
WORKFLOW_MODES = {"scientific-reproduction", "image-derived-reconstruction"}
DISTRIBUTION_CLASSES = {"local-private", "shareable"}
PLAN_INPUTS = {
    "report": "shared/plan/report.json",
    "target_manifest": "shared/plan/target-manifest.json",
    "approval": "shared/plan/approval.json",
    "gate_result": "shared/plan/gate-result.json",
}
REQUIRED_SHARED = {
    "shared/provenance/sources.json": SOURCES_SCHEMA,
    "shared/environment/environment.json": ENVIRONMENT_SCHEMA,
    "shared/execution/resource-usage.json": RESOURCE_SCHEMA,
}
ALLOWED_TOP_LEVEL = {"README.md", "manifest.json", "report", "shared", "targets"}
SENSITIVE_NAME = re.compile(
    r"(?i)^(?:\.env(?:\..*)?|id_[rd]sa(?:\.pub)?|credentials?(?:\..*)?|secrets?(?:\..*)?|tokens?(?:\..*)?|.*private[_-]?key.*)$"
)
SENSITIVE_VALUE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|cookie|credential|password|private[_-]?key|secret|session|token)"
    r"\s*[=:]\s*[\"']?[^\s\"']{8,}"
)
PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----")
LOCAL_PATH = re.compile(
    r"(?:^|[\s\"'=:(])(?:/(?:Users|home|private|tmp|var/folders|Volumes|root)/[^\s\"'<>]*|[A-Za-z]:[\\/](?:Users|Temp)[\\/][^\s\"'<>]*)"
)
TEXT_SUFFIXES = {
    ".css", ".csv", ".html", ".ini", ".js", ".json", ".jsonl", ".log", ".m", ".md",
    ".py", ".r", ".sh", ".svg", ".toml", ".tsv", ".txt", ".yaml", ".yml",
}
MEDIA_TYPES = {
    ".csv": "text/csv",
    ".css": "text/css",
    ".html": "text/html",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "text/javascript",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".log": "text/plain",
    ".md": "text/markdown",
    ".m": "text/plain",
    ".npz": "application/octet-stream",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".py": "text/x-python",
    ".svg": "image/svg+xml",
    ".toml": "application/toml",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}

DECISION_REPORT_REQUIRED = {
    "index.html", "app.js", "styles.css", "report-data.js", "report.json", "manifest.json",
}
RESULT_IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".svg", ".webp"}
FIGURE_ARTIFACT_SUFFIXES = RESULT_IMAGE_SUFFIXES
SCIENTIFIC_CHANGE_DOMAINS = {
    "input", "data", "formula", "preprocessing", "algorithm", "parameter",
    "randomization", "numerical", "axis-scale", "unit-conversion", "range-selection",
}
PRESENTATION_CHANGE_DOMAINS = {
    "axis-label", "tick-format", "palette", "line-style", "marker-style", "legend",
    "typography", "layout", "export", "overlap", "contrast", "readability",
}
COMPARISON_MODES = {"side-by-side", "metrics-only"}
DIRECT_MISCONDUCT_ALLEGATION = re.compile(
    r"(?i)(?:"
    r"(?:authors?|researchers?|paper|study)\s+(?:have\s+|has\s+|committed\s+)?"
    r"(?:fabricated|falsified|manipulated|committed\s+(?:fraud|misconduct))"
    r"|(?:proves?|demonstrates?|confirms?|establishes?)\s+(?:research\s+)?(?:fraud|misconduct|fabrication|falsification)"
    r"|(?:作者|研究者|论文|研究)\s*(?:存在|涉嫌|已经|被证实|有)?\s*(?:造假|伪造|篡改|学术不端)"
    r"|(?:证明|证实|确认|表明)\s*(?:了|存在|作者|研究者|论文|研究)?\s*(?:造假|伪造|篡改|学术不端)"
    r")"
)


class BundleError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleError(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: object, field: str) -> datetime:
    require(isinstance(value, str) and value, f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BundleError(f"{field} must be an ISO-8601 timestamp") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def safe_relative(value: str) -> bool:
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


def exists_lstat(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def atomic_publish_directory(source: Path, destination: Path) -> None:
    """Rename ``source`` without intentionally replacing ``destination``.

    The adjacent exclusive lock closes races between cooperating SciRepro
    processes. ``os.rename`` is deliberately used instead of ``os.replace``;
    the latter would silently destroy an empty destination directory on some
    platforms. A failed publish leaves the source directory in place.
    """
    lock = destination.parent / f"{destination.name}.publish.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise BundleError(f"another publish is in progress or left a lock: {lock}") from exc
    published = False
    try:
        require(not exists_lstat(destination), f"destination already exists: {destination}")
        rename_directory_no_replace(source, destination)
        published = True
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # The directory publication itself is authoritative. A stale
            # advisory lock must not turn a successful atomic rename into an
            # apparent failure.
            if not published:
                raise


def rename_directory_no_replace(source: Path, destination: Path) -> None:
    """Use the platform's atomic no-replace rename when it is available."""
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        renamex_np = libc.renamex_np
        renamex_np.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        renamex_np.restype = ctypes.c_int
        # <stdio.h>: RENAME_EXCL prevents replacement of an existing object.
        result = renamex_np(source_bytes, destination_bytes, 0x00000004)
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        renameat2 = libc.renameat2
        renameat2.argtypes = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, source_bytes, -100, destination_bytes, 0x00000001)
    else:
        # Windows already gives os.rename no-replace behavior. The remaining
        # fallback is protected from cooperating writers by the lock above.
        os.rename(source, destination)
        return
    if result != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise BundleError(f"destination already exists: {destination}")
        raise OSError(code, os.strerror(code), str(destination))


def checked_existing_directory(raw: Path, purpose: str) -> Path:
    expanded = raw.expanduser()
    absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
    # Resolve ordinary platform aliases such as macOS /tmp -> /private/tmp.  The
    # bundle itself is scanned with lstat below, so no symlink can survive in it.
    try:
        mode = absolute.lstat().st_mode
    except FileNotFoundError as exc:
        raise BundleError(f"{purpose} does not exist: {absolute}") from exc
    require(not stat.S_ISLNK(mode), f"{purpose} may not itself be a symlink: {absolute}")
    require(stat.S_ISDIR(mode), f"{purpose} is not a directory: {absolute}")
    return absolute.resolve(strict=True)


def approved_descendant_directory(
    workspace: Path,
    relative: str,
    purpose: str,
    *,
    create: bool,
) -> Path:
    """Resolve/create an approval-bound directory without following symlinks.

    ``relative`` has already passed ``safe_relative``.  Every existing
    component below the trusted, resolved workspace is inspected with lstat.
    Creation is one component at a time and each new component is checked
    before it becomes the parent of the next one.
    """
    current = workspace
    missing_parent = False
    for part in PurePosixPath(relative).parts:
        candidate = current / part
        if missing_parent and not create:
            current = candidate
            continue
        try:
            mode = candidate.lstat().st_mode
        except FileNotFoundError:
            if not create:
                missing_parent = True
                current = candidate
                continue
            try:
                candidate.mkdir()
            except FileExistsError:
                pass
            try:
                mode = candidate.lstat().st_mode
            except FileNotFoundError as exc:
                raise BundleError(f"{purpose} disappeared during creation: {candidate}") from exc
        require(not stat.S_ISLNK(mode), f"{purpose} contains a symlinked component: {candidate}")
        require(stat.S_ISDIR(mode), f"{purpose} component is not a directory: {candidate}")
        current = candidate
    return current


def checked_regular_file(raw: Path, purpose: str) -> Path:
    expanded = raw.expanduser()
    absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
    try:
        mode = absolute.lstat().st_mode
    except FileNotFoundError as exc:
        raise BundleError(f"{purpose} does not exist: {absolute}") from exc
    require(stat.S_ISREG(mode), f"{purpose} is not a regular non-symlink file: {absolute}")
    return absolute.resolve(strict=True)


def scan_tree(root: Path) -> tuple[list[Path], list[Path]]:
    """Return regular files/directories after an lstat-only, no-follow walk.

    This must run before opening any bundle member. A FIFO presented where JSON
    is expected must fail rather than block the process on read.
    """
    files: list[Path] = []
    directories: list[Path] = [root]
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise BundleError(f"cannot scan bundle directory: {directory}") from exc
        for entry in entries:
            candidate = Path(entry.path)
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                raise BundleError(f"cannot inspect bundle member: {candidate}") from exc
            relative = candidate.relative_to(root).as_posix()
            require(safe_relative(relative), f"unsafe bundle-relative path: {relative}")
            require(not stat.S_ISLNK(mode), f"bundle may not contain symlinks: {relative}")
            if stat.S_ISDIR(mode):
                directories.append(candidate)
                pending.append(candidate)
            elif stat.S_ISREG(mode):
                files.append(candidate)
            else:
                raise BundleError(f"bundle may contain only directories and regular files: {relative}")
    return sorted(files), sorted(directories)


def require_regular_member(path: Path, purpose: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise BundleError(f"{purpose} is missing: {path}") from exc
    require(stat.S_ISREG(mode), f"{purpose} must be a regular non-symlink file: {path}")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = pretty_json_bytes(value).decode("utf-8")
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def pretty_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_object(path: Path, purpose: str) -> dict:
    require_regular_member(path, purpose)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"{purpose} is not valid UTF-8 JSON: {path}") from exc
    require(isinstance(value, dict), f"{purpose} must be a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def approval_decision_payload(report: dict) -> dict:
    """Return the audience-neutral part of a Phase 1 decision report.

    Execution approval binds the exact local report.  A shareable run bundle,
    however, must contain a separately built public report whose target pixels
    may be omitted.  The builder changes only the fields normalized here when
    switching audiences; every scientific statement, route, parameter,
    assumption, cost, permission, and target binding remains covered.
    """
    clone = json.loads(json.dumps(report))
    clone.pop("audience", None)
    integrity = clone.get("integrity")
    if isinstance(integrity, dict):
        integrity["reportSha256"] = ""
    for figure in clone.get("figures", []):
        if not isinstance(figure, dict):
            continue
        target = figure.get("target")
        if isinstance(target, dict):
            materialization = target.get("materialization")
            target["requestedRef"] = (
                materialization.get("figureReference") if isinstance(materialization, dict) else None
            ) or target.get("targetId")
            if isinstance(materialization, dict):
                materialization["sourceFileName"] = None
        image = figure.get("image")
        if isinstance(image, dict):
            for field in (
                "bundleState", "relativePath", "sizeBytes", "sha256",
                "metadataStripped", "displayProxy",
            ):
                image.pop(field, None)
    return clone


def approval_decision_hash(report: dict) -> str:
    return canonical_hash(approval_decision_payload(report))


def canonical_embedded_hash(value: dict, container: str, field: str) -> str:
    clone = json.loads(json.dumps(value))
    require(isinstance(clone.get(container), dict), f"{container} must be an object")
    clone[container][field] = ""
    return canonical_hash(clone)


def manifest_self_hash(manifest: dict) -> str:
    clone = json.loads(json.dumps(manifest))
    clone.setdefault("integrity", {})["manifestSha256"] = ""
    return canonical_hash(clone)


def validate_built_decision_report(
    root: Path,
    *,
    expected_report_sha256: str | None,
    distribution_class: str,
    approved_report: dict | None = None,
) -> dict:
    """Validate an immutable Phase 1 web bundle before it enters a run report."""
    files, _ = scan_tree(root)
    actual = {path.relative_to(root).as_posix(): path for path in files}
    missing = DECISION_REPORT_REQUIRED - set(actual)
    require(not missing, f"result-report source is missing: {', '.join(sorted(missing))}")

    bundle_manifest = read_object(root / "manifest.json", "decision-report manifest")
    require(bundle_manifest.get("schemaVersion") == "reprofig.bundle/v1", "unsupported decision-report bundle schema")
    declared = bundle_manifest.get("files")
    require(isinstance(declared, list), "decision-report manifest files must be an array")
    declared_paths: set[str] = set()
    for index, entry in enumerate(declared):
        require(isinstance(entry, dict), f"decision-report manifest files[{index}] must be an object")
        relative = entry.get("path")
        require(isinstance(relative, str) and safe_relative(relative), f"unsafe decision-report path: {relative!r}")
        require(relative not in declared_paths and relative != "manifest.json", f"duplicate decision-report path: {relative}")
        declared_paths.add(relative)
        require(relative in actual, f"decision-report file is missing: {relative}")
        path = actual[relative]
        require(entry.get("sizeBytes") == path.stat().st_size, f"decision-report size mismatch: {relative}")
        require(entry.get("sha256") == sha256_file(path), f"decision-report hash mismatch: {relative}")
    require(declared_paths == set(actual) - {"manifest.json"}, "decision-report manifest does not exactly inventory its files")

    report = read_object(root / "report.json", "decision-report JSON")
    try:
        validate_phase_one_report(report, allow_built_assets=True)
    except PhaseOneReportError as exc:
        raise BundleError(f"invalid decision-report JSON: {exc}") from exc
    report_hash = hashlib.sha256(canonical_report_payload(report)).hexdigest()
    require(report.get("integrity", {}).get("reportSha256") == report_hash, "decision-report integrity hash mismatch")
    require(bundle_manifest.get("reportId") == report.get("reportId"), "decision-report ID mismatch")
    require(bundle_manifest.get("reportSha256") == report_hash, "decision-report manifest hash mismatch")
    expected_audience = "local" if distribution_class == "local-private" else "public"
    require(
        report.get("audience") == expected_audience and bundle_manifest.get("audience") == expected_audience,
        f"{distribution_class} result bundle requires a {expected_audience} decision report",
    )
    if expected_report_sha256 is not None:
        if distribution_class == "local-private":
            require(report_hash == expected_report_sha256, "result-report source is not the approved Phase 1 report")
        else:
            require(approved_report is not None, "shareable result report requires the archived approved local report")
            try:
                validate_phase_one_report(approved_report, allow_built_assets=True)
            except PhaseOneReportError as exc:
                raise BundleError(f"invalid archived approved report: {exc}") from exc
            approved_hash = hashlib.sha256(canonical_report_payload(approved_report)).hexdigest()
            require(
                approved_report.get("audience") == "local"
                and approved_report.get("integrity", {}).get("reportSha256") == approved_hash
                and approved_hash == expected_report_sha256,
                "shareable result report is not derived from the exact approved local report",
            )
            require(
                approval_decision_hash(report) == approval_decision_hash(approved_report),
                "shareable result report decision content differs from the approved local report",
            )
    return report


def make_result_report_summary(
    root: Path,
    *,
    bundle_id: str,
    status: str,
    finalized_at: str,
    report_sha256: str | None,
    distribution_class: str,
) -> dict:
    targets = []
    for record in target_records(root, distribution_class=distribution_class):
        result = read_object(root / record["resultPath"], f"{record['targetId']} result")
        validation = read_object(root / record["validationPath"], f"{record['targetId']} validation")
        calibration = result.get("calibration")
        calibration_details = None
        if isinstance(calibration, dict):
            calibration_details = {
                "comparisons": calibration["comparisons"],
                "difference": read_object(root / calibration["differenceSummary"], "difference summary"),
                "visualQuality": read_object(root / calibration["visualQualityCheck"], "visual quality check"),
                "adjustments": read_object(root / calibration["adjustments"], "adjustments"),
            }
        reference = f"targets/{record['targetId']}/reference/target.png"
        targets.append(
            {
                "targetId": record["targetId"],
                "workflowMode": record["workflowMode"],
                "targetSha256": record["targetSha256"],
                "routeId": record["routeId"],
                "operationalStatus": record["operationalStatus"],
                "validationStatus": record["validationStatus"],
                "claimStatus": record["claimStatus"],
                "summary": result["summary"],
                "validationSummary": validation["summary"],
                "reference": reference if (root / reference).is_file() else None,
                "outputs": result["outputs"],
                "validationArtifacts": validation.get("artifacts", []),
                "calibration": calibration,
                "calibrationDetails": calibration_details,
            }
        )
    return {
        "schemaVersion": RESULT_REPORT_SCHEMA,
        "bundleId": bundle_id,
        "status": status,
        "finalizedAt": finalized_at,
        "decisionReportSha256": report_sha256,
        "targets": targets,
    }


def decision_report_hash(root: Path, plan_bindings: dict) -> str | None:
    bound = plan_bindings.get("reportSha256")
    if bound is not None:
        return bound
    archived = root / PLAN_INPUTS["report"]
    if archived.is_file():
        report = read_object(archived, "archived report")
        value = report.get("integrity", {}).get("reportSha256")
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "archived report hash is invalid")
        return value
    return None


def archived_approved_report(root: Path) -> dict | None:
    path = root / PLAN_INPUTS["report"]
    return read_object(path, "archived approved report") if path.is_file() else None


def result_report_html(summary: dict) -> bytes:
    summary_hash = hashlib.sha256(pretty_json_bytes(summary)).hexdigest()
    cards = []
    for target in summary["targets"]:
        target_id = html.escape(target["targetId"])
        status = html.escape(target["operationalStatus"])
        media = []
        rendered_media: set[str] = set()

        def add_media(relative: str, label: str, alt: str) -> None:
            if relative in rendered_media or PurePosixPath(relative).suffix.lower() not in RESULT_IMAGE_SUFFIXES:
                return
            rendered_media.add(relative)
            href = "../" + relative
            media.append(
                f'<figure><a href="{html.escape(href, quote=True)}"><img src="{html.escape(href, quote=True)}" '
                f'alt="{html.escape(alt, quote=True)}"></a><figcaption>{html.escape(label)}</figcaption></figure>'
            )

        reference = target.get("reference")
        if reference:
            add_media(reference, "Published target / 目标图", f"Published target {target_id}")
        calibration = target.get("calibration") or {}
        version_roles = (
            (calibration.get("baselineV0"), "V0 · untuned baseline / 未调参基线"),
            (calibration.get("scientificV1"), "V1 · scientific correction / 科学修正"),
            (calibration.get("presentationV2"), "V2 · presentation quality / 表达与质量修正"),
        )
        for relative, label in version_roles:
            if isinstance(relative, str):
                add_media(relative, label, label)
        details = target.get("calibrationDetails") or {}
        for comparison in details.get("comparisons", []):
            mode_label = "side-by-side / 并排" if comparison["mode"] == "side-by-side" else "metrics-only / 仅指标"
            add_media(
                comparison["artifact"],
                f'{comparison["comparisonId"]} · {mode_label}',
                f'{comparison["comparisonId"]} comparison',
            )
        for relative in target.get("outputs", []):
            label = PurePosixPath(relative).name
            if re.fullmatch(r"calibrated-v(?:[3-9]|[1-9][0-9]+)", PurePosixPath(relative).stem):
                label += " · approved scientific hypothesis / 已批准科学假设"
            else:
                label += " · generated artifact / 生成成果"
            add_media(relative, label, label)
        for relative in target.get("validationArtifacts", []):
            add_media(relative, f"{PurePosixPath(relative).name} · validation artifact / 验证成果", relative)
        artifacts = []
        for relative in target.get("outputs", []) + target.get("validationArtifacts", []):
            href = "../" + relative
            artifacts.append(f'<li><a href="{html.escape(href, quote=True)}">{html.escape(relative)}</a></li>')
        artifact_html = "<ul>" + "".join(dict.fromkeys(artifacts)) + "</ul>" if artifacts else "<p>None recorded.</p>"
        selected_output = calibration.get("selectedOutput")
        calibration_html = ""
        if isinstance(selected_output, str) and details:
            difference = details["difference"]
            quality = details["visualQuality"]
            adjustments = details["adjustments"]
            dimension_labels = {
                "axesUnitsScale": "Axes, units, scale / 坐标轴、单位、尺度",
                "trendsPeaksMagnitude": "Trends, peaks, magnitude / 趋势、峰值、量级",
                "colorsLinesLegends": "Colors, lines, legends / 配色、线型、图例",
                "layoutTypography": "Layout, typography / 布局、文字",
            }
            dimension_html = "".join(
                f'<li><strong>{html.escape(dimension_labels[key])}:</strong> {html.escape(difference["dimensions"][key])}</li>'
                for key in dimension_labels
            )
            issues = quality["issuesRemaining"]
            issues_html = "".join(f"<li>{html.escape(item)}</li>" for item in issues) or "<li>None / 无</li>"
            round_rows = []
            for record in adjustments["rounds"]:
                changes = "; ".join(
                    f'{change["changeDomain"]}: {change["subject"]}' for change in record["changes"]
                )
                round_rows.append(
                    f'<tr><td>V{record["round"]}</td><td>{html.escape(record["kind"])}</td>'
                    f'<td>{html.escape(changes)}</td><td>{html.escape(record["rationale"])}</td></tr>'
                )
            rounds_html = (
                '<table><thead><tr><th>Round</th><th>Type</th><th>Changes</th><th>Rationale</th></tr></thead>'
                f'<tbody>{"".join(round_rows)}</tbody></table>'
                if round_rows else '<p>No adjustment round was needed / 无需调整轮次。</p>'
            )
            calibration_html = f'''
<section class="calibration"><h3>Comparison and bounded calibration / 对比与有界校准</h3>
<p><strong>Selected figure / 选定图件:</strong> {html.escape(selected_output)}</p>
<p class="conclusion"><strong>Scientific conclusion / 科学结论:</strong> {html.escape(difference["scientificConclusion"])}</p>
<ul>{dimension_html}</ul>
<div class="quality"><strong>Visual QA / 视觉质检:</strong> {html.escape(quality["status"])}<ul>{issues_html}</ul></div>
{rounds_html}<p><strong>Stop reason / 停止原因:</strong> {html.escape(adjustments["stopReason"])}</p></section>'''
        cards.append(
            f'''<article class="target-card">
<header><div><p class="eyebrow">Target</p><h2>{target_id}</h2></div><span class="status">{status}</span></header>
<dl><div><dt>Validation</dt><dd>{html.escape(target["validationStatus"])}</dd></div>
<div><dt>Claim</dt><dd>{html.escape(target["claimStatus"])}</dd></div>
<div><dt>Mode</dt><dd>{html.escape(target["workflowMode"])}</dd></div></dl>
<p>{html.escape(target["summary"])}</p><p class="validation">{html.escape(target["validationSummary"])}</p>
<div class="media">{"".join(media)}</div>{calibration_html}<h3>Artifacts / 成果文件</h3>{artifact_html}
</article>'''
        )
    document = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="scirepro-result-sha256" content="{summary_hash}"><title>SciRepro result · {html.escape(summary["bundleId"])}</title>
<style>
:root{{--ink:#172033;--muted:#64748b;--line:#dce3ec;--paper:#fff;--wash:#f5f7fb;--accent:#1463df}}*{{box-sizing:border-box}}
body{{margin:0;background:var(--wash);color:var(--ink);font:15px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{width:min(1100px,calc(100% - 32px));margin:36px auto 72px}}.hero{{background:#101a31;color:#fff;border-radius:20px;padding:28px 32px}}
.hero p{{color:#c7d2e6;margin:.4rem 0}}.hero a{{color:#8fc1ff}}h1{{margin:0;font-size:clamp(28px,4vw,48px)}}.eyebrow{{margin:0;color:#5796ff;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}}
.target-card{{margin-top:18px;background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:24px;box-shadow:0 8px 24px #26334d0d}}
.target-card header{{display:flex;justify-content:space-between;gap:16px;align-items:start}}h2{{margin:.15rem 0 0}}.status{{padding:5px 10px;border-radius:999px;background:#e9f2ff;color:#0757c6;font-weight:700}}
dl{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:20px 0}}dl div{{background:var(--wash);border-radius:10px;padding:10px}}dt{{color:var(--muted);font-size:12px}}dd{{margin:0;font-weight:650;overflow-wrap:anywhere}}
.validation{{border-left:3px solid var(--accent);padding-left:12px;color:#334155}}.media{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}figure{{margin:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff}}figure img{{display:block;width:100%;max-height:420px;object-fit:contain;background:#f8fafc}}figcaption{{padding:8px 10px;color:var(--muted)}}.calibration{{margin:20px 0;padding:18px;border-radius:12px;background:#f8fafc;border:1px solid var(--line)}}.conclusion{{border-left:3px solid #14804a;padding-left:12px}}table{{width:100%;border-collapse:collapse;margin:12px 0}}th,td{{padding:8px;border:1px solid var(--line);text-align:left;vertical-align:top}}a{{color:#0757c6}}@media(max-width:650px){{main{{width:min(100% - 20px,1100px);margin-top:10px}}.hero,.target-card{{border-radius:12px;padding:18px}}dl{{grid-template-columns:1fr}}table{{display:block;overflow-x:auto}}}}
</style></head><body><main><section class="hero"><p class="eyebrow">SciRepro · Phase 2</p><h1>复现结果 / Run result</h1>
<p><strong>{html.escape(summary["bundleId"])}</strong> · {html.escape(summary["status"])}</p>
<p>执行、验收与论文主张分别记录。<a href="decision/index.html">查看执行前研判报告 / Open decision report</a></p></section>
{"".join(cards)}</main></body></html>'''
    return document.encode("utf-8")


def write_result_report(root: Path, summary: dict) -> None:
    write_json(root / "report/run-results.json", summary)
    write_bytes(root / "report/index.html", result_report_html(summary))


def validate_result_report(root: Path, manifest: dict) -> None:
    report_root = root / "report"
    require(report_root.is_dir() and not report_root.is_symlink(), "bundle is missing the final local result report")
    require_regular_member(report_root / "index.html", "result-report index")
    stored = read_object(report_root / "run-results.json", "result-report summary")
    report_hash = decision_report_hash(root, manifest.get("planBindings", {}))
    expected = make_result_report_summary(
        root,
        bundle_id=manifest["bundleId"],
        status=manifest["status"],
        finalized_at=manifest["finalizedAt"],
        report_sha256=report_hash,
        distribution_class=manifest["rights"]["distributionClass"],
    )
    require(stored == expected, "result-report summary does not match terminal target results")
    require((report_root / "index.html").read_bytes() == result_report_html(stored), "result-report HTML does not match its result summary")
    validate_built_decision_report(
        report_root / "decision",
        expected_report_sha256=report_hash,
        distribution_class=manifest["rights"]["distributionClass"],
        approved_report=archived_approved_report(root),
    )


def parse_target_spec(value: str, default_mode: str) -> tuple[str, str]:
    if "=" in value:
        target_id, mode = value.split("=", 1)
    else:
        target_id, mode = value, default_mode
    require(bool(IDENTIFIER.fullmatch(target_id)), f"unsafe target ID: {target_id!r}")
    require(mode in WORKFLOW_MODES, f"unsupported workflow mode for {target_id}: {mode}")
    return target_id, mode


def validate_plan_inputs(args: argparse.Namespace) -> dict:
    require(args.report is None or args.target_manifest is not None, "--report requires --target-manifest")
    require(args.approval is None or args.report is not None, "--approval requires --report and --target-manifest")
    require(args.gate_result is None or args.approval is not None, "--gate-result requires --approval")
    context: dict = {
        "manifest": None,
        "manifestPath": None,
        "targets": {},
        "report": None,
        "approval": None,
        "gate": None,
        "approvedTargetIds": None,
    }

    if args.target_manifest is not None:
        path = checked_regular_file(args.target_manifest, "target manifest")
        value = read_object(path, "target manifest")
        try:
            targets = validate_phase_zero_manifest(value, root=path.parent, require_verified=True)
        except PhaseZeroTargetError as exc:
            raise BundleError(f"invalid verified Phase 0 target manifest: {exc}") from exc
        context.update({"manifest": value, "manifestPath": path, "targets": targets})

    if args.report is not None:
        path = checked_regular_file(args.report, "report")
        report = read_object(path, "report")
        try:
            validate_phase_one_report(report, allow_built_assets=True)
        except PhaseOneReportError as exc:
            raise BundleError(f"invalid Phase 1 report: {exc}") from exc
        expected_report_hash = hashlib.sha256(canonical_report_payload(report)).hexdigest()
        require(
            report.get("integrity", {}).get("reportSha256") == expected_report_hash,
            "Phase 1 report integrity hash mismatch",
        )
        manifest = context["manifest"]
        targets = context["targets"]
        report_set = report.get("targetSet", {})
        require(report_set.get("targetSetId") == manifest.get("targetSetId"), "report/manifest targetSetId mismatch")
        require(
            report_set.get("manifestSha256") == manifest.get("integrity", {}).get("manifestSha256"),
            "report/manifest hash mismatch",
        )
        report_targets: dict[str, dict] = {}
        for figure in report.get("figures", []):
            target = figure.get("target", {})
            target_id = target.get("targetId")
            require(target_id in targets and target_id not in report_targets, "report target scope differs from manifest")
            source = targets[target_id]
            require(target.get("workflowMode") == source.get("workflowMode"), f"{target_id}: report workflow mode mismatch")
            require(target.get("acquisitionMode") == source.get("acquisitionMode"), f"{target_id}: report acquisition mode mismatch")
            require(target.get("targetSha256") == source.get("targetSha256"), f"{target_id}: report target hash mismatch")
            require(
                target.get("materialization", {}).get("qaStatus") == "verified",
                f"{target_id}: report target is not verified",
            )
            report_targets[target_id] = figure
        require(set(report_targets) == set(targets), "report must bind the complete verified target manifest")
        context.update({"report": report, "reportPath": path, "reportTargets": report_targets})

    if args.approval is not None:
        approval_path = checked_regular_file(args.approval, "approval")
        approval = read_object(approval_path, "approval")
        gate_script = Path(__file__).resolve().with_name("plan_gate.py")
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(gate_script),
                    "--report",
                    str(context["reportPath"]),
                    "--approval",
                    str(approval_path),
                    "--target-manifest",
                    str(context["manifestPath"]),
                ],
                text=True,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BundleError("could not run the bounded Phase 2 approval gate") from exc
        require(completed.returncode == 0, f"approval gate rejected the plan: {completed.stderr.strip()[:512]}")
        try:
            authoritative_gate = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise BundleError("approval gate returned malformed JSON") from exc
        require(isinstance(authoritative_gate, dict) and authoritative_gate.get("status") == "valid", "approval gate did not return valid status")
        require(authoritative_gate.get("schemaVersion") == "scirepro.gate-result/v1", "approval gate returned a legacy result contract")
        approval_digest = sha256_file(approval_path)
        require(authoritative_gate.get("approvalSha256") == approval_digest, "approval gate did not bind exact approval bytes")
        require(authoritative_gate.get("outputPolicy") == approval.get("outputPolicy"), "approval gate output policy mismatch")
        selected_target_records = authoritative_gate.get("selectedTargets")
        require(isinstance(selected_target_records, list) and selected_target_records, "approval gate omitted selected target bindings")
        if args.gate_result is not None:
            supplied_gate = read_object(checked_regular_file(args.gate_result, "gate result"), "gate result")
            require(supplied_gate == authoritative_gate, "supplied gate result does not match a fresh approval validation")
        approved_target_ids = []
        for binding in selected_target_records:
            require(isinstance(binding, dict), "approval gate selected target must be an object")
            target_id = binding.get("targetId")
            require(target_id in context["targets"] and target_id not in approved_target_ids, "approval gate selected target scope is invalid")
            target = context["targets"][target_id]
            require(binding.get("targetSha256") == target["targetSha256"], f"{target_id}: gate target hash mismatch")
            require(binding.get("workflowMode") == target["workflowMode"], f"{target_id}: gate workflow mode mismatch")
            approved_target_ids.append(target_id)
        context.update(
            {
                "approval": approval,
                "approvalPath": approval_path,
                "gate": authoritative_gate,
                "approvedTargetIds": approved_target_ids,
            }
        )
    return context


def selected_targets(args: argparse.Namespace, context: dict) -> list[tuple[str, str]]:
    available = {target_id: target["workflowMode"] for target_id, target in context["targets"].items()}
    approved = context.get("approvedTargetIds")
    default_ids = approved if approved is not None else list(available)
    if not args.target:
        require(
            bool(default_ids),
            "provide at least one --target, or provide a target manifest/report containing targets",
        )
        return [(target_id, available[target_id]) for target_id in default_ids]

    selected = []
    for raw in args.target:
        explicit_mode = "=" in raw
        raw_id = raw.split("=", 1)[0]
        default_mode = available.get(raw_id, args.default_mode)
        target_id, mode = parse_target_spec(raw, default_mode)
        if available:
            require(target_id in available, f"selected target is absent from the supplied plan: {target_id}")
            if explicit_mode:
                require(mode == available[target_id], f"{target_id}: selected workflow mode disagrees with the supplied plan")
            mode = available[target_id]
        selected.append((target_id, mode))
    if approved is not None:
        require(
            [target_id for target_id, _ in selected] == approved,
            "run target order and scope must exactly match the fresh approval gate",
        )
    return selected


def initial_readme(run_id: str, target_ids: list[str], distribution_class: str) -> str:
    targets = "\n".join(f"- `{target_id}`" for target_id in target_ids)
    return f"""# SciRepro run `{run_id}`

**Status:** staging

**Distribution:** `{distribution_class}`

**Created:** {now_iso()}

## Targets

{targets}

## Result

<!-- scirepro-result:start -->
The run is still staging. Terminal target outcomes will be inserted here.
<!-- scirepro-result:end -->

## Re-run

Machine-readable commands, environment, sources, resource use, and per-target validation
live under `shared/` and `targets/`. If `shared/execution/commands.jsonl` is absent, no
verified replay command sequence was recorded.

## Limits

Inspect each `targets/<target-id>/result.json`, the validation summaries, source records,
and `shared/provenance/omissions.json` when present. Do not treat an image-derived
reconstruction as evidence for a paper claim.
"""


def initial_target_result(
    target_id: str,
    mode: str,
    *,
    target_sha256: str | None = None,
    route_id: str | None = None,
) -> dict:
    return {
        "schemaVersion": TARGET_RESULT_SCHEMA,
        "targetId": target_id,
        "workflowMode": mode,
        "targetSha256": target_sha256,
        "routeId": route_id,
        "operationalStatus": "pending",
        "claimStatus": "not-tested" if mode == "scientific-reproduction" else "not-applicable",
        "summary": "Run has not reached a terminal state.",
        "outputs": [],
        "calibration": None,
        "warnings": [],
        "errors": [],
    }


def initial_validation(target_id: str, mode: str) -> dict:
    return {
        "schemaVersion": VALIDATION_SCHEMA,
        "targetId": target_id,
        "workflowMode": mode,
        "status": "not-run",
        "summary": "Validation has not run.",
        "criteria": [],
        "metrics": [],
        "artifacts": [],
    }


def copy_plan_inputs(root: Path, context: dict) -> None:
    sources = {
        "report": context.get("reportPath"),
        "target_manifest": context.get("manifestPath"),
        "approval": context.get("approvalPath"),
    }
    for name, source in sources.items():
        if source is not None:
            destination = root / PLAN_INPUTS[name]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    if context.get("gate") is not None:
        write_json(root / PLAN_INPUTS["gate_result"], context["gate"])


def materialize_target_references(root: Path, context: dict, target_ids: list[str], distribution: str) -> None:
    sources: list[dict] = []
    omissions: list[dict] = []
    manifest_path = context.get("manifestPath")
    if manifest_path is None:
        write_json(root / "shared/provenance/sources.json", {"schemaVersion": SOURCES_SCHEMA, "sources": []})
        return
    for target_id in target_ids:
        target = context["targets"][target_id]
        source = checked_regular_file(manifest_path.parent / target["normalizedPath"], f"{target_id} normalized target")
        include = distribution == "local-private" or target.get("localAnalysisOnly") is False
        source_record = {
            "sourceId": f"phase0-{target_id}",
            "kind": "target-image",
            "title": f"Verified Phase 0 target {target_id}",
            "sha256": target["targetSha256"],
            "sizeBytes": source.stat().st_size,
            "redistributionStatus": (
                "local-only" if distribution == "local-private" else "permitted"
            ),
        }
        if include:
            relative = f"targets/{target_id}/reference/target.png"
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            require(sha256_file(destination) == target["targetSha256"], f"{target_id}: copied target hash mismatch")
            source_record["includedPath"] = relative
            sources.append(source_record)
        else:
            source_record["includedPath"] = None
            sources.append(source_record)
            omissions.append(
                {
                    "artifactId": f"phase0-{target_id}",
                    "kind": "target-image",
                    "sha256": target["targetSha256"],
                    "sizeBytes": source.stat().st_size,
                    "reason": "Phase 0 target is restricted to local analysis and cannot enter a shareable bundle.",
                    "locator": f"Phase 0 manifest normalizedPath: {target['normalizedPath']}",
                }
            )
    write_json(root / "shared/provenance/sources.json", {"schemaVersion": SOURCES_SCHEMA, "sources": sources})
    if omissions:
        write_json(
            root / "shared/provenance/omissions.json",
            {"schemaVersion": OMISSIONS_SCHEMA, "omissions": omissions},
        )


def initialize_bundle(args: argparse.Namespace) -> Path:
    require(bool(RUN_IDENTIFIER.fullmatch(args.run_id)), "run ID must be path-safe and at most 64 characters")
    context = validate_plan_inputs(args)
    requested_parent = args.parent.expanduser()
    requested_parent = requested_parent if requested_parent.is_absolute() else Path.cwd() / requested_parent
    if context.get("approval") is not None:
        require(args.workspace_root is not None, "--workspace-root is required with --approval")
        workspace = checked_existing_directory(args.workspace_root, "approval workspace root")
        relative_root = context["gate"].get("outputPolicy", {}).get("relativeRoot")
        require(isinstance(relative_root, str) and safe_relative(relative_root), "approval output root is unsafe")
        expected_parent = approved_descendant_directory(
            workspace, relative_root, "approval output root", create=False,
        )
        require(
            requested_parent.resolve(strict=False) == expected_parent,
            f"output root is not the approval-bound path: {expected_parent}",
        )
        parent = approved_descendant_directory(
            workspace, relative_root, "approval output root", create=True,
        )
        parent = checked_existing_directory(parent, "bundle parent")
    else:
        requested_parent.mkdir(parents=True, exist_ok=True)
        parent = checked_existing_directory(requested_parent, "bundle parent")
    parsed_targets = selected_targets(args, context)
    target_ids = [target_id for target_id, _ in parsed_targets]
    require(len(target_ids) == len(set(target_ids)), "target IDs must be unique")

    staging = parent / f".scirepro-run-{args.run_id}.staging"
    final = parent / f"scirepro-run-{args.run_id}"
    require(not staging.exists(), f"staging bundle already exists: {staging}")
    require(not final.exists(), f"final bundle already exists: {final}")

    temporary = Path(tempfile.mkdtemp(prefix=f".scirepro-run-{args.run_id}.init-", dir=parent))
    try:
        created_at = now_iso()
        (temporary / "README.md").write_text(
            initial_readme(args.run_id, target_ids, args.distribution), encoding="utf-8"
        )
        state = {
            "schemaVersion": STAGING_SCHEMA,
            "runId": args.run_id,
            "bundleId": f"scirepro-run-{args.run_id}",
            "createdAt": created_at,
            "distributionClass": args.distribution,
            "gateValidated": context.get("gate") is not None,
            "planBindings": {
                "reportSha256": (context.get("gate") or {}).get("reportSha256"),
                "targetManifestSha256": (
                    context.get("manifest", {}).get("integrity", {}).get("manifestSha256")
                    if context.get("manifest") is not None else None
                ),
                "approvalId": (context.get("gate") or {}).get("approvalId"),
                "approvalSha256": (context.get("gate") or {}).get("approvalSha256"),
                "gateResultSha256": (
                    hashlib.sha256(pretty_json_bytes(context["gate"])).hexdigest()
                    if context.get("gate") is not None else None
                ),
                "idempotencyKey": (context.get("gate") or {}).get("idempotencyKey"),
            },
            "targets": [
                {
                    "targetId": target_id,
                    "workflowMode": mode,
                    "targetSha256": context.get("targets", {}).get(target_id, {}).get("targetSha256"),
                }
                for target_id, mode in parsed_targets
            ],
        }
        write_json(temporary / ".scirepro-staging.json", state)
        materialize_target_references(temporary, context, target_ids, args.distribution)
        write_json(
            temporary / "shared/environment/environment.json",
            {
                "schemaVersion": ENVIRONMENT_SCHEMA,
                "captureStatus": "not-recorded",
                "runtime": {},
                "hardware": {},
                "notes": [],
            },
        )
        write_json(
            temporary / "shared/execution/resource-usage.json",
            {
                "schemaVersion": RESOURCE_SCHEMA,
                "measurementStatus": "not-recorded",
                "wallSeconds": None,
                "peakMemoryBytes": None,
                "diskBytes": None,
                "networkBytes": None,
                "cost": None,
            },
        )
        for target_id, mode in parsed_targets:
            gate_binding = next(
                (
                    item for item in (context.get("gate") or {}).get("selectedTargets", [])
                    if item.get("targetId") == target_id
                ),
                None,
            )
            write_json(
                temporary / "targets" / target_id / "result.json",
                initial_target_result(
                    target_id,
                    mode,
                    target_sha256=context.get("targets", {}).get(target_id, {}).get("targetSha256"),
                    route_id=(gate_binding or {}).get("routeId"),
                ),
            )
            write_json(
                temporary / "targets" / target_id / "validation" / "summary.json",
                initial_validation(target_id, mode),
            )
        copy_plan_inputs(temporary, context)
        atomic_publish_directory(temporary, staging)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return staging


def relative_files(
    root: Path,
    *,
    include_manifest: bool = False,
    include_staging_state: bool = False,
) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    scanned_files, _ = scan_tree(root)
    for candidate in scanned_files:
        relative = candidate.relative_to(root).as_posix()
        if not include_manifest and relative == "manifest.json":
            continue
        if not include_staging_state and relative == ".scirepro-staging.json":
            continue
        files.append((relative, candidate))
    return sorted(files)


def file_role(relative: str) -> str:
    if relative == "README.md":
        return "human-entry"
    if relative.startswith("report/"):
        return "report"
    if relative.startswith("shared/plan/"):
        return "approved-plan"
    if relative.startswith("shared/provenance/"):
        return "provenance"
    if relative.startswith("shared/environment/"):
        return "environment"
    if relative.startswith("shared/execution/"):
        return "execution-record"
    if relative.startswith("shared/code/") or "/code/" in relative:
        return "code"
    if relative.startswith("shared/config/"):
        return "configuration"
    if relative.endswith("/adjustments.json"):
        return "validation"
    if "/validation/" in relative:
        return "validation"
    if "/outputs/" in relative:
        return "output"
    if "/derived/" in relative:
        return "derived-data"
    return "artifact"


def inventory(root: Path) -> list[dict]:
    entries = []
    for relative, path in relative_files(root):
        media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
        entries.append(
            {
                "path": relative,
                "role": file_role(relative),
                "mediaType": media_type,
                "sizeBytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def target_records(
    root: Path,
    expected_targets: list[dict] | None = None,
    *,
    distribution_class: str = "local-private",
) -> list[dict]:
    targets_root = root / "targets"
    require(targets_root.exists(), "bundle is missing targets/")
    records = []
    for target_dir in sorted(targets_root.iterdir(), key=lambda item: item.name):
        require(target_dir.is_dir() and not target_dir.is_symlink(), f"invalid target directory: {target_dir}")
        target_id = target_dir.name
        require(bool(IDENTIFIER.fullmatch(target_id)), f"unsafe target directory name: {target_id}")
        result = read_object(target_dir / "result.json", f"{target_id} result")
        validation = read_object(target_dir / "validation/summary.json", f"{target_id} validation summary")
        validate_target_documents(
            root,
            target_id,
            result,
            validation,
            terminal=True,
            distribution_class=distribution_class,
        )
        records.append(
            {
                "targetId": target_id,
                "workflowMode": result["workflowMode"],
                "targetSha256": result["targetSha256"],
                "routeId": result["routeId"],
                "operationalStatus": result["operationalStatus"],
                "validationStatus": validation["status"],
                "claimStatus": result["claimStatus"],
                "resultPath": f"targets/{target_id}/result.json",
                "validationPath": f"targets/{target_id}/validation/summary.json",
            }
        )
    require(bool(records), "bundle must contain at least one target")
    if expected_targets is not None:
        expected = [
            (item.get("targetId"), item.get("workflowMode"), item.get("targetSha256"))
            for item in expected_targets
        ]
        actual = [
            (item["targetId"], item["workflowMode"], item["targetSha256"])
            for item in records
        ]
        require(actual == expected, "staging target directories/IDs/modes/hashes differ from the initialized target set")
    return records


def validate_artifact_references(
    root: Path,
    target_id: str,
    values: object,
    label: str,
    allowed_prefixes: tuple[str, ...],
    allowed_exact: tuple[str, ...] = (),
) -> list[str]:
    require(isinstance(values, list), f"{target_id}: {label} must be an array of bundle-relative paths")
    require(all(isinstance(value, str) and safe_relative(value) for value in values), f"{target_id}: unsafe {label} path")
    require(len(values) == len(set(values)), f"{target_id}: duplicate {label} path")
    for relative in values:
        require(
            relative in allowed_exact or any(relative.startswith(prefix) for prefix in allowed_prefixes),
            f"{target_id}: {label} path escapes its target/shared scope: {relative}",
        )
        require_regular_member(root / relative, f"{target_id} {label} artifact")
    return values


def require_named_figure_path(
    root: Path,
    target_id: str,
    value: object,
    stem: str,
    label: str,
) -> str:
    require(isinstance(value, str) and safe_relative(value), f"{target_id}: {label} path is unsafe")
    path = PurePosixPath(value)
    require(
        path.parent.as_posix() == f"targets/{target_id}/outputs"
        and path.stem == stem
        and path.suffix.lower() in FIGURE_ARTIFACT_SUFFIXES,
        f"{target_id}: {label} must be outputs/{stem}.<figure-format>",
    )
    require_regular_member(root / value, f"{target_id} {label}")
    return value


def require_named_validation_path(
    root: Path,
    target_id: str,
    value: object,
    relative_name: str,
    label: str,
) -> str:
    expected = f"targets/{target_id}/validation/{relative_name}"
    require(value == expected, f"{target_id}: {label} must be {expected}")
    require_regular_member(root / expected, f"{target_id} {label}")
    return expected


def require_nonempty_string(value: object, message: str) -> str:
    require(isinstance(value, str) and value.strip(), message)
    return value.strip()


def require_neutral_integrity_language(value: str, target_id: str, label: str) -> None:
    require(
        DIRECT_MISCONDUCT_ALLEGATION.search(value) is None,
        f"{target_id}: {label} makes a direct misconduct/fabrication allegation; record only a neutral potential research-integrity concern",
    )


def require_exact_keys(value: dict, keys: set[str], message: str) -> None:
    require(set(value) == keys, message)


def validate_adjustment_change(target_id: str, number: int, change: object) -> None:
    require(isinstance(change, dict), f"{target_id}: round {number} change must be an object")
    if number == 2:
        require_exact_keys(
            change,
            {"changeDomain", "subject", "before", "after", "reason"},
            f"{target_id}: round 2 changes have missing or unknown fields",
        )
        require(
            change.get("changeDomain") in PRESENTATION_CHANGE_DOMAINS,
            f"{target_id}: round 2 changeDomain must be presentation-only; axis scale, units, and range belong in V1",
        )
    else:
        require_exact_keys(
            change,
            {
                "changeDomain", "subject", "before", "after", "reason",
                "diagnosisRef", "evidenceRefs", "scientificBasis",
            },
            f"{target_id}: scientific-round changes have missing or unknown fields",
        )
        require(
            change.get("changeDomain") in SCIENTIFIC_CHANGE_DOMAINS,
            f"{target_id}: round {number} changeDomain must be scientific",
        )
        diagnosis = change.get("diagnosisRef")
        require(diagnosis is None or (isinstance(diagnosis, str) and diagnosis.strip()), f"{target_id}: invalid diagnosisRef")
        evidence = change.get("evidenceRefs")
        require(
            isinstance(evidence, list) and all(isinstance(item, str) and item.strip() for item in evidence),
            f"{target_id}: evidenceRefs must be an array of non-empty references",
        )
        basis = change.get("scientificBasis")
        require(basis is None or (isinstance(basis, str) and basis.strip()), f"{target_id}: invalid scientificBasis")
        require(
            bool((isinstance(diagnosis, str) and diagnosis.strip()) or evidence or (isinstance(basis, str) and basis.strip())),
            f"{target_id}: round {number} scientific change requires diagnosisRef, evidenceRefs, or scientificBasis",
        )
    require_nonempty_string(change.get("subject"), f"{target_id}: round {number} change subject is required")
    require_nonempty_string(change.get("reason"), f"{target_id}: round {number} change reason is required")
    require("before" in change and "after" in change, f"{target_id}: round {number} change requires before and after")
    require(
        canonical_hash(change["before"]) != canonical_hash(change["after"]),
        f"{target_id}: round {number} change must alter the recorded value",
    )


def validate_comparison_record(
    root: Path,
    target_id: str,
    record: object,
    *,
    expected_id: str,
    expected_output: str,
    distribution_class: str,
) -> str:
    require(isinstance(record, dict), f"{target_id}: comparison record must be an object")
    require_exact_keys(
        record,
        {"comparisonId", "output", "mode", "artifact", "targetPixelRights"},
        f"{target_id}: comparison record has missing or unknown fields",
    )
    require(record.get("comparisonId") == expected_id, f"{target_id}: expected {expected_id} comparison")
    require(record.get("output") == expected_output, f"{target_id}: {expected_id} output binding is wrong")
    mode = record.get("mode")
    require(mode in COMPARISON_MODES, f"{target_id}: invalid comparison mode")
    relative = record.get("artifact")
    require(isinstance(relative, str) and safe_relative(relative), f"{target_id}: unsafe comparison artifact path")
    path = PurePosixPath(relative)
    require(
        path.parent.as_posix() == f"targets/{target_id}/validation/comparisons"
        and path.stem == expected_id
        and path.suffix.lower() in RESULT_IMAGE_SUFFIXES,
        f"{target_id}: {expected_id} must be an image under validation/comparisons/",
    )
    require_regular_member(root / relative, f"{target_id} {expected_id} comparison")
    rights = record.get("targetPixelRights")
    require(isinstance(rights, dict), f"{target_id}: comparison targetPixelRights must be an object")
    require_exact_keys(
        rights,
        {"included", "sourceId", "redistributionStatus"},
        f"{target_id}: comparison targetPixelRights fields are invalid",
    )
    if mode == "metrics-only":
        require(
            rights == {"included": False, "sourceId": None, "redistributionStatus": "not-included"},
            f"{target_id}: metrics-only comparison must exclude target pixels",
        )
    else:
        require(rights.get("included") is True, f"{target_id}: side-by-side comparison includes target pixels")
        source_id = rights.get("sourceId")
        require(isinstance(source_id, str) and bool(IDENTIFIER.fullmatch(source_id)), f"{target_id}: side-by-side comparison needs a sourceId")
        allowed_rights = {"local-only", "permitted", "public-domain", "generated"}
        require(rights.get("redistributionStatus") in allowed_rights, f"{target_id}: invalid target-pixel rights")
        sources = read_object(root / "shared/provenance/sources.json", "sources record")
        source = next((item for item in sources.get("sources", []) if item.get("sourceId") == source_id), None)
        require(isinstance(source, dict), f"{target_id}: target-pixel sourceId is not declared")
        require(
            source.get("redistributionStatus") == rights["redistributionStatus"],
            f"{target_id}: comparison rights disagree with the declared target source",
        )
        if distribution_class == "shareable":
            require(
                rights["redistributionStatus"] in {"permitted", "public-domain", "generated"},
                f"{target_id}: shareable side-by-side comparison lacks target-pixel redistribution rights",
            )
    return relative


def validate_calibration_documents(
    root: Path,
    target_id: str,
    result: dict,
    validation: dict,
    output_refs: list[str],
    validation_artifacts: list[str],
    distribution_class: str,
) -> None:
    """Validate the bounded V0/V1/V2 comparison and adjustment record.

    V0 and the comparison/quality records are mandatory for a complete or
    partial figure result. V1 and V2 are optional: an unneeded round must not
    be represented by a placeholder artifact. Round 3+ is possible only when
    its record binds a new testable hypothesis and a target-specific approval.
    """
    calibration = result.get("calibration")
    require(isinstance(calibration, dict), f"{target_id}: completed/partial work requires calibration metadata")
    required_fields = {
        "baselineV0", "scientificV1", "presentationV2", "selectedOutput",
        "comparisons", "differenceSummary", "visualQualityCheck", "adjustments",
    }
    require(set(calibration) == required_fields, f"{target_id}: calibration fields are missing or unknown")

    baseline = require_named_figure_path(
        root, target_id, calibration["baselineV0"], "baseline-v0", "baseline V0"
    )
    scientific_v1 = calibration["scientificV1"]
    if scientific_v1 is not None:
        scientific_v1 = require_named_figure_path(
            root, target_id, scientific_v1, "calibrated-v1", "scientific V1"
        )
    presentation_v2 = calibration["presentationV2"]
    if presentation_v2 is not None:
        presentation_v2 = require_named_figure_path(
            root, target_id, presentation_v2, "final-v2", "presentation V2"
        )

    comparisons = calibration["comparisons"]
    require(isinstance(comparisons, list), f"{target_id}: calibration comparisons must be an array")
    comparison_ids = [item.get("comparisonId") for item in comparisons if isinstance(item, dict)]
    require(
        len(comparison_ids) == len(comparisons) and len(comparison_ids) == len(set(comparison_ids)),
        f"{target_id}: calibration comparisons must have unique comparisonId values",
    )
    require(
        set(comparison_ids).issubset({"original-vs-v0", "original-vs-final"}),
        f"{target_id}: calibration comparisonId is unknown",
    )
    baseline_record = next(
        (item for item in comparisons if item.get("comparisonId") == "original-vs-v0"), None
    )
    require(baseline_record is not None, f"{target_id}: original-vs-v0 comparison is required")
    comparison_paths = {
        validate_comparison_record(
            root,
            target_id,
            baseline_record,
            expected_id="original-vs-v0",
            expected_output=baseline,
            distribution_class=distribution_class,
        )
    }

    difference_path = require_named_validation_path(
        root, target_id, calibration["differenceSummary"], "difference-summary.json", "difference summary"
    )
    quality_path = require_named_validation_path(
        root, target_id, calibration["visualQualityCheck"], "visual-quality-check.json", "visual quality check"
    )
    adjustments_path = f"targets/{target_id}/adjustments.json"
    require(calibration["adjustments"] == adjustments_path, f"{target_id}: adjustments must be {adjustments_path}")
    require_regular_member(root / adjustments_path, f"{target_id} adjustments")

    required_output_refs = {baseline}
    if scientific_v1 is not None:
        required_output_refs.add(scientific_v1)
    if presentation_v2 is not None:
        required_output_refs.add(presentation_v2)
    require(required_output_refs.issubset(output_refs), f"{target_id}: versioned figures must be declared in result.outputs")
    required_validation_refs = {
        *comparison_paths,
        difference_path,
        quality_path,
        adjustments_path,
    }
    require(
        required_validation_refs.issubset(validation_artifacts),
        f"{target_id}: comparison, difference, quality, and adjustment records must be validation artifacts",
    )

    difference = read_object(root / difference_path, f"{target_id} difference summary")
    require(difference.get("schemaVersion") == DIFFERENCE_SUMMARY_SCHEMA, f"{target_id}: unsupported difference-summary schema")
    require_exact_keys(
        difference,
        {"schemaVersion", "targetId", "baseline", "selected", "dimensions", "scientificConclusion", "remainingDifferences"},
        f"{target_id}: difference-summary fields are missing or unknown",
    )
    require(difference.get("targetId") == target_id, f"{target_id}: difference-summary target mismatch")
    require(difference.get("baseline") == baseline, f"{target_id}: difference-summary baseline mismatch")
    dimensions = difference.get("dimensions")
    required_dimensions = {
        "axesUnitsScale", "trendsPeaksMagnitude", "colorsLinesLegends", "layoutTypography",
    }
    require(isinstance(dimensions, dict) and set(dimensions) == required_dimensions, f"{target_id}: difference-summary dimensions are incomplete")
    for name, assessment in dimensions.items():
        require_nonempty_string(assessment, f"{target_id}: difference-summary {name} assessment is required")
    scientific_conclusion = require_nonempty_string(
        difference.get("scientificConclusion"), f"{target_id}: difference-summary scientific conclusion is required"
    )
    if result.get("workflowMode") == "scientific-reproduction":
        require_neutral_integrity_language(
            scientific_conclusion, target_id, "difference-summary scientificConclusion",
        )
    require(
        isinstance(difference.get("remainingDifferences"), list)
        and all(isinstance(item, str) and item.strip() for item in difference["remainingDifferences"]),
        f"{target_id}: remainingDifferences must be an array of strings",
    )

    quality = read_object(root / quality_path, f"{target_id} visual quality check")
    require(quality.get("schemaVersion") == VISUAL_QUALITY_SCHEMA, f"{target_id}: unsupported visual-quality schema")
    require_exact_keys(
        quality,
        {"schemaVersion", "targetId", "status", "checks", "issuesRemaining"},
        f"{target_id}: visual-quality fields are missing or unknown",
    )
    require(quality.get("targetId") == target_id, f"{target_id}: visual-quality target mismatch")
    require(quality.get("status") in {"passed", "issues-remain"}, f"{target_id}: invalid visual-quality status")
    checks = quality.get("checks")
    required_checks = {"textOverlap", "legendDataOverlap", "clipping", "contrast", "readability"}
    require(isinstance(checks, dict) and set(checks) == required_checks, f"{target_id}: visual-quality checks are incomplete")
    for name, assessment in checks.items():
        require_nonempty_string(assessment, f"{target_id}: visual-quality {name} assessment is required")
    require(
        isinstance(quality.get("issuesRemaining"), list)
        and all(isinstance(item, str) and item.strip() for item in quality["issuesRemaining"]),
        f"{target_id}: visual-quality issuesRemaining must be an array of strings",
    )
    require(
        (quality["status"] == "passed" and not quality["issuesRemaining"])
        or (quality["status"] == "issues-remain" and bool(quality["issuesRemaining"])),
        f"{target_id}: visual-quality status and remaining issues disagree",
    )

    adjustments = read_object(root / adjustments_path, f"{target_id} adjustments")
    require(adjustments.get("schemaVersion") == ADJUSTMENTS_SCHEMA, f"{target_id}: unsupported adjustments schema")
    require_exact_keys(
        adjustments,
        {"schemaVersion", "targetId", "rounds", "selectedOutput", "stopReason"},
        f"{target_id}: adjustments fields are missing or unknown",
    )
    require(adjustments.get("targetId") == target_id, f"{target_id}: adjustments target mismatch")
    rounds = adjustments.get("rounds")
    require(isinstance(rounds, list), f"{target_id}: adjustments rounds must be an array")
    round_numbers: list[int] = []
    round_outputs: dict[int, str] = {}
    extension_hypotheses: set[str] = set()
    extension_approval_ids: set[str] = set()
    extension_idempotency_keys: set[str] = set()
    for record in rounds:
        require(isinstance(record, dict), f"{target_id}: each adjustment round must be an object")
        number = record.get("round")
        require(type(number) is int and number >= 1, f"{target_id}: adjustment round number must be a positive integer")
        require(number not in round_numbers, f"{target_id}: adjustment round numbers must be unique")
        round_numbers.append(number)
        expected_kind = "scientific-difference" if number == 1 else "presentation-quality" if number == 2 else "scientific-hypothesis"
        expected_fields = {"round", "kind", "output", "rationale", "changes"}
        if number >= 3:
            expected_fields.add("hypothesis")
            if "approvalEvidence" in record:
                expected_fields.add("approvalEvidence")
        require_exact_keys(
            record,
            expected_fields,
            f"{target_id}: round {number} fields are missing or unknown",
        )
        require(record.get("kind") == expected_kind, f"{target_id}: round {number} has the wrong adjustment kind")
        require_nonempty_string(record.get("rationale"), f"{target_id}: round {number} rationale is required")
        require(
            isinstance(record.get("changes"), list)
            and bool(record["changes"])
            and all(isinstance(item, dict) for item in record["changes"]),
            f"{target_id}: round {number} changes must be a non-empty array of objects",
        )
        for change in record["changes"]:
            validate_adjustment_change(target_id, number, change)
        expected_stem = "calibrated-v1" if number == 1 else "final-v2" if number == 2 else f"calibrated-v{number}"
        output = require_named_figure_path(root, target_id, record.get("output"), expected_stem, f"round {number} output")
        require(output in output_refs, f"{target_id}: round {number} output is absent from result.outputs")
        round_outputs[number] = output
        if number >= 3:
            hypothesis = require_nonempty_string(
                record.get("hypothesis"), f"{target_id}: round {number} requires a new testable hypothesis"
            )
            require(
                hypothesis not in extension_hypotheses,
                f"{target_id}: round {number} must introduce a new testable hypothesis",
            )
            extension_hypotheses.add(hypothesis)
            approval_relative = f"targets/{target_id}/validation/calibration-round-{number}-approval.json"
            require(record.get("approvalEvidence") == approval_relative, f"{target_id}: round {number} requires {approval_relative}")
            require(approval_relative in validation_artifacts, f"{target_id}: round {number} approval must be a validation artifact")
            approval = read_object(root / approval_relative, f"{target_id} round {number} approval")
            require(approval.get("schemaVersion") == CALIBRATION_APPROVAL_SCHEMA, f"{target_id}: unsupported calibration approval schema")
            require_exact_keys(
                approval,
                {
                    "schemaVersion", "approvalId", "idempotencyKey", "targetId", "round",
                    "decision", "hypothesis", "approvedAt", "previousOutput",
                    "previousOutputSha256", "maxAttempts",
                },
                f"{target_id}: round {number} approval fields are missing or unknown",
            )
            require(
                approval.get("targetId") == target_id
                and type(approval.get("round")) is int
                and approval.get("round") == number
                and approval.get("decision") == "approve"
                and approval.get("hypothesis") == hypothesis,
                f"{target_id}: round {number} approval does not bind the hypothesis",
            )
            approval_id = approval.get("approvalId")
            idempotency_key = approval.get("idempotencyKey")
            require(
                isinstance(approval_id, str) and bool(IDENTIFIER.fullmatch(approval_id))
                and approval_id not in extension_approval_ids,
                f"{target_id}: round {number} approvalId must be unique and path-safe",
            )
            require(
                isinstance(idempotency_key, str) and bool(IDENTIFIER.fullmatch(idempotency_key))
                and idempotency_key not in extension_idempotency_keys,
                f"{target_id}: round {number} idempotencyKey must be unique and path-safe",
            )
            extension_approval_ids.add(approval_id)
            extension_idempotency_keys.add(idempotency_key)
            previous_output = round_outputs.get(number - 1)
            require(previous_output is not None, f"{target_id}: round {number} has no prior output to approve")
            require(approval.get("previousOutput") == previous_output, f"{target_id}: round {number} approval does not bind the prior output")
            require(
                isinstance(approval.get("previousOutputSha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", approval["previousOutputSha256"])
                and approval["previousOutputSha256"] == sha256_file(root / previous_output),
                f"{target_id}: round {number} approval prior-output hash mismatch",
            )
            require(
                type(approval.get("maxAttempts")) is int and 1 <= approval["maxAttempts"] <= 10,
                f"{target_id}: round {number} approval maxAttempts must be an integer from 1 to 10",
            )
            parse_timestamp(approval.get("approvedAt"), f"{target_id} round {number} approval approvedAt")
    require(round_numbers == sorted(round_numbers), f"{target_id}: adjustment rounds must be ordered")
    if any(number >= 3 for number in round_numbers):
        require(
            round_numbers == list(range(1, max(round_numbers) + 1)),
            f"{target_id}: extended calibration rounds must preserve the complete V1..Vn history",
        )
    require((1 in round_outputs) == (scientific_v1 is not None), f"{target_id}: V1 artifact and round record disagree")
    require((2 in round_outputs) == (presentation_v2 is not None), f"{target_id}: V2 artifact and round record disagree")

    available_outputs = {baseline, *round_outputs.values()}
    selected = calibration["selectedOutput"]
    require(selected in available_outputs, f"{target_id}: selectedOutput is not a recorded version")
    require(adjustments.get("selectedOutput") == selected, f"{target_id}: selected output disagrees with adjustments")
    require(difference.get("selected") == selected, f"{target_id}: selected output disagrees with difference summary")
    require_nonempty_string(adjustments.get("stopReason"), f"{target_id}: bounded calibration stop reason is required")
    if selected != baseline:
        final_record = next(
            (item for item in comparisons if item.get("comparisonId") == "original-vs-final"), None
        )
        require(final_record is not None, f"{target_id}: original-vs-final comparison is required when a calibrated output is selected")
        final_comparison = validate_comparison_record(
            root,
            target_id,
            final_record,
            expected_id="original-vs-final",
            expected_output=selected,
            distribution_class=distribution_class,
        )
        require(final_comparison in validation_artifacts, f"{target_id}: original-vs-final must be a validation artifact")
    else:
        require("original-vs-final" not in comparison_ids, f"{target_id}: original-vs-final is misleading when V0 is selected")


def validate_target_documents(
    root: Path,
    target_id: str,
    result: dict,
    validation: dict,
    *,
    terminal: bool,
    distribution_class: str,
) -> None:
    require(result.get("schemaVersion") == TARGET_RESULT_SCHEMA, f"{target_id}: unsupported result schema")
    require(result.get("targetId") == target_id, f"{target_id}: result target ID mismatch")
    require(result.get("workflowMode") in WORKFLOW_MODES, f"{target_id}: invalid workflow mode")
    require(
        result.get("targetSha256") is None
        or (isinstance(result["targetSha256"], str) and re.fullmatch(r"[0-9a-f]{64}", result["targetSha256"])),
        f"{target_id}: invalid target SHA-256",
    )
    require(
        result.get("routeId") is None
        or (isinstance(result["routeId"], str) and bool(IDENTIFIER.fullmatch(result["routeId"]))),
        f"{target_id}: invalid route ID",
    )
    status = result.get("operationalStatus")
    require(status in TARGET_STATUSES, f"{target_id}: invalid operational status")
    if terminal:
        require(status in RUN_STATUSES, f"{target_id}: operational status is not terminal")
    claim = result.get("claimStatus")
    require(claim in CLAIM_STATUSES, f"{target_id}: invalid claim status")
    if result.get("workflowMode") == "image-derived-reconstruction":
        require(claim == "not-applicable", f"{target_id}: image-derived work cannot test a paper claim")
    require(isinstance(result.get("summary"), str) and result["summary"].strip(), f"{target_id}: result summary is required")
    if (
        result.get("workflowMode") == "scientific-reproduction"
        and status in {"complete", "partial"}
    ):
        require_neutral_integrity_language(result["summary"], target_id, "result summary")
    output_refs = validate_artifact_references(
        root,
        target_id,
        result.get("outputs"),
        "outputs",
        (
            f"targets/{target_id}/outputs/",
            f"targets/{target_id}/derived/",
            f"targets/{target_id}/code/",
            "shared/artifacts/",
            "shared/code/",
            "shared/config/",
            "shared/patches/",
        ),
    )
    for field in ("warnings", "errors"):
        require(
            isinstance(result.get(field), list) and all(isinstance(item, str) for item in result[field]),
            f"{target_id}: result {field} must be an array of strings",
        )

    require(validation.get("schemaVersion") == VALIDATION_SCHEMA, f"{target_id}: unsupported validation schema")
    require(validation.get("targetId") == target_id, f"{target_id}: validation target ID mismatch")
    require(validation.get("workflowMode") == result.get("workflowMode"), f"{target_id}: workflow modes disagree")
    require(validation.get("status") in VALIDATION_STATUSES, f"{target_id}: invalid validation status")
    require(
        isinstance(validation.get("summary"), str) and validation["summary"].strip(),
        f"{target_id}: validation summary is required",
    )
    require(isinstance(validation.get("criteria"), list), f"{target_id}: validation criteria must be an array")
    require(isinstance(validation.get("metrics"), list), f"{target_id}: validation metrics must be an array")
    validation_artifacts = validate_artifact_references(
        root,
        target_id,
        validation.get("artifacts", []),
        "validation artifacts",
        (
            f"targets/{target_id}/validation/",
            f"targets/{target_id}/outputs/",
            f"targets/{target_id}/derived/",
            "shared/artifacts/",
        ),
        (f"targets/{target_id}/adjustments.json",),
    )

    validation_status = validation["status"]
    if validation_status in {"passed", "partially-passed", "failed", "inconclusive"}:
        require(
            bool(validation.get("criteria") or validation.get("metrics") or validation_artifacts),
            f"{target_id}: actual validation requires criteria, metrics, or an artifact",
        )
    if status == "complete":
        require(bool(output_refs), f"{target_id}: completed target requires at least one generated output")
        require(
            validation_status in {"passed", "partially-passed", "failed", "inconclusive"},
            f"{target_id}: completed target requires actual validation",
        )
    elif status == "partial":
        require(bool(output_refs), f"{target_id}: partial target requires at least one generated output")
        require(
            validation_status in {"partially-passed", "failed", "inconclusive"},
            f"{target_id}: partial target has an incoherent validation status",
        )
    elif status == "failed":
        require(validation_status in {"failed", "inconclusive", "not-run"}, f"{target_id}: failed target validation is incoherent")
    else:
        require(validation_status == "not-run", f"{target_id}: blocked/cancelled target must use validation not-run")

    if result["workflowMode"] == "scientific-reproduction":
        if claim == "supported":
            require(status == "complete" and validation_status == "passed", f"{target_id}: supported claim requires complete, passed validation")
        elif claim in {"partially-supported", "unsupported"}:
            require(
                status in {"complete", "partial"} and validation_status in {"passed", "partially-passed"},
                f"{target_id}: {claim} claim is inconsistent with execution/validation",
            )
        elif claim == "inconclusive":
            require(
                status in {"complete", "partial", "failed"} and validation_status in {"partially-passed", "failed", "inconclusive"},
                f"{target_id}: inconclusive claim is inconsistent with execution/validation",
            )
        elif status == "complete":
            raise BundleError(f"{target_id}: a completed scientific target cannot leave the claim untested")

    if status in {"complete", "partial"}:
        validate_calibration_documents(
            root,
            target_id,
            result,
            validation,
            output_refs,
            validation_artifacts,
            distribution_class,
        )


def terminalize_pending_targets(root: Path, status: str, reason: str | None) -> None:
    for result_path in sorted((root / "targets").glob("*/result.json")):
        result = read_object(result_path, "target result")
        if result.get("operationalStatus") != "pending":
            continue
        require(
            status in {"failed", "blocked", "cancelled"},
            f"{result.get('targetId', result_path.parent.name)}: set a terminal target result before completing the bundle",
        )
        require(bool(reason and reason.strip()), f"--reason is required when terminalizing pending targets as {status}")
        result["operationalStatus"] = status
        result["claimStatus"] = (
            "not-applicable" if result.get("workflowMode") == "image-derived-reconstruction" else "not-tested"
        )
        result["summary"] = reason.strip()
        errors = result.setdefault("errors", [])
        if status in {"failed", "blocked"}:
            errors.append(reason.strip())
        write_json(result_path, result)

        summary_path = result_path.parent / "validation/summary.json"
        validation = read_object(summary_path, "validation summary")
        validation["status"] = "not-run"
        validation["summary"] = f"Validation did not run: {reason.strip()}"
        write_json(summary_path, validation)


def validate_aggregate_status(status: str, targets: list[dict]) -> None:
    statuses = [target["operationalStatus"] for target in targets]
    unique = set(statuses)
    expected = statuses[0] if len(unique) == 1 and statuses[0] != "partial" else "partial"
    require(status == expected, f"bundle status {status} is inconsistent with target statuses {statuses}; expected {expected}")


def update_readme_status(
    root: Path,
    status: str,
    finalized_at: str,
    expected_targets: list[dict],
    distribution_class: str,
) -> None:
    path = root / "README.md"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\*\*Status:\*\*\s+[^\n]+", f"**Status:** {status}  ", text, count=1)
    if "**Finalized:**" not in text:
        marker = f"**Finalized:** {finalized_at}  \n"
        distribution_line = re.search(r"\*\*Distribution:\*\*[^\n]+\n", text)
        if distribution_line:
            offset = distribution_line.end()
            text = text[:offset] + marker + text[offset:]
        else:
            text = marker + text
    start_marker = "<!-- scirepro-result:start -->"
    end_marker = "<!-- scirepro-result:end -->"
    if start_marker in text and end_marker in text:
        rows = ["| Target | Execution | Validation | Claim |", "|---|---|---|---|"]
        details = []
        for record in target_records(
            root,
            expected_targets,
            distribution_class=distribution_class,
        ):
            rows.append(
                f"| `{record['targetId']}` | {record['operationalStatus']} | "
                f"{record['validationStatus']} | {record['claimStatus']} |"
            )
            result = read_object(root / record["resultPath"], f"{record['targetId']} result")
            details.append(f"- **{record['targetId']}:** {result['summary'].strip()}")
        report_link = ["", "[Open the local result report / 查看本地结果报告](report/index.html)"] if (root / "report/index.html").is_file() else []
        replacement = start_marker + "\n" + "\n".join(rows + [""] + details + report_link) + "\n" + end_marker
        prefix, remainder = text.split(start_marker, 1)
        _, suffix = remainder.split(end_marker, 1)
        text = prefix + replacement + suffix
    write_bytes(path, text.encode("utf-8"))


def build_manifest(root: Path, state: dict, status: str, finalized_at: str) -> dict:
    files = inventory(root)
    targets = target_records(
        root,
        state["targets"],
        distribution_class=state["distributionClass"],
    )
    validate_aggregate_status(status, targets)
    plan_paths = {
        name: relative for name, relative in PLAN_INPUTS.items() if (root / relative).is_file()
    }
    omissions = "shared/provenance/omissions.json"
    manifest = {
        "schemaVersion": BUNDLE_SCHEMA,
        "bundleId": state["bundleId"],
        "runId": state["runId"],
        "createdAt": state["createdAt"],
        "finalizedAt": finalized_at,
        "generator": {"name": "SciRepro", "component": "finalize_run_bundle.py", "schema": 2},
        "status": status,
        "planBindings": state["planBindings"],
        "scope": {"targetCount": len(targets), "targetIds": [target["targetId"] for target in targets]},
        "targets": targets,
        "shared": {
            "plan": plan_paths,
            "sources": "shared/provenance/sources.json",
            "environment": "shared/environment/environment.json",
            "resourceUsage": "shared/execution/resource-usage.json",
        },
        "rights": {
            "distributionClass": state["distributionClass"],
            "policy": (
                "local research use; redistribution has not been asserted"
                if state["distributionClass"] == "local-private"
                else "only generated or redistribution-cleared artifacts may be included"
            ),
            "omissions": omissions if (root / omissions).is_file() else None,
        },
        "files": files,
        "warnings": duplicate_warnings(files),
        "errors": [],
        "integrity": {"inventorySha256": canonical_hash(files), "manifestSha256": ""},
    }
    manifest["integrity"]["manifestSha256"] = manifest_self_hash(manifest)
    return manifest


def duplicate_warnings(files: list[dict]) -> list[str]:
    by_hash: dict[str, list[dict]] = {}
    for entry in files:
        if entry["sizeBytes"] == 0 or not entry["path"].startswith("targets/"):
            continue
        by_hash.setdefault(entry["sha256"], []).append(entry)
    warnings = []
    for entries in by_hash.values():
        target_ids = {entry["path"].split("/", 2)[1] for entry in entries}
        if len(target_ids) > 1:
            paths = ", ".join(entry["path"] for entry in entries)
            warnings.append(f"identical per-target files may belong in shared/: {paths}")
    return warnings


def validate_sources_rights(root: Path, distribution_class: str) -> None:
    sources = read_object(root / "shared/provenance/sources.json", "sources record")
    require(sources.get("schemaVersion") == SOURCES_SCHEMA, "unsupported sources schema")
    entries = sources.get("sources")
    require(isinstance(entries, list), "sources.sources must be an array")
    declared_paths: set[str] = set()
    for index, source in enumerate(entries):
        require(isinstance(source, dict), f"sources[{index}] must be an object")
        for field in ("sourceId", "kind", "title"):
            require(isinstance(source.get(field), str) and source[field].strip(), f"sources[{index}].{field} is required")
        included = source.get("includedPath")
        if included is not None:
            require(isinstance(included, str) and safe_relative(included), f"sources[{index}].includedPath is unsafe")
            require_regular_member(root / included, f"sources[{index}].includedPath")
            require(included not in declared_paths, f"duplicate included source path: {included}")
            declared_paths.add(included)
            if source.get("sha256") is not None:
                require(
                    isinstance(source["sha256"], str)
                    and re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
                    and sha256_file(root / included) == source["sha256"],
                    f"sources[{index}].sha256 does not match includedPath",
                )
            if source.get("sizeBytes") is not None:
                require(
                    isinstance(source["sizeBytes"], int)
                    and source["sizeBytes"] >= 0
                    and (root / included).stat().st_size == source["sizeBytes"],
                    f"sources[{index}].sizeBytes does not match includedPath",
                )
            if distribution_class == "shareable":
                require(
                    source.get("redistributionStatus") in {"permitted", "generated", "public-domain"},
                    f"sources[{index}] is included in a shareable bundle without redistribution clearance",
                )
    if distribution_class == "shareable":
        omissions_path = root / "shared/provenance/omissions.json"
        if omissions_path.exists():
            omissions = read_object(omissions_path, "omissions record")
            require(omissions.get("schemaVersion") == OMISSIONS_SCHEMA, "unsupported omissions schema")
            require(isinstance(omissions.get("omissions"), list), "omissions must be an array")
        generated_paths = declared_generated_paths(root)
        for relative, path in relative_files(root, include_manifest=True):
            if relative in declared_paths or is_generated_shareable_path(relative, generated_paths):
                scan_shareable_text(path, relative)
                continue
            raise BundleError(
                f"shareable bundle file lacks a permitted/generated/public-domain source declaration: {relative}"
            )


def declared_generated_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    targets_root = root / "targets"
    if not targets_root.exists():
        return paths
    for target_dir in targets_root.iterdir():
        if not target_dir.is_dir() or target_dir.is_symlink():
            continue
        result = read_object(target_dir / "result.json", "shareable target result")
        validation = read_object(target_dir / "validation/summary.json", "shareable validation summary")
        for value in result.get("outputs", []) + validation.get("artifacts", []):
            if isinstance(value, str) and safe_relative(value):
                paths.add(value)
    return paths


def is_generated_shareable_path(relative: str, generated_paths: set[str]) -> bool:
    fixed_contract_files = {
        "README.md",
        "manifest.json",
        *PLAN_INPUTS.values(),
        "shared/provenance/sources.json",
        "shared/provenance/omissions.json",
        "shared/environment/environment.json",
        "shared/execution/resource-usage.json",
        "shared/execution/commands.jsonl",
        "shared/execution/run.log",
    }
    if relative in fixed_contract_files:
        return True
    if relative.startswith("report/"):
        # A shareable report is accepted only after its embedded Phase 1 bundle
        # has passed the public-audience and inventory checks.
        return True
    if relative in generated_paths:
        return True
    if relative.startswith("shared/environment/lockfiles/") and PurePosixPath(relative).suffix.lower() in TEXT_SUFFIXES:
        return True
    parts = PurePosixPath(relative).parts
    if len(parts) >= 3 and parts[0] == "targets":
        tail = "/".join(parts[2:])
        return (
            tail in {"result.json", "validation/summary.json", "validation/metrics.json"}
            or (tail.startswith("logs/") and PurePosixPath(relative).suffix.lower() in TEXT_SUFFIXES)
        )
    return False


def scan_shareable_text(path: Path, relative: str) -> None:
    require(not SENSITIVE_NAME.fullmatch(path.name), f"shareable bundle contains a suspicious secret filename: {relative}")
    if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 2 * 1024 * 1024:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise BundleError(f"shareable text file is not valid UTF-8: {relative}") from exc
    require(PRIVATE_KEY_BLOCK.search(text) is None, f"shareable bundle contains a private key: {relative}")
    require(SENSITIVE_VALUE.search(text) is None, f"shareable bundle contains a possible secret: {relative}")
    require(LOCAL_PATH.search(text) is None, f"shareable bundle contains an absolute local path: {relative}")


def validate_required_json(root: Path) -> None:
    for relative, schema in REQUIRED_SHARED.items():
        value = read_object(root / relative, relative)
        require(value.get("schemaVersion") == schema, f"{relative}: unsupported schema")
    environment = read_object(root / "shared/environment/environment.json", "environment record")
    require(environment.get("captureStatus") in {"not-recorded", "partial", "recorded"}, "environment captureStatus is invalid")
    require(isinstance(environment.get("runtime"), dict), "environment runtime must be an object")
    resources = read_object(root / "shared/execution/resource-usage.json", "resource-usage record")
    require(
        resources.get("measurementStatus") in {"not-recorded", "partial", "recorded"},
        "resource-usage measurementStatus is invalid",
    )
    require_exact_keys(
        resources,
        {
            "schemaVersion", "measurementStatus", "wallSeconds", "peakMemoryBytes",
            "diskBytes", "networkBytes", "cost",
        },
        "resource-usage fields are missing or unknown",
    )
    numeric_fields = ("wallSeconds", "peakMemoryBytes", "diskBytes", "networkBytes")
    for field in numeric_fields:
        value = resources.get(field)
        require(
            value is None or (type(value) in {int, float} and value >= 0),
            f"resource-usage {field} must be null or a non-negative number",
        )
    if resources["measurementStatus"] in {"partial", "recorded"}:
        require(
            any(resources.get(field) is not None for field in (*numeric_fields, "cost")),
            "measured resource usage requires at least one recorded measurement",
        )


def validate_archived_parameter_value(spec: dict, value: object, label: str) -> None:
    kind = spec.get("type")
    if kind == "string":
        require(isinstance(value, str) and len(value) <= 4096, f"{label}: expected a bounded string")
    elif kind == "integer":
        require(type(value) is int, f"{label}: expected integer")
    elif kind == "number":
        try:
            finite = type(value) in {int, float} and math.isfinite(value)
        except OverflowError:
            finite = False
        require(
            finite,
            f"{label}: expected finite number",
        )
    elif kind == "boolean":
        require(type(value) is bool, f"{label}: expected boolean")
    elif kind == "enum":
        require(value in spec.get("enum", []), f"{label}: invalid enum value")
    elif kind == "relative-path":
        require(isinstance(value, str) and safe_relative(value), f"{label}: unsafe relative path")
    else:
        raise BundleError(f"{label}: unsupported parameter type")
    try:
        require_secret_free(value, f"{label} value")
    except PhaseOneReportError as exc:
        raise BundleError(str(exc)) from exc
    if type(value) in {int, float}:
        if "min" in spec:
            require(value >= spec["min"], f"{label}: below minimum")
        if "max" in spec:
            require(value <= spec["max"], f"{label}: above maximum")


def validate_archived_gate_authority(
    report: dict,
    approval: dict,
    gate: dict,
    targets: dict[str, dict],
) -> None:
    """Reconstruct the approved authority from immutable report semantics.

    Hashes make changes visible but do not prove that a recomputed gate still
    represents the report and approval.  This check independently crosses all
    execution-bearing values back to those two source records.
    """
    figures = {figure.get("figureId"): figure for figure in report.get("figures", [])}
    selections = approval.get("selectedFigures")
    require(isinstance(selections, list) and selections, "archived approval selectedFigures are missing")
    require(all(isinstance(item, dict) for item in selections), "archived approval selection is invalid")
    selection_fields = {"figureId", "sourceImageSha256", "routeId", "parameters", "deliverables"}
    for item in selections:
        require(set(item) == selection_fields, "archived approval selection fields are invalid")
    selection_ids = [item.get("figureId") for item in selections]
    require(
        all(isinstance(value, str) and value in figures for value in selection_ids)
        and len(selection_ids) == len(set(selection_ids)),
        "archived approval selected figure scope is invalid",
    )
    require(gate.get("selectedFigures") == selection_ids, "archived gate selectedFigures differ from approval")

    bindings = gate.get("selectedTargets")
    require(
        isinstance(bindings, list) and len(bindings) == len(selections),
        "archived gate selected target count differs from approval",
    )
    binding_fields = {
        "figureId", "targetId", "targetSha256", "workflowMode", "routeId",
        "parameters", "deliverables",
    }
    selected_effects: set[str] = set()
    seen_targets: set[str] = set()
    for selection, binding in zip(selections, bindings):
        require(isinstance(binding, dict) and set(binding) == binding_fields, "archived gate selected target fields are invalid")
        figure_id = selection["figureId"]
        require(binding.get("figureId") == figure_id, f"{figure_id}: gate figure binding differs from approval")
        figure = figures[figure_id]
        target = figure.get("target", {})
        target_id = target.get("targetId")
        require(target_id in targets and target_id not in seen_targets, f"{figure_id}: gate target scope is invalid")
        seen_targets.add(target_id)
        manifest_target = targets[target_id]
        require(
            selection.get("sourceImageSha256") == target.get("targetSha256") == manifest_target.get("targetSha256"),
            f"{figure_id}: approval target hash differs from report/manifest",
        )
        require(binding.get("targetId") == target_id, f"{figure_id}: gate targetId differs from report")
        require(binding.get("targetSha256") == target["targetSha256"], f"{figure_id}: gate target hash differs from approval/report")
        require(
            binding.get("workflowMode") == target.get("workflowMode") == manifest_target.get("workflowMode"),
            f"{figure_id}: gate workflow differs from report/manifest",
        )

        routes = {route.get("routeId"): route for route in figure.get("routes", [])}
        route_id = selection.get("routeId")
        require(
            isinstance(route_id, str)
            and route_id in routes
            and binding.get("routeId") == route_id,
            f"{figure_id}: gate route differs from approval/report",
        )
        route = routes[route_id]
        require(route.get("status") != "blocked" and not route.get("blockers"), f"{figure_id}: archived gate selects a blocked route")

        parameter_values = selection.get("parameters")
        require(isinstance(parameter_values, dict), f"{figure_id}: approval parameters must be an object")
        require(binding.get("parameters") == parameter_values, f"{figure_id}: gate parameters differ from approval")
        parameter_specs = {item.get("parameterId"): item for item in route.get("parameters", [])}
        require(set(parameter_values) <= set(parameter_specs), f"{figure_id}: approval/gate contains an undeclared parameter")
        for parameter_id, spec in parameter_specs.items():
            if spec.get("required"):
                require(parameter_id in parameter_values, f"{figure_id}: approved route is missing required parameter {parameter_id}")
            if parameter_id in parameter_values:
                validate_archived_parameter_value(spec, parameter_values[parameter_id], f"{figure_id}.{parameter_id}")

        deliverables = selection.get("deliverables")
        require(
            isinstance(deliverables, list)
            and bool(deliverables)
            and all(isinstance(item, str) and item for item in deliverables)
            and len(deliverables) == len(set(deliverables)),
            f"{figure_id}: approval deliverables are invalid",
        )
        require(binding.get("deliverables") == deliverables, f"{figure_id}: gate deliverables differ from approval")
        declared_deliverables = {item.get("kind") for item in route.get("deliverables", [])}
        require(set(deliverables) <= declared_deliverables, f"{figure_id}: approval/gate contains an undeclared deliverable")
        route_effects = route.get("effects")
        require(
            isinstance(route_effects, list)
            and all(isinstance(effect, str) and effect for effect in route_effects)
            and len(route_effects) == len(set(route_effects)),
            f"{figure_id}: selected route effects are invalid",
        )
        selected_effects.update(route_effects)

    approval_effects = approval.get("authorizedEffects")
    gate_effects = gate.get("authorizedEffects")
    require(
        isinstance(approval_effects, list)
        and all(isinstance(effect, str) and effect for effect in approval_effects)
        and len(approval_effects) == len(set(approval_effects)),
        "archived approval authorizedEffects are invalid",
    )
    require(
        isinstance(gate_effects, list)
        and all(isinstance(effect, str) and effect for effect in gate_effects)
        and len(gate_effects) == len(set(gate_effects)),
        "archived gate authorizedEffects are invalid",
    )
    require(
        set(approval_effects) == set(gate_effects) == selected_effects,
        "archived authorizedEffects differ from approval or selected report routes",
    )
    require(gate_effects == sorted(gate_effects), "archived gate authorizedEffects must be canonical")

    policy = report.get("approvalPolicy", {})
    allowed_effects = set(policy.get("allowedEffects", [])) | set(policy.get("consentRequiredEffects", []))
    require(selected_effects <= allowed_effects, "archived selected route contains an undeclared effect")
    acknowledgements = approval.get("acknowledgements")
    require(isinstance(acknowledgements, list), "archived approval acknowledgements must be a list")
    acknowledged: set[str] = set()
    created_at = parse_timestamp(approval.get("createdAt"), "archived approval createdAt")
    expires_at = parse_timestamp(approval.get("expiresAt"), "archived approval expiresAt")
    require(created_at < expires_at, "archived approval timestamps are invalid")
    for acknowledgement in acknowledgements:
        require(
            isinstance(acknowledgement, dict)
            and set(acknowledgement) == {"effect", "acceptedAt"},
            "archived approval acknowledgement fields are invalid",
        )
        effect = acknowledgement.get("effect")
        require(isinstance(effect, str) and effect not in acknowledged, "archived approval acknowledgement effect is invalid")
        accepted_at = parse_timestamp(acknowledgement.get("acceptedAt"), "archived acknowledgement acceptedAt")
        require(created_at <= accepted_at <= expires_at, "archived acknowledgement is outside the approval window")
        acknowledged.add(effect)
    expected_acknowledgements = selected_effects & set(policy.get("consentRequiredEffects", []))
    require(
        acknowledged == expected_acknowledgements,
        "archived acknowledgements differ from consent-required selected route effects",
    )


def validate_archived_plan(root: Path, state: dict | None = None) -> dict:
    plan_root = root / "shared/plan"
    if not plan_root.exists():
        if state is not None:
            require(not state.get("gateValidated"), "gated staging bundle is missing archived plan records")
        return {}
    plan_files = {
        path.relative_to(root).as_posix()
        for path in scan_tree(plan_root)[0]
    }
    require(plan_files <= set(PLAN_INPUTS.values()), "archived plan contains an unknown artifact")
    present = {name: relative for name, relative in PLAN_INPUTS.items() if (root / relative).exists()}
    require("target_manifest" in present or not present, "archived report/approval requires a target manifest")
    manifest = read_object(root / PLAN_INPUTS["target_manifest"], "archived target manifest") if "target_manifest" in present else None
    targets: dict[str, dict] = {}
    if manifest is not None:
        require(manifest.get("schemaVersion") == "scirepro.targets/v1", "archived target manifest schema is invalid")
        expected_hash = canonical_embedded_hash(manifest, "integrity", "manifestSha256")
        require(manifest.get("integrity", {}).get("manifestSha256") == expected_hash, "archived target manifest hash mismatch")
        require(manifest.get("targetCount") == len(manifest.get("targets", [])), "archived target count mismatch")
        for target in manifest.get("targets", []):
            require(isinstance(target, dict), "archived target entry must be an object")
            target_id = target.get("targetId")
            require(isinstance(target_id, str) and bool(IDENTIFIER.fullmatch(target_id)), "archived target ID is invalid")
            require(target_id not in targets, "archived target IDs must be unique")
            require(target.get("qaStatus") == "verified", f"{target_id}: archived target is not verified")
            require(target.get("workflowMode") in WORKFLOW_MODES, f"{target_id}: archived target workflow mode is invalid")
            require(isinstance(target.get("targetSha256"), str) and re.fullmatch(r"[0-9a-f]{64}", target["targetSha256"]), f"{target_id}: archived target hash is invalid")
            targets[target_id] = target

    report = read_object(root / PLAN_INPUTS["report"], "archived report") if "report" in present else None
    if report is not None:
        require(manifest is not None, "archived report requires target manifest")
        try:
            validate_phase_one_report(report, allow_built_assets=True)
        except PhaseOneReportError as exc:
            raise BundleError(f"invalid archived report: {exc}") from exc
        report_hash = hashlib.sha256(canonical_report_payload(report)).hexdigest()
        require(report.get("integrity", {}).get("reportSha256") == report_hash, "archived report hash mismatch")
        require(report.get("targetSet", {}).get("targetSetId") == manifest.get("targetSetId"), "archived report target-set mismatch")
        require(report.get("targetSet", {}).get("manifestSha256") == manifest["integrity"]["manifestSha256"], "archived report/manifest hash mismatch")
        report_target_ids = []
        for figure in report.get("figures", []):
            target = figure.get("target", {})
            target_id = target.get("targetId")
            require(target_id in targets and target_id not in report_target_ids, "archived report target scope is invalid")
            source = targets[target_id]
            require(target.get("targetSha256") == source["targetSha256"], f"{target_id}: archived report target hash mismatch")
            require(target.get("workflowMode") == source["workflowMode"], f"{target_id}: archived report workflow mismatch")
            report_target_ids.append(target_id)
        require(set(report_target_ids) == set(targets), "archived report does not bind all manifest targets")

    approval = read_object(root / PLAN_INPUTS["approval"], "archived approval") if "approval" in present else None
    gate = read_object(root / PLAN_INPUTS["gate_result"], "archived gate result") if "gate_result" in present else None
    if approval is not None:
        require(report is not None, "archived approval requires report")
        require(approval.get("schemaVersion") == "reprofig.approval/v1", "archived approval schema is invalid")
        require(approval.get("decision") == "approve", "archived approval decision is not approve")
        require(approval.get("reportId") == report.get("reportId"), "archived approval report ID mismatch")
        require(approval.get("reportSha256") == report["integrity"]["reportSha256"], "archived approval report hash mismatch")
    if gate is not None:
        require(approval is not None, "archived gate result requires approval")
        require(gate.get("schemaVersion") == "scirepro.gate-result/v1" and gate.get("status") == "valid", "archived gate status is invalid")
        require(gate.get("approvalSha256") == sha256_file(root / PLAN_INPUTS["approval"]), "archived gate approval hash mismatch")
        require(gate.get("reportId") == report.get("reportId"), "archived gate report ID mismatch")
        require(gate.get("reportSha256") == report["integrity"]["reportSha256"], "archived gate report hash mismatch")
        require(gate.get("targetManifestSha256") == manifest["integrity"]["manifestSha256"], "archived gate target-manifest hash mismatch")
        require(gate.get("approvalId") == approval.get("approvalId"), "archived gate approval ID mismatch")
        require(gate.get("idempotencyKey") == approval.get("idempotencyKey"), "archived gate idempotency key mismatch")
        require(gate.get("outputPolicy") == approval.get("outputPolicy"), "archived gate output policy mismatch")
        validate_archived_gate_authority(report, approval, gate, targets)

    if state is not None:
        bindings = state.get("planBindings", {})
        require(state.get("gateValidated") == (gate is not None), "staging gate state disagrees with archived records")
        require(bindings.get("targetManifestSha256") == (manifest or {}).get("integrity", {}).get("manifestSha256"), "staging target-manifest binding mismatch")
        require(bindings.get("reportSha256") == (gate or {}).get("reportSha256"), "staging report binding mismatch")
        require(bindings.get("approvalId") == (gate or {}).get("approvalId"), "staging approval binding mismatch")
        require(bindings.get("approvalSha256") == (gate or {}).get("approvalSha256"), "staging approval hash binding mismatch")
        require(
            bindings.get("gateResultSha256")
            == (hashlib.sha256(pretty_json_bytes(gate)).hexdigest() if gate is not None else None),
            "staging gate-result hash binding mismatch",
        )
        require(bindings.get("idempotencyKey") == (gate or {}).get("idempotencyKey"), "staging idempotency binding mismatch")
        state_targets = state.get("targets", [])
        if manifest is not None:
            for item in state_targets:
                target_id = item.get("targetId") if isinstance(item, dict) else None
                require(target_id in targets, f"staging target is absent from archived target manifest: {target_id}")
                require(item.get("targetSha256") == targets[target_id].get("targetSha256"), f"{target_id}: staging target hash binding mismatch")
                require(item.get("workflowMode") == targets[target_id].get("workflowMode"), f"{target_id}: staging target mode binding mismatch")
        if gate is not None:
            gate_scope = [
                (item.get("targetId"), item.get("targetSha256"), item.get("workflowMode"))
                for item in gate.get("selectedTargets", [])
            ]
            state_scope = [
                (item.get("targetId"), item.get("targetSha256"), item.get("workflowMode"))
                for item in state_targets
            ]
            require(state_scope == gate_scope, "staging target scope differs from archived approval gate")
    return present


def validate_terminal_traceability(root: Path, targets: list[dict]) -> None:
    if not any(target["operationalStatus"] in {"complete", "partial"} for target in targets):
        return
    sources = read_object(root / "shared/provenance/sources.json", "sources record")
    require(bool(sources.get("sources")), "completed/partial work requires at least one traceable source")
    environment = read_object(root / "shared/environment/environment.json", "environment record")
    require(environment.get("captureStatus") in {"recorded", "partial"}, "completed/partial work requires a captured environment")
    resources = read_object(root / "shared/execution/resource-usage.json", "resource-usage record")
    require(
        resources.get("measurementStatus") in {"recorded", "partial"},
        "completed/partial work requires recorded or partial resource usage",
    )


def empty_directories(root: Path) -> list[str]:
    files, directories = scan_tree(root)
    children = {directory: 0 for directory in directories}
    for file_path in files:
        children[file_path.parent] = children.get(file_path.parent, 0) + 1
    for directory in directories:
        if directory != root:
            children[directory.parent] = children.get(directory.parent, 0) + 1
    return sorted(directory.relative_to(root).as_posix() for directory, count in children.items() if directory != root and count == 0)


def validate_manifest(
    root: Path,
    *,
    allow_staging_name: bool = False,
    expected_state: dict | None = None,
) -> tuple[dict, list[str]]:
    scan_tree(root)
    name = root.name
    if allow_staging_name:
        require(
            bool(re.fullmatch(r"\.scirepro-run-[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.staging", name)),
            "staging bundle name must be .scirepro-run-<run-id>.staging",
        )
    else:
        require(
            bool(re.fullmatch(r"scirepro-run-[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name)),
            "final bundle name must be scirepro-run-<run-id>",
        )

    root_files, directories = scan_tree(root)
    top_level = {
        path.relative_to(root).parts[0]
        for path in directories + root_files
        if path != root
    }
    unexpected = top_level - ALLOWED_TOP_LEVEL
    require(not unexpected, f"unexpected top-level entries: {', '.join(sorted(unexpected))}")
    require((root / "README.md").is_file(), "bundle is missing README.md")
    require((root / "manifest.json").is_file(), "bundle is missing manifest.json")
    validate_required_json(root)
    require(not empty_directories(root), f"bundle contains empty directories: {', '.join(empty_directories(root))}")

    manifest = read_object(root / "manifest.json", "run manifest")
    required_root_keys = {
        "schemaVersion",
        "bundleId",
        "runId",
        "createdAt",
        "finalizedAt",
        "generator",
        "status",
        "planBindings",
        "scope",
        "targets",
        "shared",
        "rights",
        "files",
        "warnings",
        "errors",
        "integrity",
    }
    require(set(manifest) == required_root_keys, "manifest has missing or unknown top-level fields")
    require(manifest.get("schemaVersion") == BUNDLE_SCHEMA, "unsupported run-bundle schema")
    require(manifest.get("status") in RUN_STATUSES, "manifest status must be terminal")
    require(manifest.get("integrity", {}).get("manifestSha256") == manifest_self_hash(manifest), "manifest self hash mismatch")
    created_at = parse_timestamp(manifest.get("createdAt"), "manifest.createdAt")
    finalized_at = parse_timestamp(manifest.get("finalizedAt"), "manifest.finalizedAt")
    require(finalized_at >= created_at, "manifest.finalizedAt precedes createdAt")
    run_id = manifest.get("runId")
    require(isinstance(run_id, str) and bool(RUN_IDENTIFIER.fullmatch(run_id)), "manifest runId is invalid")
    require(manifest.get("bundleId") == f"scirepro-run-{run_id}", "manifest bundleId/runId mismatch")
    expected_name = f".scirepro-run-{run_id}.staging" if allow_staging_name else f"scirepro-run-{run_id}"
    require(name == expected_name, "directory name does not match manifest runId")

    generator = manifest.get("generator")
    require(
        generator == {"name": "SciRepro", "component": "finalize_run_bundle.py", "schema": 2},
        "manifest generator record is invalid",
    )

    rights = manifest.get("rights")
    require(isinstance(rights, dict), "manifest rights must be an object")
    require(set(rights) == {"distributionClass", "policy", "omissions"}, "manifest rights fields are invalid")
    distribution = rights.get("distributionClass")
    require(distribution in DISTRIBUTION_CLASSES, "invalid distribution class")
    require(isinstance(rights.get("policy"), str) and rights["policy"], "manifest rights policy is required")
    omissions = rights.get("omissions")
    if omissions is not None:
        require(isinstance(omissions, str) and safe_relative(omissions), "manifest omissions path is unsafe")
        require((root / omissions).is_file(), "manifest omissions record is missing")
    validate_sources_rights(root, distribution)

    expected_files = inventory(root)
    declared_files = manifest.get("files")
    require(isinstance(declared_files, list), "manifest files must be an array")
    require(declared_files == expected_files, "manifest inventory does not exactly match regular bundle files")
    require(
        manifest.get("integrity", {}).get("inventorySha256") == canonical_hash(declared_files),
        "manifest inventory hash mismatch",
    )
    targets = target_records(
        root,
        expected_state.get("targets") if expected_state is not None else None,
        distribution_class=distribution,
    )
    validate_terminal_traceability(root, targets)
    require_regular_member(root / "README.md", "README")
    readme = (root / "README.md").read_text(encoding="utf-8")
    require(f"**Status:** {manifest['status']}" in readme, "README status disagrees with manifest")
    require(f"**Distribution:** `{distribution}`" in readme, "README distribution disagrees with manifest")
    require(f"**Finalized:** {manifest['finalizedAt']}" in readme, "README finalized timestamp disagrees with manifest")
    for target in targets:
        row = (
            f"| `{target['targetId']}` | {target['operationalStatus']} | "
            f"{target['validationStatus']} | {target['claimStatus']} |"
        )
        require(row in readme, f"README result row disagrees for {target['targetId']}")
    if (root / "report/index.html").is_file():
        require("(report/index.html)" in readme, "README is missing the local result-report link")
    require(manifest.get("targets") == targets, "manifest target records do not match target result files")
    require(
        manifest.get("scope")
        == {"targetCount": len(targets), "targetIds": [target["targetId"] for target in targets]},
        "manifest scope does not match target records",
    )
    shared = manifest.get("shared")
    require(isinstance(shared, dict), "manifest shared record must be an object")
    require(set(shared) == {"plan", "sources", "environment", "resourceUsage"}, "manifest shared fields are invalid")
    require(shared.get("sources") == "shared/provenance/sources.json", "manifest sources path is invalid")
    require(shared.get("environment") == "shared/environment/environment.json", "manifest environment path is invalid")
    require(shared.get("resourceUsage") == "shared/execution/resource-usage.json", "manifest resource path is invalid")
    require(isinstance(shared.get("plan"), dict), "manifest plan record must be an object")
    archived_plan = validate_archived_plan(root)
    require(shared["plan"] == archived_plan, "manifest plan paths do not match archived plan records")
    for name, relative in shared["plan"].items():
        require(name in PLAN_INPUTS, f"unknown plan artifact: {name}")
        require(relative == PLAN_INPUTS[name] and (root / relative).is_file(), f"invalid plan artifact path: {name}")
    plan_bindings = manifest.get("planBindings")
    require(
        isinstance(plan_bindings, dict)
        and set(plan_bindings)
        == {
            "reportSha256", "targetManifestSha256", "approvalId", "approvalSha256",
            "gateResultSha256", "idempotencyKey",
        },
        "manifest plan bindings are invalid",
    )
    gate = read_object(root / PLAN_INPUTS["gate_result"], "archived gate result") if "gate_result" in archived_plan else None
    archived_target_manifest = (
        read_object(root / PLAN_INPUTS["target_manifest"], "archived target manifest")
        if "target_manifest" in archived_plan else None
    )
    require(plan_bindings.get("reportSha256") == (gate or {}).get("reportSha256"), "manifest report binding mismatch")
    require(
        plan_bindings.get("targetManifestSha256")
        == (archived_target_manifest or {}).get("integrity", {}).get("manifestSha256"),
        "manifest target-manifest binding mismatch",
    )
    require(plan_bindings.get("approvalId") == (gate or {}).get("approvalId"), "manifest approval binding mismatch")
    require(plan_bindings.get("approvalSha256") == (gate or {}).get("approvalSha256"), "manifest approval hash binding mismatch")
    require(
        plan_bindings.get("gateResultSha256")
        == (hashlib.sha256(pretty_json_bytes(gate)).hexdigest() if gate is not None else None),
        "manifest gate-result hash binding mismatch",
    )
    require(plan_bindings.get("idempotencyKey") == (gate or {}).get("idempotencyKey"), "manifest idempotency binding mismatch")
    if gate is not None:
        gate_targets = [
            (item["targetId"], item["workflowMode"], item["targetSha256"], item["routeId"])
            for item in gate["selectedTargets"]
        ]
        actual_targets = [
            (item["targetId"], item["workflowMode"], item["targetSha256"], item["routeId"])
            for item in targets
        ]
        require(actual_targets == gate_targets, "final targets differ from the approval-gate target scope")
    validate_aggregate_status(manifest["status"], targets)
    if manifest["status"] in {"complete", "partial"}:
        validate_result_report(root, manifest)
    elif (root / "report").exists():
        validate_result_report(root, manifest)
    warnings = duplicate_warnings(expected_files)
    require(manifest.get("warnings") == warnings, "manifest warnings do not match current bundle content")
    require(
        isinstance(manifest.get("errors"), list) and all(isinstance(item, str) for item in manifest["errors"]),
        "manifest errors must be an array of strings",
    )
    return manifest, warnings


def finalize_bundle(args: argparse.Namespace) -> Path:
    root = checked_existing_directory(args.bundle, "staging bundle")
    require(root.name.startswith(".scirepro-run-") and root.name.endswith(".staging"), "finalize expects a staging bundle")
    scan_tree(root)
    state_path = root / ".scirepro-staging.json"
    state = read_object(state_path, "staging state")
    require(
        set(state)
        == {
            "schemaVersion", "runId", "bundleId", "createdAt", "distributionClass",
            "gateValidated", "planBindings", "targets",
        },
        "staging state fields are invalid",
    )
    require(state.get("schemaVersion") == STAGING_SCHEMA, "unsupported staging schema")
    require(state.get("distributionClass") in DISTRIBUTION_CLASSES, "invalid staging distribution class")
    require(root.name == f".scirepro-run-{state.get('runId')}.staging", "staging directory/run ID mismatch")
    require(isinstance(state.get("gateValidated"), bool), "staging gateValidated must be boolean")
    require(isinstance(state.get("planBindings"), dict), "staging planBindings must be an object")
    require(isinstance(state.get("targets"), list) and state["targets"], "staging targets must be a non-empty array")
    for item in state["targets"]:
        require(
            isinstance(item, dict)
            and set(item) == {"targetId", "workflowMode", "targetSha256"}
            and isinstance(item.get("targetId"), str)
            and bool(IDENTIFIER.fullmatch(item["targetId"]))
            and item.get("workflowMode") in WORKFLOW_MODES
            and (item.get("targetSha256") is None or re.fullmatch(r"[0-9a-f]{64}", item["targetSha256"])),
            "staging target binding is invalid",
        )
    plan_bindings = state["planBindings"]
    require(
        set(plan_bindings)
        == {
            "reportSha256", "targetManifestSha256", "approvalId", "approvalSha256",
            "gateResultSha256", "idempotencyKey",
        },
        "staging plan bindings are invalid",
    )
    if state["gateValidated"]:
        require(all(plan_bindings.get(key) for key in plan_bindings), "gated staging bundle has incomplete plan bindings")
    validate_archived_plan(root, state)
    report_hash = decision_report_hash(root, plan_bindings)
    if args.status in {"complete", "partial"}:
        require(state["gateValidated"], f"{args.status} bundle requires a successfully validated approval gate")
        require(args.result_report is not None, f"{args.status} bundle requires --result-report")
    require(not (root / "report").exists(), "report/ is owned by finalize; provide the Phase 1 web directory with --result-report")
    report_source = None
    approved_report = archived_approved_report(root)
    if args.result_report is not None:
        report_source = checked_existing_directory(args.result_report, "result-report source")
        require(root not in report_source.parents and report_source != root, "result-report source may not be inside the staging bundle")
        validate_built_decision_report(
            report_source,
            expected_report_sha256=report_hash,
            distribution_class=state["distributionClass"],
            approved_report=approved_report,
        )
    final_path = root.parent / state["bundleId"]
    require(not final_path.exists(), f"final bundle already exists: {final_path}")

    # Fail before touching terminal records when the staging tree already
    # contains a symlink or other unsupported filesystem object.
    relative_files(root, include_manifest=True, include_staging_state=True)
    mutable_paths = [root / "README.md", state_path, root / "manifest.json"]
    mutable_paths.extend(sorted((root / "targets").glob("*/result.json")))
    mutable_paths.extend(sorted((root / "targets").glob("*/validation/summary.json")))
    backups = {}
    for path in mutable_paths:
        if path.exists():
            require_regular_member(path, "mutable staging record")
            backups[path] = path.read_bytes()
        else:
            backups[path] = None
    try:
        terminalize_pending_targets(root, args.status, args.reason)
        finalized_at = now_iso()
        if report_source is not None:
            shutil.copytree(report_source, root / "report/decision", symlinks=False)
            for directory in sorted(
                (path for path in (root / "report/decision").rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                if not any(directory.iterdir()):
                    directory.rmdir()
            validate_built_decision_report(
                root / "report/decision",
                expected_report_sha256=report_hash,
                distribution_class=state["distributionClass"],
                approved_report=approved_report,
            )
            summary = make_result_report_summary(
                root,
                bundle_id=state["bundleId"],
                status=args.status,
                finalized_at=finalized_at,
                report_sha256=report_hash,
                distribution_class=state["distributionClass"],
            )
            write_result_report(root, summary)
        update_readme_status(
            root,
            args.status,
            finalized_at,
            state["targets"],
            state["distributionClass"],
        )
        state_path.unlink()
        manifest_path = root / "manifest.json"
        if manifest_path.exists():
            manifest_path.unlink()
        manifest = build_manifest(root, state, args.status, finalized_at)
        write_json(manifest_path, manifest)
        validate_manifest(root, allow_staging_name=True, expected_state=state)
        atomic_publish_directory(root, final_path)
    except Exception:
        if exists_lstat(root):
            if args.result_report is not None and exists_lstat(root / "report"):
                shutil.rmtree(root / "report", ignore_errors=True)
            for path, payload in backups.items():
                if payload is None:
                    if exists_lstat(path):
                        require_regular_member(path, "rollback staging record")
                        path.unlink()
                else:
                    write_bytes(path, payload)
        raise
    return final_path


def validate_bundle(args: argparse.Namespace) -> tuple[Path, list[str]]:
    root = checked_existing_directory(args.bundle, "run bundle")
    scan_tree(root)
    _, warnings = validate_manifest(root, allow_staging_name=args.allow_staging)
    return root, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="atomically create a staging run bundle")
    init_parser.add_argument(
        "--parent",
        "--output-root",
        dest="parent",
        type=Path,
        default=Path.cwd(),
        help="output root that will contain exactly one scirepro-run-<run-id> directory",
    )
    init_parser.add_argument("--run-id", required=True, help="path-safe run identifier (maximum 64 characters)")
    init_parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="ID[=MODE]",
        help="target ID; repeat/select a subset; omitted means all targets from --target-manifest or --report",
    )
    init_parser.add_argument(
        "--default-mode", choices=sorted(WORKFLOW_MODES), default="scientific-reproduction"
    )
    init_parser.add_argument("--distribution", choices=sorted(DISTRIBUTION_CLASSES), default="local-private")
    init_parser.add_argument("--report", type=Path, help="copy the approved Phase 1 report JSON")
    init_parser.add_argument("--target-manifest", type=Path, help="copy the verified Phase 0 target manifest")
    init_parser.add_argument("--approval", type=Path, help="copy the researcher approval JSON")
    init_parser.add_argument("--gate-result", type=Path, help="copy the successful gate result JSON")
    init_parser.add_argument(
        "--workspace-root",
        type=Path,
        help="workspace root used to resolve an approval outputPolicy.relativeRoot",
    )
    init_parser.add_argument("--json", action="store_true", help="print machine-readable output")

    finalize_parser = subparsers.add_parser("finalize", help="inventory, validate, and atomically publish a terminal bundle")
    finalize_parser.add_argument("--bundle", required=True, type=Path, help=".scirepro-run-<run-id>.staging directory")
    finalize_parser.add_argument("--status", required=True, choices=sorted(RUN_STATUSES))
    finalize_parser.add_argument(
        "--reason",
        help="required when pending targets are finalized as failed, blocked, or cancelled",
    )
    finalize_parser.add_argument(
        "--result-report",
        type=Path,
        help="validated Phase 1 web-report directory to copy and augment with terminal results; required for complete/partial",
    )
    finalize_parser.add_argument("--json", action="store_true", help="print machine-readable output")

    validate_parser = subparsers.add_parser("validate", help="verify layout, statuses, rights, hashes, and inventory")
    validate_parser.add_argument("--bundle", required=True, type=Path, help="final scirepro-run-<run-id> directory")
    validate_parser.add_argument(
        "--allow-staging",
        action="store_true",
        help="validate a fully inventoried staging directory (normally only finalize uses this)",
    )
    validate_parser.add_argument("--json", action="store_true", help="print machine-readable output")
    return parser


def emit(result: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(result["path"])
        for warning in result.get("warnings", []):
            print(f"warning: {warning}", file=sys.stderr)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "init":
            path = initialize_bundle(args)
            emit({"status": "staging", "path": str(path)}, as_json=args.json)
        elif args.command == "finalize":
            path = finalize_bundle(args)
            manifest = read_object(path / "manifest.json", "run manifest")
            emit(
                {"status": manifest["status"], "path": str(path), "warnings": manifest.get("warnings", [])},
                as_json=args.json,
            )
        else:
            path, warnings = validate_bundle(args)
            emit({"status": "valid", "path": str(path), "warnings": warnings}, as_json=args.json)
    except (BundleError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
