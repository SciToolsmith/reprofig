#!/usr/bin/env python3
"""Small create-only output helper shared by SciRepro inspection scripts."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class SafeOutputError(ValueError):
    pass


def checked_directory_create_only(raw: Path) -> Path:
    """Create/check a directory path without following user-controlled links."""
    expanded = raw.expanduser()
    absolute = Path(os.path.abspath(os.fspath(expanded)))
    cursor = Path(absolute.anchor)
    parts = absolute.parts[1:]
    for index, part in enumerate(parts, start=1):
        candidate = cursor / part
        if os.path.lexists(candidate):
            if candidate.is_symlink():
                # macOS exposes /tmp, /var, and /etc through root-level aliases.
                if index == 1 and candidate.parent == Path(candidate.anchor):
                    try:
                        resolved = candidate.resolve(strict=True)
                    except OSError as exc:
                        raise SafeOutputError(f"output parent alias is unavailable: {candidate}") from exc
                    if not resolved.is_dir():
                        raise SafeOutputError(f"output parent alias is not a directory: {candidate}")
                    cursor = resolved
                    continue
                raise SafeOutputError(f"output path may not contain symlink components: {candidate}")
            if not candidate.is_dir():
                raise SafeOutputError(f"output parent is not a directory: {candidate}")
        else:
            try:
                candidate.mkdir(mode=0o700)
            except FileExistsError:
                if candidate.is_symlink() or not candidate.is_dir():
                    raise SafeOutputError(f"output parent is unsafe: {candidate}")
            except OSError as exc:
                raise SafeOutputError(f"could not create output parent: {candidate}") from exc
        cursor = candidate
    return cursor


def _checked_parent(raw: Path) -> tuple[Path, Path]:
    expanded = raw.expanduser()
    absolute = Path(os.path.abspath(os.fspath(expanded)))
    if not absolute.name:
        raise SafeOutputError("output must name a file")
    parent = checked_directory_create_only(absolute.parent)
    return parent, parent / absolute.name


def write_text_create_only(raw: Path, payload: str) -> Path:
    """Atomically create one text file without following or replacing links."""
    parent, destination = _checked_parent(raw)
    if os.path.lexists(destination):
        raise SafeOutputError(f"output already exists: {destination.name}")

    descriptor, temporary_raw = tempfile.mkstemp(
        prefix=f".{destination.name}.staging-", dir=parent
    )
    temporary = Path(temporary_raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise SafeOutputError(f"output already exists: {destination.name}") from exc
        except OSError as exc:
            raise SafeOutputError(f"could not publish output: {destination.name}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return destination
