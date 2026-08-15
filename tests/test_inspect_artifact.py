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
SCRIPT = REPO / "scirepro" / "scripts" / "inspect_artifact.py"


class InspectArtifactTests(unittest.TestCase):
    def run_inspector(self, artifact: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(artifact), *arguments],
            cwd=REPO,
            text=True,
            capture_output=True,
            timeout=10,
        )

    def test_regular_file_is_hashed_without_exposing_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "input.txt"
            artifact.write_text("scientific input\n", encoding="utf-8")

            completed = self.run_inspector(artifact)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn(temporary, completed.stdout)
            report = json.loads(completed.stdout)
            self.assertEqual(report["schemaVersion"], "scirepro.artifact/v2")
            self.assertEqual(report["type"], "file")
            self.assertRegex(report["sha256"], r"^[0-9a-f]{64}$")

    def test_output_is_create_only_and_does_not_follow_leaf_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "input.txt"
            artifact.write_text("input\n", encoding="utf-8")
            existing = root / "existing.json"
            existing.write_text("sentinel\n", encoding="utf-8")

            overwrite = self.run_inspector(artifact, "--output", str(existing))
            self.assertEqual(overwrite.returncode, 2)
            self.assertEqual(existing.read_text(encoding="utf-8"), "sentinel\n")

            target = root / "target.json"
            target.write_text("target sentinel\n", encoding="utf-8")
            linked = root / "linked.json"
            linked.symlink_to(target)
            through_link = self.run_inspector(artifact, "--output", str(linked))
            self.assertEqual(through_link.returncode, 2)
            self.assertEqual(target.read_text(encoding="utf-8"), "target sentinel\n")

    def test_root_symlink_is_reported_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "private.txt"
            target.write_text("do not hash through link\n", encoding="utf-8")
            link = root / "artifact-link"
            link.symlink_to(target)

            completed = self.run_inspector(link)

            self.assertEqual(completed.returncode, 2, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["type"], "symlink")
            self.assertTrue(report["symlink"])
            self.assertNotIn("sha256", report)
            self.assertTrue(report["inventory"]["suspiciousEntries"])

    def test_sensitive_root_symlink_name_is_never_echoed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "safe.txt"
            target.write_text("safe\n", encoding="utf-8")
            link = root / "API_KEY=supersecretvalue"
            link.symlink_to(target)

            completed = self.run_inspector(link)

            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertNotIn("supersecretvalue", completed.stdout)
            report = json.loads(completed.stdout)
            self.assertEqual(report["name"], "$REDACTED_SENSITIVE_NAME")
            self.assertEqual(
                report["inventory"]["suspiciousEntries"][0]["name"],
                "$REDACTED_SENSITIVE_NAME",
            )

    def test_sensitive_regular_root_name_is_redacted_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / ".env"
            artifact.write_text("scientific fixture without credentials\n", encoding="utf-8")

            completed = self.run_inspector(artifact)

            self.assertEqual(completed.returncode, 2, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["name"], "$REDACTED_SENSITIVE_NAME")
            self.assertTrue(report["sensitiveName"])

    def test_artifact_path_may_not_traverse_a_user_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            (real / "artifact.txt").write_text("private\n", encoding="utf-8")
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)

            completed = self.run_inspector(linked / "artifact.txt")

            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, "")
            self.assertIn("symlink components", completed.stderr)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO creation is unavailable")
    def test_directory_fifo_and_symlink_are_suspicious(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"
            root.mkdir()
            (root / "regular.txt").write_text("ok\n", encoding="utf-8")
            outside = Path(temporary) / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            (root / "linked.txt").symlink_to(outside)
            os.mkfifo(root / "stream.pipe")

            completed = self.run_inspector(root)

            self.assertEqual(completed.returncode, 2, completed.stderr)
            report = json.loads(completed.stdout)
            names = {item["name"] for item in report["inventory"]["suspiciousEntries"]}
            self.assertEqual(names, {"linked.txt", "stream.pipe"})
            entries = report["inventory"]["entries"]
            self.assertEqual([item["name"] for item in entries], ["regular.txt"])

    def test_archive_safety_scans_beyond_display_limit_and_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "inputs.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("safe.txt", "safe")
                archive.writestr("../../escape.txt", "unsafe")
                secret = zipfile.ZipInfo("payload/API_KEY=supersecretvalue.txt")
                secret.create_system = 3
                secret.external_attr = (0o100644 << 16)
                archive.writestr(secret, "metadata")
                fifo = zipfile.ZipInfo("stream.pipe")
                fifo.create_system = 3
                fifo.external_attr = ((0o010000 | 0o644) << 16)
                archive.writestr(fifo, "")

            completed = self.run_inspector(archive_path, "--max-entries", "1")

            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertNotIn("supersecretvalue", completed.stdout)
            report = json.loads(completed.stdout)
            inventory = report["inventory"]
            self.assertTrue(inventory["truncated"])
            self.assertEqual(len(inventory["entries"]), 1)
            self.assertEqual(inventory["suspiciousEntryCount"], 3)
            self.assertTrue(inventory["suspiciousEntries"])

    def test_directory_sensitive_name_is_redacted_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "tree"
            root.mkdir()
            (root / "API_KEY=supersecretvalue.txt").write_text("metadata\n", encoding="utf-8")

            completed = self.run_inspector(root)

            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertNotIn("supersecretvalue", completed.stdout)
            report = json.loads(completed.stdout)
            self.assertEqual(
                report["inventory"]["entries"][0]["name"],
                "$REDACTED_SENSITIVE_NAME",
            )


if __name__ == "__main__":
    unittest.main()
