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
import zlib
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, urlsplit


LEVELS = {
    "direct-recompute",
    "mechanism-reproduction",
    "alternative-validation",
    "editable-reconstruction",
    "original-case-blocked",
}
ENVIRONMENT_STATES = {"verified", "available", "unknown", "missing"}
ENVIRONMENT_PROVISIONING = {"existing-only", "isolated-open-source"}
SOURCE_KINDS = {"paper", "official-code", "third-party-code", "dataset", "documentation", "skill"}
ACCESS_STATES = {"local", "downloadable", "login-required", "request-required", "controlled", "unavailable", "not-found"}
LICENSE_STATES = {"verified", "declared", "unknown", "restricted"}
REQUIREMENT_CATEGORIES = ["input", "method", "protocol", "validation", "environment"]
REQUIREMENT_STATES = {"verified", "derivable", "assumable", "missing", "not-required"}
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


def non_empty_string(value: object, label: str, *, max_length: int = 20000) -> str:
    require(isinstance(value, str) and value.strip(), f"{label} must be a non-empty string")
    require(len(value) <= max_length, f"{label} exceeds {max_length} characters")
    return value


def evidence_refs(value: object, label: str, source_ids: set[str]) -> list[str]:
    refs = string_list(value, label, ids=True)
    require(set(refs) <= source_ids, f"{label} contains an unknown source reference")
    return refs


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
    allow_keys(report, {
        "schemaVersion", "reportId", "generatedAt", "generator", "workflow", "integrity",
        "paper", "summary", "environment", "sources", "figures", "approvalPolicy",
    }, "report")
    require(report.get("schemaVersion") == "reprofig.report/v2", "unsupported schemaVersion; regenerate legacy reports with the current SciRepro skill")
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
    generator = allow_keys(report.get("generator", {}), {"name", "version"}, "generator")
    integrity = allow_keys(report.get("integrity", {}), {"algorithm", "canonicalization", "reportSha256"}, "integrity")
    paper = allow_keys(report.get("paper", {}), {"paperId", "title", "doi", "citation", "sourcePath"}, "paper")
    summary = allow_keys(report.get("summary", {}), {"objective", "overallLevel", "oneLine", "figureCount"}, "summary")
    non_empty_string(generator.get("name"), "generator.name", max_length=256)
    non_empty_string(generator.get("version"), "generator.version", max_length=128)
    require(integrity.get("algorithm") in {None, "sha256"}, "integrity.algorithm must be sha256 when declared")
    require(integrity.get("canonicalization") in {None, "json-sort-keys-v1"}, "unsupported integrity canonicalization")
    non_empty_string(paper.get("paperId"), "paper.paperId", max_length=512)
    non_empty_string(paper.get("title"), "paper.title")
    non_empty_string(paper.get("citation"), "paper.citation")
    non_empty_string(summary.get("objective"), "summary.objective")
    require(summary.get("overallLevel") in LEVELS | {"mixed"}, "summary.overallLevel must be a reproduction level or mixed")
    non_empty_string(summary.get("oneLine"), "summary.oneLine")
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
        figure_fields = {
            "figureId", "label", "page", "section", "caption", "image", "understanding",
            "generationLogic", "validationTargets", "reproduction", "requirements", "routes", "sourceRefs",
        }
        allow_keys(figure, figure_fields, f"figure {figure_id}")
        require(set(figure) == figure_fields, f"{figure_id}: figure must declare all scientific report fields")
        non_empty_string(figure.get("label"), f"{figure_id} label", max_length=256)
        non_empty_string(figure.get("caption"), f"{figure_id} caption")
        if figure.get("section") is not None:
            non_empty_string(figure["section"], f"{figure_id} section", max_length=1024)

        source_refs = evidence_refs(figure.get("sourceRefs"), f"{figure_id} sourceRefs", source_ids)
        require(bool(source_refs), f"{figure_id}: at least one figure source reference is required")

        image = allow_keys(figure.get("image", {}), {"sourcePath", "relativePath", "sourceRef", "redistributionAllowed", "mediaType", "width", "height", "sizeBytes", "sha256", "metadataStripped"}, f"{figure_id} image")
        if image.get("sourceRef") is not None:
            require(image["sourceRef"] in source_ids, f"{figure_id}: image sourceRef does not resolve")
        if image.get("mediaType") is not None:
            require(image["mediaType"] == "image/png", f"{figure_id}: only image/png figure assets are supported")
        if image.get("sourcePath") is not None:
            non_empty_string(image["sourcePath"], f"{figure_id} image sourcePath")
            require(image.get("mediaType") == "image/png", f"{figure_id}: bundled figure assets must declare mediaType image/png")
            require(image.get("relativePath") is None, f"{figure_id}: relativePath is builder output and cannot accompany sourcePath")
        elif allow_built_assets and image.get("relativePath") is not None:
            require(safe_relative(image["relativePath"]), f"{figure_id}: unsafe built image relativePath")
            require(image["relativePath"] == f"assets/{figure_id}.png", f"{figure_id}: built image path must be assets/{figure_id}.png")
            require(image.get("mediaType") == "image/png", f"{figure_id}: built figure assets must declare mediaType image/png")
            require(isinstance(image.get("sizeBytes"), int) and image["sizeBytes"] > 0, f"{figure_id}: built image sizeBytes is invalid")
            require(isinstance(image.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", image["sha256"]), f"{figure_id}: built image SHA-256 is invalid")
            require(image.get("metadataStripped") is True, f"{figure_id}: built image must record metadata stripping")
        else:
            require(image.get("relativePath") is None, f"{figure_id}: relativePath is builder output, not an input asset")
            require(image.get("sourceRef") in source_ids, f"{figure_id}: an unbundled image requires a sourceRef")
            source = next(item for item in sources if item["sourceId"] == image["sourceRef"])
            require(source.get("url") is not None, f"{figure_id}: unbundled image sourceRef must provide a verified HTTPS URL")
            require(
                source.get("access", {}).get("state") not in {"not-found", "unavailable"},
                f"{figure_id}: unbundled image source is not currently accessible",
            )

        understanding_fields = {
            "visualSummary", "observations", "paperClaim", "evidenceRole", "authorInterpretation", "limitations",
        }
        understanding = allow_keys(figure.get("understanding", {}), understanding_fields, f"{figure_id} understanding")
        require(set(understanding) == understanding_fields, f"{figure_id}: understanding must declare {sorted(understanding_fields)}")
        non_empty_string(understanding.get("visualSummary"), f"{figure_id} visualSummary")
        non_empty_string(understanding.get("paperClaim"), f"{figure_id} paperClaim")
        non_empty_string(understanding.get("evidenceRole"), f"{figure_id} evidenceRole")
        non_empty_string(understanding.get("authorInterpretation"), f"{figure_id} authorInterpretation")
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

        generation_fields = {"inputs", "steps", "plotMapping", "unknowns"}
        generation = allow_keys(figure.get("generationLogic", {}), generation_fields, f"{figure_id} generationLogic")
        require(set(generation) == generation_fields, f"{figure_id}: generationLogic must declare {sorted(generation_fields)}")
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

        validation_targets = figure.get("validationTargets")
        require(isinstance(validation_targets, list) and 1 <= len(validation_targets) <= 32, f"{figure_id}: 1-32 validation targets are required")
        validation_target_ids = unique_ids(validation_targets, "targetId", f"{figure_id} validation target")
        validation_fields = {"targetId", "label", "kind", "origin", "observable", "criterion", "supportsClaim", "evidenceRefs"}
        for target in validation_targets:
            target_id = target["targetId"]
            allow_keys(target, validation_fields, f"validation target {target_id}")
            require(set(target) == validation_fields, f"{target_id}: validation target fields are incomplete")
            non_empty_string(target.get("label"), f"{target_id} label", max_length=1024)
            require(target.get("kind") in VALIDATION_KINDS, f"{target_id}: invalid validation kind")
            require(target.get("origin") in ORIGINS, f"{target_id}: invalid validation origin")
            non_empty_string(target.get("observable"), f"{target_id} observable")
            non_empty_string(target.get("criterion"), f"{target_id} criterion")
            non_empty_string(target.get("supportsClaim"), f"{target_id} supportsClaim")
            refs = evidence_refs(target.get("evidenceRefs"), f"{target_id} evidenceRefs", source_ids)
            require(bool(refs), f"{target_id}: at least one evidence reference is required")

        reproduction_fields = {"level", "verdict", "confidence", "assessment", "recommendedRouteId"}
        reproduction = allow_keys(figure.get("reproduction", {}), reproduction_fields, f"{figure_id} reproduction")
        require(set(reproduction) == reproduction_fields, f"{figure_id}: reproduction fields are incomplete")
        require(reproduction.get("level") in LEVELS, f"{figure_id}: invalid reproduction level")
        require(reproduction.get("confidence") in CONFIDENCE_LEVELS, f"{figure_id}: invalid confidence")
        non_empty_string(reproduction.get("verdict"), f"{figure_id} reproduction verdict")
        non_empty_string(reproduction.get("assessment"), f"{figure_id} reproduction assessment")

        requirements = figure.get("requirements", [])
        require(isinstance(requirements, list) and 5 <= len(requirements) <= 80, f"{figure_id}: 5-80 route requirements are required")
        requirement_ids = unique_ids(requirements, "requirementId", f"{figure_id} requirement")
        requirement_fields = {"requirementId", "category", "label", "state", "blocking", "detail", "evidenceRefs"}
        for requirement in requirements:
            requirement_id = requirement["requirementId"]
            allow_keys(requirement, requirement_fields, f"{figure_id} requirement {requirement_id}")
            require(set(requirement) == requirement_fields, f"{requirement_id}: requirement fields are incomplete")
            non_empty_string(requirement.get("label"), f"{requirement_id} label", max_length=1024)
            non_empty_string(requirement.get("detail"), f"{requirement_id} detail")
            require(requirement.get("category") in REQUIREMENT_CATEGORIES, f"{requirement_id}: invalid requirement category")
            require(requirement.get("state") in REQUIREMENT_STATES, f"{figure_id}: invalid requirement state")
            require(isinstance(requirement.get("blocking"), bool), f"{requirement_id}: blocking must be boolean")
            evidence_refs(requirement.get("evidenceRefs"), f"{requirement_id} evidenceRefs", source_ids)

        requirements_by_id = {item["requirementId"]: item for item in requirements}

        routes = figure.get("routes", [])
        require(isinstance(routes, list) and 1 <= len(routes) <= 16, f"{figure_id}: 1-16 routes are required")
        route_ids = unique_ids(routes, "routeId", f"{figure_id} route")
        require(not (route_ids_global & route_ids), "route IDs must be unique across the report")
        route_ids_global |= route_ids
        recommended = reproduction.get("recommendedRouteId")
        if recommended is not None:
            require(recommended in route_ids, f"{figure_id}: recommended route does not exist")
        elif reproduction.get("level") != "original-case-blocked":
            raise ReportError(f"{figure_id}: a recommended route is required")

        recommended_flags: set[str] = set()
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
            require(len(requirement_refs) == 5, f"{route_id}: exactly five route requirements are required")
            require(
                [requirements_by_id[requirement_id]["category"] for requirement_id in requirement_refs] == REQUIREMENT_CATEGORIES,
                f"{route_id}: requirement order must be {REQUIREMENT_CATEGORIES}",
            )
            if route["status"] != "blocked":
                require(
                    not any(requirements_by_id[requirement_id]["blocking"] for requirement_id in requirement_refs),
                    f"{route_id}: a non-blocked route cannot reference a blocking requirement",
                )
            referenced_requirement_states = {
                requirements_by_id[requirement_id]["state"] for requirement_id in requirement_refs
            }
            effects = set(string_list(route.get("effects"), f"{route_id} effects", ids=True))
            require(effects <= CANONICAL_EFFECTS, f"{route_id}: unknown canonical effect")
            require(effects <= allowed_effects | consent_effects, f"{route_id}: undeclared effect")
            referenced_environments = [
                environment for environment in environments if environment["environmentId"] in environment_refs
            ]
            referenced_environment_states = {environment["status"] for environment in referenced_environments}
            if route["status"] == "ready":
                require(
                    referenced_requirement_states <= {"verified", "not-required"},
                    f"{route_id}: a ready route cannot depend on derivation, assumptions, or missing conditions",
                )
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

        expected_flags = {recommended} if recommended is not None else set()
        require(recommended_flags == expected_flags, f"{figure_id}: recommended flags must match recommendedRouteId")


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
            "files": [
                {"path": name, "sizeBytes": (output / name).stat().st_size, "sha256": sha256_file(output / name)}
                for name in generated_files
            ],
        }
        write_json(output / "manifest.json", manifest)
        print(json.dumps({"status": "ok", "output": str(output), "reportSha256": integrity["reportSha256"]}, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ReportError) as exc:
        print(f"SciRepro report build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
