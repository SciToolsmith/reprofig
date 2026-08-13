from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

try:
    import pdfplumber  # noqa: F401
    from PIL import Image
except ImportError:  # pragma: no cover - exercised by clean-install CI
    pdfplumber = None
    Image = None

from tests.fixture_factory import write_json
from tests.test_run_bundle import artifact_record, record_environment, record_resources, run_bundle


REPO = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO / "scirepro/scripts/materialize_target_figures.py"


def pdf_object(number: int, body: bytes) -> bytes:
    return f"{number} 0 obj\n".encode() + body + b"\nendobj\n"


def write_fixture_pdf(path: Path) -> None:
    """Write a one-page paper fixture with a quantitative plot and caption."""
    stream = b"\n".join([
        b"0.8 w 70 250 m 70 530 l 360 530 l S",
        b"0 0 1 RG 2 w 75 500 m 130 455 l 185 405 l 240 350 l 300 285 l S",
        b"0 G BT /F1 11 Tf 70 228 Td (Fig. 1. Linear response produced by the declared model.) Tj ET",
    ])
    objects = [
        pdf_object(1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        pdf_object(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        pdf_object(3, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"),
        pdf_object(4, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"),
        pdf_object(5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(data))
        data.extend(obj)
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(data)


def png_bytes(width: int = 640, height: int = 420) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + b"\xff\xff\xff" * width
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b"")


@unittest.skipUnless(pdfplumber is not None and Image is not None, "PDF acquisition dependencies are required")
class ScientificWorkflowE2ETests(unittest.TestCase):
    def test_paper_figure_to_v0_to_validated_single_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            paper = root / "paper.pdf"
            targets = root / "targets"
            write_fixture_pdf(paper)
            acquired = subprocess.run(
                [
                    sys.executable, str(MATERIALIZER), "--paper", str(paper),
                    "--figures", "1", "--output", str(targets), "--target-set-id", "fixture-paper",
                ],
                cwd=REPO, text=True, capture_output=True,
            )
            self.assertEqual(acquired.returncode, 0, acquired.stderr)
            manifest_path = targets / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["targetCount"], 1)
            self.assertEqual(manifest["targets"][0]["qaStatus"], "needs-review")
            verified = subprocess.run(
                [sys.executable, str(MATERIALIZER), "--verify-manifest", str(manifest_path), "--verify-all"],
                cwd=REPO, text=True, capture_output=True,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)

            initialized = run_bundle(
                "init", "--output-root", str(root), "--run-id", "paper-fig1",
                "--target-manifest", str(manifest_path), "--json",
            )
            staging = Path(json.loads(initialized.stdout)["path"])
            result_path = staging / "targets/fig-01/result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            input_path = "targets/fig-01/inputs/samples.csv"
            code_path = "targets/fig-01/code/reproduce.py"
            config_path = "targets/fig-01/config/run.json"
            v0_path = "targets/fig-01/outputs/baseline-v0.png"
            for relative, payload in (
                (input_path, "x,y\n0,0\n1,1\n"),
                (code_path, "# deterministic fixture\n"),
                (config_path, '{"model":"linear"}\n'),
            ):
                path = staging / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")
            (staging / v0_path).parent.mkdir(parents=True, exist_ok=True)
            (staging / v0_path).write_bytes(png_bytes())
            environment_path = record_environment(staging, "fig-01", "Python")
            record_resources(staging)
            reference = result["identity"]["referencePath"]
            result.update({
                "route": {
                    "routeId": "fixture-direct",
                    "kind": "direct-recompute",
                    "tests": "The declared model produces the target's monotonic linear response.",
                    "doesNotSupport": [],
                    "engine": {"name": "Python", "version": "test-1", "native": True},
                },
                "execution": {
                    "argv": ["python", code_path, "--input", input_path, "--config", config_path],
                    "workingDirectory": ".",
                    "frozenArtifacts": [
                        artifact_record("source", reference, staging, result["identity"]["rightsStatus"]),
                        artifact_record("input", input_path, staging),
                        artifact_record("code", code_path, staging),
                        artifact_record("config", config_path, staging),
                        artifact_record("environment", environment_path, staging),
                    ],
                },
                "operationalStatus": "complete",
                "validationStatus": "passed",
                "claimStatus": "supported",
                "summary": "The fixture's declared linear trend is reproduced.",
                "baselineV0": v0_path,
                "selectedOutput": v0_path,
                "outputs": [v0_path],
                "blocker": None,
                "assumptions": ["The fixture PDF and generated samples define the same linear model."],
                "remainingDiscrepancies": [],
                "acceptance": {
                    "overallStatus": "passed",
                    "criteria": [{
                        "criterionId": "linear-trend", "status": "passed",
                        "statement": "The output increases monotonically.", "evidencePaths": [v0_path],
                    }],
                },
            })
            write_json(result_path, result)
            finalized = run_bundle("finalize", "--bundle", str(staging), "--status", "complete", "--json")
            final = Path(json.loads(finalized.stdout)["path"])
            run_bundle("validate", "--bundle", str(final))
            self.assertEqual(final.parent.resolve(), root.resolve())
            self.assertFalse(any(path.suffix == ".html" for path in final.rglob("*")))


if __name__ == "__main__":
    unittest.main()
