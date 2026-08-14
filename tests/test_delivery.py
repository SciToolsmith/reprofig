from __future__ import annotations

import json
import os
import subprocess
import sys
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
        reference: bool = True,
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
            "validationBasis": validation_basis,
            "materialAssumptions": [],
            "conclusion": f"The declared observable for {target_id} was assessed.",
            "mainResult": self.artifact(
                f"{target_id}/result.bin",
                "result.png" if kind != "semantic-diagram" else "result.pptx",
                b"result:" + target_id.encode("ascii"),
            ),
            "implementation": [],
            "parameters": [],
            "evidence": [],
            "dependencies": [],
            "limitations": [f"Scope is limited to {target_id}."],
            "rights": "All generated output is deliverable.",
        }
        if reference:
            target["reference"] = self.artifact(
                f"{target_id}/reference.bin",
                "reference.png",
                b"reference:" + target_id.encode("ascii"),
                "local-only",
            )
        if executable:
            extension = "mjs" if kind == "semantic-diagram" else "py"
            executable_name = "build.mjs" if kind == "semantic-diagram" else "reproduce.py"
            executable_command = "node" if kind == "semantic-diagram" else "python3"
            target["implementation"] = [
                self.artifact(
                    f"{target_id}/implementation.{extension}",
                    executable_name,
                    f"// implementation {target_id}\n" if extension == "mjs" else f"print({target_id!r})\n",
                )
            ]
            target["parameters"] = [
                self.artifact(
                    f"{target_id}/parameters.json",
                    "parameters.json",
                    json.dumps({"target": target_id}) + "\n",
                )
            ]
            target["dependencies"] = [
                self.artifact(
                    f"{target_id}/requirements.txt",
                    "requirements.txt" if kind != "semantic-diagram" else "package.json",
                    f"dependency-for-{target_id}\n",
                )
            ]
            target["rerunArgv"] = [
                executable_command,
                f"figures/{target_id}/{executable_name}",
                "--config",
                f"figures/{target_id}/parameters.json",
            ]
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
            "validationBasis": [],
            "materialAssumptions": [],
            "blocker": "The required original input was not published.",
            "conclusion": "No useful result could be produced because the required input is unavailable.",
            "mainResult": None,
            "implementation": [],
            "parameters": [],
            "evidence": [],
            "dependencies": [],
            "limitations": ["The required input was not published."],
            "rights": "No third-party file is included.",
        }

    def plan(
        self,
        targets: list[dict],
        *,
        slug: str = "example-study",
        distribution: str = "local-private",
        shared: list[dict] | None = None,
        licenses: list[dict] | None = None,
    ) -> Path:
        value = {
            "schemaVersion": "scirepro.delivery-plan/v2",
            "title": "Example scientific reproduction",
            "slug": slug,
            "distribution": distribution,
            "conclusion": "The final conclusions are reported without hiding negative results.",
            "targets": targets,
            "shared": shared or [],
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
            target["evidence"] = [
                fixture.artifact(
                    "tmp/qa-summary.json",
                    "scientific-evidence.json",
                    '{"criterion":"trend","status":"passed"}\n',
                    label="Acceptance evidence",
                )
            ]
            fixture.file("tmp/raw.log", "internal trace\n")
            fixture.file("tmp/.DS_Store", b"internal metadata")
            plan = fixture.plan([target])

            completed = run_assembler(plan, root / "deliveries")
            delivery = Path(json.loads(completed.stdout)["path"])
            readme = (delivery / "README.md").read_text(encoding="utf-8")

            self.assertIn("The final conclusions", readme)
            self.assertIn("`complete`", readme)
            self.assertIn("`passed`", readme)
            self.assertIn("`supported`", readme)
            self.assertIn("`direct-recompute`", readme)
            self.assertIn("The declared observable was checked against the target criterion.", readme)
            self.assertIn("Material assumptions:** None declared.", readme)
            self.assertIn("figures/fig-01/result.png", readme)
            self.assertIn("python3 figures/fig-01/reproduce.py", readme)
            self.assertTrue((delivery / "figures/fig-01/scientific-evidence.json").is_file())
            self.assertFalse((delivery / "delivery-plan.json").exists())
            self.assertFalse(any(path.name == "raw.log" for path in delivery.rglob("*")))
            self.assertFalse((delivery / "manifest.json").exists())
            self.assertFalse((delivery / "shared").exists())
            self.assertFalse((delivery / "LICENSES").exists())

            (delivery / ".DS_Store").write_bytes(b"created later")
            self.assertEqual((delivery / "README.md").read_text(encoding="utf-8"), readme)
            self.assertFalse(any(path.is_dir() and not any(path.iterdir()) for path in delivery.rglob("*")))

    def test_image_derived_delivery_has_no_fake_command(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("panel-a", kind="image-derived", executable=False)
            plan = fixture.plan([target])
            delivery = Path(json.loads(run_assembler(plan, root / "out").stdout)["path"])
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertIn("`image-derived`", readme)
            self.assertIn("`image-derived-reconstruction`", readme)
            self.assertIn("`not-applicable`", readme)
            self.assertIn("does not recover or validate the original data", readme)
            self.assertNotIn("### Re-run", readme)

    def test_blocked_image_derived_target_does_not_claim_a_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("panel-a", kind="image-derived", executable=False)
            target.update({
                "operationalStatus": "blocked",
                "validationStatus": "not-run",
                "validationBasis": [],
                "blocker": "The image does not identify the hidden mapping required by the request.",
                "conclusion": "No defensible reconstruction could be produced from the supplied pixels alone.",
                "mainResult": None,
            })
            plan = fixture.plan([target])
            delivery = Path(json.loads(run_assembler(plan, root / "out").stdout)["path"])
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertIn("No result", readme)
            self.assertIn("No image-derived reconstruction was produced", readme)
            self.assertNotIn("This reconstructs visible geometry", readme)

    def test_semantic_diagram_delivery_is_editable_and_rerunnable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-diagram", kind="semantic-diagram", reference=False)
            target["evidence"] = [
                fixture.artifact("fig-diagram/check.json", "editability-check.json", '{"status":"PASS"}\n')
            ]
            plan = fixture.plan([target], distribution="shareable")
            delivery = Path(json.loads(run_assembler(plan, root / "out").stdout)["path"])
            self.assertTrue((delivery / "figures/fig-diagram/result.pptx").is_file())
            self.assertTrue((delivery / "figures/fig-diagram/build.mjs").is_file())
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertIn("node figures/fig-diagram/build.mjs", readme)
            self.assertIn("`not-applicable`", readme)

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
                target["dependencies"] = [{"sharedRef": "common-environment.txt"}]
            license_entry = fixture.artifact("licenses/generated.txt", "GENERATED.txt", "Generated-code notice.\n")
            plan = fixture.plan(
                [quantitative, diagram, blocked],
                distribution="shareable",
                shared=shared,
                licenses=[license_entry],
            )
            delivery = Path(json.loads(run_assembler(plan, root / "out").stdout)["path"])
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertEqual(len(list((delivery / "shared").iterdir())), 1)
            self.assertEqual(len(list((delivery / "LICENSES").iterdir())), 1)
            self.assertIn("No result", readme)
            self.assertIn("`blocked`", readme)
            self.assertIn("The required original input was not published.", readme)
            self.assertFalse((delivery / "figures/fig-03").exists())
            self.assertFalse(any(path.is_dir() and not any(path.iterdir()) for path in delivery.rglob("*")))

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
                    self.assertIn(f"`{route}`", readme)
                    self.assertIn("Material assumptions:** None declared.", readme)

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

    def test_executable_target_requires_dependencies_or_note(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            target = fixture.target("fig-01", reference=False)
            target["dependencies"] = []
            failed = run_assembler(fixture.plan([target]), root / "out", check=False)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("dependency", failed.stderr)

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

    def test_duplicate_content_requires_canonical_shared_entry(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            first = fixture.target("fig-01", executable=False, reference=False)
            second = fixture.target("fig-02", executable=False, reference=False)
            first["evidence"] = [fixture.artifact("a.csv", "a.csv", "same evidence\n")]
            second["evidence"] = [fixture.artifact("b.csv", "b.csv", "same evidence\n")]
            completed = run_assembler(fixture.plan([first, second]), root / "out", check=False)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("canonical shared", completed.stderr)

            shared = [fixture.artifact("shared.csv", "common.csv", "same evidence\n")]
            first["evidence"] = [{"sharedRef": "common.csv"}]
            second["evidence"] = [{"sharedRef": "common.csv"}]
            delivery = Path(
                json.loads(run_assembler(fixture.plan([first, second], shared=shared), root / "out").stdout)["path"]
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
                        target["evidence"] = [
                            fixture.artifact("secret.txt", "evidence.txt", "API_KEY=supersecretvalue\n")
                        ]
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
                        target["evidence"] = [{
                            "source": link.relative_to(root).as_posix(),
                            "name": "evidence.csv",
                            "rights": "generated",
                        }]
                    elif case == "name":
                        target["mainResult"]["name"] = "../escape.png"
                    else:
                        huge = fixture.file("huge.bin", b"")
                        with huge.open("wb") as handle:
                            handle.truncate(MAX_FILE_BYTES + 1)
                        target["evidence"] = [{
                            "source": huge.relative_to(root).as_posix(),
                            "name": "huge.bin",
                            "rights": "generated",
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
