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
) -> Path | dict[str, Path]:
    workspace = parent / "workspace"
    target_manifest, target_sha = create_target_workspace(workspace / "phase-zero", target_id)
    report_input = create_report_input(workspace / "report-input.json", target_id)
    report_bundle = workspace / "report-bundle"
    built = subprocess.run(
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
            "local",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    if built.returncode != 0:
        raise AssertionError(built.stderr)
    report_path = report_bundle / "report.json"
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
        "report": report_path,
        "report_bundle": report_bundle,
        "approval": approval_path,
        "gate": gate_path,
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
        check=check,
    )
    if not check:
        return completed
    return Path(json.loads(completed.stdout)["path"])


def complete_target(staging: Path, target_id: str, *, image_derived: bool = False) -> None:
    output_path = staging / "targets" / target_id / "outputs" / "reproduced-figure.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("deterministic generated test output\n", encoding="utf-8")
    result_path = staging / "targets" / target_id / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.update(
        {
            "operationalStatus": "complete",
            "claimStatus": "not-applicable" if image_derived else "supported",
            "summary": "The bounded test run completed.",
            "outputs": [f"targets/{target_id}/outputs/reproduced-figure.txt"],
        }
    )
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary_path = staging / "targets" / target_id / "validation" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        {
            "status": "passed",
            "summary": "The declared test criterion passed.",
            "artifacts": [f"targets/{target_id}/outputs/reproduced-figure.txt"],
        }
    )
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    environment_path = staging / "shared" / "environment" / "environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    environment["captureStatus"] = "recorded"
    environment["runtime"] = {"name": "python", "version": sys.version.split()[0]}
    environment_path.write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")

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


def report_source_for(staging: Path) -> Path:
    for parent in staging.parents:
        candidate = parent / "report-bundle"
        if candidate.is_dir():
            return candidate
    raise AssertionError(f"could not locate report source for {staging}")


class RunBundleTests(unittest.TestCase):
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
            self.assertEqual(result_report["schemaVersion"], "scirepro.result-report/v1")
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

    def test_manifest_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            final = self._final_bundle(Path(raw), "tamper")
            readme = final / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
            completed = run_bundle("validate", "--bundle", str(final), check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("inventory", completed.stderr)

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
