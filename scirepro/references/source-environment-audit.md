# Source and environment audit

Use this audit only when a candidate route depends on external code/data or uncertain local capability. Start from route requirements; do not inventory unrelated software, hardware, repositories, or datasets.

## Source authority and record

Prefer: user artifact → author/publisher/official project → institution/funder repository → paper-cited repository → verified archive → labeled third-party source.

For each relevant source, record authority, URL, version/commit, checked date, access state, declared/local size, SHA-256, license, and redistribution status. A local archived artifact may coexist with an upstream `login-required` state. Public visibility does not imply a license.

## Code audit

1. Retrieve only from a verified public route and within budget, unless separately approved.
2. Preserve and hash the original. List an archive before extraction; reject absolute paths, `..`, device files, and suspicious links.
3. Read the license, dependency declarations, public entry point, key implementation, defaults, randomness, I/O, network/system effects, install hooks, native binaries, unsafe deserialization, and telemetry relevant to the route.
4. Map interfaces and key source to generation-chain links; label origins `paper`, `code`, `derived`, `assumption`, or `user`.
5. After static inspection, run only the smallest useful smoke test in a temporary directory with bounded resources and no network after setup. Record command, environment, exit code, runtime, output shape/type, and errors. Do not call it figure reproduction.

Use `<skill-root>/scripts/inspect_artifact.py` for the initial inventory. Stop once enough evidence exists to accept, reject, or condition the route.

## Data identity

Do not accept a dataset by topic or filename alone. Match the paper case using DOI/authors/experiment, variables and units, sample count/rate/duration, channels or specimen/device IDs, split/segment, preprocessing/calibration, version, checksums, license, and restrictions.

Classify it as exact original input, official example with stated confidence, paper-defined simulation, substitute data for alternative validation, or unavailable/request-required/restricted. Determine payload size from metadata or headers before download. Ask before large, login-gated, controlled, paid, private, or over-budget retrieval.

## Avoid environment false negatives

Probe only engines, packages/toolboxes, functions, licenses, and hardware required by candidate routes. Use `<skill-root>/scripts/probe_environment.py` with explicit `--runtime`; reserve `--runtime all` for a requested inventory. Automatic Python discovery is static-only and must never launch a PATH, Conda, or workspace candidate.

Check, in order:

1. active/current interpreter or executable and project configuration;
2. PATH plus shell aliases/functions and standard OS application locations;
3. project-local `.venv`, Conda/virtualenv/pyenv/uv/Poetry environments and product launchers;
4. candidate executables by absolute path;
5. exact package/toolbox/function, license, and hardware capability.

Do not infer absence from one failed `which`, import, or launcher probe. Use:

- `verified` only after the exact route-required capability succeeds in the current interpreter or a deliberately selected, safely audited project environment;
- `available` when static inspection finds a candidate but route-level execution remains untested;
- `unknown` when probing is inconclusive;
- `missing` only after the documented relevant search finds no candidate.

Keep evidence certainty separate from execution readiness. A statically available runtime may leave a route `conditional`; a verified runtime does not repair missing data or method evidence.

When promoting a route environment to `verified`, save a redacted route-specific probe result as a local file, hash it, and declare it as an `environment-audit` source artifact. Reference that source from the environment. Do not use the paper, a documentation page, or a bare executable path as proof that the required runtime/toolbox/license capability actually ran.

### Python and open-source ecosystems

First inspect the current interpreter and existing project-local environments without modifying them. Finding an interpreter is only `available`. To live-probe an interpreter the user or approved route deliberately selected, pass its absolute path explicitly:

```bash
python <skill-root>/scripts/probe_environment.py \
  --workspace <task-workspace> \
  --runtime python \
  --python-executable /absolute/path/to/python \
  --output <task-workspace>/environment-audit.json
```

The selected launcher may be a regular native executable or a symlink resolving to one. SciRepro records the launcher and resolved native binary as separate redacted identities. Script/shim targets and broken or non-regular targets are rejected before execution when their file type can be established.

For a workspace virtual environment, add the separate explicit gate `--allow-workspace-python`. The launcher must have the standard `<venv>/bin/python*` or `<venv>/Scripts/python*.exe` shape and `<venv>/pyvenv.cfg` must be a regular non-symlink file. This establishes only a static PEP 405 identity. Without the gate, workspace executables remain static-only; do not add the gate merely because discovery found one.

Every explicit Python probe uses `-I -S`, a minimal allowlisted environment, and a 60-second maximum timeout. `-S` is mandatory: it prevents `site`, `sitecustomize.py`, `.pth` processing, and site-packages from running. The probe performs no install, global mutation, or network request. A failed or malformed probe stays `failed`, never `verified`, and its evidence remains redacted.

Because `-S` also suppresses PEP 405 activation on supported Python versions, a selected venv reports two deliberately separate facts: `pep405Identity.status: detected-static` and `binaryProbeStatus: verified-no-site`. Keep its overall `verificationStatus: available`, `verified: false`, `siteRuntimeVerified: false`, and `packagesVerified: false`. Do not treat the marker detection or no-site binary start as proof that the venv, its packages, or its `sitecustomize`-affected runtime works.

This probe verifies the interpreter and isolation flags only. Promote a route environment to `verified` only after separate bounded checks also establish its exact route imports/functions and basic invocation; merely finding its directory or passing the interpreter probe is insufficient.

Prefer a compatible existing environment. If none works, create a new project-local isolated environment within the R1 budget; never change global packages. Treat packages with native install hooks or unknown binaries according to their higher permission level.

### MATLAB

Check PATH and standard application locations such as macOS `/Applications/MATLAB_R*.app/bin/matlab`, Windows Program Files, and common Linux roots. Static release detection is `available + existing-only`, not verified.

A live batch probe can execute startup configuration or consume a shared license. Treat it as R2 when license consumption, startup effects, or institutional access may occur. Verify version, required toolboxes/functions, and `license('test', ...)`; do not install MATLAB or accept terms automatically. If a user says MATLAB exists after an inconclusive probe, search direct application paths before reporting `missing`.

### Other proprietary tools and hardware

For COMSOL, Abaqus, ANSYS, Mathematica, LabVIEW, Origin, and similar tools, verify executable, version, required modules, license availability, and noninteractive support. Installation, activation, shared-license use, or remote submission requires approval.

Record CPU architecture, RAM, free disk, and route-required GPU/driver/runtime. Do not use cloud services or shared clusters without separate approval.

## If no compatible runtime exists

- For open-source routes, propose or create a project-local environment within budget.
- For proprietary routes, complete static inspection and mark execution verification unavailable; do not silently install or substitute.
- Offer an open-source implementation only as a separate evidence-backed route. Do not imply numerical equivalence without validation.
