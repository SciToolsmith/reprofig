from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import contextlib
import io
from pathlib import Path
from unittest import mock

from tests.fixture_factory import create_report_input, create_target_workspace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scirepro" / "scripts"))
import build_report  # noqa: E402
import materialize_target_figures as materializer  # noqa: E402


REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "scirepro" / "scripts" / "build_report.py"
MATERIALIZER = REPO / "scirepro" / "scripts" / "materialize_target_figures.py"


class ReportBuilderTests(unittest.TestCase):
    def run_builder(self, root: Path, report_input: Path, target_manifest: Path, output_name: str = "report") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--input",
                str(report_input),
                "--output",
                str(root / output_name),
                "--target-manifest",
                str(target_manifest),
                "--audience",
                "local",
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
        )

    @staticmethod
    def add_formula_audit(report: dict) -> dict:
        report["figures"][0]["generationLogic"]["formulaAudit"] = {
            "scope": "target-chain-only",
            "included": ["Visible-coordinate transform"],
            "excluded": ["Unrelated theory"],
            "rationale": "The transform directly determines the reconstructed target geometry.",
            "items": [
                {
                    "checkId": "formula-coordinate-transform",
                    "label": "Coordinate transform",
                    "dependency": "Maps target pixels to the reconstructed output coordinates.",
                    "sourceStatement": "The bounded transform used by the reconstruction route.",
                    "checks": ["derivation", "dimensions", "boundary-cases", "figure-trend"],
                    "status": "derived",
                    "finding": "The transform is dimensionally consistent and preserves the visible ordering.",
                    "implementationDecision": "use-derived",
                    "routeBindings": [{"routeId": "route-local", "interpretation": "derived"}],
                    "evidenceRefs": ["src-target"],
                }
            ],
        }
        return report

    def test_target_scoped_formula_audit_is_validated_and_rendered(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = self.add_formula_audit(json.loads(report_input.read_text(encoding="utf-8")))
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

            completed = self.run_builder(root, report_input, target_manifest)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            built = json.loads((root / "report" / "report.json").read_text(encoding="utf-8"))
            audit = built["figures"][0]["generationLogic"]["formulaAudit"]
            self.assertEqual(audit["scope"], "target-chain-only")
            self.assertEqual(audit["items"][0]["implementationDecision"], "use-derived")
            self.assertEqual(
                audit["items"][0]["routeBindings"],
                [{"routeId": "route-local", "interpretation": "derived"}],
            )
            app = (root / "report" / "app.js").read_text(encoding="utf-8")
            self.assertIn("相关公式、参数与假设核验", app)
            self.assertIn("绑定路线", app)
            self.assertIn("privateKeyMarker", app)
            self.assertIn("secretAssignment", app)

    def test_report_rejects_credential_shaped_prose_before_persistence(self) -> None:
        credential_samples = (
            "Authorization: Bearer abcdefghijklmnop",
            "api_key=sk-example-credential",
            "OPENAI_API_KEY=sk-example-provider-credential",
            "AWS_SECRET_ACCESS_KEY=example-aws-credential",
            "-----BEGIN PRIVATE KEY-----\nnot-a-real-key",
        )
        for index, sample in enumerate(credential_samples):
            with self.subTest(sample=sample), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                target_manifest, _ = create_target_workspace(root / "targets")
                report_input = create_report_input(root / "report-input.json")
                report = json.loads(report_input.read_text(encoding="utf-8"))
                report["sources"][0]["note"] = f"Checked source. {sample}"
                report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

                completed = self.run_builder(root, report_input, target_manifest, output_name=f"report-{index}")
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("possible credential material", completed.stderr)
                self.assertNotIn("sk-example-credential", completed.stderr)
                self.assertFalse((root / f"report-{index}" / "report.json").exists())

    def test_parameter_default_rejects_secret_but_benign_scientific_prose_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            route = report["figures"][0]["routes"][0]
            route["parameters"] = [{
                "parameterId": "token_count_note",
                "label": "Method note",
                "type": "string",
                "required": False,
                "default": "The token count is a scientific observable; authorization is discussed conceptually.",
                "origin": "paper",
            }]
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            benign = self.run_builder(root, report_input, target_manifest, output_name="benign-report")
            self.assertEqual(benign.returncode, 0, benign.stderr)
            built = json.loads((root / "benign-report" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(
                built["figures"][0]["routes"][0]["parameters"][0]["parameterId"],
                "token_count_note",
            )
            self.assertIn(
                "authorization is discussed conceptually",
                built["figures"][0]["routes"][0]["parameters"][0]["default"],
            )

            route["parameters"][0]["default"] = "password=hunter-example"
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            secret = self.run_builder(root, report_input, target_manifest, output_name="secret-report")
            self.assertNotEqual(secret.returncode, 0)
            self.assertIn("possible credential material", secret.stderr)

    def test_nonblocked_deliverables_require_workspace_file_effect(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            report["figures"][0]["routes"][0]["effects"].remove("create-workspace-files")
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("deliverables must declare create-workspace-files", completed.stderr)

    def test_formula_divergence_cannot_be_silently_used_as_stated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = self.add_formula_audit(json.loads(report_input.read_text(encoding="utf-8")))
            item = report["figures"][0]["generationLogic"]["formulaAudit"]["items"][0]
            item["status"] = "paper-code-divergence"
            item["implementationDecision"] = "use-as-stated"
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("paper-code-divergence cannot use implementation decision use-as-stated", completed.stderr)

    def test_ambiguous_formula_cannot_be_silently_used_as_stated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = self.add_formula_audit(json.loads(report_input.read_text(encoding="utf-8")))
            item = report["figures"][0]["generationLogic"]["formulaAudit"]["items"][0]
            item["status"] = "ambiguous"
            item["implementationDecision"] = "use-as-stated"
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("ambiguous cannot use implementation decision use-as-stated", completed.stderr)

    def test_formula_divergence_split_decision_requires_distinct_routes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = self.add_formula_audit(json.loads(report_input.read_text(encoding="utf-8")))
            item = report["figures"][0]["generationLogic"]["formulaAudit"]["items"][0]
            item["status"] = "paper-code-divergence"
            item["implementationDecision"] = "split-routes"
            item["routeBindings"] = [
                {"routeId": "route-local", "interpretation": "paper-formula"},
                {"routeId": "route-local", "interpretation": "code-implementation"},
            ]
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("routeBindings must not repeat a routeId", completed.stderr)

    def test_formula_split_requires_two_interpretation_roles(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = self.add_formula_audit(json.loads(report_input.read_text(encoding="utf-8")))
            item = report["figures"][0]["generationLogic"]["formulaAudit"]["items"][0]
            item.update(
                {
                    "status": "ambiguous",
                    "implementationDecision": "split-routes",
                    "routeBindings": [
                        {"routeId": "route-local", "interpretation": "alternative-derived"},
                        {"routeId": "route-other", "interpretation": "alternative-derived"},
                    ],
                }
            )
            other = json.loads(json.dumps(report["figures"][0]["routes"][0]))
            other["routeId"] = "route-other"
            other["label"] = "Alternative route"
            other["recommended"] = False
            other["scientificScope"]["assumptions"] = ["Alternative target-scoped interpretation."]
            report["figures"][0]["routes"].append(other)
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("requires distinct route interpretations", completed.stderr)

    def test_formula_split_rejects_unknown_or_cloned_routes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = self.add_formula_audit(json.loads(report_input.read_text(encoding="utf-8")))
            item = report["figures"][0]["generationLogic"]["formulaAudit"]["items"][0]
            item.update(
                {
                    "status": "paper-code-divergence",
                    "implementationDecision": "split-routes",
                    "routeBindings": [
                        {"routeId": "route-local", "interpretation": "paper-formula"},
                        {"routeId": "route-unrelated", "interpretation": "code-implementation"},
                    ],
                }
            )
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            unknown = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(unknown.returncode, 0)
            self.assertIn("must resolve to routes in the same figure", unknown.stderr)

            clone = json.loads(json.dumps(report["figures"][0]["routes"][0]))
            clone["routeId"] = "route-unrelated"
            clone["label"] = "Renamed duplicate route"
            clone["recommended"] = False
            report["figures"][0]["routes"].append(clone)
            item["routeBindings"][1]["interpretation"] = "alternative-derived"
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            wrong_roles = self.run_builder(root, report_input, target_manifest, output_name="wrong-roles-report")
            self.assertNotEqual(wrong_roles.returncode, 0)
            self.assertIn("requires paper-formula and code-implementation bindings", wrong_roles.stderr)

            item["routeBindings"][1]["interpretation"] = "code-implementation"
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            cloned = self.run_builder(root, report_input, target_manifest, output_name="cloned-report")
            self.assertNotEqual(cloned.returncode, 0)
            self.assertIn("scientifically distinct route definitions", cloned.stderr)

    def test_paper_code_split_accepts_structured_distinct_interpretations(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = self.add_formula_audit(json.loads(report_input.read_text(encoding="utf-8")))
            item = report["figures"][0]["generationLogic"]["formulaAudit"]["items"][0]
            item.update(
                {
                    "status": "paper-code-divergence",
                    "implementationDecision": "split-routes",
                    "routeBindings": [
                        {"routeId": "route-local", "interpretation": "paper-formula"},
                        {"routeId": "route-code", "interpretation": "code-implementation"},
                    ],
                }
            )
            code_route = json.loads(json.dumps(report["figures"][0]["routes"][0]))
            code_route["routeId"] = "route-code"
            code_route["label"] = "Code implementation route"
            code_route["recommended"] = False
            code_route["scientificScope"]["assumptions"] = ["Use the implementation ordering found in code."]
            code_route["plan"] = ["Execute the code-ordering interpretation and validate its visible result."]
            report["figures"][0]["routes"].append(code_route)
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

            completed = self.run_builder(root, report_input, target_manifest)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            built = json.loads((root / "report" / "report.json").read_text(encoding="utf-8"))
            bindings = built["figures"][0]["generationLogic"]["formulaAudit"]["items"][0]["routeBindings"]
            self.assertEqual({binding["interpretation"] for binding in bindings}, {"paper-formula", "code-implementation"})

    def test_formula_block_binding_matches_blocked_route_scope(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = self.add_formula_audit(json.loads(report_input.read_text(encoding="utf-8")))
            item = report["figures"][0]["generationLogic"]["formulaAudit"]["items"][0]
            item.update(
                {
                    "status": "not-checkable",
                    "implementationDecision": "block",
                    "routeBindings": [{"routeId": "route-local", "interpretation": "derived"}],
                }
            )
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            bound_ready = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(bound_ready.returncode, 0)
            self.assertIn("block may bind only blocked routes", bound_ready.stderr)

            item["routeBindings"] = []
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            unbound_ready = self.run_builder(root, report_input, target_manifest, output_name="unbound-ready")
            self.assertNotEqual(unbound_ready.returncode, 0)
            self.assertIn("unbound block requires every figure route to be blocked", unbound_ready.stderr)

            figure = report["figures"][0]
            route = figure["routes"][0]
            route.update(
                {
                    "status": "blocked",
                    "recommended": False,
                    "deliverables": [],
                    "plan": [],
                    "blockers": ["The target-chain expression cannot currently be checked."],
                }
            )
            figure["reproduction"]["recommendedRouteId"] = None
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            blocked = self.run_builder(root, report_input, target_manifest, output_name="blocked")
            self.assertEqual(blocked.returncode, 0, blocked.stderr)

    def test_ready_route_accepts_only_a_resolved_derivation_or_assumption(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            requirement = report["figures"][0]["requirements"][0]
            requirement.update({
                "state": "derivable",
                "resolution": {"status": "frozen", "basis": "Deterministic test derivation."},
            })
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable, str(BUILDER), "--input", str(report_input),
                    "--output", str(root / "report"), "--target-manifest", str(target_manifest),
                    "--audience", "local",
                ],
                cwd=REPO, text=True, capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            report["figures"][0]["requirements"][0].pop("resolution")
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable, str(BUILDER), "--input", str(report_input),
                    "--output", str(root / "invalid-report"), "--target-manifest", str(target_manifest),
                    "--audience", "local",
                ],
                cwd=REPO, text=True, capture_output=True,
            )
            self.assertNotEqual(completed.returncode, 0)

    def test_conditional_route_also_rejects_an_unresolved_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            report["figures"][0]["routes"][0]["status"] = "conditional"
            report["figures"][0]["requirements"][0].update({"state": "assumable"})
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("unresolved requirement", completed.stderr)

    def test_null_recommendation_is_rejected_while_a_non_blocked_route_exists(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            report["figures"][0]["reproduction"]["recommendedRouteId"] = None
            report["figures"][0]["routes"][0]["recommended"] = False
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("recommended route is required while a non-blocked candidate exists", completed.stderr)

    def test_resolution_state_must_match_requirement_state(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            report["figures"][0]["requirements"][0].update({
                "state": "assumable",
                "resolution": {"status": "frozen", "basis": "Wrong resolution kind."},
            })
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("accepted resolution", completed.stderr)

    def test_verified_environment_requires_declared_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            report["environment"] = [{
                "environmentId": "env-test",
                "label": "Test runtime",
                "status": "verified",
                "provisioning": "existing-only",
                "version": "1",
                "detail": "Claimed without any probe evidence.",
                "evidenceRefs": [],
            }]
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("verified status requires evidenceRefs", completed.stderr)

            report["environment"][0]["evidenceRefs"] = ["src-target"]
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest, "wrong-kind-env-report")
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("hashed environment-audit artifact", completed.stderr)

    def test_verified_environment_accepts_a_hashed_environment_audit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            audit = root / "environment-audit.json"
            audit.write_text('{"probe":"passed"}\n', encoding="utf-8")
            digest = build_report.sha256_file(audit)
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            report["sources"].append({
                "sourceId": "src-env-audit",
                "kind": "environment-audit",
                "title": "Route-specific runtime probe",
                "access": {"state": "local", "checkedAt": "2026-08-12T00:00:00Z"},
                "license": {"state": "unknown"},
                "artifact": {
                    "sourcePath": str(audit),
                    "fileName": audit.name,
                    "mediaType": "application/json",
                    "sizeBytes": audit.stat().st_size,
                    "sha256": digest,
                },
            })
            report["environment"] = [{
                "environmentId": "env-test",
                "label": "Test runtime",
                "status": "verified",
                "provisioning": "existing-only",
                "version": "1",
                "detail": "Route-specific probe passed.",
                "evidenceRefs": ["src-env-audit"],
            }]
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_verified_requirement_requires_declared_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            report["figures"][0]["requirements"][0].update({"state": "verified", "evidenceRefs": []})
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("verified requirement needs evidenceRefs", completed.stderr)

    def test_source_artifact_is_read_and_hash_checked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            artifact = root / "code.zip"
            artifact.write_bytes(b"verified artifact bytes")
            digest = build_report.sha256_file(artifact)
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            report["sources"][0]["artifact"] = {
                "sourcePath": str(artifact),
                "fileName": artifact.name,
                "mediaType": "application/zip",
                "sizeBytes": artifact.stat().st_size,
                "sha256": digest,
            }
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest, "valid-artifact-report")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            built = json.loads((root / "valid-artifact-report" / "report.json").read_text(encoding="utf-8"))
            self.assertNotIn("sourcePath", built["sources"][0]["artifact"])

            report["sources"][0]["artifact"]["sha256"] = "0" * 64
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest, "bad-artifact-report")
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("artifact hash mismatch", completed.stderr)

            report["sources"][0]["artifact"].update({
                "sourcePath": str(root / "missing.zip"),
                "sha256": digest,
            })
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest, "missing-artifact-report")
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("artifact sourcePath does not exist", completed.stderr)

            report["sources"][0]["artifact"].pop("sourcePath")
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest, "unbound-artifact-report")
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("artifact sourcePath must be a non-empty string", completed.stderr)

    def test_executable_route_requires_finite_estimates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            report_input = create_report_input(root / "report-input.json")
            report = json.loads(report_input.read_text(encoding="utf-8"))
            route = report["figures"][0]["routes"][0]
            route["effects"].append("network")
            route["estimated"]["downloadBytes"] = None
            report["approvalPolicy"]["consentRequiredEffects"].append("network")
            report_input.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            completed = self.run_builder(root, report_input, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("finite resource estimates", completed.stderr)

    def test_v3_fixture_builds_portable_local_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            targets = root / "targets"
            target_manifest, target_hash = create_target_workspace(targets)
            report_input = create_report_input(root / "report-input.json")
            output = root / "report"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--input",
                    str(report_input),
                    "--output",
                    str(output),
                    "--target-manifest",
                    str(target_manifest),
                    "--audience",
                    "local",
                ],
                cwd=REPO,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "assets" / "figure-01.png").is_file())
            built = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(built["schemaVersion"], "reprofig.report/v3")
            self.assertEqual(built["figures"][0]["target"]["targetSha256"], target_hash)
            self.assertEqual(built["figures"][0]["image"]["bundleState"], "embedded-local")
            self.assertNotIn("sourcePath", built["figures"][0]["image"])
            self.assertNotIn(str(root), (output / "report-data.js").read_text(encoding="utf-8"))

    def test_failed_build_leaves_no_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, _ = create_target_workspace(root / "targets")
            invalid = root / "invalid.json"
            invalid.write_text('{"schemaVersion":"wrong"}\n', encoding="utf-8")
            output = root / "should-not-exist"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--input",
                    str(invalid),
                    "--output",
                    str(output),
                    "--target-manifest",
                    str(target_manifest),
                    "--audience",
                    "local",
                ],
                cwd=REPO,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".should-not-exist.staging-*")), [])

    def test_verified_subset_manifest_is_create_only_and_reuses_target_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "targets"
            source, _ = create_target_workspace(root, "target-01")
            before = source.read_bytes()
            destination = root / "manifest.verified.json"
            with contextlib.redirect_stdout(io.StringIO()):
                count = materializer.derive_verified_subset(
                    source,
                    destination,
                    "verified-subset",
                    None,
                )
            self.assertEqual(count, 1)
            self.assertEqual(source.read_bytes(), before)
            derived = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(derived["targetCount"], 1)
            self.assertEqual(derived["targets"][0]["normalizedPath"], "normalized/target-01.png")
            with self.assertRaises(materializer.TargetError):
                with contextlib.redirect_stdout(io.StringIO()):
                    materializer.derive_verified_subset(source, destination, "another-subset", None)

    def test_verified_subset_cli_exits_success_after_writing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "targets"
            source, _ = create_target_workspace(root, "target-01")
            destination = root / "manifest.verified.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MATERIALIZER),
                    "--derive-subset-manifest",
                    str(source),
                    "--subset-output",
                    str(destination),
                    "--subset-target-set-id",
                    "verified-subset",
                ],
                cwd=REPO,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(destination.is_file())
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "verified-subset-created")
            self.assertEqual(payload["targets"], ["target-01"])

    @unittest.skipUnless(build_report.Image is not None, "Pillow is required for report proxy generation")
    def test_large_valid_target_uses_a_report_proxy_without_changing_target_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "target.png"
            proxy = root / "proxy.png"
            build_report.Image.new("RGB", (5000, 2), "white").save(source, format="PNG")
            source_hash = build_report.sha256_file(source)
            with mock.patch.object(build_report, "MAX_ASSET_BYTES", 256):
                _width, _height, display_proxy = build_report.build_report_png(source, proxy)
            self.assertTrue(display_proxy)
            self.assertEqual(source_hash, build_report.sha256_file(source))
            self.assertLessEqual(build_report.png_dimensions(proxy)[0], build_report.MAX_REPORT_IMAGE_EDGE)


if __name__ == "__main__":
    unittest.main()
