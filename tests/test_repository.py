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
        ):
            self.assertIn(reference, text, "SKILL.md must route to " + reference)
            self.assertTrue((SKILL / "references" / reference).is_file())

    def test_generated_cache_files_are_not_tracked(self) -> None:
        completed = subprocess.run(
            ["git", "ls-files"], cwd=REPO, text=True, capture_output=True, check=True,
        )
        forbidden = [
            path for path in completed.stdout.splitlines()
            if path.endswith((".pyc", ".pyo", ".DS_Store")) or "/__pycache__/" in f"/{path}/"
        ]
        self.assertEqual(forbidden, [], "generated cache files must not be tracked")


if __name__ == "__main__":
    unittest.main()
