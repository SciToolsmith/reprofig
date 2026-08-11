#!/usr/bin/env python3
"""Validate that a ReproFig approval is a safe subset of its report."""

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

from build_report import ReportError as ReportValidationError
from build_report import validate_report


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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "min" in spec:
            require(value >= spec["min"], f"{spec['parameterId']}: below minimum")
        if "max" in spec:
            require(value <= spec["max"], f"{spec['parameterId']}: above maximum")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--approval", required=True, type=Path)
    args = parser.parse_args()

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        approval = json.loads(args.approval.read_text(encoding="utf-8"))
        require(isinstance(report, dict), "report must be an object")
        require(isinstance(approval, dict), "approval must be an object")
        validate_report(report)
        require(report.get("schemaVersion") == "reprofig.report/v1", "unsupported report schema")
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
        maximum = int(policy.get("maxFigures", 3))
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
            expected_image_hash = figure.get("image", {}).get("sha256")
            require(selection.get("sourceImageSha256") == expected_image_hash, f"{figure_id}: image hash mismatch")
            routes = {route["routeId"]: route for route in figure.get("routes", [])}
            route_id = selection.get("routeId")
            require(route_id in routes, f"{figure_id}: unknown route")
            route = routes[route_id]
            require(route.get("status") != "blocked", f"{figure_id}: blocked route cannot be approved")

            route_effects = set(route.get("effects", []))
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

        print(json.dumps({
            "status": "valid",
            "reportId": report["reportId"],
            "reportSha256": expected_hash,
            "approvalId": approval_id,
            "idempotencyKey": idempotency_key,
            "replayProtection": "not-enforced-by-stateless-validator",
            "selectedFigures": figure_ids,
            "authorizedEffects": sorted(authorized),
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, GateError, ReportValidationError, KeyError, AttributeError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        print(f"ReproFig approval rejected: {safe_error_message(exc)}", file=sys.stderr)
        return 2
    except Exception:
        # Approval files are untrusted input. Fail closed without exposing a traceback.
        print("ReproFig approval rejected: malformed approval or report", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
