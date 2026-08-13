#!/usr/bin/env python3
"""Validate that a SciRepro approval is a safe subset of its report."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

from build_report import MAX_ASSET_BYTES
from build_report import ReportError as ReportValidationError
from build_report import load_target_manifest, require_secret_free, sha256_file, validate_report, validate_sanitized_png


class GateError(ValueError):
    pass


APPROVAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def canonical_hash(report: dict) -> str:
    clone = copy.deepcopy(report)
    clone.setdefault("integrity", {})["reportSha256"] = ""
    payload = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_identifier(field: str, value: object) -> str:
    require(isinstance(value, str), f"{field} must be a string")
    require(8 <= len(value) <= 128, f"{field} must contain 8 to 128 characters")
    require(bool(APPROVAL_ID_PATTERN.fullmatch(value)), f"{field} contains invalid characters")
    return value


def parse_time(value: object, field: str) -> datetime:
    require(isinstance(value, str) and 1 <= len(value) <= 64, f"{field} must be a bounded timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise GateError(f"{field} is not a valid ISO-8601 timestamp") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def safe_error_message(exc: Exception) -> str:
    message = str(exc).replace("\r", " ").replace("\n", " ")
    message = "".join(char if 32 <= ord(char) < 127 or ord(char) >= 160 else " " for char in message)
    return message[:512] or "malformed approval or report"


def safe_relative(value: str) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "%" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith(("/", "//", "~")):
        return False
    # Reject URI schemes and Windows drive prefixes (for example C:/path).
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", normalized):
        return False
    path = PurePosixPath(normalized)
    return not path.is_absolute() and ".." not in path.parts and all(part not in {"", "."} for part in path.parts)


def validate_parameter(spec: dict, value: object) -> None:
    kind = spec.get("type")
    if kind == "string":
        require(isinstance(value, str) and len(value) <= 4096, f"{spec['parameterId']}: expected a bounded string")
    elif kind == "integer":
        require(isinstance(value, int) and not isinstance(value, bool), f"{spec['parameterId']}: expected integer")
    elif kind == "number":
        require(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
            f"{spec['parameterId']}: expected finite number",
        )
    elif kind == "boolean":
        require(isinstance(value, bool), f"{spec['parameterId']}: expected boolean")
    elif kind == "enum":
        require(value in spec.get("enum", []), f"{spec['parameterId']}: invalid enum value")
    elif kind == "relative-path":
        require(isinstance(value, str) and safe_relative(value), f"{spec['parameterId']}: unsafe relative path")
    else:
        raise GateError(f"{spec['parameterId']}: unsupported parameter type")
    if isinstance(value, str):
        try:
            require_secret_free(value, f"{spec['parameterId']}: value")
        except ReportValidationError as exc:
            raise GateError(str(exc)) from exc
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "min" in spec:
            require(value >= spec["min"], f"{spec['parameterId']}: below minimum")
        if "max" in spec:
            require(value <= spec["max"], f"{spec['parameterId']}: above maximum")


def requirement_can_run(requirement: dict) -> bool:
    """Return whether a requirement is concrete enough for execution."""
    state = requirement.get("state")
    if state in {"verified", "not-required"}:
        return True
    if state in {"derivable", "assumable"}:
        resolution = requirement.get("resolution")
        expected = {"derivable": "frozen", "assumable": "accepted"}[state]
        return (
            isinstance(resolution, dict)
            and resolution.get("status") == expected
            and isinstance(resolution.get("basis"), str)
            and bool(resolution["basis"].strip())
        )
    return False


def estimate_is_bounded(route: dict) -> bool:
    estimate = route.get("estimated")
    return isinstance(estimate, dict) and all(
        estimate.get(field) is not None
        for field in ("downloadBytes", "diskBytes", "runtimeMinutes", "costUsd")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument(
        "--target-manifest",
        required=True,
        type=Path,
        help="Current verified scirepro.targets/v1 manifest bound by the local report.",
    )
    args = parser.parse_args()

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        approval = json.loads(args.approval.read_text(encoding="utf-8"))
        require(isinstance(report, dict), "report must be an object")
        require(isinstance(approval, dict), "approval must be an object")
        try:
            require_secret_free(approval, "approval")
        except ReportValidationError as exc:
            raise GateError(str(exc)) from exc
        schema_version = report.get("schemaVersion")
        require(
            schema_version == "reprofig.report/v3",
            "unsupported report schema; legacy reports must be regenerated before approval",
        )
        validate_report(report, allow_built_assets=True)
        require(report.get("audience") == "local", "execution approval must be exported from the local Phase 0 report")
        target_manifest_path = args.target_manifest.expanduser().resolve()
        require(target_manifest_path.is_file(), "Phase 0 target manifest is missing")
        target_manifest, manifest_targets = load_target_manifest(target_manifest_path)
        report_target_set = report.get("targetSet", {})
        require(
            report_target_set.get("manifestSha256") == target_manifest.get("integrity", {}).get("manifestSha256"),
            "Phase 0 target manifest hash no longer matches the approved report",
        )
        require(
            report_target_set.get("targetSetId") == target_manifest.get("targetSetId"),
            "Phase 0 target-set identity mismatch",
        )
        require(
            report_target_set.get("targetCount") == target_manifest.get("targetCount") == len(manifest_targets),
            "Phase 0 target count mismatch",
        )
        report_target_ids = {figure.get("target", {}).get("targetId") for figure in report.get("figures", [])}
        require(report_target_ids == set(manifest_targets), "report targets no longer match the Phase 0 manifest")
        manifest_paper = target_manifest.get("paper")
        report_paper = report.get("paper")
        if manifest_paper is None:
            require(report_paper is None, "images-only report unexpectedly declares a paper")
        else:
            require(isinstance(report_paper, dict), "paper-backed report is missing its paper binding")
            require(report_paper.get("sourceSha256") == manifest_paper.get("sha256"), "preserved paper hash mismatch")
            require(report_paper.get("pageCount") == manifest_paper.get("pageCount"), "preserved paper page-count mismatch")
        for figure in report.get("figures", []):
            target = figure.get("target", {})
            target_id = target.get("targetId")
            manifest_target = manifest_targets[target_id]
            require(target.get("targetSha256") == manifest_target.get("targetSha256"), f"{figure['figureId']}: current Phase 0 target hash mismatch")
            require(target.get("acquisitionMode") == manifest_target.get("acquisitionMode"), f"{figure['figureId']}: acquisition mode changed after report generation")
            require(target.get("workflowMode") == manifest_target.get("workflowMode"), f"{figure['figureId']}: workflow mode changed after report generation")
        report_root = args.report.parent.resolve()
        for figure in report.get("figures", []):
            image = figure.get("image", {})
            relative_path = image.get("relativePath")
            if relative_path is None:
                continue
            candidate = args.report.parent / relative_path
            require(not candidate.is_symlink(), f"{figure['figureId']}: built image cannot be a symlink")
            resolved = candidate.resolve()
            try:
                resolved.relative_to(report_root)
            except ValueError as exc:
                raise GateError(f"{figure['figureId']}: built image escapes the report directory") from exc
            require(resolved.is_file(), f"{figure['figureId']}: built image is missing")
            require(resolved.stat().st_size <= MAX_ASSET_BYTES, f"{figure['figureId']}: built image exceeds the size limit")
            require(resolved.stat().st_size == image.get("sizeBytes"), f"{figure['figureId']}: built image size mismatch")
            require(sha256_file(resolved) == image.get("sha256"), f"{figure['figureId']}: built image hash mismatch")
            validate_sanitized_png(resolved)
        require(approval.get("schemaVersion") == "reprofig.approval/v1", "unsupported approval schema")

        allowed_root = {
            "schemaVersion", "approvalId", "reportId", "reportSha256", "decision",
            "createdAt", "expiresAt", "selectedFigures", "outputPolicy",
            "authorizedEffects", "acknowledgements", "idempotencyKey",
        }
        require(set(approval) <= allowed_root, "approval contains unknown top-level fields")
        required_root = allowed_root
        require(required_root <= set(approval), "approval is missing required top-level fields")
        approval_id = validate_identifier("approvalId", approval.get("approvalId"))
        idempotency_key = validate_identifier("idempotencyKey", approval.get("idempotencyKey"))
        expected_hash = canonical_hash(report)
        require(report.get("integrity", {}).get("reportSha256") == expected_hash, "report integrity hash is invalid")
        require(approval.get("reportId") == report.get("reportId"), "approval reportId mismatch")
        require(approval.get("reportSha256") == expected_hash, "approval report hash mismatch")
        require(approval.get("decision") == "approve", "approval decision must be approve for execution")
        created_at = parse_time(approval.get("createdAt"), "createdAt")
        expires_at = parse_time(approval.get("expiresAt"), "expiresAt")
        now = datetime.now(timezone.utc)
        ttl_minutes = int(report.get("approvalPolicy", {}).get("ttlMinutes", 1440))
        require(1 <= ttl_minutes <= 10080, "report approval TTL is outside the allowed range")
        require(created_at <= now + timedelta(minutes=5), "approval createdAt is unreasonably in the future")
        require(expires_at > now, "approval has expired")
        require(expires_at > created_at, "approval expiry must follow creation")
        require(expires_at - created_at <= timedelta(minutes=ttl_minutes), "approval exceeds the report TTL")

        figures = {figure["figureId"]: figure for figure in report.get("figures", [])}
        selections = approval.get("selectedFigures", [])
        policy = report.get("approvalPolicy", {})
        minimum = int(policy.get("minFigures", 1))
        maximum = int(policy.get("maxFigures", len(figures)))
        require(isinstance(selections, list) and minimum <= len(selections) <= maximum, "invalid selected figure count")
        require(all(isinstance(selection, dict) for selection in selections), "selection must be an object")
        figure_ids = [selection.get("figureId") for selection in selections]
        require(all(isinstance(figure_id, str) and figure_id for figure_id in figure_ids), "selection figureId must be a non-empty string")
        require(len(figure_ids) == len(set(figure_ids)), "duplicate selected figure")

        authorized_values = approval.get("authorizedEffects")
        require(isinstance(authorized_values, list), "authorizedEffects must be a list")
        require(all(isinstance(effect, str) and effect for effect in authorized_values), "authorizedEffects must contain non-empty strings")
        require(len(authorized_values) == len(set(authorized_values)), "duplicate authorized effect")
        authorized = set(authorized_values)
        allowed = set(policy.get("allowedEffects", [])) | set(policy.get("consentRequiredEffects", []))
        require(authorized <= allowed, "approval authorizes an undeclared effect")
        acknowledgements = approval.get("acknowledgements")
        require(isinstance(acknowledgements, list), "acknowledgements must be a list")
        acknowledged = set()
        for item in acknowledgements:
            require(isinstance(item, dict) and set(item) <= {"effect", "acceptedAt"}, "malformed acknowledgement")
            require(isinstance(item.get("effect"), str) and isinstance(item.get("acceptedAt"), str), "malformed acknowledgement")
            require(item["effect"] not in acknowledged, "duplicate acknowledgement")
            accepted_at = parse_time(item["acceptedAt"], "acknowledgement acceptedAt")
            require(created_at <= accepted_at <= now + timedelta(minutes=5), "acknowledgement timestamp is outside the approval window")
            acknowledged.add(item["effect"])
        consent_required = set(policy.get("consentRequiredEffects", []))
        required_effects: set[str] = set()

        for selection in selections:
            allowed_selection = {"figureId", "sourceImageSha256", "routeId", "parameters", "deliverables"}
            require(set(selection) <= allowed_selection, "selection contains unknown fields")
            require(allowed_selection <= set(selection), "selection is missing required fields")
            figure_id = selection.get("figureId")
            require(figure_id in figures, f"unknown figure {figure_id}")
            figure = figures[figure_id]
            target = figure.get("target", {})
            expected_target_hash = target.get("targetSha256")
            require(selection.get("sourceImageSha256") == expected_target_hash, f"{figure_id}: Phase 0 target hash mismatch")
            image = figure.get("image", {})
            require(image.get("bundleState") in {"embedded-local", "embedded-public"}, f"{figure_id}: target image is not available in this report and cannot be approved")
            routes = {route["routeId"]: route for route in figure.get("routes", [])}
            route_id = selection.get("routeId")
            require(route_id in routes, f"{figure_id}: unknown route")
            route = routes[route_id]
            require(route.get("status") != "blocked", f"{figure_id}: blocked route cannot be approved")
            require(not route.get("blockers"), f"{figure_id}: a route with blockers cannot be approved")
            require(estimate_is_bounded(route), f"{figure_id}: selected route has an unbounded resource estimate")
            requirements = {item["requirementId"]: item for item in figure.get("requirements", [])}
            referenced_requirements = []
            for requirement_id in route.get("requirementIds", []):
                requirement = requirements.get(requirement_id)
                require(requirement is not None, f"{figure_id}: unknown route requirement")
                require(requirement.get("blocking") is not True, f"{figure_id}: route references a blocking requirement")
                referenced_requirements.append(requirement)

            route_effects = set(route.get("effects", []))
            require(
                not route.get("deliverables") or "create-workspace-files" in route_effects,
                f"{figure_id}: selected route deliverables require create-workspace-files",
            )
            environments = {item["environmentId"]: item for item in report.get("environment", [])}
            referenced_environments = [
                environments[environment_id]
                for environment_id in route.get("environmentIds", [])
                if environment_id in environments
            ]
            referenced_environment_states = {environment["status"] for environment in referenced_environments}
            require(
                all(requirement_can_run(requirement) for requirement in referenced_requirements),
                f"{figure_id}: selected route contains an unresolved requirement",
            )
            if route.get("status") == "ready":
                require(
                    referenced_environment_states <= {"verified"},
                    f"{figure_id}: ready route references an environment without route-level verification",
                )
            elif route.get("status") == "conditional":
                unresolved_environments = [
                    environment
                    for environment in referenced_environments
                    if environment["status"] in {"unknown", "missing"}
                ]
                require(
                    not any(environment.get("provisioning") == "existing-only" for environment in unresolved_environments),
                    f"{figure_id}: an existing-only environment cannot be installed by the approved route",
                )
                if unresolved_environments:
                    require(
                        "install" in route_effects,
                        f"{figure_id}: unresolved isolated open-source environment has no approved installation route",
                    )
            required_effects |= route_effects

            parameter_specs = {item["parameterId"]: item for item in route.get("parameters", [])}
            parameter_values = selection.get("parameters", {})
            require(isinstance(parameter_values, dict) and set(parameter_values) <= set(parameter_specs), f"{figure_id}: unknown parameter")
            for parameter_id, spec in parameter_specs.items():
                if spec.get("required"):
                    require(parameter_id in parameter_values, f"{figure_id}: missing required parameter {parameter_id}")
                if parameter_id in parameter_values:
                    validate_parameter(spec, parameter_values[parameter_id])

            allowed_deliverables = {item["kind"] for item in route.get("deliverables", [])}
            requested_values = selection.get("deliverables")
            require(isinstance(requested_values, list), f"{figure_id}: deliverables must be a list")
            require(all(isinstance(value, str) and value for value in requested_values), f"{figure_id}: deliverables must contain non-empty strings")
            require(len(requested_values) == len(set(requested_values)), f"{figure_id}: duplicate deliverable")
            requested_deliverables = set(requested_values)
            require(bool(requested_deliverables) and requested_deliverables <= allowed_deliverables, f"{figure_id}: invalid deliverables")

        require(authorized == required_effects, "authorized effects must exactly match selected routes")
        required_acknowledgements = required_effects & consent_required
        require(acknowledged == required_acknowledgements, "acknowledgements must exactly match consent-required route effects")

        output = approval.get("outputPolicy", {})
        require(isinstance(output, dict), "outputPolicy must be an object")
        require(set(output) <= {"relativeRoot", "mode", "overwrite", "explicitFiles"}, "outputPolicy contains unknown fields")
        require(output.get("mode") in {"create-only", "overwrite-approved"}, "invalid output mode")
        require(output.get("overwrite") in {"never", "explicit-files"}, "invalid overwrite policy")
        require(isinstance(output.get("relativeRoot"), str) and safe_relative(output["relativeRoot"]), "unsafe output root")
        explicit_files = output.get("explicitFiles", [])
        require(isinstance(explicit_files, list), "explicitFiles must be a list")
        require(all(isinstance(value, str) and safe_relative(value) for value in explicit_files), "unsafe explicit overwrite path")
        if output.get("mode") == "create-only":
            require(output.get("overwrite") == "never" and not explicit_files, "create-only mode cannot authorize overwrite")
            require("overwrite" not in required_effects, "create-only output cannot approve a route that requires overwrite")
        else:
            require("overwrite" in required_effects, "overwrite-approved output requires the selected route to declare overwrite")
            require(output.get("overwrite") == "explicit-files", "overwrite-approved requires explicit-files policy")
            require(bool(explicit_files), "overwrite-approved requires explicit files")
            require(len(explicit_files) == len(set(explicit_files)), "duplicate explicit overwrite path")

        selected_targets = []
        for selection in selections:
            figure = figures[selection["figureId"]]
            target = figure["target"]
            selected_targets.append({
                "figureId": selection["figureId"],
                "targetId": target["targetId"],
                "targetSha256": target["targetSha256"],
                "workflowMode": target["workflowMode"],
                "routeId": selection["routeId"],
                "parameters": dict(selection["parameters"]),
                "deliverables": list(selection["deliverables"]),
            })

        print(json.dumps({
            "schemaVersion": "scirepro.gate-result/v1",
            "status": "valid",
            "reportId": report["reportId"],
            "reportSha256": expected_hash,
            "targetManifestSha256": target_manifest["integrity"]["manifestSha256"],
            "approvalId": approval_id,
            "approvalSha256": sha256_file(args.approval),
            "idempotencyKey": idempotency_key,
            "replayProtection": "not-enforced-by-stateless-validator",
            "selectedFigures": figure_ids,
            "selectedTargets": selected_targets,
            "authorizedEffects": sorted(authorized),
            "outputPolicy": output,
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, GateError, ReportValidationError, KeyError, AttributeError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        print(f"SciRepro approval rejected: {safe_error_message(exc)}", file=sys.stderr)
        return 2
    except Exception:
        # Approval files are untrusted input. Fail closed without exposing a traceback.
        print("SciRepro approval rejected: malformed approval or report", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
