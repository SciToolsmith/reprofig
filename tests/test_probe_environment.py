from __future__ import annotations

import json
import os
import shlex
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

    def test_exact_matlab_static_selection_is_available_not_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            sentinel = root / "matlab-started.txt"
            matlab = root / "MATLAB_R2025a" / "bin" / "matlab"
            self.make_executable(
                matlab,
                f"#!/bin/sh\nprintf started > {sentinel}\nexit 0\n",
            )

            completed = self.run_probe(
                workspace,
                "--matlab-executable",
                str(matlab),
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

    def test_matlab_function_requirement_rejects_code_injection_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            matlab = root / "MATLAB_R2025a" / "bin" / "matlab"
            self.make_executable(matlab, "#!/bin/sh\nexit 0\n")

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

    def test_matlab_live_probe_stops_for_startup_license_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            sentinel = root / "matlab-started.txt"
            matlab = root / "MATLAB_R2025a" / "bin" / "matlab"
            self.make_executable(
                matlab,
                f"#!/bin/sh\nprintf started > {sentinel}\nexit 0\n",
            )
            for name in ("target_method.m", "target_entrypoint.m", "target_input.mat"):
                (workspace / name).write_text("fixture\n", encoding="utf-8")

            completed = self.run_probe(
                workspace,
                "--matlab-executable",
                str(matlab),
                "--matlab-live-probe",
                "--matlab-required-toolbox",
                "Signal Processing Toolbox",
                "--matlab-required-function",
                "target_method",
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
            self.assertFalse(sentinel.exists(), "MATLAB must not start before the separate risk opt-in")
            self.assertNotIn(str(root), completed.stdout)
            report = json.loads(completed.stdout)
            entry = next(item for item in report["matlab"] if item["explicitSelection"])
            self.assertEqual(entry["release"], "R2025a")
            self.assertEqual(entry["verificationStatus"], "needs-user-decision")
            self.assertFalse(entry["runtimeVerified"])
            self.assertEqual(entry["decision"]["status"], "needs-user-decision")
            self.assertEqual(
                entry["decision"]["optInFlag"],
                "--allow-matlab-startup-license-risk",
            )
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
            self.assertTrue(recommendation["decisionRequired"])

    def test_explicit_matlab_application_live_probe_verifies_route_capabilities(self) -> None:
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
            application = root / "MATLAB_R2025a.app"
            matlab = application / "bin" / "matlab"
            expression_capture = root / "matlab-expression.txt"
            payload = {
                "release": "2025a",
                "version": "25.1.0",
                "toolboxes": [
                    {"name": "MATLAB", "version": "25.1"},
                    {"name": "Signal Processing Toolbox", "version": "25.1"},
                ],
                "requiredFunctions": [{"name": "target_method", "exists": True}],
                "entrypoint": {"path": str(entrypoint), "exists": True},
            }
            self.make_executable(
                matlab,
                "#!/bin/sh\n"
                f"printf '%s' \"$2\" > {shlex.quote(str(expression_capture))}\n"
                f"printf '%s\\n' {shlex.quote('SCIREPRO_MATLAB_PROBE_JSON:' + json.dumps(payload))}\n",
            )

            completed = self.run_probe(
                workspace,
                "--matlab-application",
                str(application),
                "--matlab-live-probe",
                "--allow-matlab-startup-license-risk",
                "--matlab-required-toolbox",
                "Signal Processing Toolbox",
                "--matlab-required-function",
                "target_method",
                "--matlab-entrypoint",
                str(entrypoint),
                "--author-artifact",
                str(method),
                "--author-artifact",
                str(data),
                "--python-fallback-reason",
                "Independent cross-check of the reported trend only.",
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
            self.assertEqual(entry["verificationStatus"], "verified")
            self.assertTrue(entry["runtimeVerified"])
            self.assertTrue(entry["baseLicenseStartupVerified"])
            self.assertTrue(entry["requiredToolboxInstallationsVerified"])
            self.assertTrue(entry["requiredFunctionsVerified"])
            self.assertTrue(entry["entrypointVerified"])
            self.assertTrue(entry["routeCapabilityVerified"])
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
            expression = expression_capture.read_text(encoding="utf-8")
            matlab_literal = str(source_directory).replace("'", "''")
            self.assertIn("p0=path;pc=onCleanup(@()path(p0));", expression)
            self.assertIn(f"addpath('{matlab_literal}','-begin');", expression)
            self.assertEqual(expression.count("addpath("), 1, "route directories must be de-duplicated")
            self.assertNotIn("genpath", expression)
            self.assertNotIn("run(", expression)
            self.assertEqual(report["privacy"]["explicitMatlabLiveProbeCount"], 1)
            recommendation = report["routeRecommendation"]
            self.assertEqual(recommendation["recommendedRouteKind"], "author-native")
            self.assertEqual(recommendation["recommendedRuntime"], "matlab")
            self.assertEqual(recommendation["pythonRole"], "fallback-or-cross-check")
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
            matlab = root / "MATLAB_R2025a" / "bin" / "matlab"
            payload = {
                "release": "R2025a",
                "version": "25.1.0",
                "toolboxes": [{"name": "MATLAB", "version": "25.1"}],
                "requiredFunctions": [{"name": "target_method", "exists": False}],
                "entrypoint": {"path": "", "exists": True},
            }
            self.make_executable(
                matlab,
                "#!/bin/sh\n"
                f"printf '%s\\n' 'SCIREPRO_MATLAB_PROBE_JSON:{json.dumps(payload)}'\n",
            )

            completed = self.run_probe(
                workspace,
                "--matlab-executable",
                str(matlab),
                "--matlab-live-probe",
                "--allow-matlab-startup-license-risk",
                "--matlab-required-function",
                "target_method",
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
                "--matlab-live-probe",
                "--allow-matlab-startup-license-risk",
                "--matlab-required-function",
                "target_method",
                "--author-artifact",
                str(method),
                "--python-fallback-reason",
                "Reimplement the target equation after the native capability was shown unavailable.",
                home=root,
            )
            self.assertEqual(with_fallback.returncode, 0, with_fallback.stderr)
            fallback_report = json.loads(with_fallback.stdout)
            fallback = fallback_report["routeRecommendation"]
            self.assertEqual(fallback["recommendedRuntime"], "python")
            self.assertEqual(fallback["recommendedRouteKind"], "declared-fallback")
            self.assertTrue(fallback["pythonPrimaryEligible"])

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
                matlab = root / "MATLAB_R2025a" / "bin" / "matlab"
                self.make_executable(matlab, body)

                arguments = (
                    "--matlab-executable", str(matlab),
                    "--matlab-live-probe",
                    "--allow-matlab-startup-license-risk",
                    "--matlab-required-function", "target_method",
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
                        "--python-fallback-reason",
                        "Reimplement only the target-dependent equation and record the changed evidence boundary.",
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
            matlab = root / "runtime-install" / "MATLAB_R2025a" / "bin" / "matlab"
            payload = {
                "release": "R2025a",
                "version": "25.1.0",
                "toolboxes": [{"name": "MATLAB", "version": "25.1"}],
                "requiredFunctions": [{"name": "target_method", "exists": True}],
                "entrypoint": {"path": str(entrypoint), "exists": True},
            }
            self.make_executable(
                matlab,
                "#!/bin/sh\n"
                f"printf '%s\\n' {shlex.quote('diagnostic at ' + str(entrypoint))} >&2\n"
                f"printf '%s\\n' {shlex.quote('SCIREPRO_MATLAB_PROBE_JSON:' + json.dumps(payload))}\n",
            )

            completed = self.run_probe(
                workspace,
                "--matlab-executable", str(matlab),
                "--matlab-live-probe",
                "--allow-matlab-startup-license-risk",
                "--matlab-required-function", "target_method",
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
