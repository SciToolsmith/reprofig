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
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    from .safe_output import SafeOutputError, write_text_create_only
except ImportError:  # Direct script execution.
    from safe_output import SafeOutputError, write_text_create_only


SENSITIVE_KEY = re.compile(r"(?i)(?:authorization|cookie|credential|password|secret|session|token)")
SENSITIVE_QUERY = re.compile(
    r"(?i)([?&](?:access[_-]?key|api[_-]?key|auth|credential|password|secret|signature|sig|token)=)[^&#\s]+"
)
SECRET_SHAPED_TEXT = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?key|authorization|credential|password|secret|token)\s*[:=]\s*\S+"
)
PRIVATE_KEY_TEXT = re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----")
ASSIGNED_SECRET_TEXT = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?key|authorization|bearer|client[_-]?secret|"
    r"cookie|credential|password|passwd|private[_-]?key|secret|session[_-]?token|"
    r"access[_-]?token|auth[_-]?token|refresh[_-]?token)\s*[=:]\s*"
    r"(?:[\"'][^\s\"']{8,}[\"']|[A-Za-z0-9_./+=-]{16,})"
)
SECRET_TOKEN_TEXT = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)
URI_USERINFO = re.compile(r"(?i)(https?://)[^/@\s]+@")
FILE_URI_PATH = re.compile(r"(?i)file:///(?:[^\s\"'`;(),\[\]{}]+)")
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
MATLAB_LICENSE_FEATURE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
MATLAB_PROBE_MARKER = "SCIREPRO_MATLAB_PROBE_JSON:"
RUNTIME_CHOICES = {"python", "matlab", "r", "rscript", "julia", "octave", "node", "nvidia"}
ROUTE_RUNTIME_CHOICES = RUNTIME_CHOICES - {"nvidia"}
SUBSTITUTE_ROLES = {
    "fallback-primary", "portability-primary", "independent-primary", "cross-check",
}
ARTIFACT_RUNTIME_CANDIDATES = {
    ".m": ("matlab", "octave"),
    ".mlx": ("matlab",),
    ".p": ("matlab",),
    ".r": ("r",),
    ".rmd": ("r",),
    ".jl": ("julia",),
    ".py": ("python",),
    ".js": ("node",),
    ".mjs": ("node",),
    ".cjs": ("node",),
}
MAX_PROBE_TIMEOUT_SECONDS = 60
MAX_RAW_PROBE_TAIL = 64 * 1024
MAX_SUBSTITUTE_REASON_CHARACTERS = 500
NATIVE_EXECUTABLE_MAGICS = {
    b"\x7fELF",  # ELF
    b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",  # Mach-O, big endian
    b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",  # Mach-O, little endian
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",  # universal Mach-O
    b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",  # universal Mach-O 64
}
PYTHON_EXECUTABLE_NAME = re.compile(
    r"(?i)^(?:python|pypy)(?:\d+(?:\.\d+)*)?(?:[-_][A-Za-z0-9._-]+)?(?:\.exe)?$"
)


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
    result = FILE_URI_PATH.sub("file:///$ABSOLUTE_PATH", result)
    if any(pattern.search(result) for pattern in (
        SECRET_SHAPED_TEXT,
        PRIVATE_KEY_TEXT,
        ASSIGNED_SECRET_TEXT,
        SECRET_TOKEN_TEXT,
    )):
        return "[REDACTED_SECRET_OUTPUT]"
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
    working_directory: Path | None = None,
) -> dict | tuple[dict, str]:
    private_paths = list(redact_paths or [])
    if cmd and Path(cmd[0]).is_absolute():
        private_paths.append(cmd[0])
    replacements = exact_path_replacements(private_paths, workspace)
    public_cmd = public_command(cmd, workspace, replacements)
    process: subprocess.Popen[bytes] | None = None
    stdout_tail = bytearray()
    stderr_tail = bytearray()

    def drain(stream: object, destination: bytearray) -> None:
        try:
            while True:
                block = stream.read(64 * 1024)  # type: ignore[attr-defined]
                if not block:
                    break
                destination.extend(block)
                if len(destination) > MAX_RAW_PROBE_TAIL:
                    del destination[:-MAX_RAW_PROBE_TAIL]
        except (OSError, ValueError):
            # A forced process-group shutdown may close a pipe while a drain
            # thread is blocked. The bounded tail already captured is enough.
            return

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment or minimal_environment(),
            cwd=working_directory,
            start_new_session=(os.name == "posix"),
        )
        assert process.stdout is not None and process.stderr is not None
        stdout_thread = threading.Thread(target=drain, args=(process.stdout, stdout_tail), daemon=True)
        stderr_thread = threading.Thread(target=drain, args=(process.stderr, stderr_tail), daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                process.terminate()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
            # The direct process may exit on SIGTERM while a descendant in the
            # same group ignores it. Always terminate the remaining group.
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.kill()
            if process.poll() is None:
                process.wait()
        if not timed_out and os.name == "posix":
            # A probe wrapper can exit successfully after spawning background
            # work. Its entire fresh process group is part of the bounded
            # probe and must not survive the direct child.
            group_existed = False
            try:
                os.killpg(process.pid, signal.SIGTERM)
                group_existed = True
            except ProcessLookupError:
                pass
            if group_existed:
                time.sleep(0.05)
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        stdout_thread.join(timeout=0.75)
        stderr_thread.join(timeout=0.75)
        if stdout_thread.is_alive() or stderr_thread.is_alive():
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            stdout_thread.join(timeout=0.25)
            stderr_thread.join(timeout=0.25)
        process.stdout.close()
        process.stderr.close()
        raw_stdout = bytes(stdout_tail).decode("utf-8", errors="replace")
        raw_stderr = bytes(stderr_tail).decode("utf-8", errors="replace")
        report = {
            "command": public_cmd,
            "returncode": None if timed_out else process.returncode,
            "stdout": raw_stdout.strip()[-4000:],
            "stderr": raw_stderr.strip()[-2000:],
            "timedOut": timed_out,
        }
    except OSError as exc:
        raw_stdout = ""
        report = {
            "command": public_cmd,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "timedOut": False,
        }
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
    if PYTHON_EXECUTABLE_NAME.fullmatch(resolved.name) is None:
        raise ValueError("must resolve to a recognizable Python interpreter executable")

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


def matlab_installation_identity(executable: Path) -> dict | None:
    """Validate a MATLAB installation shape using bounded static product metadata."""
    if executable.name.casefold() not in {"matlab", "matlab.exe"}:
        return None
    if executable.parent.name.casefold() == "bin":
        installation_root = executable.parent.parent
    elif (
        executable.name == "MATLAB"
        and executable.parent.name == "MacOS"
        and executable.parent.parent.name == "Contents"
        and executable.parent.parent.parent.suffix.lower() == ".app"
    ):
        installation_root = executable.parent.parent.parent
    else:
        return None

    version_info = installation_root / "VersionInfo.xml"
    if version_info.is_file() and not version_info.is_symlink():
        try:
            text = version_info.read_text(encoding="utf-8", errors="replace")[:100_000]
        except OSError:
            return None
        version_match = re.search(r"<version>([^<]+)</version>", text, re.IGNORECASE)
        release_match = re.search(r"<release>(R\d{4}[ab])</release>", text, re.IGNORECASE)
        if version_match and release_match:
            return {
                "installationRoot": installation_root,
                "identitySource": version_info,
                "version": version_match.group(1).strip(),
                "release": normalize_matlab_release(release_match.group(1)),
            }

    if installation_root.suffix.lower() == ".app":
        plist = installation_root / "Contents" / "Info.plist"
        if plist.is_file() and not plist.is_symlink():
            try:
                with plist.open("rb") as handle:
                    payload = plistlib.load(handle)
            except (OSError, plistlib.InvalidFileException):
                return None
            bundle_identifier = str(payload.get("CFBundleIdentifier") or "")
            version = payload.get("CFBundleShortVersionString") or payload.get("CFBundleVersion")
            release_match = MATLAB_RELEASE.search(installation_root.name)
            if "mathworks" in bundle_identifier.casefold() and version and release_match:
                value = release_match.group(1)
                return {
                    "installationRoot": installation_root,
                    "identitySource": plist,
                    "version": str(version),
                    "release": f"R{value[1:-1]}{value[-1].lower()}",
                }
    return None


def selected_matlab_executable(raw: str, *, application: bool, workspace: Path) -> dict:
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
    if (
        is_lexically_within(selected, workspace)
        or is_lexically_within(executable, workspace)
        or is_within(resolved, workspace)
    ):
        raise ValueError("MATLAB selection must not be workspace-controlled or an author-supplied launcher")
    identity = matlab_installation_identity(executable)
    if identity is None:
        raise ValueError(
            "MATLAB selection must have a recognized installation shape and trusted static product identity"
        )
    return {
        "selectionKind": selection_kind,
        "selectedPath": selected,
        "invocationPath": executable,
        "resolvedPath": resolved,
        "installationRoot": identity["installationRoot"],
        "identitySource": identity["identitySource"],
        "staticIdentity": {
            "release": identity["release"],
            "version": identity["version"],
        },
    }


def matlab_quote(value: str) -> str:
    """Quote a Python string as one MATLAB character vector literal."""
    return "'" + value.replace("'", "''").replace("\r", " ").replace("\n", " ") + "'"


def is_regular_non_symlink_file(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)


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
    required_license_features: list[str],
    required_functions: list[str],
    _entrypoint: Path | None,
    _search_directories: list[Path],
) -> str:
    """Build a read-only runtime/prerequisite probe with a machine-readable result marker."""
    toolbox_cells = "{" + ",".join(matlab_quote(item) for item in required_toolboxes) + "}"
    license_cells = "{" + ",".join(matlab_quote(item) for item in required_license_features) + "}"
    function_cells = "{" + ",".join(matlab_quote(item) for item in required_functions) + "}"
    return (
        "try;"
        "p0=path;pc=onCleanup(@()path(p0));restoredefaultpath;"
        "v=ver;"
        f"rt={toolbox_cells};rl={license_cells};rf={function_cells};"
        "tr=repmat(struct('name','','installed',false,'version',''),1,numel(rt));"
        "for i=1:numel(rt);tr(i).name=rt{i};j=find(strcmpi({v.Name},rt{i}),1);"
        "if ~isempty(j);tr(i).installed=true;tr(i).version=v(j).Version;end;end;"
        "lr=arrayfun(@(i)struct('feature',rl{i},'available',logical(license('test',rl{i}))),"
        "1:numel(rl));"
        "fc=arrayfun(@(i)exist(rf{i},'file'),1:numel(rf));"
        "fr=arrayfun(@(i)struct('name',rf{i},'existCode',fc(i),"
        "'exists',any(fc(i)==[2,3,6])),"
        "1:numel(rf));"
        "o=struct('release',version('-release'),'version',version,"
        "'cleanPathReset',true,'requiredToolboxes',tr,'requiredLicenseFeatures',lr,"
        "'requiredFunctions',fr);"
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


def validated_substitute_reason(value: str) -> str:
    reason = value.strip()
    if not reason:
        raise ValueError("must contain a non-empty scientific or deliverable reason")
    if len(reason) > MAX_SUBSTITUTE_REASON_CHARACTERS:
        raise ValueError(f"must be at most {MAX_SUBSTITUTE_REASON_CHARACTERS} characters")
    if "\n" in reason or "\r" in reason:
        raise ValueError("must be a single line")
    if any(ord(character) < 32 or ord(character) == 127 for character in reason):
        raise ValueError("must not contain control characters")
    if any(pattern.search(reason) for pattern in (
        SECRET_SHAPED_TEXT,
        PRIVATE_KEY_TEXT,
        ASSIGNED_SECRET_TEXT,
        SECRET_TOKEN_TEXT,
        SENSITIVE_QUERY,
        URI_USERINFO,
    )):
        raise ValueError("must not contain secret-shaped text")
    return reason


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
        suffix = path.suffix.lower()
        runtime_candidates = list(ARTIFACT_RUNTIME_CANDIDATES.get(suffix, ()))
        records.append({
            "path": display_invocation_path(path, workspace),
            "suffix": suffix,
            "exists": path.is_file(),
            "artifactKind": (
                "data" if suffix == ".mat" else
                "implementation" if runtime_candidates else
                "unknown"
            ),
            "runtimeCandidates": runtime_candidates,
            "runtimeAmbiguous": len(runtime_candidates) > 1,
        })
    return records


def native_route_recommendation(
    artifacts: list[dict],
    runtime_entries: dict[str, list[dict]] | list[dict],
    substitute_reason: str | None = None,
    substitute_role: str | None = None,
    *,
    author_native_runtime: str | None = None,
    substitute_runtime: str | None = None,
    author_runtime_selection_source: str | None = None,
    legacy_python_arguments_used: bool = False,
) -> dict:
    """Recommend a route only after the author-native runtime is explicit.

    Artifact suffixes are candidate metadata, not runtime identity. In
    particular, ``.m`` is shared by MATLAB and GNU Octave. ``runtime_entries``
    may be a mapping for the generic API; accepting a list preserves the old
    internal MATLAB-only call shape without restoring suffix inference.
    """
    implementation_artifacts = [
        item for item in artifacts
        if item.get("exists") and item.get("suffix") != ".mat"
    ]
    data_artifacts = [
        item for item in artifacts if item.get("exists") and item.get("suffix") == ".mat"
    ]
    candidate_runtimes = sorted({
        runtime
        for item in implementation_artifacts
        for runtime in item.get(
            "runtimeCandidates",
            ARTIFACT_RUNTIME_CANDIDATES.get(str(item.get("suffix", "")).lower(), ()),
        )
    })
    ambiguous_artifacts = [
        item["path"] for item in implementation_artifacts
        if len(item.get(
            "runtimeCandidates",
            ARTIFACT_RUNTIME_CANDIDATES.get(str(item.get("suffix", "")).lower(), ()),
        )) > 1
    ]
    substitute_declared = bool(substitute_runtime and substitute_reason and substitute_role)
    python_alias_active = substitute_runtime == "python"

    def compatibility_fields(primary_eligible: bool) -> dict:
        return {
            # Deprecated aliases retained so old consumers can migrate without
            # making Python the conceptual default of the generic router.
            "pythonRole": (
                substitute_role if python_alias_active else
                "fallback-or-cross-check"
                if substitute_runtime is None and author_native_runtime == "matlab" else
                "not-selected"
            ),
            "pythonFallbackEligible": substitute_declared and python_alias_active,
            "pythonPrimaryEligible": primary_eligible and python_alias_active,
            "pythonFallbackReason": substitute_reason if python_alias_active else None,
            "legacyPythonArgumentsUsed": legacy_python_arguments_used,
        }

    if not author_native_runtime:
        if ambiguous_artifacts:
            artifact_hint = "ambiguous-runtime-artifact"
            if any(str(item.get("suffix", "")).lower() == ".m" for item in implementation_artifacts):
                rationale = (
                    "At least one author .m artifact is compatible with both MATLAB and GNU Octave. "
                    "Identify the intended author-native runtime from target-relevant evidence before probing or "
                    "selecting a substitute."
                )
            else:
                rationale = (
                    "At least one author artifact has more than one plausible runtime. Identify the intended "
                    "author-native runtime from target-relevant evidence before probing or selecting a substitute."
                )
        elif candidate_runtimes:
            artifact_hint = "runtime-candidates-require-confirmation"
            rationale = (
                "Artifact suffixes provide runtime candidates but do not establish the author-native runtime. "
                "Confirm it from target-relevant documentation, syntax, dependencies, or an intended launcher."
            )
        elif data_artifacts:
            artifact_hint = "data-format-only"
            rationale = "A .mat data file identifies a data format, not the author-native runtime."
        else:
            artifact_hint = None
            rationale = "No explicit target-relevant author-native runtime was supplied."
        return {
            "evaluated": False,
            "authorNativeRuntime": None,
            "authorNativeRuntimeSelectionSource": None,
            "candidateNativeRuntimes": candidate_runtimes,
            "ambiguousAuthorArtifactPaths": ambiguous_artifacts,
            "nativePriorityApplied": False,
            "recommendedRuntime": None,
            "recommendedRouteKind": None,
            "substituteRuntime": substitute_runtime,
            "substituteRole": substitute_role,
            "substituteReason": substitute_reason,
            "substituteEligible": False,
            "substitutePrimaryEligible": False,
            "nextAction": "identify-author-native-runtime",
            "artifactHint": artifact_hint,
            "rationale": rationale,
            **compatibility_fields(False),
        }

    if isinstance(runtime_entries, list):
        entries_by_runtime = {"matlab": runtime_entries}
    else:
        entries_by_runtime = runtime_entries
    all_native_entries = list(entries_by_runtime.get(author_native_runtime, []))
    # An exact selection is the route that was actually tested. Do not let a
    # different, merely discovered installation hide a failed selected probe.
    selected_entries = [entry for entry in all_native_entries if entry.get("explicitSelection")]
    route_entries = selected_entries or all_native_entries
    live_probe_failures = {
        "probe-command-failed", "probe-timed-out", "probe-output-invalid",
    }
    native_probe_failed = any(
        entry.get("verificationStatus") == "failed"
        and entry.get("failureReason") in live_probe_failures
        for entry in route_entries
    )
    route_verified = any(
        entry.get("routeSmokeTested") and entry.get("routeCapabilityVerified")
        for entry in route_entries
    )
    runtime_verified = any(
        entry.get("runtimeVerified") or entry.get("verified")
        for entry in route_entries
    )
    prerequisites_present = any(entry.get("prerequisitesPresent") for entry in route_entries)
    path_only_runtime = author_native_runtime in {"r", "rscript", "julia", "octave", "node"}
    native_not_discovered = path_only_runtime and not route_entries
    if route_verified:
        native_status = "verified"
    elif runtime_verified:
        native_status = "runtime-verified"
    elif native_probe_failed:
        native_status = "failed"
    elif route_entries:
        native_status = "available"
    elif native_not_discovered:
        native_status = "not-discovered"
    else:
        native_status = "missing"
    native_available = native_status in {"available", "runtime-verified", "verified"}
    if route_verified:
        native_capability_status = "verified"
    elif prerequisites_present:
        native_capability_status = "prerequisites-present"
    elif any(
        entry.get("runtimeVerified")
        and entry.get("failureReason") == "route-required-capability-missing"
        for entry in route_entries
    ):
        native_capability_status = "missing"
    elif native_probe_failed:
        native_capability_status = "inconclusive"
    elif runtime_verified:
        native_capability_status = "inconclusive"
    elif native_available:
        native_capability_status = "available-untested"
    elif native_not_discovered:
        native_capability_status = "inconclusive"
    else:
        native_capability_status = "unavailable"
    capability_missing = native_capability_status == "missing"
    native_missing = native_status == "missing"
    native_route_unusable = native_missing or capability_missing or native_probe_failed
    objective_substitute = substitute_declared and substitute_role in {
        "portability-primary", "independent-primary",
    }
    declared_fallback = substitute_declared and substitute_role == "fallback-primary"
    use_declared_fallback = native_route_unusable and declared_fallback
    if objective_substitute:
        recommended_runtime = substitute_runtime
        recommended_route_kind = "declared-substitute"
        next_action = "execute-declared-substitute"
    elif route_verified:
        recommended_runtime = author_native_runtime
        recommended_route_kind = "author-native"
        next_action = "execute-native-route"
    elif prerequisites_present:
        recommended_runtime = author_native_runtime
        recommended_route_kind = "author-native"
        next_action = "run-reviewed-native-smoke"
    elif use_declared_fallback:
        recommended_runtime = substitute_runtime
        recommended_route_kind = "declared-fallback"
        next_action = "execute-declared-fallback"
    elif capability_missing:
        recommended_runtime = None
        recommended_route_kind = "blocked-native-capability"
        next_action = "declare-substitute-or-block"
    elif native_probe_failed:
        recommended_runtime = None
        recommended_route_kind = "native-probe-inconclusive"
        next_action = "one-bounded-diagnostic-or-route-decision"
    elif native_not_discovered:
        recommended_runtime = None
        recommended_route_kind = "native-runtime-not-discovered"
        next_action = "locate-reviewed-native-runtime-or-decide-route"
    elif native_missing:
        recommended_runtime = None
        recommended_route_kind = "native-runtime-missing"
        next_action = "declare-substitute-or-block"
    elif native_status == "runtime-verified":
        recommended_runtime = author_native_runtime
        recommended_route_kind = "author-native"
        next_action = "run-reviewed-native-smoke"
    elif native_status == "available":
        recommended_runtime = author_native_runtime
        recommended_route_kind = "author-native"
        next_action = (
            "live-probe-native-prerequisites"
            if author_native_runtime == "matlab" else
            "select-and-run-reviewed-native-smoke"
        )
    else:
        recommended_runtime = author_native_runtime if native_available else None
        recommended_route_kind = "author-native" if native_available else None
        next_action = "run-reviewed-native-smoke" if runtime_verified else "select-route"
    compatible_artifacts = []
    conflicting_artifacts = []
    for item in implementation_artifacts:
        candidates = list(item.get(
            "runtimeCandidates",
            ARTIFACT_RUNTIME_CANDIDATES.get(str(item.get("suffix", "")).lower(), ()),
        ))
        compatible = author_native_runtime in candidates
        if author_native_runtime == "rscript" and "r" in candidates:
            compatible = True
        if not candidates or compatible:
            compatible_artifacts.append(item["path"])
        else:
            conflicting_artifacts.append(item["path"])
    substitute_primary_eligible = objective_substitute or use_declared_fallback
    return {
        "evaluated": True,
        "authorNativeRuntime": author_native_runtime,
        "authorNativeRuntimeSelectionSource": author_runtime_selection_source or "explicit-selection",
        "candidateNativeRuntimes": candidate_runtimes,
        "ambiguousAuthorArtifactPaths": ambiguous_artifacts,
        "authorImplementationArtifactPaths": [item["path"] for item in implementation_artifacts],
        "authorDataArtifactPaths": [item["path"] for item in data_artifacts],
        "authorRuntimeCompatibleArtifactPaths": compatible_artifacts,
        "authorRuntimeConflictingArtifactPaths": conflicting_artifacts,
        "nativeRuntimeStatus": native_status,
        "nativeRouteCapabilityStatus": native_capability_status,
        "nativePriorityApplied": (
            recommended_runtime == author_native_runtime and not objective_substitute
        ),
        "nativeRouteRejected": native_route_unusable,
        "nativeRouteReady": route_verified,
        "recommendedRuntime": recommended_runtime,
        "recommendedRouteKind": recommended_route_kind,
        "substituteRuntime": substitute_runtime,
        "substituteRole": substitute_role,
        "substituteReason": substitute_reason,
        "substituteEligible": substitute_declared,
        "substitutePrimaryEligible": substitute_primary_eligible,
        "nextAction": next_action,
        "decisionRequired": (native_probe_failed and not use_declared_fallback) or native_not_discovered,
        "rationale": (
            f"The objective explicitly requires a portable or independent implementation. {substitute_runtime} "
            "may be primary "
            "without pretending to be author-native execution; the changed evidence boundary remains explicit."
            if objective_substitute else
            "The author-native prerequisites are present, but the target route itself has not been smoke-tested. "
            "Run one reviewed target-relevant native operation before treating the route as verified."
            if prerequisites_present else
            "The author-native runtime is detected but untested. Static availability is not route-execution "
            "evidence and cannot justify a silent substitute; run the smallest bounded runtime/route probe next."
            if native_status == "available" else
            "The selected generic runtime was not found in PATH-only discovery. This does not prove absence from "
            "custom installations and cannot authorize a fallback by itself; locate a reviewed executable or make "
            "an explicit route decision."
            if native_not_discovered else
            "The live native prerequisite probe found a required route capability missing; the explicit scientific "
            f"fallback reason makes {substitute_runtime} eligible as a declared substitute, not as an equivalent "
            "native route."
            if capability_missing and use_declared_fallback else
            "The live native prerequisite probe found a required route capability missing, and no scientific reason "
            "authorizes a substitute runtime; no automatic runtime switch was made."
            if capability_missing else
            "The selected native probe failed or returned unusable evidence. The native route is "
            f"inconclusive for this run; the explicit scientific fallback reason makes {substitute_runtime} eligible "
            "as a declared substitute, not as proof of native equivalence."
            if native_probe_failed and use_declared_fallback else
            "The selected native probe failed or returned unusable evidence. No substitute was "
            "authorized, so the native route remains inconclusive and requires a route decision."
            if native_probe_failed else
            f"The author-native runtime was explicitly identified as {author_native_runtime}; an installed "
            "candidate remains primary until the objective or route evidence justifies a declared substitute."
            if native_available
            else f"The author-native runtime was explicitly identified as {author_native_runtime}, but no "
            "installation was found. A "
            "substitute is eligible only with an explicit scientific reason and equivalence boundary."
        ),
        **compatibility_fields(substitute_primary_eligible),
    }


def frozen_environment_components(
    python_entries: list[dict],
    matlab_entries: list[dict],
    other_entries: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Project verified probes into a compact reusable environment record."""
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
            verificationStatus="runtime-verified",
            productVersion=entry.get("version"),
            prerequisitesPresent=bool(entry.get("prerequisitesPresent")),
            routeCapabilityVerified=bool(entry.get("routeCapabilityVerified")),
            invocationPath=entry.get("path"),
        )
        details = entry.get("details")
        toolboxes = details.get("requiredToolboxes", []) if isinstance(details, dict) else []
        if not toolboxes and isinstance(details, dict):
            toolboxes = details.get("toolboxes", [])
        if isinstance(toolboxes, dict):
            toolboxes = [toolboxes]
        for toolbox in toolboxes if isinstance(toolboxes, list) else []:
            if not isinstance(toolbox, dict):
                continue
            name = toolbox.get("name")
            version = toolbox.get("version")
            installed = toolbox.get("installed", True)
            if (
                installed is not False
                and isinstance(name, str) and name.strip()
                and isinstance(version, str) and version.strip()
            ):
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
            "No runtime is selected by default. Use all only for an explicitly requested inventory."
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
            "Run a bounded MATLAB -batch startup and prerequisite probe of the exact selected "
            "application/executable. Invoke only after applying permission-gates.md; this flag is the "
            "explicit launch action and does not install or activate MATLAB."
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
        help=(
            "Record and test one clean-default-path MATLAB or toolbox function required by the target route; "
            "repeat as needed. Never use this for an author function; identify author code with "
            "--matlab-entrypoint and verify it only in the later reviewed route smoke."
        ),
    )
    parser.add_argument(
        "--matlab-required-license-feature",
        action="append",
        default=[],
        metavar="LICENSE_FEATURE",
        help=(
            "Test one exact MATLAB license feature identifier required by the target route; repeat as needed. "
            "This is distinct from checking that a toolbox is installed."
        ),
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
        help=(
            "Record a target-relevant author artifact; repeat as needed. Suffixes are retained as candidate "
            "metadata only and never select the author-native runtime."
        ),
    )
    parser.add_argument(
        "--author-native-runtime",
        choices=sorted(ROUTE_RUNTIME_CHOICES),
        help=(
            "Explicitly identify the target-relevant author-native runtime after reviewing paper/code evidence. "
            "Required for route recommendation; an artifact suffix alone, especially .m, is insufficient."
        ),
    )
    parser.add_argument(
        "--substitute-runtime",
        choices=sorted(ROUTE_RUNTIME_CHOICES),
        help="Runtime for a declared fallback, portability route, independent implementation, or cross-check.",
    )
    parser.add_argument(
        "--substitute-reason",
        help="Scientific or deliverable reason for using the declared substitute runtime.",
    )
    parser.add_argument(
        "--substitute-role",
        choices=sorted(SUBSTITUTE_ROLES),
        help=(
            "Role of the declared substitute. fallback-primary becomes eligible only after native "
            "unavailability/inconclusiveness; portability-primary and independent-primary are objective-driven; "
            "cross-check is not primary."
        ),
    )
    parser.add_argument(
        "--python-fallback-reason",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--python-substitute-role",
        choices=sorted(SUBSTITUTE_ROLES),
        help=argparse.SUPPRESS,
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
    selected_runtimes = set(args.runtime or [])
    if "all" in selected_runtimes:
        selected_runtimes = set(RUNTIME_CHOICES)
    if args.author_native_runtime:
        selected_runtimes.add(args.author_native_runtime)
    if args.substitute_runtime:
        selected_runtimes.add(args.substitute_runtime)
    if args.probe_matlab:
        selected_runtimes.add("matlab")
    matlab_specific = any((
        args.matlab_executable,
        args.matlab_application,
        args.matlab_live_probe,
        args.matlab_required_toolbox,
        args.matlab_required_license_feature,
        args.matlab_required_function,
        args.matlab_entrypoint,
    ))
    if matlab_specific:
        selected_runtimes.add("matlab")
    if args.python_executable:
        selected_runtimes.add("python")
    if args.allow_workspace_python and not args.python_executable:
        parser.error("--allow-workspace-python requires --python-executable")
    if args.matlab_live_probe and not (args.matlab_executable or args.matlab_application):
        parser.error("--matlab-live-probe requires --matlab-executable or --matlab-application")
    if (args.matlab_required_toolbox or args.matlab_required_license_feature or args.matlab_required_function or args.matlab_entrypoint) and not (
        args.matlab_executable or args.matlab_application
    ):
        parser.error("MATLAB route requirements require --matlab-executable or --matlab-application")
    for function_name in args.matlab_required_function:
        if not MATLAB_FUNCTION.fullmatch(function_name):
            parser.error(f"invalid --matlab-required-function value: {function_name!r}")
    for feature_name in args.matlab_required_license_feature:
        if not MATLAB_LICENSE_FEATURE.fullmatch(feature_name):
            parser.error(f"invalid --matlab-required-license-feature value: {feature_name!r}")
    legacy_python_arguments_used = bool(
        args.python_fallback_reason or args.python_substitute_role
    )
    generic_substitute_arguments_used = bool(
        args.substitute_runtime or args.substitute_reason or args.substitute_role
    )
    if legacy_python_arguments_used and generic_substitute_arguments_used:
        parser.error(
            "deprecated Python substitute flags cannot be combined with --substitute-runtime/role/reason"
        )
    if args.python_substitute_role and not args.python_fallback_reason:
        parser.error("--python-substitute-role requires --python-fallback-reason")
    if legacy_python_arguments_used:
        args.substitute_runtime = "python"
        args.substitute_reason = args.python_fallback_reason
        args.substitute_role = args.python_substitute_role or "fallback-primary"
        selected_runtimes.add("python")
    elif generic_substitute_arguments_used and not all((
        args.substitute_runtime,
        args.substitute_reason,
        args.substitute_role,
    )):
        parser.error(
            "--substitute-runtime, --substitute-role, and --substitute-reason must be supplied together"
        )
    if args.substitute_reason is not None:
        try:
            args.substitute_reason = validated_substitute_reason(args.substitute_reason)
        except ValueError as exc:
            parser.error(f"--substitute-reason {exc}")
    if (
        args.author_native_runtime
        and args.substitute_runtime
        and args.author_native_runtime == args.substitute_runtime
    ):
        parser.error("--substitute-runtime must differ from --author-native-runtime")

    selected_matlab: dict | None = None
    if args.matlab_executable or args.matlab_application:
        try:
            selected_matlab = selected_matlab_executable(
                args.matlab_application or args.matlab_executable,
                application=bool(args.matlab_application),
                workspace=workspace,
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
            for key in (
                "selectedPath", "invocationPath", "resolvedPath", "installationRoot", "identitySource",
            )
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
            "runtimeId": "python",
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
                "runtimeId": "python",
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
            "runtimeId": "matlab",
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
                "requiredLicenseFeatures": (
                    list(args.matlab_required_license_feature) if is_selected else []
                ),
                "requiredFunctions": list(args.matlab_required_function) if is_selected else [],
                "entrypoint": (
                    display_invocation_path(matlab_entrypoint, workspace)
                    if is_selected and matlab_entrypoint else None
                ),
                "entrypointPresentStatic": (
                    is_regular_non_symlink_file(matlab_entrypoint)
                    if is_selected and matlab_entrypoint else None
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

        if is_selected and args.matlab_live_probe:
            expression = matlab_live_probe_expression(
                list(args.matlab_required_toolbox),
                list(args.matlab_required_license_feature),
                list(args.matlab_required_function),
                matlab_entrypoint,
                matlab_search_directories,
            )
            with tempfile.TemporaryDirectory(prefix="scirepro-matlab-probe-") as probe_directory:
                probe_cwd = Path(probe_directory)
                probe, raw_stdout = run(
                    [str(candidate), "-batch", expression],
                    args.timeout,
                    workspace,
                    return_raw=True,
                    environment=matlab_probe_environment(),
                    redact_paths=[*matlab_private_paths, probe_cwd],
                    working_directory=probe_cwd,
                )
            entry["liveProbe"] = probe
            entry["workingDirectoryPolicy"] = "controlled-empty-temporary-directory"
            entry["verificationScope"] = (
                "runtime-startup-base-license-and-route-prerequisites-no-route-smoke"
            )
            entry["launchAuthorizedByPolicy"] = True
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
                    toolbox_payload = details.get("requiredToolboxes", [])
                    if isinstance(toolbox_payload, dict):
                        toolbox_payload = [toolbox_payload]
                    if not isinstance(toolbox_payload, list):
                        raise ValueError("MATLAB required toolbox results missing or invalid")
                    reported_toolboxes = {
                        str(item.get("name")).casefold(): {
                            "installed": bool(item.get("installed")),
                            "version": str(item.get("version") or ""),
                        }
                        for item in toolbox_payload
                        if isinstance(item, dict) and item.get("name")
                    }
                    # Accept the older compact test/fixture shape without asking the live probe
                    # to emit a machine-wide toolbox inventory. Production probes return only
                    # route-required toolbox checks so their bounded output cannot be truncated.
                    if args.matlab_required_toolbox and not reported_toolboxes:
                        legacy_toolboxes = details.get("toolboxes", [])
                        if isinstance(legacy_toolboxes, dict):
                            legacy_toolboxes = [legacy_toolboxes]
                        if not isinstance(legacy_toolboxes, list):
                            raise ValueError("MATLAB toolbox results missing or invalid")
                        installed_toolboxes = {
                            str(item.get("name", "")).casefold(): str(item.get("version") or "")
                            for item in legacy_toolboxes
                            if isinstance(item, dict) and item.get("name")
                        }
                        reported_toolboxes = {
                            name.casefold(): {
                                "installed": name.casefold() in installed_toolboxes,
                                "version": installed_toolboxes.get(name.casefold(), ""),
                            }
                            for name in args.matlab_required_toolbox
                        }
                    toolbox_checks = [
                        {
                            "name": name,
                            "installed": reported_toolboxes.get(
                                name.casefold(), {"installed": False},
                            )["installed"],
                            "version": reported_toolboxes.get(
                                name.casefold(), {"version": ""},
                            )["version"],
                        }
                        for name in args.matlab_required_toolbox
                    ]
                    license_payload = details.get("requiredLicenseFeatures", [])
                    if isinstance(license_payload, dict):
                        license_payload = [license_payload]
                    if not isinstance(license_payload, list):
                        raise ValueError("MATLAB license feature results missing or invalid")
                    reported_licenses = {
                        str(item.get("feature")): bool(item.get("available"))
                        for item in license_payload
                        if isinstance(item, dict) and item.get("feature")
                    }
                    license_checks = [
                        {"feature": name, "available": reported_licenses.get(name, False)}
                        for name in args.matlab_required_license_feature
                    ]
                    function_payload = details.get("requiredFunctions", [])
                    if isinstance(function_payload, dict):
                        function_payload = [function_payload]
                    if not isinstance(function_payload, list):
                        raise ValueError("MATLAB function results missing or invalid")
                    reported_functions = {}
                    for item in function_payload:
                        if not isinstance(item, dict) or not item.get("name"):
                            continue
                        exist_code = item.get("existCode")
                        if not isinstance(exist_code, int):
                            raise ValueError("MATLAB function result is missing an integer existCode")
                        reported_functions[str(item["name"])] = exist_code
                    function_checks = [
                        {
                            "name": name,
                            "existCode": reported_functions.get(name, 0),
                            "exists": reported_functions.get(name, 0) in {2, 3, 6},
                        }
                        for name in args.matlab_required_function
                    ]
                    entrypoint_exists = (
                        is_regular_non_symlink_file(matlab_entrypoint)
                        if matlab_entrypoint else True
                    )
                    details["entrypoint"] = {
                        "path": (
                            display_invocation_path(matlab_entrypoint, workspace)
                            if matlab_entrypoint else ""
                        ),
                        "exists": entrypoint_exists,
                        "verification": "python-static-regular-non-symlink-file",
                    }
                    details["requiredToolboxes"] = toolbox_checks
                    details["requiredLicenseFeatures"] = license_checks
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
                    entry["requiredLicenseFeaturesVerified"] = all(
                        item["available"] for item in license_checks
                    )
                    entry["requiredFunctionsVerified"] = all(
                        item["exists"] for item in function_checks
                    )
                    entry["entrypointVerified"] = entrypoint_exists
                    prerequisites_present = all((
                        entry["requiredToolboxInstallationsVerified"],
                        entry["requiredLicenseFeaturesVerified"],
                        entry["requiredFunctionsVerified"],
                        entry["entrypointVerified"],
                    ))
                    entry["prerequisitesPresent"] = prerequisites_present
                    entry["routeCapabilityVerified"] = False
                    entry["routeSmokeTested"] = False
                    entry["verified"] = False
                    entry["verificationStatus"] = (
                        "prerequisites-present" if prerequisites_present else "failed"
                    )
                    if not prerequisites_present:
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
            "runtimeId": runtime_id,
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
    matlab_live_probed = bool(selected_matlab and args.matlab_live_probe)
    matlab_workspace_executed = bool(
        matlab_live_probed and is_lexically_within(selected_matlab["invocationPath"], workspace)
    )
    workspace_execution_scopes = []
    if workspace_python_probed:
        workspace_execution_scopes.append("explicit-pep405-python-binary-no-site-only")
    if matlab_workspace_executed:
        workspace_execution_scopes.append("explicit-matlab-live-probe")
    runtime_entries: dict[str, list[dict]] = {
        "python": py_entries,
        "matlab": matlab_entries,
    }
    for entry in other:
        runtime_id = entry.get("runtimeId")
        if isinstance(runtime_id, str):
            runtime_entries.setdefault(runtime_id, []).append(entry)
    route_recommendation = native_route_recommendation(
        artifacts,
        runtime_entries,
        args.substitute_reason,
        args.substitute_role,
        author_native_runtime=args.author_native_runtime,
        substitute_runtime=args.substitute_runtime,
        author_runtime_selection_source=(
            "--author-native-runtime" if args.author_native_runtime else None
        ),
        legacy_python_arguments_used=legacy_python_arguments_used,
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
        "A MATLAB live probe requires a non-workspace launcher with a recognized installation shape, trusted static product identity, an exact --matlab-application/--matlab-executable, and --matlab-live-probe. The caller must apply permission-gates.md before invoking it; no second approval flag is required.",
        "A successful MATLAB prerequisite probe verifies startup/base runtime, installed toolboxes, supplied license feature identifiers, clean-path system functions, and a Python-static regular entrypoint. It does not execute the entrypoint or constitute a route smoke test.",
        "The MATLAB prerequisite probe starts in a controlled empty temporary working directory, resets to the default MATLAB path before queries, never adds or executes author directories, and restores the original path before exit.",
        "MATLAB may execute the user's configured startup hooks before the batch expression begins; the probe cannot suppress or characterize those trusted user-level hooks.",
        "Artifact suffixes are candidate metadata, not author-runtime identity. In particular, .m is shared by MATLAB and GNU Octave; route recommendation requires an explicit --author-native-runtime selection supported by target-relevant evidence.",
        "An available-but-untested author-native stage must be resolved before a fallback-primary substitute. Objective-driven portability or independent implementations may use any declared --substitute-runtime with an explicit role and reason.",
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
        try:
            write_text_create_only(args.output, payload)
        except SafeOutputError as exc:
            parser.error(str(exc))
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
