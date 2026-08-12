"""Small, deterministic fixtures created entirely inside each test workspace."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def tiny_png() -> bytes:
    """Return a valid metadata-free 2 x 2 RGB PNG without third-party libraries."""
    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    rows = b"\x00\x20\x70\xd0\xd0\x80\x20" + b"\x00\xd0\x80\x20\x20\x70\xd0"
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(rows)) + _png_chunk(b"IEND", b"")


def _canonical_manifest(manifest: dict) -> bytes:
    clone = json.loads(json.dumps(manifest))
    clone.setdefault("integrity", {})["manifestSha256"] = ""
    return json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def create_target_workspace(root: Path, target_id: str = "target-01") -> tuple[Path, str]:
    original = root / "originals" / (target_id + ".png")
    normalized = root / "normalized" / (target_id + ".png")
    payload = tiny_png()
    original.parent.mkdir(parents=True, exist_ok=True)
    normalized.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(payload)
    normalized.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    manifest = {
        "schemaVersion": "scirepro.targets/v1",
        "targetSetId": "test-target-set",
        "createdAt": "2026-08-12T00:00:00Z",
        "paper": None,
        "targetCount": 1,
        "targets": [
            {
                "targetId": target_id,
                "acquisitionMode": "images-only",
                "workflowMode": "image-derived-reconstruction",
                "identityStatus": "not-applicable",
                "requestedAs": "test image",
                "figureReference": None,
                "paperPage": None,
                "caption": None,
                "originalPath": original.relative_to(root).as_posix(),
                "normalizedPath": normalized.relative_to(root).as_posix(),
                "sourceFileName": original.name,
                "sourceSha256": digest,
                "normalizedSha256": digest,
                "targetSha256": digest,
                "mediaType": "image/png",
                "width": 2,
                "height": 2,
                "dpi": 300,
                "cropBoxPdfPoints": None,
                "captionIncluded": False,
                "qaStatus": "verified",
                "localAnalysisOnly": True,
                "notes": ["Synthetic offline test target."],
            }
        ],
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "json-sort-keys-v1",
            "manifestSha256": "",
        },
    }
    manifest["integrity"]["manifestSha256"] = hashlib.sha256(_canonical_manifest(manifest)).hexdigest()
    path = root / "manifest.json"
    write_json(path, manifest)
    return path, digest


def create_report_input(path: Path, target_id: str = "target-01") -> Path:
    requirements = []
    for category in ("input", "method", "protocol", "validation", "environment"):
        requirements.append(
            {
                "requirementId": "req-" + category,
                "category": category,
                "label": category.title(),
                "state": "not-required",
                "blocking": False,
                "detail": "Not required by this bounded image-derived test route.",
                "evidenceRefs": ["src-target"],
            }
        )
    report = {
        "schemaVersion": "reprofig.report/v3",
        "reportId": "rpt-offline-fixture",
        "generatedAt": "2026-08-12T00:00:00Z",
        "generator": {"name": "scirepro-test", "version": "1"},
        "workflow": {"stage": "awaiting-approval", "executionAllowed": False, "approvalRequired": True},
        "integrity": {"algorithm": "sha256", "canonicalization": "json-sort-keys-v1", "reportSha256": ""},
        "audience": "local",
        "targetSet": {
            "targetSetId": "test-target-set",
            "manifestSha256": "0" * 64,
            "targetCount": 1,
            "acquisitionModes": ["images-only"],
        },
        "paper": None,
        "summary": {
            "objective": "Exercise the offline report builder.",
            "overallLevel": "image-derived-reconstruction",
            "oneLine": "A small visible target can be reconstructed locally.",
            "figureCount": 1,
        },
        "environment": [],
        "sources": [
            {
                "sourceId": "src-target",
                "kind": "target-image",
                "title": "Synthetic target",
                "access": {"state": "local", "checkedAt": "2026-08-12T00:00:00Z"},
                "license": {"state": "unknown"},
            }
        ],
        "figures": [
            {
                "figureId": "figure-01",
                "label": "Test figure",
                "page": None,
                "section": None,
                "caption": "Synthetic 2 x 2 target.",
                "target": {
                    "targetId": target_id,
                    "acquisitionMode": "images-only",
                    "workflowMode": "image-derived-reconstruction",
                    "requestedRef": None,
                    "targetSha256": "0" * 64,
                    "materialization": {
                        "method": "user-upload",
                        "qaStatus": "verified",
                        "page": None,
                        "renderDpi": 300,
                        "captionIncluded": False,
                        "sourceFileName": None,
                        "figureReference": None,
                        "cropBoxPdfPoints": None,
                        "width": 2,
                        "height": 2,
                    },
                },
                "image": {"sourceRef": "src-target"},
                "understanding": {
                    "visualSummary": "A tiny synthetic raster used only for builder regression testing.",
                    "observations": [
                        {
                            "observationId": "obs-visible",
                            "location": "entire target",
                            "statement": "The raster has visible coloured pixels.",
                            "confidence": "high",
                            "evidenceRefs": ["src-target"],
                        }
                    ],
                    "paperClaim": None,
                    "evidenceRole": "Visible-geometry reconstruction only.",
                    "authorInterpretation": None,
                    "limitations": ["No paper or scientific claim is attached."],
                },
                "generationLogic": {
                    "inputs": [
                        {
                            "inputId": "input-raster",
                            "label": "Visible raster",
                            "description": "The user-visible target pixels.",
                            "origin": "user",
                            "evidenceRefs": ["src-target"],
                        }
                    ],
                    "steps": [
                        {
                            "stepId": "step-copy",
                            "label": "Read geometry",
                            "description": "Read the bounded visible geometry without scientific inference.",
                            "origin": "derived",
                            "evidenceRefs": ["src-target"],
                        }
                    ],
                    "plotMapping": {
                        "description": "Pixels map directly to visible output geometry.",
                        "encodings": ["pixel colour"],
                        "evidenceRefs": ["src-target"],
                    },
                    "unknowns": ["Original generating process is unknown."],
                },
                "validationTargets": [
                    {
                        "targetId": "validate-visible",
                        "label": "Visible geometry",
                        "kind": "visual-fidelity",
                        "origin": "derived",
                        "observable": "Generated raster dimensions and visible colours.",
                        "criterion": "The output can be compared visibly with the target.",
                        "supportsClaim": "Only visible fidelity; no scientific claim.",
                        "evidenceRefs": ["src-target"],
                    }
                ],
                "reproduction": {
                    "level": "image-derived-reconstruction",
                    "verdict": "A bounded visual reconstruction route is available.",
                    "confidence": "high",
                    "assessment": "The local target is sufficient for a non-scientific visual reconstruction.",
                    "recommendedRouteId": "route-local",
                },
                "requirements": requirements,
                "routes": [
                    {
                        "routeId": "route-local",
                        "label": "Local visual route",
                        "status": "ready",
                        "recommended": True,
                        "scientificScope": {
                            "goal": "Reconstruct visible geometry only.",
                            "reproducesObservationIds": ["obs-visible"],
                            "claimCoverage": "No paper claim is tested.",
                            "doesNotReproduce": ["Original data and method"],
                            "substitutions": [],
                            "assumptions": [],
                            "validationTargetIds": ["validate-visible"],
                            "recommendationRationale": "The target itself is sufficient for the bounded goal.",
                        },
                        "engine": "Local Python",
                        "environmentIds": [],
                        "requirementIds": [item["requirementId"] for item in requirements],
                        "deliverables": [{"kind": "figure", "extension": ".png", "label": "Reconstructed target"}],
                        "parameters": [],
                        "effects": ["run-local-code", "create-workspace-files"],
                        "estimated": {"downloadBytes": 0, "diskBytes": 4096, "runtimeMinutes": 0.1, "gpu": False, "costUsd": 0},
                        "plan": ["Read the target and create a bounded local output."],
                        "blockers": [],
                    }
                ],
                "sourceRefs": ["src-target"],
            }
        ],
        "approvalPolicy": {
            "minFigures": 1,
            "maxFigures": 1,
            "defaultOutputPolicy": "create-only",
            "allowedEffects": ["run-local-code", "create-workspace-files"],
            "consentRequiredEffects": [],
            "ttlMinutes": 60,
        },
    }
    write_json(path, report)
    return path
