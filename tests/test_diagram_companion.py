from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ENSURE = REPO / "scirepro" / "scripts" / "ensure_diagram_companion.py"
SKILL_NAME = "sci-diagram-pptx"
SOURCE_REPO = "SciToolsmith/sci-diagram-pptx"
SOURCE_PATH = "skills/sci-diagram-pptx"
SOURCE_REF = "26a2ae281df4209fa9687ca80d27a3aa7feb1ee3"
SOURCE_URL = f"https://github.com/{SOURCE_REPO}/tree/{SOURCE_REF}/{SOURCE_PATH}"
REQUIRED_FILES = (
    "LICENSE",
    "agents/openai.yaml",
    "references/runtime-artifact-tool.md",
    "references/runtime-pptxgenjs.md",
    "scripts/check_pptx.py",
    "scripts/panel_crop.py",
    "scripts/probe_runtime.mjs",
    "scripts/render_pptx.py",
)


def write_valid_skill(path: Path, *, name: str = SKILL_NAME, include_scripts: bool = True) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test companion\n---\n\n# Test\n",
        encoding="utf-8",
    )
    if include_scripts:
        for relative in REQUIRED_FILES:
            target = path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# test fixture\n", encoding="utf-8")


class DiagramCompanionTests(unittest.TestCase):
    def run_ensure(self, home: Path, **extra_env: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(extra_env)
        env["CODEX_HOME"] = str(home)
        return subprocess.run(
            [sys.executable, str(ENSURE)],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
        )

    def write_mock_installer(self, home: Path, body: str) -> Path:
        installer = home / "skills" / ".system" / "skill-installer" / "scripts" / "install-skill-from-github.py"
        installer.parent.mkdir(parents=True, exist_ok=True)
        installer.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
        return installer

    def test_existing_valid_install_is_reused_without_modification(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "codex"
            skill_dir = home / "skills" / SKILL_NAME
            write_valid_skill(skill_dir)
            original = (skill_dir / "SKILL.md").read_bytes()
            marker = Path(raw) / "installer-called"
            self.write_mock_installer(
                home,
                f"""
                from pathlib import Path
                Path({str(marker)!r}).write_text("called", encoding="utf-8")
                raise SystemExit(99)
                """,
            )

            completed = self.run_ensure(home)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["skillDir"], str(skill_dir))
            self.assertEqual(payload["source"], "existing-user-managed")
            self.assertIsNone(payload["ref"])
            self.assertFalse(payload["installedThisRun"])
            self.assertFalse(marker.exists())
            self.assertEqual((skill_dir / "SKILL.md").read_bytes(), original)

    def test_missing_install_uses_pinned_download_command_and_validates_result(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "codex"
            args_path = Path(raw) / "installer-args.json"
            self.write_mock_installer(
                home,
                """
                import json
                import os
                import sys
                from pathlib import Path

                args = sys.argv[1:]
                record = {
                    "args": args,
                    "githubTokenPresent": bool(os.environ.get("GITHUB_TOKEN")),
                    "ghTokenPresent": bool(os.environ.get("GH_TOKEN")),
                    "unexpectedCredentialPresent": bool(os.environ.get("AUDIT_FAKE_CREDENTIAL")),
                }
                Path(__ARGS_PATH__).write_text(json.dumps(record), encoding="utf-8")
                dest = Path(args[args.index("--dest") + 1]) / args[args.index("--name") + 1]
                (dest / "scripts").mkdir(parents=True)
                (dest / "agents").mkdir(parents=True)
                (dest / "references").mkdir(parents=True)
                (dest / "SKILL.md").write_text(
                    "---\\nname: sci-diagram-pptx\\ndescription: mock\\n---\\n",
                    encoding="utf-8",
                )
                (dest / "LICENSE").write_text("mock license\\n", encoding="utf-8")
                (dest / "agents" / "openai.yaml").write_text("interface: {{}}\\n", encoding="utf-8")
                (dest / "references" / "runtime-artifact-tool.md").write_text("# mock\\n", encoding="utf-8")
                (dest / "references" / "runtime-pptxgenjs.md").write_text("# mock\\n", encoding="utf-8")
                (dest / "scripts" / "check_pptx.py").write_text("# mock\\n", encoding="utf-8")
                (dest / "scripts" / "panel_crop.py").write_text("# mock\\n", encoding="utf-8")
                (dest / "scripts" / "probe_runtime.mjs").write_text("// mock\\n", encoding="utf-8")
                (dest / "scripts" / "render_pptx.py").write_text("# mock\\n", encoding="utf-8")
                """.replace("__ARGS_PATH__", repr(str(args_path))),
            )

            completed = self.run_ensure(
                home,
                GITHUB_TOKEN="must-not-reach-installer",
                GH_TOKEN="must-not-reach-installer",
                AUDIT_FAKE_CREDENTIAL="supersecretvalue",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "installed")
            self.assertTrue(payload["installedThisRun"])
            self.assertEqual(payload["source"], SOURCE_URL)
            record = json.loads(args_path.read_text(encoding="utf-8"))
            self.assertFalse(record["githubTokenPresent"])
            self.assertFalse(record["ghTokenPresent"])
            self.assertFalse(record["unexpectedCredentialPresent"])
            args = record["args"]
            self.assertEqual(args[args.index("--repo") + 1], SOURCE_REPO)
            self.assertEqual(args[args.index("--path") + 1], SOURCE_PATH)
            self.assertEqual(args[args.index("--ref") + 1], SOURCE_REF)
            self.assertEqual(args[args.index("--method") + 1], "download")
            self.assertEqual(args[args.index("--name") + 1], SKILL_NAME)
            self.assertEqual(args[args.index("--dest") + 1], str(home / "skills"))

    def test_existing_conflicts_fail_closed_without_invoking_installer(self) -> None:
        scenarios = ("regular-file", "wrong-name", "missing-critical", "symlink", "nested-symlink")
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                home = root / "codex"
                skill_dir = home / "skills" / SKILL_NAME
                if scenario == "regular-file":
                    skill_dir.parent.mkdir(parents=True)
                    skill_dir.write_text("collision", encoding="utf-8")
                elif scenario == "wrong-name":
                    write_valid_skill(skill_dir, name="not-the-companion")
                elif scenario == "missing-critical":
                    write_valid_skill(skill_dir, include_scripts=False)
                elif scenario == "symlink":
                    real = root / "real-skill"
                    write_valid_skill(real)
                    skill_dir.parent.mkdir(parents=True)
                    skill_dir.symlink_to(real, target_is_directory=True)
                else:
                    write_valid_skill(skill_dir)
                    real_scripts = root / "real-scripts"
                    real_scripts.mkdir()
                    for script_name in (
                        "check_pptx.py", "panel_crop.py", "probe_runtime.mjs", "render_pptx.py",
                    ):
                        (real_scripts / script_name).write_text("# fixture\n", encoding="utf-8")
                    for child in (skill_dir / "scripts").iterdir():
                        child.unlink()
                    (skill_dir / "scripts").rmdir()
                    (skill_dir / "scripts").symlink_to(real_scripts, target_is_directory=True)

                marker = root / "installer-called"
                self.write_mock_installer(
                    home,
                    f"""
                    from pathlib import Path
                    Path({str(marker)!r}).write_text("called", encoding="utf-8")
                    """,
                )
                completed = self.run_ensure(home)
                self.assertNotEqual(completed.returncode, 0)
                self.assertEqual(completed.stdout, "")
                self.assertIn("error:", completed.stderr)
                self.assertFalse(marker.exists())

    def test_missing_or_failed_installer_and_invalid_post_install_fail_closed(self) -> None:
        scenarios = ("missing", "failed", "invalid-result")
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as raw:
                home = Path(raw) / "codex"
                if scenario == "failed":
                    self.write_mock_installer(home, "raise SystemExit(7)\n")
                elif scenario == "invalid-result":
                    self.write_mock_installer(
                        home,
                        """
                        import sys
                        from pathlib import Path
                        args = sys.argv[1:]
                        dest = Path(args[args.index("--dest") + 1]) / args[args.index("--name") + 1]
                        dest.mkdir(parents=True)
                        (dest / "SKILL.md").write_text(
                            "---\\nname: wrong-skill\\ndescription: mock\\n---\\n",
                            encoding="utf-8",
                        )
                        """,
                    )
                else:
                    (home / "skills").mkdir(parents=True)

                completed = self.run_ensure(home)
                self.assertNotEqual(completed.returncode, 0)
                self.assertEqual(completed.stdout, "")
                self.assertIn("error:", completed.stderr)

    def test_symlinked_skills_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home = root / "codex"
            real_skills = root / "skills"
            real_skills.mkdir()
            home.mkdir()
            (home / "skills").symlink_to(real_skills, target_is_directory=True)

            completed = self.run_ensure(home)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("refusing symlink", completed.stderr)

    def test_symlinked_codex_home_ancestor_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            real_parent = root / "real-parent"
            real_home = real_parent / "codex"
            (real_home / "skills").mkdir(parents=True)
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)

            completed = self.run_ensure(linked_parent / "codex")

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("symlink ancestor", completed.stderr)


if __name__ == "__main__":
    unittest.main()
