from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

try:
    import pdfplumber  # noqa: F401
    from PIL import Image
except ImportError:  # pragma: no cover - exercised by clean-install CI
    pdfplumber = None
    Image = None

from tests.fixture_factory import write_json


REPO = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO / "scirepro/scripts/materialize_target_figures.py"
ASSEMBLER = REPO / "scirepro/scripts/assemble_delivery.py"
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def pdf_object(number: int, body: bytes) -> bytes:
    return f"{number} 0 obj\n".encode() + body + b"\nendobj\n"


def write_fixture_pdf(path: Path) -> None:
    """Write a generic one-page paper fixture with a quantitative plot and caption."""
    stream = b"\n".join([
        b"0.8 w 70 250 m 70 530 l 360 530 l S",
        b"0 0 1 RG 2 w 75 500 m 130 455 l 185 405 l 240 350 l 300 285 l S",
        b"0 G BT /F1 10 Tf 245 500 Td (y = 2x + 1) Tj ET",
        b"0 G BT /F1 11 Tf 70 228 Td (Fig. 1. Linear response: y = 2x + 1.) Tj ET",
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(source: str, name: str, *, rights: str = "generated", label: str | None = None) -> dict:
    value = {"source": source, "name": name, "rights": rights}
    if label is not None:
        value["label"] = label
    return value


def run_assembler(plan: Path, output_root: Path) -> Path:
    completed = subprocess.run(
        [
            sys.executable,
            str(ASSEMBLER),
            "--plan",
            str(plan),
            "--output-root",
            str(output_root),
            "--json",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return Path(json.loads(completed.stdout)["path"])


def assert_customer_links(test: unittest.TestCase, delivery: Path) -> None:
    readme = (delivery / "README.md").read_text(encoding="utf-8")
    for raw_link in MARKDOWN_LINK.findall(readme):
        test.assertFalse(raw_link.startswith(("/", "~")), raw_link)
        test.assertTrue((delivery / raw_link).is_file(), raw_link)


def assert_no_internal_artifacts(test: unittest.TestCase, delivery: Path) -> None:
    for path in delivery.rglob("*"):
        lowered_parts = {part.casefold() for part in path.relative_to(delivery).parts}
        test.assertNotIn("tmp", lowered_parts)
        test.assertNotIn("logs", lowered_parts)
        test.assertNotEqual(path.name.casefold(), "manifest.json")
        test.assertFalse(path.suffix.casefold() == ".html")


def write_linear_work(
    work: Path, *, target_sha256: str, target_caption: str
) -> tuple[Path, Path, Path, Path]:
    """Create and execute a small raw scientific fixture with an independent oracle."""
    work.mkdir(parents=True)
    data_path = work / "series.csv"
    data_path.write_text("x,y\n0,1\n1,3\n2,5\n3,7\n4,9\n", encoding="utf-8")
    config_path = work / "config.json"
    write_json(
        config_path,
        {
            "data": "series.csv",
            "result": "result.svg",
            "observables": "observables.json",
            "expectedSlope": 2.0,
            "expectedIntercept": 1.0,
            "targetSha256": target_sha256,
            "targetCaption": target_caption,
        },
    )
    code_path = work / "reproduce.py"
    code_path.write_text(
        textwrap.dedent(
            '''\
            #!/usr/bin/env python3
            from __future__ import annotations

            import argparse
            import csv
            import json
            import math
            from pathlib import Path


            parser = argparse.ArgumentParser()
            parser.add_argument("--config", type=Path, required=True)
            args = parser.parse_args()
            config_path = args.config.resolve()
            config = json.loads(config_path.read_text(encoding="utf-8"))
            base = config_path.parent
            with (base / config["data"]).open(newline="", encoding="utf-8") as handle:
                rows = [(float(row["x"]), float(row["y"])) for row in csv.DictReader(handle)]
            mean_x = sum(x for x, _ in rows) / len(rows)
            mean_y = sum(y for _, y in rows) / len(rows)
            slope = sum((x - mean_x) * (y - mean_y) for x, y in rows) / sum(
                (x - mean_x) ** 2 for x, _ in rows
            )
            intercept = mean_y - slope * mean_x
            if not math.isclose(slope, config["expectedSlope"], abs_tol=1e-12):
                raise SystemExit("slope acceptance failed")
            if not math.isclose(intercept, config["expectedIntercept"], abs_tol=1e-12):
                raise SystemExit("intercept acceptance failed")
            points = " ".join(f"{60 + x * 100:.1f},{360 - y * 32:.1f}" for x, y in rows)
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="560" height="420" '
                'viewBox="0 0 560 420"><rect width="560" height="420" fill="white"/>'
                '<path d="M60 40V360H520" fill="none" stroke="black"/>'
                f'<polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="4"/>'
                f'<text x="75" y="70">y = {slope:g}x + {intercept:g}</text></svg>\\n'
            )
            (base / config["result"]).write_text(svg, encoding="utf-8")
            (base / config["observables"]).write_text(
                json.dumps(
                    {
                        "pointCount": len(rows),
                        "slope": slope,
                        "intercept": intercept,
                        "targetSha256": config["targetSha256"],
                        "targetCaption": config["targetCaption"],
                    },
                    indent=2,
                    sort_keys=True,
                ) + "\\n",
                encoding="utf-8",
            )
            '''
        ),
        encoding="utf-8",
    )
    executed = subprocess.run(
        [sys.executable, str(code_path), "--config", str(config_path)],
        cwd=work,
        text=True,
        capture_output=True,
    )
    if executed.returncode != 0:
        raise AssertionError(executed.stderr)

    # The test oracle reads the raw series independently of reproduce.py.
    with data_path.open(newline="", encoding="utf-8") as handle:
        rows = [(float(row["x"]), float(row["y"])) for row in csv.DictReader(handle)]
    test_slope = (rows[-1][1] - rows[0][1]) / (rows[-1][0] - rows[0][0])
    test_intercept = rows[0][1] - test_slope * rows[0][0]
    observed = json.loads((work / "observables.json").read_text(encoding="utf-8"))
    if observed != {
        "pointCount": 5,
        "slope": test_slope,
        "intercept": test_intercept,
        "targetSha256": target_sha256,
        "targetCaption": target_caption,
    }:
        raise AssertionError(f"unexpected generated observables: {observed}")
    return code_path, config_path, data_path, work / "result.svg"


@unittest.skipUnless(
    pdfplumber is not None and Image is not None and ASSEMBLER.is_file(),
    "target acquisition dependencies and the customer assembler are required",
)
class ScientificWorkflowE2ETests(unittest.TestCase):
    def test_raw_scientific_target_to_rerunnable_customer_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            transient = root / "transient"
            transient.mkdir()
            paper = transient / "paper.pdf"
            targets = transient / "targets"
            write_fixture_pdf(paper)
            acquired = subprocess.run(
                [
                    sys.executable,
                    str(MATERIALIZER),
                    "--paper",
                    str(paper),
                    "--figures",
                    "1",
                    "--output",
                    str(targets),
                    "--target-set-id",
                    "generic-linear-target",
                ],
                cwd=REPO,
                text=True,
                capture_output=True,
            )
            self.assertEqual(acquired.returncode, 0, acquired.stderr)
            manifest_path = targets / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["targetCount"], 1)
            self.assertEqual(manifest["targets"][0]["qaStatus"], "needs-review")
            verified = subprocess.run(
                [
                    sys.executable,
                    str(MATERIALIZER),
                    "--verify-manifest",
                    str(manifest_path),
                    "--verify-all",
                ],
                cwd=REPO,
                text=True,
                capture_output=True,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            target = manifest["targets"][0]
            self.assertEqual(target["qaStatus"], "verified")
            self.assertEqual(
                target["caption"],
                "Fig. 1. Linear response: y = 2x + 1.",
            )
            with pdfplumber.open(paper) as document:
                paper_text = document.pages[0].extract_text() or ""
            self.assertIn("y = 2x + 1", paper_text)

            code_path, config_path, data_path, result_path = write_linear_work(
                transient / "work",
                target_sha256=target["targetSha256"],
                target_caption=target["caption"],
            )
            evidence_path = transient / "work" / "observables.json"
            # Internal-only material proves assembly is a whitelist, not a tree copy.
            (transient / "tmp").mkdir()
            (transient / "tmp" / "intermediate.txt").write_text("discard me\n", encoding="utf-8")
            (transient / "logs").mkdir()
            (transient / "logs" / "raw.log").write_text("internal trace\n", encoding="utf-8")

            plan_path = transient / "delivery-plan.json"
            reference_source = (targets / target["normalizedPath"]).relative_to(transient).as_posix()
            plan = {
                "schemaVersion": "scirepro.delivery-plan/v1",
                "title": "Generic linear-response reproduction",
                "slug": "generic-linear",
                "distribution": "local-private",
                "conclusion": "The declared linear response is reproduced and independently checked.",
                "shared": [],
                "licenses": [],
                "targets": [
                    {
                        "id": "fig-01",
                        "title": "Linear response",
                        "kind": "quantitative",
                        "operationalStatus": "complete",
                        "validationStatus": "passed",
                        "claimStatus": "supported",
                        "conclusion": "Five raw points reproduce y = 2x + 1 exactly.",
                        "mainResult": artifact("work/result.svg", "result.svg", label="Reproduced response"),
                        "reference": artifact(
                            reference_source,
                            "reference.png",
                            rights="local-only",
                            label="Acquired paper target",
                        ),
                        "implementation": [artifact("work/reproduce.py", "reproduce.py")],
                        "parameters": [
                            artifact("work/config.json", "config.json"),
                            artifact("work/series.csv", "series.csv", label="Raw series"),
                        ],
                        "evidence": [artifact("work/observables.json", "observables.json")],
                        "dependencies": [],
                        "dependencyNote": "Python standard library only.",
                        "rerunArgv": [
                            "python3",
                            "figures/fig-01/reproduce.py",
                            "--config",
                            "figures/fig-01/config.json",
                        ],
                        "limitations": ["This fixture tests a declared deterministic model."],
                        "rights": "The generated fixture and output are local test artifacts.",
                    }
                ],
            }
            write_json(plan_path, plan)
            output_root = root / "customer"
            delivery = run_assembler(plan_path, output_root)

            self.assertEqual(delivery.resolve(), (output_root / "generic-linear-reproduction").resolve())
            self.assertEqual([item.name for item in output_root.iterdir()], [delivery.name])
            self.assertEqual(
                {item.name for item in delivery.iterdir()},
                {"README.md", "figures"},
            )
            target_dir = delivery / "figures" / "fig-01"
            self.assertEqual(
                {item.name for item in target_dir.iterdir()},
                {
                    "config.json",
                    "observables.json",
                    "reference.png",
                    "reproduce.py",
                    "result.svg",
                    "series.csv",
                },
            )
            for source, delivered_name in (
                (code_path, "reproduce.py"),
                (config_path, "config.json"),
                (data_path, "series.csv"),
                (result_path, "result.svg"),
                (evidence_path, "observables.json"),
            ):
                self.assertEqual(sha256(source), sha256(target_dir / delivered_name))

            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertIn("The declared linear response is reproduced", readme)
            self.assertIn("python3 figures/fig-01/reproduce.py --config figures/fig-01/config.json", readme)
            self.assertNotIn(str(root), readme)
            assert_customer_links(self, delivery)
            assert_no_internal_artifacts(self, delivery)

            result_digest = sha256(target_dir / "result.svg")
            rerun = subprocess.run(
                plan["targets"][0]["rerunArgv"],
                cwd=delivery,
                text=True,
                capture_output=True,
            )
            self.assertEqual(rerun.returncode, 0, rerun.stderr)
            self.assertEqual(sha256(target_dir / "result.svg"), result_digest)

    def test_mixed_quantitative_and_semantic_outputs_stay_concise(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            work = root / "work"
            work.mkdir()
            (work / "curve.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 10L10 0"/></svg>\n',
                encoding="utf-8",
            )
            with zipfile.ZipFile(work / "editable.pptx", "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>")
                archive.writestr("ppt/presentation.xml", "<p:presentation xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"/>")
            Image.new("RGB", (32, 24), color=(245, 248, 252)).save(work / "preview.png")

            plan_path = root / "mixed-plan.json"
            write_json(
                plan_path,
                {
                    "schemaVersion": "scirepro.delivery-plan/v1",
                    "title": "Mixed figure reproduction",
                    "slug": "mixed-figures",
                    "distribution": "local-private",
                    "conclusion": "The quantitative and semantic targets have separate outcomes.",
                    "targets": [
                        {
                            "id": "fig-01",
                            "title": "Response curve",
                            "kind": "quantitative",
                            "operationalStatus": "complete",
                            "validationStatus": "passed",
                            "claimStatus": "supported",
                            "conclusion": "The declared trend is present.",
                            "mainResult": artifact("work/curve.svg", "result.svg"),
                            "implementation": [],
                            "parameters": [],
                            "evidence": [],
                            "dependencies": [],
                            "limitations": [],
                            "rights": "Generated fixture.",
                        },
                        {
                            "id": "fig-02",
                            "title": "Semantic workflow",
                            "kind": "semantic-diagram",
                            "operationalStatus": "complete",
                            "validationStatus": "passed",
                            "claimStatus": "not-applicable",
                            "conclusion": "The editable topology and preview are delivered.",
                            "mainResult": artifact("work/editable.pptx", "editable.pptx"),
                            "implementation": [],
                            "parameters": [],
                            "evidence": [artifact("work/preview.png", "preview.png")],
                            "dependencies": [],
                            "limitations": [],
                            "rights": "Generated fixture.",
                        },
                    ],
                },
            )
            delivery = run_assembler(plan_path, root / "customer")
            self.assertEqual(
                {path.name for path in (delivery / "figures").iterdir()},
                {"fig-01", "fig-02"},
            )
            self.assertEqual(
                {path.name for path in (delivery / "figures" / "fig-02").iterdir()},
                {"editable.pptx", "preview.png"},
            )
            self.assertFalse(any(path.name == "build.mjs" for path in delivery.rglob("*")))
            readme = (delivery / "README.md").read_text(encoding="utf-8")
            self.assertIn("`quantitative`", readme)
            self.assertIn("`semantic-diagram`", readme)
            self.assertIn("`not-applicable`", readme)
            assert_customer_links(self, delivery)
            assert_no_internal_artifacts(self, delivery)


if __name__ == "__main__":
    unittest.main()
