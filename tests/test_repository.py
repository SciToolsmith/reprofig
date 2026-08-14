from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "scirepro"
REFERENCE_LINK = re.compile(r"\[[^\]]+\]\((references/[^)#]+\.md)(?:#[^)]+)?\)")


def direct_reference_paths(skill_text: str) -> tuple[Path, ...]:
    """Return the references selected directly by the active SKILL entrypoint."""
    return tuple(SKILL / relative for relative in dict.fromkeys(REFERENCE_LINK.findall(skill_text)))


def read_existing(paths: list[Path]) -> str:
    """Read active contract files that exist."""
    return "\n".join(path.read_text(encoding="utf-8") for path in paths if path.is_file())


class RepositoryContractTests(unittest.TestCase):
    def test_python_sources_compile(self) -> None:
        sources = sorted((SKILL / "scripts").glob("*.py")) + sorted((REPO / "tests").glob("*.py"))
        completed = subprocess.run(
            [sys.executable, "-m", "py_compile", *map(str, sources)],
            cwd=REPO,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_skill_frontmatter_and_routed_references(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertRegex(frontmatter, r"(?m)^name:\s*scirepro\s*$")
        self.assertRegex(frontmatter, r"(?m)^description:\s*\S")
        for reference in (
            "target-figure-acquisition.md",
            "image-derived-reconstruction.md",
            "source-environment-audit.md",
            "permission-gates.md",
            "execution-validation.md",
            "delivery-contract.md",
            "diagram-handoff.md",
        ):
            self.assertIn(reference, text, "SKILL.md must route to " + reference)
            self.assertTrue((SKILL / "references" / reference).is_file())

    def test_skill_uses_one_adaptive_workflow_without_named_tiers(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        workflow_headings = re.findall(r"(?im)^##\s+([^\n]*workflow[^\n]*)$", skill_text)
        self.assertEqual(
            len(workflow_headings),
            1,
            "the entrypoint should expose one workflow rather than a menu of modes",
        )
        self.assertIn("adaptive", skill_text.casefold())
        self.assertRegex(skill_text.casefold(), r"decision-changing|information gain|acceptance")
        self.assertRegex(skill_text.casefold(), r"\bstop\b")

        for named_tier in (
            r"(?im)^#{1,6}\s*(?:quick|standard|audit)(?:\s+(?:mode|tier|workflow))?\s*$",
            r"(?i)\b(?:quick|standard|audit)\s+(?:mode|tier|workflow)\b",
            r"(?i)\b(?:mode|tier|workflow)s?\s*:\s*quick\s*[,/|>-]+\s*standard\s*[,/|>-]+\s*audit\b",
            r"(?m)^#{1,6}\s*(?:快速|标准|审计)(?:档|模式|流程)?\s*$",
        ):
            self.assertNotRegex(skill_text, named_tier)

    def test_active_workflow_has_no_default_pre_execution_web_report_or_approval(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        governed_files = [
            REPO / "README.md",
            REPO / "README.en.md",
            SKILL / "SKILL.md",
            SKILL / "agents" / "openai.yaml",
            *direct_reference_paths(skill_text),
        ]
        governed = read_existing(governed_files)
        for forbidden in (
            "report-before-execution",
            "awaiting-approval",
            "Review the report before execution",
            "先看报告，再决定",
            "docs/assets/report-preview.webp",
            "web-report-contract.md",
        ):
            self.assertNotIn(forbidden, governed)
        self.assertNotRegex(governed.casefold(), r"default[^\n]{0,80}(?:webpage|web report|approval gate)")
        self.assertRegex(
            governed.casefold(),
            r"(?:do not|never|without)[^\n]{0,100}pre-execution[^\n]{0,100}(?:web|report|approval)",
        )

    def test_skill_routes_directly_one_level_to_customer_delivery_contract(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        links = REFERENCE_LINK.findall(skill_text)
        self.assertEqual(links.count("references/delivery-contract.md"), 1)

        contract_path = SKILL / "references" / "delivery-contract.md"
        self.assertTrue(contract_path.is_file())
        contract = contract_path.read_text(encoding="utf-8")
        self.assertIn("assemble_delivery.py", contract)

    def test_customer_delivery_is_distinct_from_transient_workspace(self) -> None:
        contract_path = SKILL / "references" / "delivery-contract.md"
        self.assertTrue(contract_path.is_file())
        contract = contract_path.read_text(encoding="utf-8")
        workflow = "\n".join((
            (SKILL / "SKILL.md").read_text(encoding="utf-8"),
            (SKILL / "references" / "execution-validation.md").read_text(encoding="utf-8"),
            contract,
        ))
        lowered = workflow.casefold()
        self.assertRegex(lowered, r"customer(?:-facing)?(?: delivery| folder| output)")
        self.assertRegex(lowered, r"(?:transient|temporary|internal)[^\n]{0,80}(?:workspace|staging)")
        self.assertIn(".scirepro-work/<task-id>/", workflow)
        self.assertIn("never a second visible peer delivery", workflow)
        for customer_item in ("README.md", "rerun"):
            self.assertIn(customer_item.casefold(), contract.casefold())
        self.assertRegex(contract.casefold(), r"(?:main|primary|selected)\s+(?:result|output|artifact)")
        self.assertTrue((SKILL / "scripts" / "assemble_delivery.py").is_file())

    def test_active_default_does_not_route_to_retired_finalizer(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        active_files = [
            SKILL / "SKILL.md",
            SKILL / "agents" / "openai.yaml",
            *direct_reference_paths(skill_text),
        ]
        active_text = read_existing(active_files)
        self.assertNotIn("finalize_run_bundle.py", active_text)
        self.assertNotIn("assemble_delivery.py build", active_text)

    def test_semantic_schematics_are_terminally_handed_off(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        handoff = (SKILL / "references" / "diagram-handoff.md").read_text(encoding="utf-8")
        gates = (SKILL / "references" / "permission-gates.md").read_text(encoding="utf-8")
        execution = (SKILL / "references" / "execution-validation.md").read_text(encoding="utf-8")
        acquisition = (SKILL / "references" / "target-figure-acquisition.md").read_text(encoding="utf-8")
        agent = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")

        route_heading = re.search(r"(?im)^##\s+Route ownership(?:\s+first)?\s*$", skill_text)
        workflow_heading = re.search(r"(?im)^##\s+[^\n]*workflow[^\n]*$", skill_text)
        self.assertIsNotNone(route_heading)
        self.assertIsNotNone(workflow_heading)
        self.assertLess(route_heading.start(), workflow_heading.start())
        self.assertIn("end SciRepro ownership", skill_text)
        self.assertRegex(handoff, r"Once (?:the )?transfer succeeds, SciRepro instructions cease to govern")
        self.assertIn("Pinned diagram companion exception", gates)
        self.assertRegex(execution, r"semantic scientific schematic[^\n]+misrouted[^\n]+diagram-handoff\.md")
        self.assertIn("For a semantic schematic, follow [diagram-handoff.md]", acquisition)
        self.assertRegex(agent, r"semantic schematics[^\n]+terminal")
        self.assertRegex(
            handoff,
            r"Do not create a SciRepro target workspace[^\n]+validation record",
        )
        self.assertIn("In a mixed task", handoff)
        self.assertIn("companion's final artifacts", handoff)
        self.assertRegex(handoff, r"(?m)^Pass only(?: the material the receiving skill needs)?:\s*$")
        self.assertRegex(handoff, r"the user's (?:original )?requested deliverable and constraints")
        self.assertIn("## Default terminal deliverable", handoff)
        self.assertIn("`.pptx`", handoff)
        self.assertIn("PNG preview", handoff)
        self.assertRegex(handoff, r"Do not add SVG, PDF,[^\n]+customer folder by default")
        self.assertIn("may create build source and QA artifacts internally", handoff)
        for internal_artifact in ("manifest.json", "logs/"):
            self.assertNotIn(internal_artifact, handoff)

        for pinned in (
            "SciToolsmith/sci-diagram-pptx",
            "skills/sci-diagram-pptx",
            "26a2ae281df4209fa9687ca80d27a3aa7feb1ee3",
        ):
            self.assertIn(pinned, handoff)

    def test_legacy_decision_report_stack_is_not_installed(self) -> None:
        retired = (
            "scripts/build_report.py",
            "scripts/init_report.py",
            "scripts/plan_gate.py",
            "scripts/execution_gate.py",
            "references/investigation-schema.md",
            "references/report-scaffold.md",
            "references/web-report-contract.md",
            "references/execution-contract.md",
            "references/automatic-run-folder.md",
            "assets/research-report-web/index.html",
        )
        for relative in retired:
            self.assertFalse((SKILL / relative).exists(), relative + " must not ship in the active skill")

    def test_runtime_dependencies_and_pdf_ci_are_declared(self) -> None:
        requirements = (SKILL / "requirements.txt").read_text(encoding="utf-8")
        workflow = (REPO / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        self.assertIn("Pillow", requirements)
        self.assertIn("pdfplumber", requirements)
        self.assertIn("poppler", workflow)
        self.assertIn("scirepro/requirements.txt", workflow)
        self.assertIn('"3.10"', workflow)

    def test_installable_skill_contains_no_case_specific_rules(self) -> None:
        installable_files = [
            path for path in SKILL.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        ]
        installable_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in installable_files
        )
        for case_specific_pattern in (
            r"\bfeature mode decomposition\b",
            r"\bfmd(?:\.m)?\b",
            r"\bimckd\b",
            r"\bsig1(?:\.mat)?\b",
        ):
            self.assertNotRegex(
                installable_text.casefold(),
                case_specific_pattern,
                "regression-case details must stay in tests, not the reusable skill",
            )

    def test_readmes_describe_the_active_customer_workflow(self) -> None:
        chinese_path = REPO / "README.md"
        english_path = REPO / "README.en.md"
        chinese = chinese_path.read_text(encoding="utf-8")
        english = english_path.read_text(encoding="utf-8")

        self.assertEqual(chinese.count('<h1 align="center">SciRepro</h1>'), 1)
        self.assertEqual(english.count('<h1 align="center">SciRepro</h1>'), 1)
        self.assertNotIn("scirepro-hero", chinese + english)
        self.assertNotIn("docs/assets/report-preview.webp", chinese + english)
        for required in ("使用 $skill-installer", "使用 $scirepro", "客户"):
            self.assertIn(required, chinese)
        for required in ("Use $skill-installer", "Use $scirepro", "customer"):
            self.assertIn(required, english)

    def test_generated_cache_files_are_not_tracked(self) -> None:
        completed = subprocess.run(
            ["git", "ls-files"], cwd=REPO, text=True, capture_output=True, check=True,
        )
        forbidden = [
            path for path in completed.stdout.splitlines()
            if path.endswith((".pyc", ".pyo", ".DS_Store")) or "/__pycache__/" in f"/{path}/"
        ]
        self.assertEqual(forbidden, [], "generated cache files must not be tracked")

    def test_negative_reproduction_and_integrity_language_is_bounded(self) -> None:
        execution = (SKILL / "references" / "execution-validation.md").read_text(encoding="utf-8")
        for claim_status in (
            "`supported`",
            "`partially-supported`",
            "`unsupported`",
            "`inconclusive`",
            "`not-tested`",
        ):
            self.assertIn(claim_status, execution)
        self.assertIn("Failure to reproduce is not by itself evidence of fabrication", execution)
        self.assertRegex(execution, r"potential (?:research-)?integrity concern")
        self.assertRegex(execution, r"requires explicit (?:user )?authorization")


if __name__ == "__main__":
    unittest.main()
