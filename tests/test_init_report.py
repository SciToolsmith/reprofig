from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:  # Support both unittest discovery and dotted-module invocation.
    from .fixture_factory import create_target_workspace, write_json
except ImportError:  # pragma: no cover - exercised by discovery mode
    from fixture_factory import create_target_workspace, write_json


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scirepro" / "scripts" / "init_report.py"
BUILD_SCRIPT = ROOT / "scirepro" / "scripts" / "build_report.py"


def run_scaffold(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(value) for value in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def canonical_manifest(manifest: dict) -> bytes:
    clone = json.loads(json.dumps(manifest))
    clone["integrity"]["manifestSha256"] = ""
    return json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def make_ready_image_compact(compact: dict) -> None:
    compact.update(
        {
            "objective": "Reconstruct the bounded visible geometry.",
            "oneLine": "The verified image supports an image-derived reconstruction.",
        }
    )
    for figure in compact["figures"]:
        observation = figure["understanding"]["observations"][0]
        observation.update(
            {
                "location": "entire target",
                "statement": "The target contains visible coloured pixels.",
                "confidence": "high",
            }
        )
        figure["understanding"].update(
            {
                "visualSummary": "A small raster target with visible colour regions.",
                "evidenceRole": "Visible-geometry reconstruction only.",
                "limitations": ["No paper or original generation process is available."],
            }
        )
        generation_input = figure["generation"]["inputs"][0]
        generation_input.update(
            {
                "label": "Visible target raster",
                "description": "The verified Phase 0 target pixels.",
                "origin": "user",
            }
        )
        generation_step = figure["generation"]["steps"][0]
        generation_step.update(
            {
                "label": "Reconstruct visible geometry",
                "description": "Read the bounded visible geometry and render it locally.",
                "origin": "derived",
            }
        )
        figure["generation"]["plotMapping"].update(
            {
                "description": "Target pixels map directly to output pixels.",
                "encodings": ["pixel colour and position"],
            }
        )
        figure["generation"]["unknowns"] = ["The original generator is unknown."]
        validation = figure["validation"][0]
        validation.update(
            {
                "label": "Visible geometry",
                "kind": "visual-fidelity",
                "origin": "derived",
                "observable": "Output dimensions and visible colour regions.",
                "criterion": "The output preserves the bounded visible arrangement.",
                "supportsClaim": "Visible fidelity only; no scientific claim is tested.",
            }
        )
        figure["assessment"].update(
            {
                "verdict": "A bounded visual reconstruction is available.",
                "confidence": "high",
                "rationale": "The verified target is sufficient for visible reconstruction only.",
            }
        )
        route = figure["route"]
        route.update(
            {
                "label": "Local image-derived reconstruction",
                "status": "ready",
                "goal": "Reconstruct visible geometry only.",
                "claimCoverage": "No paper claim is tested.",
                "doesNotReproduce": ["Original data, method, or scientific result"],
                "rationale": "The verified target is sufficient for the bounded route.",
                "engine": "Local Python",
                "deliverables": [
                    {"kind": "figure", "extension": ".png", "label": "Generated figure"}
                ],
                "plan": ["Read the verified target and create a bounded output."],
                "blockers": [],
            }
        )
        route["estimated"].update(
            {"downloadBytes": 0, "diskBytes": 4096, "runtimeMinutes": 0.1, "costUsd": 0}
        )
        for category, condition in route["conditions"].items():
            condition.update(
                {
                    "state": "not-required",
                    "blocking": False,
                    "detail": f"{category.title()} needs no extra condition for this bounded route.",
                }
            )


def make_blocked_image_compact(compact: dict) -> None:
    make_ready_image_compact(compact)
    for figure in compact["figures"]:
        figure["assessment"].update(
            {
                "verdict": "The image-derived route is locally blocked.",
                "confidence": "high",
                "rationale": "The visible target is understood, but the required local capability is unavailable.",
            }
        )
        route = figure["route"]
        route.update(
            {
                "status": "blocked",
                "rationale": "No candidate can run until the missing local capability is supplied.",
                "deliverables": [],
                "plan": [],
                "blockers": ["The required local image-processing capability is unavailable."],
            }
        )
        route["conditions"]["environment"].update(
            {
                "state": "missing",
                "blocking": True,
                "detail": "The required local image-processing capability is unavailable.",
            }
        )


class InitReportTests(unittest.TestCase):
    def test_init_is_compact_and_uses_shared_root_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _ = create_target_workspace(root / "targets")
            output = root / "compact.json"
            result = run_scaffold("init", "--target-manifest", manifest, "--output", output, "--mode", "compact")
            self.assertEqual(result.returncode, 0, result.stderr)
            compact = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(compact["schemaVersion"], "scirepro.compact-report/v1")
            self.assertEqual(compact["sources"], [])
            self.assertEqual(compact["environment"], [])
            self.assertEqual(len(compact["figures"]), 1)
            figure = compact["figures"][0]
            self.assertEqual(set(figure["route"]["conditions"]), {"input", "method", "protocol", "validation", "environment"})
            self.assertNotIn("figureId", figure)
            self.assertNotIn("target", figure)
            self.assertNotIn("requirementId", json.dumps(figure))

    def test_expand_generates_stable_ids_and_full_v3_at_lower_authoring_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _ = create_target_workspace(root / "targets")
            compact_path = root / "compact.json"
            expanded_path = root / "scirepro-report.json"
            self.assertEqual(run_scaffold("init", "--target-manifest", manifest, "--output", compact_path).returncode, 0)
            compact = json.loads(compact_path.read_text(encoding="utf-8"))
            make_ready_image_compact(compact)
            write_json(compact_path, compact)
            result = run_scaffold(
                "expand", "--input", compact_path, "--target-manifest", manifest, "--output", expanded_path
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expanded = json.loads(expanded_path.read_text(encoding="utf-8"))
            self.assertEqual(expanded["schemaVersion"], "reprofig.report/v3")
            figure = expanded["figures"][0]
            self.assertTrue(figure["figureId"].startswith("fig-"))
            self.assertEqual(len(figure["requirements"]), 5)
            self.assertEqual(len(figure["routes"]), 1)
            self.assertEqual(figure["routes"][0]["scientificScope"]["reproducesObservationIds"], [figure["understanding"]["observations"][0]["observationId"]])
            self.assertLess(compact_path.stat().st_size, expanded_path.stat().st_size * 0.75)

    def test_blocked_image_compact_expands_and_builds_without_changing_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _ = create_target_workspace(root / "targets")
            compact_path = root / "compact-blocked.json"
            expanded_path = root / "blocked-report.json"
            web_output = root / "blocked-report-web"
            self.assertEqual(run_scaffold("init", "--target-manifest", manifest, "--output", compact_path).returncode, 0)
            compact = json.loads(compact_path.read_text(encoding="utf-8"))
            make_blocked_image_compact(compact)
            write_json(compact_path, compact)

            expanded_result = run_scaffold(
                "expand", "--input", compact_path, "--target-manifest", manifest, "--output", expanded_path
            )
            self.assertEqual(expanded_result.returncode, 0, expanded_result.stderr)
            expanded = json.loads(expanded_path.read_text(encoding="utf-8"))
            figure = expanded["figures"][0]
            self.assertEqual(figure["target"]["workflowMode"], "image-derived-reconstruction")
            self.assertEqual(figure["reproduction"]["level"], "image-derived-reconstruction")
            self.assertIsNone(figure["reproduction"]["recommendedRouteId"])
            self.assertEqual(figure["routes"][0]["status"], "blocked")
            self.assertFalse(figure["routes"][0]["recommended"])

            built = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--input",
                    str(expanded_path),
                    "--output",
                    str(web_output),
                    "--target-manifest",
                    str(manifest),
                    "--audience",
                    "local",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            rendered = json.loads((web_output / "report.json").read_text(encoding="utf-8"))
            self.assertIsNone(rendered["figures"][0]["reproduction"]["recommendedRouteId"])

    def test_create_only_applies_to_compact_and_expanded_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _ = create_target_workspace(root / "targets")
            compact_path = root / "compact.json"
            first = run_scaffold("init", "--target-manifest", manifest, "--output", compact_path)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = compact_path.read_bytes()
            second = run_scaffold("init", "--target-manifest", manifest, "--output", compact_path)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(compact_path.read_bytes(), before)
            self.assertFalse(list(root.glob(".compact.json.tmp-*")))

            compact = json.loads(compact_path.read_text(encoding="utf-8"))
            make_ready_image_compact(compact)
            write_json(compact_path, compact)
            expanded = root / "expanded.json"
            first_expand = run_scaffold("expand", "--input", compact_path, "--target-manifest", manifest, "--output", expanded)
            self.assertEqual(first_expand.returncode, 0, first_expand.stderr)
            expanded_before = expanded.read_bytes()
            second_expand = run_scaffold("expand", "--input", compact_path, "--target-manifest", manifest, "--output", expanded)
            self.assertEqual(second_expand.returncode, 2)
            self.assertEqual(expanded.read_bytes(), expanded_before)

    def test_validate_ready_rejects_todos_then_accepts_completed_compact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _ = create_target_workspace(root / "targets")
            compact_path = root / "compact.json"
            self.assertEqual(run_scaffold("init", "--target-manifest", manifest, "--output", compact_path).returncode, 0)
            unresolved = run_scaffold("validate-ready", "--input", compact_path, "--target-manifest", manifest)
            self.assertEqual(unresolved.returncode, 2)
            self.assertIn("unresolved TODO fields", unresolved.stderr)
            compact = json.loads(compact_path.read_text(encoding="utf-8"))
            make_ready_image_compact(compact)
            write_json(compact_path, compact)
            ready = run_scaffold("validate-ready", "--input", compact_path, "--target-manifest", manifest)
            self.assertEqual(ready.returncode, 0, ready.stderr)
            self.assertEqual(json.loads(ready.stdout)["status"], "ready")

    def test_unfinished_compact_cannot_enter_report_builder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _ = create_target_workspace(root / "targets")
            compact_path = root / "compact.json"
            output = root / "report-web"
            self.assertEqual(run_scaffold("init", "--target-manifest", manifest, "--output", compact_path).returncode, 0)
            built = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--input", str(compact_path), "--output", str(output), "--target-manifest", str(manifest), "--audience", "local"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(built.returncode, 2)
            self.assertIn("must use reprofig.report/v3", built.stderr)
            self.assertFalse(output.exists())

    def test_paper_manifest_keeps_only_minimal_authored_paper_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target_root = root / "targets"
            manifest_path, _ = create_target_workspace(target_root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            paper_path = target_root / "originals" / "paper.pdf"
            paper_path.write_bytes(b"%PDF-1.4\n% compact offline fixture\n")
            paper_sha = hashlib.sha256(paper_path.read_bytes()).hexdigest()
            manifest["paper"] = {"fileName": "paper.pdf", "originalPath": "originals/paper.pdf", "sha256": paper_sha, "pageCount": 1}
            manifest["targets"][0].update(
                {
                    "acquisitionMode": "paper-with-images",
                    "workflowMode": "scientific-reproduction",
                    "identityStatus": "resolved",
                    "requestedAs": "Fig. 1",
                    "figureReference": "Fig. 1",
                    "paperPage": 1,
                    "caption": "Fig. 1. Compact scaffold fixture.",
                    "captionIncluded": True,
                }
            )
            manifest["integrity"]["manifestSha256"] = hashlib.sha256(canonical_manifest(manifest)).hexdigest()
            write_json(manifest_path, manifest)
            output = root / "compact-paper.json"
            result = run_scaffold("init", "--target-manifest", manifest_path, "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            compact = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(set(compact["paper"]), {"title", "doi", "citation"})
            self.assertEqual(compact["sources"], [])
            self.assertNotIn("paperId", json.dumps(compact))
            self.assertNotIn("sourceSha256", json.dumps(compact))


if __name__ == "__main__":
    unittest.main()
