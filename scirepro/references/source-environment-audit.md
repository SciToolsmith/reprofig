# Source, data, and environment investigation

Use this reference only when a named uncertainty about external code, data, formulas, or execution capability can change the route, supported claim, safety, material cost, or required deliverable. Begin with the target-dependent generation chain and stop when another check cannot change a decision.

## Govern investigation cost

Before expanding investigation with another search branch, subagent, broad probe, or additional scientific run, name internally the unknown it will resolve and the decision it can change. Normal reads and commands inside the chosen branch need no per-call justification or narration. Prefer one authoritative check over parallel archaeology. Do not reopen a settled question merely to collect more sources.

Delegate only an independently bounded specialist question that materially benefits from parallel work. Pass the minimum paper section, target, source path, and decision context; do not send the whole task or launch duplicate scouts.

Reach a runnable, scientifically defensible route as soon as possible. Do not delay the first useful V0 for exhaustive paper review, dependency inventory, historical version search, or machine-wide discovery.

Treat missing information by scientific consequence, not by completeness. After one bounded authoritative check of the paper and strongest available artifact, if unavailable or unpublished exact original-case input, configuration, parameters, or realization prevents direct recomputation, do not widen archaeology merely to recover it. Continue investigating only when another bounded source is likely to change a declared observable or claim. Otherwise switch immediately to a transparent `mechanism-reproduction` or `alternative-validation` when it still answers the objective, or report the narrower exact-original case as blocked.

## Choose evidence for the objective

Author code in its native data format and runtime is normally the strongest evidence-preserving route for exact or close recomputation. Prefer it when it serves the user's objective.

Native-first is a preference, not a universal rule. An independent derivation or implementation may better test a mechanism; a port may be required for portability; a second engine may provide a requested cross-check. State each substitution, why it serves the objective, what evidence boundary changes, and which target-relevant compatibility checks support it. Never imply equivalence merely because both routes run.

## Source and code

Prefer authority in this order when applicable: verified user-supplied artifact; author, publisher, or official project; institution or funder repository; paper-cited repository; verified archive; clearly labelled third-party source.

For each source that materially supports execution or interpretation, retain internally its identity, authority, safe locator, version or commit, checked date, hash when useful, access state, license, and redistribution status. Public availability does not imply redistribution permission.

Use `scripts/inspect_artifact.py` when a local archive or code tree needs deterministic, non-executing inspection. Limit review to target-relevant licenses, dependency declarations, entry points, defaults or randomness capable of changing the result, I/O, network/system effects, install hooks, binaries, unsafe deserialization, and telemetry. Map only relevant source paths to the target's input, preprocessing, method, aggregation, and plotted output.

Use the smallest bounded smoke test that can distinguish runnable from unavailable; it is not a reproduced figure. Preserve necessary compatibility changes as small overlays or diffs and state their scientific effect.

## Formula and implementation correspondence

Check only mathematical dependencies capable of changing the target or acceptance result: relevant definitions, units, dimensions, shapes, indices, normalization, signs, initial/boundary conditions, admissible ranges, and parameter values. Do not audit every formula in the paper.

If paper and code differ materially, preserve both readings. Compare them when both answer the objective, ask when the choice changes the supported claim, or block when neither can be justified. Never silently correct an expression or select whichever interpretation resembles the published figure.

## Data identity

Match data by more than topic or filename. Check only identifiers required to establish the paper case: variables and units, sample count/rate, duration, channels or specimen/device IDs, split/segment, preprocessing/calibration, version, hash, license, and restrictions. Classify the input as exact original, official example, paper-defined simulation, substitute validation data, or unavailable/restricted. Determine material size and access requirements before retrieval.

## Runtime capability

Probe only the engines, packages/toolboxes, functions, licenses, and hardware required by the chosen route. Use `scripts/probe_environment.py` when its deterministic discovery or route-specific probe can resolve a live uncertainty; do not run broad inventory by default.

Distinguish:

- `verified`: the exact required capability ran successfully;
- `available`: a candidate installation exists but route capability remains untested;
- `unknown`: the focused probe was inconclusive;
- `missing`: the relevant documented search found no candidate.

Do not infer absence from one failed `which`, import, or launcher. A found runtime does not establish its packages, toolbox, license, entry point, or data compatibility.

For MATLAB, pass the exact entrypoint and only relevant author `.m`, `.mlx`, or `.p` artifacts to a live capability probe. Static discovery is not execution evidence. A failed or timed-out native probe leaves the route inconclusive unless a target-relevant fallback reason already justifies a declared substitute; do not silently retry broadly or switch languages.

For ecosystems without a specialized probe, validate a reviewed absolute executable with the smallest safe route-specific command. Follow [permission-gates.md](permission-gates.md) before proprietary-runtime launch, dependency installation, or binaries with uncertain effects.

Prefer an existing compatible environment. Check host-provided bundled workspace runtime paths before provisioning another copy, then inspect only relevant task or user environments. If none works, create a project-local open-source environment only within permitted bounds. Never change global packages or install or activate proprietary software silently.

Keep queries, discarded sources, repository inventories, probe transcripts, machine-wide findings, and diagnostic logs in the transient workspace. The customer folder receives only the selected source/data identity, actual runtime and dependencies needed to rerun, material substitutions, rights, and unresolved capability limits.
