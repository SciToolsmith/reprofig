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
GENERIC_UNIX_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9_$:/])/(?!/)[^\s\"'`;(),\[\]{}]+"
)
GENERIC_WINDOWS_ABSOLUTE_PATH = re.compile(
    r"(?i)(?<![A-Za-z0-9_$])[A-Z]:[\\/][^\s\"'`;(),\[\]{}]+"
)
MATLAB_RELEASE = re.compile(r"(?i)(?:MATLAB[_-])?(R\d{4}[ab])")
MATLAB_FUNCTION = re.compile(r"^[A-Za-z]\w*(?:\.[A-Za-z]\w*)*$")
MATLAB_PROBE_MARKER = "SCIREPRO_MATLAB_PROBE_JSON:"
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


def exact_path_replacements(values: list[str | Path], workspace: Path) -> list[tuple[str, str]]:
    """Map task-supplied local paths, including escaped forms, to public labels."""
    replacements: set[tuple[str, str]] = set()
    for value in values:
        path = lexical_absolute(Path(value))
        candidates = [(path, display_invocation_path(path, workspace))]
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            resolved = None
        if resolved is not None:
            candidates.append((resolved, display_path(resolved, workspace)))
        for candidate, placeholder in candidates:
            raw = str(candidate)
            forms = {
                raw: placeholder,
                candidate.as_posix(): placeholder,
                json.dumps(raw)[1:-1]: json.dumps(placeholder)[1:-1],
                raw.replace("'", "''"): placeholder.replace("'", "''"),
            }
            replacements.update((source, target) for source, target in forms.items() if source)
    return sorted(replacements, key=lambda item: len(item[0]), reverse=True)


def redact_text(
    value: str,
    workspace: Path,
    path_replacements: list[tuple[str, str]] | None = None,
) -> str:
    replacements = [
        (str(workspace), "$WORKSPACE"),
        (workspace.as_posix(), "$WORKSPACE"),
        (str(Path.home()), "$HOME"),
        (Path.home().as_posix(), "$HOME"),
    ]
    replacements.extend(path_replacements or [])
    result = value
    for raw, placeholder in sorted(set(replacements), key=lambda item: len(item[0]), reverse=True):
        if raw:
            result = result.replace(raw, placeholder)
            result = result.replace(json.dumps(raw)[1:-1], placeholder)
    result = UNIX_USER_PATH.sub("/$USER", result)
    result = WINDOWS_USER_PATH.sub(r"C:\\Users\\$USER", result)
    result = URI_USERINFO.sub(r"\1[REDACTED]@", result)
    result = SENSITIVE_QUERY.sub(r"\1[REDACTED]", result)
    # Exact task paths above preserve useful placeholders. These final guards
    # ensure unexpected runtime diagnostics cannot persist another absolute
    # machine path while the record claims pathsRedacted=true.
    result = GENERIC_WINDOWS_ABSOLUTE_PATH.sub("$ABSOLUTE_PATH", result)
    result = GENERIC_UNIX_ABSOLUTE_PATH.sub("$ABSOLUTE_PATH", result)
    return result


def redact_value(
    value: object,
    workspace: Path,
    key: str | None = None,
    path_replacements: list[tuple[str, str]] | None = None,
) -> object:
    if key and SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            item_key: redact_value(item, workspace, item_key, path_replacements)
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item, workspace, path_replacements=path_replacements) for item in value]
    if isinstance(value, str):
        return redact_text(value, workspace, path_replacements)
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


def public_command(
    cmd: list[str],
    workspace: Path,
    path_replacements: list[tuple[str, str]] | None = None,
) -> list[str]:
    result = list(cmd)
    if result and Path(result[0]).is_absolute():
        result[0] = display_invocation_path(result[0], workspace)
    return [redact_text(item, workspace, path_replacements) for item in result]


def run(
    cmd: list[str],
    timeout: int,
    workspace: Path,
    *,
    return_raw: bool = False,
    environment: dict[str, str] | None = None,
    redact_paths: list[str | Path] | None = None,
) -> dict | tuple[dict, str]:
    private_paths = list(redact_paths or [])
    if cmd and Path(cmd[0]).is_absolute():
        private_paths.append(cmd[0])
    replacements = exact_path_replacements(private_paths, workspace)
    public_cmd = public_command(cmd, workspace, replacements)
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment or minimal_environment(),
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
    redacted = redact_value(report, workspace, path_replacements=replacements)  # type: ignore[assignment]
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


def selected_matlab_executable(raw: str, *, application: bool) -> dict:
    """Resolve one exact MATLAB application or executable without launching it."""
    supplied = Path(raw)
    if not supplied.is_absolute():
        kind = "application" if application else "executable"
        raise ValueError(f"MATLAB {kind} must be an absolute path")
    selected = lexical_absolute(supplied)
    if application:
        if not selected.is_dir():
            raise ValueError("MATLAB application must identify an accessible directory")
        candidates = [
            selected / "bin" / ("matlab.exe" if os.name == "nt" else "matlab"),
            selected / "Contents" / "MacOS" / "MATLAB",
        ]
        executable = next((path for path in candidates if path.is_file()), None)
        if executable is None:
            raise ValueError("MATLAB application does not contain a recognized MATLAB launcher")
        selection_kind = "application"
    else:
        executable = selected
        selection_kind = "executable"

    try:
        metadata = executable.lstat()
    except OSError as exc:
        raise ValueError("MATLAB executable does not identify an accessible file") from exc
    if not (stat.S_ISLNK(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
        raise ValueError("MATLAB executable must identify a regular file or symlink launcher")
    if not os.access(executable, os.X_OK):
        raise ValueError("MATLAB executable is not executable")
    try:
        resolved = executable.resolve(strict=True)
    except OSError as exc:
        raise ValueError("MATLAB executable does not resolve to an accessible file") from exc
    if not resolved.is_file():
        raise ValueError("MATLAB executable must resolve to a regular file")
    return {
        "selectionKind": selection_kind,
        "selectedPath": selected,
        "invocationPath": executable,
        "resolvedPath": resolved,
    }


def matlab_quote(value: str) -> str:
    """Quote a Python string as one MATLAB character vector literal."""
    return "'" + value.replace("'", "''").replace("\r", " ").replace("\n", " ") + "'"


def matlab_route_search_directories(
    entrypoint: Path | None,
    raw_artifacts: list[str],
    workspace: Path,
) -> list[Path]:
    """Return exact, existing route directories without recursively scanning them."""
    candidates: list[Path] = []
    if entrypoint is not None and entrypoint.parent.is_dir():
        candidates.append(lexical_absolute(entrypoint.parent))
    for raw in raw_artifacts:
        supplied = Path(raw).expanduser()
        artifact = lexical_absolute(supplied if supplied.is_absolute() else workspace / supplied)
        if artifact.is_file() and artifact.suffix.lower() in {".m", ".mlx", ".p"}:
            candidates.append(lexical_absolute(artifact.parent))

    result: list[Path] = []
    seen: set[Path] = set()
    for directory in candidates:
        if directory not in seen:
            seen.add(directory)
            result.append(directory)
    return result


def normalize_matlab_release(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(?i)R?(\d{4})([ab])", value.strip())
    if not match:
        return None
    return f"R{match.group(1)}{match.group(2).lower()}"


def matlab_live_probe_expression(
    required_toolboxes: list[str],
    required_functions: list[str],
    entrypoint: Path | None,
    search_directories: list[Path],
) -> str:
    """Build a read-only route-capability probe with a machine-readable result marker."""
    toolbox_cells = "{" + ",".join(matlab_quote(item) for item in required_toolboxes) + "}"
    function_cells = "{" + ",".join(matlab_quote(item) for item in required_functions) + "}"
    entrypoint_literal = matlab_quote(str(entrypoint)) if entrypoint else "''"
    path_setup = "p0=path;pc=onCleanup(@()path(p0));" + "".join(
        f"addpath({matlab_quote(str(directory))},'-begin');" for directory in search_directories
    )
    return (
        "try;"
        f"{path_setup}"
        "v=ver;"
        "tb=arrayfun(@(x)struct('name',x.Name,'version',x.Version),v);"
        f"rt={toolbox_cells};rf={function_cells};ep={entrypoint_literal};"
        "tr=arrayfun(@(i)struct('name',rt{i},'installed',any(strcmpi({v.Name},rt{i}))),"
        "1:numel(rt));"
        "fr=arrayfun(@(i)struct('name',rf{i},'exists',exist(rf{i},'file')>0),"
        "1:numel(rf));"
        "if isempty(ep);er=struct('path','','exists',true);"
        "else;er=struct('path',ep,'exists',exist(ep,'file')>0);end;"
        "o=struct('release',version('-release'),'version',version,'toolboxes',tb,"
        "'requiredToolboxes',tr,'requiredFunctions',fr,'entrypoint',er);"
        "clear pc;"
        f"fprintf('{MATLAB_PROBE_MARKER}%s\\n',jsonencode(o));"
        "catch ME;"
        "if exist('pc','var');clear pc;end;"
        "e=struct('errorIdentifier',ME.identifier,'errorMessage',ME.message);"
        f"fprintf(2,'{MATLAB_PROBE_MARKER}%s\\n',jsonencode(e));exit(73);"
        "end;"
    )


def extract_matlab_probe_payload(raw_stdout: str) -> dict:
    for line in reversed(raw_stdout.splitlines()):
        if MATLAB_PROBE_MARKER not in line:
            continue
        payload = line.split(MATLAB_PROBE_MARKER, 1)[1].strip()
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise ValueError("MATLAB probe payload is not an object")
        return parsed
    raise ValueError("MATLAB probe marker was not found")


def matlab_probe_environment() -> dict[str, str]:
    """Provide MATLAB only the local home needed for installed license/preferences."""
    environment = minimal_environment()
    environment["HOME"] = str(Path.home())
    for name in ("TMPDIR", "TEMP", "TMP"):
        if os.environ.get(name):
            environment[name] = os.environ[name]
    return environment


def author_artifact_records(raw_values: list[str], workspace: Path) -> list[dict]:
    records = []
    seen: set[Path] = set()
    for raw in raw_values:
        supplied = Path(raw).expanduser()
        path = supplied if supplied.is_absolute() else workspace / supplied
        path = lexical_absolute(path)
        if path in seen:
            continue
        seen.add(path)
        records.append({
            "path": display_invocation_path(path, workspace),
            "suffix": path.suffix.lower(),
            "exists": path.is_file(),
        })
    return records


def native_route_recommendation(
    artifacts: list[dict],
    matlab_entries: list[dict],
    python_fallback_reason: str | None,
) -> dict:
    matlab_implementation_artifacts = [
        item for item in artifacts if item["exists"] and item["suffix"] in {".m", ".mlx", ".p"}
    ]
    matlab_data_artifacts = [item for item in artifacts if item["exists"] and item["suffix"] == ".mat"]
    if not matlab_implementation_artifacts:
        return {
            "evaluated": False,
            "authorNativeRuntime": None,
            "nativePriorityApplied": False,
            "recommendedRuntime": None,
            "pythonRole": "undetermined",
            "pythonFallbackEligible": False,
            "pythonFallbackReason": python_fallback_reason,
            "artifactHint": "matlab-data-format-only" if matlab_data_artifacts else None,
            "rationale": (
                "A .mat data file alone does not prove that the author implementation is MATLAB."
                if matlab_data_artifacts else "No author artifact identified a native runtime."
            ),
        }

    # An exact selection is the route that was actually tested. Do not let a
    # different, merely discovered installation hide a failed selected probe.
    selected_entries = [entry for entry in matlab_entries if entry.get("explicitSelection")]
    route_entries = selected_entries or matlab_entries
    statuses = {entry.get("verificationStatus", "available") for entry in route_entries}
    live_probe_failures = {
        "probe-command-failed", "probe-timed-out", "probe-output-invalid",
    }
    native_probe_failed = any(
        entry.get("verificationStatus") == "failed"
        and entry.get("failureReason") in live_probe_failures
        for entry in route_entries
    )
    if any(entry.get("runtimeVerified") for entry in route_entries):
        native_status = "verified"
    elif "needs-user-decision" in statuses:
        native_status = "needs-user-decision"
    elif native_probe_failed:
        native_status = "failed"
    elif route_entries:
        native_status = "available"
    else:
        native_status = "missing"
    native_available = native_status in {"available", "verified", "needs-user-decision"}
    if any(entry.get("routeCapabilityVerified") for entry in route_entries):
        native_capability_status = "verified"
    elif any(
        entry.get("runtimeVerified")
        and entry.get("failureReason") == "route-required-capability-missing"
        for entry in route_entries
    ):
        native_capability_status = "missing"
    elif native_probe_failed:
        native_capability_status = "inconclusive"
    elif any(entry.get("runtimeVerified") for entry in route_entries):
        native_capability_status = "incomplete"
    elif native_status == "needs-user-decision":
        native_capability_status = "needs-user-decision"
    elif native_available:
        native_capability_status = "untested"
    else:
        native_capability_status = "unavailable"
    capability_missing = native_capability_status == "missing"
    native_route_unusable = capability_missing or native_probe_failed
    use_declared_fallback = native_route_unusable and bool(python_fallback_reason)
    if use_declared_fallback:
        recommended_runtime = "python"
        recommended_route_kind = "declared-fallback"
    elif capability_missing:
        recommended_runtime = None
        recommended_route_kind = "blocked-native-capability"
    elif native_probe_failed:
        recommended_runtime = None
        recommended_route_kind = "native-probe-inconclusive"
    else:
        recommended_runtime = "matlab" if native_available else None
        recommended_route_kind = "author-native" if native_available else None
    return {
        "evaluated": True,
        "authorNativeRuntime": "matlab",
        "authorImplementationArtifactPaths": [item["path"] for item in matlab_implementation_artifacts],
        "authorDataArtifactPaths": [item["path"] for item in matlab_data_artifacts],
        "nativeRuntimeStatus": native_status,
        "nativeRouteCapabilityStatus": native_capability_status,
        "nativePriorityApplied": native_available and not native_route_unusable,
        "nativeRouteRejected": native_route_unusable,
        "recommendedRuntime": recommended_runtime,
        "recommendedRouteKind": recommended_route_kind,
        "pythonRole": "fallback-or-cross-check",
        "pythonFallbackEligible": bool(python_fallback_reason),
        "pythonPrimaryEligible": (not native_available or native_route_unusable) and bool(python_fallback_reason),
        "pythonFallbackReason": python_fallback_reason,
        "decisionRequired": (
            native_status == "needs-user-decision"
            or (native_probe_failed and not use_declared_fallback)
        ),
        "rationale": (
            "The live MATLAB probe found a required route capability missing; the explicit scientific "
            "fallback reason makes Python eligible as a declared substitute, not as an equivalent native route."
            if capability_missing and use_declared_fallback else
            "The live MATLAB probe found a required route capability missing, and no scientific reason "
            "authorizes a substitute runtime; no automatic runtime switch was made."
            if capability_missing else
            "The selected MATLAB live probe failed or returned unusable evidence. The native route is "
            "inconclusive for this run; the explicit scientific fallback reason makes Python eligible "
            "as a declared substitute, not as proof of native equivalence."
            if native_probe_failed and use_declared_fallback else
            "The selected MATLAB live probe failed or returned unusable evidence. No substitute was "
            "authorized, so the native route remains inconclusive and requires a route decision."
            if native_probe_failed else
            "Author .m/.mat-family artifacts identify MATLAB as the native route; an installed "
            "MATLAB candidate outranks a Python port. Python remains only a declared fallback or cross-check."
            if native_available
            else "Author artifacts identify MATLAB as native, but no installation was found. A Python "
            "substitute is eligible only with an explicit scientific reason and equivalence boundary."
        ),
    }


def frozen_environment_components(
    python_entries: list[dict],
    matlab_entries: list[dict],
    other_entries: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Project verified probes into the environment record consumed by the run bundler."""
    engines: list[dict] = []
    packages: list[dict] = []
    seen_engines: set[tuple[str, str]] = set()

    def add_engine(name: str, version: object, **evidence: object) -> None:
        if not isinstance(version, str) or not version.strip():
            return
        key = (name.casefold(), version.strip())
        if key in seen_engines:
            return
        seen_engines.add(key)
        engines.append({"name": name, "version": version.strip(), **evidence})

    for entry in python_entries:
        details = entry.get("details")
        if entry.get("verified") and isinstance(details, dict):
            add_engine(
                "Python",
                details.get("version"),
                verificationStatus="verified",
                invocationPath=entry.get("invocationPath"),
            )

    for entry in matlab_entries:
        if not entry.get("runtimeVerified"):
            continue
        add_engine(
            "MATLAB",
            entry.get("release") or entry.get("version"),
            verificationStatus="verified",
            productVersion=entry.get("version"),
            routeCapabilityVerified=bool(entry.get("routeCapabilityVerified")),
            invocationPath=entry.get("path"),
        )
        details = entry.get("details")
        toolboxes = details.get("toolboxes", []) if isinstance(details, dict) else []
        if isinstance(toolboxes, dict):
            toolboxes = [toolboxes]
        for toolbox in toolboxes if isinstance(toolboxes, list) else []:
            if not isinstance(toolbox, dict):
                continue
            name = toolbox.get("name")
            version = toolbox.get("version")
            if isinstance(name, str) and name.strip() and isinstance(version, str) and version.strip():
                packages.append({
                    "ecosystem": "MATLAB-toolbox",
                    "name": name.strip(),
                    "version": version.strip(),
                })

    for entry in other_entries:
        probe = entry.get("probe")
        if not entry.get("verified") or not isinstance(probe, dict):
            continue
        stdout = probe.get("stdout")
        first_line = stdout.splitlines()[0].strip() if isinstance(stdout, str) and stdout.strip() else None
        add_engine(str(entry.get("label") or "runtime"), first_line, verificationStatus="verified")

    return engines, packages


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
    matlab_selection = parser.add_mutually_exclusive_group()
    matlab_selection.add_argument(
        "--matlab-executable",
        metavar="/ABSOLUTE/PATH/TO/MATLAB",
        help="Select one exact existing MATLAB executable for route-specific inspection or live probing.",
    )
    matlab_selection.add_argument(
        "--matlab-application",
        metavar="/ABSOLUTE/PATH/TO/MATLAB_APP",
        help="Select one exact existing MATLAB application bundle or installation root.",
    )
    parser.add_argument(
        "--matlab-live-probe",
        action="store_true",
        help=(
            "Request a bounded MATLAB -batch capability probe of the exact selected application/executable. "
            "Without --allow-matlab-startup-license-risk this records needs-user-decision and does not launch MATLAB."
        ),
    )
    parser.add_argument(
        "--allow-matlab-startup-license-risk",
        action="store_true",
        help=(
            "Explicitly allow the selected installed MATLAB to start, run startup hooks, and acquire its configured "
            "local or shared license for the bounded live probe. Never installs or activates MATLAB."
        ),
    )
    parser.add_argument(
        "--matlab-required-toolbox",
        action="append",
        default=[],
        metavar="TOOLBOX_NAME",
        help="Record and test one exact toolbox name required by the target route; repeat as needed.",
    )
    parser.add_argument(
        "--matlab-required-function",
        action="append",
        default=[],
        metavar="FUNCTION_NAME",
        help="Record and test one MATLAB function required by the target route; repeat as needed.",
    )
    parser.add_argument(
        "--matlab-entrypoint",
        metavar="PATH/TO/ENTRYPOINT_M",
        help="Record and test the exact author entrypoint required by the target route.",
    )
    parser.add_argument(
        "--author-artifact",
        action="append",
        default=[],
        metavar="PATH",
        help="Record an author artifact used to infer the native runtime; repeat for .m, .mat, and related files.",
    )
    parser.add_argument(
        "--python-fallback-reason",
        help=(
            "Scientific reason for retaining Python as an explicit substitute or cross-check when author artifacts "
            "identify another native runtime."
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
    artifacts = author_artifact_records(args.author_artifact, workspace)
    if not 1 <= args.timeout <= MAX_PROBE_TIMEOUT_SECONDS:
        parser.error(f"--timeout must be between 1 and {MAX_PROBE_TIMEOUT_SECONDS} seconds")
    selected_runtimes = set(args.runtime or ["python"])
    if "all" in selected_runtimes:
        selected_runtimes = set(RUNTIME_CHOICES)
    if args.probe_matlab:
        selected_runtimes.add("matlab")
    matlab_specific = any((
        args.matlab_executable,
        args.matlab_application,
        args.matlab_live_probe,
        args.matlab_required_toolbox,
        args.matlab_required_function,
        args.matlab_entrypoint,
    ))
    if matlab_specific:
        selected_runtimes.add("matlab")
    if any(item["exists"] and item["suffix"] in {".m", ".mlx", ".p"} for item in artifacts):
        selected_runtimes.add("matlab")
    if args.python_executable:
        selected_runtimes.add("python")
    if args.allow_workspace_python and not args.python_executable:
        parser.error("--allow-workspace-python requires --python-executable")
    if args.matlab_live_probe and not (args.matlab_executable or args.matlab_application):
        parser.error("--matlab-live-probe requires --matlab-executable or --matlab-application")
    if args.allow_matlab_startup_license_risk and not args.matlab_live_probe:
        parser.error("--allow-matlab-startup-license-risk requires --matlab-live-probe")
    if (args.matlab_required_toolbox or args.matlab_required_function or args.matlab_entrypoint) and not (
        args.matlab_executable or args.matlab_application
    ):
        parser.error("MATLAB route requirements require --matlab-executable or --matlab-application")
    for function_name in args.matlab_required_function:
        if not MATLAB_FUNCTION.fullmatch(function_name):
            parser.error(f"invalid --matlab-required-function value: {function_name!r}")

    selected_matlab: dict | None = None
    if args.matlab_executable or args.matlab_application:
        try:
            selected_matlab = selected_matlab_executable(
                args.matlab_application or args.matlab_executable,
                application=bool(args.matlab_application),
            )
        except ValueError as exc:
            parser.error(str(exc))
    matlab_entrypoint = None
    if args.matlab_entrypoint:
        supplied_entrypoint = Path(args.matlab_entrypoint).expanduser()
        matlab_entrypoint = lexical_absolute(
            supplied_entrypoint if supplied_entrypoint.is_absolute() else workspace / supplied_entrypoint
        )
    matlab_search_directories = matlab_route_search_directories(
        matlab_entrypoint,
        list(args.author_artifact),
        workspace,
    )
    matlab_private_paths: list[str | Path] = list(matlab_search_directories)
    if matlab_entrypoint is not None:
        matlab_private_paths.append(matlab_entrypoint)
    for raw in args.author_artifact:
        supplied = Path(raw).expanduser()
        matlab_private_paths.append(
            lexical_absolute(supplied if supplied.is_absolute() else workspace / supplied)
        )
    if selected_matlab:
        matlab_private_paths.extend(
            selected_matlab[key]
            for key in ("selectedPath", "invocationPath", "resolvedPath")
        )

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
    matlab_paths = matlab_candidates() if "matlab" in selected_runtimes else []
    if selected_matlab and not any(
        same_file(selected_matlab["invocationPath"], candidate) for candidate in matlab_paths
    ):
        matlab_paths.append(selected_matlab["invocationPath"])

    for candidate in matlab_paths:
        is_selected = bool(selected_matlab and same_file(selected_matlab["invocationPath"], candidate))
        entry = {
            "path": display_invocation_path(candidate, workspace),
            "resolvedPath": display_path(candidate.resolve(), workspace),
            "installationDetected": True,
            "explicitSelection": is_selected,
            "selectionKind": selected_matlab["selectionKind"] if is_selected else "discovered-executable",
            "selectedApplicationOrExecutable": (
                display_invocation_path(selected_matlab["selectedPath"], workspace) if is_selected else None
            ),
            "metadataVerified": False,
            "runtimeVerified": False,
            "baseLicenseStartupVerified": False,
            "routeSmokeTested": False,
            "verified": False,
            "verificationStatus": "available",
            "verificationScope": "static-discovery-only",
            "version": None,
            "release": None,
            "probe": None,
            "liveProbe": None,
            "routeRequirements": {
                "requiredToolboxes": list(args.matlab_required_toolbox) if is_selected else [],
                "requiredFunctions": list(args.matlab_required_function) if is_selected else [],
                "entrypoint": (
                    display_invocation_path(matlab_entrypoint, workspace)
                    if is_selected and matlab_entrypoint else None
                ),
                "entrypointPresentStatic": (
                    matlab_entrypoint.is_file() if is_selected and matlab_entrypoint else None
                ),
                "searchDirectories": (
                    [display_invocation_path(path, workspace) for path in matlab_search_directories]
                    if is_selected else []
                ),
            },
        }
        if args.probe_matlab or is_selected:
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

        if is_selected and args.matlab_live_probe and not args.allow_matlab_startup_license_risk:
            entry["verificationStatus"] = "needs-user-decision"
            entry["verificationScope"] = "live-probe-requested-not-authorized"
            entry["decision"] = {
                "status": "needs-user-decision",
                "effect": "start-installed-matlab-and-use-configured-license",
                "reason": (
                    "MATLAB startup may execute startup.m and may acquire a local or shared license. "
                    "No process was started because that effect was not explicitly accepted."
                ),
                "optInFlag": "--allow-matlab-startup-license-risk",
            }
        elif is_selected and args.matlab_live_probe:
            expression = matlab_live_probe_expression(
                list(args.matlab_required_toolbox),
                list(args.matlab_required_function),
                matlab_entrypoint,
                matlab_search_directories,
            )
            probe, raw_stdout = run(
                [str(candidate), "-batch", expression],
                args.timeout,
                workspace,
                return_raw=True,
                environment=matlab_probe_environment(),
                redact_paths=matlab_private_paths,
            )
            entry["liveProbe"] = probe
            entry["verificationScope"] = "runtime-release-toolboxes-functions-entrypoint"
            entry["startupLicenseRiskAccepted"] = True
            if probe["returncode"] != 0 or probe["timedOut"]:
                entry["verificationStatus"] = "failed"
                entry["failureReason"] = (
                    "probe-timed-out" if probe["timedOut"] else "probe-command-failed"
                )
            else:
                try:
                    details = extract_matlab_probe_payload(raw_stdout)
                    release = normalize_matlab_release(details.get("release"))
                    if release is None:
                        raise ValueError("MATLAB release missing or invalid")
                    toolboxes = details.get("toolboxes", [])
                    if isinstance(toolboxes, dict):
                        toolboxes = [toolboxes]
                    if not isinstance(toolboxes, list) or not all(isinstance(item, dict) for item in toolboxes):
                        raise ValueError("MATLAB toolbox inventory missing or invalid")
                    installed_toolboxes = {
                        str(item.get("name", "")).casefold() for item in toolboxes if item.get("name")
                    }
                    toolbox_checks = [
                        {"name": name, "installed": name.casefold() in installed_toolboxes}
                        for name in args.matlab_required_toolbox
                    ]
                    function_payload = details.get("requiredFunctions", [])
                    if isinstance(function_payload, dict):
                        function_payload = [function_payload]
                    if not isinstance(function_payload, list):
                        raise ValueError("MATLAB function results missing or invalid")
                    reported_functions = {
                        str(item.get("name")): bool(item.get("exists"))
                        for item in function_payload if isinstance(item, dict) and item.get("name")
                    }
                    function_checks = [
                        {"name": name, "exists": reported_functions.get(name, False)}
                        for name in args.matlab_required_function
                    ]
                    entrypoint_payload = details.get("entrypoint", {})
                    if not isinstance(entrypoint_payload, dict):
                        raise ValueError("MATLAB entrypoint result missing or invalid")
                    entrypoint_exists = (
                        bool(entrypoint_payload.get("exists")) if matlab_entrypoint else True
                    )
                    if entrypoint_payload.get("path"):
                        entrypoint_payload["path"] = display_invocation_path(
                            entrypoint_payload["path"], workspace
                        )
                    details["entrypoint"] = entrypoint_payload
                    details["requiredToolboxes"] = toolbox_checks
                    details["requiredFunctions"] = function_checks
                    entry["details"] = details
                    entry["release"] = release
                    if details.get("version"):
                        entry["version"] = str(details["version"])
                    entry["runtimeVerified"] = True
                    entry["baseLicenseStartupVerified"] = True
                    entry["requiredToolboxInstallationsVerified"] = all(
                        item["installed"] for item in toolbox_checks
                    )
                    entry["requiredFunctionsVerified"] = all(
                        item["exists"] for item in function_checks
                    )
                    entry["entrypointVerified"] = entrypoint_exists
                    route_capability = all((
                        entry["requiredToolboxInstallationsVerified"],
                        entry["requiredFunctionsVerified"],
                        entry["entrypointVerified"],
                    ))
                    entry["routeCapabilityVerified"] = route_capability
                    entry["verified"] = route_capability
                    entry["verificationStatus"] = "verified" if route_capability else "failed"
                    if not route_capability:
                        entry["failureReason"] = "route-required-capability-missing"
                except (json.JSONDecodeError, OSError, TypeError, ValueError):
                    entry["verificationStatus"] = "failed"
                    entry["failureReason"] = "probe-output-invalid"
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
        entry = {
            "label": label,
            "path": display_path(path, workspace),
            "verificationStatus": "available",
            "verified": False,
            "probe": None,
            "probeSkipped": (
                "Generic runtime discovery is static-only. Verify the selected route with an "
                "explicitly reviewed absolute executable and the smallest route-specific smoke command."
            ),
        }
        other.append(entry)

    disk = shutil.disk_usage(workspace)
    workspace_python_probed = any(selection["workspaceControlled"] for selection in explicitly_selected_python)
    matlab_live_probed = bool(
        selected_matlab and args.matlab_live_probe and args.allow_matlab_startup_license_risk
    )
    matlab_workspace_executed = bool(
        matlab_live_probed and is_lexically_within(selected_matlab["invocationPath"], workspace)
    )
    workspace_execution_scopes = []
    if workspace_python_probed:
        workspace_execution_scopes.append("explicit-pep405-python-binary-no-site-only")
    if matlab_workspace_executed:
        workspace_execution_scopes.append("explicit-matlab-live-probe")
    route_recommendation = native_route_recommendation(
        artifacts,
        matlab_entries,
        args.python_fallback_reason,
    )
    hardware = {
        "platform": platform.platform(),
        "os": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpuCount": os.cpu_count(),
        "disk": {"totalBytes": disk.total, "usedBytes": disk.used, "freeBytes": disk.free},
    }
    engines, packages = frozen_environment_components(py_entries, matlab_entries, other)
    notes = [
        "Discovery cannot prove absence from every custom location.",
        "Only runtimes selected for candidate routes are probed unless --runtime all is explicitly used.",
        "Automatic Python discovery is static-only; a live probe requires an explicit --python-executable absolute path.",
        "Explicit Python probes use the selected launcher, a minimal allowlisted environment, -I -S isolation, and a bounded timeout; sitecustomize and site-packages are never loaded.",
        "Workspace Python execution additionally requires --allow-workspace-python; PEP 405 identity is detected statically and the no-site binary probe does not verify the venv runtime or packages.",
        "--probe-matlab reads static metadata only and never launches MATLAB.",
        "A MATLAB live probe requires an exact --matlab-application/--matlab-executable, --matlab-live-probe, and the separate --allow-matlab-startup-license-risk acknowledgement.",
        "A successful MATLAB capability probe verifies startup, release, installed toolboxes, named functions, and entrypoint presence; it does not execute the entrypoint or constitute a route smoke test.",
        "The MATLAB capability probe temporarily adds only explicit route directories and restores the original MATLAB path; it never executes author entrypoints or recursively scans source trees.",
        "When author .m/.mat-family artifacts and an installed MATLAB coexist, the author-native MATLAB route outranks Python until a live probe falsifies a required capability or leaves the selected runtime inconclusive; Python becomes a declared substitute only with an explicit target-relevant fallback reason.",
        "R, Julia, Octave, Node, and accelerator discovery is static-only; validate a chosen route with an explicitly reviewed executable and a route-specific smoke command.",
        "Verify required packages, toolboxes, licenses, and hardware separately for each selected route.",
    ]
    privacy = {
        "pathsRedacted": True,
        "environmentPolicy": "minimal-allowlist",
        "workspaceExecutablesRun": workspace_python_probed or matlab_workspace_executed,
        "workspaceExecutionScope": ",".join(workspace_execution_scopes) or "none",
        "explicitPythonProbeCount": len(explicitly_selected_python),
        "explicitMatlabLiveProbeCount": 1 if matlab_live_probed else 0,
    }
    report = {
        "schemaVersion": "scirepro.environment/v2",
        "captureStatus": "recorded" if engines else "partial",
        "engines": engines,
        "packages": packages,
        "hardware": hardware,
        "notes": notes,
        "workspace": "$WORKSPACE",
        "privacy": privacy,
        "selectedRuntimes": sorted(selected_runtimes),
        "system": hardware,
        "python": py_entries,
        "matlab": matlab_entries,
        "authorArtifacts": artifacts,
        "routeRecommendation": route_recommendation,
        "other": other,
        "evidence": {
            "privacy": privacy,
            "selectedRuntimes": sorted(selected_runtimes),
            "python": py_entries,
            "matlab": matlab_entries,
            "authorArtifacts": artifacts,
            "routeRecommendation": route_recommendation,
            "other": other,
        },
    }
    report_private_paths = list(matlab_private_paths)
    for selection in explicitly_selected_python:
        report_private_paths.extend(
            selection[key]
            for key in ("invocationPath", "resolvedPath")
        )
        if selection.get("venvRoot") is not None:
            report_private_paths.append(selection["venvRoot"])
    report_replacements = exact_path_replacements(report_private_paths, workspace)
    payload = json.dumps(
        redact_value(report, workspace, path_replacements=report_replacements),
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
