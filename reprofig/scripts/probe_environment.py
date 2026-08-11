#!/usr/bin/env python3
"""Privacy-preserving discovery of local runtimes and hardware for ReproFig."""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path


SENSITIVE_KEY = re.compile(r"(?i)(?:authorization|cookie|credential|password|secret|session|token)")
SENSITIVE_QUERY = re.compile(
    r"(?i)([?&](?:access[_-]?key|api[_-]?key|auth|credential|password|secret|signature|sig|token)=)[^&#\s]+"
)
URI_USERINFO = re.compile(r"(?i)(https?://)[^/@\s]+@")
UNIX_USER_PATH = re.compile(r"/(?:Users|home)/[^/\s\"']+")
WINDOWS_USER_PATH = re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"']+")
MATLAB_RELEASE = re.compile(r"(?i)(?:MATLAB[_-])?(R\d{4}[ab])")


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def display_path(value: str | Path, workspace: Path) -> str:
    """Return a stable placeholder path that does not expose a username."""
    path = Path(value).expanduser().resolve()
    roots = [
        (workspace, "$WORKSPACE"),
        (Path.home(), "$HOME"),
        (Path("/Applications"), "$APPLICATIONS"),
        (Path("/usr/local"), "$USR_LOCAL"),
        (Path("/opt"), "$OPT"),
        (Path("/usr"), "$USR"),
        (Path("/bin"), "$BIN"),
    ]
    for root, label in roots:
        try:
            relative = path.relative_to(root.resolve())
        except (OSError, ValueError):
            continue
        return label if str(relative) == "." else f"{label}/{relative.as_posix()}"
    return f"$SYSTEM/{path.name}"


def redact_text(value: str, workspace: Path) -> str:
    replacements = [
        (str(workspace), "$WORKSPACE"),
        (workspace.as_posix(), "$WORKSPACE"),
        (str(Path.home()), "$HOME"),
        (Path.home().as_posix(), "$HOME"),
    ]
    result = value
    for raw, placeholder in sorted(set(replacements), key=lambda item: len(item[0]), reverse=True):
        if raw:
            result = result.replace(raw, placeholder)
            result = result.replace(json.dumps(raw)[1:-1], placeholder)
    result = UNIX_USER_PATH.sub("/$USER", result)
    result = WINDOWS_USER_PATH.sub(r"C:\\Users\\$USER", result)
    result = URI_USERINFO.sub(r"\1[REDACTED]@", result)
    result = SENSITIVE_QUERY.sub(r"\1[REDACTED]", result)
    return result


def redact_value(value: object, workspace: Path, key: str | None = None) -> object:
    if key and SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: redact_value(item, workspace, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, workspace) for item in value]
    if isinstance(value, str):
        return redact_text(value, workspace)
    return value


def minimal_environment() -> dict[str, str]:
    """Do not expose the caller's credentials, HOME, or project environment."""
    env = {
        "PATH": os.defpath,
        "LANG": "C",
        "LC_ALL": "C",
        "NO_COLOR": "1",
        "PAGER": "cat",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "R_ENVIRON_USER": os.devnull,
        "R_PROFILE_USER": os.devnull,
    }
    for name in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    return env


def public_command(cmd: list[str], workspace: Path) -> list[str]:
    result = list(cmd)
    if result and Path(result[0]).is_absolute():
        result[0] = display_path(result[0], workspace)
    return [redact_text(item, workspace) for item in result]


def run(cmd: list[str], timeout: int, workspace: Path) -> dict:
    public_cmd = public_command(cmd, workspace)
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=minimal_environment(),
        )
        report = {
            "command": public_cmd,
            "returncode": result.returncode,
            "stdout": result.stdout.strip()[:4000],
            "stderr": result.stderr.strip()[:2000],
            "timedOut": False,
        }
    except subprocess.TimeoutExpired as exc:
        report = {
            "command": public_cmd,
            "returncode": None,
            "stdout": (exc.stdout or "")[:4000] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[:2000] if isinstance(exc.stderr, str) else "",
            "timedOut": True,
        }
    except OSError as exc:
        report = {
            "command": public_cmd,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "timedOut": False,
        }
    return redact_value(report, workspace)  # type: ignore[return-value]


def unique_existing(paths: list[str]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for raw in paths:
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        if path not in seen and path.is_file():
            seen.add(path)
            result.append(path)
    return result


def same_file(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return left.resolve() == right.resolve()


def conda_metadata_candidates() -> list[str]:
    """Read Conda's inventory file without invoking Conda or its environments."""
    inventory = Path.home() / ".conda" / "environments.txt"
    if not inventory.is_file():
        return []
    try:
        roots = [line.strip() for line in inventory.read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return []
    suffix = Path("python.exe") if os.name == "nt" else Path("bin/python")
    return [str(Path(root) / suffix) for root in roots if root]


def python_candidates(workspace: Path) -> list[dict]:
    current = Path(sys.executable).resolve()
    candidates: list[tuple[str, str, bool]] = [(str(current), "current-interpreter", True)]
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            candidate = Path(found).resolve()
            candidates.append((str(candidate), f"PATH:{name}", same_file(candidate, current)))
    candidates.extend((path, "conda-metadata", False) for path in conda_metadata_candidates())
    for relative in (".venv/bin/python", "venv/bin/python", ".venv/Scripts/python.exe", "venv/Scripts/python.exe"):
        candidates.append((str(workspace / relative), "workspace-virtualenv", False))

    result = []
    seen: set[Path] = set()
    for raw, source, safe_to_probe in candidates:
        path = Path(raw).expanduser().resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        result.append({
            "actualPath": path,
            "source": source,
            "safeToProbe": safe_to_probe and not is_within(path, workspace),
        })
    return result


def matlab_candidates() -> list[Path]:
    paths: list[str] = []
    found = shutil.which("matlab")
    if found:
        paths.append(found)
    patterns = [
        "/Applications/MATLAB_R*.app/bin/matlab",
        str(Path.home() / "Applications/MATLAB_R*.app/bin/matlab"),
        "/usr/local/MATLAB/R*/bin/matlab",
        "/opt/MATLAB/R*/bin/matlab",
    ]
    if os.name == "nt":
        for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if root:
                patterns.append(str(Path(root) / "MATLAB/R*/bin/matlab.exe"))
    for pattern in patterns:
        paths.extend(glob.glob(pattern))
    return unique_existing(paths)


def matlab_static_metadata(candidate: Path) -> dict | None:
    """Read release metadata without launching MATLAB or executing startup.m."""
    metadata: dict[str, str] = {}
    release_match = MATLAB_RELEASE.search(str(candidate))
    if release_match:
        value = release_match.group(1)
        metadata["release"] = f"R{value[1:-1]}{value[-1].lower()}"

    for parent in candidate.parents:
        version_info = parent / "VersionInfo.xml"
        if version_info.is_file():
            try:
                text = version_info.read_text(encoding="utf-8", errors="replace")[:100_000]
            except OSError:
                break
            version_match = re.search(r"<version>([^<]+)</version>", text, re.IGNORECASE)
            release_xml = re.search(r"<release>(R\d{4}[ab])</release>", text, re.IGNORECASE)
            if version_match:
                metadata["version"] = version_match.group(1).strip()
            if release_xml:
                value = release_xml.group(1)
                metadata["release"] = f"R{value[1:-1]}{value[-1].lower()}"
            break
        if parent.suffix.lower() == ".app":
            plist = parent / "Contents" / "Info.plist"
            if plist.is_file():
                try:
                    with plist.open("rb") as handle:
                        payload = plistlib.load(handle)
                    version = payload.get("CFBundleShortVersionString") or payload.get("CFBundleVersion")
                    if version:
                        metadata["version"] = str(version)
                except (OSError, plistlib.InvalidFileException):
                    pass
            break
    return metadata or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--probe-matlab",
        action="store_true",
        help=(
            "R2-gated: inspect static MATLAB release metadata after approval. "
            "This never launches MATLAB, executes startup.m, or consumes a license."
        ),
    )
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    py_entries = []
    python_probe = (
        "import json,platform,sys;"
        "print(json.dumps({'version':platform.python_version(),'implementation':platform.python_implementation(),"
        "'executable':sys.executable,'prefix':sys.prefix,'base_prefix':sys.base_prefix}))"
    )
    for candidate in python_candidates(workspace):
        path = candidate["actualPath"]
        entry = {
            "path": display_path(path, workspace),
            "source": candidate["source"],
            "verified": False,
            "details": None,
            "probe": None,
        }
        if candidate["safeToProbe"]:
            probe = run([str(path), "-I", "-S", "-c", python_probe], args.timeout, workspace)
            entry["probe"] = probe
            if probe["returncode"] == 0:
                try:
                    details = json.loads(probe["stdout"].splitlines()[-1])
                    for key in ("executable", "prefix", "base_prefix"):
                        if details.get(key):
                            raw_path = details[key]
                            public_path = display_path(raw_path, workspace)
                            probe["stdout"] = probe["stdout"].replace(raw_path, public_path)
                            details[key] = public_path
                    entry["details"] = details
                    entry["verified"] = True
                except (json.JSONDecodeError, IndexError, TypeError):
                    pass
        else:
            entry["probeSkipped"] = "Untrusted or non-current interpreter; static discovery only."
        py_entries.append(entry)

    matlab_entries = []
    for candidate in matlab_candidates():
        entry = {
            "path": display_path(candidate, workspace),
            "verified": False,
            "version": None,
            "release": None,
            "probe": None,
        }
        if args.probe_matlab:
            metadata = matlab_static_metadata(candidate)
            entry["probe"] = {
                "mode": "static-metadata",
                "gated": True,
                "startupExecuted": False,
                "licenseConsumed": False,
            }
            if metadata:
                entry.update(metadata)
                entry["verified"] = True
        else:
            entry["probeSkipped"] = "Static MATLAB metadata probe requires explicit R2 approval."
        matlab_entries.append(entry)

    other = []
    commands = {
        "R": ["R", "--vanilla", "--version"],
        "Rscript": ["Rscript", "--vanilla", "--version"],
        "Julia": ["julia", "--startup-file=no", "--history-file=no", "--version"],
        "GNU Octave": ["octave", "--no-init-file", "--no-site-file", "--version"],
        "Node.js": ["node", "--version"],
        "NVIDIA": ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
    }
    for label, cmd in commands.items():
        executable = shutil.which(cmd[0])
        if not executable:
            continue
        path = Path(executable).resolve()
        entry = {"label": label, "path": display_path(path, workspace), "verified": False, "probe": None}
        if is_within(path, workspace):
            entry["probeSkipped"] = "Workspace-controlled executable; static discovery only."
        else:
            probe = run([str(path), *cmd[1:]], args.timeout, workspace)
            entry["probe"] = probe
            entry["verified"] = probe["returncode"] == 0
        other.append(entry)

    disk = shutil.disk_usage(workspace)
    report = {
        "schemaVersion": "reprofig.environment/v1",
        "workspace": "$WORKSPACE",
        "privacy": {
            "pathsRedacted": True,
            "environmentPolicy": "minimal-allowlist",
            "workspaceExecutablesRun": False,
        },
        "system": {
            "platform": platform.platform(),
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpuCount": os.cpu_count(),
            "disk": {"totalBytes": disk.total, "usedBytes": disk.used, "freeBytes": disk.free},
        },
        "python": py_entries,
        "matlab": matlab_entries,
        "other": other,
        "notes": [
            "Discovery cannot prove absence from every custom location.",
            "Workspace and non-current Python interpreters are listed but never executed automatically.",
            "--probe-matlab reads static metadata only; MATLAB is never launched by this script.",
            "Verify required packages, toolboxes, licenses, and hardware separately for each approved route.",
        ],
    }
    payload = json.dumps(redact_value(report, workspace), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
