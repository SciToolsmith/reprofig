#!/usr/bin/env python3
"""Ensure the pinned SciDiagram companion skill is safely available."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


SKILL_NAME = "sci-diagram-pptx"
SOURCE_REPO = "SciToolsmith/sci-diagram-pptx"
SOURCE_PATH = "skills/sci-diagram-pptx"
SOURCE_REF = "26a2ae281df4209fa9687ca80d27a3aa7feb1ee3"
SOURCE_URL = f"https://github.com/{SOURCE_REPO}/tree/{SOURCE_REF}/{SOURCE_PATH}"
INSTALL_METHOD = "download"
REQUIRED_FILES = (
    "SKILL.md",
    "LICENSE",
    "agents/openai.yaml",
    "references/runtime-artifact-tool.md",
    "references/runtime-pptxgenjs.md",
    "scripts/check_pptx.py",
    "scripts/panel_crop.py",
    "scripts/probe_runtime.mjs",
    "scripts/render_pptx.py",
)
FRONTMATTER_NAME = re.compile(r"(?m)^name:\s*sci-diagram-pptx\s*$")


class CompanionError(RuntimeError):
    """Raised when the companion cannot be trusted or installed safely."""


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    path = Path(configured).expanduser() if configured else Path.home() / ".codex"
    if not path.is_absolute():
        raise CompanionError("CODEX_HOME must be an absolute path")
    return path


def reject_symlink_or_wrong_type(path: Path, *, expected: str) -> None:
    if path.is_symlink():
        raise CompanionError(f"refusing symlink at {path}")
    if expected == "directory" and not path.is_dir():
        raise CompanionError(f"expected directory at {path}")
    if expected == "file" and not path.is_file():
        raise CompanionError(f"required file is missing or invalid: {path}")


def validate_skill(skill_dir: Path) -> None:
    reject_symlink_or_wrong_type(skill_dir, expected="directory")
    for relative in REQUIRED_FILES:
        candidate = skill_dir / relative
        reject_symlink_or_wrong_type(candidate, expected="file")

    skill_md = skill_dir / "SKILL.md"
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CompanionError(f"cannot read {skill_md}") from exc
    if not text.startswith("---\n"):
        raise CompanionError("companion SKILL.md has no YAML frontmatter")
    closing = text.find("\n---\n", 4)
    if closing < 0 or not FRONTMATTER_NAME.search(text[4:closing]):
        raise CompanionError("companion SKILL.md has an unexpected name")


def installer_path(home: Path) -> Path:
    return home / "skills" / ".system" / "skill-installer" / "scripts" / "install-skill-from-github.py"


def safe_process_detail(value: str) -> str:
    detail = " ".join(value.split())
    return detail[:500]


def install_companion(home: Path, skills_root: Path) -> None:
    installer = installer_path(home)
    reject_symlink_or_wrong_type(installer, expected="file")
    command = [
        sys.executable,
        str(installer),
        "--repo",
        SOURCE_REPO,
        "--path",
        SOURCE_PATH,
        "--ref",
        SOURCE_REF,
        "--dest",
        str(skills_root),
        "--name",
        SKILL_NAME,
        "--method",
        INSTALL_METHOD,
    ]
    installer_env = os.environ.copy()
    installer_env.pop("GITHUB_TOKEN", None)
    installer_env.pop("GH_TOKEN", None)
    try:
        completed = subprocess.run(
            command,
            env=installer_env,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CompanionError("companion installer could not complete") from exc
    if completed.returncode != 0:
        detail = safe_process_detail(completed.stderr) or f"exit {completed.returncode}"
        raise CompanionError(f"companion installation failed: {detail}")


def result(skill_dir: Path, *, installed_this_run: bool) -> dict[str, object]:
    return {
        "status": "installed" if installed_this_run else "ready",
        "skillDir": str(skill_dir),
        "source": SOURCE_URL if installed_this_run else "existing-user-managed",
        "ref": SOURCE_REF if installed_this_run else None,
        "installedThisRun": installed_this_run,
    }


def main() -> int:
    try:
        home = codex_home()
        skills_root = home / "skills"
        skill_dir = skills_root / SKILL_NAME

        if skill_dir.exists() or skill_dir.is_symlink():
            validate_skill(skill_dir)
            print(json.dumps(result(skill_dir, installed_this_run=False), separators=(",", ":")))
            return 0

        if skills_root.exists() or skills_root.is_symlink():
            reject_symlink_or_wrong_type(skills_root, expected="directory")

        install_companion(home, skills_root)
        if not (skill_dir.exists() or skill_dir.is_symlink()):
            raise CompanionError("installer reported success but the companion directory is missing")
        validate_skill(skill_dir)
        print(json.dumps(result(skill_dir, installed_this_run=True), separators=(",", ":")))
        return 0
    except CompanionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
