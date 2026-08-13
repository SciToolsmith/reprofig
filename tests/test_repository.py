from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "scirepro"


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

    def test_browser_javascript_parses(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required to syntax-check the offline report application")
        app = SKILL / "assets" / "research-report-web" / "app.js"
        completed = subprocess.run([node, "--check", str(app)], cwd=REPO, text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        source = app.read_text(encoding="utf-8")
        self.assertNotIn("findRoute(", source)
        self.assertIn("routeFor(figure, binding.routeId)", source)

    def test_skill_frontmatter_and_routed_references(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertRegex(frontmatter, r"(?m)^name:\s*scirepro\s*$")
        self.assertRegex(frontmatter, r"(?m)^description:\s*\S")
        for reference in (
            "target-figure-acquisition.md",
            "report-scaffold.md",
            "image-derived-reconstruction.md",
            "source-environment-audit.md",
            "investigation-schema.md",
            "web-report-contract.md",
            "permission-gates.md",
            "execution-validation.md",
            "run-bundle-contract.md",
            "diagram-handoff.md",
        ):
            self.assertIn(reference, text, "SKILL.md must route to " + reference)
            self.assertTrue((SKILL / "references" / reference).is_file())

    def test_skill_uses_one_minimum_sufficient_workflow(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Unified workflow and stopping rule", skill_text)
        self.assertIn("minimum sufficient investigation", skill_text)
        self.assertIn("candidate specifications, not automatically correct facts", skill_text)
        self.assertIn("Do not derive or audit unrelated formulas", skill_text)
        self.assertIn("build the local target-displaying report", skill_text)

        governed_files = (
            REPO / "README.md",
            REPO / "README.en.md",
            SKILL / "SKILL.md",
            SKILL / "agents" / "openai.yaml",
            SKILL / "references" / "permission-gates.md",
            SKILL / "references" / "report-scaffold.md",
        )
        governed_text = "\n".join(path.read_text(encoding="utf-8") for path in governed_files)
        for retired_term in (
            "**简析**",
            "**轻量报告**",
            "**完整审计**",
            "adaptive workflow depth",
            "**Compact local report**",
            "**Full audited report**",
            "choose the smallest sufficient assessment depth",
        ):
            self.assertNotIn(retired_term, governed_text)

    def test_semantic_schematics_are_terminally_handed_off(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        handoff = (SKILL / "references" / "diagram-handoff.md").read_text(encoding="utf-8")
        gates = (SKILL / "references" / "permission-gates.md").read_text(encoding="utf-8")
        execution = (SKILL / "references" / "execution-validation.md").read_text(encoding="utf-8")
        schema = (SKILL / "references" / "investigation-schema.md").read_text(encoding="utf-8")
        acquisition = (SKILL / "references" / "target-figure-acquisition.md").read_text(encoding="utf-8")
        agent = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")

        router_at = skill_text.index("## Terminal diagram router")
        self.assertLess(router_at, skill_text.index("## Invariants"))
        self.assertLess(router_at, skill_text.index("## Unified workflow and stopping rule"))
        self.assertIn("end SciRepro ownership immediately", skill_text)
        self.assertIn("Do not create or continue a SciRepro target manifest", skill_text)
        self.assertNotIn("## Specialized routing", skill_text)
        self.assertIn("Once the transfer succeeds, SciRepro instructions cease to govern", handoff)
        self.assertIn("one standing exception before SciRepro Phase 0", gates)
        self.assertIn("must have left SciRepro through the terminal router", execution)
        self.assertIn("legacy protocol value", execution)
        self.assertIn("only for compatibility with archived protocol records", schema)
        self.assertIn("do not create a SciRepro target workspace or manifest", acquisition)
        self.assertIn("hand semantic schematics off to $sci-diagram-pptx immediately", agent)

        for pinned in (
            "SciToolsmith/sci-diagram-pptx",
            "skills/sci-diagram-pptx",
            "26a2ae281df4209fa9687ca80d27a3aa7feb1ee3",
        ):
            self.assertIn(pinned, handoff)

    def test_readmes_are_compact_parallel_product_pages(self) -> None:
        chinese_path = REPO / "README.md"
        english_path = REPO / "README.en.md"
        chinese = chinese_path.read_text(encoding="utf-8")
        english = english_path.read_text(encoding="utf-8")

        self.assertLessEqual(len(chinese.splitlines()), 80)
        self.assertLessEqual(len(english.splitlines()), 80)
        self.assertEqual(chinese.count('<h1 align="center">SciRepro</h1>'), 1)
        self.assertEqual(english.count('<h1 align="center">SciRepro</h1>'), 1)
        self.assertNotIn("scirepro-hero", chinese + english)
        self.assertIn("docs/assets/report-preview.webp", chinese)
        self.assertIn("docs/assets/report-preview.webp", english)
        for required in (
            "使用 $skill-installer",
            "使用 $scirepro",
            "先看报告，再决定",
            "你会得到",
            "科学边界",
        ):
            self.assertIn(required, chinese)
        for required in (
            "Use $skill-installer",
            "Use $scirepro",
            "Review the report before execution",
            "What you receive",
            "Scientific boundaries",
        ):
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
        self.assertIn("potential research-integrity concern", execution)
        self.assertIn("requires explicit user authorization", execution)


if __name__ == "__main__":
    unittest.main()
