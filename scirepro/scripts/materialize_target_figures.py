#!/usr/bin/env python3
"""Materialize one or more SciRepro target figures from a paper or image set."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple

try:  # Keep --help and manifest-only verification usable before environment setup.
    import pdfplumber
except ImportError:  # pragma: no cover - depends on the selected local runtime
    pdfplumber = None

try:
    from PIL import Image, ImageDraw, ImageOps
except ImportError:  # pragma: no cover - depends on the selected local runtime
    Image = ImageDraw = ImageOps = None


SCHEMA_VERSION = "scirepro.targets/v1"
ACQUISITION_MODES = {
    "paper-with-images",
    "paper-with-figure-references",
    "images-only",
}
WORKFLOW_MODES = {"scientific-reproduction", "image-derived-reconstruction"}
QA_STATES = {"needs-review", "verified", "rejected"}
IDENTITY_STATES = {"resolved", "unresolved", "not-applicable"}
TARGET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FIGURE_CAPTION = re.compile(r"^\s*(?:fig(?:ure)?\.?)[\s\u00a0]*(\d+)(?:\s*[.:\-])?\s*(.*)$", re.IGNORECASE)
MAX_TARGETS = 256
MAX_IMAGE_BYTES = 100 * 1024 * 1024
MAX_PDF_BYTES = 512 * 1024 * 1024
MAX_PDF_PAGES = 5000
MAX_RENDER_PIXELS = 120_000_000
MAX_IMAGE_PIXELS = 120_000_000


class TargetError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TargetError(message)


def checked_user_path(raw: Path, purpose: str, *, must_exist: bool = True) -> Path:
    """Resolve a user path only after rejecting every symlink component."""
    expanded = raw.expanduser()
    absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise TargetError(f"{purpose} may not contain symlink components: {cursor}")
        if not cursor.exists():
            break
    if must_exist:
        require(absolute.exists(), f"{purpose} does not exist: {absolute}")
    return absolute.resolve(strict=must_exist)


def checked_manifest_child(root: Path, relative: str, purpose: str) -> Path:
    """Open an integrity-bound workspace file without following symlinks."""
    require(safe_relative(relative), f"{purpose} path is unsafe")
    root_checked = checked_user_path(root, "target workspace", must_exist=True)
    candidate = root_checked
    for part in PurePosixPath(relative).parts:
        candidate = candidate / part
        require(not candidate.is_symlink(), f"{purpose} may not be symlinked: {candidate}")
    require(candidate.is_file(), f"{purpose} is missing: {candidate}")
    return candidate


def require_pillow() -> None:
    require(
        Image is not None,
        "Pillow is required for target images; use an existing compatible environment or create a project-local isolated environment",
    )


def require_pdfplumber() -> None:
    require(
        pdfplumber is not None,
        "pdfplumber is required for paper figure extraction; use an existing compatible environment or create a project-local isolated environment",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
    temporary.replace(path)


def canonical_manifest(manifest: dict) -> bytes:
    clone = json.loads(json.dumps(manifest))
    clone.setdefault("integrity", {})["manifestSha256"] = ""
    return json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def refresh_manifest_integrity(manifest: dict) -> None:
    integrity = manifest.setdefault("integrity", {})
    integrity["algorithm"] = "sha256"
    integrity["canonicalization"] = "json-sort-keys-v1"
    integrity["manifestSha256"] = hashlib.sha256(canonical_manifest(manifest)).hexdigest()


def safe_filename(value: str, *, fallback: str, limit: int = 180) -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f/:\\]+", " - ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:limit].rstrip(" .")


def safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "%" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and all(part not in {"", "."} for part in path.parts)


def parse_figure_numbers(value: Optional[str]) -> List[int]:
    if not value:
        return []
    numbers: list[int] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_raw, end_raw = token.split("-", 1)
            require(start_raw.isdigit() and end_raw.isdigit(), f"invalid figure range: {token}")
            start, end = int(start_raw), int(end_raw)
            require(1 <= start <= end, f"invalid figure range: {token}")
            require(end - start + 1 <= MAX_TARGETS, f"figure range exceeds the {MAX_TARGETS}-target safety limit")
            require(len(numbers) + end - start + 1 <= MAX_TARGETS, f"figure request exceeds the {MAX_TARGETS}-target safety limit")
            numbers.extend(range(start, end + 1))
        else:
            require(token.isdigit() and int(token) >= 1, f"invalid figure number: {token}")
            require(len(numbers) < MAX_TARGETS, f"figure request exceeds the {MAX_TARGETS}-target safety limit")
            numbers.append(int(token))
    require(len(numbers) == len(set(numbers)), "figure references must not contain duplicates")
    return numbers


def figure_reference_number(value: object) -> Optional[int]:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*fig(?:ure)?\.?\s*(\d+)\s*", value, re.IGNORECASE)
    return int(match.group(1)) if match else None


def group_lines(words: list[dict], tolerance: float = 2.5) -> list[dict]:
    lines: list[dict] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        top = float(word["top"])
        line = next((item for item in reversed(lines[-4:]) if abs(item["top"] - top) <= tolerance), None)
        if line is None:
            line = {"top": top, "bottom": float(word["bottom"]), "words": []}
            lines.append(line)
        line["words"].append(word)
        line["top"] = min(line["top"], top)
        line["bottom"] = max(line["bottom"], float(word["bottom"]))
    for line in lines:
        line["words"].sort(key=lambda item: float(item["x0"]))
        line["text"] = " ".join(str(item["text"]) for item in line["words"])
        line["x0"] = min(float(item["x0"]) for item in line["words"])
        line["x1"] = max(float(item["x1"]) for item in line["words"])
        line["height"] = line["bottom"] - line["top"]
        line["wordHeight"] = statistics.median(
            float(item["bottom"]) - float(item["top"]) for item in line["words"]
        )
    return lines


def merge_caption_lines(lines: List[dict]) -> str:
    """Join wrapped caption lines without preserving extraction-only hyphens."""
    merged = ""
    for line in lines:
        text = re.sub(r"\s+", " ", str(line["text"])).strip()
        if not merged:
            merged = text
        elif merged.endswith("-") and text and text[0].islower():
            merged = merged[:-1] + text
        else:
            merged += " " + text
    return merged


def _caption_candidates(page: object, figure_number: int) -> List[dict]:
    """Return geometric caption candidates without merging two PDF columns.

    A full-page `extract_words` line can silently concatenate a left-column
    caption with right-column prose at the same y coordinate.  SciRepro first
    indexes each half-column independently and fails closed when two equally
    plausible candidates remain.  Full-width captions are considered only
    when neither half contains the requested marker.
    """
    words = page.extract_words(
        x_tolerance=1,
        y_tolerance=2,
        use_text_flow=False,
        keep_blank_chars=False,
    ) or []
    midpoint = float(page.width) / 2
    columns: List[Tuple[str, float, float]] = [
        ("left", 0.0, midpoint),
        ("right", midpoint, float(page.width)),
    ]
    results: List[dict] = []
    for column, column_x0, column_x1 in columns:
        column_words = [
            word for word in words
            if column_x0 <= (float(word["x0"]) + float(word["x1"])) / 2 < column_x1
        ]
        lines = group_lines(column_words)
        for index, line in enumerate(lines):
            marker = FIGURE_CAPTION.match(line["text"])
            if not marker or int(marker.group(1)) != figure_number:
                continue
            selected = [line]
            previous = line
            for candidate in lines[index + 1:index + 7]:
                gap = candidate["top"] - previous["bottom"]
                same_caption_size = abs(candidate["wordHeight"] - line["wordHeight"]) <= max(
                    0.8, line["wordHeight"] * 0.12
                )
                if gap < -1 or gap > max(5.0, line["wordHeight"] * 0.72) or not same_caption_size:
                    break
                if FIGURE_CAPTION.match(candidate["text"]):
                    break
                selected.append(candidate)
                previous = candidate
            results.append({
                "text": merge_caption_lines(selected),
                "bbox": (
                    min(item["x0"] for item in selected),
                    min(item["top"] for item in selected),
                    max(item["x1"] for item in selected),
                    max(item["bottom"] for item in selected),
                ),
                "wordHeight": line["wordHeight"],
                "column": column,
            })

    if results:
        return results

    # Conservative fallback for a genuine full-width caption.  Reject a line
    # containing another figure marker because that is characteristic of two
    # interleaved columns, not one caption.
    lines = group_lines(words)
    for index, line in enumerate(lines):
        marker = FIGURE_CAPTION.match(line["text"])
        if not marker or int(marker.group(1)) != figure_number:
            continue
        if len(re.findall(r"\bfig(?:ure)?\.?\s*\d+", line["text"], re.IGNORECASE)) != 1:
            continue
        selected = [line]
        previous = line
        for candidate in lines[index + 1:index + 7]:
            gap = candidate["top"] - previous["bottom"]
            same_caption_size = abs(candidate["wordHeight"] - line["wordHeight"]) <= max(
                0.8, line["wordHeight"] * 0.12
            )
            if gap < -1 or gap > max(5.0, line["wordHeight"] * 0.72) or not same_caption_size:
                break
            if FIGURE_CAPTION.match(candidate["text"]):
                break
            selected.append(candidate)
            previous = candidate
        bbox = (
            min(item["x0"] for item in selected),
            min(item["top"] for item in selected),
            max(item["x1"] for item in selected),
            max(item["bottom"] for item in selected),
        )
        if bbox[2] - bbox[0] >= float(page.width) * 0.52:
            results.append({
                "text": merge_caption_lines(selected),
                "bbox": bbox,
                "wordHeight": line["wordHeight"],
                "column": "full",
            })
    return results


def caption_for(page: object, figure_number: int) -> Optional[Tuple[str, Tuple[float, float, float, float]]]:
    candidates = _caption_candidates(page, figure_number)
    if not candidates:
        return None

    # Captions and body references can both begin with "Fig. N".  A caption is
    # normally typeset smaller.  Select it only when that distinction is
    # decisive; otherwise stop rather than crop the wrong object.
    candidates.sort(key=lambda item: (item["wordHeight"], item["bbox"][1]))
    winner = candidates[0]
    if len(candidates) > 1:
        runner_up = candidates[1]
        require(
            runner_up["wordHeight"] - winner["wordHeight"] >= max(0.75, winner["wordHeight"] * 0.08),
            f"Fig. {figure_number} has ambiguous caption candidates on one page; use a reviewed manual crop",
        )
    text = winner["text"]
    # Some PDFs visually typeset the caption separator but omit it from the
    # text layer (FMD Fig. 17 is one example).  Normalize only a missing
    # separator in an otherwise recognized `Fig. N` marker.
    marker = re.match(
        rf"^\s*(fig(?:ure)?\.?)\s*{figure_number}(?:\s*[.:-])?\s*",
        text,
        flags=re.IGNORECASE,
    )
    if marker:
        label = "Figure" if marker.group(1).lower().startswith("figure") else "Fig."
        text = f"{label} {figure_number}. " + text[marker.end():].lstrip()
    return text, winner["bbox"]


def column_bounds(page_width: float, caption_bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x0, _, x1, _ = caption_bbox
    # Start from a deliberately broad, column-safe region. A later pixel pass
    # tightens this region around the complete figure and caption. Keeping the
    # first pass broad avoids clipping legends or long wrapped captions whose
    # ink extends beyond the PDF text box.
    margin = page_width * 0.03
    midpoint = page_width / 2
    if x1 - x0 >= page_width * 0.52 or (x0 < midpoint and x1 > midpoint):
        return margin, page_width - margin
    if (x0 + x1) / 2 < midpoint:
        return margin, midpoint
    return midpoint, page_width - margin


def tighten_horizontal_bounds(
    page_image: Image.Image,
    broad_x0: int,
    broad_x1: int,
    top: int,
    bottom: int,
    dpi: int,
) -> tuple[int, int]:
    """Find the full ink extent inside a safe column and add a small pad."""
    region = ImageOps.grayscale(page_image).crop((broad_x0, top, broad_x1, bottom))
    ink = region.point(lambda value: 255 if value < 245 else 0)
    bbox = ink.getbbox()
    if bbox is None:
        return broad_x0, broad_x1
    pad = max(10, round(dpi * 0.05))
    left = max(broad_x0, broad_x0 + bbox[0] - pad)
    right = min(broad_x1, broad_x0 + bbox[2] + pad)

    # A non-zero mark touching a broad column boundary is usually part of the
    # target (for example a rotated y-label), not safe whitespace. Do not ship
    # a clipped automatic crop: keep the broad side and let visual QA decide.
    edge_band = max(2, round(dpi / 150))
    left_edge_has_ink = any(ink.getpixel((x, y)) for x in range(min(edge_band, ink.width)) for y in range(ink.height))
    right_edge_has_ink = any(
        ink.getpixel((x, y))
        for x in range(max(0, ink.width - edge_band), ink.width)
        for y in range(ink.height)
    )
    if left_edge_has_ink:
        left = broad_x0
    if right_edge_has_ink:
        right = broad_x1
    return left, right


def run_pdftoppm(pdf: Path, page_number: int, dpi: int, output_stem: Path) -> Path:
    command = [
        "pdftoppm", "-f", str(page_number), "-l", str(page_number),
        "-r", str(dpi), "-singlefile", "-png", str(pdf), str(output_stem),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    except FileNotFoundError as exc:
        raise TargetError("pdftoppm is required for paper figure extraction") from exc
    require(completed.returncode == 0, f"pdftoppm failed for page {page_number}: {completed.stderr.strip()}")
    rendered = output_stem.with_suffix(".png")
    require(rendered.is_file(), f"pdftoppm did not create {rendered.name}")
    return rendered


def detect_figure_top(
    page_image: Image.Image,
    x0_px: int,
    x1_px: int,
    caption_top_px: int,
    dpi: int,
) -> int:
    gray = ImageOps.grayscale(page_image).crop((x0_px, 0, x1_px, caption_top_px))
    width, height = gray.size
    pixels = gray.load()
    minimum_ink = max(2, int(width * 0.0015))
    active_rows: list[bool] = []
    for y in range(height):
        ink = 0
        for x in range(width):
            if pixels[x, y] < 245:
                ink += 1
                if ink >= minimum_ink:
                    break
        active_rows.append(ink >= minimum_ink)

    # Publisher figure panels commonly contain 10-15 px internal gutters at
    # 300 DPI.  A separator between a figure and surrounding prose is much
    # larger.  Requiring roughly 0.15 inch avoids treating a panel gutter as
    # the top boundary (the FMD Fig. 20 photo/schematic pair is a regression
    # case) while remaining conservative: every crop still requires QA.
    gap_required = max(36, round(dpi * 0.15))
    blank = 0
    seen_content = False
    for y in range(height - 1, -1, -1):
        if active_rows[y]:
            seen_content = True
            blank = 0
            continue
        if seen_content:
            blank += 1
            if blank >= gap_required:
                return min(height, y + blank + 1)
    return max(0, round(dpi * 0.18))


def render_qa_overlay(page_image: Image.Image, crop: tuple[int, int, int, int], output: Path) -> None:
    preview = page_image.copy().convert("RGB")
    draw = ImageDraw.Draw(preview)
    width = max(4, round(preview.width / 500))
    draw.rectangle(crop, outline=(220, 38, 38), width=width)
    preview.thumbnail((1500, 1900), Image.Resampling.LANCZOS)
    preview.save(output, format="PNG", optimize=True)


def normalize_uploaded_image(source: Path, destination: Path, dpi: int) -> tuple[int, int]:
    require_pillow()
    require(source.is_file() and not source.is_symlink(), f"image does not exist or is symlinked: {source}")
    require(source.stat().st_size <= MAX_IMAGE_BYTES, f"image exceeds {MAX_IMAGE_BYTES} bytes: {source.name}")
    try:
        with Image.open(source) as opened:
            width, height = opened.size
            require(
                width > 0 and height > 0 and width * height <= MAX_IMAGE_PIXELS,
                f"image exceeds the {MAX_IMAGE_PIXELS}-pixel safety limit: {source.name}",
            )
            image = ImageOps.exif_transpose(opened).convert("RGB")
            size = image.size
            image.save(destination, format="PNG", dpi=(dpi, dpi), optimize=True)
            return size
    except (OSError, Image.DecompressionBombError) as exc:
        raise TargetError(f"unsupported or malformed image {source.name}: {exc}") from exc


def target_record(
    *,
    target_id: str,
    acquisition_mode: str,
    workflow_mode: str,
    identity_status: str,
    requested_as: str,
    normalized_path: Path,
    original_path: Path,
    output: Path,
    source_sha256: str,
    source_file_name: str,
    caption: Optional[str],
    figure_reference: Optional[str],
    page: Optional[int],
    crop_box: Optional[List[float]],
    dpi: int,
    caption_included: bool,
    qa_status: str,
    notes: list[str],
) -> dict:
    require(TARGET_ID.fullmatch(target_id) is not None, f"invalid target ID: {target_id}")
    require(acquisition_mode in ACQUISITION_MODES, f"invalid acquisition mode: {acquisition_mode}")
    require(workflow_mode in WORKFLOW_MODES, f"invalid workflow mode: {workflow_mode}")
    require(identity_status in IDENTITY_STATES, f"invalid identity status: {identity_status}")
    require(qa_status in QA_STATES, f"invalid QA status: {qa_status}")
    relative = normalized_path.relative_to(output).as_posix()
    original_relative = original_path.relative_to(output).as_posix()
    with Image.open(normalized_path) as image:
        width, height = image.size
    return {
        "targetId": target_id,
        "acquisitionMode": acquisition_mode,
        "workflowMode": workflow_mode,
        "identityStatus": identity_status,
        "requestedAs": requested_as,
        "figureReference": figure_reference,
        "paperPage": page,
        "caption": caption,
        "originalPath": original_relative,
        "normalizedPath": relative,
        "sourceFileName": source_file_name,
        "sourceSha256": source_sha256,
        "normalizedSha256": sha256_file(normalized_path),
        "targetSha256": sha256_file(normalized_path),
        "mediaType": "image/png",
        "width": width,
        "height": height,
        "dpi": dpi,
        "cropBoxPdfPoints": crop_box,
        "captionIncluded": caption_included,
        "qaStatus": qa_status,
        "localAnalysisOnly": True,
        "notes": notes,
    }


def validate_manifest(manifest: object, *, root: Optional[Path] = None, require_verified: bool = False) -> Dict[str, dict]:
    require(isinstance(manifest, dict), "target manifest must be an object")
    require(manifest.get("schemaVersion") == SCHEMA_VERSION, f"unsupported target manifest schema: {manifest.get('schemaVersion')}")
    integrity = manifest.get("integrity")
    require(isinstance(integrity, dict), "target manifest integrity is required")
    require(integrity.get("algorithm") == "sha256", "target manifest integrity algorithm must be sha256")
    require(integrity.get("canonicalization") == "json-sort-keys-v1", "unsupported target manifest canonicalization")
    manifest_hash = integrity.get("manifestSha256")
    require(isinstance(manifest_hash, str) and re.fullmatch(r"[0-9a-f]{64}", manifest_hash), "invalid target manifest SHA-256")
    require(hashlib.sha256(canonical_manifest(manifest)).hexdigest() == manifest_hash, "target manifest hash mismatch")
    require(isinstance(manifest.get("targetSetId"), str) and TARGET_ID.fullmatch(manifest["targetSetId"]), "invalid targetSetId")
    require(isinstance(manifest.get("createdAt"), str) and manifest["createdAt"], "target manifest createdAt is required")
    paper = manifest.get("paper")
    if paper is not None:
        require(isinstance(paper, dict), "target manifest paper must be an object or null")
        require(
            set(paper) == {"fileName", "originalPath", "sha256", "pageCount"},
            "target manifest paper fields are invalid",
        )
        require(isinstance(paper.get("fileName"), str) and paper["fileName"], "paper fileName is required")
        require(safe_relative(paper.get("originalPath")), "paper originalPath is unsafe")
        require(
            isinstance(paper.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", paper["sha256"]),
            "paper SHA-256 is invalid",
        )
        require(isinstance(paper.get("pageCount"), int) and paper["pageCount"] >= 1, "paper pageCount is invalid")
        if root is not None:
            paper_path = checked_manifest_child(root, paper["originalPath"], "preserved paper")
            require(sha256_file(paper_path) == paper["sha256"], "preserved paper hash mismatch")
    targets = manifest.get("targets")
    require(isinstance(targets, list) and 1 <= len(targets) <= MAX_TARGETS, f"target manifest must contain 1-{MAX_TARGETS} targets")
    require(manifest.get("targetCount") == len(targets), "targetCount must equal the target array length")
    by_id: dict[str, dict] = {}
    used_paths: set[str] = set()
    for target in targets:
        require(isinstance(target, dict), "target entries must be objects")
        target_id = target.get("targetId")
        require(isinstance(target_id, str) and TARGET_ID.fullmatch(target_id), f"invalid target ID: {target_id!r}")
        require(target_id not in by_id, f"duplicate target ID: {target_id}")
        require(target.get("acquisitionMode") in ACQUISITION_MODES, f"{target_id}: invalid acquisition mode")
        require(target.get("workflowMode") in WORKFLOW_MODES, f"{target_id}: invalid workflow mode")
        acquisition_mode = target["acquisitionMode"]
        workflow_mode = target["workflowMode"]
        identity_status = target.get("identityStatus")
        require(identity_status in IDENTITY_STATES, f"{target_id}: invalid identity status")
        figure_number = figure_reference_number(target.get("figureReference"))
        caption = target.get("caption")
        paper_page = target.get("paperPage")
        if acquisition_mode == "images-only":
            require(paper is None, f"{target_id}: images-only manifest must not carry a paper")
            require(identity_status == "not-applicable", f"{target_id}: images-only identity must be not-applicable")
            require(workflow_mode == "image-derived-reconstruction", f"{target_id}: images-only target cannot claim scientific reproduction")
            require(target.get("figureReference") is None and caption is None and paper_page is None, f"{target_id}: images-only target cannot claim paper identity")
        if acquisition_mode in {"paper-with-images", "paper-with-figure-references"}:
            require(paper is not None, f"{target_id}: paper acquisition mode requires a preserved paper")
            if workflow_mode == "scientific-reproduction":
                require(identity_status == "resolved", f"{target_id}: unresolved paper target cannot claim scientific reproduction")
            if identity_status == "unresolved":
                require(
                    workflow_mode == "image-derived-reconstruction",
                    f"{target_id}: unresolved paper target must remain image-derived",
                )
        if identity_status == "resolved" or workflow_mode == "scientific-reproduction":
            require(acquisition_mode != "images-only", f"{target_id}: scientific identity requires a paper mode")
            require(figure_number is not None, f"{target_id}: resolved identity requires one normalized figure reference")
            require(isinstance(caption, str) and caption.strip(), f"{target_id}: resolved identity requires a caption")
            caption_match = FIGURE_CAPTION.match(caption)
            require(
                caption_match is not None and int(caption_match.group(1)) == figure_number,
                f"{target_id}: caption and figure reference disagree",
            )
            require(
                isinstance(paper_page, int) and 1 <= paper_page <= paper["pageCount"],
                f"{target_id}: resolved identity requires a valid paper page",
            )
            require(identity_status == "resolved" and workflow_mode == "scientific-reproduction", f"{target_id}: scientific workflow and resolved identity must agree")
        require(target.get("qaStatus") in QA_STATES, f"{target_id}: invalid QA status")
        require(isinstance(target.get("captionIncluded"), bool), f"{target_id}: captionIncluded must be boolean")
        require(isinstance(target.get("localAnalysisOnly"), bool), f"{target_id}: localAnalysisOnly must be boolean")
        require(isinstance(target.get("notes"), list) and all(isinstance(note, str) for note in target["notes"]), f"{target_id}: notes must be an array of strings")
        require(isinstance(target.get("width"), int) and target["width"] > 0, f"{target_id}: width is invalid")
        require(isinstance(target.get("height"), int) and target["height"] > 0, f"{target_id}: height is invalid")
        require(isinstance(target.get("dpi"), int) and 72 <= target["dpi"] <= 600, f"{target_id}: dpi is invalid")
        crop_box = target.get("cropBoxPdfPoints")
        require(
            crop_box is None or (
                isinstance(crop_box, list) and len(crop_box) == 4
                and all(isinstance(value, (int, float)) for value in crop_box)
                and crop_box[0] < crop_box[2] and crop_box[1] < crop_box[3]
            ),
            f"{target_id}: cropBoxPdfPoints is invalid",
        )
        if acquisition_mode == "paper-with-figure-references":
            require(identity_status == "resolved" and workflow_mode == "scientific-reproduction", f"{target_id}: PDF extraction must retain resolved scientific identity")
            require(crop_box is not None, f"{target_id}: PDF extraction requires a recorded crop box")
            require(target.get("captionIncluded") is True, f"{target_id}: PDF extraction must include its indexed caption")
        else:
            require(crop_box is None, f"{target_id}: only PDF extraction targets may carry a PDF crop box")
        if require_verified:
            require(target.get("qaStatus") == "verified", f"{target_id}: target crop has not been visually verified")
        relative = target.get("normalizedPath")
        original_relative = target.get("originalPath")
        require(safe_relative(relative), f"{target_id}: unsafe normalizedPath")
        require(safe_relative(original_relative), f"{target_id}: unsafe originalPath")
        require(relative not in used_paths, f"{target_id}: duplicate normalizedPath: {relative}")
        require(original_relative not in used_paths, f"{target_id}: duplicate originalPath: {original_relative}")
        used_paths.update({relative, original_relative})
        require(target.get("mediaType") == "image/png", f"{target_id}: normalized target must be PNG")
        history = target.get("provenanceHistory", [])
        require(isinstance(history, list), f"{target_id}: provenanceHistory must be an array")
        for expected_version, event in enumerate(history, start=1):
            require(isinstance(event, dict), f"{target_id}: invalid provenance event")
            require(event.get("version") == expected_version, f"{target_id}: provenance versions must be contiguous")
            previous = event.get("previous")
            replacement = event.get("replacement")
            require(isinstance(previous, dict) and isinstance(replacement, dict), f"{target_id}: invalid provenance event payload")
            for key in ("originalPath", "normalizedPath"):
                require(safe_relative(previous.get(key)), f"{target_id}: unsafe previous {key}")
                require(safe_relative(replacement.get(key)), f"{target_id}: unsafe replacement {key}")
            for key in ("sourceSha256", "normalizedSha256"):
                require(
                    isinstance(replacement.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", replacement[key]),
                    f"{target_id}: invalid replacement {key}",
                )
        require(isinstance(target.get("normalizedSha256"), str) and re.fullmatch(r"[0-9a-f]{64}", target["normalizedSha256"]), f"{target_id}: invalid normalized SHA-256")
        require(target.get("targetSha256") == target.get("normalizedSha256"), f"{target_id}: target hash must bind the normalized Phase 0 object")
        require(isinstance(target.get("sourceSha256"), str) and re.fullmatch(r"[0-9a-f]{64}", target["sourceSha256"]), f"{target_id}: invalid source SHA-256")
        if root is not None:
            require_pillow()
            path = checked_manifest_child(root, relative, f"{target_id} normalized target")
            original_path = checked_manifest_child(root, original_relative, f"{target_id} original target")
            require(sha256_file(path) == target["normalizedSha256"], f"{target_id}: normalized target hash mismatch")
            require(sha256_file(original_path) == target["sourceSha256"], f"{target_id}: original target hash mismatch")
            try:
                with Image.open(path) as normalized_image:
                    require(normalized_image.format == "PNG", f"{target_id}: normalized target is not a PNG")
                    require(
                        normalized_image.width * normalized_image.height <= MAX_IMAGE_PIXELS,
                        f"{target_id}: normalized target exceeds the pixel safety limit",
                    )
                    require(normalized_image.size == (target["width"], target["height"]), f"{target_id}: normalized dimensions do not match the manifest")
                    normalized_image.verify()
            except (OSError, Image.DecompressionBombError) as exc:
                raise TargetError(f"{target_id}: normalized PNG failed to decode: {exc}") from exc
        by_id[target_id] = target
    return by_id


def mark_verified(manifest_path: Path, target_ids: list[str], caption_included: bool) -> int:
    manifest_path = checked_user_path(manifest_path, "target manifest", must_exist=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    targets = validate_manifest(manifest, root=manifest_path.parent)
    require(target_ids, "verification requires --verify-targets; use --verify-all only after reviewing every target")
    selected = set(target_ids)
    require(selected <= set(targets), f"unknown target IDs: {sorted(selected - set(targets))}")
    for target_id in selected:
        target = targets[target_id]
        target["qaStatus"] = "verified"
        if caption_included:
            target["captionIncluded"] = True
        # Verification is the explicit visual identity attestation.  A mere
        # `--uploaded-figure-refs 7` label is only a candidate match and must
        # not grant scientific-reproduction status before this step.
        if (
            target.get("acquisitionMode") in {"paper-with-images", "paper-with-figure-references"}
            and target.get("figureReference")
            and target.get("caption")
            and target.get("paperPage")
        ):
            target["identityStatus"] = "resolved"
            target["workflowMode"] = "scientific-reproduction"
            if isinstance(target.get("identityBinding"), dict):
                target["identityBinding"]["status"] = "verified"
                target["identityBinding"]["verifiedAt"] = datetime.now(timezone.utc).replace(
                    microsecond=0
                ).isoformat().replace("+00:00", "Z")
    refresh_manifest_integrity(manifest)
    validate_manifest(manifest, root=manifest_path.parent)
    write_json(manifest_path, manifest)
    print(json.dumps({"status": "verified", "manifest": str(manifest_path), "targets": sorted(selected)}, ensure_ascii=False))
    return 0


def bind_uploaded_identity(
    manifest_path: Path,
    target_id: str,
    figure_number: int,
    paper_page: Optional[int],
) -> int:
    """Bind an uploaded candidate to indexed paper metadata, pending visual QA."""
    require_pdfplumber()
    manifest_path = checked_user_path(manifest_path, "target manifest", must_exist=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    targets = validate_manifest(manifest, root=manifest_path.parent)
    require(target_id in targets, f"unknown target ID: {target_id}")
    target = targets[target_id]
    require(
        target.get("acquisitionMode") == "paper-with-images",
        "identity binding is only valid for an uploaded target accompanied by a paper",
    )
    paper = manifest.get("paper")
    require(isinstance(paper, dict), "identity binding requires a preserved paper")
    require(figure_number >= 1, "--paper-figure-ref must be a positive integer")
    preserved_paper = checked_manifest_child(
        manifest_path.parent, paper["originalPath"], "preserved paper"
    )
    require(preserved_paper.suffix.lower() == ".pdf", "preserved paper must be a PDF")

    with pdfplumber.open(preserved_paper) as pdf:
        require(len(pdf.pages) == paper["pageCount"], "preserved paper page count changed")
        if paper_page is not None:
            require(1 <= paper_page <= len(pdf.pages), "--paper-page is outside the preserved paper")
            result = caption_for(pdf.pages[paper_page - 1], figure_number)
            require(result is not None, f"Fig. {figure_number} caption was not found on paper page {paper_page}")
            matches = [(paper_page, result[0])]
        else:
            matches = []
            for page_index, page in enumerate(pdf.pages, start=1):
                result = caption_for(page, figure_number)
                if result:
                    matches.append((page_index, result[0]))
            require(matches, f"Fig. {figure_number} caption was not found in the preserved paper")
            require(
                len(matches) == 1,
                f"Fig. {figure_number} matched multiple pages; provide --paper-page after reviewing the paper",
            )
    matched_page, caption = matches[0]

    prior_binding = target.get("identityBinding")
    if prior_binding is not None:
        target.setdefault("identityBindingHistory", []).append(json.loads(json.dumps(prior_binding)))
    target.update({
        "figureReference": f"Fig. {figure_number}",
        "paperPage": matched_page,
        "caption": caption,
        "identityStatus": "unresolved",
        "workflowMode": "image-derived-reconstruction",
        "qaStatus": "needs-review",
        "captionIncluded": False,
        "cropBoxPdfPoints": None,
        "identityBinding": {
            "boundAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "method": "reviewed-paper-index",
            "status": "pending-visual-verification",
            "figureReference": f"Fig. {figure_number}",
            "paperPage": matched_page,
            "caption": caption,
        },
    })
    target.setdefault("notes", []).append(
        f"Candidate identity bound to Fig. {figure_number}, paper page {matched_page}; visual verification is still required."
    )
    refresh_manifest_integrity(manifest)
    validate_manifest(manifest, root=manifest_path.parent)
    write_json(manifest_path, manifest)
    print(json.dumps({
        "status": "identity-bound-needs-review",
        "manifest": str(manifest_path),
        "target": target_id,
        "figureReference": f"Fig. {figure_number}",
        "paperPage": matched_page,
    }, ensure_ascii=False))
    return 0


def replace_target(manifest_path: Path, target_id: str, replacement: Path, dpi: int) -> int:
    """Transactionally replace a bad crop while retaining full provenance."""
    require_pillow()
    manifest_path = checked_user_path(manifest_path, "target manifest", must_exist=True)
    replacement = checked_user_path(replacement, "replacement image", must_exist=True)
    require(replacement.is_file(), "replacement image is not a regular file")
    workspace = manifest_path.parent
    original_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current_targets = validate_manifest(original_manifest, root=workspace)
    require(target_id in current_targets, f"unknown target ID: {target_id}")
    current_target = current_targets[target_id]
    history = current_target.get("provenanceHistory", [])
    require(isinstance(history, list), f"{target_id}: provenanceHistory must be an array")
    version = len(history) + 1

    originals = workspace / "originals" / "replacements"
    figures = workspace / "figures"
    qa = workspace / "qa"
    require(figures.is_dir() and not figures.is_symlink(), "figures directory is missing or symlinked")
    require(qa.is_dir() and not qa.is_symlink(), "QA directory is missing or symlinked")
    require(not originals.is_symlink(), "replacement originals directory may not be symlinked")
    final_original = originals / f"{target_id}-replacement-v{version:03d}{replacement.suffix.lower() or '.bin'}"
    final_normalized = figures / f"{target_id}-replacement-v{version:03d}.png"
    overlay = qa / f"{target_id}-crop-overlay.png"
    require(not overlay.is_symlink(), f"{target_id}: QA overlay may not be symlinked")
    final_overlay_archive = qa / f"{target_id}-crop-overlay-v{version:03d}-superseded.png"
    require(not final_original.exists(), f"{target_id}: replacement provenance path already exists")
    require(not final_normalized.exists(), f"{target_id}: replacement output path already exists")
    require(not final_overlay_archive.exists(), f"{target_id}: QA overlay history path already exists")

    staging = Path(tempfile.mkdtemp(prefix=f".{target_id}-replacement-", dir=workspace))
    created: List[Path] = []
    created_originals_dir = False
    manifest_committed = False
    overlay_removed = False
    try:
        staged_original = staging / "original" / final_original.name
        staged_normalized = staging / "normalized" / final_normalized.name
        staged_original.parent.mkdir()
        staged_normalized.parent.mkdir()
        shutil.copy2(replacement, staged_original)
        normalize_uploaded_image(replacement, staged_normalized, dpi)
        with Image.open(staged_normalized) as image:
            width, height = image.size
        source_sha = sha256_file(staged_original)
        normalized_sha = sha256_file(staged_normalized)

        next_manifest = json.loads(json.dumps(original_manifest))
        target = next(item for item in next_manifest["targets"] if item["targetId"] == target_id)
        full_previous = {
            key: json.loads(json.dumps(value))
            for key, value in target.items()
            if key != "provenanceHistory"
        }
        archived_overlay_relative = None
        staged_overlay = None
        if overlay.is_file():
            staged_overlay = staging / final_overlay_archive.name
            shutil.copy2(overlay, staged_overlay)
            archived_overlay_relative = final_overlay_archive.relative_to(workspace).as_posix()
        target.setdefault("provenanceHistory", []).append({
            "version": version,
            "replacedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "previous": full_previous,
            "previousQaOverlayPath": archived_overlay_relative,
            "replacement": {
                "sourceFileName": replacement.name,
                "sourceSha256": source_sha,
                "originalPath": final_original.relative_to(workspace).as_posix(),
                "normalizedPath": final_normalized.relative_to(workspace).as_posix(),
                "normalizedSha256": normalized_sha,
            },
        })
        target.update({
            "sourceFileName": replacement.name,
            "sourceSha256": source_sha,
            "originalPath": final_original.relative_to(workspace).as_posix(),
            "normalizedPath": final_normalized.relative_to(workspace).as_posix(),
            "normalizedSha256": normalized_sha,
            "targetSha256": normalized_sha,
            "width": width,
            "height": height,
            "dpi": dpi,
            "qaStatus": "needs-review",
            "captionIncluded": False,
            "cropBoxPdfPoints": None,
        })
        if target.get("acquisitionMode") in {"paper-with-images", "paper-with-figure-references"}:
            target["acquisitionMode"] = "paper-with-images"
            target["identityStatus"] = "unresolved"
            target["workflowMode"] = "image-derived-reconstruction"
            if isinstance(target.get("identityBinding"), dict):
                target["identityBinding"]["status"] = "superseded-by-replacement"
        target.setdefault("notes", []).append(
            f"Target pixels replaced as provenance version {version}; PDF crop, identity, caption inclusion, and QA verification were reset."
        )
        refresh_manifest_integrity(next_manifest)
        validate_manifest(next_manifest, root=None)

        if not originals.exists():
            originals.mkdir()
            created_originals_dir = True
        staged_original.replace(final_original)
        created.append(final_original)
        staged_normalized.replace(final_normalized)
        created.append(final_normalized)
        if staged_overlay is not None:
            staged_overlay.replace(final_overlay_archive)
            created.append(final_overlay_archive)
        validate_manifest(next_manifest, root=workspace)
        write_json(manifest_path, next_manifest)
        manifest_committed = True
        if overlay.is_file():
            overlay.unlink()
            overlay_removed = True
    except Exception:
        if manifest_committed:
            write_json(manifest_path, original_manifest)
        if overlay_removed and final_overlay_archive.is_file():
            shutil.copy2(final_overlay_archive, overlay)
        for path in reversed(created):
            if path.is_file() and not path.is_symlink():
                path.unlink()
        if created_originals_dir and originals.is_dir() and not any(originals.iterdir()):
            originals.rmdir()
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print(json.dumps({"status": "replaced", "manifest": str(manifest_path), "target": target_id}, ensure_ascii=False))
    return 0


def preflight_acquisition(args: argparse.Namespace) -> Tuple[Optional[Path], List[Path], List[int], List[int]]:
    """Resolve every input and target ID before creating output artifacts."""
    paper = checked_user_path(args.paper, "paper", must_exist=True) if args.paper else None
    images = [checked_user_path(path, "target image", must_exist=True) for path in args.image]
    figure_numbers = parse_figure_numbers(args.figures)
    uploaded_refs = parse_figure_numbers(args.uploaded_figure_refs)
    require(paper is not None or images, "provide --paper with --figures, or one or more --image files")
    require(bool(images or figure_numbers), "provide at least one target image or figure reference")
    if uploaded_refs:
        require(len(uploaded_refs) == len(images), "--uploaded-figure-refs must contain one figure number per --image")
    require(len(images) + len(figure_numbers) <= MAX_TARGETS, f"a target set may contain at most {MAX_TARGETS} items")
    if paper is not None:
        require(paper.is_file() and not paper.is_symlink(), f"paper does not exist or is symlinked: {paper}")
        require(paper.suffix.lower() == ".pdf", "--paper must be a PDF file")
        require(paper.stat().st_size <= MAX_PDF_BYTES, f"paper exceeds the {MAX_PDF_BYTES}-byte safety limit")
    elif figure_numbers:
        raise TargetError("--figures requires --paper")
    for source in images:
        require(source.is_file() and not source.is_symlink(), f"image does not exist or is symlinked: {source}")
        require(source.stat().st_size <= MAX_IMAGE_BYTES, f"image exceeds {MAX_IMAGE_BYTES} bytes: {source.name}")

    uploaded_ids = [
        f"fig-{reference:02d}" if uploaded_refs else f"image-{index:03d}"
        for index, reference in enumerate(uploaded_refs or ([None] * len(images)), start=1)
    ]
    extracted_ids = [f"fig-{number:02d}" for number in figure_numbers]
    all_ids = uploaded_ids + extracted_ids
    require(len(all_ids) == len(set(all_ids)), "uploaded images and paper references resolve to duplicate target IDs")
    return paper, images, figure_numbers, uploaded_refs


def materialize_into(args: argparse.Namespace, output: Path) -> int:
    require_pillow()
    output.mkdir(parents=True, exist_ok=True)
    originals = output / "originals"
    figures_dir = output / "figures"
    qa_dir = output / "qa"
    originals.mkdir()
    figures_dir.mkdir()
    qa_dir.mkdir()

    paper, images, figure_numbers, uploaded_refs = preflight_acquisition(args)

    paper_info = None
    pdf = None
    if paper is not None:
        require_pdfplumber()
        require(paper.is_file() and not paper.is_symlink(), f"paper does not exist or is symlinked: {paper}")
        require(paper.suffix.lower() == ".pdf", "--paper must be a PDF file")
        paper_original = originals / "paper-source.pdf"
        shutil.copy2(paper, paper_original)
        pdf = pdfplumber.open(paper)
        require(1 <= len(pdf.pages) <= MAX_PDF_PAGES, f"paper must contain 1-{MAX_PDF_PAGES} pages")
        paper_info = {
            "fileName": paper.name,
            "originalPath": paper_original.relative_to(output).as_posix(),
            "sha256": sha256_file(paper),
            "pageCount": len(pdf.pages),
        }
    targets: list[dict] = []
    used_ids: set[str] = set()
    try:
        for index, source in enumerate(images, start=1):
            reference = uploaded_refs[index - 1] if uploaded_refs else None
            target_id = f"fig-{reference:02d}" if reference else f"image-{index:03d}"
            require(target_id not in used_ids, f"duplicate target: {target_id}")
            used_ids.add(target_id)
            original_name = f"{target_id}-original{source.suffix.lower() or '.bin'}"
            original_copy = originals / original_name
            require(source.is_file() and not source.is_symlink(), f"image does not exist or is symlinked: {source}")
            shutil.copy2(source, original_copy)
            reference_text = f"Fig. {reference}" if reference else None
            label = reference_text or source.stem
            normalized = figures_dir / f"{target_id} - {safe_filename(label, fallback=target_id, limit=140)}.png"
            normalize_uploaded_image(source, normalized, args.dpi)
            mode = "paper-with-images" if paper else "images-only"
            notes = ["User-supplied image preserved byte-for-byte in originals/."]
            matched_caption = None
            matched_page = None
            if pdf is not None and reference is not None:
                caption_matches = []
                for page_index, candidate_page in enumerate(pdf.pages, start=1):
                    result = caption_for(candidate_page, reference)
                    if result:
                        caption_matches.append((page_index, result[0]))
                if len(caption_matches) == 1:
                    matched_page, matched_caption = caption_matches[0]
                    notes.append("Figure reference and authoritative caption matched to the supplied paper; verify the uploaded pixels visually.")
                elif not caption_matches:
                    notes.append("The supplied figure reference was not found in the paper; identity remains unresolved until QA.")
                else:
                    notes.append("The supplied figure reference occurs more than once; resolve its paper identity during QA.")
            if paper and not reference:
                notes.append("Figure identity must be matched against the supplied paper during visual QA.")
            # A unique paper caption makes this a strong candidate, but the
            # uploaded pixels are not the paper figure until visual QA attests
            # that identity through --verify-manifest.
            identity_status = "unresolved" if paper else "not-applicable"
            workflow = "image-derived-reconstruction"
            targets.append(target_record(
                target_id=target_id,
                acquisition_mode=mode,
                workflow_mode=workflow,
                identity_status=identity_status,
                requested_as=source.name,
                normalized_path=normalized,
                original_path=original_copy,
                output=output,
                source_sha256=sha256_file(original_copy),
                source_file_name=source.name,
                caption=matched_caption,
                figure_reference=reference_text,
                page=matched_page,
                crop_box=None,
                dpi=args.dpi,
                caption_included=False,
                qa_status="needs-review",
                notes=notes,
            ))

        if figure_numbers:
            require(pdf is not None and paper is not None, "paper could not be opened")
            with tempfile.TemporaryDirectory(prefix="scirepro-targets-") as temporary:
                temporary_dir = Path(temporary)
                rendered_pages: Dict[int, Path] = {}
                for figure_number in figure_numbers:
                    target_id = f"fig-{figure_number:02d}"
                    require(target_id not in used_ids, f"duplicate target: {target_id}")
                    used_ids.add(target_id)
                    matches: list[tuple[int, str, tuple[float, float, float, float]]] = []
                    for page_index, page in enumerate(pdf.pages, start=1):
                        result = caption_for(page, figure_number)
                        if result:
                            matches.append((page_index, result[0], result[1]))
                    require(matches, f"Fig. {figure_number} caption was not found in the paper")
                    require(len(matches) == 1, f"Fig. {figure_number} matched multiple paper pages; use a reviewed manual crop")
                    page_number, caption, caption_bbox = matches[0]
                    page = pdf.pages[page_number - 1]
                    estimated_pixels = (float(page.width) * args.dpi / 72) * (float(page.height) * args.dpi / 72)
                    require(estimated_pixels <= MAX_RENDER_PIXELS, f"Fig. {figure_number}: rendered page would exceed {MAX_RENDER_PIXELS} pixels")
                    rendered = rendered_pages.get(page_number)
                    if rendered is None:
                        rendered = run_pdftoppm(
                            paper, page_number, args.dpi, temporary_dir / f"page-{page_number}"
                        )
                        rendered_pages[page_number] = rendered
                    with Image.open(rendered) as opened:
                        page_image = opened.convert("RGB")
                    scale_x = page_image.width / float(page.width)
                    scale_y = page_image.height / float(page.height)
                    x0_pt, x1_pt = column_bounds(float(page.width), caption_bbox)
                    # Add a small column-side safety margin. Phase 0 values
                    # completeness over tight crops; QA may subsequently trim
                    # whitespace, but must never recreate clipped labels.
                    safety_pt = min(5.0, float(page.width) * 0.009)
                    x0_pt = max(0.0, x0_pt - safety_pt)
                    x1_pt = min(float(page.width), x1_pt + safety_pt)
                    x0_px = max(0, round(x0_pt * scale_x))
                    x1_px = min(page_image.width, round(x1_pt * scale_x))
                    caption_top_px = max(0, round(caption_bbox[1] * scale_y))
                    top_px = detect_figure_top(page_image, x0_px, x1_px, caption_top_px, args.dpi)
                    pad_px = max(8, round(args.dpi * 0.045))
                    bottom_px = min(page_image.height, round(caption_bbox[3] * scale_y) + pad_px)
                    top_with_pad = max(0, top_px - pad_px)
                    x0_px, x1_px = tighten_horizontal_bounds(
                        page_image, x0_px, x1_px, top_with_pad, bottom_px, args.dpi
                    )
                    crop_px = (x0_px, top_with_pad, x1_px, bottom_px)
                    require(crop_px[2] > crop_px[0] and crop_px[3] > crop_px[1], f"Fig. {figure_number}: invalid crop")
                    cropped = page_image.crop(crop_px)
                    file_stem = safe_filename(caption, fallback=f"Fig. {figure_number}", limit=140)
                    original_crop = originals / f"{target_id} - {file_stem}.png"
                    cropped.save(original_crop, format="PNG", dpi=(args.dpi, args.dpi))
                    normalized = figures_dir / f"{target_id} - {file_stem}.png"
                    cropped.save(normalized, format="PNG", dpi=(args.dpi, args.dpi), optimize=True)
                    render_qa_overlay(page_image, crop_px, qa_dir / f"{target_id}-crop-overlay.png")
                    crop_points = [
                        round(crop_px[0] / scale_x, 3),
                        round(crop_px[1] / scale_y, 3),
                        round(crop_px[2] / scale_x, 3),
                        round(crop_px[3] / scale_y, 3),
                    ]
                    targets.append(target_record(
                        target_id=target_id,
                        acquisition_mode="paper-with-figure-references",
                        workflow_mode="scientific-reproduction",
                        identity_status="resolved",
                        requested_as=f"Fig. {figure_number}",
                        normalized_path=normalized,
                        original_path=original_crop,
                        output=output,
                        source_sha256=sha256_file(original_crop),
                        source_file_name=paper.name,
                        caption=caption,
                        figure_reference=f"Fig. {figure_number}",
                        page=page_number,
                        crop_box=crop_points,
                        dpi=args.dpi,
                        caption_included=True,
                        qa_status="needs-review",
                        notes=["Automatically extracted from the supplied paper; inspect qa/ before verification."],
                    ))
    finally:
        if pdf is not None:
            pdf.close()

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "targetSetId": args.target_set_id,
        "createdAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "paper": paper_info,
        "targetCount": len(targets),
        "targets": targets,
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "json-sort-keys-v1",
            "manifestSha256": "",
        },
    }
    refresh_manifest_integrity(manifest)
    validate_manifest(manifest, root=output)
    write_json(output / "manifest.json", manifest)
    return len(targets)


def materialize(args: argparse.Namespace) -> int:
    final_output = checked_user_path(args.output, "output directory", must_exist=False)
    require(
        not final_output.exists() or (final_output.is_dir() and not any(final_output.iterdir())),
        "output directory must be new or empty",
    )
    preflight_acquisition(args)
    final_output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{final_output.name}.staging-", dir=final_output.parent))
    committed = False
    try:
        target_count = materialize_into(args, staging)
        if final_output.exists():
            # The preflight guaranteed this is an empty directory.  Keep it in
            # place until every artifact and manifest hash has validated.
            final_output.rmdir()
        staging.replace(final_output)
        committed = True
    finally:
        if not committed and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    print(json.dumps({
        "status": "ok",
        "output": str(final_output),
        "targets": target_count,
        "manifest": str(final_output / "manifest.json"),
    }, ensure_ascii=False))
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, help="New target workspace directory.")
    cli.add_argument("--target-set-id", default="targets-current", help="Stable target-set identifier.")
    cli.add_argument("--paper", type=Path, help="Source paper PDF.")
    cli.add_argument("--figures", help="Comma-separated figure numbers and ranges, for example 1,3,5-8.")
    cli.add_argument("--image", action="append", default=[], type=Path, help="Uploaded target image; repeat for multiple images.")
    cli.add_argument("--uploaded-figure-refs", help="Optional comma-separated figure numbers matching repeated --image arguments.")
    cli.add_argument("--dpi", type=int, default=300, help="Normalization/rendering DPI (default: 300).")
    cli.add_argument("--verify-manifest", type=Path, help="Mark reviewed target crops as verified instead of acquiring targets.")
    cli.add_argument("--verify-targets", help="Comma-separated target IDs that were visually reviewed.")
    cli.add_argument("--verify-all", action="store_true", help="Verify every manifest target after reviewing the complete set.")
    cli.add_argument("--verified-caption-included", action="store_true", help="Record that the reviewed uploaded targets contain the complete original caption.")
    cli.add_argument("--replace-manifest", type=Path, help="Replace one rejected automatic crop in an existing manifest.")
    cli.add_argument("--replace-target", help="Target ID to replace when using --replace-manifest.")
    cli.add_argument("--replacement-image", type=Path, help="Reviewed replacement image for --replace-target.")
    cli.add_argument("--bind-manifest", type=Path, help="Bind one uploaded paper target to reviewed paper metadata.")
    cli.add_argument("--bind-target", help="Target ID to bind when using --bind-manifest.")
    cli.add_argument("--paper-figure-ref", type=int, help="Positive paper figure number for identity binding.")
    cli.add_argument("--paper-page", type=int, help="Optional one-based paper page for an ambiguous identity binding.")
    return cli


def main() -> int:
    args = parser().parse_args()
    try:
        special_modes = sum(bool(value) for value in (args.replace_manifest, args.verify_manifest, args.bind_manifest))
        require(special_modes <= 1, "choose only one acquisition, replacement, verification, or binding mode")
        if args.bind_manifest:
            require(
                args.output is None and args.paper is None and not args.image and args.figures is None
                and args.uploaded_figure_refs is None and args.replace_manifest is None
                and args.verify_manifest is None and not args.verify_targets and not args.verify_all
                and not args.verified_caption_included and args.replace_target is None
                and args.replacement_image is None,
                "identity-binding mode cannot acquire, replace, or verify targets",
            )
            require(args.bind_target, "identity-binding mode requires --bind-target")
            require(
                isinstance(args.paper_figure_ref, int) and args.paper_figure_ref >= 1,
                "identity-binding mode requires a positive --paper-figure-ref",
            )
            require(args.paper_page is None or args.paper_page >= 1, "--paper-page must be positive")
            return bind_uploaded_identity(
                args.bind_manifest, args.bind_target, args.paper_figure_ref, args.paper_page
            )
        if args.replace_manifest:
            require(
                args.output is None and args.paper is None and not args.image and args.figures is None
                and args.uploaded_figure_refs is None and args.verify_manifest is None
                and not args.verify_targets and not args.verify_all and not args.verified_caption_included
                and args.bind_manifest is None and args.bind_target is None
                and args.paper_figure_ref is None and args.paper_page is None,
                "replacement mode cannot acquire or verify targets",
            )
            require(args.replace_target and args.replacement_image, "replacement mode requires --replace-target and --replacement-image")
            require(72 <= args.dpi <= 600, "--dpi must be between 72 and 600")
            return replace_target(args.replace_manifest, args.replace_target, args.replacement_image, args.dpi)
        if args.verify_manifest:
            require(
                args.output is None and args.paper is None and not args.image and args.figures is None
                and args.uploaded_figure_refs is None and args.replace_manifest is None
                and args.replace_target is None and args.replacement_image is None
                and args.bind_manifest is None and args.bind_target is None
                and args.paper_figure_ref is None and args.paper_page is None,
                "verification mode cannot acquire, replace, or bind targets",
            )
            require(not (args.verify_targets and args.verify_all), "choose --verify-targets or --verify-all, not both")
            require(args.verify_targets or args.verify_all, "verification requires --verify-targets or explicit --verify-all")
            selected = [item.strip() for item in (args.verify_targets or "").split(",") if item.strip()]
            if args.verify_all:
                verified_manifest_path = checked_user_path(args.verify_manifest, "target manifest", must_exist=True)
                manifest = json.loads(verified_manifest_path.read_text(encoding="utf-8"))
                selected = sorted(validate_manifest(manifest, root=verified_manifest_path.parent))
            return mark_verified(args.verify_manifest, selected, args.verified_caption_included)
        require(
            args.replace_target is None and args.replacement_image is None
            and args.bind_target is None and args.paper_figure_ref is None and args.paper_page is None
            and not args.verify_targets and not args.verify_all and not args.verified_caption_included,
            "mode-specific flags require --replace-manifest, --bind-manifest, or --verify-manifest",
        )
        require(args.output is not None, "--output is required")
        require(72 <= args.dpi <= 600, "--dpi must be between 72 and 600")
        require(TARGET_ID.fullmatch(args.target_set_id) is not None, "invalid --target-set-id")
        return materialize(args)
    except (OSError, json.JSONDecodeError, TargetError) as exc:
        print(f"SciRepro target acquisition failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
