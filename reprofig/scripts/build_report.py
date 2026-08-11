#!/usr/bin/env python3
"""Validate ReproFig report JSON and build a portable static approval report."""

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
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, urlsplit


LEVELS = {
    "direct-recompute",
    "mechanism-reproduction",
    "alternative-validation",
    "editable-reconstruction",
    "original-case-blocked",
}
REQUIREMENT_CATEGORIES = ["environment", "input", "method", "protocol", "validation"]
REQUIREMENT_STATES = {"verified", "derivable", "assumable", "missing", "not-required"}
ROUTE_STATES = {"ready", "conditional", "blocked"}
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
SENSITIVE_KEY = re.compile(r"(?i)(?:authorization|cookie|credential|password|private[_-]?key|secret|session|token)")
SENSITIVE_QUERY_KEY = re.compile(
    r"(?i)^(?:access[_-]?key|api[_-]?key|auth|authorization|credential|password|secret|signature|sig|token|x-amz-.*)$"
)
UNIX_USER_PATH = re.compile(r"/(?:Users|home)/[^/\s\"']+")
WINDOWS_USER_PATH = re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"']+")
URI_USERINFO = re.compile(r"(?i)(https://)[^/@\s]+@")
SENSITIVE_QUERY = re.compile(
    r"(?i)([?&](?:access[_-]?key|api[_-]?key|auth|authorization|credential|password|secret|signature|sig|token|x-amz-[^=&#\s]+)=)[^&#\s]+"
)
GENERIC_UNIX_PATH = re.compile(
    r"(?<![:/A-Za-z0-9])/(?:Users|home|Volumes|private|var|srv|opt|etc|mnt|media|root|tmp)(?:/[^\s\"'<>]*)?"
)
ABSOLUTE_POSIX_PATH = re.compile(r"(?<![:/A-Za-z0-9])/(?:[^\s\"'<>/]+/)+[^\s\"'<>]*")
GENERIC_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:[\\/][^\s\"'<>]*")
UNC_PATH = re.compile(r"\\\\[^\\\s\"']+[\\/][^\s\"']*")
URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>]+")
MAX_ASSET_BYTES = 25 * 1024 * 1024


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


def validate_report(report: dict) -> None:
    allow_keys(report, {
        "schemaVersion", "reportId", "generatedAt", "generator", "workflow", "integrity",
        "paper", "summary", "environment", "sources", "figures", "approvalPolicy",
    }, "report")
    require(report.get("schemaVersion") == "reprofig.report/v1", "unsupported schemaVersion")
    require(isinstance(report.get("reportId"), str) and ID_PATTERN.fullmatch(report["reportId"]), "invalid reportId")
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
    require(isinstance(figures, list) and 1 <= len(figures) <= 3, "report must contain 1-3 figures")

    environment_ids = unique_ids(environments, "environmentId", "environment")
    source_ids = unique_ids(sources, "sourceId", "source")
    unique_ids(figures, "figureId", "figure")
    allow_keys(report.get("generator", {}), {"name", "version"}, "generator")
    allow_keys(report.get("integrity", {}), {"algorithm", "canonicalization", "reportSha256"}, "integrity")
    allow_keys(report.get("paper", {}), {"paperId", "title", "doi", "citation", "sourcePath"}, "paper")
    allow_keys(report.get("summary", {}), {"overallLevel", "oneLine", "figureCount"}, "summary")
    for environment in environments:
        allow_keys(environment, {"environmentId", "label", "status", "version", "detail", "evidenceRefs"}, f"environment {environment.get('environmentId')}")
        refs = string_list(environment.get("evidenceRefs", []), f"environment {environment['environmentId']} evidenceRefs", ids=True)
        require(set(refs) <= source_ids, f"environment {environment['environmentId']}: unknown evidence source")
    for source in sources:
        allow_keys(source, {"sourceId", "kind", "title", "publisher", "url", "access", "license", "artifact", "note"}, f"source {source.get('sourceId')}")
        allow_keys(source.get("access", {}), {"state", "checkedAt", "httpStatus", "note"}, f"source {source['sourceId']} access")
        allow_keys(source.get("license", {}), {"state", "spdxId", "name", "url"}, f"source {source['sourceId']} license")
        if source.get("artifact") is not None:
            allow_keys(source["artifact"], {"sourcePath", "relativePath", "fileName", "mediaType", "sizeBytes", "sha256"}, f"source {source['sourceId']} artifact")
        validate_url(source.get("url"), f"source {source['sourceId']} URL")
        validate_url(source.get("license", {}).get("url"), f"source {source['sourceId']} license URL")

    policy = report.get("approvalPolicy", {})
    allow_keys(policy, {"minFigures", "maxFigures", "defaultOutputPolicy", "allowedEffects", "consentRequiredEffects", "ttlMinutes"}, "approvalPolicy")
    minimum = finite_number(policy.get("minFigures"), "approvalPolicy.minFigures", integer=True)
    maximum = finite_number(policy.get("maxFigures"), "approvalPolicy.maxFigures", integer=True)
    ttl = finite_number(policy.get("ttlMinutes"), "approvalPolicy.ttlMinutes", integer=True)
    require(1 <= minimum <= maximum <= 3, "approvalPolicy figure bounds must satisfy 1 <= minFigures <= maxFigures <= 3")
    require(1 <= ttl <= 10080, "approvalPolicy.ttlMinutes must be between 1 and 10080")
    require(policy.get("defaultOutputPolicy") == "create-only", "approvalPolicy.defaultOutputPolicy must be create-only")
    allowed_effects = set(string_list(policy.get("allowedEffects"), "approvalPolicy.allowedEffects", ids=True))
    consent_effects = set(string_list(policy.get("consentRequiredEffects"), "approvalPolicy.consentRequiredEffects", ids=True))
    require(allowed_effects <= CANONICAL_AUTOMATIC_EFFECTS, "allowedEffects contains an unknown or gated effect")
    require(consent_effects <= CANONICAL_GATED_EFFECTS, "consentRequiredEffects contains an unknown or automatic effect")
    require(not (allowed_effects & consent_effects), "automatic and consent-required effects must be disjoint")

    route_ids_global: set[str] = set()
    for figure in figures:
        figure_id = figure["figureId"]
        allow_keys(figure, {"figureId", "label", "page", "section", "caption", "image", "role", "summary", "reproduction", "requirements", "routes", "sourceRefs"}, f"figure {figure_id}")
        image = allow_keys(figure.get("image", {}), {"sourcePath", "relativePath", "redistributionAllowed", "mediaType", "width", "height", "sizeBytes", "sha256", "metadataStripped"}, f"{figure_id} image")
        if image.get("mediaType") is not None:
            require(image["mediaType"] == "image/png", f"{figure_id}: only image/png figure assets are supported")
        if image.get("sourcePath") is not None:
            require(isinstance(image["sourcePath"], str) and image["sourcePath"], f"{figure_id}: image sourcePath must be a non-empty string")
            require(image.get("mediaType") == "image/png", f"{figure_id}: bundled figure assets must declare mediaType image/png")
        reproduction = figure.get("reproduction", {})
        allow_keys(reproduction, {"level", "verdict", "confidence", "assessment", "recommendedRouteId"}, f"{figure_id} reproduction")
        require(reproduction.get("level") in LEVELS, f"{figure_id}: invalid reproduction level")
        require(reproduction.get("confidence") in {"high", "medium", "low"}, f"{figure_id}: invalid confidence")
        require(isinstance(figure.get("summary"), str) and figure["summary"].strip(), f"{figure_id}: summary is required")

        requirements = figure.get("requirements", [])
        require(isinstance(requirements, list) and len(requirements) == 5, f"{figure_id}: exactly five requirements are required")
        requirement_ids = unique_ids(requirements, "requirementId", f"{figure_id} requirement")
        categories = [item.get("category") for item in requirements]
        require(categories == REQUIREMENT_CATEGORIES, f"{figure_id}: requirement order must be {REQUIREMENT_CATEGORIES}")
        for requirement in requirements:
            allow_keys(requirement, {"requirementId", "category", "label", "state", "blocking", "detail", "evidenceRefs"}, f"{figure_id} requirement {requirement.get('requirementId')}")
            require(requirement.get("state") in REQUIREMENT_STATES, f"{figure_id}: invalid requirement state")
            refs = string_list(requirement.get("evidenceRefs", []), f"{figure_id} requirement evidenceRefs", ids=True)
            require(set(refs) <= source_ids, f"{figure_id}: unknown requirement evidence source")

        routes = figure.get("routes", [])
        require(isinstance(routes, list), f"{figure_id}: routes must be a list")
        route_ids = unique_ids(routes, "routeId", f"{figure_id} route")
        require(not (route_ids_global & route_ids), "route IDs must be unique across the report")
        route_ids_global |= route_ids
        recommended = reproduction.get("recommendedRouteId")
        if recommended is not None:
            require(recommended in route_ids, f"{figure_id}: recommended route does not exist")
        elif reproduction.get("level") != "original-case-blocked":
            raise ReportError(f"{figure_id}: a recommended route is required")

        for route in routes:
            route_id = route["routeId"]
            allow_keys(route, {"routeId", "label", "status", "recommended", "engine", "environmentIds", "requirementIds", "deliverables", "parameters", "effects", "estimated", "plan", "blockers"}, f"route {route_id}")
            require(route.get("status") in ROUTE_STATES, f"{route_id}: invalid route status")
            if route_id == recommended:
                require(route.get("status") != "blocked", f"{route_id}: recommended route cannot be blocked")
            string_list(route.get("plan", []), f"{route_id} plan", max_items=5)
            string_list(route.get("blockers", []), f"{route_id} blockers", max_items=32)
            require(not any(key in route for key in ("command", "commands", "shell", "script")), f"{route_id}: executable commands are forbidden in reports")
            environment_refs = string_list(route.get("environmentIds", []), f"{route_id} environmentIds", ids=True)
            requirement_refs = string_list(route.get("requirementIds", []), f"{route_id} requirementIds", ids=True)
            require(set(environment_refs) <= environment_ids, f"{route_id}: unknown environment reference")
            require(set(requirement_refs) <= requirement_ids, f"{route_id}: unknown requirement reference")
            effects = set(string_list(route.get("effects", []), f"{route_id} effects", ids=True))
            require(effects <= CANONICAL_EFFECTS, f"{route_id}: unknown canonical effect")
            require(effects <= allowed_effects | consent_effects, f"{route_id}: undeclared effect")
            deliverables = route.get("deliverables", [])
            require(isinstance(deliverables, list), f"{route_id}: deliverables must be a list")
            for deliverable in deliverables:
                allow_keys(deliverable, {"kind", "extension", "label"}, f"{route_id} deliverable")
            parameters = route.get("parameters", [])
            require(isinstance(parameters, list), f"{route_id}: parameters must be a list")
            for parameter in parameters:
                allow_keys(parameter, {"parameterId", "label", "type", "required", "default", "enum", "min", "max", "unit", "origin"}, f"{route_id} parameter")
                require(parameter.get("type") in {"string", "number", "integer", "boolean", "enum", "relative-path"}, f"{route_id}: unsupported parameter type")
                require(isinstance(parameter.get("parameterId"), str) and ID_PATTERN.fullmatch(parameter["parameterId"]), f"{route_id}: invalid parameter ID")
                require(SENSITIVE_KEY.search(parameter["parameterId"]) is None, f"{route_id}: sensitive parameter IDs are forbidden")
            validate_estimate(route.get("estimated"), route_id, effects)

        source_refs = string_list(figure.get("sourceRefs", []), f"{figure_id} sourceRefs", ids=True)
        require(set(source_refs) <= source_ids, f"{figure_id}: unknown source reference")


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


def sanitize_png(source: Path, destination: Path) -> None:
    payload = source.read_bytes()
    signature = b"\x89PNG\r\n\x1a\n"
    require(payload.startswith(signature), f"{source.name}: extension does not match PNG content")
    output = bytearray(signature)
    offset = len(signature)
    seen_ihdr = False
    seen_iend = False
    # Keep critical image chunks plus transparency; discard text, time, EXIF,
    # color profiles, and animation metadata that can carry identifying data.
    allowed = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}
    while offset + 12 <= len(payload):
        length = int.from_bytes(payload[offset:offset + 4], "big")
        end = offset + 12 + length
        require(end <= len(payload), f"{source.name}: malformed PNG chunk")
        kind = payload[offset + 4:offset + 8]
        if kind == b"IHDR":
            require(not seen_ihdr and length == 13, f"{source.name}: invalid PNG header")
            seen_ihdr = True
        if kind in allowed:
            output.extend(payload[offset:end])
        if kind == b"IEND":
            seen_iend = True
            break
        offset = end
    require(seen_ihdr and seen_iend, f"{source.name}: incomplete PNG")
    destination.write_bytes(bytes(output))


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


def copy_figure_assets(report: dict, output: Path, asset_root: Path) -> None:
    assets = output / "assets"
    assets.mkdir()
    for figure in report["figures"]:
        image = figure.get("image", {})
        source_raw = image.get("sourcePath")
        if not source_raw:
            # A new bundle is self-contained; never inherit an unresolved local path.
            image.pop("relativePath", None)
            continue
        require(image.get("redistributionAllowed") is True, f"{figure['figureId']}: image redistribution is not authorized")
        candidate = Path(source_raw).expanduser()
        require(not candidate.is_symlink(), f"{figure['figureId']}: symlinked image files are forbidden")
        source = candidate.resolve()
        # Resolving first also makes an intermediate symlink that escapes the
        # approved root fail containment, while harmless system aliases such as
        # macOS /tmp -> /private/tmp do not create false positives.
        require(is_within(source, asset_root), f"{figure['figureId']}: image is outside the approved asset root")
        require(source.is_file(), f"{figure['figureId']}: image does not exist: {source}")
        require(source.stat().st_size <= MAX_ASSET_BYTES, f"{figure['figureId']}: image exceeds {MAX_ASSET_BYTES} bytes")
        suffix = source.suffix.lower()
        require(
            suffix in SAFE_EXTENSIONS,
            f"{figure['figureId']}: unsupported image extension {suffix}; public bundles accept sanitized PNG only",
        )
        destination = assets / f"{figure['figureId']}.png"
        sanitize_png(source, destination)
        image["relativePath"] = destination.relative_to(output).as_posix()
        image["sizeBytes"] = destination.stat().st_size
        image["sha256"] = sha256_file(destination)
        image["metadataStripped"] = True


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--asset-root",
        type=Path,
        help="Approved directory containing redistributable figure assets (defaults to the input JSON directory).",
    )
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    output = args.output.expanduser().resolve()
    try:
        require(input_path.is_file(), f"input file does not exist: {input_path}")
        if output.exists():
            require(output.is_dir() and not any(output.iterdir()), f"output directory must be new or empty: {output}")
        else:
            output.mkdir(parents=True)

        report = json.loads(input_path.read_text(encoding="utf-8"))
        validate_report(report)
        asset_root = (args.asset_root or input_path.parent).expanduser().resolve()
        require(asset_root.is_dir(), f"asset root does not exist: {asset_root}")
        copy_figure_assets(report, output, asset_root)
        report = public_report(report)
        require(isinstance(report, dict), "public report must remain an object")
        report.setdefault("summary", {})["figureCount"] = len(report["figures"])
        integrity = report.setdefault("integrity", {})
        integrity["algorithm"] = "sha256"
        integrity["canonicalization"] = "json-sort-keys-v1"
        integrity["reportSha256"] = hashlib.sha256(canonical_payload(report)).hexdigest()

        template = Path(__file__).resolve().parent.parent / "assets" / "feasibility-web"
        for name in ("index.html", "app.js", "styles.css"):
            source = template / name
            require(source.is_file(), f"missing report template: {source}")
            shutil.copy2(source, output / name)

        write_json(output / "report.json", report)
        data = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        data = data.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        (output / "report-data.js").write_text(f'"use strict";\nwindow.__REPROFIG_REPORT__ = {data};\n', encoding="utf-8")

        generated_files = ["index.html", "app.js", "styles.css", "report-data.js", "report.json"]
        generated_files += sorted(path.relative_to(output).as_posix() for path in (output / "assets").glob("*") if path.is_file())
        manifest = {
            "schemaVersion": "reprofig.bundle/v1",
            "reportId": report["reportId"],
            "reportSha256": integrity["reportSha256"],
            "files": [
                {"path": name, "sizeBytes": (output / name).stat().st_size, "sha256": sha256_file(output / name)}
                for name in generated_files
            ],
        }
        write_json(output / "manifest.json", manifest)
        print(json.dumps({"status": "ok", "output": str(output), "reportSha256": integrity["reportSha256"]}, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ReportError) as exc:
        print(f"ReproFig report build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
