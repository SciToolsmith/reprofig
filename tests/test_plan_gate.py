from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.fixture_factory import create_report_input, create_target_workspace, write_json


REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "scirepro" / "scripts" / "build_report.py"
GATE = REPO / "scirepro" / "scripts" / "plan_gate.py"


def canonical_report_hash(report: dict) -> str:
    clone = json.loads(json.dumps(report))
    clone.setdefault("integrity", {})["reportSha256"] = ""
    payload = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class PlanGateTests(unittest.TestCase):
    def make_built_report(self, root: Path) -> tuple[Path, Path, dict]:
        target_manifest, _ = create_target_workspace(root / "targets")
        report_input = create_report_input(root / "report-input.json")
        report_dir = root / "report"
        completed = subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--input",
                str(report_input),
                "--output",
                str(report_dir),
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
        report_path = report_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return target_manifest, report_path, report

    def write_approval(self, path: Path, report: dict) -> dict:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        figure = report["figures"][0]
        route = figure["routes"][0]
        approval = {
            "schemaVersion": "reprofig.approval/v1",
            "approvalId": "apr-test-0001",
            "reportId": report["reportId"],
            "reportSha256": report["integrity"]["reportSha256"],
            "decision": "approve",
            "createdAt": now.isoformat().replace("+00:00", "Z"),
            "expiresAt": (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
            "selectedFigures": [{
                "figureId": figure["figureId"],
                "sourceImageSha256": figure["target"]["targetSha256"],
                "routeId": route["routeId"],
                "parameters": {},
                "deliverables": [route["deliverables"][0]["kind"]],
            }],
            "outputPolicy": {
                "relativeRoot": "runs/run-001",
                "mode": "create-only",
                "overwrite": "never",
                "explicitFiles": [],
            },
            "authorizedEffects": list(route["effects"]),
            "acknowledgements": [],
            "idempotencyKey": "idem-test-0001",
        }
        write_json(path, approval)
        return approval

    def run_gate(self, report_path: Path, approval_path: Path, target_manifest: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(GATE),
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

    def test_success_result_binds_approval_output_and_selected_targets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, report_path, report = self.make_built_report(root)
            approval_path = root / "approval.json"
            approval = self.write_approval(approval_path, report)
            completed = self.run_gate(report_path, approval_path, target_manifest)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["schemaVersion"], "scirepro.gate-result/v1")
            self.assertEqual(result["approvalSha256"], hashlib.sha256(approval_path.read_bytes()).hexdigest())
            self.assertEqual(result["outputPolicy"], approval["outputPolicy"])
            self.assertEqual(result["selectedTargets"], [{
                "figureId": "figure-01",
                "targetId": "target-01",
                "targetSha256": report["figures"][0]["target"]["targetSha256"],
                "workflowMode": "image-derived-reconstruction",
                "routeId": "route-local",
                "deliverables": ["figure"],
            }])

    def test_conditional_route_with_unresolved_requirement_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, report_path, report = self.make_built_report(root)
            report["figures"][0]["routes"][0]["status"] = "conditional"
            report["figures"][0]["requirements"][0].update({
                "state": "assumable",
                "resolution": None,
            })
            report["integrity"]["reportSha256"] = canonical_report_hash(report)
            write_json(report_path, report)
            approval_path = root / "approval.json"
            self.write_approval(approval_path, report)
            completed = self.run_gate(report_path, approval_path, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("unresolved requirement", completed.stderr)

    def test_selected_network_route_with_unknown_download_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target_manifest, report_path, report = self.make_built_report(root)
            route = report["figures"][0]["routes"][0]
            route["effects"].append("network")
            route["estimated"]["downloadBytes"] = None
            report["approvalPolicy"]["consentRequiredEffects"].append("network")
            report["integrity"]["reportSha256"] = canonical_report_hash(report)
            write_json(report_path, report)
            approval_path = root / "approval.json"
            approval = self.write_approval(approval_path, report)
            approval["acknowledgements"] = [{"effect": "network", "acceptedAt": approval["createdAt"]}]
            write_json(approval_path, approval)
            completed = self.run_gate(report_path, approval_path, target_manifest)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("finite resource estimates", completed.stderr)


if __name__ == "__main__":
    unittest.main()
