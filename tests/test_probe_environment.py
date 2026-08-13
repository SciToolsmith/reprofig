from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scirepro" / "scripts" / "probe_environment.py"


class ProbeEnvironmentTests(unittest.TestCase):
    def run_probe(
        self,
        workspace: Path,
        *arguments: str,
        path: str | None = None,
        home: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        if path is not None:
            environment["PATH"] = path
        if home is not None:
            environment["HOME"] = str(home)
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--workspace", str(workspace), *arguments],
            cwd=REPO,
            env=environment,
            text=True,
            capture_output=True,
            timeout=20,
        )

    @staticmethod
    def make_executable(path: Path, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def test_automatic_python_discovery_never_runs_path_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            sentinel = root / "executed.txt"
            fake_python = root / "bin" / "python"
            self.make_executable(
                fake_python,
                f"#!/bin/sh\nprintf executed > {sentinel}\nexit 0\n",
            )

            completed = self.run_probe(
                workspace,
                "--runtime",
                "python",
                path=str(fake_python.parent),
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(sentinel.exists(), "automatic discovery must remain static-only")
            self.assertNotIn(str(root), completed.stdout)
            report = json.loads(completed.stdout)
            path_entry = next(entry for entry in report["python"] if entry["source"] == "PATH:python")
            self.assertEqual(path_entry["verificationStatus"], "available")
            self.assertFalse(path_entry["verified"])
            self.assertIsNone(path_entry["probe"])
            self.assertFalse(path_entry["explicitSelection"])

    def test_explicit_real_interpreter_is_verified_with_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            interpreter = Path(sys.executable).resolve(strict=True)
            self.assertFalse(interpreter.is_symlink())

            completed = self.run_probe(
                workspace,
                "--runtime",
                "python",
                "--python-executable",
                str(interpreter),
                "--timeout",
                "5",
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn(str(root), completed.stdout)
            report = json.loads(completed.stdout)
            entry = next(entry for entry in report["python"] if entry["explicitSelection"])
            self.assertTrue(entry["verified"])
            self.assertEqual(entry["verificationStatus"], "verified")
            self.assertEqual(entry["binaryProbeStatus"], "verified-no-site")
            self.assertEqual(entry["probe"]["returncode"], 0)
            self.assertIn("-I", entry["probe"]["command"])
            self.assertIn("-S", entry["probe"]["command"])
            self.assertTrue(entry["details"]["isolation"]["no_user_site"])
            self.assertEqual(
                entry["details"]["isolation"],
                {
                    "isolated": True,
                    "no_site": True,
                    "no_user_site": True,
                    "ignore_environment": True,
                },
            )
            self.assertEqual(report["privacy"]["explicitPythonProbeCount"], 1)

    def test_explicit_probe_failure_is_reported_without_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            fake_python = root / "bin" / "python-fails"
            self.make_executable(fake_python, "#!/bin/sh\necho \"failure at $0\" >&2\nexit 7\n")

            completed = self.run_probe(
                workspace,
                "--python-executable",
                str(fake_python),
                home=root,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertNotIn(str(root), completed.stdout)
            self.assertIn("native Python executable", completed.stderr)

    def test_invalid_selected_executables_are_rejected_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            interpreter = Path(sys.executable).resolve(strict=True)
            link = root / "python-link"
            link.symlink_to(interpreter)
            not_executable = root / "python-no-exec"
            not_executable.write_text("not executable\n", encoding="utf-8")
            sentinel = root / "workspace-executed.txt"
            workspace_python = workspace / "python"
            self.make_executable(
                workspace_python,
                f"#!/bin/sh\nprintf executed > {sentinel}\nexit 0\n",
            )

            cases = (
                ("python3", "absolute path"),
                (str(root / "missing"), "accessible executable file"),
                (str(root), "regular executable"),
                (str(not_executable), "not executable"),
                (str(workspace_python), "workspace-controlled"),
            )
            for selected, expected_message in cases:
                with self.subTest(selected=selected):
                    completed = self.run_probe(
                        workspace,
                        "--python-executable",
                        selected,
                        home=root,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn(expected_message, completed.stderr)
                    self.assertNotIn(str(root), completed.stderr)
            self.assertFalse(sentinel.exists())

    def test_explicit_native_symlink_launcher_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            launcher = root / "python-launcher"
            launcher.symlink_to(Path(sys.executable).resolve(strict=True))

            completed = self.run_probe(
                workspace,
                "--python-executable",
                str(launcher),
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            entries = [entry for entry in report["python"] if entry["explicitSelection"]]
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertTrue(entry["verified"])
            self.assertTrue(entry["invocationPath"].endswith("/python-launcher"))
            self.assertNotEqual(entry["invocationPath"], entry["resolvedPath"])

    def test_workspace_pep405_venv_reports_static_identity_without_loading_site(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            venv = workspace / ".venv"
            created = subprocess.run(
                [sys.executable, "-m", "venv", str(venv)],
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            launcher = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            sentinel = root / "sitecustomize-executed.txt"
            if os.name == "nt":
                site_packages = venv / "Lib" / "site-packages"
            else:
                version = f"python{sys.version_info.major}.{sys.version_info.minor}"
                site_packages = venv / "lib" / version / "site-packages"
            site_packages.mkdir(parents=True, exist_ok=True)
            (site_packages / "sitecustomize.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n",
                encoding="utf-8",
            )

            rejected = self.run_probe(
                workspace,
                "--python-executable",
                str(launcher),
                home=root,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("--allow-workspace-python", rejected.stderr)

            completed = self.run_probe(
                workspace,
                "--python-executable",
                str(launcher),
                "--allow-workspace-python",
                home=root,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn(str(root), completed.stdout)
            report = json.loads(completed.stdout)
            entries = [entry for entry in report["python"] if entry["explicitSelection"]]
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertFalse(sentinel.exists(), "-I -S probe must never load sitecustomize")
            self.assertFalse(entry["verified"])
            self.assertEqual(entry["verificationStatus"], "available")
            self.assertEqual(entry["binaryProbeStatus"], "verified-no-site")
            self.assertEqual(entry["verificationScope"], "interpreter-binary-no-site")
            self.assertFalse(entry["siteRuntimeVerified"])
            self.assertFalse(entry["packagesVerified"])
            self.assertEqual(entry["invocationPath"], "$WORKSPACE/.venv/bin/python")
            self.assertEqual(entry["pep405Root"], "$WORKSPACE/.venv")
            self.assertEqual(entry["pep405Identity"]["status"], "detected-static")
            self.assertEqual(entry["pep405Identity"]["marker"], "$WORKSPACE/.venv/pyvenv.cfg")
            self.assertIn("-S", entry["probe"]["command"])
            self.assertTrue(entry["details"]["isolation"]["no_site"])
            self.assertEqual(
                report["privacy"]["workspaceExecutionScope"],
                "explicit-pep405-python-binary-no-site-only",
            )

    def test_workspace_symlink_without_pep405_marker_is_rejected_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            launcher = workspace / ".venv" / "bin" / "python"
            launcher.parent.mkdir(parents=True)
            launcher.symlink_to(Path(sys.executable).resolve(strict=True))

            completed = self.run_probe(
                workspace,
                "--python-executable",
                str(launcher),
                "--allow-workspace-python",
                home=root,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("pyvenv.cfg", completed.stderr)

    def test_workspace_fake_pep405_script_is_rejected_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            launcher = workspace / ".venv" / "bin" / "python"
            sentinel = root / "executed.txt"
            self.make_executable(
                launcher,
                f"#!/bin/sh\nprintf executed > {sentinel}\nexit 0\n",
            )
            (workspace / ".venv" / "pyvenv.cfg").write_text("home = /invalid\n", encoding="utf-8")

            completed = self.run_probe(
                workspace,
                "--python-executable",
                str(launcher),
                "--allow-workspace-python",
                home=root,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("native Python executable", completed.stderr)
            self.assertFalse(sentinel.exists())

    def test_timeout_is_positive_and_capped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            for timeout in ("0", "61"):
                with self.subTest(timeout=timeout):
                    completed = self.run_probe(workspace, "--timeout", timeout)
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn("between 1 and 60 seconds", completed.stderr)


if __name__ == "__main__":
    unittest.main()
