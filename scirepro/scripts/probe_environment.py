#!/usr/bin/env python3
"""Privacy-preserving discovery of local runtimes and hardware for SciRepro."""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import plistlib
import re
import shutil
import stat
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
RUNTIME_CHOICES = {"python", "matlab", "r", "rscript", "julia", "octave", "node", "nvidia"}
MAX_PROBE_TIMEOUT_SECONDS = 60
NATIVE_EXECUTABLE_MAGICS = {
    b"\x7fELF",  # ELF
    b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",  # Mach-O, big endian
    b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",  # Mach-O, little endian
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",  # universal Mach-O
    b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",  # universal Mach-O 64
}


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def is_lexically_within(path: Path, root: Path) -> bool:
    """Check containment without following a selected executable symlink."""
    try:
        lexical_absolute(path).relative_to(lexical_absolute(root))
        return True
    except ValueError:
        return False


def lexical_absolute(path: Path) -> Path:
    """Normalize dot segments without resolving the final symlink."""
    expanded = path.expanduser()
    raw = expanded if expanded.is_absolute() else Path.cwd() / expanded
    return Path(os.path.normpath(str(raw)))


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


def display_invocation_path(value: str | Path, workspace: Path) -> str:
    """Redact a launcher path while preserving its lexical venv identity."""
    path = lexical_absolute(Path(value))
    roots = [
        (workspace.absolute(), "$WORKSPACE"),
        (Path.home().absolute(), "$HOME"),
        (Path("/Applications"), "$APPLICATIONS"),
        (Path("/usr/local"), "$USR_LOCAL"),
        (Path("/opt"), "$OPT"),
        (Path("/usr"), "$USR"),
        (Path("/bin"), "$BIN"),
    ]
    for root, label in roots:
        try:
            relative = path.relative_to(root)
        except ValueError:
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
        result[0] = display_invocation_path(result[0], workspace)
    return [redact_text(item, workspace) for item in result]


def run(cmd: list[str], timeout: int, workspace: Path, *, return_raw: bool = False) -> dict | tuple[dict, str]:
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
    raw_stdout = report["stdout"]
    redacted = redact_value(report, workspace)  # type: ignore[assignment]
    return (redacted, raw_stdout) if return_raw else redacted  # type: ignore[return-value]


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
    candidates: list[tuple[str, str]] = [(sys.executable, "current-interpreter")]
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append((found, f"PATH:{name}"))
    candidates.extend((path, "conda-metadata") for path in conda_metadata_candidates())
    for relative in (".venv/bin/python", "venv/bin/python", ".venv/Scripts/python.exe", "venv/Scripts/python.exe"):
        candidates.append((str(workspace / relative), "workspace-virtualenv"))

    result = []
    seen: set[Path] = set()
    for raw, source in candidates:
        path = lexical_absolute(Path(raw))
        if path in seen or not path.is_file():
            continue
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        seen.add(path)
        result.append({
            "invocationPath": path,
            "resolvedPath": resolved,
            "source": source,
        })
    return result


def is_native_executable(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(4)
    except OSError:
        return False
    return header in NATIVE_EXECUTABLE_MAGICS or header[:2] == b"MZ"


def workspace_venv_root(invocation: Path) -> Path | None:
    if invocation.parent.name.lower() not in {"bin", "scripts"}:
        return None
    if not re.fullmatch(r"(?i)python(?:\d+(?:\.\d+)*)?(?:\.exe)?", invocation.name):
        return None
    return invocation.parent.parent


def selected_python_executable(raw: str, workspace: Path, allow_workspace: bool) -> dict:
    """Validate one explicitly selected native Python launcher without running it."""
    supplied = Path(raw)
    if not supplied.is_absolute():
        raise ValueError("must be an absolute path")
    candidate = lexical_absolute(supplied)
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise ValueError("does not identify an accessible executable file") from exc
    if not (stat.S_ISLNK(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
        raise ValueError("must identify a regular executable or symlink launcher")
    if not os.access(candidate, os.X_OK):
        raise ValueError("is not executable")

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("does not identify a stable executable file") from exc
    try:
        resolved_metadata = resolved.lstat()
    except OSError as exc:
        raise ValueError("does not resolve to an accessible executable file") from exc
    if stat.S_ISLNK(resolved_metadata.st_mode) or not stat.S_ISREG(resolved_metadata.st_mode):
        raise ValueError("must resolve to a regular non-symlink executable")

    workspace_controlled = is_lexically_within(candidate, workspace) or is_within(resolved, workspace)
    venv_root = workspace_venv_root(candidate) if workspace_controlled else None
    if workspace_controlled and not allow_workspace:
        raise ValueError("is workspace-controlled; pass --allow-workspace-python to probe it")
    if workspace_controlled:
        if venv_root is None:
            raise ValueError("must be a standard workspace PEP 405 virtual-environment launcher")
        config = venv_root / "pyvenv.cfg"
        try:
            config_metadata = config.lstat()
        except OSError as exc:
            raise ValueError("requires a regular non-symlink pyvenv.cfg") from exc
        if stat.S_ISLNK(config_metadata.st_mode) or not stat.S_ISREG(config_metadata.st_mode):
            raise ValueError("requires a regular non-symlink pyvenv.cfg")

    if not is_native_executable(resolved):
        raise ValueError("must resolve to a native Python executable")

    return {
        "invocationPath": candidate,
        "resolvedPath": resolved,
        "workspaceControlled": workspace_controlled,
        "venvRoot": venv_root,
    }


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
        "--runtime",
        action="append",
        choices=sorted(RUNTIME_CHOICES | {"all"}),
        help=(
            "Probe only a runtime required by a candidate route; repeat for multiple runtimes. "
            "Defaults to python. Use all only for an explicitly requested inventory."
        ),
    )
    parser.add_argument(
        "--probe-matlab",
        action="store_true",
        help=(
            "Inspect static MATLAB release metadata without launching MATLAB. "
            "This never launches MATLAB, executes startup.m, or consumes a license."
        ),
    )
    parser.add_argument(
        "--python-executable",
        action="append",
        metavar="/ABSOLUTE/PATH/TO/PYTHON",
        help=(
            "Explicitly opt in to a bounded live probe of an existing Python interpreter; "
            "repeat to probe more than one. The path must be an absolute regular native "
            "executable or symlink launcher. Workspace PEP 405 environments require the "
            "separate --allow-workspace-python gate."
        ),
    )
    parser.add_argument(
        "--allow-workspace-python",
        action="store_true",
        help=(
            "Allow explicitly selected standard PEP 405 Python environments inside the workspace. "
            "This has no effect on automatic discovery and requires --python-executable."
        ),
    )
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    workspace = lexical_absolute(args.workspace)
    if not 1 <= args.timeout <= MAX_PROBE_TIMEOUT_SECONDS:
        parser.error(f"--timeout must be between 1 and {MAX_PROBE_TIMEOUT_SECONDS} seconds")
    selected_runtimes = set(args.runtime or ["python"])
    if "all" in selected_runtimes:
        selected_runtimes = set(RUNTIME_CHOICES)
    if args.probe_matlab:
        selected_runtimes.add("matlab")
    if args.python_executable:
        selected_runtimes.add("python")
    if args.allow_workspace_python and not args.python_executable:
        parser.error("--allow-workspace-python requires --python-executable")

    explicitly_selected_python: list[dict] = []
    selected_seen: set[Path] = set()
    for raw in args.python_executable or []:
        try:
            candidate = selected_python_executable(raw, workspace, args.allow_workspace_python)
        except ValueError as exc:
            parser.error(f"--python-executable {exc}")
        invocation = candidate["invocationPath"]
        if invocation not in selected_seen:
            selected_seen.add(invocation)
            explicitly_selected_python.append(candidate)

    py_entries = []
    python_probe = (
        "import json,platform,sys;"
        "print(json.dumps({'version':platform.python_version(),'implementation':platform.python_implementation(),"
        "'executable':sys.executable,'prefix':sys.prefix,'base_prefix':sys.base_prefix,"
        "'isolation':{'isolated':bool(sys.flags.isolated),'no_site':bool(sys.flags.no_site),"
        "'no_user_site':bool(sys.flags.no_user_site),"
        "'ignore_environment':bool(sys.flags.ignore_environment)}}))"
    )
    py_entries_by_path: dict[Path, dict] = {}
    for candidate in python_candidates(workspace) if "python" in selected_runtimes else []:
        invocation = candidate["invocationPath"]
        resolved = candidate["resolvedPath"]
        entry = {
            "path": display_invocation_path(invocation, workspace),
            "invocationPath": display_invocation_path(invocation, workspace),
            "resolvedPath": display_path(resolved, workspace),
            "source": candidate["source"],
            "explicitSelection": False,
            "workspaceControlled": is_lexically_within(invocation, workspace) or is_within(resolved, workspace),
            "pep405Root": None,
            "pep405Identity": None,
            "verificationStatus": "available",
            "verified": False,
            "verificationScope": "static-discovery-only",
            "binaryProbeStatus": "not-run",
            "siteRuntimeVerified": False,
            "packagesVerified": False,
            "details": None,
            "probe": None,
            "probeSkipped": "Automatic Python discovery is static-only; select an absolute executable to probe it.",
        }
        py_entries.append(entry)
        py_entries_by_path[invocation] = entry

    for selection in explicitly_selected_python:
        invocation = selection["invocationPath"]
        resolved = selection["resolvedPath"]
        venv_root = selection["venvRoot"]
        entry = py_entries_by_path.get(invocation)
        if entry is None:
            entry = {
                "path": display_invocation_path(invocation, workspace),
                "invocationPath": display_invocation_path(invocation, workspace),
                "resolvedPath": display_path(resolved, workspace),
                "source": "explicit-selection",
                "explicitSelection": True,
                "workspaceControlled": selection["workspaceControlled"],
                "pep405Root": display_path(venv_root, workspace) if venv_root else None,
                "pep405Identity": None,
                "verificationStatus": "failed",
                "verified": False,
                "verificationScope": "interpreter-binary-no-site",
                "binaryProbeStatus": "failed",
                "siteRuntimeVerified": False,
                "packagesVerified": False,
                "details": None,
                "probe": None,
            }
            py_entries.append(entry)
            py_entries_by_path[invocation] = entry
        else:
            entry["explicitSelection"] = True
            entry["resolvedPath"] = display_path(resolved, workspace)
            entry["workspaceControlled"] = selection["workspaceControlled"]
            entry["pep405Root"] = display_path(venv_root, workspace) if venv_root else None
            entry["verificationScope"] = "interpreter-binary-no-site"
            entry["binaryProbeStatus"] = "failed"
            entry["siteRuntimeVerified"] = False
            entry["packagesVerified"] = False
            entry.pop("probeSkipped", None)

        if venv_root is not None:
            entry["pep405Identity"] = {
                "status": "detected-static",
                "root": display_invocation_path(venv_root, workspace),
                "marker": display_invocation_path(venv_root / "pyvenv.cfg", workspace),
                "launcherShapeVerified": True,
                "markerRegularNonSymlink": True,
            }

        probe, raw_stdout = run(
            [str(invocation), "-I", "-S", "-c", python_probe],
            args.timeout,
            workspace,
            return_raw=True,
        )
        entry["probe"] = probe
        if probe["returncode"] != 0 or probe["timedOut"]:
            entry["verificationStatus"] = "failed"
            entry["binaryProbeStatus"] = "failed"
            entry["failureReason"] = "probe-timed-out" if probe["timedOut"] else "probe-command-failed"
            continue
        try:
            details = json.loads(raw_stdout.splitlines()[-1])
            if not isinstance(details, dict):
                raise ValueError("probe output is not an object")
            isolation = details.get("isolation", {})
            if not isinstance(isolation, dict) or not all(
                isolation.get(flag) is True
                for flag in ("isolated", "no_site", "no_user_site", "ignore_environment")
            ):
                raise ValueError("missing isolation evidence")
            reported_executable = Path(details["executable"]).resolve(strict=True)
            if not same_file(reported_executable, resolved):
                raise ValueError("reported executable does not match selected native target")
            for key in ("executable", "prefix", "base_prefix"):
                if details.get(key):
                    raw_path = details[key]
                    public_path = (
                        display_invocation_path(raw_path, workspace)
                        if key == "executable"
                        else display_path(raw_path, workspace)
                    )
                    probe["stdout"] = probe["stdout"].replace(raw_path, public_path)
                    details[key] = public_path
            entry["details"] = details
            entry["binaryProbeStatus"] = "verified-no-site"
            if venv_root is None:
                entry["verificationStatus"] = "verified"
                entry["verified"] = True
            else:
                # -S deliberately suppresses PEP 405 activation and all site
                # hooks.  This proves only the native binary can start safely;
                # the venv packages and site runtime remain unexecuted.
                entry["verificationStatus"] = "available"
                entry["verified"] = False
                entry["limitation"] = "PEP 405 identity is static; site runtime and packages were not loaded."
            entry.pop("failureReason", None)
        except (json.JSONDecodeError, IndexError, KeyError, OSError, TypeError, ValueError, AttributeError):
            entry["verificationStatus"] = "failed"
            entry["binaryProbeStatus"] = "failed"
            entry["failureReason"] = "probe-output-invalid"

    matlab_entries = []
    for candidate in matlab_candidates() if "matlab" in selected_runtimes else []:
        entry = {
            "path": display_path(candidate, workspace),
            "installationDetected": True,
            "metadataVerified": False,
            "runtimeVerified": False,
            "verified": False,
            "version": None,
            "release": None,
            "probe": None,
        }
        if args.probe_matlab:
            metadata = matlab_static_metadata(candidate)
            entry["probe"] = {
                "mode": "static-metadata",
                "gated": False,
                "startupExecuted": False,
                "licenseConsumed": False,
                "runtimeVerified": False,
            }
            if metadata:
                entry.update(metadata)
                entry["metadataVerified"] = True
        else:
            entry["probeSkipped"] = "Static MATLAB metadata probe was not requested; installation path only."
        matlab_entries.append(entry)

    other = []
    commands = {
        "r": ("R", ["R", "--vanilla", "--version"]),
        "rscript": ("Rscript", ["Rscript", "--vanilla", "--version"]),
        "julia": ("Julia", ["julia", "--startup-file=no", "--history-file=no", "--version"]),
        "octave": ("GNU Octave", ["octave", "--no-init-file", "--no-site-file", "--version"]),
        "node": ("Node.js", ["node", "--version"]),
        "nvidia": ("NVIDIA", ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
    }
    for runtime_id, (label, cmd) in commands.items():
        if runtime_id not in selected_runtimes:
            continue
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
    workspace_python_probed = any(selection["workspaceControlled"] for selection in explicitly_selected_python)
    report = {
        "schemaVersion": "reprofig.environment/v1",
        "workspace": "$WORKSPACE",
        "privacy": {
            "pathsRedacted": True,
            "environmentPolicy": "minimal-allowlist",
            "workspaceExecutablesRun": workspace_python_probed,
            "workspaceExecutionScope": "explicit-pep405-python-binary-no-site-only" if workspace_python_probed else "none",
            "explicitPythonProbeCount": len(explicitly_selected_python),
        },
        "selectedRuntimes": sorted(selected_runtimes),
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
            "Only runtimes selected for candidate routes are probed unless --runtime all is explicitly used.",
            "Automatic Python discovery is static-only; a live probe requires an explicit --python-executable absolute path.",
            "Explicit Python probes use the selected launcher, a minimal allowlisted environment, -I -S isolation, and a bounded timeout; sitecustomize and site-packages are never loaded.",
            "Workspace Python execution additionally requires --allow-workspace-python; PEP 405 identity is detected statically and the no-site binary probe does not verify the venv runtime or packages.",
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
