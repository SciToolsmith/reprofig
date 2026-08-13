from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.fixture_factory import create_target_workspace, tiny_png, write_json


REPO = Path(__file__).resolve().parents[1]
BUNDLER = REPO / "scirepro/scripts/finalize_run_bundle.py"


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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def init_from_manifest(root: Path, run_id: str = "direct") -> Path:
    workspace = root / "workspace"
    manifest, _ = create_target_workspace(workspace / "phase-zero", "figure-01")
    completed = run_bundle(
        "init",
        "--output-root", str(workspace),
        "--run-id", run_id,
        "--target-manifest", str(manifest),
        "--json",
    )
    return Path(json.loads(completed.stdout)["path"])


def init_targets(root: Path, run_id: str, specs: list[str], distribution: str = "local-private") -> Path:
    args = [
        "init", "--output-root", str(root), "--run-id", run_id,
        "--distribution", distribution, "--json",
    ]
    for spec in specs:
        args.extend(["--target", spec])
    return Path(json.loads(run_bundle(*args).stdout)["path"])


def artifact_record(role: str, path: str, root: Path, rights: str = "generated") -> dict:
    record = {
        "role": role,
        "includedPath": path,
        "sha256": digest(root / path),
        "rightsStatus": rights,
    }
    if role == "source":
        record["provenance"] = {
            "authority": "offline-test-author",
            "version": "fixture-v1",
            "license": "test-only",
            "rights": rights,
        }
    return record


def record_environment(staging: Path, target_id: str, engine_name: str) -> str:
    relative = f"targets/{target_id}/environment/environment.json"
    document = {
        "schemaVersion": "scirepro.environment/v2",
        "captureStatus": "recorded",
        "engines": [{"name": engine_name, "version": "test-1"}],
        "packages": [],
        "hardware": {"platform": "test"},
        "notes": ["Offline fixture."],
    }
    write_json(staging / relative, document)
    shared_path = staging / "shared/environment/environment.json"
    shared = json.loads(shared_path.read_text(encoding="utf-8"))
    shared.update({
        "captureStatus": "recorded",
        "engines": sorted(
            shared.get("engines", []) + [{"name": engine_name, "version": "test-1"}],
            key=lambda item: item["name"],
        ),
        "hardware": {"platform": "test"},
    })
    write_json(shared_path, shared)
    return relative


def record_resources(staging: Path, *, cap_enforcement: str = "declared-only", mechanism=None) -> None:
    write_json(staging / "shared/execution/resource-usage.json", {
        "schemaVersion": "scirepro.resource-usage/v2",
        "caps": [{
            "resource": "wall-time",
            "limit": 60,
            "unit": "seconds",
            "enforcement": cap_enforcement,
            "mechanism": mechanism,
        }],
        "measurements": [{
            "resource": "wall-time",
            "value": 0.01,
            "unit": "seconds",
            "method": "monotonic-clock",
        }],
        "notes": [],
    })


def prepare_complete_target(
    staging: Path,
    target_id: str,
    *,
    engine: str = "Python",
    native: bool = True,
    reference_exists: bool = True,
) -> None:
    prefix = f"targets/{target_id}"
    result_path = staging / prefix / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))

    reference = result["identity"].get("referencePath")
    if not reference_exists or reference is None:
        reference = f"{prefix}/reference/target.png"
        (staging / reference).parent.mkdir(parents=True, exist_ok=True)
        (staging / reference).write_bytes(tiny_png())
        result["identity"] = {
            "targetSha256": digest(staging / reference),
            "referencePath": reference,
            "rightsStatus": "generated",
        }

    source_path = f"{prefix}/sources/paper-source.txt"
    input_path = f"{prefix}/inputs/samples.csv"
    code_path = f"{prefix}/code/reproduce.py"
    config_path = f"{prefix}/config/run.json"
    baseline = f"{prefix}/outputs/baseline-v0.svg"
    for relative, payload in (
        (source_path, f"author source record for {target_id}\n"),
        (input_path, "x,y\n0,0\n1,1\n"),
        (code_path, "print('offline fixture')\n"),
        (config_path, '{"seed": 7}\n'),
        (baseline, '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 1L1 0"/></svg>\n'),
    ):
        path = staging / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    environment_path = record_environment(staging, target_id, engine)
    record_resources(staging)

    result.update({
        "route": {
            "routeId": f"route-{target_id}",
            "kind": (
                "image-derived-reconstruction"
                if result["workflowMode"] == "image-derived-reconstruction"
                else "direct-recompute"
            ),
            "tests": "Whether the declared target trend is reproduced.",
            "doesNotSupport": [],
            "engine": {"name": engine, "version": "test-1", "native": native},
        },
        "execution": {
            "argv": [engine.lower(), code_path, "--config", config_path, "--input", input_path],
            "workingDirectory": ".",
            "frozenArtifacts": [
                artifact_record("source", source_path, staging),
                artifact_record("input", input_path, staging),
                artifact_record("code", code_path, staging),
                artifact_record("config", config_path, staging),
                artifact_record("environment", environment_path, staging),
            ],
        },
        "operationalStatus": "complete",
        "validationStatus": "passed",
        "claimStatus": (
            "not-applicable"
            if result["workflowMode"] == "image-derived-reconstruction"
            else "supported"
        ),
        "summary": "The declared acceptance criterion passed.",
        "baselineV0": baseline,
        "selectedOutput": baseline,
        "outputs": [baseline],
        "blocker": None,
        "acceptance": {
            "overallStatus": "passed",
            "criteria": [{
                "criterionId": "trend",
                "status": "passed",
                "statement": "The expected trend is present.",
                "evidencePaths": [baseline],
            }],
        },
        "calibration": None,
        "visualQA": None,
        "assumptions": [],
        "remainingDiscrepancies": [],
    })
    write_json(result_path, result)


def prepare_blocked_target(staging: Path, target_id: str, detail: str = "Original data are unavailable.") -> None:
    path = staging / f"targets/{target_id}/result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    if result["identity"].get("targetSha256") is None:
        reference = f"targets/{target_id}/reference/target.png"
        (staging / reference).parent.mkdir(parents=True, exist_ok=True)
        (staging / reference).write_bytes(tiny_png())
        result["identity"] = {
            "targetSha256": digest(staging / reference),
            "referencePath": reference,
            "rightsStatus": "generated",
        }
    result.update({
        "operationalStatus": "blocked",
        "validationStatus": "not-run",
        "summary": detail,
        "blocker": {"code": "missing-input", "detail": detail},
        "acceptance": {"overallStatus": "not-run", "criteria": []},
    })
    write_json(path, result)


class RunBundleTests(unittest.TestCase):
    def finalize(self, staging: Path, status: str) -> Path:
        completed = run_bundle(
            "finalize", "--bundle", str(staging), "--status", status, "--json"
        )
        return Path(json.loads(completed.stdout)["path"])

    def test_safe_local_run_starts_without_contract_gate_or_webpage(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "no-ceremony")
            self.assertFalse((staging / "shared/plan/execution-contract.json").exists())
            self.assertFalse((staging / "shared/plan/execution-gate-result.json").exists())
            prepare_complete_target(staging, "figure-01")
            final = self.finalize(staging, "complete")
            self.assertEqual(run_bundle("validate", "--bundle", str(final)).returncode, 0)
            self.assertFalse((final / "report").exists())
            self.assertFalse(any(path.suffix == ".html" for path in final.rglob("*")))
            manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schemaVersion"], "scirepro.run-bundle/v3")
            self.assertEqual(manifest["targets"][0]["validationStatus"], "passed")

    def test_per_target_routes_support_heterogeneous_engines(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_targets(
                Path(raw), "mixed-engines",
                [
                    "figure-native-a=scientific-reproduction",
                    "figure-native-b=scientific-reproduction",
                    "figure-portable=image-derived-reconstruction",
                ],
            )
            prepare_complete_target(
                staging, "figure-native-a", engine="MATLAB", native=True, reference_exists=False,
            )
            prepare_complete_target(
                staging, "figure-native-b", engine="R", native=True, reference_exists=False,
            )
            prepare_complete_target(
                staging, "figure-portable", engine="Python", native=False, reference_exists=False,
            )
            final = self.finalize(staging, "complete")
            manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [item["engine"]["name"] for item in manifest["targets"]],
                ["MATLAB", "R", "Python"],
            )

    def test_optional_calibration_and_visual_qa_are_not_required(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "v0-enough")
            prepare_complete_target(staging, "figure-01")
            final = self.finalize(staging, "complete")
            result = json.loads((final / "targets/figure-01/result.json").read_text(encoding="utf-8"))
            self.assertIsNone(result["calibration"])
            self.assertIsNone(result["visualQA"])

    def test_blocked_before_execution_needs_v0_or_terminal_blocker_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "blocked")
            prepare_blocked_target(staging, "figure-01")
            final = self.finalize(staging, "blocked")
            self.assertEqual(run_bundle("validate", "--bundle", str(final)).returncode, 0)
            result = json.loads((final / "targets/figure-01/result.json").read_text(encoding="utf-8"))
            self.assertIsNone(result["execution"])
            self.assertIsNotNone(result["blocker"])

    def test_partial_run_keeps_independent_target_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_targets(Path(raw), "partial", [
                "ready=image-derived-reconstruction", "missing=scientific-reproduction",
            ])
            prepare_complete_target(staging, "ready", reference_exists=False)
            prepare_blocked_target(staging, "missing")
            final = self.finalize(staging, "partial")
            manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([item["operationalStatus"] for item in manifest["targets"]], ["complete", "blocked"])

    def test_scientific_claim_status_requires_a_compatible_completed_test(self) -> None:
        cases = (
            ("supported", "complete", "not-run"),
            ("supported", "complete", "failed"),
            ("supported", "partial", "passed"),
            ("partially-supported", "complete", "passed"),
            ("unsupported", "failed", "failed"),
            ("unsupported", "complete", "not-run"),
            ("unsupported", "complete", "passed"),
            ("inconclusive", "complete", "failed"),
            ("not-tested", "complete", "inconclusive"),
            ("not-applicable", "complete", "passed"),
        )
        for claim, operational, validation in cases:
            with self.subTest(
                claim=claim,
                operational=operational,
                validation=validation,
            ), tempfile.TemporaryDirectory() as raw:
                staging = init_targets(
                    Path(raw),
                    f"claim-{claim}-{operational}-{validation}",
                    ["figure-01=scientific-reproduction"],
                )
                prepare_complete_target(staging, "figure-01", reference_exists=False)
                path = staging / "targets/figure-01/result.json"
                result = json.loads(path.read_text(encoding="utf-8"))
                result.update({
                    "operationalStatus": operational,
                    "validationStatus": validation,
                    "claimStatus": claim,
                })
                write_json(path, result)
                completed = run_bundle(
                    "finalize", "--bundle", str(staging), "--status", operational,
                    check=False,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("claimStatus", completed.stderr)

    def test_unexecuted_scientific_target_cannot_claim_a_tested_outcome(self) -> None:
        for claim in ("supported", "partially-supported", "unsupported", "inconclusive"):
            with self.subTest(claim=claim), tempfile.TemporaryDirectory() as raw:
                staging = init_targets(
                    Path(raw),
                    f"unexecuted-{claim}",
                    ["figure-01=scientific-reproduction"],
                )
                prepare_blocked_target(staging, "figure-01")
                path = staging / "targets/figure-01/result.json"
                result = json.loads(path.read_text(encoding="utf-8"))
                result["claimStatus"] = claim
                write_json(path, result)
                completed = run_bundle(
                    "finalize", "--bundle", str(staging), "--status", "blocked",
                    check=False,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("claimStatus", completed.stderr)

    def test_inconclusive_scientific_claim_requires_an_execution_trace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_targets(
                Path(raw),
                "unexecuted-inconclusive",
                ["figure-01=scientific-reproduction"],
            )
            prepare_blocked_target(staging, "figure-01")
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result.update({
                "operationalStatus": "failed",
                "validationStatus": "inconclusive",
                "claimStatus": "inconclusive",
                "acceptance": {
                    "overallStatus": "inconclusive",
                    "criteria": [{
                        "criterionId": "unresolved-test",
                        "status": "inconclusive",
                        "statement": "The scientific test did not run.",
                        "evidencePaths": [],
                    }],
                },
            })
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "failed",
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("requires an executed scientific test", completed.stderr)

    def test_image_derived_claim_status_remains_not_applicable(self) -> None:
        for claim in (
            "supported",
            "partially-supported",
            "unsupported",
            "inconclusive",
            "not-tested",
        ):
            with self.subTest(claim=claim), tempfile.TemporaryDirectory() as raw:
                staging = init_targets(
                    Path(raw),
                    f"image-claim-{claim}",
                    ["figure-01=image-derived-reconstruction"],
                )
                prepare_complete_target(staging, "figure-01", reference_exists=False)
                path = staging / "targets/figure-01/result.json"
                result = json.loads(path.read_text(encoding="utf-8"))
                result["claimStatus"] = claim
                write_json(path, result)
                completed = run_bundle(
                    "finalize", "--bundle", str(staging), "--status", "complete",
                    check=False,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(
                    "image-derived reconstruction cannot support a paper claim",
                    completed.stderr,
                )

    def test_scientific_claim_status_matrix_accepts_truthful_outcomes(self) -> None:
        cases = (
            ("supported", "complete", "passed", ["passed"]),
            ("partially-supported", "complete", "partially-passed", ["passed", "failed"]),
            ("partially-supported", "partial", "partially-passed", ["passed", "failed"]),
            ("unsupported", "complete", "failed", ["failed"]),
            ("inconclusive", "complete", "inconclusive", ["inconclusive"]),
            ("inconclusive", "partial", "inconclusive", ["inconclusive"]),
            ("inconclusive", "failed", "inconclusive", ["inconclusive"]),
            ("not-tested", "complete", "not-run", []),
        )
        for claim, operational, validation, criterion_statuses in cases:
            with self.subTest(
                claim=claim,
                operational=operational,
                validation=validation,
            ), tempfile.TemporaryDirectory() as raw:
                staging = init_targets(
                    Path(raw),
                    f"truthful-{claim}-{operational}",
                    ["figure-01=scientific-reproduction"],
                )
                prepare_complete_target(staging, "figure-01", reference_exists=False)
                path = staging / "targets/figure-01/result.json"
                result = json.loads(path.read_text(encoding="utf-8"))
                result.update({
                    "operationalStatus": operational,
                    "validationStatus": validation,
                    "claimStatus": claim,
                })
                result["acceptance"] = {
                    "overallStatus": validation,
                    "criteria": [
                        {
                            "criterionId": f"criterion-{index}",
                            "status": criterion_status,
                            "statement": "The declared scientific observable was tested.",
                            "evidencePaths": [result["baselineV0"]],
                        }
                        for index, criterion_status in enumerate(criterion_statuses, 1)
                    ],
                }
                write_json(path, result)
                final = self.finalize(staging, operational)
                self.assertEqual(
                    run_bundle("validate", "--bundle", str(final)).returncode,
                    0,
                )

    def test_actual_frozen_input_hash_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "frozen-input")
            prepare_complete_target(staging, "figure-01")
            (staging / "targets/figure-01/inputs/samples.csv").write_text("changed\n", encoding="utf-8")
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("frozen input artifact hash mismatch", completed.stderr)

    def test_archived_target_manifest_binding_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "target-manifest")
            prepare_complete_target(staging, "figure-01")
            path = staging / "shared/targets/manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["targets"][0]["notes"] = ["changed after initialization"]
            write_json(path, manifest)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("target-manifest canonical hash mismatch", completed.stderr)

    def test_every_scientific_trace_role_is_required_after_execution(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "missing-role")
            prepare_complete_target(staging, "figure-01")
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["execution"]["frozenArtifacts"] = [
                item for item in result["execution"]["frozenArtifacts"] if item["role"] != "config"
            ]
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("every absent optional role needs exactly one roleDisposition", completed.stderr)

    def test_roles_must_be_unique_and_aliases_must_be_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "duplicate-role")
            prepare_complete_target(staging, "figure-01")
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["execution"]["frozenArtifacts"].append(
                dict(result["execution"]["frozenArtifacts"][2])
            )
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("duplicate frozen artifact role", completed.stderr)

        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "explicit-alias")
            prepare_complete_target(staging, "figure-01")
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            source_record = next(
                item for item in result["execution"]["frozenArtifacts"] if item["role"] == "source"
            )
            input_record = next(
                item for item in result["execution"]["frozenArtifacts"] if item["role"] == "input"
            )
            input_record.update({
                "includedPath": source_record["includedPath"],
                "sha256": source_record["sha256"],
                "roleAlias": "source",
                "justification": "This route reads the published numeric table as both source evidence and direct input.",
            })
            write_json(path, result)
            final = self.finalize(staging, "complete")
            self.assertEqual(run_bundle("validate", "--bundle", str(final)).returncode, 0)

    def test_optional_roles_can_be_truthfully_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_targets(
                Path(raw), "minimal-evidence", ["figure-01=image-derived-reconstruction"]
            )
            prepare_complete_target(staging, "figure-01", reference_exists=False)
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["execution"]["frozenArtifacts"] = [
                item for item in result["execution"]["frozenArtifacts"]
                if item["role"] in {"source", "code", "environment"}
            ]
            result["execution"]["roleDispositions"] = {
                "input": {
                    "status": "not-applicable",
                    "reason": "The target pixels are read directly through the source binding.",
                    "binding": "route:route-figure-01",
                },
                "config": {
                    "status": "not-applicable",
                    "reason": "The executable has no external configuration for this deterministic route.",
                    "binding": "route:route-figure-01",
                },
            }
            write_json(path, result)
            final = self.finalize(staging, "complete")
            self.assertEqual(run_bundle("validate", "--bundle", str(final)).returncode, 0)

    def test_frozen_artifact_paths_are_role_and_target_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_targets(Path(raw), "cross-target", [
                "one=scientific-reproduction", "two=scientific-reproduction",
            ])
            prepare_complete_target(staging, "one", reference_exists=False)
            prepare_complete_target(staging, "two", reference_exists=False)
            path = staging / "targets/one/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            input_record = next(
                item for item in result["execution"]["frozenArtifacts"] if item["role"] == "input"
            )
            replacement = "targets/two/inputs/samples.csv"
            input_record.update({"includedPath": replacement, "sha256": digest(staging / replacement)})
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("outside its permitted bundle domain", completed.stderr)

        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "one-file-five-roles")
            prepare_complete_target(staging, "figure-01")
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            source_record = next(
                item for item in result["execution"]["frozenArtifacts"] if item["role"] == "source"
            )
            input_record = next(
                item for item in result["execution"]["frozenArtifacts"] if item["role"] == "input"
            )
            input_record.update({
                "includedPath": source_record["includedPath"],
                "sha256": source_record["sha256"],
            })
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("input artifact is outside its permitted bundle domain", completed.stderr)

        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "missing-artifact")
            prepare_complete_target(staging, "figure-01")
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            input_record = next(
                item for item in result["execution"]["frozenArtifacts"] if item["role"] == "input"
            )
            input_record["includedPath"] = "targets/figure-01/inputs/missing.csv"
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("missing figure-01 input artifact", completed.stderr)

    def test_argv_rejects_machine_paths_and_credentials(self) -> None:
        cases = {
            "posix": ["python", "/Users/alice/reproduce.py"],
            "linux": ["python", "--input=/home/alice/data.csv"],
            "windows": ["python", r"C:\\Users\\alice\\reproduce.py"],
            "tilde": ["python", "~/reproduce.py"],
            "file-uri": ["python", "file:///Users/alice/reproduce.py"],
            "embedded-path": ["matlab", "-batch", "run('/Users/alice/reproduce.m')"],
            "password": ["python", "run.py", "--password", "open-sesame"],
            "api-key": ["python", "run.py", "--api-key=abcdefghijklmnopqrstuvwxyz"],
            "bearer": ["python", "run.py", "Authorization=Bearer abcdefghijklmnopqrstuvwxyz"],
        }
        for name, argv in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as raw:
                staging = init_from_manifest(Path(raw), f"argv-{name}")
                prepare_complete_target(staging, "figure-01")
                path = staging / "targets/figure-01/result.json"
                result = json.loads(path.read_text(encoding="utf-8"))
                result["execution"]["argv"] = argv
                write_json(path, result)
                completed = run_bundle(
                    "finalize", "--bundle", str(staging), "--status", "complete", check=False,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertRegex(completed.stderr, "absolute or home-relative|secret-bearing")

    def test_route_engine_must_match_target_and_shared_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "target-env-mismatch")
            prepare_complete_target(staging, "figure-01", engine="MATLAB")
            env_path = staging / "targets/figure-01/environment/environment.json"
            environment = json.loads(env_path.read_text(encoding="utf-8"))
            environment["engines"] = [{"name": "Python", "version": "test-1"}]
            write_json(env_path, environment)
            result_path = staging / "targets/figure-01/result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            environment_record = next(
                item for item in result["execution"]["frozenArtifacts"] if item["role"] == "environment"
            )
            environment_record["sha256"] = digest(env_path)
            write_json(result_path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("route engine/version is absent or inconsistent", completed.stderr)

        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "shared-env-mismatch")
            prepare_complete_target(staging, "figure-01", engine="MATLAB")
            shared_path = staging / "shared/environment/environment.json"
            shared = json.loads(shared_path.read_text(encoding="utf-8"))
            shared["engines"] = [{"name": "Python", "version": "test-1"}]
            write_json(shared_path, shared)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("shared environment record", completed.stderr)

    def test_route_semantics_and_source_provenance_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "route-semantics")
            prepare_complete_target(staging, "figure-01")
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["route"].pop("tests")
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("route tests must be a non-empty short statement", completed.stderr)

        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "source-provenance")
            prepare_complete_target(staging, "figure-01")
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            source = next(
                item for item in result["execution"]["frozenArtifacts"] if item["role"] == "source"
            )
            source.pop("provenance")
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("source provenance is required", completed.stderr)

    def test_v0_and_outputs_must_be_generated_under_target_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "reference-as-v0")
            prepare_complete_target(staging, "figure-01")
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            reference = result["identity"]["referencePath"]
            result["baselineV0"] = reference
            result["selectedOutput"] = reference
            result["outputs"] = [reference]
            result["acceptance"]["criteria"][0]["evidencePaths"] = [reference]
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("baseline V0 is outside its permitted bundle domain", completed.stderr)

        with tempfile.TemporaryDirectory() as raw:
            staging = init_targets(
                Path(raw), "copied-target-as-v0", ["figure-01=scientific-reproduction"]
            )
            prepare_complete_target(staging, "figure-01", reference_exists=False)
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            reference = staging / result["identity"]["referencePath"]
            baseline = staging / result["baselineV0"]
            baseline.write_bytes(reference.read_bytes())
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("baselineV0 may not duplicate target pixels", completed.stderr)

    def test_resource_cap_cannot_claim_enforcement_without_mechanism(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "dishonest-cap")
            prepare_complete_target(staging, "figure-01")
            record_resources(staging, cap_enforcement="technically-enforced", mechanism=None)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("requires its mechanism", completed.stderr)

    def test_final_folder_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            staging = init_from_manifest(root, "collision")
            (staging.parent / "scirepro-run-collision").mkdir()
            prepare_complete_target(staging, "figure-01")
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("destination already exists", completed.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlink support")
    def test_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "symlink")
            prepare_complete_target(staging, "figure-01")
            os.symlink(staging / "targets/figure-01/result.json", staging / "targets/figure-01/link.json")
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("symlinks are forbidden", completed.stderr)

    def test_secret_like_content_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "secret")
            prepare_complete_target(staging, "figure-01")
            secret = staging / "targets/figure-01/logs/run.log"
            secret.parent.mkdir(parents=True, exist_ok=True)
            secret.write_text("api_key=abcdefghijklmnopqrstuvwxyz\n", encoding="utf-8")
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("secret-like assignment", completed.stderr)

    def test_shareable_bundle_rejects_local_only_executed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_targets(
                Path(raw), "rights", ["figure-01=image-derived-reconstruction"], distribution="shareable",
            )
            prepare_complete_target(staging, "figure-01", reference_exists=False)
            path = staging / "targets/figure-01/result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["execution"]["frozenArtifacts"][1]["rightsStatus"] = "local-only"
            write_json(path, result)
            completed = run_bundle(
                "finalize", "--bundle", str(staging), "--status", "complete", check=False,
            )
            self.assertIn("artifact is not shareable", completed.stderr)

    def test_post_publish_tampering_is_rejected_by_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            staging = init_from_manifest(Path(raw), "tamper")
            prepare_complete_target(staging, "figure-01")
            final = self.finalize(staging, "complete")
            readme = final / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
            completed = run_bundle("validate", "--bundle", str(final), check=False)
            self.assertIn("inventory", completed.stderr)


if __name__ == "__main__":
    unittest.main()
