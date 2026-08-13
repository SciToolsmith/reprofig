from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.fixture_factory import create_report_input, create_target_workspace, write_json


REPO = Path(__file__).resolve().parents[1]
BUNDLER = REPO / "scirepro" / "scripts" / "finalize_run_bundle.py"
REPORT_BUILDER = REPO / "scirepro" / "scripts" / "build_report.py"
PLAN_GATE = REPO / "scirepro" / "scripts" / "plan_gate.py"
sys.path.insert(0, str(BUNDLER.parent))
from finalize_run_bundle import validate_target_documents  # noqa: E402


def run_bundle(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, str(BUNDLER), *args],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed


def rewrite_target_manifest(path: Path, mutator) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutator(manifest)
    clone = json.loads(json.dumps(manifest))
    clone["integrity"]["manifestSha256"] = ""
    manifest["integrity"]["manifestSha256"] = hashlib.sha256(
        json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(path, manifest)


def canonical_json_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def rehash_tampered_archived_authority(final: Path, mutator) -> None:
    """Mutate approval/gate and recompute every superficial integrity binding."""
    approval_path = final / "shared/plan/approval.json"
    gate_path = final / "shared/plan/gate-result.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    mutator(approval, gate)
    write_json(approval_path, approval)
    approval_sha = hashlib.sha256(approval_path.read_bytes()).hexdigest()
    gate["approvalSha256"] = approval_sha
    write_json(gate_path, gate)

    manifest_path = final / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["planBindings"]["approvalSha256"] = approval_sha
    gate_pretty = (json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest["planBindings"]["gateResultSha256"] = hashlib.sha256(gate_pretty).hexdigest()
    changed = {
        "shared/plan/approval.json": approval_path,
        "shared/plan/gate-result.json": gate_path,
    }
    for entry in manifest["files"]:
        if entry["path"] in changed:
            path = changed[entry["path"]]
            entry["sizeBytes"] = path.stat().st_size
            entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest["integrity"]["inventorySha256"] = canonical_json_hash(manifest["files"])
    clone = json.loads(json.dumps(manifest))
    clone["integrity"]["manifestSha256"] = ""
    manifest["integrity"]["manifestSha256"] = canonical_json_hash(clone)
    write_json(manifest_path, manifest)


def init_bundle(parent: Path, run_id: str, targets: list[str]) -> Path:
    args = ["init", "--parent", str(parent), "--run-id", run_id, "--json"]
    for target in targets:
        args.extend(["--target", target])
    completed = run_bundle(*args)
    return Path(json.loads(completed.stdout)["path"])


def init_approved_bundle(
    parent: Path,
    run_id: str,
    target_id: str = "figure-01",
    *,
    initialize: bool = True,
    distribution: str = "local-private",
) -> Path | dict[str, Path]:
    workspace = parent / "workspace"
    target_manifest, target_sha = create_target_workspace(workspace / "phase-zero", target_id)
    report_input = create_report_input(workspace / "report-input.json", target_id)
    approved_report_bundle = workspace / (
        "report-bundle" if distribution == "local-private" else "report-bundle-local"
    )
    built = subprocess.run(
        [
            sys.executable,
            str(REPORT_BUILDER),
            "--input",
            str(report_input),
            "--output",
            str(approved_report_bundle),
            "--target-manifest",
            str(target_manifest),
            "--audience",
            "local",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    if built.returncode != 0:
        raise AssertionError(built.stderr)
    report_path = approved_report_bundle / "report.json"
    report_bundle = approved_report_bundle
    if distribution == "shareable":
        report_bundle = workspace / "report-bundle"
        public_build = subprocess.run(
            [
                sys.executable,
                str(REPORT_BUILDER),
                "--input",
                str(report_input),
                "--output",
                str(report_bundle),
                "--target-manifest",
                str(target_manifest),
                "--audience",
                "public",
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
        )
        if public_build.returncode != 0:
            raise AssertionError(public_build.stderr)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    relative_root = f"outputs/{run_id}"
    approval = {
        "schemaVersion": "reprofig.approval/v1",
        "approvalId": f"approval-{run_id}",
        "reportId": report["reportId"],
        "reportSha256": report["integrity"]["reportSha256"],
        "decision": "approve",
        "createdAt": now.isoformat().replace("+00:00", "Z"),
        "expiresAt": (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
        "selectedFigures": [
            {
                "figureId": "figure-01",
                "sourceImageSha256": target_sha,
                "routeId": "route-local",
                "parameters": {},
                "deliverables": ["figure"],
            }
        ],
        "outputPolicy": {
            "relativeRoot": relative_root,
            "mode": "create-only",
            "overwrite": "never",
            "explicitFiles": [],
        },
        "authorizedEffects": ["run-local-code", "create-workspace-files"],
        "acknowledgements": [],
        "idempotencyKey": f"idempotency-{run_id}",
    }
    approval_path = workspace / "approval.json"
    write_json(approval_path, approval)
    gate = subprocess.run(
        [
            sys.executable,
            str(PLAN_GATE),
            "--report",
            str(report_path),
            "--approval",
            str(approval_path),
            "--target-manifest",
            str(target_manifest),
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    if gate.returncode != 0:
        raise AssertionError(gate.stderr)
    gate_path = workspace / "gate-result.json"
    gate_path.write_text(gate.stdout, encoding="utf-8")
    output_root = workspace / relative_root
    context = {
        "workspace": workspace,
        "output_root": output_root,
        "target_manifest": target_manifest,
        "report_input": report_input,
        "report": report_path,
        "report_bundle": report_bundle,
        "approved_report_bundle": approved_report_bundle,
        "approval": approval_path,
        "gate": gate_path,
        "distribution": distribution,
    }
    if not initialize:
        return context
    return init_from_plan(context, run_id)


def init_from_plan(context: dict[str, Path], run_id: str, *, check: bool = True) -> Path | subprocess.CompletedProcess[str]:
    completed = run_bundle(
        "init",
        "--output-root",
        str(context["output_root"]),
        "--workspace-root",
        str(context["workspace"]),
        "--run-id",
        run_id,
        "--report",
        str(context["report"]),
        "--target-manifest",
        str(context["target_manifest"]),
        "--approval",
        str(context["approval"]),
        "--gate-result",
        str(context["gate"]),
        "--json",
        "--distribution",
        str(context.get("distribution", "local-private")),
        check=check,
    )
    if not check:
        return completed
    return Path(json.loads(completed.stdout)["path"])


def complete_target(staging: Path, target_id: str, *, image_derived: bool = False) -> None:
    calibration = add_bounded_calibration(staging, target_id)
    result_path = staging / "targets" / target_id / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.update(
        {
            "operationalStatus": "complete",
            "claimStatus": "not-applicable" if image_derived else "supported",
            "summary": "The bounded test run completed.",
            "outputs": [calibration["baselineV0"]],
            "calibration": calibration,
        }
    )
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary_path = staging / "targets" / target_id / "validation" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        {
            "status": "passed",
            "summary": "The declared test criterion passed.",
            "artifacts": [
                *(item["artifact"] for item in calibration["comparisons"]),
                calibration["differenceSummary"],
                calibration["visualQualityCheck"],
                calibration["adjustments"],
            ],
        }
    )
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    environment_path = staging / "shared" / "environment" / "environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    environment["captureStatus"] = "recorded"
    environment["runtime"] = {"name": "python", "version": sys.version.split()[0]}
    environment_path.write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")

    resource_path = staging / "shared" / "execution" / "resource-usage.json"
    resources = json.loads(resource_path.read_text(encoding="utf-8"))
    resources["measurementStatus"] = "partial"
    resources["wallSeconds"] = 0.01
    resource_path.write_text(json.dumps(resources, indent=2) + "\n", encoding="utf-8")

    sources_path = staging / "shared" / "provenance" / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    if not sources["sources"]:
        sources["sources"].append(
            {
                "sourceId": "synthetic-test-input",
                "kind": "generated-test-fixture",
                "title": "Synthetic offline input",
                "redistributionStatus": "generated",
            }
        )
    sources_path.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")


def write_svg(path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40">'
        f'<text x="4" y="24">{label}</text></svg>\n',
        encoding="utf-8",
    )


def add_bounded_calibration(staging: Path, target_id: str) -> dict:
    target_prefix = f"targets/{target_id}"
    baseline = f"{target_prefix}/outputs/baseline-v0.svg"
    comparison = f"{target_prefix}/validation/comparisons/original-vs-v0.svg"
    difference = f"{target_prefix}/validation/difference-summary.json"
    quality = f"{target_prefix}/validation/visual-quality-check.json"
    adjustments = f"{target_prefix}/adjustments.json"
    sources = json.loads((staging / "shared/provenance/sources.json").read_text(encoding="utf-8"))["sources"]
    if sources:
        source_id = sources[0]["sourceId"]
        redistribution = sources[0]["redistributionStatus"]
        target_pixels_included = sources[0].get("includedPath") is not None
    else:
        source_id = "synthetic-test-input"
        redistribution = "generated"
        target_pixels_included = True
    comparison_record = {
        "comparisonId": "original-vs-v0",
        "output": baseline,
        "mode": "side-by-side" if target_pixels_included else "metrics-only",
        "artifact": comparison,
        "targetPixelRights": {
            "included": target_pixels_included,
            "sourceId": source_id if target_pixels_included else None,
            "redistributionStatus": redistribution if target_pixels_included else "not-included",
        },
    }
    write_svg(staging / baseline, "V0")
    write_svg(staging / comparison, "original vs V0")
    write_json(
        staging / difference,
        {
            "schemaVersion": "scirepro.difference-summary/v2",
            "targetId": target_id,
            "baseline": baseline,
            "selected": baseline,
            "dimensions": {
                "axesUnitsScale": "Axes, units, and scale agree with the test fixture.",
                "trendsPeaksMagnitude": "The declared deterministic trend agrees.",
                "colorsLinesLegends": "Styling is legible; exact color is not evidence.",
                "layoutTypography": "The compact fixture has no layout defect.",
            },
            "scientificConclusion": "The synthetic criterion is supported.",
            "remainingDifferences": [],
        },
    )
    write_json(
        staging / quality,
        {
            "schemaVersion": "scirepro.visual-quality-check/v2",
            "targetId": target_id,
            "status": "passed",
            "checks": {
                "textOverlap": "No overlap detected.",
                "legendDataOverlap": "No legend is present.",
                "clipping": "Nothing is clipped.",
                "contrast": "Contrast is sufficient.",
                "readability": "Text remains readable.",
            },
            "issuesRemaining": [],
        },
    )
    write_json(
        staging / adjustments,
        {
            "schemaVersion": "scirepro.adjustments/v2",
            "targetId": target_id,
            "rounds": [],
            "selectedOutput": baseline,
            "stopReason": "The baseline already satisfies the scientific criterion and quality checks.",
        },
    )
    return {
        "baselineV0": baseline,
        "scientificV1": None,
        "presentationV2": None,
        "selectedOutput": baseline,
        "comparisons": [comparison_record],
        "differenceSummary": difference,
        "visualQualityCheck": quality,
        "adjustments": adjustments,
    }


def add_valid_two_rounds(staging: Path, target_id: str) -> dict[str, Path | str]:
    target = staging / "targets" / target_id
    v1 = f"targets/{target_id}/outputs/calibrated-v1.svg"
    v2 = f"targets/{target_id}/outputs/final-v2.svg"
    comparison = f"targets/{target_id}/validation/comparisons/original-vs-final.svg"
    write_svg(staging / v1, "V1")
    write_svg(staging / v2, "V2")
    write_svg(staging / comparison, "original vs V2")
    result_path = target / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    rights = result["calibration"]["comparisons"][0]["targetPixelRights"]
    result["outputs"].extend([v1, v2])
    result["calibration"].update(
        {
            "scientificV1": v1,
            "presentationV2": v2,
            "selectedOutput": v2,
            "comparisons": [
                result["calibration"]["comparisons"][0],
                {
                    "comparisonId": "original-vs-final",
                    "output": v2,
                    "mode": "side-by-side",
                    "artifact": comparison,
                    "targetPixelRights": rights,
                },
            ],
        }
    )
    write_json(result_path, result)
    validation_path = target / "validation/summary.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["artifacts"].append(comparison)
    write_json(validation_path, validation)
    difference_path = target / "validation/difference-summary.json"
    difference = json.loads(difference_path.read_text(encoding="utf-8"))
    difference["selected"] = v2
    write_json(difference_path, difference)
    adjustments_path = target / "adjustments.json"
    adjustments = json.loads(adjustments_path.read_text(encoding="utf-8"))
    adjustments.update(
        {
            "selectedOutput": v2,
            "stopReason": "The scientific criterion passes and presentation is readable.",
            "rounds": [
                {
                    "round": 1,
                    "kind": "scientific-difference",
                    "output": v1,
                    "rationale": "Correct a diagnosed unit conversion.",
                    "changes": [{
                        "changeDomain": "unit-conversion",
                        "subject": "amplitude unit",
                        "before": "V",
                        "after": "mV",
                        "reason": "Match the declared measurement unit.",
                        "diagnosisRef": "difference-summary:axesUnitsScale",
                        "evidenceRefs": ["paper-axis-label"],
                        "scientificBasis": None,
                    }],
                },
                {
                    "round": 2,
                    "kind": "presentation-quality",
                    "output": v2,
                    "rationale": "Repair a label overlap without changing data interpretation.",
                    "changes": [{
                        "changeDomain": "overlap",
                        "subject": "x-axis label spacing",
                        "before": 2,
                        "after": 8,
                        "reason": "Prevent text overlap.",
                    }],
                },
            ],
        }
    )
    write_json(adjustments_path, adjustments)
    return {"target": target, "v1": v1, "v2": v2, "comparison": comparison, "adjustments": adjustments_path}


def report_source_for(staging: Path) -> Path:
    for parent in staging.parents:
        candidate = parent / "report-bundle"
        if candidate.is_dir():
            return candidate
    raise AssertionError(f"could not locate report source for {staging}")


class RunBundleTests(unittest.TestCase):
    def test_complete_requires_a_preserved_v0_and_comparison_records(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_approved_bundle(Path(raw), "missing-calibration")
            complete_target(staging, "figure-01", image_derived=True)
            result_path = staging / "targets/figure-01/result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["calibration"] = None
            write_json(result_path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete",
                "--result-report", str(report_source_for(staging)), check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("requires calibration metadata", completed.stderr)

    def test_optional_v1_v2_rounds_and_final_comparison_are_valid(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_approved_bundle(Path(raw), "bounded-rounds")
            complete_target(staging, "figure-01", image_derived=True)
            target = staging / "targets/figure-01"
            v1 = "targets/figure-01/outputs/calibrated-v1.svg"
            v2 = "targets/figure-01/outputs/final-v2.svg"
            final_comparison = "targets/figure-01/validation/comparisons/original-vs-final.svg"
            write_svg(staging / v1, "V1")
            write_svg(staging / v2, "V2")
            write_svg(staging / final_comparison, "original vs V2")

            result_path = target / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["outputs"].extend([v1, v2])
            result["calibration"].update(
                {
                    "scientificV1": v1,
                    "presentationV2": v2,
                    "selectedOutput": v2,
                    "comparisons": [
                        result["calibration"]["comparisons"][0],
                        {
                            "comparisonId": "original-vs-final",
                            "output": v2,
                            "mode": "side-by-side",
                            "artifact": final_comparison,
                            "targetPixelRights": {
                                "included": True,
                                "sourceId": "phase0-figure-01",
                                "redistributionStatus": "local-only",
                            },
                        },
                    ],
                }
            )
            write_json(result_path, result)

            summary_path = target / "validation/summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["artifacts"].append(final_comparison)
            write_json(summary_path, summary)

            difference_path = target / "validation/difference-summary.json"
            difference = json.loads(difference_path.read_text(encoding="utf-8"))
            difference["selected"] = v2
            difference["remainingDifferences"] = ["A non-critical palette difference remains."]
            write_json(difference_path, difference)

            adjustments_path = target / "adjustments.json"
            adjustments = json.loads(adjustments_path.read_text(encoding="utf-8"))
            adjustments.update(
                {
                    "selectedOutput": v2,
                    "stopReason": "The scientific criterion passes and remaining differences are cosmetic.",
                    "rounds": [
                        {
                            "round": 1,
                            "kind": "scientific-difference",
                            "output": v1,
                            "rationale": "Correct the documented unit conversion.",
                            "changes": [{
                                "changeDomain": "unit-conversion",
                                "subject": "scale",
                                "before": "raw units",
                                "after": "declared units",
                                "reason": "unit correction",
                                "diagnosisRef": "difference-summary:axesUnitsScale",
                                "evidenceRefs": [],
                                "scientificBasis": "The declared axis unit requires this conversion.",
                            }],
                        },
                        {
                            "round": 2,
                            "kind": "presentation-quality",
                            "output": v2,
                            "rationale": "Remove label overlap and align axis presentation.",
                            "changes": [{
                                "changeDomain": "legend",
                                "subject": "legend position",
                                "before": "over data",
                                "after": "clear margin",
                                "reason": "readability",
                            }],
                        },
                    ],
                }
            )
            write_json(adjustments_path, adjustments)

            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete",
                "--result-report", str(report_source_for(staging)), "--json",
            )
            final = Path(json.loads(completed.stdout)["path"])
            self.assertEqual(run_bundle("validate", "--bundle", str(final)).returncode, 0)
            result_html = (final / "report/index.html").read_text(encoding="utf-8")
            self.assertIn("original-vs-final.svg", result_html)
            self.assertIn("V0 · untuned baseline", result_html)
            self.assertIn("V1 · scientific correction", result_html)
            self.assertIn("V2 · presentation quality", result_html)
            self.assertIn("Scientific conclusion / 科学结论", result_html)
            self.assertIn("Visual QA / 视觉质检", result_html)
            self.assertIn("Stop reason / 停止原因", result_html)

    def test_legacy_v1_target_result_requires_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_bundle(Path(raw), "legacy-v1", ["figure-01"])
            result_path = staging / "targets/figure-01/result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["schemaVersion"] = "scirepro.target-result/v1"
            write_json(result_path, result)
            completed = run_bundle(
                "finalize",
                "--bundle",
                str(staging),
                "--status",
                "blocked",
                "--reason",
                "Legacy records must be regenerated.",
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("unsupported result schema", completed.stderr)

    def test_round_three_requires_new_hypothesis_and_specific_approval(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_approved_bundle(Path(raw), "third-round")
            complete_target(staging, "figure-01", image_derived=True)
            target = staging / "targets/figure-01"
            v1 = "targets/figure-01/outputs/calibrated-v1.svg"
            v2 = "targets/figure-01/outputs/final-v2.svg"
            v3 = "targets/figure-01/outputs/calibrated-v3.svg"
            final_comparison = "targets/figure-01/validation/comparisons/original-vs-final.svg"
            write_svg(staging / v1, "V1")
            write_svg(staging / v2, "V2")
            write_svg(staging / v3, "V3")
            write_svg(staging / final_comparison, "original vs V3")

            result_path = target / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["outputs"].extend([v1, v2, v3])
            result["calibration"].update(
                {"scientificV1": v1, "presentationV2": v2, "selectedOutput": v3}
            )
            result["calibration"]["comparisons"].append(
                {
                    "comparisonId": "original-vs-final",
                    "output": v3,
                    "mode": "side-by-side",
                    "artifact": final_comparison,
                    "targetPixelRights": {
                        "included": True,
                        "sourceId": "phase0-figure-01",
                        "redistributionStatus": "local-only",
                    },
                }
            )
            write_json(result_path, result)
            summary_path = target / "validation/summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["artifacts"].append(final_comparison)
            write_json(summary_path, summary)
            difference_path = target / "validation/difference-summary.json"
            difference = json.loads(difference_path.read_text(encoding="utf-8"))
            difference["selected"] = v3
            write_json(difference_path, difference)
            adjustments_path = target / "adjustments.json"
            adjustments = json.loads(adjustments_path.read_text(encoding="utf-8"))
            adjustments["selectedOutput"] = v3
            adjustments["rounds"] = [
                {
                    "round": 1,
                    "kind": "scientific-difference",
                    "output": v1,
                    "rationale": "Test the initial scientifically justified correction.",
                    "changes": [{
                        "changeDomain": "unit-conversion",
                        "subject": "scale",
                        "before": "raw units",
                        "after": "declared units",
                        "reason": "unit correction",
                        "diagnosisRef": "difference-summary:axesUnitsScale",
                        "evidenceRefs": [],
                        "scientificBasis": "The axis definition requires the conversion.",
                    }],
                },
                {
                    "round": 2,
                    "kind": "presentation-quality",
                    "output": v2,
                    "rationale": "Repair the documented label overlap.",
                    "changes": [{
                        "changeDomain": "legend",
                        "subject": "legend position",
                        "before": "over data",
                        "after": "clear margin",
                        "reason": "readability",
                    }],
                },
                {
                    "round": 3,
                    "kind": "scientific-hypothesis",
                    "output": v3,
                    "rationale": "Test a newly identified boundary-condition hypothesis.",
                    "changes": [{
                        "changeDomain": "parameter",
                        "subject": "boundary condition",
                        "before": "fixed",
                        "after": "periodic",
                        "reason": "testable hypothesis",
                        "diagnosisRef": "difference-summary:trendsPeaksMagnitude",
                        "evidenceRefs": ["paper-equation-boundary"],
                        "scientificBasis": "Periodic closure predicts the observed trend.",
                    }],
                    "hypothesis": "The published trend depends on a periodic boundary condition.",
                }
            ]
            write_json(adjustments_path, adjustments)
            failed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete",
                "--result-report", str(report_source_for(staging)), check=False,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("requires targets/figure-01/validation/calibration-round-3-approval.json", failed.stderr)

            approval_relative = "targets/figure-01/validation/calibration-round-3-approval.json"
            write_json(
                staging / approval_relative,
                {
                    "schemaVersion": "scirepro.calibration-approval/v2",
                    "approvalId": "approval-third-round-3",
                    "idempotencyKey": "third-round-3-once",
                    "targetId": "figure-01",
                    "round": 3,
                    "decision": "approve",
                    "hypothesis": "The published trend depends on a periodic boundary condition.",
                    "approvedAt": "2026-08-12T12:00:00Z",
                    "previousOutput": v2,
                    "previousOutputSha256": hashlib.sha256((staging / v2).read_bytes()).hexdigest(),
                    "maxAttempts": 1,
                },
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            adjustments = json.loads(adjustments_path.read_text(encoding="utf-8"))
            adjustments["rounds"][2]["approvalEvidence"] = approval_relative
            write_json(adjustments_path, adjustments)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["artifacts"].append(approval_relative)
            write_json(summary_path, summary)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete",
                "--result-report", str(report_source_for(staging)), "--json",
            )
            final = Path(json.loads(completed.stdout)["path"])
            self.assertEqual(run_bundle("validate", "--bundle", str(final)).returncode, 0)

    def test_adjustment_schema_rejects_visual_science_mixing_and_boolean_rounds(self) -> None:
        cases = (
            ("boolean-round", lambda rounds: rounds[0].update({"round": True}), "positive integer"),
            (
                "visual-v1",
                lambda rounds: rounds[0]["changes"][0].update({"changeDomain": "palette"}),
                "must be scientific",
            ),
            (
                "scientific-v2",
                lambda rounds: rounds[1]["changes"][0].update({"changeDomain": "axis-scale"}),
                "presentation-only",
            ),
            ("empty-change", lambda rounds: rounds[0].update({"changes": [{}]}), "missing or unknown fields"),
        )
        for index, (label, mutate, expected) in enumerate(cases):
            with self.subTest(case=label), tempfile.TemporaryDirectory() as raw:
                staging = init_bundle(Path(raw), f"strict-round-{index}", ["figure-01"])
                complete_target(staging, "figure-01")
                configured = add_valid_two_rounds(staging, "figure-01")
                adjustments_path = configured["adjustments"]
                assert isinstance(adjustments_path, Path)
                adjustments = json.loads(adjustments_path.read_text(encoding="utf-8"))
                mutate(adjustments["rounds"])
                write_json(adjustments_path, adjustments)
                result = json.loads((configured["target"] / "result.json").read_text(encoding="utf-8"))
                validation = json.loads((configured["target"] / "validation/summary.json").read_text(encoding="utf-8"))
                with self.assertRaisesRegex(ValueError, expected):
                    validate_target_documents(
                        staging,
                        "figure-01",
                        result,
                        validation,
                        terminal=True,
                        distribution_class="local-private",
                    )

    def test_shareable_comparison_requires_metrics_only_or_redistribution_rights(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_bundle(Path(raw), "share-comparison", ["figure-01"])
            complete_target(staging, "figure-01")
            sources_path = staging / "shared/provenance/sources.json"
            sources = json.loads(sources_path.read_text(encoding="utf-8"))
            sources["sources"][0]["redistributionStatus"] = "local-only"
            write_json(sources_path, sources)
            result_path = staging / "targets/figure-01/result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            rights = result["calibration"]["comparisons"][0]["targetPixelRights"]
            rights["redistributionStatus"] = "local-only"
            write_json(result_path, result)
            validation_path = staging / "targets/figure-01/validation/summary.json"
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "lacks target-pixel redistribution rights"):
                validate_target_documents(
                    staging,
                    "figure-01",
                    result,
                    validation,
                    terminal=True,
                    distribution_class="shareable",
                )

            comparison = result["calibration"]["comparisons"][0]
            comparison["mode"] = "metrics-only"
            comparison["targetPixelRights"] = {
                "included": False,
                "sourceId": None,
                "redistributionStatus": "not-included",
            }
            write_json(result_path, result)
            validate_target_documents(
                staging,
                "figure-01",
                result,
                validation,
                terminal=True,
                distribution_class="shareable",
            )

    def test_valid_negative_scientific_result_can_be_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_bundle(Path(raw), "unsupported-result", ["figure-01"])
            complete_target(staging, "figure-01")
            result_path = staging / "targets/figure-01/result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["claimStatus"] = "unsupported"
            result["summary"] = "The valid test completed but did not support the declared phenomenon."
            write_json(result_path, result)
            difference_path = staging / "targets/figure-01/validation/difference-summary.json"
            difference = json.loads(difference_path.read_text(encoding="utf-8"))
            difference["scientificConclusion"] = "The prespecified criterion is not supported."
            write_json(difference_path, difference)
            validation_path = staging / "targets/figure-01/validation/summary.json"
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            validate_target_documents(
                staging,
                "figure-01",
                result,
                validation,
                terminal=True,
                distribution_class="local-private",
            )

    def test_scientific_result_rejects_direct_misconduct_allegations(self) -> None:
        cases = (
            ("result", "The authors fabricated the reported result."),
            ("conclusion", "This proves research fraud."),
        )
        for index, (field, prose) in enumerate(cases):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as raw:
                staging = init_bundle(Path(raw), f"neutral-language-{index}", ["figure-01"])
                complete_target(staging, "figure-01")
                result_path = staging / "targets/figure-01/result.json"
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if field == "result":
                    result["summary"] = prose
                    write_json(result_path, result)
                else:
                    difference_path = staging / "targets/figure-01/validation/difference-summary.json"
                    difference = json.loads(difference_path.read_text(encoding="utf-8"))
                    difference["scientificConclusion"] = prose
                    write_json(difference_path, difference)
                validation = json.loads(
                    (staging / "targets/figure-01/validation/summary.json").read_text(encoding="utf-8")
                )
                with self.assertRaisesRegex(ValueError, "direct misconduct/fabrication allegation"):
                    validate_target_documents(
                        staging,
                        "figure-01",
                        result,
                        validation,
                        terminal=True,
                        distribution_class="local-private",
                    )

    def test_complete_requires_resource_measurement(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_approved_bundle(Path(raw), "missing-resource-usage")
            complete_target(staging, "figure-01", image_derived=True)
            resource_path = staging / "shared/execution/resource-usage.json"
            resources = json.loads(resource_path.read_text(encoding="utf-8"))
            resources.update(
                {
                    "measurementStatus": "not-recorded",
                    "wallSeconds": None,
                    "peakMemoryBytes": None,
                    "diskBytes": None,
                    "networkBytes": None,
                    "cost": None,
                }
            )
            write_json(resource_path, resources)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete",
                "--result-report", str(report_source_for(staging)), check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("requires recorded or partial resource usage", completed.stderr)

    def test_failed_finalize_does_not_publish_a_partial_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = init_bundle(parent, "unfinished", ["figure-01"])
            protected = [
                staging / "README.md",
                staging / "targets" / "figure-01" / "result.json",
                staging / "targets" / "figure-01" / "validation" / "summary.json",
            ]
            before = {path: path.read_bytes() for path in protected}
            completed = run_bundle(
                "finalize",
                "--bundle",
                str(staging),
                "--status",
                "complete",
                "--json",
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertTrue(staging.is_dir())
            self.assertFalse((parent / "scirepro-run-unfinished").exists())
            self.assertFalse((staging / "manifest.json").exists())
            for path, payload in before.items():
                self.assertEqual(path.read_bytes(), payload)

    def test_init_can_derive_targets_from_phase_zero_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            target_manifest, _ = create_target_workspace(parent / "phase-zero", "uploaded-01")
            completed = run_bundle(
                "init",
                "--parent",
                str(parent),
                "--run-id",
                "from-manifest",
                "--target-manifest",
                str(target_manifest),
                "--json",
            )
            staging = Path(json.loads(completed.stdout)["path"])
            result = json.loads(
                (staging / "targets" / "uploaded-01" / "result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["workflowMode"], "image-derived-reconstruction")
            self.assertTrue((staging / "shared" / "plan" / "target-manifest.json").is_file())

    def test_single_target_finalize_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = init_approved_bundle(parent, "single")
            complete_target(staging, "figure-01", image_derived=True)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete",
                "--result-report", str(report_source_for(staging)), "--json",
            )
            final = Path(json.loads(completed.stdout)["path"])
            self.assertEqual(final.name, "scirepro-run-single")
            self.assertFalse(staging.exists())
            self.assertEqual(run_bundle("validate", "--bundle", str(final)).returncode, 0)
            manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["scope"]["targetIds"], ["figure-01"])
            self.assertTrue((final / "report" / "index.html").is_file())
            self.assertTrue((final / "report" / "decision" / "index.html").is_file())
            result_report = json.loads((final / "report" / "run-results.json").read_text(encoding="utf-8"))
            self.assertEqual(result_report["schemaVersion"], "scirepro.result-report/v2")
            self.assertEqual(result_report["targets"][0]["operationalStatus"], "complete")
            self.assertIn("report/index.html", (final / "README.md").read_text(encoding="utf-8"))

    def test_multi_target_uses_the_same_per_target_shape(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = init_bundle(
                parent,
                "multi",
                ["figure-01", "figure-02=image-derived-reconstruction"],
            )
            expected = {"result.json", "validation/summary.json"}
            for target_id in ("figure-01", "figure-02"):
                files = {
                    path.relative_to(staging / "targets" / target_id).as_posix()
                    for path in (staging / "targets" / target_id).rglob("*")
                    if path.is_file()
                }
                self.assertEqual(files, expected)
            completed = run_bundle(
                "finalize",
                "--bundle",
                str(staging),
                "--status",
                "blocked",
                "--reason",
                "Synthetic blocked test.",
                "--json",
            )
            final = Path(json.loads(completed.stdout)["path"])
            self.assertEqual(run_bundle("validate", "--bundle", str(final)).returncode, 0)
            manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["scope"]["targetCount"], 2)

    def _final_bundle(self, parent: Path, run_id: str) -> Path:
        staging = init_approved_bundle(parent, run_id)
        complete_target(staging, "figure-01", image_derived=True)
        completed = run_bundle(
            "finalize", "--bundle", str(staging), "--status", "complete",
            "--result-report", str(report_source_for(staging)), "--json",
        )
        return Path(json.loads(completed.stdout)["path"])

    def test_complete_requires_a_bound_result_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_approved_bundle(Path(raw), "missing-result-report")
            complete_target(staging, "figure-01", image_derived=True)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("requires --result-report", completed.stderr)
            self.assertTrue(staging.is_dir())
            self.assertFalse((staging / "report").exists())

    def test_result_report_must_match_the_approved_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = init_approved_bundle(parent, "wrong-result-report")
            complete_target(staging, "figure-01", image_derived=True)
            source = report_source_for(staging)
            report_path = source / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["reportId"] = "rpt-different"
            write_json(report_path, report)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete",
                "--result-report", str(source), check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertTrue(
                "hash mismatch" in completed.stderr
                or "size mismatch" in completed.stderr
                or "integrity" in completed.stderr
            )
            self.assertFalse((staging / "report").exists())

    def test_shareable_complete_uses_public_derivative_of_local_approved_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_approved_bundle(
                Path(raw), "shareable-approved-local", distribution="shareable",
            )
            complete_target(staging, "figure-01", image_derived=True)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete",
                "--result-report", str(report_source_for(staging)), "--json",
            )
            final = Path(json.loads(completed.stdout)["path"])
            self.assertEqual(run_bundle("validate", "--bundle", str(final)).returncode, 0)
            approved = json.loads(
                (final / "shared/plan/report.json").read_text(encoding="utf-8")
            )
            bundled = json.loads(
                (final / "report/decision/report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(approved["audience"], "local")
            self.assertEqual(bundled["audience"], "public")
            self.assertNotEqual(
                approved["integrity"]["reportSha256"],
                bundled["integrity"]["reportSha256"],
            )
            self.assertEqual(bundled["figures"][0]["image"]["bundleState"], "omitted-rights")
            self.assertFalse((final / "targets/figure-01/reference/target.png").exists())

    def test_shareable_public_derivative_cannot_change_approved_decision_content(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = init_approved_bundle(
                Path(raw), "shareable-changed-decision", initialize=False,
                distribution="shareable",
            )
            assert isinstance(context, dict)
            changed = json.loads(context["report_input"].read_text(encoding="utf-8"))
            changed["summary"]["oneLine"] = "A different scientific decision was substituted."
            changed_input = context["workspace"] / "changed-report-input.json"
            write_json(changed_input, changed)
            changed_public = context["workspace"] / "changed-public-report"
            built = subprocess.run(
                [
                    sys.executable,
                    str(REPORT_BUILDER),
                    "--input", str(changed_input),
                    "--output", str(changed_public),
                    "--target-manifest", str(context["target_manifest"]),
                    "--audience", "public",
                ],
                cwd=REPO,
                text=True,
                capture_output=True,
            )
            if built.returncode != 0:
                raise AssertionError(built.stderr)
            staging = init_from_plan(context, "shareable-changed-decision")
            assert isinstance(staging, Path)
            complete_target(staging, "figure-01", image_derived=True)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete",
                "--result-report", str(changed_public), check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("decision content differs", completed.stderr)
            self.assertFalse((staging / "report").exists())

    def test_manifest_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            final = self._final_bundle(Path(raw), "tamper")
            readme = final / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
            completed = run_bundle("validate", "--bundle", str(final), check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("inventory", completed.stderr)

    def test_rehashed_archived_gate_cannot_expand_or_change_authority(self) -> None:
        cases = (
            (
                "undeclared-parameter",
                lambda approval, gate: (
                    approval["selectedFigures"][0]["parameters"].update({"seed": 999}),
                    gate["selectedTargets"][0]["parameters"].update({"seed": 999}),
                ),
                "undeclared parameter",
            ),
            (
                "missing-effect",
                lambda approval, gate: (
                    approval.update({"authorizedEffects": ["create-workspace-files"]}),
                    gate.update({"authorizedEffects": ["create-workspace-files"]}),
                ),
                "authorizedEffects differ",
            ),
            (
                "extra-effect",
                lambda approval, gate: (
                    approval.update({"authorizedEffects": ["create-workspace-files", "network", "run-local-code"]}),
                    gate.update({"authorizedEffects": ["create-workspace-files", "network", "run-local-code"]}),
                ),
                "authorizedEffects differ",
            ),
            (
                "acknowledgement-mismatch",
                lambda approval, gate: approval.update(
                    {
                        "acknowledgements": [
                            {"effect": "run-local-code", "acceptedAt": approval["createdAt"]}
                        ]
                    }
                ),
                "acknowledgements differ",
            ),
            (
                "undeclared-deliverable",
                lambda approval, gate: (
                    approval["selectedFigures"][0].update({"deliverables": ["figure", "table"]}),
                    gate["selectedTargets"][0].update({"deliverables": ["figure", "table"]}),
                ),
                "undeclared deliverable",
            ),
        )
        for label, mutate, expected in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as raw:
                final = self._final_bundle(Path(raw), f"authority-{label}")
                rehash_tampered_archived_authority(final, mutate)
                completed = run_bundle("validate", "--bundle", str(final), check=False)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(expected, completed.stderr)

    def test_untracked_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            final = self._final_bundle(Path(raw), "untracked")
            (final / "shared" / "execution" / "surprise.txt").write_text("not inventoried\n", encoding="utf-8")
            completed = run_bundle("validate", "--bundle", str(final), check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("inventory", completed.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlink support")
    def test_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            final = self._final_bundle(root, "symlink")
            os.symlink(final / "README.md", final / "shared" / "linked-readme")
            completed = run_bundle("validate", "--bundle", str(final), check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("symlink", completed.stderr)

    def test_init_rejects_unverified_or_bad_hash_target_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            manifest, _ = create_target_workspace(parent / "phase-zero", "figure-01")
            rewrite_target_manifest(manifest, lambda value: value["targets"][0].update({"qaStatus": "needs-review"}))
            completed = run_bundle(
                "init",
                "--parent",
                str(parent / "out"),
                "--run-id",
                "unverified",
                "--target-manifest",
                str(manifest),
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("not been visually verified", completed.stderr)

            rewrite_target_manifest(manifest, lambda value: value["targets"][0].update({"qaStatus": "verified"}))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["integrity"]["manifestSha256"] = "0" * 64
            write_json(manifest, value)
            completed = run_bundle(
                "init",
                "--parent",
                str(parent / "out2"),
                "--run-id",
                "bad-hash",
                "--target-manifest",
                str(manifest),
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("hash mismatch", completed.stderr)

    def test_init_rejects_invalid_approval_gate_and_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            context = init_approved_bundle(parent, "binding", initialize=False)
            assert isinstance(context, dict)
            approval = json.loads(context["approval"].read_text(encoding="utf-8"))
            approval["decision"] = "reject"
            write_json(context["approval"], approval)
            completed = init_from_plan(context, "binding", check=False)
            assert isinstance(completed, subprocess.CompletedProcess)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("approval gate rejected", completed.stderr)

            context = init_approved_bundle(parent / "gate", "gate-binding", initialize=False)
            assert isinstance(context, dict)
            gate = json.loads(context["gate"].read_text(encoding="utf-8"))
            gate["approvalId"] = "approval-tampered"
            write_json(context["gate"], gate)
            completed = init_from_plan(context, "gate-binding", check=False)
            assert isinstance(completed, subprocess.CompletedProcess)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("does not match", completed.stderr)

            context = init_approved_bundle(parent / "root", "root-binding", initialize=False)
            assert isinstance(context, dict)
            context["output_root"] = context["workspace"] / "wrong-output-root"
            completed = init_from_plan(context, "root-binding", check=False)
            assert isinstance(completed, subprocess.CompletedProcess)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("approval-bound path", completed.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlink support")
    def test_approved_output_root_rejects_symlinked_workspace_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            context = init_approved_bundle(parent, "symlink-output-root", initialize=False)
            assert isinstance(context, dict)
            outside = parent / "outside"
            outside.mkdir()
            os.symlink(outside, context["workspace"] / "outputs")
            completed = init_from_plan(context, "symlink-output-root", check=False)
            assert isinstance(completed, subprocess.CompletedProcess)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("symlinked component", completed.stderr)
            self.assertFalse((outside / "symlink-output-root").exists())

    def test_init_rejects_report_manifest_scope_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            context = init_approved_bundle(parent, "scope", initialize=False)
            assert isinstance(context, dict)
            rewrite_target_manifest(
                context["target_manifest"],
                lambda value: value.update({"targetSetId": "different-target-set"}),
            )
            completed = init_from_plan(context, "scope", check=False)
            assert isinstance(completed, subprocess.CompletedProcess)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("targetSetId mismatch", completed.stderr)

    def test_staging_target_identity_cannot_be_renamed_or_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = init_bundle(parent, "rename", ["figure-01"])
            (staging / "targets" / "figure-01").rename(staging / "targets" / "figure-evil")
            result_path = staging / "targets" / "figure-evil" / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["targetId"] = "figure-evil"
            write_json(result_path, result)
            summary_path = staging / "targets" / "figure-evil" / "validation" / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["targetId"] = "figure-evil"
            write_json(summary_path, summary)
            completed = run_bundle(
                "finalize",
                "--bundle",
                str(staging),
                "--status",
                "blocked",
                "--reason",
                "identity test",
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("initialized target set", completed.stderr)

    def test_artifact_references_must_be_safe_existing_and_scoped(self) -> None:
        bad_values = ["../outside.txt", "/Users/alice/secret.dat", "targets/other/outputs/x.png", "targets/figure-01/outputs/missing.png"]
        for index, bad in enumerate(bad_values):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as raw:
                parent = Path(raw)
                staging = init_bundle(parent, f"bad-ref-{index}", ["figure-01"])
                result_path = staging / "targets" / "figure-01" / "result.json"
                result = json.loads(result_path.read_text(encoding="utf-8"))
                result.update({"operationalStatus": "failed", "summary": "failed", "outputs": [bad]})
                write_json(result_path, result)
                completed = run_bundle(
                    "finalize",
                    "--bundle",
                    str(staging),
                    "--status",
                    "failed",
                    check=False,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertTrue("unsafe" in completed.stderr or "scope" in completed.stderr or "missing" in completed.stderr)

    def test_shareable_rejects_undeclared_artifact_local_path_and_secret(self) -> None:
        cases = ("arbitrary", "local-path", "secret")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw:
                parent = Path(raw)
                staging = Path(
                    json.loads(
                        run_bundle(
                            "init",
                            "--parent",
                            str(parent),
                            "--run-id",
                            f"share-{case}",
                            "--target",
                            "figure-01",
                            "--distribution",
                            "shareable",
                            "--json",
                        ).stdout
                    )["path"]
                )
                if case == "arbitrary":
                    path = staging / "shared" / "artifacts" / "restricted-paper.pdf"
                    path.parent.mkdir(parents=True)
                    path.write_bytes(b"restricted")
                else:
                    result_path = staging / "targets" / "figure-01" / "result.json"
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                    result.update({"operationalStatus": "blocked", "summary": "/Users/alice/secret.dat"})
                    if case == "secret":
                        result["summary"] = "api_key=abcdefghijk-secret-value"
                    write_json(result_path, result)
                completed = run_bundle(
                    "finalize",
                    "--bundle",
                    str(staging),
                    "--status",
                    "blocked",
                    "--reason",
                    "shareable negative test",
                    check=False,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertTrue(
                    "source declaration" in completed.stderr
                    or "absolute local path" in completed.stderr
                    or "possible secret" in completed.stderr
                )

    @unittest.skipUnless(hasattr(os, "mkfifo"), "platform has no FIFO support")
    def test_fifo_is_rejected_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = init_bundle(parent, "fifo", ["figure-01"])
            sources = staging / "shared" / "provenance" / "sources.json"
            sources.unlink()
            os.mkfifo(sources)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(BUNDLER),
                    "finalize",
                    "--bundle",
                    str(staging),
                    "--status",
                    "blocked",
                    "--reason",
                    "fifo test",
                ],
                cwd=REPO,
                text=True,
                capture_output=True,
                timeout=3,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("regular files", completed.stderr)

    def test_incoherent_status_tuple_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = init_bundle(parent, "tuple", ["figure-01"])
            output = staging / "targets" / "figure-01" / "outputs" / "partial.txt"
            output.parent.mkdir(parents=True)
            output.write_text("partial\n", encoding="utf-8")
            result_path = staging / "targets" / "figure-01" / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result.update(
                {
                    "operationalStatus": "partial",
                    "claimStatus": "supported",
                    "summary": "incoherent tuple",
                    "outputs": ["targets/figure-01/outputs/partial.txt"],
                }
            )
            write_json(result_path, result)
            completed = run_bundle(
                "finalize",
                "--bundle",
                str(staging),
                "--status",
                "failed",
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("incoherent", completed.stderr)

    def test_complete_requires_successful_gate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = init_bundle(parent, "ungated-complete", ["figure-01"])
            complete_target(staging, "figure-01")
            completed = run_bundle(
                "finalize",
                "--bundle",
                str(staging),
                "--status",
                "complete",
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("approval gate", completed.stderr)

    def test_manifest_metadata_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            final = self._final_bundle(Path(raw), "manifest-self-hash")
            manifest_path = final / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["finalizedAt"] = "2030-01-01T00:00:00Z"
            write_json(manifest_path, manifest)
            completed = run_bundle("validate", "--bundle", str(final), check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("self hash", completed.stderr)

    def test_target_reference_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = init_approved_bundle(parent, "reference-hash")
            reference = staging / "targets" / "figure-01" / "reference" / "target.png"
            reference.write_bytes(reference.read_bytes() + b"tamper")
            completed = run_bundle(
                "finalize",
                "--bundle",
                str(staging),
                "--status",
                "blocked",
                "--reason",
                "target integrity test",
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("sha256", completed.stderr)

    def test_publish_lock_failure_rolls_back_and_can_retry(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = init_bundle(parent, "retry-publish", ["figure-01"])
            lock = parent / "scirepro-run-retry-publish.publish.lock"
            lock.write_text("competing publisher\n", encoding="utf-8")
            failed = run_bundle(
                "finalize",
                "--bundle",
                str(staging),
                "--status",
                "blocked",
                "--reason",
                "bounded diagnostic",
                check=False,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertTrue((staging / ".scirepro-staging.json").is_file())
            self.assertFalse((staging / "manifest.json").exists())
            lock.unlink()
            succeeded = run_bundle(
                "finalize",
                "--bundle",
                str(staging),
                "--status",
                "blocked",
                "--reason",
                "bounded diagnostic",
                "--json",
            )
            final = Path(json.loads(succeeded.stdout)["path"])
            self.assertTrue(final.is_dir())
            self.assertEqual(run_bundle("validate", "--bundle", str(final)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
