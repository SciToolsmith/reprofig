#!/usr/bin/env python3
"""Validate SciRepro report JSON and build a portable scientific investigation report."""

from __future__ import annotations

import argparse
import copy
import hashlib
import ipaddress
import json
import math
import re
import shutil
import sys
import tempfile
import zlib
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, urlsplit

from materialize_target_figures import TargetError as TargetManifestError
from materialize_target_figures import validate_manifest as validate_target_manifest

try:  # Phase 0 already requires Pillow; keep validation imports usable without it.
    from PIL import Image
except ImportError:  # pragma: no cover - depends on the selected local runtime
    Image = None


LEVELS = {
    "direct-recompute",
    "mechanism-reproduction",
    "alternative-validation",
    "editable-reconstruction",
    "image-derived-reconstruction",
    "original-case-blocked",
}
ENVIRONMENT_STATES = {"verified", "available", "unknown", "missing"}
ENVIRONMENT_PROVISIONING = {"existing-only", "isolated-open-source"}
SOURCE_KINDS = {
    "paper", "official-code", "third-party-code", "dataset", "documentation", "skill", "target-image",
    "environment-audit",
}
ACCESS_STATES = {"local", "downloadable", "login-required", "request-required", "controlled", "unavailable", "not-found"}
LICENSE_STATES = {"verified", "declared", "unknown", "restricted"}
REQUIREMENT_CATEGORIES = ["input", "method", "protocol", "validation", "environment"]
REQUIREMENT_STATES = {"verified", "derivable", "assumable", "missing", "not-required"}
REQUIREMENT_RESOLUTION_STATES = {"frozen", "accepted"}
ROUTE_STATES = {"ready", "conditional", "blocked"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
ORIGINS = {"paper", "code", "derived", "assumption", "user"}
VALIDATION_KINDS = {
    "qualitative-pattern",
    "quantitative",
    "comparative",
    "structural",
    "visual-fidelity",
}
FORMULA_CHECK_TYPES = {
    "derivation",
    "self-consistency",
    "dimensions",
    "units",
    "boundary-cases",
    "matrix-shape",
    "code-cross-check",
    "source-cross-check",
    "figure-trend",
}
FORMULA_CHECK_STATUSES = {
    "verified",
    "derived",
    "ambiguous",
    "paper-code-divergence",
    "invalid",
    "not-checkable",
}
FORMULA_IMPLEMENTATION_DECISIONS = {
    "use-as-stated",
    "use-derived",
    "split-routes",
    "freeze-assumption",
    "block",
}
FORMULA_DECISIONS_BY_STATUS = {
    "verified": {"use-as-stated"},
    "derived": {"use-derived"},
    "ambiguous": {"freeze-assumption", "split-routes", "block"},
    "paper-code-divergence": {"split-routes", "block"},
    "invalid": {"use-derived", "block"},
    "not-checkable": {"freeze-assumption", "block"},
}
FORMULA_ROUTE_INTERPRETATIONS = {
    "paper-formula",
    "code-implementation",
    "alternative-derived",
    "as-stated",
    "derived",
    "assumed",
}
FORMULA_INTERPRETATIONS_BY_DECISION = {
    "use-as-stated": {"as-stated", "paper-formula"},
    "use-derived": {"derived", "alternative-derived"},
    "freeze-assumption": {"assumed", "alternative-derived"},
    "split-routes": {"paper-formula", "code-implementation", "alternative-derived"},
    "block": FORMULA_ROUTE_INTERPRETATIONS,
}
CANONICAL_AUTOMATIC_EFFECTS = frozenset({"run-local-code", "create-workspace-files"})
CANONICAL_GATED_EFFECTS = frozenset({
    "network",
    "install",
    "login",
    "payment",
    "upload",
    "overwrite",
    "gpu",
    "shared-license",
    "external-publish",
})
CANONICAL_EFFECTS = CANONICAL_AUTOMATIC_EFFECTS | CANONICAL_GATED_EFFECTS
NETWORK_DEPENDENT_EFFECTS = frozenset({"login", "payment", "upload", "external-publish"})
ESTIMATE_FIELDS = frozenset({"downloadBytes", "diskBytes", "runtimeMinutes", "gpu", "costUsd"})
SAFE_EXTENSIONS = {".png"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
SENSITIVE_KEY = re.compile(
    r"(?i)^(?:authorization|cookie|credentials?|passw(?:or)?d|private[_-]?key|secret|session|token|"
    r"(?:[a-z0-9]+[_-])?api[_-]?key|access[_-]?key(?:[_-]?id)?|client[_-]?secret|secret[_-]?key|"
    r"auth[_-]?token|(?:[a-z0-9]+[_-])?access[_-]?token|(?:[a-z0-9]+[_-])?refresh[_-]?token|"
    r"bearer[_-]?token|session[_-]?token)$"
)
SENSITIVE_QUERY_KEY = re.compile(
    r"(?i)^(?:access[_-]?key|api[_-]?key|auth|authorization|credential|password|secret|signature|sig|token|x-amz-.*)$"
)
UNIX_USER_PATH = re.compile(r"/(?:Users|home)/[^/\s\"']+")
WINDOWS_USER_PATH = re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"']+")
URI_USERINFO = re.compile(r"(?i)(https://)[^/@\s]+@")
SENSITIVE_QUERY = re.compile(
    r"(?i)([?&](?:access[_-]?key|api[_-]?key|auth|authorization|credential|password|secret|signature|sig|token|x-amz-[^=&#\s]+)=)[^&#\s]+"
)
PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----", re.IGNORECASE)
# Detect credential material carried inside otherwise ordinary prose or parameter
# values.  Keep this deliberately assignment/header-shaped so scientific uses of
# words such as "token", "secret", or "authorization" are not rejected.
SECRET_ASSIGNMENT = re.compile(
    r"(?im)(?:^|[\s;,])(?:export\s+)?(?:aws[_-]?access[_-]?key[_-]?id|aws[_-]?secret[_-]?access[_-]?key|"
    r"access[_-]?key(?:[_-]?id)?|(?:[a-z0-9]+[_-])?api[_-]?key|auth[_-]?token|client[_-]?secret|"
    r"credential|passw(?:or)?d|private[_-]?key|secret[_-]?key|(?:[a-z0-9]+[_-])?access[_-]?token|"
    r"(?:[a-z0-9]+[_-])?refresh[_-]?token|bearer[_-]?token|session[_-]?token)"
    r"\s*[:=]\s*(?:['\"])?(?!\[REDACTED\])[^\s,'\";]+"
)
AUTHORIZATION_VALUE = re.compile(r"(?im)\bauthorization\s*:\s*(?:bearer|basic)\s+[A-Za-z0-9+/._~=-]+")
KNOWN_SECRET_VALUE = re.compile(
    r"(?i)(?:\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{20,}\b|\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
    r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b)"
)
GENERIC_UNIX_PATH = re.compile(
    r"(?<![:/A-Za-z0-9])/(?:Users|home|Volumes|private|var|srv|opt|etc|mnt|media|root|tmp)(?:/[^\s\"'<>]*)?"
)
ABSOLUTE_POSIX_PATH = re.compile(r"(?<![:/A-Za-z0-9])/(?:[^\s\"'<>/]+/)+[^\s\"'<>]*")
GENERIC_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:[\\/][^\s\"'<>]*")
UNC_PATH = re.compile(r"\\\\[^\\\s\"']+[\\/][^\s\"']*")
URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>]+")
MAX_ASSET_BYTES = 25 * 1024 * 1024
MAX_REPORT_IMAGE_EDGE = 4096
MAX_TARGETS = 256
ACQUISITION_MODES = {"paper-with-images", "paper-with-figure-references", "images-only"}
WORKFLOW_MODES = {"scientific-reproduction", "image-derived-reconstruction"}


class ReportError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportError(message)


def unique_ids(items: list[dict], key: str, label: str) -> set[str]:
    values: list[str] = []
    for item in items:
        require(isinstance(item, dict), f"{label} entries must be objects")
        value = item.get(key)
        require(isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None, f"invalid {label} ID: {value!r}")
        values.append(value)
    require(len(values) == len(set(values)), f"duplicate {label} ID")
    return set(values)


def string_list(value: object, label: str, *, ids: bool = False, max_items: int = 256) -> list[str]:
    require(isinstance(value, list), f"{label} must be a list")
    require(len(value) <= max_items, f"{label} contains too many items")
    require(all(isinstance(item, str) and item.strip() for item in value), f"{label} must contain non-empty strings")
    if ids:
        require(all(ID_PATTERN.fullmatch(item) is not None for item in value), f"{label} contains an invalid ID")
    require(len(value) == len(set(value)), f"{label} must not contain duplicates")
    return value


def non_empty_string(value: object, label: str, *, max_length: int = 20000) -> str:
    require(isinstance(value, str) and value.strip(), f"{label} must be a non-empty string")
    require(len(value) <= max_length, f"{label} exceeds {max_length} characters")
    return value


def contains_obvious_secret(value: str) -> bool:
    """Return true only for credential-shaped content, not benign prose."""
    return bool(
        PRIVATE_KEY_BLOCK.search(value)
        or AUTHORIZATION_VALUE.search(value)
        or SECRET_ASSIGNMENT.search(value)
        or KNOWN_SECRET_VALUE.search(value)
    )


def require_secret_free(value: object, label: str) -> None:
    if isinstance(value, str):
        require(not contains_obvious_secret(value), f"{label} contains possible credential material")
    elif isinstance(value, dict):
        for child_key, child in value.items():
            require_secret_free(child, f"{label}.{child_key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            require_secret_free(child, f"{label}[{index}]")


def evidence_refs(value: object, label: str, source_ids: set[str]) -> list[str]:
    refs = string_list(value, label, ids=True)
    require(set(refs) <= source_ids, f"{label} contains an unknown source reference")
    return refs


def source_is_usable_evidence(source: dict) -> bool:
    """Exclude citations that are only missing or inaccessible locators."""
    return isinstance(source.get("artifact"), dict) or source.get("access", {}).get("state") in {"local", "downloadable"}


def finite_number(value: object, label: str, *, integer: bool = False, nullable: bool = False) -> int | float | None:
    if value is None and nullable:
        return None
    if integer:
        require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be an integer")
    else:
        require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label} must be a number")
    require(math.isfinite(value), f"{label} must be finite")
    return value


def allow_keys(value: object, allowed: set[str], label: str) -> dict:
    require(isinstance(value, dict), f"{label} must be an object")
    unknown = set(value) - allowed
    require(not unknown, f"{label} contains unknown fields: {sorted(unknown)}")
    return value


def validate_estimate(value: object, route_id: str, effects: set[str]) -> None:
    estimate = allow_keys(value, set(ESTIMATE_FIELDS), f"{route_id} estimate")
    require(set(estimate) == ESTIMATE_FIELDS, f"{route_id}: estimate must declare {sorted(ESTIMATE_FIELDS)}")
    download = finite_number(estimate["downloadBytes"], f"{route_id}: downloadBytes", integer=True, nullable=True)
    disk = finite_number(estimate["diskBytes"], f"{route_id}: diskBytes", integer=True, nullable=True)
    runtime = finite_number(estimate["runtimeMinutes"], f"{route_id}: runtimeMinutes", nullable=True)
    cost = finite_number(estimate["costUsd"], f"{route_id}: costUsd", nullable=True)
    gpu = estimate["gpu"]
    require(isinstance(gpu, bool), f"{route_id}: gpu estimate must be boolean")
    for amount, field in ((download, "downloadBytes"), (disk, "diskBytes"), (runtime, "runtimeMinutes"), (cost, "costUsd")):
        require(amount is None or amount >= 0, f"{route_id}: {field} must be non-negative or null")
    require(not download or "network" in effects, f"{route_id}: a positive download estimate requires the network effect")
    require(("gpu" in effects) == gpu, f"{route_id}: gpu effect and gpu estimate must agree")
    require(not cost or "payment" in effects, f"{route_id}: a positive cost estimate requires the payment effect")
    if effects & NETWORK_DEPENDENT_EFFECTS:
        require("network" in effects, f"{route_id}: external effects also require the network effect")


def requirement_can_run(requirement: dict) -> bool:
    """Return whether a declared requirement is concrete enough to execute."""
    state = requirement.get("state")
    if state in {"verified", "not-required"}:
        return True
    resolution = requirement.get("resolution")
    expected = {"derivable": "frozen", "assumable": "accepted"}.get(state)
    return (
        expected is not None
        and isinstance(resolution, dict)
        and resolution.get("status") == expected
        and isinstance(resolution.get("basis"), str)
        and bool(resolution["basis"].strip())
    )


def estimate_is_bounded(value: dict) -> bool:
    """Return whether the executable route has finite declared resource bounds."""
    return all(value.get(field) is not None for field in ("downloadBytes", "diskBytes", "runtimeMinutes", "costUsd"))


def validate_parameter_spec(parameter: dict, route_id: str) -> None:
    parameter_id = parameter["parameterId"]
    kind = parameter.get("type")
    require(kind in {"string", "number", "integer", "boolean", "enum", "relative-path"}, f"{route_id}: unsupported parameter type")
    require(isinstance(parameter.get("required"), bool), f"{route_id}: parameter required must be boolean")
    require(parameter.get("origin") in ORIGINS, f"{route_id}: invalid parameter origin")
    if "unit" in parameter:
        non_empty_string(parameter["unit"], f"{parameter_id}: unit", max_length=128)

    minimum = maximum = None
    if kind in {"number", "integer"}:
        if "min" in parameter:
            minimum = finite_number(parameter["min"], f"{parameter_id}: min", integer=kind == "integer")
        if "max" in parameter:
            maximum = finite_number(parameter["max"], f"{parameter_id}: max", integer=kind == "integer")
        if minimum is not None and maximum is not None:
            require(minimum <= maximum, f"{parameter_id}: min must not exceed max")
    else:
        require("min" not in parameter and "max" not in parameter, f"{parameter_id}: min/max require a numeric type")

    choices: list[str] | None = None
    if kind == "enum":
        choices = string_list(parameter.get("enum"), f"{parameter_id}: enum", max_items=256)
        require(bool(choices), f"{parameter_id}: enum must not be empty")
    else:
        require("enum" not in parameter, f"{parameter_id}: enum values require enum type")

    if "default" not in parameter:
        return
    default = parameter["default"]
    if kind == "string":
        require(isinstance(default, str) and len(default) <= 4096, f"{parameter_id}: invalid string default")
    elif kind == "relative-path":
        require(isinstance(default, str) and safe_relative(default), f"{parameter_id}: unsafe relative-path default")
    elif kind == "boolean":
        require(isinstance(default, bool), f"{parameter_id}: invalid boolean default")
    elif kind == "integer":
        finite_number(default, f"{parameter_id}: default", integer=True)
    elif kind == "number":
        finite_number(default, f"{parameter_id}: default")
    elif kind == "enum":
        require(isinstance(default, str) and choices is not None and default in choices, f"{parameter_id}: default is not an enum choice")
    if isinstance(default, str):
        require_secret_free(default, f"{parameter_id}: default")
    if kind in {"number", "integer"}:
        if minimum is not None:
            require(default >= minimum, f"{parameter_id}: default is below min")
        if maximum is not None:
            require(default <= maximum, f"{parameter_id}: default is above max")


def safe_relative(value: str) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "%" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith(("/", "//", "~")) or SCHEME_PATTERN.match(normalized):
        return False
    path = PurePosixPath(normalized)
    return not path.is_absolute() and ".." not in path.parts and all(part not in {"", "."} for part in path.parts)


def public_host(hostname: str) -> bool:
    host = hostname.rstrip(".").lower()
    if (
        not host
        or "." not in host
        or host == "localhost"
        or host.endswith((".localhost", ".local", ".internal", ".intranet", ".corp", ".lan", ".home", ".onion"))
    ):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not any((
        address.is_private,
        address.is_loopback,
        address.is_link_local,
        address.is_multicast,
        address.is_reserved,
        address.is_unspecified,
    ))


def validate_url(value: object, label: str) -> None:
    if value is None:
        return
    require(isinstance(value, str), f"{label} must be a string")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ReportError(f"{label} is invalid: {exc}") from exc
    require(parsed.scheme == "https", f"{label} must use https")
    require(bool(parsed.hostname) and public_host(parsed.hostname), f"{label} must use a public host")
    require(not parsed.username and not parsed.password, f"{label} must not contain credentials")
    require(port in {None, 443}, f"{label} must not use a non-HTTPS port")
    # Fragments are never sent to the server, cannot be verified during source
    # auditing, and are commonly used to carry bearer tokens or signed state.
    # Reject even an empty trailing '#', rather than attempting to distinguish
    # benign anchors from secrets.
    require("#" not in value, f"{label} must not contain a URL fragment")
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        require(SENSITIVE_QUERY_KEY.fullmatch(key) is None, f"{label} must not contain a sensitive query parameter")


def validate_report(report: dict, *, allow_built_assets: bool = False) -> None:
    # Validate this before any portable report bytes are written.  The same
    # validation runs again at the approval gate, so a hand-edited report
    # cannot smuggle credentials into approval parameters or gate output.
    require_secret_free(report, "report")
    allow_keys(report, {
        "schemaVersion", "reportId", "generatedAt", "generator", "workflow", "integrity",
        "audience", "targetSet", "paper", "summary", "environment", "sources", "figures", "approvalPolicy",
    }, "report")
    require(report.get("schemaVersion") == "reprofig.report/v3", "unsupported schemaVersion; regenerate legacy reports with the current SciRepro skill")
    require(isinstance(report.get("reportId"), str) and ID_PATTERN.fullmatch(report["reportId"]), "invalid reportId")
    require(report.get("audience") in {"local", "public"}, "report.audience must be local or public")
    workflow = report.get("workflow", {})
    allow_keys(workflow, {"stage", "executionAllowed", "approvalRequired"}, "workflow")
    require(workflow.get("stage") == "awaiting-approval", "workflow.stage must be awaiting-approval")
    require(workflow.get("executionAllowed") is False, "report cannot allow execution")
    require(workflow.get("approvalRequired") is True, "report must require approval")

    environments = report.get("environment", [])
    sources = report.get("sources", [])
    figures = report.get("figures", [])
    require(isinstance(environments, list), "environment must be a list")
    require(isinstance(sources, list), "sources must be a list")
    require(isinstance(figures, list) and 1 <= len(figures) <= MAX_TARGETS, f"report must contain 1-{MAX_TARGETS} targets")

    environment_ids = unique_ids(environments, "environmentId", "environment")
    source_ids = unique_ids(sources, "sourceId", "source")
    sources_by_id = {source["sourceId"]: source for source in sources}
    unique_ids(figures, "figureId", "figure")
    generator = allow_keys(report.get("generator", {}), {"name", "version"}, "generator")
    integrity = allow_keys(report.get("integrity", {}), {"algorithm", "canonicalization", "reportSha256"}, "integrity")
    target_set = allow_keys(report.get("targetSet", {}), {"targetSetId", "manifestSha256", "targetCount", "acquisitionModes"}, "targetSet")
    require(isinstance(target_set.get("targetSetId"), str) and ID_PATTERN.fullmatch(target_set["targetSetId"]), "invalid targetSetId")
    require(isinstance(target_set.get("manifestSha256"), str) and re.fullmatch(r"[0-9a-f]{64}", target_set["manifestSha256"]), "invalid targetSet manifest hash")
    require(
        isinstance(target_set.get("targetCount"), int)
        and not isinstance(target_set["targetCount"], bool)
        and target_set["targetCount"] == len(figures),
        "targetSet targetCount must equal report figures",
    )
    declared_mode_list = string_list(target_set.get("acquisitionModes"), "targetSet.acquisitionModes")
    declared_modes = set(declared_mode_list)
    require(len(declared_mode_list) == len(declared_modes), "targetSet.acquisitionModes must not contain duplicates")
    require(declared_modes and declared_modes <= ACQUISITION_MODES, "targetSet contains an invalid acquisition mode")
    paper_value = report.get("paper")
    require(paper_value is None or isinstance(paper_value, dict), "paper must be an object or null")
    paper = allow_keys(
        paper_value,
        {"paperId", "title", "doi", "citation", "sourcePath", "sourceSha256", "pageCount"},
        "paper",
    ) if paper_value is not None else None
    summary = allow_keys(report.get("summary", {}), {"objective", "overallLevel", "oneLine", "figureCount"}, "summary")
    non_empty_string(generator.get("name"), "generator.name", max_length=256)
    non_empty_string(generator.get("version"), "generator.version", max_length=128)
    require(integrity.get("algorithm") in {None, "sha256"}, "integrity.algorithm must be sha256 when declared")
    require(integrity.get("canonicalization") in {None, "json-sort-keys-v1"}, "unsupported integrity canonicalization")
    if paper is not None:
        non_empty_string(paper.get("paperId"), "paper.paperId", max_length=512)
        non_empty_string(paper.get("title"), "paper.title")
        non_empty_string(paper.get("citation"), "paper.citation")
        if paper.get("sourcePath") is not None:
            non_empty_string(paper["sourcePath"], "paper.sourcePath")
        require(
            isinstance(paper.get("sourceSha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", paper["sourceSha256"]),
            "paper.sourceSha256 must bind the preserved Phase 0 paper",
        )
        require(
            isinstance(paper.get("pageCount"), int)
            and not isinstance(paper["pageCount"], bool)
            and paper["pageCount"] >= 1,
            "paper.pageCount must be a positive integer",
        )
    non_empty_string(summary.get("objective"), "summary.objective")
    require(summary.get("overallLevel") in LEVELS | {"mixed"}, "summary.overallLevel must be a reproduction level or mixed")
    non_empty_string(summary.get("oneLine"), "summary.oneLine")
    require(
        isinstance(summary.get("figureCount"), int)
        and not isinstance(summary["figureCount"], bool)
        and summary["figureCount"] == len(figures),
        "summary.figureCount must equal report figures",
    )
    for environment in environments:
        allow_keys(environment, {"environmentId", "label", "status", "provisioning", "version", "detail", "evidenceRefs"}, f"environment {environment.get('environmentId')}")
        non_empty_string(environment.get("label"), f"environment {environment['environmentId']} label", max_length=1024)
        require(environment.get("status") in ENVIRONMENT_STATES, f"environment {environment['environmentId']}: invalid status")
        require(
            environment.get("provisioning") in ENVIRONMENT_PROVISIONING,
            f"environment {environment['environmentId']}: invalid provisioning policy",
        )
        if environment.get("version") is not None:
            non_empty_string(environment["version"], f"environment {environment['environmentId']} version", max_length=256)
        if environment.get("detail") is not None:
            non_empty_string(environment["detail"], f"environment {environment['environmentId']} detail")
        refs = string_list(environment.get("evidenceRefs", []), f"environment {environment['environmentId']} evidenceRefs", ids=True)
        require(set(refs) <= source_ids, f"environment {environment['environmentId']}: unknown evidence source")
        require(
            environment.get("status") != "verified" or bool(refs),
            f"environment {environment['environmentId']}: verified status requires evidenceRefs",
        )
        if environment.get("status") == "verified":
            require(
                any(
                    sources_by_id[source_id].get("kind") == "environment-audit"
                    and isinstance(sources_by_id[source_id].get("artifact"), dict)
                    and source_is_usable_evidence(sources_by_id[source_id])
                    for source_id in refs
                ),
                f"environment {environment['environmentId']}: verified status requires a hashed environment-audit artifact",
            )
    for source in sources:
        allow_keys(source, {"sourceId", "kind", "title", "publisher", "url", "access", "license", "artifact", "note"}, f"source {source.get('sourceId')}")
        require(source.get("kind") in SOURCE_KINDS, f"source {source['sourceId']}: invalid kind")
        non_empty_string(source.get("title"), f"source {source['sourceId']} title", max_length=1024)
        if source.get("publisher") is not None:
            non_empty_string(source["publisher"], f"source {source['sourceId']} publisher", max_length=1024)
        access = allow_keys(source.get("access", {}), {"state", "checkedAt", "httpStatus", "note"}, f"source {source['sourceId']} access")
        require(access.get("state") in ACCESS_STATES, f"source {source['sourceId']}: invalid access state")
        non_empty_string(access.get("checkedAt"), f"source {source['sourceId']} checkedAt", max_length=64)
        if access.get("httpStatus") is not None:
            status = finite_number(access["httpStatus"], f"source {source['sourceId']} httpStatus", integer=True)
            require(100 <= status <= 599, f"source {source['sourceId']}: invalid HTTP status")
        license_info = allow_keys(source.get("license", {}), {"state", "spdxId", "name", "url"}, f"source {source['sourceId']} license")
        require(license_info.get("state") in LICENSE_STATES, f"source {source['sourceId']}: invalid license state")
        if source.get("artifact") is not None:
            artifact = allow_keys(
                source["artifact"],
                {"sourcePath", "relativePath", "fileName", "mediaType", "sizeBytes", "sha256"},
                f"source {source['sourceId']} artifact",
            )
            required_artifact_fields = {"fileName", "mediaType", "sizeBytes", "sha256"}
            require(
                required_artifact_fields <= set(artifact),
                f"source {source['sourceId']}: artifact is missing stable identity fields",
            )
            non_empty_string(artifact.get("fileName"), f"source {source['sourceId']} artifact fileName", max_length=1024)
            non_empty_string(artifact.get("mediaType"), f"source {source['sourceId']} artifact mediaType", max_length=256)
            size = finite_number(artifact.get("sizeBytes"), f"source {source['sourceId']} artifact sizeBytes", integer=True)
            require(size >= 0, f"source {source['sourceId']}: artifact sizeBytes must be non-negative")
            require(
                isinstance(artifact.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]),
                f"source {source['sourceId']}: artifact sha256 must be a lowercase SHA-256 digest",
            )
            relative_path = artifact.get("relativePath")
            if relative_path is not None:
                require(safe_relative(relative_path), f"source {source['sourceId']}: artifact relativePath is unsafe")
            require(
                relative_path is None,
                f"source {source['sourceId']}: source artifacts are not copied by the report builder; omit relativePath",
            )
            source_path = artifact.get("sourcePath")
            if allow_built_assets:
                require(source_path is None, f"source {source['sourceId']}: built report must not retain artifact sourcePath")
            else:
                non_empty_string(source_path, f"source {source['sourceId']} artifact sourcePath")
                candidate = Path(source_path).expanduser()
                require(not candidate.is_symlink(), f"source {source['sourceId']}: artifact sourcePath cannot be a symlink")
                resolved = candidate.resolve()
                require(resolved.is_file(), f"source {source['sourceId']}: artifact sourcePath does not exist")
                require(resolved.stat().st_size == size, f"source {source['sourceId']}: artifact size mismatch")
                require(sha256_file(resolved) == artifact["sha256"], f"source {source['sourceId']}: artifact hash mismatch")
        validate_url(source.get("url"), f"source {source['sourceId']} URL")
        validate_url(source.get("license", {}).get("url"), f"source {source['sourceId']} license URL")

    policy = report.get("approvalPolicy", {})
    allow_keys(policy, {"minFigures", "maxFigures", "defaultOutputPolicy", "allowedEffects", "consentRequiredEffects", "ttlMinutes"}, "approvalPolicy")
    minimum = finite_number(policy.get("minFigures"), "approvalPolicy.minFigures", integer=True)
    maximum = finite_number(policy.get("maxFigures"), "approvalPolicy.maxFigures", integer=True)
    ttl = finite_number(policy.get("ttlMinutes"), "approvalPolicy.ttlMinutes", integer=True)
    require(1 <= minimum <= maximum <= len(figures), "approvalPolicy bounds must be within the materialized target set")
    require(1 <= ttl <= 10080, "approvalPolicy.ttlMinutes must be between 1 and 10080")
    require(policy.get("defaultOutputPolicy") == "create-only", "approvalPolicy.defaultOutputPolicy must be create-only")
    allowed_effects = set(string_list(policy.get("allowedEffects"), "approvalPolicy.allowedEffects", ids=True))
    consent_effects = set(string_list(policy.get("consentRequiredEffects"), "approvalPolicy.consentRequiredEffects", ids=True))
    require(allowed_effects <= CANONICAL_AUTOMATIC_EFFECTS, "allowedEffects contains an unknown or gated effect")
    require(consent_effects <= CANONICAL_GATED_EFFECTS, "consentRequiredEffects contains an unknown or automatic effect")
    require(not (allowed_effects & consent_effects), "automatic and consent-required effects must be disjoint")

    route_ids_global: set[str] = set()
    target_ids_global: list[str] = []
    actual_modes: set[str] = set()
    for figure in figures:
        figure_id = figure["figureId"]
        figure_fields = {
            "figureId", "label", "page", "section", "caption", "target", "image", "understanding",
            "generationLogic", "validationTargets", "reproduction", "requirements", "routes", "sourceRefs",
        }
        allow_keys(figure, figure_fields, f"figure {figure_id}")
        require(set(figure) == figure_fields, f"{figure_id}: figure must declare all scientific report fields")
        non_empty_string(figure.get("label"), f"{figure_id} label", max_length=256)
        non_empty_string(figure.get("caption"), f"{figure_id} caption")
        if figure.get("section") is not None:
            non_empty_string(figure["section"], f"{figure_id} section", max_length=1024)

        target_fields = {"targetId", "acquisitionMode", "workflowMode", "requestedRef", "targetSha256", "materialization"}
        target = allow_keys(figure.get("target", {}), target_fields, f"{figure_id} target")
        require(set(target) == target_fields, f"{figure_id}: target fields are incomplete")
        require(isinstance(target.get("targetId"), str) and ID_PATTERN.fullmatch(target["targetId"]), f"{figure_id}: invalid targetId")
        require(target.get("acquisitionMode") in ACQUISITION_MODES, f"{figure_id}: invalid acquisition mode")
        require(target.get("workflowMode") in WORKFLOW_MODES, f"{figure_id}: invalid workflow mode")
        target_ids_global.append(target["targetId"])
        actual_modes.add(target["acquisitionMode"])
        if target["acquisitionMode"] == "images-only":
            require(
                target["workflowMode"] == "image-derived-reconstruction",
                f"{figure_id}: images-only acquisition requires image-derived-reconstruction",
            )
        else:
            require(
                target["workflowMode"] == "scientific-reproduction",
                f"{figure_id}: a paper-grounded acquisition requires scientific-reproduction",
            )
        if target.get("requestedRef") is not None:
            non_empty_string(target["requestedRef"], f"{figure_id}: requestedRef", max_length=1024)
        require(isinstance(target.get("targetSha256"), str) and re.fullmatch(r"[0-9a-f]{64}", target["targetSha256"]), f"{figure_id}: invalid target SHA-256")
        materialization_fields = {"method", "qaStatus", "page", "renderDpi", "captionIncluded", "sourceFileName", "figureReference", "cropBoxPdfPoints", "width", "height"}
        materialization = allow_keys(target.get("materialization", {}), materialization_fields, f"{figure_id} materialization")
        require(set(materialization) == materialization_fields, f"{figure_id}: materialization fields are incomplete")
        non_empty_string(materialization.get("method"), f"{figure_id}: materialization method", max_length=256)
        require(materialization.get("qaStatus") == "verified", f"{figure_id}: Phase 0 target must be visually verified")
        if materialization.get("page") is not None:
            require(
                isinstance(materialization["page"], int)
                and not isinstance(materialization["page"], bool)
                and materialization["page"] >= 1,
                f"{figure_id}: invalid paper page",
            )
        require(
            isinstance(materialization.get("renderDpi"), int)
            and not isinstance(materialization["renderDpi"], bool)
            and 72 <= materialization["renderDpi"] <= 600,
            f"{figure_id}: invalid render DPI",
        )
        require(isinstance(materialization.get("captionIncluded"), bool), f"{figure_id}: captionIncluded must be boolean")
        for dimension in ("width", "height"):
            require(
                isinstance(materialization.get(dimension), int)
                and not isinstance(materialization[dimension], bool)
                and materialization[dimension] > 0,
                f"{figure_id}: invalid target {dimension}",
            )
        if target["workflowMode"] == "scientific-reproduction":
            require(paper is not None, f"{figure_id}: scientific reproduction requires a paper")
        elif paper is None:
            require(target["acquisitionMode"] == "images-only", f"{figure_id}: a paperless target must use images-only acquisition")

        source_refs = evidence_refs(figure.get("sourceRefs"), f"{figure_id} sourceRefs", source_ids)
        require(bool(source_refs), f"{figure_id}: at least one figure source reference is required")

        image = allow_keys(figure.get("image", {}), {"sourcePath", "relativePath", "sourceRef", "redistributionAllowed", "bundleState", "mediaType", "width", "height", "sizeBytes", "sha256", "metadataStripped", "displayProxy"}, f"{figure_id} image")
        if image.get("sourceRef") is not None:
            require(image["sourceRef"] in source_ids, f"{figure_id}: image sourceRef does not resolve")
        if image.get("mediaType") is not None:
            require(image["mediaType"] == "image/png", f"{figure_id}: only image/png figure assets are supported")
        if image.get("sourcePath") is not None:
            non_empty_string(image["sourcePath"], f"{figure_id} image sourcePath")
            require(image.get("mediaType") == "image/png", f"{figure_id}: bundled figure assets must declare mediaType image/png")
            require(image.get("relativePath") is None, f"{figure_id}: relativePath is builder output and cannot accompany sourcePath")
            require("displayProxy" not in image, f"{figure_id}: displayProxy is builder output")
        elif allow_built_assets and image.get("relativePath") is not None:
            require(safe_relative(image["relativePath"]), f"{figure_id}: unsafe built image relativePath")
            require(image["relativePath"] == f"assets/{figure_id}.png", f"{figure_id}: built image path must be assets/{figure_id}.png")
            require(image.get("mediaType") == "image/png", f"{figure_id}: built figure assets must declare mediaType image/png")
            require(isinstance(image.get("sizeBytes"), int) and image["sizeBytes"] > 0, f"{figure_id}: built image sizeBytes is invalid")
            require(isinstance(image.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", image["sha256"]), f"{figure_id}: built image SHA-256 is invalid")
            require(image.get("metadataStripped") is True, f"{figure_id}: built image must record metadata stripping")
            require(isinstance(image.get("displayProxy"), bool), f"{figure_id}: built image displayProxy must be boolean")
            require(image.get("bundleState") in {"embedded-local", "embedded-public"}, f"{figure_id}: embedded image has invalid bundleState")
            require(image.get("bundleState") == ("embedded-local" if report["audience"] == "local" else "embedded-public"), f"{figure_id}: bundleState does not match report audience")
        elif allow_built_assets and image.get("bundleState") == "omitted-rights":
            require(report["audience"] == "public", f"{figure_id}: local reports may not omit Phase 0 targets")
            require(image.get("relativePath") is None and image.get("sha256") is None, f"{figure_id}: omitted target may not carry a bundled asset")
        else:
            require(image.get("sourcePath") is not None, f"{figure_id}: report input must bind a Phase 0 target image")

        understanding_fields = {
            "visualSummary", "observations", "paperClaim", "evidenceRole", "authorInterpretation", "limitations",
        }
        understanding = allow_keys(figure.get("understanding", {}), understanding_fields, f"{figure_id} understanding")
        require(set(understanding) == understanding_fields, f"{figure_id}: understanding must declare {sorted(understanding_fields)}")
        non_empty_string(understanding.get("visualSummary"), f"{figure_id} visualSummary")
        if target["workflowMode"] == "scientific-reproduction":
            non_empty_string(understanding.get("paperClaim"), f"{figure_id} paperClaim")
            non_empty_string(understanding.get("evidenceRole"), f"{figure_id} evidenceRole")
            non_empty_string(understanding.get("authorInterpretation"), f"{figure_id} authorInterpretation")
        else:
            require(understanding.get("paperClaim") is None, f"{figure_id}: image-derived reconstruction cannot assert a paper claim")
            require(understanding.get("authorInterpretation") is None, f"{figure_id}: image-derived reconstruction cannot assert an author interpretation")
            if understanding.get("evidenceRole") is not None:
                non_empty_string(understanding["evidenceRole"], f"{figure_id} visual reconstruction scope")
        string_list(understanding.get("limitations"), f"{figure_id} limitations", max_items=32)

        observations = understanding.get("observations")
        require(isinstance(observations, list) and 1 <= len(observations) <= 32, f"{figure_id}: 1-32 observations are required")
        observation_ids = unique_ids(observations, "observationId", f"{figure_id} observation")
        observation_fields = {"observationId", "location", "statement", "confidence", "evidenceRefs"}
        for observation in observations:
            observation_id = observation["observationId"]
            allow_keys(observation, observation_fields, f"observation {observation_id}")
            require(set(observation) == observation_fields, f"{observation_id}: observation fields are incomplete")
            non_empty_string(observation.get("location"), f"{observation_id} location", max_length=1024)
            non_empty_string(observation.get("statement"), f"{observation_id} statement")
            require(observation.get("confidence") in CONFIDENCE_LEVELS, f"{observation_id}: invalid confidence")
            refs = evidence_refs(observation.get("evidenceRefs"), f"{observation_id} evidenceRefs", source_ids)
            require(bool(refs), f"{observation_id}: at least one evidence reference is required")

        generation_fields = {"inputs", "steps", "plotMapping", "unknowns", "formulaAudit"}
        required_generation_fields = generation_fields - {"formulaAudit"}
        generation = allow_keys(figure.get("generationLogic", {}), generation_fields, f"{figure_id} generationLogic")
        require(
            required_generation_fields <= set(generation),
            f"{figure_id}: generationLogic must declare {sorted(required_generation_fields)}",
        )
        generation_inputs = generation.get("inputs")
        require(isinstance(generation_inputs, list) and 1 <= len(generation_inputs) <= 32, f"{figure_id}: 1-32 generation inputs are required")
        input_ids = unique_ids(generation_inputs, "inputId", f"{figure_id} generation input")
        input_fields = {"inputId", "label", "description", "origin", "evidenceRefs"}
        for generation_input in generation_inputs:
            input_id = generation_input["inputId"]
            allow_keys(generation_input, input_fields, f"generation input {input_id}")
            require(set(generation_input) == input_fields, f"{input_id}: generation input fields are incomplete")
            non_empty_string(generation_input.get("label"), f"{input_id} label", max_length=1024)
            non_empty_string(generation_input.get("description"), f"{input_id} description")
            require(generation_input.get("origin") in ORIGINS, f"{input_id}: invalid origin")
            refs = evidence_refs(generation_input.get("evidenceRefs"), f"{input_id} evidenceRefs", source_ids)
            require(bool(refs), f"{input_id}: at least one evidence reference is required")

        generation_steps = generation.get("steps")
        require(isinstance(generation_steps, list) and 1 <= len(generation_steps) <= 64, f"{figure_id}: 1-64 generation steps are required")
        step_ids = unique_ids(generation_steps, "stepId", f"{figure_id} generation step")
        require(not (input_ids & step_ids), f"{figure_id}: generation input and step IDs must be distinct")
        step_fields = {"stepId", "label", "description", "origin", "evidenceRefs"}
        for step in generation_steps:
            step_id = step["stepId"]
            allow_keys(step, step_fields, f"generation step {step_id}")
            require(set(step) == step_fields, f"{step_id}: generation step fields are incomplete")
            non_empty_string(step.get("label"), f"{step_id} label", max_length=1024)
            non_empty_string(step.get("description"), f"{step_id} description")
            require(step.get("origin") in ORIGINS, f"{step_id}: invalid origin")
            refs = evidence_refs(step.get("evidenceRefs"), f"{step_id} evidenceRefs", source_ids)
            require(bool(refs), f"{step_id}: at least one evidence reference is required")

        plot_fields = {"description", "encodings", "evidenceRefs"}
        plot_mapping = allow_keys(generation.get("plotMapping", {}), plot_fields, f"{figure_id} plotMapping")
        require(set(plot_mapping) == plot_fields, f"{figure_id}: plotMapping fields are incomplete")
        non_empty_string(plot_mapping.get("description"), f"{figure_id} plotMapping description")
        string_list(plot_mapping.get("encodings"), f"{figure_id} plot encodings", max_items=32)
        refs = evidence_refs(plot_mapping.get("evidenceRefs"), f"{figure_id} plotMapping evidenceRefs", source_ids)
        require(bool(refs), f"{figure_id}: plotMapping requires at least one evidence reference")
        string_list(generation.get("unknowns"), f"{figure_id} generation unknowns", max_items=32)

        formula_audit = generation.get("formulaAudit")
        formula_route_bindings: list[tuple[str, str, str, list[dict[str, str]]]] = []
        if formula_audit is not None:
            audit_fields = {"scope", "included", "excluded", "rationale", "items"}
            audit = allow_keys(formula_audit, audit_fields, f"{figure_id} formulaAudit")
            require(set(audit) == audit_fields, f"{figure_id}: formulaAudit fields are incomplete")
            require(
                audit.get("scope") == "target-chain-only",
                f"{figure_id}: formulaAudit scope must be target-chain-only",
            )
            included = string_list(audit.get("included"), f"{figure_id} formulaAudit included", max_items=32)
            string_list(audit.get("excluded"), f"{figure_id} formulaAudit excluded", max_items=32)
            require(bool(included), f"{figure_id}: formulaAudit must name at least one relevant dependency")
            non_empty_string(audit.get("rationale"), f"{figure_id} formulaAudit rationale")
            items = audit.get("items")
            require(isinstance(items, list) and 1 <= len(items) <= 32, f"{figure_id}: formulaAudit requires 1-32 items")
            unique_ids(items, "checkId", f"{figure_id} formula check")
            item_fields = {
                "checkId", "label", "dependency", "sourceStatement", "checks", "status", "finding",
                "implementationDecision", "routeBindings", "evidenceRefs",
            }
            for item in items:
                check_id = item["checkId"]
                allow_keys(item, item_fields, f"formula check {check_id}")
                require(set(item) == item_fields, f"{check_id}: formula check fields are incomplete")
                for field in ("label", "dependency", "sourceStatement", "finding"):
                    non_empty_string(item.get(field), f"{check_id} {field}")
                checks = set(string_list(item.get("checks"), f"{check_id} checks", ids=True, max_items=16))
                require(bool(checks), f"{check_id}: at least one check is required")
                require(checks <= FORMULA_CHECK_TYPES, f"{check_id}: unsupported formula check type")
                status = item.get("status")
                decision = item.get("implementationDecision")
                require(status in FORMULA_CHECK_STATUSES, f"{check_id}: invalid formula check status")
                require(decision in FORMULA_IMPLEMENTATION_DECISIONS, f"{check_id}: invalid implementation decision")
                require(
                    decision in FORMULA_DECISIONS_BY_STATUS[status],
                    f"{check_id}: {status} cannot use implementation decision {decision}",
                )
                if decision == "use-derived":
                    require(
                        "derivation" in checks,
                        f"{check_id}: use-derived requires an explicit derivation check",
                    )
                route_bindings = item.get("routeBindings")
                require(isinstance(route_bindings, list) and len(route_bindings) <= 16, f"{check_id} routeBindings must be a list")
                for binding in route_bindings:
                    allow_keys(binding, {"routeId", "interpretation"}, f"{check_id} route binding")
                    require(set(binding) == {"routeId", "interpretation"}, f"{check_id}: route binding fields are incomplete")
                    require(
                        isinstance(binding.get("routeId"), str) and ID_PATTERN.fullmatch(binding["routeId"]) is not None,
                        f"{check_id}: route binding contains an invalid routeId",
                    )
                    require(
                        binding.get("interpretation") in FORMULA_ROUTE_INTERPRETATIONS,
                        f"{check_id}: route binding has an invalid interpretation",
                    )
                    require(
                        binding["interpretation"] in FORMULA_INTERPRETATIONS_BY_DECISION[decision],
                        f"{check_id}: interpretation {binding['interpretation']} is incompatible with {decision}",
                    )
                route_refs = [binding["routeId"] for binding in route_bindings]
                require(len(route_refs) == len(set(route_refs)), f"{check_id}: routeBindings must not repeat a routeId")
                if decision == "split-routes":
                    require(
                        len(route_refs) >= 2,
                        f"{check_id}: split-routes requires at least two distinct bound routes",
                    )
                elif decision != "block":
                    require(
                        len(route_refs) == 1,
                        f"{check_id}: {decision} must bind exactly one route interpretation",
                    )
                formula_route_bindings.append((check_id, status, decision, route_bindings))
                refs = evidence_refs(item.get("evidenceRefs"), f"{check_id} evidenceRefs", source_ids)
                require(bool(refs), f"{check_id}: at least one evidence reference is required")

        validation_targets = figure.get("validationTargets")
        require(isinstance(validation_targets, list) and 1 <= len(validation_targets) <= 32, f"{figure_id}: 1-32 validation targets are required")
        validation_target_ids = unique_ids(validation_targets, "targetId", f"{figure_id} validation target")
        validation_fields = {"targetId", "label", "kind", "origin", "observable", "criterion", "supportsClaim", "evidenceRefs"}
        for validation_target in validation_targets:
            validation_target_id = validation_target["targetId"]
            allow_keys(validation_target, validation_fields, f"validation target {validation_target_id}")
            require(set(validation_target) == validation_fields, f"{validation_target_id}: validation target fields are incomplete")
            non_empty_string(validation_target.get("label"), f"{validation_target_id} label", max_length=1024)
            require(validation_target.get("kind") in VALIDATION_KINDS, f"{validation_target_id}: invalid validation kind")
            require(validation_target.get("origin") in ORIGINS, f"{validation_target_id}: invalid validation origin")
            non_empty_string(validation_target.get("observable"), f"{validation_target_id} observable")
            non_empty_string(validation_target.get("criterion"), f"{validation_target_id} criterion")
            non_empty_string(validation_target.get("supportsClaim"), f"{validation_target_id} supportsClaim")
            refs = evidence_refs(validation_target.get("evidenceRefs"), f"{validation_target_id} evidenceRefs", source_ids)
            require(bool(refs), f"{validation_target_id}: at least one evidence reference is required")

        reproduction_fields = {"level", "verdict", "confidence", "assessment", "recommendedRouteId"}
        reproduction = allow_keys(figure.get("reproduction", {}), reproduction_fields, f"{figure_id} reproduction")
        require(set(reproduction) == reproduction_fields, f"{figure_id}: reproduction fields are incomplete")
        require(reproduction.get("level") in LEVELS, f"{figure_id}: invalid reproduction level")
        if target["workflowMode"] == "image-derived-reconstruction":
            require(
                reproduction.get("level") == "image-derived-reconstruction",
                f"{figure_id}: image-derived workflow must use the image-derived reproduction level",
            )
        else:
            require(
                reproduction.get("level") != "image-derived-reconstruction",
                f"{figure_id}: scientific workflow cannot use the image-derived reproduction level",
            )
        require(reproduction.get("confidence") in CONFIDENCE_LEVELS, f"{figure_id}: invalid confidence")
        non_empty_string(reproduction.get("verdict"), f"{figure_id} reproduction verdict")
        non_empty_string(reproduction.get("assessment"), f"{figure_id} reproduction assessment")

        requirements = figure.get("requirements", [])
        require(isinstance(requirements, list) and 5 <= len(requirements) <= 80, f"{figure_id}: 5-80 route requirements are required")
        requirement_ids = unique_ids(requirements, "requirementId", f"{figure_id} requirement")
        requirement_fields = {
            "requirementId", "category", "label", "state", "blocking", "detail", "evidenceRefs", "resolution",
        }
        required_requirement_fields = requirement_fields - {"resolution"}
        for requirement in requirements:
            requirement_id = requirement["requirementId"]
            allow_keys(requirement, requirement_fields, f"{figure_id} requirement {requirement_id}")
            require(required_requirement_fields <= set(requirement), f"{requirement_id}: requirement fields are incomplete")
            non_empty_string(requirement.get("label"), f"{requirement_id} label", max_length=1024)
            non_empty_string(requirement.get("detail"), f"{requirement_id} detail")
            require(requirement.get("category") in REQUIREMENT_CATEGORIES, f"{requirement_id}: invalid requirement category")
            require(requirement.get("state") in REQUIREMENT_STATES, f"{figure_id}: invalid requirement state")
            require(isinstance(requirement.get("blocking"), bool), f"{requirement_id}: blocking must be boolean")
            require(
                requirement.get("state") != "missing" or requirement.get("blocking") is True,
                f"{requirement_id}: a missing condition must be blocking",
            )
            resolution = requirement.get("resolution")
            if resolution is not None:
                allow_keys(resolution, {"status", "basis"}, f"{requirement_id} resolution")
                require(set(resolution) == {"status", "basis"}, f"{requirement_id}: resolution fields are incomplete")
                require(
                    requirement.get("state") in {"derivable", "assumable"},
                    f"{requirement_id}: only derivable or assumable conditions may carry a resolution",
                )
                require(
                    resolution.get("status") in REQUIREMENT_RESOLUTION_STATES,
                    f"{requirement_id}: invalid resolution status",
                )
                expected_resolution = {"derivable": "frozen", "assumable": "accepted"}[requirement["state"]]
                require(
                    resolution.get("status") == expected_resolution,
                    f"{requirement_id}: {requirement['state']} requirements require a {expected_resolution} resolution",
                )
                non_empty_string(resolution.get("basis"), f"{requirement_id} resolution basis")
            refs = evidence_refs(requirement.get("evidenceRefs"), f"{requirement_id} evidenceRefs", source_ids)
            state = requirement.get("state")
            require(
                state not in {"verified", "derivable", "assumable"} or bool(refs) or resolution is not None,
                f"{requirement_id}: {state} requirement needs evidenceRefs or a documented resolution",
            )
            if state == "verified":
                require(
                    all(source_is_usable_evidence(sources_by_id[source_id]) for source_id in refs),
                    f"{requirement_id}: verified evidence must cite a local, downloadable, or archived source",
                )

        requirements_by_id = {item["requirementId"]: item for item in requirements}

        routes = figure.get("routes", [])
        require(isinstance(routes, list) and 1 <= len(routes) <= 16, f"{figure_id}: 1-16 routes are required")
        route_ids = unique_ids(routes, "routeId", f"{figure_id} route")
        routes_by_id = {route["routeId"]: route for route in routes}
        require(not (route_ids_global & route_ids), "route IDs must be unique across the report")
        route_ids_global |= route_ids
        recommended = reproduction.get("recommendedRouteId")
        if recommended is not None:
            require(recommended in route_ids, f"{figure_id}: recommended route does not exist")

        recommended_flags: set[str] = set()
        non_blocked_route_ids: set[str] = set()
        route_fields = {
            "routeId", "label", "status", "recommended", "scientificScope", "engine", "environmentIds",
            "requirementIds", "deliverables", "parameters", "effects", "estimated", "plan", "blockers",
        }
        scope_fields = {
            "goal", "reproducesObservationIds", "claimCoverage", "doesNotReproduce", "substitutions",
            "assumptions", "validationTargetIds", "recommendationRationale",
        }
        for route in routes:
            route_id = route["routeId"]
            allow_keys(route, route_fields, f"route {route_id}")
            require(set(route) == route_fields, f"{route_id}: route fields are incomplete")
            non_empty_string(route.get("label"), f"{route_id} label", max_length=1024)
            require(route.get("status") in ROUTE_STATES, f"{route_id}: invalid route status")
            require(isinstance(route.get("recommended"), bool), f"{route_id}: recommended must be boolean")
            if route["status"] != "blocked":
                non_blocked_route_ids.add(route_id)
            if route["recommended"]:
                recommended_flags.add(route_id)
            if route_id == recommended:
                require(route.get("status") != "blocked", f"{route_id}: recommended route cannot be blocked")

            scope = allow_keys(route.get("scientificScope", {}), scope_fields, f"{route_id} scientificScope")
            require(set(scope) == scope_fields, f"{route_id}: scientificScope fields are incomplete")
            non_empty_string(scope.get("goal"), f"{route_id} scientific goal")
            non_empty_string(scope.get("claimCoverage"), f"{route_id} claimCoverage")
            non_empty_string(scope.get("recommendationRationale"), f"{route_id} recommendationRationale")
            reproduced_observations = string_list(scope.get("reproducesObservationIds"), f"{route_id} reproducesObservationIds", ids=True, max_items=32)
            target_refs = string_list(scope.get("validationTargetIds"), f"{route_id} validationTargetIds", ids=True, max_items=32)
            require(set(reproduced_observations) <= observation_ids, f"{route_id}: unknown observation in scientific scope")
            require(set(target_refs) <= validation_target_ids, f"{route_id}: unknown validation target in scientific scope")
            string_list(scope.get("doesNotReproduce"), f"{route_id} doesNotReproduce", max_items=32)
            string_list(scope.get("substitutions"), f"{route_id} substitutions", max_items=32)
            string_list(scope.get("assumptions"), f"{route_id} assumptions", max_items=32)
            if route["status"] != "blocked":
                require(bool(reproduced_observations), f"{route_id}: a non-blocked route must reproduce at least one observation")
                require(bool(target_refs), f"{route_id}: a non-blocked route must select at least one validation target")

            plan = string_list(route.get("plan"), f"{route_id} plan", max_items=5)
            blockers = string_list(route.get("blockers"), f"{route_id} blockers", max_items=32)
            if route["status"] == "blocked":
                require(bool(blockers), f"{route_id}: a blocked route must explain at least one blocker")
            else:
                require(bool(plan), f"{route_id}: a non-blocked route needs an execution plan")
                require(not blockers, f"{route_id}: a non-blocked route cannot declare blockers")
            require(not any(key in route for key in ("command", "commands", "shell", "script")), f"{route_id}: executable commands are forbidden in reports")
            non_empty_string(route.get("engine"), f"{route_id} engine", max_length=1024)
            environment_refs = string_list(route.get("environmentIds"), f"{route_id} environmentIds", ids=True)
            requirement_refs = string_list(route.get("requirementIds"), f"{route_id} requirementIds", ids=True)
            require(set(environment_refs) <= environment_ids, f"{route_id}: unknown environment reference")
            require(set(requirement_refs) <= requirement_ids, f"{route_id}: unknown requirement reference")
            require(
                len(requirement_refs) >= len(REQUIREMENT_CATEGORIES),
                f"{route_id}: route requirements must cover all five readiness categories",
            )
            require(
                {
                    requirements_by_id[requirement_id]["category"]
                    for requirement_id in requirement_refs
                } == set(REQUIREMENT_CATEGORIES),
                f"{route_id}: requirements must cover {REQUIREMENT_CATEGORIES}; categories may contain multiple conditions",
            )
            if route["status"] != "blocked":
                require(
                    not any(requirements_by_id[requirement_id]["blocking"] for requirement_id in requirement_refs),
                    f"{route_id}: a non-blocked route cannot reference a blocking requirement",
                )
                require(
                    all(requirement_can_run(requirements_by_id[requirement_id]) for requirement_id in requirement_refs),
                    f"{route_id}: an executable route contains an unresolved requirement",
                )
            effects = set(string_list(route.get("effects"), f"{route_id} effects", ids=True))
            require(effects <= CANONICAL_EFFECTS, f"{route_id}: unknown canonical effect")
            require(effects <= allowed_effects | consent_effects, f"{route_id}: undeclared effect")
            referenced_environments = [
                environment for environment in environments if environment["environmentId"] in environment_refs
            ]
            referenced_environment_states = {environment["status"] for environment in referenced_environments}
            if route["status"] == "ready":
                require(
                    referenced_environment_states <= {"verified"},
                    f"{route_id}: a ready route requires route-level verified environments",
                )
            elif route["status"] == "conditional":
                unresolved_environments = [
                    environment
                    for environment in referenced_environments
                    if environment["status"] in {"unknown", "missing"}
                ]
                require(
                    not any(environment["provisioning"] == "existing-only" for environment in unresolved_environments),
                    f"{route_id}: an unknown or missing existing-only environment makes the route blocked",
                )
                if unresolved_environments:
                    require(
                        "install" in effects,
                        f"{route_id}: an unknown or missing isolated open-source environment requires an explicit install effect",
                    )

            deliverables = route.get("deliverables")
            require(isinstance(deliverables, list), f"{route_id}: deliverables must be a list")
            if route["status"] != "blocked":
                require(bool(deliverables), f"{route_id}: a non-blocked route must declare deliverables")
            deliverable_fields = {"kind", "extension", "label"}
            deliverable_kinds: list[str] = []
            for deliverable in deliverables:
                allow_keys(deliverable, deliverable_fields, f"{route_id} deliverable")
                require(set(deliverable) == deliverable_fields, f"{route_id}: deliverable fields are incomplete")
                kind = non_empty_string(deliverable.get("kind"), f"{route_id} deliverable kind", max_length=128)
                deliverable_kinds.append(kind)
                extension = non_empty_string(deliverable.get("extension"), f"{route_id} deliverable extension", max_length=32)
                require(extension.startswith(".") and "/" not in extension and "\\" not in extension, f"{route_id}: unsafe deliverable extension")
                non_empty_string(deliverable.get("label"), f"{route_id} deliverable label", max_length=1024)
            require(len(deliverable_kinds) == len(set(deliverable_kinds)), f"{route_id}: duplicate deliverable kind")
            if route["status"] != "blocked" and deliverables:
                require(
                    "create-workspace-files" in effects,
                    f"{route_id}: a route with deliverables must declare create-workspace-files",
                )

            parameters = route.get("parameters")
            require(isinstance(parameters, list), f"{route_id}: parameters must be a list")
            parameter_ids = unique_ids(parameters, "parameterId", f"{route_id} parameter") if parameters else set()
            parameter_fields = {"parameterId", "label", "type", "required", "default", "enum", "min", "max", "unit", "origin"}
            for parameter in parameters:
                allow_keys(parameter, parameter_fields, f"{route_id} parameter")
                require(parameter["parameterId"] in parameter_ids, f"{route_id}: invalid parameter ID")
                require(SENSITIVE_KEY.search(parameter["parameterId"]) is None, f"{route_id}: sensitive parameter IDs are forbidden")
                non_empty_string(parameter.get("label"), f"{route_id} parameter label", max_length=1024)
                validate_parameter_spec(parameter, route_id)
            validate_estimate(route.get("estimated"), route_id, effects)
            if route["status"] != "blocked":
                require(
                    estimate_is_bounded(route["estimated"]),
                    f"{route_id}: an executable route requires finite resource estimates before approval",
                )

        for check_id, formula_status, decision, route_bindings in formula_route_bindings:
            route_refs = [binding["routeId"] for binding in route_bindings]
            require(
                set(route_refs) <= route_ids,
                f"{check_id}: formula routeBindings must resolve to routes in the same figure",
            )
            interpretations = {binding["interpretation"] for binding in route_bindings}
            if formula_status == "paper-code-divergence" and route_bindings:
                require(
                    {"paper-formula", "code-implementation"} <= interpretations,
                    f"{check_id}: paper/code divergence requires paper-formula and code-implementation bindings",
                )
            if decision == "split-routes":
                require(
                    len(interpretations) >= 2,
                    f"{check_id}: split-routes requires distinct route interpretations",
                )
                bound_routes = [routes_by_id[route_id] for route_id in route_refs]
                route_signatures = {
                    json.dumps(
                        {
                            "scientificScope": {
                                key: value
                                for key, value in route["scientificScope"].items()
                                if key != "recommendationRationale"
                            },
                            "engine": route["engine"],
                            "plan": route["plan"],
                            "requirementIds": route["requirementIds"],
                            "parameters": route["parameters"],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    for route in bound_routes
                }
                require(
                    len(route_signatures) >= 2,
                    f"{check_id}: split-routes must bind scientifically distinct route definitions",
                )
            elif decision == "block":
                if route_refs:
                    require(
                        all(routes_by_id[route_id]["status"] == "blocked" for route_id in route_refs),
                        f"{check_id}: block may bind only blocked routes",
                    )
                else:
                    require(
                        all(route["status"] == "blocked" for route in routes),
                        f"{check_id}: an unbound block requires every figure route to be blocked",
                    )
                if formula_status == "paper-code-divergence":
                    require(
                        set(route_refs) == route_ids or (not route_refs and all(route["status"] == "blocked" for route in routes)),
                        f"{check_id}: blocking a paper/code divergence must cover every candidate route",
                    )

        if recommended is None:
            require(
                not non_blocked_route_ids,
                f"{figure_id}: a recommended route is required while a non-blocked candidate exists",
            )
        else:
            require(
                recommended in non_blocked_route_ids,
                f"{figure_id}: recommended route must be non-blocked",
            )
        expected_flags = {recommended} if recommended is not None else set()
        require(recommended_flags == expected_flags, f"{figure_id}: recommended flags must match recommendedRouteId")

    require(len(target_ids_global) == len(set(target_ids_global)), "target IDs must be unique across the report")
    require(actual_modes == declared_modes, "targetSet.acquisitionModes must exactly match report targets")
    if actual_modes == {"images-only"}:
        require(paper is None, "an images-only target set cannot declare a paper")
    else:
        require(paper is not None, "paper-backed targets require a paper")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def png_chunks(payload: bytes, name: str) -> list[tuple[bytes, int, int]]:
    signature = b"\x89PNG\r\n\x1a\n"
    require(payload.startswith(signature), f"{name}: extension does not match PNG content")
    offset = len(signature)
    seen_ihdr = False
    seen_iend = False
    seen_idat = False
    chunks: list[tuple[bytes, int, int]] = []
    while offset + 12 <= len(payload):
        length = int.from_bytes(payload[offset:offset + 4], "big")
        end = offset + 12 + length
        require(end <= len(payload), f"{name}: malformed PNG chunk")
        kind = payload[offset + 4:offset + 8]
        data_end = offset + 8 + length
        expected_crc = int.from_bytes(payload[data_end:data_end + 4], "big")
        actual_crc = zlib.crc32(payload[offset + 4:data_end]) & 0xFFFFFFFF
        require(actual_crc == expected_crc, f"{name}: invalid PNG chunk checksum")
        if kind == b"IHDR":
            require(not seen_ihdr and not chunks and length == 13, f"{name}: invalid PNG header")
            seen_ihdr = True
        if kind == b"IDAT":
            seen_idat = True
        chunks.append((kind, offset, end))
        if kind == b"IEND":
            require(length == 0, f"{name}: invalid PNG end chunk")
            seen_iend = True
            require(end == len(payload), f"{name}: trailing bytes after PNG end chunk")
            break
        offset = end
    require(seen_ihdr and seen_idat and seen_iend, f"{name}: incomplete PNG")
    return chunks


def sanitize_png(source: Path, destination: Path) -> None:
    payload = source.read_bytes()
    output = bytearray(b"\x89PNG\r\n\x1a\n")
    # Keep critical image chunks plus transparency; discard text, time, EXIF,
    # color profiles, and animation metadata that can carry identifying data.
    allowed = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}
    for kind, start, end in png_chunks(payload, source.name):
        if kind in allowed:
            output.extend(payload[start:end])
    destination.write_bytes(bytes(output))


def validate_sanitized_png(path: Path) -> None:
    require(path.suffix.lower() == ".png", f"{path.name}: built figure asset must use .png")
    require(path.is_file() and not path.is_symlink(), f"{path.name}: built figure asset is missing or symlinked")
    require(path.stat().st_size <= MAX_ASSET_BYTES, f"{path.name}: built figure asset exceeds {MAX_ASSET_BYTES} bytes")
    allowed = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}
    chunks = png_chunks(path.read_bytes(), path.name)
    require(all(kind in allowed for kind, _, _ in chunks), f"{path.name}: built figure asset contains unsanitized PNG metadata")


def png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    chunks = png_chunks(payload, path.name)
    require(chunks and chunks[0][0] == b"IHDR", f"{path.name}: PNG header is missing")
    ihdr_start = chunks[0][1] + 8
    width = int.from_bytes(payload[ihdr_start:ihdr_start + 4], "big")
    height = int.from_bytes(payload[ihdr_start + 4:ihdr_start + 8], "big")
    require(width > 0 and height > 0, f"{path.name}: invalid PNG dimensions")
    return width, height


def build_report_png(source: Path, destination: Path) -> tuple[int, int, bool]:
    """Create a metadata-free report asset, using a visual proxy when needed.

    The Phase 0 target remains bound by ``targetSha256``.  A proxy only keeps
    an unusually large target displayable in the portable report; it is never
    substituted for the scientific reproduction input.
    """
    sanitize_png(source, destination)
    width, height = png_dimensions(destination)
    if destination.stat().st_size <= MAX_ASSET_BYTES and max(width, height) <= MAX_REPORT_IMAGE_EDGE:
        validate_sanitized_png(destination)
        return width, height, False

    require(Image is not None, "Pillow is required to create a report proxy for an oversized target image")
    try:
        with Image.open(source) as opened:
            opened.load()
            working = opened.convert("RGBA" if "A" in opened.getbands() else "RGB")
    except (OSError, Image.DecompressionBombError) as exc:
        raise ReportError(f"{source.name}: oversized target could not be decoded for a report proxy: {exc}") from exc

    longest = max(working.size)
    if longest > MAX_REPORT_IMAGE_EDGE:
        scale = MAX_REPORT_IMAGE_EDGE / longest
        working = working.resize(
            (max(1, round(working.width * scale)), max(1, round(working.height * scale))),
            Image.Resampling.LANCZOS,
        )

    proxy_path = destination.with_name(f".{destination.name}.proxy")
    try:
        for _ in range(16):
            working.save(proxy_path, format="PNG", optimize=True, compress_level=9)
            sanitize_png(proxy_path, destination)
            if destination.stat().st_size <= MAX_ASSET_BYTES:
                validate_sanitized_png(destination)
                return working.width, working.height, True
            require(min(working.size) > 1, f"{source.name}: cannot create a report proxy below the asset limit")
            working = working.resize(
                (max(1, round(working.width * 0.8)), max(1, round(working.height * 0.8))),
                Image.Resampling.LANCZOS,
            )
    finally:
        proxy_path.unlink(missing_ok=True)
    raise ReportError(f"{source.name}: report proxy still exceeds {MAX_ASSET_BYTES} bytes")


def canonical_payload(report: dict) -> bytes:
    clone = copy.deepcopy(report)
    clone.setdefault("integrity", {})["reportSha256"] = ""
    return json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def redact_text(value: str) -> str:
    result = UNIX_USER_PATH.sub("/$USER", value)
    result = WINDOWS_USER_PATH.sub(r"C:\\Users\\$USER", result)
    result = GENERIC_UNIX_PATH.sub("/[REDACTED_PATH]", result)
    result = ABSOLUTE_POSIX_PATH.sub("/[REDACTED_PATH]", result)
    result = GENERIC_WINDOWS_PATH.sub(r"C:\\[REDACTED_PATH]", result)
    result = UNC_PATH.sub(r"\\\\[REDACTED_PATH]", result)
    result = URI_USERINFO.sub(r"\1[REDACTED]@", result)
    result = SENSITIVE_QUERY.sub(r"\1[REDACTED]", result)
    if value.startswith("file:"):
        return "[REDACTED_LOCAL_URI]"
    def replace_url(match: re.Match[str]) -> str:
        candidate = match.group(0)
        try:
            validate_url(candidate, "embedded URL")
            return candidate
        except ReportError:
            return "[REDACTED_URL]"
    result = URL_IN_TEXT.sub(replace_url, result)
    return result


def public_report(value: object, key: str | None = None) -> object:
    """Return a recursively redacted report suitable for a portable bundle."""
    if key == "sourcePath":
        return None
    if key and SENSITIVE_KEY.search(key) and key not in {"reportSha256", "sha256", "sourceImageSha256"}:
        return "[REDACTED]"
    if key in {"stdout", "stderr", "command", "commands", "rawLog", "actualPath"}:
        return "[REDACTED_PRIVATE_EVIDENCE]"
    if isinstance(value, dict):
        result = {}
        for child_key, child in value.items():
            if child_key == "sourcePath":
                continue
            result[child_key] = public_report(child, child_key)
        return result
    if isinstance(value, list):
        return [public_report(child) for child in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def load_target_manifest(path: Path) -> tuple[dict, dict[str, dict]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    root = path.parent.resolve()
    try:
        by_id = validate_target_manifest(manifest, root=root, require_verified=True)
    except TargetManifestError as exc:
        raise ReportError(f"invalid Phase 0 target manifest: {exc}") from exc

    require(
        isinstance(manifest.get("targetCount"), int)
        and not isinstance(manifest["targetCount"], bool)
        and manifest["targetCount"] == len(by_id),
        "Phase 0 targetCount must be an integer equal to the materialized target set",
    )
    paper = manifest.get("paper")
    paper_backed = [target_id for target_id, target in by_id.items() if target["acquisitionMode"] != "images-only"]
    if paper_backed:
        require(isinstance(paper, dict), "paper-backed targets require a preserved Phase 0 paper")
        require(
            isinstance(paper.get("pageCount"), int)
            and not isinstance(paper["pageCount"], bool)
            and paper["pageCount"] >= 1,
            "preserved Phase 0 paper pageCount must be a positive integer",
        )
    else:
        require(paper is None, "an images-only target manifest cannot bind an unrelated paper")

    for target_id, target in by_id.items():
        for dimension in ("width", "height", "dpi"):
            require(
                isinstance(target.get(dimension), int) and not isinstance(target[dimension], bool),
                f"{target_id}: {dimension} must be an integer",
            )
        if target.get("paperPage") is not None:
            require(
                isinstance(target["paperPage"], int) and not isinstance(target["paperPage"], bool),
                f"{target_id}: paperPage must be an integer",
            )
        crop_box = target.get("cropBoxPdfPoints")
        if crop_box is not None:
            require(
                all(not isinstance(value, bool) for value in crop_box),
                f"{target_id}: cropBoxPdfPoints cannot contain booleans",
            )
        if target["acquisitionMode"] == "images-only":
            require(target.get("identityStatus") == "not-applicable", f"{target_id}: images-only identity must be not-applicable")
            require(
                target["workflowMode"] == "image-derived-reconstruction",
                f"{target_id}: images-only acquisition requires image-derived-reconstruction",
            )
        else:
            require(target.get("identityStatus") == "resolved", f"{target_id}: paper identity must be resolved before report generation")
            require(
                target["workflowMode"] == "scientific-reproduction",
                f"{target_id}: paper-grounded acquisition requires scientific-reproduction",
            )
    return manifest, by_id


def bind_target_manifest(report: dict, manifest: dict, targets: dict[str, dict], manifest_path: Path, audience: str) -> None:
    figures = report.get("figures")
    require(isinstance(figures, list), "report figures must be a list")
    manifest_paper = manifest.get("paper")
    paper_backed = any(target["acquisitionMode"] != "images-only" for target in targets.values())
    if paper_backed:
        require(isinstance(manifest_paper, dict), "paper-backed targets require a preserved Phase 0 paper")
        require(isinstance(report.get("paper"), dict), "paper-backed targets require report paper metadata")
        report["paper"]["sourceSha256"] = manifest_paper["sha256"]
        report["paper"]["pageCount"] = manifest_paper["pageCount"]
    else:
        require(report.get("paper") is None, "an images-only report cannot declare a paper")
    figure_target_ids: list[str] = []
    for figure in figures:
        require(isinstance(figure, dict), "report figure entries must be objects")
        target_stub = figure.get("target")
        require(isinstance(target_stub, dict), f"{figure.get('figureId')}: target binding is required")
        target_id = target_stub.get("targetId")
        require(target_id in targets, f"{figure.get('figureId')}: targetId does not exist in the Phase 0 manifest")
        figure_target_ids.append(target_id)
        source = targets[target_id]
        target_hash = source["targetSha256"]
        method = "pdf-extraction" if source["acquisitionMode"] == "paper-with-figure-references" else "user-upload"
        public_requested_ref = source.get("figureReference") or target_id
        figure["target"] = {
            "targetId": target_id,
            "acquisitionMode": source["acquisitionMode"],
            "workflowMode": source["workflowMode"],
            "requestedRef": public_requested_ref if audience == "public" else (source.get("requestedAs") or source.get("figureReference")),
            "targetSha256": target_hash,
            "materialization": {
                "method": method,
                "qaStatus": source["qaStatus"],
                "page": source.get("paperPage"),
                "renderDpi": source.get("dpi"),
                "captionIncluded": bool(source.get("captionIncluded")),
                "sourceFileName": None if audience == "public" else source.get("sourceFileName"),
                "figureReference": source.get("figureReference"),
                "cropBoxPdfPoints": source.get("cropBoxPdfPoints"),
                "width": source.get("width"),
                "height": source.get("height"),
            },
        }
        if source.get("paperPage") is not None:
            figure["page"] = source["paperPage"]
        if source.get("caption"):
            figure["caption"] = source["caption"]
        elif not figure.get("caption"):
            figure["caption"] = (
                source.get("sourceFileName") or source.get("requestedAs") or target_id
                if audience == "local"
                else public_requested_ref
            )
        image = figure.setdefault("image", {})
        # Distribution authority belongs to the Phase 0 target record.  Report
        # prose may not promote a local-analysis-only object into a public
        # asset merely by setting a boolean in the input JSON.
        redistribution = source.get("localAnalysisOnly") is False
        source_ref = image.get("sourceRef")
        image.clear()
        image.update({
            "sourcePath": str((manifest_path.parent / source["normalizedPath"]).resolve()),
            "sourceRef": source_ref,
            "redistributionAllowed": redistribution,
            "bundleState": None,
            "mediaType": "image/png",
            "width": source.get("width"),
            "height": source.get("height"),
        })
    require(len(figure_target_ids) == len(set(figure_target_ids)), "each report figure must bind a unique Phase 0 target")
    require(set(figure_target_ids) == set(targets), "every Phase 0 target must appear exactly once in the report")
    report["schemaVersion"] = "reprofig.report/v3"
    report.setdefault("generator", {})["name"] = "scirepro"
    report["audience"] = audience
    report["targetSet"] = {
        "targetSetId": manifest.get("targetSetId"),
        "manifestSha256": manifest["integrity"]["manifestSha256"],
        "targetCount": len(targets),
        "acquisitionModes": sorted({target["acquisitionMode"] for target in targets.values()}),
    }


def copy_figure_assets(report: dict, output: Path, asset_root: Path, audience: str) -> list[str]:
    assets = output / "assets"
    assets.mkdir()
    omitted: list[str] = []
    for figure in report["figures"]:
        image = figure.get("image", {})
        source_raw = image.get("sourcePath")
        require(source_raw, f"{figure['figureId']}: Phase 0 target image is not bound")
        if audience == "public" and image.get("redistributionAllowed") is not True:
            image.pop("relativePath", None)
            image.pop("sha256", None)
            image.pop("sizeBytes", None)
            image.pop("metadataStripped", None)
            image["bundleState"] = "omitted-rights"
            omitted.append(figure["target"]["targetId"])
            continue
        candidate = Path(source_raw).expanduser()
        require(not candidate.is_symlink(), f"{figure['figureId']}: symlinked image files are forbidden")
        source = candidate.resolve()
        # Resolving first also makes an intermediate symlink that escapes the
        # approved root fail containment, while harmless system aliases such as
        # macOS /tmp -> /private/tmp do not create false positives.
        require(is_within(source, asset_root), f"{figure['figureId']}: image is outside the approved asset root")
        require(source.is_file(), f"{figure['figureId']}: image does not exist: {source}")
        suffix = source.suffix.lower()
        require(
            suffix in SAFE_EXTENSIONS,
            f"{figure['figureId']}: unsupported image extension {suffix}; public bundles accept sanitized PNG only",
        )
        destination = assets / f"{figure['figureId']}.png"
        width, height, display_proxy = build_report_png(source, destination)
        image["relativePath"] = destination.relative_to(output).as_posix()
        image["width"] = width
        image["height"] = height
        image["sizeBytes"] = destination.stat().st_size
        image["sha256"] = sha256_file(destination)
        image["metadataStripped"] = True
        image["displayProxy"] = display_proxy
        image["bundleState"] = "embedded-local" if audience == "local" else "embedded-public"
    return omitted


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--target-manifest", required=True, type=Path, help="Verified scirepro.targets/v1 Phase 0 manifest.")
    parser.add_argument("--audience", required=True, choices=("local", "public"), help="Local analysis report or rights-filtered public bundle.")
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    final_output = args.output.expanduser().resolve()
    staging: Path | None = None
    committed = False
    try:
        require(input_path.is_file(), f"input file does not exist: {input_path}")
        if final_output.exists():
            require(
                final_output.is_dir() and not any(final_output.iterdir()),
                f"output directory must be new or empty: {final_output}",
            )
        final_output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{final_output.name}.staging-", dir=final_output.parent))
        output = staging

        report = json.loads(input_path.read_text(encoding="utf-8"))
        require(
            isinstance(report, dict) and report.get("schemaVersion") == "reprofig.report/v3",
            "report input must use reprofig.report/v3; regenerate legacy v1/v2 reports",
        )
        manifest_path = args.target_manifest.expanduser().resolve()
        require(manifest_path.is_file(), f"target manifest does not exist: {manifest_path}")
        manifest, targets = load_target_manifest(manifest_path)
        bind_target_manifest(report, manifest, targets, manifest_path, args.audience)
        validate_report(report)
        asset_root = manifest_path.parent.resolve()
        require(asset_root.is_dir(), f"asset root does not exist: {asset_root}")
        omitted_target_ids = copy_figure_assets(report, output, asset_root, args.audience)
        report = public_report(report)
        require(isinstance(report, dict), "public report must remain an object")
        report.setdefault("summary", {})["figureCount"] = len(report["figures"])
        validate_report(report, allow_built_assets=True)
        integrity = report.setdefault("integrity", {})
        integrity["algorithm"] = "sha256"
        integrity["canonicalization"] = "json-sort-keys-v1"
        integrity["reportSha256"] = hashlib.sha256(canonical_payload(report)).hexdigest()

        template = Path(__file__).resolve().parent.parent / "assets" / "research-report-web"
        for name in ("index.html", "app.js", "styles.css"):
            source = template / name
            require(source.is_file(), f"missing report template: {source}")
            shutil.copy2(source, output / name)

        write_json(output / "report.json", report)
        data = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        data = data.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        (output / "report-data.js").write_text(f'"use strict";\nwindow.__SCIREPRO_REPORT__ = {data};\n', encoding="utf-8")

        generated_files = ["index.html", "app.js", "styles.css", "report-data.js", "report.json"]
        generated_files += sorted(path.relative_to(output).as_posix() for path in (output / "assets").glob("*") if path.is_file())
        manifest = {
            "schemaVersion": "reprofig.bundle/v1",
            "reportId": report["reportId"],
            "reportSha256": integrity["reportSha256"],
            "audience": args.audience,
            "targetManifestSha256": report["targetSet"]["manifestSha256"],
            "omittedTargetIds": omitted_target_ids,
            "files": [
                {"path": name, "sizeBytes": (output / name).stat().st_size, "sha256": sha256_file(output / name)}
                for name in generated_files
            ],
        }
        write_json(output / "manifest.json", manifest)
        if final_output.exists():
            # Preflight proved this path was an empty directory.  Leave it
            # untouched until every report file and hash has validated.
            final_output.rmdir()
        staging.replace(final_output)
        committed = True
        print(json.dumps({"status": "ok", "output": str(final_output), "reportSha256": integrity["reportSha256"]}, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ReportError) as exc:
        print(f"SciRepro report build failed: {exc}", file=sys.stderr)
        return 2
    finally:
        if not committed and staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
