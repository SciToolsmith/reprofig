# Source and environment audit

## Purpose and timing

Use this audit only after the target figure's scientific meaning, paper-evidence role, generation chain, validation target, and candidate routes are understood. Treat sources and environments as evidence for or constraints on those routes, not as the purpose of SciRepro.

Start from candidate-route requirements. Audit relevant sources and local capabilities thoroughly enough to avoid false negatives, but do not inventory unrelated software, hardware, repositories, or datasets. Return every finding to a generation-chain link, route decision, or validation condition.

## Establish source authority

Use this priority order:

1. user-provided artifact;
2. author, publisher, or official project page;
3. institution or funder repository;
4. repository cited by the paper;
5. archival service with author/version evidence;
6. third-party port or mirror, explicitly labeled.

For each source, record author/publisher, URL, version or commit, checked date, access state, declared size, local size, SHA-256, license, and whether redistribution is permitted. Treat `access.state` as the current upstream retrieval or reacquisition status; a verified `artifact` separately records that a local copy is already present. For example, a local archived ZIP may coexist with `access.state: login-required` when a fresh upstream download requires sign-in. Use `local` for a user/local-only source without a separately verified retrieval route. A GitHub repository without a license is readable but not automatically reusable or redistributable.

## Inspect code before execution

1. Download only through a verified public route within budget.
2. Preserve the original archive and compute SHA-256.
3. List archive entries without extracting first. Reject absolute paths, `..`, device files, and suspicious links.
4. Find the license and distinguish use permission from redistribution permission.
5. Read the public entry point, key algorithm implementation, dependency declarations, defaults, randomness, file/network/system operations, unsafe deserialization, native binaries, MEX files, install hooks, and telemetry.
6. Map relevant entry points, function inputs and outputs, defaults, and file interfaces to the figure's explicit generation-chain stages. Use the schema origins `paper`, `code`, `derived`, `assumption`, or `user` for documented links. Put uncovered links in `generationLogic.unknowns` and, when they constrain a route, in a `missing` requirement or route blocker.
7. Run a bounded smoke test only after static inspection. Use a temporary directory, non-root execution, resource limits, and no network after environment setup.
8. Record exact command, exit code, runtime, output shape/type, and errors. Describe it as a smoke test, not figure reproduction.

If no compatible runtime exists:

- For open-source ecosystems, first search existing environments; then create a project-local isolated environment within budget.
- For proprietary runtimes, do not download installers, accept terms, or consume shared licenses automatically. Complete static inspection and mark execution verification unavailable.
- Treat an open-source alternative as a separate route. Do not imply numerical equivalence without validation.

Use `scripts/inspect_artifact.py` to create the initial artifact inventory.

Map environment findings into the report conservatively:

- use `verified` only after the exact route-required executable, packages/toolboxes/functions, license, and hardware capability have passed a live probe;
- use `available` when static inspection finds an installation or candidate runtime but does not establish route-level execution capability;
- use `unknown` when inspection is inconclusive and `missing` only after the documented search finds no candidate;
- mark proprietary, institutional, licensed, hardware-bound, or user-provided runtimes as `existing-only`;
- mark only project-locally installable open-source stacks as `isolated-open-source`.

An `available` environment can support only a `conditional` route. An unresolved `existing-only` environment blocks execution; do not convert it into an installation plan. An unresolved `isolated-open-source` environment may remain conditional only with an explicit gated `install` effect.

## Verify data identity

Do not accept a dataset merely because its topic or filename is similar. First identify which generation-chain stage and target observation require it, then compare:

- paper title, DOI, authors, experiment name, and repository citation;
- variables, units, sample count, sampling rate, duration, channels, subject/device/specimen IDs;
- train/test split, selected segment, preprocessing, calibration, missing-value policy;
- archive contents, checksums, version, license, and access restrictions.

Classify data as:

- exact original input;
- official example likely corresponding to the case, with stated confidence;
- paper-defined simulation that can be generated independently;
- substitute dataset suitable only for alternative validation;
- not found, request-required, controlled, or restricted.

Before download, obtain size from HTTP headers, repository metadata, manifests, or file listings. Ask before large data, login, DUA, payment, private access, or a download above the approved threshold. If possible, inspect metadata or a manifest without downloading the payload.

## Avoid environment false negatives

Probe the engines, packages, toolboxes, licenses, and hardware required by candidate routes. Call `probe_environment.py` with explicit route-specific `--runtime` values; its default is Python, and `--runtime all` is reserved for an explicitly requested inventory. Do not conclude “not installed” from one `which` or import failure, and do not perform a broad machine inventory unrelated to those routes.

### General sequence

1. Check current PATH and shell aliases/functions.
2. Check standard OS application and executable locations.
3. Query product-specific launchers and package managers.
4. Enumerate isolated environments.
5. Probe candidate executables directly by absolute path.
6. Verify the required package, toolbox, function, license, and hardware—not only the base executable.
7. Report `unknown` when access or probing is inconclusive.

### Python

Check the active interpreter, `python`, `python3`, Conda environments, virtualenvs, pyenv, uv, Poetry, and project-local environments. Probe imports in each candidate interpreter. Prefer an existing compatible environment; otherwise create a new project-local environment without changing global packages.

### MATLAB

Check PATH plus standard application locations such as macOS `/Applications/MATLAB_R*.app/bin/matlab`, Windows Program Files, and common Linux install roots. `probe_environment.py --runtime matlab --probe-matlab` reads static release metadata only and is safe for Phase 1; it records installation and metadata detection separately from runtime verification, does not launch MATLAB, and does not verify licensing. Launching an absolute-path batch probe to obtain the live version, toolbox inventory, `license('test', ...)`, or required function locations can execute startup configuration or consume a shared license. Treat that as a separately approved R2 investigation action and log the decision; when a floating or institutional license may be consumed, also declare `shared-license` on any execution route that needs it. Do not infer absence from PATH alone. Do not install MATLAB or accept a MathWorks license automatically.

In report terms, static MATLAB detection is `available + existing-only`, never `verified`. Promote it to `verified` only after the separately approved live probe establishes the exact capabilities required by the selected route.

### Other proprietary tools

For COMSOL, Abaqus, ANSYS, Mathematica, LabVIEW, Origin, and similar systems, verify executable, version, license availability, required modules, and noninteractive support. Installation, activation, shared-license consumption, and remote cluster submission require explicit approval.

### Hardware

Record CPU architecture, RAM, free disk, GPU model/driver/runtime, and whether the approved job fits local resources. Do not use cloud services or shared clusters without separate approval.
