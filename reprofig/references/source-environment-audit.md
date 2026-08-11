# Source and environment audit

## Establish source authority

Use this priority order:

1. user-provided artifact;
2. author, publisher, or official project page;
3. institution or funder repository;
4. repository cited by the paper;
5. archival service with author/version evidence;
6. third-party port or mirror, explicitly labeled.

For each source, record author/publisher, URL, version or commit, checked date, access state, declared size, local size, SHA-256, license, and whether redistribution is permitted. A GitHub repository without a license is readable but not automatically reusable or redistributable.

## Inspect code before execution

1. Download only through a verified public route within budget.
2. Preserve the original archive and compute SHA-256.
3. List archive entries without extracting first. Reject absolute paths, `..`, device files, and suspicious links.
4. Find the license and distinguish use permission from redistribution permission.
5. Read the public entry point, key algorithm implementation, dependency declarations, defaults, randomness, file/network/system operations, unsafe deserialization, native binaries, MEX files, install hooks, and telemetry.
6. Map function inputs and outputs to the figure dependencies.
7. Run a bounded smoke test only after static inspection. Use a temporary directory, non-root execution, resource limits, and no network after environment setup.
8. Record exact command, exit code, runtime, output shape/type, and errors. Describe it as a smoke test, not figure reproduction.

If no compatible runtime exists:

- For open-source ecosystems, first search existing environments; then create a project-local isolated environment within budget.
- For proprietary runtimes, do not download installers, accept terms, or consume shared licenses automatically. Complete static inspection and mark execution verification unavailable.
- Treat an open-source alternative as a separate route. Do not imply numerical equivalence without validation.

Use `scripts/inspect_artifact.py` to create the initial artifact inventory.

## Verify data identity

Do not accept a dataset merely because its topic or filename is similar. Compare:

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

Do not conclude “not installed” from one `which` or import failure.

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

Check PATH plus standard application locations such as macOS `/Applications/MATLAB_R*.app/bin/matlab`, Windows Program Files, and common Linux install roots. Use absolute-path batch probes to obtain version, toolbox inventory, `license('test', ...)`, and required function locations. Do not infer absence from PATH alone. Do not install MATLAB or accept a MathWorks license automatically.

### Other proprietary tools

For COMSOL, Abaqus, ANSYS, Mathematica, LabVIEW, Origin, and similar systems, verify executable, version, license availability, required modules, and noninteractive support. Installation, activation, shared-license consumption, and remote cluster submission require explicit approval.

### Hardware

Record CPU architecture, RAM, free disk, GPU model/driver/runtime, and whether the approved job fits local resources. Do not use cloud services or shared clusters without separate approval.
