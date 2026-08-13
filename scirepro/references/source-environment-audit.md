# Source, data, and environment audit

Use this reference only when external code/data or uncertain execution capability can change the selected route. Begin with the target-dependent generation chain and stop when another check cannot change feasibility, claim scope, material cost, or safety.

## Choose evidence for the objective

Author code in its native data format and runtime is normally the strongest route for exact or close recomputation. Prefer it when it serves the user’s objective. Do not choose Python merely because it is convenient when the relevant author implementation is MATLAB, R, Julia, Fortran, or a domain solver.

Native-first is an evidence preference, not an end in itself. An independent derivation or reimplementation may be preferable for mechanism testing; a port may be required for portability; a second engine may be valuable for cross-validation. State every substitution, why it serves the objective, what evidence it changes, and which compatibility checks support it. Never imply equivalence merely because both routes run.

## Source and code

Prefer authority in this order when applicable: user-supplied verified artifact; author/publisher/official project; institution or funder repository; paper-cited repository; verified archive; clearly labelled third-party source.

For each source that materially supports execution or interpretation, record identity, authority, URL or safe locator, version/commit, checked date, hash when available, size, access state, license, and redistribution status. Public availability does not imply redistribution permission.

Use `scripts/inspect_artifact.py` when a local archive or code tree needs a deterministic, non-executing inventory. Before execution:

1. Preserve and hash the original artifact.
2. Inspect only relevant licenses, dependency declarations, entry points, defaults, randomness, I/O, network/system effects, install hooks, binaries, unsafe deserialization, and telemetry.
3. Map relevant source paths to the target’s input, preprocessing, method, aggregation, and plotted output.
4. Use the smallest bounded smoke test that can distinguish runnable from unavailable; a smoke test is not a reproduced figure.
5. Preserve compatibility patches as small overlays or diffs and record their scientific effect.

## Formula and implementation correspondence

Check only mathematical dependencies that can change the selected target or acceptance result. Verify the relevant symbol definitions, units, dimensions, shapes, indices, normalization, signs, initial/boundary conditions, admissible ranges, and parameter values against the paper, implementation, cited primary source, and target behavior.

If paper and code differ materially, preserve both readings. Compare them when both answer the objective, ask when choosing changes the supported claim, or block when neither reading can be justified. Do not silently correct an expression or select whichever output resembles the published curve.

## Data identity

Match data by more than topic or filename. Use the paper case, variables/units, sample count or rate, duration, channels/specimen/device IDs, split or segment, preprocessing/calibration, version, hashes, license, and restrictions. Classify the input honestly as exact original, official example, paper-defined simulation, substitute validation data, or unavailable/restricted. Determine likely size and access requirements before retrieval.

## Runtime capability

Probe only the engines, packages/toolboxes, functions, licenses, and hardware required by the route. Use `scripts/probe_environment.py` when its deterministic discovery or supported route-specific probe is useful; do not run its broad inventory unless the user requests one.

Distinguish:

- `verified`: the exact route-required capability ran successfully;
- `available`: a candidate installation or interpreter was found but route capability remains untested;
- `unknown`: the relevant probe was inconclusive;
- `missing`: the relevant documented search found no candidate.

Do not infer absence from one failed `which`, import, or launcher. A found runtime does not establish its packages, toolbox, license, entry point, or data compatibility.

For an explicit MATLAB live capability probe, pass the exact entrypoint and relevant author `.m`, `.mlx`, or `.p` artifacts. The probe temporarily adds only their existing parent directories, checks named functions and the entrypoint with `exist`, and restores the original MATLAB path with `onCleanup`; it does not recursively scan those directories or execute author code. This prevents nested author source trees from being mistaken for missing functions without turning capability discovery into a route smoke test.

`probe_environment.py` emits a `scirepro.environment/v2` record that can be frozen directly in a result bundle. Only live-verified runtimes enter `engines`; a statically discovered MATLAB installation remains `available` evidence and leaves the record `partial`. Static availability still preserves the author-native preference. If a live probe falsifies a required MATLAB capability, Python becomes the recommended `declared-fallback` only when a target-relevant fallback reason was recorded; otherwise do not switch runtimes automatically. A live-probe launch failure, timeout, or invalid result is not static availability: it leaves the selected native route inconclusive. A recorded target-relevant fallback reason permits a declared Python substitute; without one, the route needs a new decision instead of silently retrying MATLAB or switching languages. Persisted probe commands and diagnostics use path placeholders, including for entrypoints and author-source directories outside the task workspace.

For ecosystems not covered by a specialized probe, `probe_environment.py` reports only static discovery and never executes the `PATH` candidate. Validate the chosen route with an explicitly reviewed absolute executable and the smallest safe route-specific smoke command rather than biasing the route toward a better-instrumented language. Follow [permission-gates.md](permission-gates.md) before launching proprietary runtimes, installing dependencies, or executing binaries with uncertain effects.

Prefer an existing compatible environment. If none works, a project-local open-source environment may be created inside the declared automatic bounds. Never change global packages or install/activate proprietary software silently.
