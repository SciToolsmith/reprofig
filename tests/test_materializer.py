from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import pdfplumber  # noqa: F401
    from PIL import Image
except ImportError:  # pragma: no cover - clean-install CI supplies these
    pdfplumber = None
    Image = None


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scirepro/scripts/materialize_target_figures.py"
AUTO_PDFTOPPM = next(
    (path for path in (Path("/opt/homebrew/bin/pdftoppm"), Path("/usr/local/bin/pdftoppm"), Path("/usr/bin/pdftoppm")) if path.exists()),
    None,
)


def pdf_object(number: int, body: bytes) -> bytes:
    return f"{number} 0 obj\n".encode() + body + b"\nendobj\n"


def write_two_column_pdf(path: Path) -> None:
    """Create two offline pages; page one has a wrapped two-column caption."""
    streams = [
        b"\n".join([
            b"0.8 w 70 300 m 70 520 l 285 520 l S",
            b"0 0 1 RG 2 w 75 495 m 125 455 l 180 410 l 245 340 l S",
            b"0 G BT /F1 9 Tf 70 248 Td (Fig. 1. First line of the target caption) Tj ET",
            b"BT /F1 9 Tf 70 236 Td (continues on a second line.) Tj ET",
            b"BT /F1 9 Tf 330 248 Td (Right column prose must stay out.) Tj ET",
            b"BT /F1 9 Tf 330 236 Td (It is unrelated to the figure.) Tj ET",
        ]),
        b"\n".join([
            b"0.8 w 70 300 m 70 520 l 285 520 l S",
            b"1 0 0 RG 2 w 75 480 m 130 430 l 185 390 l 245 330 l S",
            b"0 G BT /F1 9 Tf 70 248 Td (Fig. 2. Second quantitative target.) Tj ET",
        ]),
    ]
    page_numbers = [4, 6]
    objects = [
        pdf_object(1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        pdf_object(2, b"<< /Type /Pages /Kids [4 0 R 6 0 R] /Count 2 >>"),
        pdf_object(3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ]
    for page_number, stream in zip(page_numbers, streams):
        content_number = page_number + 1
        objects.append(pdf_object(
            page_number,
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>".encode(),
        ))
        objects.append(pdf_object(content_number, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
    objects.sort(key=lambda item: int(item.split(b" ", 1)[0]))
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(data))
        data.extend(obj)
    xref = len(data)
    data.extend(b"xref\n0 8\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(data)


def make_image(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (48, 32)) -> None:
    Image.new("RGB", size, color).save(path, format="PNG")


def run_materializer(*arguments: object, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(item) for item in arguments)],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
    )


@unittest.skipUnless(pdfplumber is not None and Image is not None, "materializer dependencies are required")
class MaterializerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paper = self.root / "paper.pdf"
        self.image_a = self.root / "a.png"
        self.image_b = self.root / "b.png"
        write_two_column_pdf(self.paper)
        make_image(self.image_a, (30, 90, 180))
        make_image(self.image_b, (180, 90, 30))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assert_ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_three_entry_paths_accept_multiple_targets_and_caption_stays_in_column(self) -> None:
        images_only = self.root / "images-only"
        result = run_materializer("--image", self.image_a, "--image", self.image_b, "--output", images_only)
        self.assert_ok(result)
        manifest = json.loads((images_only / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["targetCount"], 2)
        self.assertTrue(all(item["acquisitionMode"] == "images-only" for item in manifest["targets"]))

        paper_images = self.root / "paper-images"
        result = run_materializer(
            "--paper", self.paper, "--image", self.image_a, "--image", self.image_b,
            "--uploaded-figure-refs", "1,2", "--output", paper_images,
        )
        self.assert_ok(result)
        manifest = json.loads((paper_images / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([item["targetId"] for item in manifest["targets"]], ["fig-01", "fig-02"])
        self.assertTrue(all(item["acquisitionMode"] == "paper-with-images" for item in manifest["targets"]))

        if AUTO_PDFTOPPM is None:
            self.skipTest("trusted pdftoppm is required for PDF rendering")
        paper_refs = self.root / "paper-refs"
        result = run_materializer("--paper", self.paper, "--figures", "1,2", "--output", paper_refs)
        self.assert_ok(result)
        manifest = json.loads((paper_refs / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["targetCount"], 2)
        caption = manifest["targets"][0]["caption"]
        self.assertIn("continues on a second line", caption)
        self.assertNotIn("Right column", caption)
        self.assertEqual(manifest["resourcePreflight"]["kind"], "preflight-estimate-not-runtime-enforcement")

    def test_create_only_verify_subset_replace_and_bind(self) -> None:
        workspace = self.root / "lifecycle"
        self.assert_ok(run_materializer("--image", self.image_a, "--image", self.image_b, "--output", workspace))
        before = (workspace / "manifest.json").read_bytes()
        duplicate = run_materializer("--image", self.image_a, "--output", workspace)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertEqual((workspace / "manifest.json").read_bytes(), before)

        self.assert_ok(run_materializer("--verify-manifest", workspace / "manifest.json", "--verify-all"))
        subset = workspace / "verified.json"
        self.assert_ok(run_materializer(
            "--derive-subset-manifest", workspace / "manifest.json",
            "--subset-output", subset, "--subset-target-set-id", "verified-targets",
        ))
        self.assertEqual(json.loads(subset.read_text(encoding="utf-8"))["targetCount"], 2)

        replacement = self.root / "replacement.png"
        make_image(replacement, (20, 200, 80), (64, 40))
        self.assert_ok(run_materializer(
            "--replace-manifest", workspace / "manifest.json", "--replace-target", "image-001",
            "--replacement-image", replacement,
        ))
        replaced = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))["targets"][0]
        self.assertEqual(replaced["qaStatus"], "needs-review")
        self.assertEqual(len(replaced["provenanceHistory"]), 1)

        bound_workspace = self.root / "bound"
        self.assert_ok(run_materializer("--paper", self.paper, "--image", self.image_a, "--output", bound_workspace))
        self.assert_ok(run_materializer(
            "--bind-manifest", bound_workspace / "manifest.json", "--bind-target", "image-001",
            "--paper-figure-ref", "1",
        ))
        self.assert_ok(run_materializer(
            "--verify-manifest", bound_workspace / "manifest.json", "--verify-targets", "image-001",
        ))
        bound = json.loads((bound_workspace / "manifest.json").read_text(encoding="utf-8"))["targets"][0]
        self.assertEqual(bound["identityStatus"], "resolved")
        self.assertEqual(bound["workflowMode"], "scientific-reproduction")

    @unittest.skipUnless(AUTO_PDFTOPPM is not None, "trusted pdftoppm is required")
    def test_path_sentinel_is_ignored_and_explicit_untrusted_paths_are_rejected(self) -> None:
        sentinel_dir = self.root / "sentinel-bin"
        sentinel_dir.mkdir()
        marker = self.root / "path-was-executed"
        sentinel = sentinel_dir / "pdftoppm"
        sentinel.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 91\n", encoding="utf-8")
        sentinel.chmod(0o755)
        environment = dict(os.environ)
        environment["PATH"] = f"{sentinel_dir}:{environment.get('PATH', '')}"
        result = run_materializer(
            "--paper", self.paper, "--figures", "1", "--output", self.root / "safe-auto", env=environment,
        )
        self.assert_ok(result)
        self.assertFalse(marker.exists(), "the PATH-controlled renderer was executed")

        trusted = run_materializer(
            "--paper", self.paper, "--figures", "2", "--output", self.root / "safe-explicit",
            "--pdftoppm-executable", AUTO_PDFTOPPM.resolve(),
        )
        self.assert_ok(trusted)

        relative = run_materializer(
            "--paper", self.paper, "--figures", "1", "--output", self.root / "bad-relative",
            "--pdftoppm-executable", "pdftoppm",
        )
        self.assertNotEqual(relative.returncode, 0)
        self.assertIn("absolute path", relative.stderr)
        self.assertFalse((self.root / "bad-relative").exists())

        symlink = self.root / "pdftoppm-link"
        symlink.symlink_to(AUTO_PDFTOPPM.resolve())
        linked = run_materializer(
            "--paper", self.paper, "--figures", "1", "--output", self.root / "bad-link",
            "--pdftoppm-executable", symlink,
        )
        self.assertNotEqual(linked.returncode, 0)
        self.assertIn("not a symlink", linked.stderr)
        self.assertFalse((self.root / "bad-link").exists())

        workspace_binary = self.root / "tools" / "pdftoppm"
        workspace_binary.parent.mkdir()
        shutil.copy2(AUTO_PDFTOPPM.resolve(), workspace_binary)
        workspace_binary.chmod(0o755)
        untrusted = run_materializer(
            "--paper", self.paper, "--figures", "1", "--output", self.root / "bad-workspace",
            "--pdftoppm-executable", workspace_binary,
        )
        self.assertNotEqual(untrusted.returncode, 0)
        self.assertIn("task, input, or output tree", untrusted.stderr)
        self.assertFalse((self.root / "bad-workspace").exists())

    def test_aggregate_budget_failure_creates_no_output(self) -> None:
        output = self.root / "must-not-exist"
        result = run_materializer(
            "--image", self.image_a, "--image", self.image_b, "--output", output,
            "--max-output-bytes", "1",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inputs=", result.stderr)
        self.assertIn("estimated peak acquisition=", result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(any(path.name.startswith(".must-not-exist.staging-") for path in self.root.iterdir()))

        zero = run_materializer(
            "--image", self.image_a, "--output", self.root / "zero-budget", "--max-output-bytes", "0",
        )
        self.assertNotEqual(zero.returncode, 0)
        self.assertIn("positive integer", zero.stderr)
        self.assertFalse((self.root / "zero-budget").exists())


if __name__ == "__main__":
    unittest.main()
