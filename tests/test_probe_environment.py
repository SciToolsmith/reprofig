from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import time
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

    def make_matlab_installation(
        self,
        root: Path,
        body: str,
        *,
        application: bool = False,
    ) -> tuple[Path, Path]:
        installation = root / ("MATLAB_R2025a.app" if application else "MATLAB_R2025a")
        installation.mkdir(parents=True, exist_ok=True)
        (installation / "VersionInfo.xml").write_text(
            "<MathWorks_version_info><version>25.1.0</version><release>R2025a</release>"
            "</MathWorks_version_info>\n",
            encoding="utf-8",
        )
        executable = installation / "bin" / "matlab"
        self.make_executable(executable, body)
        return installation, executable

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

    def test_generic_runtime_discovery_never_executes_path_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            bin_dir = root / "path-bin"
            sentinel = root / "generic-runtime-executed"
            fake_julia = bin_dir / "julia"
            self.make_executable(
                fake_julia,
                f"#!/bin/sh\ntouch {shlex.quote(str(sentinel))}\nprintf 'malicious-version\\n'\n",
            )

            completed = self.run_probe(
                workspace,
                "--runtime",
                "julia",
                path=f"{bin_dir}:{os.environ.get('PATH', '')}",
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(sentinel.exists())
            report = json.loads(completed.stdout)
            entry = next(item for item in report["other"] if item["label"] == "Julia")
            self.assertEqual(entry["verificationStatus"], "available")
            self.assertFalse(entry["verified"])
            self.assertIsNone(entry["probe"])
            self.assertIn("static-only", entry["probeSkipped"])

    def test_r_artifact_is_one_runtime_ecosystem_not_matlab_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            script = workspace / "analysis.R"
            script.write_text("print('analysis')\n", encoding="utf-8")

            completed = self.run_probe(
                workspace,
                "--author-artifact", str(script),
                path="/usr/bin:/bin",
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            recommendation = json.loads(completed.stdout)["routeRecommendation"]
            self.assertEqual(recommendation["candidateNativeRuntimes"], ["r"])
            self.assertEqual(recommendation["artifactHint"], "runtime-candidates-require-confirmation")
            self.assertNotIn("MATLAB", recommendation["rationale"])
            self.assertNotIn("Octave", recommendation["rationale"])

    def test_path_only_miss_does_not_claim_generic_runtime_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            script = workspace / "analysis.jl"
            script.write_text("println(1)\n", encoding="utf-8")

            completed = self.run_probe(
                workspace,
                "--author-artifact", str(script),
                "--author-native-runtime", "julia",
                "--substitute-runtime", "python",
                "--substitute-role", "fallback-primary",
                "--substitute-reason", "Use a transparent mechanism implementation only if Julia is unavailable.",
                path="/usr/bin:/bin",
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            recommendation = json.loads(completed.stdout)["routeRecommendation"]
            self.assertEqual(recommendation["nativeRuntimeStatus"], "not-discovered")
            self.assertEqual(recommendation["nativeRouteCapabilityStatus"], "inconclusive")
            self.assertFalse(recommendation["nativeRouteRejected"])
            self.assertIsNone(recommendation["recommendedRuntime"])
            self.assertFalse(recommendation["substitutePrimaryEligible"])
            self.assertTrue(recommendation["decisionRequired"])
            self.assertEqual(
                recommendation["nextAction"],
                "locate-reviewed-native-runtime-or-decide-route",
            )
            self.assertIn("does not prove absence", recommendation["rationale"])

    def test_output_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            output = root / "probe.json"
            output.write_text("sentinel\n", encoding="utf-8")

            completed = self.run_probe(workspace, "--output", str(output), home=root)

            self.assertEqual(completed.returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "sentinel\n")

    def test_explicit_non_python_native_binary_is_rejected_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()

            completed = self.run_probe(
                workspace,
                "--python-executable",
                "/bin/echo",
                home=root,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("recognizable Python interpreter", completed.stderr)

    def test_probe_output_redacts_secrets_and_file_uris(self) -> None:
        from scirepro.scripts.probe_environment import redact_text, run

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            report = run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-c",
                    "print('API_KEY=supersecretvalue')",
                ],
                5,
                workspace,
            )

            self.assertEqual(report["stdout"], "[REDACTED_SECRET_OUTPUT]")
            private_uri = "file:///Volumes/private-lab/secret/data.mat"
            redacted = redact_text(private_uri, workspace)
            self.assertNotIn("private-lab", redacted)
            self.assertEqual(redacted, "file:///$ABSOLUTE_PATH")

    @unittest.skipUnless(os.name == "posix", "process-group termination requires POSIX")
    def test_probe_timeout_terminates_sigterm_ignoring_descendants(self) -> None:
        from scirepro.scripts.probe_environment import run

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            marker = root / "descendant-survived.txt"
            child_code = (
                "import pathlib,signal,time;"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
                "time.sleep(2);"
                f"pathlib.Path({str(marker)!r}).write_text('survived')"
            )
            parent_code = (
                "import subprocess,sys,time;"
                f"subprocess.Popen([sys.executable,'-c',{child_code!r}]);"
                "time.sleep(30)"
            )
            started = time.monotonic()

            report = run(
                [sys.executable, "-I", "-S", "-c", parent_code],
                1,
                workspace,
            )

            self.assertTrue(report["timedOut"])
            self.assertLess(time.monotonic() - started, 3.0)
            time.sleep(2.2)
            self.assertFalse(marker.exists(), "timed-out descendants must not outlive the probe")

    @unittest.skipUnless(os.name == "posix", "process-group termination requires POSIX")
    def test_successful_probe_cannot_leave_background_descendants(self) -> None:
        from scirepro.scripts.probe_environment import run

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            marker = root / "background-survived.txt"
            child_code = (
                "import pathlib,signal,time;"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
                "time.sleep(1);"
                f"pathlib.Path({str(marker)!r}).write_text('survived')"
            )
            parent_code = (
                "import subprocess,sys;"
                f"subprocess.Popen([sys.executable,'-c',{child_code!r}],"
                "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
            )

            report = run(
                [sys.executable, "-I", "-S", "-c", parent_code],
                5,
                workspace,
            )

            self.assertEqual(report["returncode"], 0)
            self.assertFalse(report["timedOut"])
            time.sleep(1.2)
            self.assertFalse(marker.exists(), "successful probes must not leave background work")

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

    def test_matlab_live_probe_requires_exact_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()

            completed = self.run_probe(workspace, "--matlab-live-probe")

            self.assertEqual(completed.returncode, 2)
            self.assertIn(
                "--matlab-live-probe requires --matlab-executable or --matlab-application",
                completed.stderr,
            )

    def test_matlab_selection_rejects_workspace_or_unidentified_launchers_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            sentinel = root / "matlab-ran.txt"

            workspace_installation, workspace_matlab = self.make_matlab_installation(
                workspace,
                f"#!/bin/sh\ntouch {shlex.quote(str(sentinel))}\n",
            )
            random_matlab = root / "attachment" / "bin" / "matlab"
            self.make_executable(
                random_matlab,
                f"#!/bin/sh\ntouch {shlex.quote(str(sentinel))}\n",
            )

            cases = (
                (
                    ("--matlab-application", str(workspace_installation)),
                    "workspace-controlled",
                ),
                (
                    ("--matlab-executable", str(random_matlab)),
                    "recognized installation shape and trusted static product identity",
                ),
            )
            for arguments, expected in cases:
                with self.subTest(arguments=arguments):
                    completed = self.run_probe(
                        workspace,
                        *arguments,
                        "--matlab-live-probe",
                        home=root,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn(expected, completed.stderr)
            self.assertFalse(sentinel.exists())

    def test_exact_matlab_static_selection_requires_live_probe_before_python_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            sentinel = root / "matlab-started.txt"
            _, matlab = self.make_matlab_installation(
                root,
                f"#!/bin/sh\nprintf started > {sentinel}\nexit 0\n",
            )
            method = workspace / "target_method.m"
            method.write_text("fixture\n", encoding="utf-8")

            completed = self.run_probe(
                workspace,
                "--matlab-executable",
                str(matlab),
                "--author-native-runtime",
                "matlab",
                "--matlab-required-license-feature",
                "Signal_Toolbox",
                "--author-artifact",
                str(method),
                "--substitute-runtime",
                "python",
                "--substitute-reason",
                "Use a declared port only if the native route is genuinely unavailable.",
                "--substitute-role",
                "fallback-primary",
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(sentinel.exists())
            report = json.loads(completed.stdout)
            self.assertEqual(report["schemaVersion"], "scirepro.environment/v2")
            self.assertEqual(report["captureStatus"], "partial")
            self.assertEqual(report["engines"], [])
            self.assertIsInstance(report["packages"], list)
            self.assertIsInstance(report["hardware"], dict)
            self.assertIsInstance(report["notes"], list)
            self.assertIn("matlab", report["evidence"])
            entry = next(item for item in report["matlab"] if item["explicitSelection"])
            self.assertEqual(entry["release"], "R2025a")
            self.assertTrue(entry["metadataVerified"])
            self.assertEqual(entry["verificationStatus"], "available")
            self.assertFalse(entry["runtimeVerified"])
            self.assertFalse(entry["verified"])
            self.assertIsNone(entry["liveProbe"])
            self.assertEqual(
                entry["routeRequirements"]["requiredLicenseFeatures"],
                ["Signal_Toolbox"],
            )
            recommendation = report["routeRecommendation"]
            self.assertEqual(recommendation["nativeRuntimeStatus"], "available")
            self.assertEqual(
                recommendation["nativeRouteCapabilityStatus"], "available-untested"
            )
            self.assertEqual(recommendation["recommendedRuntime"], "matlab")
            self.assertEqual(recommendation["nextAction"], "live-probe-native-prerequisites")
            self.assertFalse(recommendation["pythonPrimaryEligible"])
            self.assertFalse(recommendation["nativeRouteRejected"])

    def test_isolated_m_artifact_is_matlab_octave_ambiguous_and_selects_neither(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            method = workspace / "target_method.m"
            method.write_text("function y=target_method(x); y=x; end\n", encoding="utf-8")

            completed = self.run_probe(
                workspace,
                "--author-artifact",
                str(method),
                path=os.environ.get("PATH", ""),
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["selectedRuntimes"], [])
            self.assertEqual(report["matlab"], [])
            artifact = report["authorArtifacts"][0]
            self.assertEqual(artifact["runtimeCandidates"], ["matlab", "octave"])
            self.assertTrue(artifact["runtimeAmbiguous"])
            recommendation = report["routeRecommendation"]
            self.assertFalse(recommendation["evaluated"])
            self.assertIsNone(recommendation["authorNativeRuntime"])
            self.assertEqual(
                recommendation["candidateNativeRuntimes"],
                ["matlab", "octave"],
            )
            self.assertEqual(recommendation["artifactHint"], "ambiguous-runtime-artifact")
            self.assertEqual(recommendation["nextAction"], "identify-author-native-runtime")

    def test_explicit_octave_evidence_routes_shared_m_source_without_matlab(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            method = workspace / "target_method.m"
            method.write_text("function y=target_method(x); y=x; end\n", encoding="utf-8")
            sentinel = root / "octave-ran.txt"
            octave = root / "bin" / "octave"
            self.make_executable(
                octave,
                f"#!/bin/sh\ntouch {shlex.quote(str(sentinel))}\n",
            )

            completed = self.run_probe(
                workspace,
                "--author-native-runtime",
                "octave",
                "--author-artifact",
                str(method),
                path=f"{octave.parent}:{os.environ.get('PATH', '')}",
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(sentinel.exists(), "generic runtime discovery must remain static")
            report = json.loads(completed.stdout)
            self.assertEqual(report["selectedRuntimes"], ["octave"])
            self.assertEqual(report["matlab"], [])
            recommendation = report["routeRecommendation"]
            self.assertTrue(recommendation["evaluated"])
            self.assertEqual(recommendation["authorNativeRuntime"], "octave")
            self.assertEqual(recommendation["nativeRuntimeStatus"], "available")
            self.assertEqual(recommendation["recommendedRuntime"], "octave")
            self.assertEqual(
                recommendation["nextAction"],
                "select-and-run-reviewed-native-smoke",
            )

    def test_r_and_julia_artifacts_preserve_generic_native_runtime_metadata(self) -> None:
        cases = (
            ("analysis.R", "rscript", "Rscript", ["r"]),
            ("analysis.jl", "julia", "julia", ["julia"]),
        )
        for filename, runtime, executable_name, candidates in cases:
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workspace = root / "workspace"
                workspace.mkdir()
                artifact = workspace / filename
                artifact.write_text("fixture\n", encoding="utf-8")
                executable = root / "bin" / executable_name
                self.make_executable(executable, "#!/bin/sh\nexit 0\n")

                completed = self.run_probe(
                    workspace,
                    "--author-native-runtime",
                    runtime,
                    "--author-artifact",
                    str(artifact),
                    path=f"{executable.parent}:{os.environ.get('PATH', '')}",
                    home=root,
                )

                self.assertEqual(completed.returncode, 0, completed.stderr)
                report = json.loads(completed.stdout)
                self.assertEqual(report["authorArtifacts"][0]["runtimeCandidates"], candidates)
                recommendation = report["routeRecommendation"]
                self.assertEqual(recommendation["authorNativeRuntime"], runtime)
                self.assertEqual(recommendation["recommendedRuntime"], runtime)
                self.assertEqual(recommendation["authorNativeRuntimeSelectionSource"], "--author-native-runtime")
                self.assertEqual(recommendation["authorRuntimeConflictingArtifactPaths"], [])

    def test_legacy_python_flags_do_not_infer_native_runtime_from_m_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            method = workspace / "target_method.m"
            method.write_text("fixture\n", encoding="utf-8")

            completed = self.run_probe(
                workspace,
                "--author-artifact",
                str(method),
                "--python-fallback-reason",
                "Use a port only after the author-native runtime is identified and unavailable.",
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            recommendation = json.loads(completed.stdout)["routeRecommendation"]
            self.assertFalse(recommendation["evaluated"])
            self.assertIsNone(recommendation["recommendedRuntime"])
            self.assertEqual(recommendation["substituteRuntime"], "python")
            self.assertEqual(recommendation["substituteRole"], "fallback-primary")
            self.assertTrue(recommendation["legacyPythonArgumentsUsed"])
            self.assertFalse(recommendation["substitutePrimaryEligible"])

    def test_missing_native_runtime_allows_only_a_declared_fallback_primary(self) -> None:
        from scirepro.scripts.probe_environment import native_route_recommendation

        artifacts = [{"path": "$WORKSPACE/target_method.m", "suffix": ".m", "exists": True}]
        undeclared = native_route_recommendation(
            artifacts,
            [],
            author_native_runtime="matlab",
        )
        self.assertEqual(undeclared["nativeRuntimeStatus"], "missing")
        self.assertEqual(undeclared["recommendedRouteKind"], "native-runtime-missing")
        self.assertIsNone(undeclared["recommendedRuntime"])
        self.assertFalse(undeclared["pythonPrimaryEligible"])

        declared = native_route_recommendation(
            artifacts,
            [],
            "Reimplement the target-relevant method because its native runtime is unavailable.",
            "fallback-primary",
            author_native_runtime="matlab",
            substitute_runtime="python",
        )
        self.assertEqual(declared["recommendedRuntime"], "python")
        self.assertEqual(declared["recommendedRouteKind"], "declared-fallback")
        self.assertEqual(declared["nextAction"], "execute-declared-fallback")
        self.assertTrue(declared["pythonPrimaryEligible"])

    def test_portability_objective_can_select_julia_before_matlab_failure(self) -> None:
        from scirepro.scripts.probe_environment import native_route_recommendation

        artifacts = [{"path": "$WORKSPACE/target_method.m", "suffix": ".m", "exists": True}]
        available_native = [{
            "explicitSelection": True,
            "verificationStatus": "available",
            "runtimeVerified": False,
            "routeSmokeTested": False,
            "routeCapabilityVerified": False,
        }]
        recommendation = native_route_recommendation(
            artifacts,
            available_native,
            "The requested deliverable must run on systems without the proprietary native engine.",
            "portability-primary",
            author_native_runtime="matlab",
            substitute_runtime="julia",
        )
        self.assertEqual(recommendation["nativeRuntimeStatus"], "available")
        self.assertEqual(recommendation["recommendedRuntime"], "julia")
        self.assertEqual(recommendation["recommendedRouteKind"], "declared-substitute")
        self.assertEqual(recommendation["nextAction"], "execute-declared-substitute")
        self.assertTrue(recommendation["substitutePrimaryEligible"])
        self.assertFalse(recommendation["pythonPrimaryEligible"])
        self.assertEqual(recommendation["substituteRuntime"], "julia")
        self.assertFalse(recommendation["nativeRouteRejected"])

    def test_substitute_declaration_rejects_blank_multiline_secret_or_same_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            cases = (
                ("   ", "non-empty"),
                ("first line\nsecond line", "single line"),
                ("API_KEY=do-not-persist", "secret-shaped"),
                ("ghp_abcdefghijklmnopqrstuvwxyz1234", "secret-shaped"),
                ("sk-abcdefghijklmnopqrstuvwxyz123456", "secret-shaped"),
                ("AKIAABCDEFGHIJKLMNOP", "secret-shaped"),
                ("xoxb-abcdefghijklmnopqrstuvwxyz1234", "secret-shaped"),
                ("eyJabcdefghijk.eyJabcdefghijk.eyJabcdefghijk", "secret-shaped"),
                ("-----BEGIN RSA PRIVATE KEY-----", "secret-shaped"),
            )
            for reason, expected in cases:
                with self.subTest(reason=reason):
                    completed = self.run_probe(
                        workspace,
                        "--author-native-runtime", "matlab",
                        "--substitute-runtime", "julia",
                        "--substitute-role", "portability-primary",
                        "--substitute-reason", reason,
                        home=root,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn(expected, completed.stderr)

            same_runtime = self.run_probe(
                workspace,
                "--author-native-runtime", "julia",
                "--substitute-runtime", "julia",
                "--substitute-role", "independent-primary",
                "--substitute-reason", "Use a separately derived implementation.",
                home=root,
            )
            self.assertEqual(same_runtime.returncode, 2)
            self.assertIn("must differ", same_runtime.stderr)

    def test_matlab_function_requirement_rejects_code_injection_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            _, matlab = self.make_matlab_installation(root, "#!/bin/sh\nexit 0\n")

            completed = self.run_probe(
                workspace,
                "--matlab-executable",
                str(matlab),
                "--matlab-required-function",
                "target_method;system('touch injected')",
                home=root,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("invalid --matlab-required-function", completed.stderr)

    def test_matlab_license_feature_requirement_rejects_non_identifier_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            _, matlab = self.make_matlab_installation(root, "#!/bin/sh\nexit 0\n")

            completed = self.run_probe(
                workspace,
                "--matlab-executable",
                str(matlab),
                "--matlab-required-license-feature",
                "Signal Toolbox;system",
                home=root,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("invalid --matlab-required-license-feature", completed.stderr)

    def test_matlab_live_probe_flag_is_the_single_bounded_launch_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            sentinel = root / "matlab-started.txt"
            payload = {
                "release": "R2025a",
                "version": "25.1.0",
                "requiredToolboxes": [
                    {"name": "Signal Processing Toolbox", "installed": True, "version": "25.1"},
                ],
                "requiredLicenseFeatures": [
                    {"feature": "Signal_Toolbox", "available": True},
                ],
                "requiredFunctions": [{"name": "hilbert", "existCode": 2, "exists": True}],
                "entrypoint": {
                    "path": str(workspace / "target_entrypoint.m"),
                    "exists": True,
                },
            }
            _, matlab = self.make_matlab_installation(
                root,
                "#!/bin/sh\n"
                f"printf started > {shlex.quote(str(sentinel))}\n"
                "printf '%5000s\\n' warning\n"
                f"printf '%s\\n' {shlex.quote('SCIREPRO_MATLAB_PROBE_JSON:' + json.dumps(payload))}\n",
            )
            for name in ("target_method.m", "target_entrypoint.m", "target_input.mat"):
                (workspace / name).write_text("fixture\n", encoding="utf-8")

            completed = self.run_probe(
                workspace,
                "--matlab-executable",
                str(matlab),
                "--author-native-runtime",
                "matlab",
                "--matlab-live-probe",
                "--matlab-required-toolbox",
                "Signal Processing Toolbox",
                "--matlab-required-license-feature",
                "Signal_Toolbox",
                "--matlab-required-function",
                "hilbert",
                "--matlab-entrypoint",
                str(workspace / "target_entrypoint.m"),
                "--author-artifact",
                str(workspace / "target_method.m"),
                "--author-artifact",
                str(workspace / "target_entrypoint.m"),
                "--author-artifact",
                str(workspace / "target_input.mat"),
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(sentinel.exists(), "--matlab-live-probe is already the explicit launch action")
            self.assertNotIn(str(root), completed.stdout)
            report = json.loads(completed.stdout)
            self.assertIn(
                {
                    "ecosystem": "MATLAB-toolbox",
                    "name": "Signal Processing Toolbox",
                    "version": "25.1",
                },
                report["packages"],
            )
            entry = next(item for item in report["matlab"] if item["explicitSelection"])
            self.assertEqual(entry["release"], "R2025a")
            self.assertEqual(entry["verificationStatus"], "prerequisites-present")
            self.assertTrue(entry["runtimeVerified"])
            self.assertTrue(entry["baseLicenseStartupVerified"])
            self.assertTrue(entry["requiredToolboxInstallationsVerified"])
            self.assertTrue(entry["requiredLicenseFeaturesVerified"])
            self.assertTrue(entry["requiredFunctionsVerified"])
            self.assertTrue(entry["entrypointVerified"])
            self.assertTrue(entry["prerequisitesPresent"])
            self.assertFalse(entry["routeSmokeTested"])
            self.assertFalse(entry["routeCapabilityVerified"])
            self.assertNotIn("'toolboxes',tb", entry["liveProbe"]["command"][-1])
            self.assertEqual(
                entry["routeRequirements"]["entrypoint"],
                "$WORKSPACE/target_entrypoint.m",
            )
            recommendation = report["routeRecommendation"]
            self.assertEqual(recommendation["authorNativeRuntime"], "matlab")
            self.assertEqual(recommendation["recommendedRuntime"], "matlab")
            self.assertEqual(recommendation["pythonRole"], "fallback-or-cross-check")
            self.assertFalse(recommendation["pythonFallbackEligible"])
            self.assertFalse(recommendation["pythonPrimaryEligible"])
            self.assertEqual(recommendation["nativeRouteCapabilityStatus"], "prerequisites-present")
            self.assertEqual(recommendation["nextAction"], "run-reviewed-native-smoke")
            self.assertFalse(recommendation["decisionRequired"])

    def test_explicit_matlab_application_live_probe_verifies_prerequisites_not_route(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            source_directory = workspace / "nested" / "author's source"
            source_directory.mkdir(parents=True)
            entrypoint = source_directory / "target_entrypoint.m"
            entrypoint.write_text("fixture\n", encoding="utf-8")
            method = source_directory / "target_method.m"
            method.write_text("fixture\n", encoding="utf-8")
            data = workspace / "target_input.mat"
            data.write_bytes(b"fixture")
            expression_capture = root / "matlab-expression.txt"
            working_directory_capture = root / "matlab-working-directory.txt"
            shadow_sentinel = root / "author-ver-ran.txt"
            (source_directory / "ver.m").write_text(
                f"fid=fopen('{shadow_sentinel}','w'); fclose(fid);\n",
                encoding="utf-8",
            )
            payload = {
                "release": "2025a",
                "version": "25.1.0",
                "toolboxes": [
                    {"name": "MATLAB", "version": "25.1"},
                    {"name": "Signal Processing Toolbox", "version": "25.1"},
                ],
                "requiredFunctions": [{"name": "hilbert", "existCode": 2, "exists": True}],
                "requiredLicenseFeatures": [
                    {"feature": "Signal_Toolbox", "available": True},
                ],
                "entrypoint": {"path": str(entrypoint), "exists": True},
            }
            application, matlab = self.make_matlab_installation(
                root,
                "#!/bin/sh\n"
                f"printf '%s' \"$2\" > {shlex.quote(str(expression_capture))}\n"
                f"pwd > {shlex.quote(str(working_directory_capture))}\n"
                f"case \"$2\" in *{shlex.quote(str(source_directory))}*) "
                f"touch {shlex.quote(str(shadow_sentinel))};; esac\n"
                f"printf '%s\\n' {shlex.quote('SCIREPRO_MATLAB_PROBE_JSON:' + json.dumps(payload))}\n",
            )

            completed = self.run_probe(
                workspace,
                "--matlab-application",
                str(application),
                "--author-native-runtime",
                "matlab",
                "--matlab-live-probe",
                "--matlab-required-toolbox",
                "Signal Processing Toolbox",
                "--matlab-required-license-feature",
                "Signal_Toolbox",
                "--matlab-required-function",
                "hilbert",
                "--matlab-entrypoint",
                str(entrypoint),
                "--author-artifact",
                str(method),
                "--author-artifact",
                str(data),
                "--substitute-runtime",
                "python",
                "--substitute-reason",
                "Independent cross-check of the reported trend only.",
                "--substitute-role",
                "cross-check",
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn(str(root), completed.stdout)
            report = json.loads(completed.stdout)
            self.assertEqual(report["schemaVersion"], "scirepro.environment/v2")
            self.assertEqual(report["captureStatus"], "recorded")
            self.assertEqual(report["engines"][0]["name"], "MATLAB")
            self.assertEqual(report["engines"][0]["version"], "R2025a")
            self.assertTrue(
                any(item["name"] == "Signal Processing Toolbox" for item in report["packages"])
            )
            entry = next(item for item in report["matlab"] if item["explicitSelection"])
            self.assertEqual(entry["selectionKind"], "application")
            self.assertEqual(entry["verificationStatus"], "prerequisites-present")
            self.assertTrue(entry["runtimeVerified"])
            self.assertTrue(entry["baseLicenseStartupVerified"])
            self.assertTrue(entry["requiredToolboxInstallationsVerified"])
            self.assertTrue(entry["requiredLicenseFeaturesVerified"])
            self.assertTrue(entry["requiredFunctionsVerified"])
            self.assertTrue(entry["entrypointVerified"])
            self.assertTrue(entry["prerequisitesPresent"])
            self.assertFalse(entry["routeCapabilityVerified"])
            self.assertFalse(entry["routeSmokeTested"])
            self.assertEqual(
                entry["details"]["entrypoint"]["path"],
                "$WORKSPACE/nested/author's source/target_entrypoint.m",
            )
            self.assertIn("-batch", entry["liveProbe"]["command"])
            self.assertEqual(
                entry["routeRequirements"]["searchDirectories"],
                ["$WORKSPACE/nested/author's source"],
            )
            self.assertEqual(
                entry["workingDirectoryPolicy"],
                "controlled-empty-temporary-directory",
            )
            probe_cwd = Path(working_directory_capture.read_text(encoding="utf-8").strip())
            self.assertNotEqual(probe_cwd, workspace)
            self.assertFalse(probe_cwd.exists(), "temporary probe directory must be cleaned")
            self.assertFalse(shadow_sentinel.exists(), "author ver.m must never enter prerequisite path")
            expression = expression_capture.read_text(encoding="utf-8")
            self.assertIn("p0=path;pc=onCleanup(@()path(p0));restoredefaultpath;", expression)
            self.assertNotIn("addpath(", expression)
            self.assertNotIn(str(source_directory), expression)
            self.assertIn("[2,3,6]", expression)
            self.assertNotIn("genpath", expression)
            self.assertNotIn("run(", expression)
            self.assertEqual(report["privacy"]["explicitMatlabLiveProbeCount"], 1)
            recommendation = report["routeRecommendation"]
            self.assertEqual(recommendation["recommendedRouteKind"], "author-native")
            self.assertEqual(recommendation["recommendedRuntime"], "matlab")
            self.assertEqual(recommendation["nativeRouteCapabilityStatus"], "prerequisites-present")
            self.assertEqual(recommendation["nextAction"], "run-reviewed-native-smoke")
            self.assertEqual(recommendation["pythonRole"], "cross-check")
            self.assertTrue(recommendation["pythonFallbackEligible"])
            self.assertFalse(recommendation["pythonPrimaryEligible"])
            self.assertEqual(
                recommendation["pythonFallbackReason"],
                "Independent cross-check of the reported trend only.",
            )

    def test_matlab_live_probe_reports_missing_route_function_without_downgrading_to_python(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            method = workspace / "target_method.m"
            method.write_text("fixture\n", encoding="utf-8")
            payload = {
                "release": "R2025a",
                "version": "25.1.0",
                "toolboxes": [{"name": "MATLAB", "version": "25.1"}],
                # MATLAB exist(..., 'file') code 7 means a directory, never a route function.
                "requiredFunctions": [{"name": "missing_toolbox_function", "existCode": 7, "exists": True}],
                "entrypoint": {"path": "", "exists": True},
            }
            _, matlab = self.make_matlab_installation(
                root,
                "#!/bin/sh\n"
                f"printf '%s\\n' 'SCIREPRO_MATLAB_PROBE_JSON:{json.dumps(payload)}'\n",
            )

            completed = self.run_probe(
                workspace,
                "--matlab-executable",
                str(matlab),
                "--author-native-runtime",
                "matlab",
                "--matlab-live-probe",
                "--matlab-required-function",
                "missing_toolbox_function",
                "--author-artifact",
                str(method),
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            entry = next(item for item in report["matlab"] if item["explicitSelection"])
            self.assertTrue(entry["runtimeVerified"])
            self.assertFalse(entry["requiredFunctionsVerified"])
            self.assertEqual(entry["verificationStatus"], "failed")
            self.assertEqual(entry["failureReason"], "route-required-capability-missing")
            recommendation = report["routeRecommendation"]
            self.assertIsNone(recommendation["recommendedRuntime"])
            self.assertEqual(recommendation["recommendedRouteKind"], "blocked-native-capability")
            self.assertFalse(recommendation["pythonPrimaryEligible"])

            with_fallback = self.run_probe(
                workspace,
                "--matlab-executable",
                str(matlab),
                "--author-native-runtime",
                "matlab",
                "--matlab-live-probe",
                "--matlab-required-function",
                "missing_toolbox_function",
                "--author-artifact",
                str(method),
                "--substitute-runtime",
                "python",
                "--substitute-reason",
                "Reimplement the target equation after the native capability was shown unavailable.",
                "--substitute-role",
                "fallback-primary",
                home=root,
            )
            self.assertEqual(with_fallback.returncode, 0, with_fallback.stderr)
            fallback_report = json.loads(with_fallback.stdout)
            fallback = fallback_report["routeRecommendation"]
            self.assertEqual(fallback["recommendedRuntime"], "python")
            self.assertEqual(fallback["recommendedRouteKind"], "declared-fallback")
            self.assertTrue(fallback["pythonPrimaryEligible"])

    def test_installed_toolbox_without_required_license_is_not_route_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            method = workspace / "target_method.m"
            method.write_text("fixture\n", encoding="utf-8")
            payload = {
                "release": "R2025a",
                "version": "25.1.0",
                "toolboxes": [
                    {"name": "MATLAB", "version": "25.1"},
                    {"name": "Signal Processing Toolbox", "version": "25.1"},
                ],
                "requiredLicenseFeatures": [
                    {"feature": "Signal_Toolbox", "available": False},
                ],
                "requiredFunctions": [{"name": "hilbert", "existCode": 2, "exists": True}],
                "entrypoint": {"path": "", "exists": True},
            }
            _, matlab = self.make_matlab_installation(
                root,
                "#!/bin/sh\n"
                f"printf '%s\\n' {shlex.quote('SCIREPRO_MATLAB_PROBE_JSON:' + json.dumps(payload))}\n",
            )

            completed = self.run_probe(
                workspace,
                "--matlab-executable",
                str(matlab),
                "--author-native-runtime",
                "matlab",
                "--matlab-live-probe",
                "--matlab-required-toolbox",
                "Signal Processing Toolbox",
                "--matlab-required-license-feature",
                "Signal_Toolbox",
                "--matlab-required-function",
                "hilbert",
                "--author-artifact",
                str(method),
                home=root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            entry = next(item for item in report["matlab"] if item["explicitSelection"])
            self.assertTrue(entry["runtimeVerified"])
            self.assertTrue(entry["requiredToolboxInstallationsVerified"])
            self.assertFalse(entry["requiredLicenseFeaturesVerified"])
            self.assertFalse(entry["prerequisitesPresent"])
            self.assertFalse(entry["routeCapabilityVerified"])
            self.assertEqual(entry["failureReason"], "route-required-capability-missing")
            recommendation = report["routeRecommendation"]
            self.assertEqual(recommendation["nativeRouteCapabilityStatus"], "missing")
            self.assertEqual(recommendation["recommendedRouteKind"], "blocked-native-capability")
            self.assertFalse(recommendation["pythonPrimaryEligible"])

    def test_matlab_live_probe_failures_are_inconclusive_or_declared_fallback(self) -> None:
        scenarios = {
            "command-failed": ("#!/bin/sh\nexit 17\n", "probe-command-failed"),
            "output-invalid": ("#!/bin/sh\nprintf 'not-a-probe-marker\\n'\n", "probe-output-invalid"),
            "timed-out": ("#!/bin/sh\nsleep 2\n", "probe-timed-out"),
        }
        for scenario, (body, failure_reason) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workspace = root / "workspace"
                workspace.mkdir()
                method = workspace / "target_method.m"
                method.write_text("fixture\n", encoding="utf-8")
                _, matlab = self.make_matlab_installation(root, body)

                arguments = (
                    "--matlab-executable", str(matlab),
                    "--author-native-runtime", "matlab",
                    "--matlab-live-probe",
                    "--matlab-required-function", "hilbert",
                    "--author-artifact", str(method),
                    "--timeout", "1" if scenario == "timed-out" else "5",
                )
                completed = self.run_probe(workspace, *arguments, home=root)

                self.assertEqual(completed.returncode, 0, completed.stderr)
                report = json.loads(completed.stdout)
                entry = next(item for item in report["matlab"] if item["explicitSelection"])
                self.assertEqual(entry["verificationStatus"], "failed")
                self.assertEqual(entry["failureReason"], failure_reason)
                recommendation = report["routeRecommendation"]
                self.assertEqual(recommendation["nativeRuntimeStatus"], "failed")
                self.assertEqual(
                    recommendation["nativeRouteCapabilityStatus"],
                    "inconclusive",
                )
                self.assertIsNone(recommendation["recommendedRuntime"])
                self.assertEqual(
                    recommendation["recommendedRouteKind"],
                    "native-probe-inconclusive",
                )
                self.assertFalse(recommendation["nativePriorityApplied"])
                self.assertTrue(recommendation["nativeRouteRejected"])
                self.assertFalse(recommendation["pythonPrimaryEligible"])
                self.assertTrue(recommendation["decisionRequired"])

                if scenario == "command-failed":
                    with_fallback = self.run_probe(
                        workspace,
                        *arguments,
                        "--substitute-runtime", "python",
                        "--substitute-reason",
                        "Reimplement only the target-dependent equation and record the changed evidence boundary.",
                        "--substitute-role", "fallback-primary",
                        home=root,
                    )
                    self.assertEqual(with_fallback.returncode, 0, with_fallback.stderr)
                    fallback = json.loads(with_fallback.stdout)["routeRecommendation"]
                    self.assertEqual(fallback["nativeRuntimeStatus"], "failed")
                    self.assertEqual(fallback["nativeRouteCapabilityStatus"], "inconclusive")
                    self.assertEqual(fallback["recommendedRuntime"], "python")
                    self.assertEqual(fallback["recommendedRouteKind"], "declared-fallback")
                    self.assertTrue(fallback["pythonPrimaryEligible"])
                    self.assertFalse(fallback["decisionRequired"])

    def test_matlab_live_probe_redacts_external_route_paths_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            home = root / "unrelated-home"
            home.mkdir()
            source_directory = root / "external-private-project" / "author's source"
            source_directory.mkdir(parents=True)
            entrypoint = source_directory / "target_entrypoint.m"
            entrypoint.write_text("fixture\n", encoding="utf-8")
            method = source_directory / "target_method.m"
            method.write_text("fixture\n", encoding="utf-8")
            payload = {
                "release": "R2025a",
                "version": "25.1.0",
                "toolboxes": [{"name": "MATLAB", "version": "25.1"}],
                "requiredFunctions": [{"name": "hilbert", "existCode": 2, "exists": True}],
                "entrypoint": {"path": str(entrypoint), "exists": True},
            }
            _, matlab = self.make_matlab_installation(
                root / "runtime-install",
                "#!/bin/sh\n"
                f"printf '%s\\n' {shlex.quote('diagnostic at ' + str(entrypoint))} >&2\n"
                f"printf '%s\\n' {shlex.quote('SCIREPRO_MATLAB_PROBE_JSON:' + json.dumps(payload))}\n",
            )

            completed = self.run_probe(
                workspace,
                "--matlab-executable", str(matlab),
                "--author-native-runtime", "matlab",
                "--matlab-live-probe",
                "--matlab-required-function", "hilbert",
                "--matlab-entrypoint", str(entrypoint),
                "--author-artifact", str(method),
                home=home,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn(str(root), completed.stdout)
            self.assertNotIn(str(source_directory), completed.stdout)
            self.assertNotIn(str(entrypoint), completed.stdout)
            report = json.loads(completed.stdout)
            self.assertTrue(report["privacy"]["pathsRedacted"])
            entry = next(item for item in report["matlab"] if item["explicitSelection"])
            self.assertEqual(
                entry["routeRequirements"]["entrypoint"],
                "$SYSTEM/target_entrypoint.m",
            )
            self.assertEqual(
                entry["routeRequirements"]["searchDirectories"],
                ["$SYSTEM/author's source"],
            )
            self.assertEqual(
                entry["details"]["entrypoint"]["path"],
                "$SYSTEM/target_entrypoint.m",
            )
            persisted_probe = json.dumps(entry["liveProbe"], ensure_ascii=False)
            self.assertNotIn(str(root), persisted_probe)
            self.assertIn("$SYSTEM", persisted_probe)

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
