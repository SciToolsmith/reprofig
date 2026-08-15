from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ASSEMBLER = REPO / "scirepro/scripts/assemble_delivery.py"
MAX_FILE_BYTES = 256 * 1024 * 1024


def run_assembler(plan: Path, output_root: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [
            sys.executable,
            str(ASSEMBLER),
            "--plan",
            str(plan),
            "--output-root",
            str(output_root),
            "--json",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.inputs = root / "internal"
        self.inputs.mkdir(parents=True)

    def file(self, name: str, content: bytes | str) -> Path:
        path = self.inputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            path.write_bytes(content)
        return path

    def artifact(
        self,
        source_name: str,
        output_name: str,
        content: bytes | str,
        rights: str = "generated",
        label: str | None = None,
    ) -> dict:
        source = self.file(source_name, content)
        value = {
            "source": source.relative_to(self.root).as_posix(),
            "name": output_name,
            "rights": rights,
        }
        if label is not None:
            value["label"] = label
        return value

    def target(
        self,
        target_id: str,
        *,
        kind: str = "quantitative",
        executable: bool = True,
        reference: bool = False,
    ) -> dict:
        if kind in {"image-derived", "semantic-diagram"}:
            claim = "not-applicable"
        else:
            claim = "supported"
        if kind == "image-derived":
            route = "image-derived-reconstruction"
            validation_basis = ["Visible geometry and labels were checked against the supplied reference."]
        elif kind == "semantic-diagram":
            route = "semantic-diagram-handoff"
            validation_basis = ["Editable structure and rendered appearance were checked."]
        else:
            route = "direct-recompute"
            validation_basis = ["The declared observable was checked against the target criterion."]
        target = {
            "id": target_id,
            "title": f"Target {target_id}",
            "kind": kind,
            "operationalStatus": "complete",
            "validationStatus": "passed",
            "claimStatus": claim,
            "route": route,
            "stageDecisions": (
                []
                if kind in {"image-derived", "semantic-diagram"}
                else [{
                    "stage": "method",
                    "materialToClaim": True,
                    "authorNative": None,
                    "selected": "python",
                    "nativeCapability": "not-applicable",
                    "selectionBasis": "no-author-native",
                    "reason": "No target-relevant author-native implementation was supplied.",
                    "evidenceBoundary": None,
                }]
            ),
            "validationBasis": validation_basis,
            "materialAssumptions": [],
            "conclusion": f"The declared observable for {target_id} was assessed.",
            "mainResult": self.artifact(
                f"{target_id}/result.bin",
                "result.png" if kind != "semantic-diagram" else "result.pptx",
                b"result:" + target_id.encode("ascii"),
            ),
            "sourceFiles": [],
            "configFiles": [],
            "inputFiles": [],
            "modelFiles": [],
            "environmentFiles": [],
            "requestedExtras": [],
            "limitations": [f"Scope is limited to {target_id}."],
            "rights": "All generated output is deliverable.",
        }
        if reference:
            target["inputFiles"] = [self.artifact(
                f"{target_id}/reference.bin",
                "reference.png",
                b"reference:" + target_id.encode("ascii"),
                "local-only",
            )]
            target["rights"] = "The supplied input is included only in this local-private delivery."
        if executable or kind in {"quantitative", "other"}:
            extension = "mjs" if kind == "semantic-diagram" else "py"
            executable_name = "build.mjs" if kind == "semantic-diagram" else "reproduce.py"
            executable_command = "node" if kind == "semantic-diagram" else "python3"
            target["sourceFiles"] = [
                self.artifact(
                    f"{target_id}/implementation.{extension}",
                    executable_name,
                    f"// implementation {target_id}\n" if extension == "mjs" else f"print({target_id!r})\n",
                ),
            ]
            target["configFiles"] = [
                self.artifact(
                    f"{target_id}/parameters.json",
                    "parameters.json",
                    json.dumps({"target": target_id}) + "\n",
                ),
            ]
            target["environmentFiles"] = [
                self.artifact(
                    f"{target_id}/requirements.txt",
                    "requirements.txt" if kind != "semantic-diagram" else "package.json",
                    f"dependency-for-{target_id}\n",
                ),
            ]
            target["_rerunExecutable"] = executable_name
            target["_rerunCommand"] = executable_command
            target["dependencyNote"] = (
                "Node.js with dependencies declared in package.json."
                if kind == "semantic-diagram"
                else "Python with dependencies declared in requirements.txt."
            )
        return target

    def blocked_target(self, target_id: str) -> dict:
        return {
            "id": target_id,
            "title": f"Blocked {target_id}",
            "kind": "quantitative",
            "operationalStatus": "blocked",
            "validationStatus": "not-run",
            "claimStatus": "not-tested",
            "route": "original-case-blocked",
            "stageDecisions": [],
            "validationBasis": [],
            "materialAssumptions": [],
            "blocker": "The required original input was not published.",
            "conclusion": "No useful result could be produced because the required input is unavailable.",
            "mainResult": None,
            "sourceFiles": [],
            "configFiles": [],
            "inputFiles": [],
            "modelFiles": [],
            "environmentFiles": [],
            "requestedExtras": [],
            "limitations": ["The required input was not published."],
            "rights": "No third-party file is included.",
        }

    def plan(
        self,
        targets: list[dict],
        *,
        slug: str = "example-study",
        distribution: str = "local-private",
        common: list[dict] | None = None,
        licenses: list[dict] | None = None,
    ) -> Path:
        multiple = len(targets) > 1
        for target in targets:
            executable_name = target.pop("_rerunExecutable", None)
            executable_command = target.pop("_rerunCommand", None)
            if executable_name is not None:
                prefix = f"{target['id']}/" if multiple else ""
                target["entrypoint"] = f"{prefix}{executable_name}"
                target["rerunArgv"] = [
                    executable_command,
                    f"{prefix}{executable_name}",
                    "--config",
                    f"{prefix}parameters.json",
                ]
                target["rerunOutputs"] = [
                    f"{prefix}{target['mainResult']['name']}"
                ]
        value = {
            "schemaVersion": "scirepro.delivery-plan/v4",
            "title": "Example scientific reproduction",
            "slug": slug,
            "distribution": distribution,
            "conclusion": "The final conclusions are reported without hiding negative results.",
            "targets": targets,
            "common": common or [],
            "licenses": licenses or [],
        }
        path = self.root / "delivery-plan.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path


class DeliveryAssemblerTests(unittest.TestCase):
    def test_quantitative_delivery_is_human_first_and_whitelisted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01")
            fixture.file("tmp/validation.json", '{"criterion":"trend","status":"passed"}\n')
            fixture.file("tmp/iteration-trace.csv", "iteration,value\n1,0.9\n")
            fixture.file("tmp/raw.log", "internal trace\n")
            fixture.file("tmp/.DS_Store", b"internal metadata")
            plan = fixture.plan([target])

            completed = run_assembler(plan, root / "deliveries")
            delivery = Path(json.loads(completed.stdout)["path"])
            readme = (delivery / "README.md").read_text(encoding="utf-8")

            self.assertIn("The declared observable for fig-01 was assessed", readme)
            self.assertNotIn("**Outcome:**", readme)
            self.assertNotIn("**Method:**", readme)
            self.assertNotIn("The declared observable was checked against the target criterion.", readme)
            self.assertNotIn("| Target | Result | Outcome |", readme)
            self.assertNotIn("`complete`", readme)
            self.assertNotIn("`passed`", readme)
            self.assertNotIn("`supported`", readme)
            self.assertNotIn("`direct-recompute`", readme)
            self.assertNotIn("engineDecision", readme)
            self.assertNotIn("nativeCapability", readme)
            self.assertIn("[result.png](result.png)", readme)
            self.assertIn("![result.png](result.png)", readme)
            self.assertIn("python3 reproduce.py --config parameters.json", readme)
            self.assertEqual(
                {path.name for path in delivery.iterdir()},
                {"README.md", "result.png", "reproduce.py", "parameters.json", "requirements.txt"},
            )
            self.assertFalse(any("validation" in path.name for path in delivery.rglob("*")))
            self.assertFalse(any("trace" in path.name for path in delivery.rglob("*")))
            self.assertFalse((delivery / "delivery-plan.json").exists())
            self.assertFalse(any(path.name == "raw.log" for path in delivery.rglob("*")))
            self.assertFalse((delivery / "manifest.json").exists())
            self.assertFalse((delivery / "shared").exists())
            self.assertFalse((delivery / "LICENSES").exists())

            (delivery / ".DS_Store").write_bytes(b"created later")
            self.assertEqual((delivery / "README.md").read_text(encoding="utf-8"), readme)
            self.assertFalse(any(path.is_dir() and not any(path.iterdir()) for path in delivery.rglob("*")))

    def test_requested_extra_requires_an_explicit_customer_purpose(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", executable=False, reference=False)
            target["requestedExtras"] = [
                fixture.artifact("work/comparison.png", "comparison.png", b"comparison")
            ]
            failed = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("purpose", failed.stderr)

            target["requestedExtras"][0]["purpose"] = "downstream-use"
            delivery = Path(
                json.loads(run_assembler(fixture.plan([target]), root / "valid").stdout)["path"]
            )
            self.assertTrue((delivery / "comparison.png").is_file())
            self.assertIn(
                "[comparison.png](comparison.png)",
                (delivery / "README.md").read_text(encoding="utf-8"),
            )

            target["requestedExtras"][0]["purpose"] = "material-comparison"
            rejected = run_assembler(
                fixture.plan([target], slug="generic-comparison"), root / "comparison", check=False
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("unsupported customer purpose", rejected.stderr)

        for name in (
            "validation.json", "iteration-trace.csv", "sensitivity-results.json",
            "route-probe.json",
        ):
            with self.subTest(process_extra=name), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                fixture = Fixture(root)
                target = fixture.target("fig-01", executable=False, reference=False)
                process_file = fixture.artifact(
                    f"work/{name}", name, '{"status":"passed"}\n'
                )
                process_file["purpose"] = "requested-output"
                target["requestedExtras"] = [process_file]
                rejected = run_assembler(fixture.plan([target]), root / "out", check=False)
                self.assertEqual(rejected.returncode, 2)
                self.assertIn("internal process evidence", rejected.stderr)

    def test_v4_roles_reject_process_evidence_and_old_schema(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            target["configFiles"].append(
                fixture.artifact("work/validation.json", "validation.json", "{}\n")
            )
            rejected = run_assembler(fixture.plan([target]), root / "process", check=False)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("internal process evidence", rejected.stderr)

            clean = fixture.target("fig-02", reference=False)
            old_plan = fixture.plan([clean], slug="old-plan")
            value = json.loads(old_plan.read_text(encoding="utf-8"))
            value["schemaVersion"] = "scirepro.delivery-plan/v3"
            old_plan.write_text(json.dumps(value), encoding="utf-8")
            rejected = run_assembler(old_plan, root / "old", check=False)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("unsupported plan schema", rejected.stderr)

        for name, role in (
            ("environment-python-miniforge-packages.json", "environmentFiles"),
            ("matlab-probe.json", "configFiles"),
            ("audit-manifest.json", "configFiles"),
            ("final-validation.json", "configFiles"),
            ("sensitivity-results.json", "configFiles"),
            ("validation.json", "inputFiles"),
            ("route-probe.json", "modelFiles"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                fixture = Fixture(root)
                target = fixture.target("fig-01", reference=False)
                target[role].append(fixture.artifact(f"work/{name}", name, "{}\n"))
                rejected = run_assembler(fixture.plan([target]), root / "out", check=False)
                self.assertEqual(rejected.returncode, 2)
                self.assertTrue(
                    "internal process evidence" in rejected.stderr
                    or "minimal dependency/environment declaration" in rejected.stderr
                )

        for role in ("configFiles", "inputFiles", "modelFiles", "requestedExtras"):
            with self.subTest(environment_snapshot_role=role), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                fixture = Fixture(root)
                target = fixture.target("fig-01", reference=False)
                snapshot = fixture.artifact(
                    "work/environment-python-miniforge-packages.json",
                    "environment-python-miniforge-packages.json",
                    "{}\n",
                )
                if role == "requestedExtras":
                    snapshot["purpose"] = "requested-output"
                target[role].append(snapshot)
                rejected = run_assembler(fixture.plan([target]), root / "out", check=False)
                self.assertEqual(rejected.returncode, 2)
                self.assertIn("internal process evidence", rejected.stderr)

        for name in ("validation.json", "v0.png", "reference-crop.png"):
            with self.subTest(main_result=name), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                fixture = Fixture(root)
                target = fixture.target("fig-01", reference=False)
                target["mainResult"] = fixture.artifact(f"work/{name}", name, b"process")
                rejected = run_assembler(fixture.plan([target]), root / "out", check=False)
                self.assertEqual(rejected.returncode, 2)
                self.assertIn("internal process evidence", rejected.stderr)

        for name in ("v0.py", "delivery-plan.py", "reference-crop.py", "resource-usage.py"):
            with self.subTest(process_source=name), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                fixture = Fixture(root)
                target = fixture.target("fig-01", reference=False)
                target["sourceFiles"].append(
                    fixture.artifact(f"work/{name}", name, "print('internal')\n")
                )
                rejected = run_assembler(fixture.plan([target]), root / "out", check=False)
                self.assertEqual(rejected.returncode, 2)
                self.assertIn("internal process evidence", rejected.stderr)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            target["sourceFiles"] = [fixture.artifact(
                "work/validation.py",
                "validation.py",
                "from pathlib import Path\nPath('result.png').write_bytes(b'ok')\n",
            )]
            target["_rerunExecutable"] = "validation.py"
            delivery = Path(
                json.loads(run_assembler(fixture.plan([target]), root / "out").stdout)["path"]
            )
            self.assertTrue((delivery / "validation.py").is_file())

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            target["mainResult"] = fixture.artifact(
                "work/validation-plot.png", "validation-plot.png", b"scientific result"
            )
            delivery = Path(
                json.loads(run_assembler(fixture.plan([target]), root / "plot").stdout)["path"]
            )
            self.assertTrue((delivery / "validation-plot.png").is_file())

        for name in ("sensitivity-analysis.png", "probe-response.png", "iteration-trace.png"):
            with self.subTest(scientific_result=name), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                fixture = Fixture(root)
                target = fixture.target("fig-01", reference=False)
                target["mainResult"] = fixture.artifact(
                    f"work/{name}", name, b"scientific result"
                )
                delivery = Path(
                    json.loads(run_assembler(fixture.plan([target]), root / "out").stdout)["path"]
                )
                self.assertTrue((delivery / name).is_file())

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            extra = fixture.artifact(
                "work/sensitivity-curve.csv",
                "sensitivity-curve.csv",
                "parameter,response\n1,2\n",
            )
            extra["purpose"] = "requested-output"
            target["requestedExtras"] = [extra]
            delivery = Path(
                json.loads(run_assembler(fixture.plan([target]), root / "out").stdout)["path"]
            )
            self.assertTrue((delivery / "sensitivity-curve.csv").is_file())

    def test_common_dependency_declarations_are_not_python_specific(self) -> None:
        dependency_names = (
            "requirements.in", "constraints-cpu.txt", "Dockerfile", "Containerfile",
            "compose.yaml", "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
            "pixi.toml", "pixi.lock", "Package.swift", "Package.resolved",
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            target["environmentFiles"] = [
                fixture.artifact(
                    f"environment/{name}", name, f"dependency declaration for {name}\n"
                )
                for name in dependency_names
            ]
            delivery = Path(
                json.loads(run_assembler(fixture.plan([target]), root / "out").stdout)["path"]
            )
            self.assertTrue(all((delivery / name).is_file() for name in dependency_names))

    def test_completed_scientific_work_requires_final_source_and_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            for field in ("sourceFiles", "configFiles", "environmentFiles"):
                target[field] = []
            for field in ("_rerunExecutable", "_rerunCommand", "dependencyNote"):
                target.pop(field, None)
            rejected = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("requires final sourceFiles", rejected.stderr)

    def test_required_data_and_model_are_delivered_by_explicit_role_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            target["inputFiles"] = [
                fixture.artifact("work/validation.csv", "validation.csv", "x,y\n1,2\n")
            ]
            target["modelFiles"] = [
                fixture.artifact("work/model.bin", "model.bin", b"used-model")
            ]
            delivery = Path(
                json.loads(run_assembler(fixture.plan([target]), root / "out").stdout)["path"]
            )
            self.assertTrue((delivery / "validation.csv").is_file())
            self.assertTrue((delivery / "model.bin").is_file())
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertIn("**Required input:**", readme)
            self.assertIn("**Required models:**", readme)

    def test_clean_rerun_contract_allows_only_result_roles(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            plan = fixture.plan([target])
            value = json.loads(plan.read_text(encoding="utf-8"))
            value["targets"][0]["rerunOutputs"].append("validation.json")
            plan.write_text(json.dumps(value), encoding="utf-8")
            rejected = run_assembler(plan, root / "bad", check=False)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("main result or explicitly requested extras", rejected.stderr)

    def test_default_rerun_recreates_result_without_process_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            target["sourceFiles"] = [fixture.artifact(
                "fig-01/final.py",
                "reproduce.py",
                "from pathlib import Path\nPath('result.png').write_bytes(b'recreated')\n",
            )]
            delivery = Path(
                json.loads(run_assembler(fixture.plan([target]), root / "out").stdout)["path"]
            )
            (delivery / "result.png").unlink()
            subprocess.run(
                [sys.executable, "reproduce.py", "--config", "parameters.json"],
                cwd=delivery,
                check=True,
            )
            self.assertTrue((delivery / "result.png").is_file())
            self.assertFalse(any(
                token in path.name.casefold()
                for path in delivery.iterdir()
                for token in ("validation", "probe", "trace", "sensitivity")
            ))

    def test_unreferenced_common_artifact_cannot_bypass_customer_selection(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            first = fixture.target("fig-01", executable=False, reference=False)
            second = fixture.target("fig-02", executable=False, reference=False)
            internal_log = fixture.artifact(
                "internal/everything.log", "everything.log", "internal audit trace\n"
            )
            failed = run_assembler(
                fixture.plan([first, second], common=[internal_log]), root / "out", check=False
            )
            self.assertEqual(failed.returncode, 2)
            self.assertIn("must be referenced by at least one target", failed.stderr)

    def test_rerun_file_arguments_must_exist_in_the_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            target["_rerunExecutable"] = "missing.py"
            failed = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("references a file absent from the delivery", failed.stderr)

        for suffix in (".slx", ".mlx", ".p", ".customformat"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                fixture = Fixture(root)
                plan = fixture.plan([fixture.target("fig-01", reference=False)])
                value = json.loads(plan.read_text(encoding="utf-8"))
                value["targets"][0]["rerunArgv"].append(f"missing{suffix}")
                plan.write_text(json.dumps(value), encoding="utf-8")
                failed = run_assembler(plan, root / "out", check=False)
                self.assertEqual(failed.returncode, 2)
                self.assertIn("references a file absent from the delivery", failed.stderr)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            plan = fixture.plan([fixture.target("fig-01", reference=False)])
            value = json.loads(plan.read_text(encoding="utf-8"))
            value["targets"][0]["rerunArgv"][0] = "missing.sh"
            plan.write_text(json.dumps(value), encoding="utf-8")
            failed = run_assembler(plan, root / "out", check=False)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("rerunArgv[0] references a file absent", failed.stderr)

    def test_target_relevant_native_stage_cannot_be_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", executable=False, reference=False)
            target["stageDecisions"] = [{
                "stage": "method",
                "materialToClaim": True,
                "authorNative": "matlab",
                "selected": "python",
                "nativeCapability": "not-applicable",
                "selectionBasis": "declared-fallback",
                "reason": "The port would replace the author-native method without capability evidence.",
                "evidenceBoundary": "This would be a reimplementation rather than native execution.",
            }]
            failed = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("may not use not-applicable capability", failed.stderr)

    def test_mixed_native_stages_and_nonmaterial_visualization_stay_concise(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", executable=False, reference=False)
            target["stageDecisions"] = [
                {
                    "stage": "input",
                    "materialToClaim": True,
                    "authorNative": "r",
                    "selected": "r",
                    "nativeCapability": "verified",
                    "selectionBasis": "author-native",
                    "reason": "The published R loader reproduced the declared input table.",
                    "evidenceBoundary": None,
                },
                {
                    "stage": "method",
                    "materialToClaim": True,
                    "authorNative": "matlab",
                    "selected": "matlab",
                    "nativeCapability": "verified",
                    "selectionBasis": "author-native",
                    "reason": "The published MATLAB method passed its route smoke test.",
                    "evidenceBoundary": None,
                },
                {
                    "stage": "visualization",
                    "materialToClaim": False,
                    "authorNative": "matlab",
                    "selected": "python",
                    "nativeCapability": "verified",
                    "selectionBasis": "declared-fallback",
                    "reason": "Python produced the requested portable final graphic.",
                    "evidenceBoundary": None,
                },
            ]
            delivery = Path(
                json.loads(run_assembler(fixture.plan([target]), root / "out").stdout)["path"]
            )
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertNotIn("Implementation boundaries", readme)
            self.assertNotIn("portable final graphic", readme)
            self.assertNotIn("author-native MATLAB", readme)

    def test_unverified_target_relevant_native_engine_cannot_be_silently_ported(self) -> None:
        for capability in ("available-untested", "prerequisites-present"):
            with self.subTest(capability=capability):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    fixture = Fixture(root)
                    target = fixture.target("fig-01", executable=False, reference=False)
                    target["stageDecisions"] = [{
                        "stage": "method",
                        "materialToClaim": True,
                        "authorNative": "matlab",
                        "selected": "python",
                        "nativeCapability": capability,
                        "selectionBasis": "declared-fallback",
                        "reason": "Python was proposed only because the native route had not yet been checked.",
                        "evidenceBoundary": "The result would test a port, not the author-native method.",
                    }]
                    failed = run_assembler(fixture.plan([target]), root / "out", check=False)
                    self.assertEqual(failed.returncode, 2)
                    self.assertIn("may not substitute a claim-relevant method stage", failed.stderr)

                    target["stageDecisions"][0]["selectionBasis"] = "objective-portability"
                    target["stageDecisions"][0]["reason"] = "The requested deliverable must be portable."
                    delivery = Path(
                        json.loads(
                            run_assembler(fixture.plan([target]), root / "portable").stdout
                        )["path"]
                    )
                    self.assertTrue((delivery / "result.png").is_file())
                    self.assertIn(
                        "Python replaced author-native MATLAB",
                        (delivery / "README.md").read_text(encoding="utf-8"),
                    )
                    self.assertIn(
                        "The result would test a port, not the author-native method.",
                        (delivery / "README.md").read_text(encoding="utf-8"),
                    )

    def test_image_derived_delivery_has_no_fake_command(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target(
                "panel-a", kind="image-derived", executable=False, reference=True
            )
            target["mainResult"]["name"] = "result.svg"
            plan = fixture.plan([target])
            delivery = Path(json.loads(run_assembler(plan, root / "out").stdout)["path"])
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertIn("image-derived reconstruction", readme)
            self.assertNotIn("`image-derived`", readme)
            self.assertNotIn("`image-derived-reconstruction`", readme)
            self.assertNotIn("`not-applicable`", readme)
            self.assertIn("does not recover or validate the original data", readme)
            self.assertNotIn("### Re-run", readme)

    def test_blocked_image_derived_target_does_not_claim_a_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target(
                "panel-a", kind="image-derived", executable=False, reference=False
            )
            target.update({
                "operationalStatus": "blocked",
                "validationStatus": "not-run",
                "validationBasis": [],
                "blocker": "The image does not identify the hidden mapping required by the request.",
                "conclusion": "No defensible reconstruction could be produced from the supplied pixels alone.",
                "mainResult": None,
            })
            plan = fixture.plan([target])
            rejected = run_assembler(plan, root / "out", check=False)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("should be returned in chat", rejected.stderr)
            self.assertFalse((root / "out/example-study-reproduction").exists())

    def test_blocked_semantic_target_delivers_only_a_readme_without_empty_directories(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target(
                "diagram", kind="semantic-diagram", executable=False, reference=False
            )
            target.update({
                "operationalStatus": "blocked",
                "validationStatus": "not-run",
                "validationBasis": [],
                "blocker": "The supplied image does not identify the hidden semantic mapping.",
                "conclusion": "No defensible editable reconstruction could be produced.",
                "mainResult": None,
            })
            rejected = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("should be returned in chat", rejected.stderr)
            self.assertFalse((root / "out/example-study-reproduction").exists())

    def test_unsupported_scientific_result_has_a_minimal_negative_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", executable=False, reference=False)
            target.update({
                "validationStatus": "failed",
                "claimStatus": "unsupported",
                "validationBasis": ["The completed test reversed the claimed ordering."],
                "conclusion": "The completed reproduction does not support the tested claim.",
                "limitations": [],
            })
            delivery = Path(
                json.loads(run_assembler(fixture.plan([target]), root / "out").stdout)["path"]
            )
            self.assertEqual(
                {path.name for path in delivery.iterdir()},
                {"README.md", "result.png", "reproduce.py", "parameters.json", "requirements.txt"},
            )
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertIn("does not support the tested claim", readme)
            self.assertNotIn("reversed the claimed ordering", readme)

    def test_semantic_diagram_delivery_is_editable_and_rerunnable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-diagram", kind="semantic-diagram", reference=False)
            plan = fixture.plan([target], distribution="shareable")
            delivery = Path(json.loads(run_assembler(plan, root / "out").stdout)["path"])
            self.assertTrue((delivery / "result.pptx").is_file())
            self.assertTrue((delivery / "build.mjs").is_file())
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertIn("node build.mjs --config parameters.json", readme)
            self.assertNotIn("`not-applicable`", readme)

    def test_mixed_targets_use_one_shared_copy_and_report_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            quantitative = fixture.target("fig-01", reference=False)
            diagram = fixture.target("fig-02", kind="semantic-diagram", reference=False)
            blocked = fixture.blocked_target("fig-03")
            shared = [
                fixture.artifact(
                    "shared/environment.txt",
                    "common-environment.txt",
                    "Shared runtime declaration.\n",
                )
            ]
            for target in (quantitative, diagram):
                target["environmentFiles"].append({"commonRef": "common-environment.txt"})
            plan = fixture.plan(
                [quantitative, diagram, blocked],
                distribution="shareable",
                common=shared,
            )
            delivery = Path(json.loads(run_assembler(plan, root / "out").stdout)["path"])
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertEqual(len(list((delivery / "common").iterdir())), 1)
            self.assertFalse((delivery / "LICENSES").exists())
            self.assertIn("No result", readme)
            self.assertNotIn("`blocked`", readme)
            self.assertIn("The required original input was not published.", readme)
            self.assertFalse((delivery / "fig-03").exists())
            self.assertFalse(any(path.is_dir() and not any(path.iterdir()) for path in delivery.rglob("*")))

    def test_common_requires_cross_target_reuse_and_reserved_target_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            shared = [fixture.artifact("shared/env.txt", "environment.txt", "Python 3\n")]
            target = fixture.target("fig-01", reference=False)
            target["environmentFiles"].append({"commonRef": "environment.txt"})
            rejected = run_assembler(
                fixture.plan([target], common=shared), root / "single", check=False
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("single-target deliveries are flat", rejected.stderr)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            shared = [fixture.artifact("shared/env.txt", "environment.txt", "Python 3\n")]
            first = fixture.target("fig-01", reference=False)
            second = fixture.target("fig-02", reference=False)
            first["environmentFiles"].append({"commonRef": "environment.txt"})
            rejected = run_assembler(
                fixture.plan([first, second], common=shared), root / "underused", check=False
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("at least two distinct targets", rejected.stderr)

        for reserved in ("common", "LICENSES", "README.md"):
            with self.subTest(reserved=reserved), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                fixture = Fixture(root)
                target = fixture.target(reserved, reference=False)
                rejected = run_assembler(
                    fixture.plan([target]), root / "reserved", check=False
                )
                self.assertEqual(rejected.returncode, 2)
                self.assertIn("reserved delivery-root name", rejected.stderr)

    def test_scientific_status_matrix_rejects_inconsistent_states(self) -> None:
        invalid = [
            ("partial", "passed", "supported"),
            ("complete", "passed", "partially-supported"),
            ("partial", "failed", "unsupported"),
            ("blocked", "inconclusive", "inconclusive"),
            ("complete", "not-run", "supported"),
        ]
        for operational, validation, claim in invalid:
            with self.subTest(operational=operational, validation=validation, claim=claim):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    fixture = Fixture(root)
                    target = fixture.target("fig-01", executable=False, reference=False)
                    target.update({
                        "operationalStatus": operational,
                        "validationStatus": validation,
                        "claimStatus": claim,
                    })
                    completed = run_assembler(fixture.plan([target]), root / "out", check=False)
                    self.assertEqual(completed.returncode, 2)
                    self.assertFalse((root / "out/example-study-reproduction").exists())

    def test_validated_target_requires_concise_validation_basis(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", executable=False, reference=False)
            target["validationBasis"] = []
            completed = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("requires validationBasis", completed.stderr)

    def test_not_run_target_requires_blocker_but_not_validation_basis(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.blocked_target("fig-01")
            target.pop("blocker")
            completed = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("requires a concise blocker", completed.stderr)

    def test_mechanism_and_alternative_routes_do_not_force_assumptions(self) -> None:
        for route in ("mechanism-reproduction", "alternative-validation"):
            with self.subTest(route=route):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    fixture = Fixture(root)
                    target = fixture.target("fig-01", executable=False, reference=False)
                    target["route"] = route
                    target["materialAssumptions"] = []
                    delivery = Path(
                        json.loads(run_assembler(fixture.plan([target]), root / "out").stdout)["path"]
                    )
                    readme = (delivery / "README.md").read_text(encoding="utf-8")
                    self.assertIn(
                        "mechanism-level reproduction" if route == "mechanism-reproduction" else "alternative validation",
                        readme,
                    )
                    self.assertNotIn(f"`{route}`", readme)

    def test_route_must_match_target_kind_and_blocked_state(self) -> None:
        cases = (
            ("image-derived", "direct-recompute", "complete"),
            ("semantic-diagram", "mechanism-reproduction", "complete"),
            ("quantitative", "image-derived-reconstruction", "complete"),
            ("quantitative", "original-case-blocked", "complete"),
        )
        for kind, route, operational in cases:
            with self.subTest(kind=kind, route=route):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    fixture = Fixture(root)
                    target = fixture.target("fig-01", kind=kind, executable=False, reference=False)
                    target["route"] = route
                    target["operationalStatus"] = operational
                    completed = run_assembler(fixture.plan([target]), root / "out", check=False)
                    self.assertEqual(completed.returncode, 2)

    def test_non_scientific_status_matrix_rejects_impossible_combinations(self) -> None:
        for kind in ("image-derived", "semantic-diagram"):
            for operational, validation in (
                ("blocked", "passed"),
                ("cancelled", "partially-passed"),
                ("complete", "not-run"),
            ):
                with self.subTest(kind=kind, operational=operational, validation=validation):
                    with tempfile.TemporaryDirectory() as raw:
                        root = Path(raw)
                        fixture = Fixture(root)
                        target = fixture.target(kind, kind=kind, executable=False, reference=False)
                        target.update({
                            "operationalStatus": operational,
                            "validationStatus": validation,
                            "mainResult": None if operational in {"blocked", "cancelled"} else target["mainResult"],
                        })
                        completed = run_assembler(fixture.plan([target]), root / "out", check=False)
                        self.assertEqual(completed.returncode, 2)
                        self.assertFalse((root / "out/example-study-reproduction").exists())

    def test_rerunnable_target_requires_dependency_note(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            target.pop("dependencyNote")
            failed = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("dependencyNote", failed.stderr)

            target["dependencyNote"] = "Python standard library only."
            delivery = Path(json.loads(run_assembler(fixture.plan([target]), root / "out").stdout)["path"])
            self.assertIn("Python standard library only", (delivery / "README.md").read_text(encoding="utf-8"))

    def test_shareable_delivery_rejects_local_only_rights(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=True)
            completed = run_assembler(
                fixture.plan([target], distribution="shareable"), root / "out", check=False
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("redistribution rights", completed.stderr)

    def test_licenses_are_only_for_included_third_party_material(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            generated_notice = fixture.artifact(
                "licenses/generated.txt", "GENERATED.txt", "Generated output notice.\n"
            )
            rejected = run_assembler(
                fixture.plan([target], licenses=[generated_notice]), root / "generated", check=False
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("included third-party material", rejected.stderr)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            target["inputFiles"] = [fixture.artifact(
                "vendor/input.csv", "input.csv", "x,y\n1,2\n", "included-permitted"
            )]
            target["rights"] = "The included input is redistributed under its accompanying license."
            license_file = fixture.artifact(
                "vendor/LICENSE", "THIRD-PARTY.txt", "Permissive test license.\n",
                "included-permitted",
            )
            delivery = Path(json.loads(run_assembler(
                fixture.plan(
                    [target], distribution="shareable", licenses=[license_file]
                ),
                root / "third-party",
            ).stdout)["path"])
            self.assertTrue((delivery / "LICENSES/THIRD-PARTY.txt").is_file())

    def test_duplicate_content_requires_canonical_shared_entry(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            first = fixture.target("fig-01", executable=False, reference=False)
            second = fixture.target("fig-02", executable=False, reference=False)
            first_support = fixture.artifact("a.csv", "a.csv", "same evidence\n")
            first_support["purpose"] = "downstream-use"
            second_support = fixture.artifact("b.csv", "b.csv", "same evidence\n")
            second_support["purpose"] = "downstream-use"
            first["requestedExtras"] = [first_support]
            second["requestedExtras"] = [second_support]
            completed = run_assembler(fixture.plan([first, second]), root / "out", check=False)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("canonical common", completed.stderr)

            shared = [fixture.artifact("shared.csv", "common.csv", "same evidence\n")]
            first["requestedExtras"] = [
                {"commonRef": "common.csv", "purpose": "downstream-use"}
            ]
            second["requestedExtras"] = [
                {"commonRef": "common.csv", "purpose": "downstream-use"}
            ]
            delivery = Path(
                json.loads(run_assembler(fixture.plan([first, second], common=shared), root / "out").stdout)["path"]
            )
            self.assertEqual(len(list(delivery.rglob("common.csv"))), 1)

    def test_secrets_and_private_paths_are_rejected(self) -> None:
        cases = ("file", "argv", "prose")
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    fixture = Fixture(root)
                    target = fixture.target("fig-01", reference=False)
                    plan = fixture.plan([target])
                    if case == "file":
                        secret = fixture.artifact(
                            "secret.txt", "evidence.txt", "API_KEY=supersecretvalue\n"
                        )
                        secret["purpose"] = "requested-output"
                        target["requestedExtras"] = [secret]
                        plan = fixture.plan([target])
                    elif case == "argv":
                        target["rerunArgv"].extend(["--token", "ghp_abcdefghijklmnopqrstuvwxyz1234"])
                        plan = fixture.plan([target])
                    else:
                        value = json.loads(plan.read_text(encoding="utf-8"))
                        value["conclusion"] = "See /Users/alice/private-project for details."
                        plan.write_text(json.dumps(value), encoding="utf-8")
                    completed = run_assembler(plan, root / "out", check=False)
                    self.assertEqual(completed.returncode, 2)
                    self.assertFalse((root / "out/example-study-reproduction").exists())

        for local_path in ("/tmp/private-result", "/Volumes/lab/private-result", "C:\\work\\private-result"):
            with self.subTest(local_path=local_path), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                fixture = Fixture(root)
                plan = fixture.plan([fixture.target("fig-01", executable=False, reference=False)])
                value = json.loads(plan.read_text(encoding="utf-8"))
                value["conclusion"] = f"Internal result remained at {local_path}."
                plan.write_text(json.dumps(value), encoding="utf-8")
                completed = run_assembler(plan, root / "out", check=False)
                self.assertEqual(completed.returncode, 2)
                self.assertIn("local absolute path", completed.stderr)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            plan = fixture.plan([fixture.target("fig-01", executable=False, reference=False)])
            value = json.loads(plan.read_text(encoding="utf-8"))
            value["targets"][0]["conclusion"] = (
                "Profile: standard. File: generated result. "
                "Public context is available at https://example.org/study."
            )
            plan.write_text(json.dumps(value), encoding="utf-8")
            delivery = Path(json.loads(run_assembler(plan, root / "out").stdout)["path"])
            self.assertIn(
                "https://example.org/study",
                (delivery / "README.md").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Profile: standard. File: generated result.",
                (delivery / "README.md").read_text(encoding="utf-8"),
            )

    def test_secret_text_inside_compressed_office_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            package = fixture.inputs / "diagram.pptx"
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "docProps/custom.xml",
                    '<Properties><property>API_KEY=supersecretvalue</property></Properties>',
                )
            target = fixture.target("diagram", kind="semantic-diagram", executable=False, reference=False)
            target["mainResult"] = {
                "source": package.relative_to(root).as_posix(),
                "name": "result.pptx",
                "rights": "generated",
            }
            completed = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("secret-shaped text", completed.stderr)
            self.assertFalse((root / "out/example-study-reproduction").exists())

    def test_archive_members_are_scanned_fail_closed(self) -> None:
        cases: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            zip_env = fixture.inputs / "hidden-env.zip"
            with zipfile.ZipFile(zip_env, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("nested/.env", "ordinary-looking-value\n")
            cases.append((zip_env.relative_to(root).as_posix(), "sensitive member name"))

            zip_traversal = fixture.inputs / "traversal.zip"
            with zipfile.ZipFile(zip_traversal, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("../../outside.sh", "echo safe\n")
            cases.append((zip_traversal.relative_to(root).as_posix(), "traverses outside"))

            tar_secret = fixture.inputs / "hidden-secret.tar.gz"
            payload = b"API_KEY=supersecretvalue\n"
            with tarfile.open(tar_secret, "w:gz") as archive:
                info = tarfile.TarInfo("payload/data.bin")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            cases.append((tar_secret.relative_to(root).as_posix(), "secret-shaped text"))

            for token_index, member_name in enumerate((
                "payload/ghp_abcdefghijklmnopqrstuvwxyz1234.txt",
                "payload/API_KEY=supersecretvalue.txt",
            )):
                named_secret = fixture.inputs / f"named-secret-{token_index}.tar.gz"
                benign = b"ordinary content\n"
                with tarfile.open(named_secret, "w:gz") as archive:
                    info = tarfile.TarInfo(member_name)
                    info.size = len(benign)
                    archive.addfile(info, io.BytesIO(benign))
                cases.append((named_secret.relative_to(root).as_posix(), "secret-shaped text"))

            inner_buffer = io.BytesIO()
            with zipfile.ZipFile(inner_buffer, "w", compression=zipfile.ZIP_DEFLATED) as inner:
                inner.writestr(".env", "API_KEY=supersecretvalue\n")
            inner_bytes = inner_buffer.getvalue()

            nested_zip = fixture.inputs / "nested.zip"
            with zipfile.ZipFile(nested_zip, "w", compression=zipfile.ZIP_DEFLATED) as outer:
                outer.writestr("payload/inner.zip", inner_bytes)
            cases.append((nested_zip.relative_to(root).as_posix(), "nested compressed package"))

            nested_tar = fixture.inputs / "nested.tar.gz"
            with tarfile.open(nested_tar, "w:gz") as outer:
                info = tarfile.TarInfo("payload/inner.zip")
                info.size = len(inner_bytes)
                outer.addfile(info, io.BytesIO(inner_bytes))
            cases.append((nested_tar.relative_to(root).as_posix(), "nested compressed package"))

            for index, (source, expected) in enumerate(cases):
                with self.subTest(source=source):
                    target = fixture.target(
                        f"archive-{index}", executable=False, reference=False
                    )
                    target["mainResult"] = {
                        "source": source,
                        "name": f"result-{index}.package",
                        "rights": "generated",
                    }
                    failed = run_assembler(
                        fixture.plan([target], slug=f"archive-case-{index}"),
                        root / f"out-{index}",
                        check=False,
                    )
                    self.assertEqual(failed.returncode, 2)
                    self.assertIn(expected, failed.stderr)

    def test_limitations_must_remain_customer_concise(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", executable=False, reference=False)
            target["limitations"] = [f"Internal audit note {index}." for index in range(13)]
            failed = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("limitations contains too many entries", failed.stderr)

    def test_symlink_unsafe_name_and_oversized_file_are_rejected(self) -> None:
        for case in ("symlink", "name", "size"):
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    fixture = Fixture(root)
                    target = fixture.target("fig-01", executable=False, reference=False)
                    if case == "symlink":
                        real = fixture.file("real.csv", "evidence\n")
                        link = fixture.inputs / "link.csv"
                        link.symlink_to(real)
                        target["requestedExtras"] = [{
                            "source": link.relative_to(root).as_posix(),
                            "name": "evidence.csv",
                            "rights": "generated",
                            "purpose": "requested-output",
                        }]
                    elif case == "name":
                        target["mainResult"]["name"] = "../escape.png"
                    else:
                        huge = fixture.file("huge.bin", b"")
                        with huge.open("wb") as handle:
                            handle.truncate(MAX_FILE_BYTES + 1)
                        target["requestedExtras"] = [{
                            "source": huge.relative_to(root).as_posix(),
                            "name": "huge.bin",
                            "rights": "generated",
                            "purpose": "requested-output",
                        }]
                    completed = run_assembler(fixture.plan([target]), root / "out", check=False)
                    self.assertEqual(completed.returncode, 2)

    def test_existing_destination_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            plan = fixture.plan([fixture.target("fig-01", reference=False)])
            destination = root / "out/example-study-reproduction"
            destination.mkdir(parents=True)
            sentinel = destination / "keep.txt"
            sentinel.write_text("original\n", encoding="utf-8")
            completed = run_assembler(plan, root / "out", check=False)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "original\n")
            self.assertFalse(any(path.name.startswith(".example-study-reproduction.staging-") for path in (root / "out").iterdir()))
            self.assertFalse((root / "out/.example-study-reproduction.publish.lock").exists())

    def test_same_plan_produces_same_files_and_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            plan = fixture.plan([fixture.target("fig-01", reference=False)])
            first = Path(json.loads(run_assembler(plan, root / "out-a").stdout)["path"])
            second = Path(json.loads(run_assembler(plan, root / "out-b").stdout)["path"])

            def snapshot(directory: Path) -> dict[str, bytes]:
                return {
                    path.relative_to(directory).as_posix(): path.read_bytes()
                    for path in directory.rglob("*")
                    if path.is_file()
                }

            self.assertEqual(snapshot(first), snapshot(second))


if __name__ == "__main__":
    unittest.main()
