# Source, data, and environment investigation

Use this reference only when a named uncertainty about external code, data, formulas, or execution capability can change the route, supported claim, safety, material cost, or required deliverable. Missingness alone never triggers network discovery. Begin with the target-dependent generation chain and stop when another check cannot change a decision.

## Start locally and keep only decision-changing gaps

Read the target caption, target-relevant paper sections, supplement/code/data statements, and user-supplied or already-local artifacts before discovery. Do not audit the whole paper merely to make a complete missing-information list. Treat an explicit paper-cited external artifact as directed retrieval, not permission for broader discovery; retrieve it only when its role in the target chain is material.

Keep a short transient decision queue containing only: the unresolved fact, the decision it can change, the strongest likely authority, and the next action if it is found or remains absent. Do not turn this queue into a schema, report, customer artifact, or completeness checklist. If no claim-defining item prevents an honest route, reach V0 before external discovery.

## Gate and sequence network work

Start a network search branch only when all are true:

- current paper, target, supplied files, and relevant local artifacts do not resolve the fact;
- the fact can change the route, acceptance, claim, safety, material cost, or required deliverable;
- a defensible assumption, derivation, or substitute route cannot answer the same objective without it;
- a specific authoritative public source or artifact is reasonably likely to resolve it;
- either finding it or confirming its absence changes the next action.

Resolve the highest expected-information item first. Combine only related queue items likely to be answered by the same authoritative source; do not batch unrelated gaps. After every material result, recompute the queue and cancel searches made obsolete by a changed route. Delegate only an independently bounded question that benefits materially from parallel work, and never launch duplicate scouts.

Use this retrieval order: explicit paper or supplement links; author, publisher, official project, institution, funder, or paper-cited repository; then a focused discovery query naming the specific artifact or identity sought. Do not use broad topic search or reverse-image search to evade missing identity. Prefer one authoritative pass over parallel archaeology and never reopen a settled question merely to collect corroboration.

Before download, check the candidate's paper/target identity, authority, version, access and license, expected size and format, execution risk, and the exact queue item it is expected to close. Skip it when metadata, documentation, or a file listing already shows it cannot change the decision. Download the smallest necessary artifact, hash it when useful, inspect it statically before execution, and classify its evidential fit as exact original, partial, official example or paper-defined simulation, declared substitute, irrelevant, or unavailable/restricted. Public availability does not imply redistribution permission.

Stop when the route is scientifically defensible, remaining gaps are non-critical, the strongest authority confirms absence or restriction, or another search cannot change the next action. After one bounded authoritative pass, do not widen archaeology merely to recover unavailable exact input, configuration, parameters, or realization. Switch to transparent `mechanism-reproduction` or `alternative-validation` when either still answers the objective, or report the narrower exact-original case as blocked.

## Choose evidence for the objective

Author code in its native data format and runtime is normally the strongest evidence-preserving route for exact or close recomputation. Prefer it when it serves the user's objective.

Native-first is a preference, not a universal rule. An independent derivation or implementation may better test a mechanism; a port may be required for portability; a second engine may provide a requested cross-check. State each substitution, why it serves the objective, what evidence boundary changes, and which target-relevant compatibility checks support it. Never imply equivalence merely because both routes run.

## Source and code

Prefer authority in this order when applicable: verified user-supplied artifact; author, publisher, or official project; institution or funder repository; paper-cited repository; verified archive; clearly labelled third-party source.

For each source that materially supports execution or interpretation, retain internally its identity, authority, safe locator, version or commit, checked date, hash when useful, access state, license, and redistribution status.

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
