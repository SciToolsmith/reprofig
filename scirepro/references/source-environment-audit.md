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

Map the generation chain by stage before choosing an engine. Determine which artifact actually produces the target input, preprocessing, method output, aggregation, and visualization. A missing original input does not make an available author method unusable: a defensible route may combine a transparent substitute input, the author-native method, and an independent plotting or validation layer. Conversely, a native artifact from another figure or downstream stage does not force its engine onto this target.

When target-relevant author-native code is present, identify its runtime from affirmative evidence before probing: the paper or author documentation, an intended launcher or manifest, target-relevant syntax and dependencies, or a user-supplied runtime identity. A filename suffix is only candidate metadata. In particular, `.m` is shared by MATLAB and GNU Octave; an isolated `.m` file must not select MATLAB, trigger a MATLAB inventory, or exclude Octave. Record the explicit author-native selection separately from any substitute runtime. For `probe_environment.py`, use `--author-native-runtime`; use the generic `--substitute-runtime`, `--substitute-role`, and `--substitute-reason` together for a fallback, portability implementation, independent implementation, or cross-check. The substitute runtime must differ from the author-native runtime, and the reason must be a concise, non-secret single-line scientific or deliverable justification. The deprecated Python-specific arguments are compatibility aliases only and never establish the author-native runtime.

Then ask whether a successful native run would materially change the route, claim, or required deliverable. If not—because the user explicitly wants a port, an independent implementation, or a mechanism-only cross-check—do not probe for ceremony; use the declared substitute and boundary. If it would change the evidence, resolve the native route before writing a primary port:

1. inspect the exact artifact and statically locate the intended runtime;
2. if detected, determine whether bounded local startup is automatic or requires new authority;
3. under automatic authority, run one focused live startup/base-license and route-prerequisite probe;
4. after static code review, run the smallest safe target-relevant operation or entrypoint smoke test needed to establish actual capability; and
5. select the primary role only after the result is `verified`, confirmed `missing` or `unavailable`, authority-required/declined, or still `inconclusive` after one useful diagnostic.

`Detected but untested` is not missing, unlicensed, or a scientific fallback reason. Do not create a circular fallback by declining to probe because license state is unknown and then citing that untested state as the reason to port. A missing or unavailable native runtime permits a declared mechanism or alternative implementation when it still answers the objective; it does not turn that implementation into an original-runtime recomputation. A failed or timed-out probe is inconclusive, not proof of absence. Ask only when native and substitute routes support materially different questions or when genuine authority is required.

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

Distinguish installation, authority, prerequisites, and executed capability rather than compressing them into one label:

- `missing`: the relevant documented search found no candidate;
- `available`: a candidate installation exists but live capability remains untested;
- `authority-required`: login, activation, shared/floating licensing, remote submission, or another gated effect prevents the probe;
- `inconclusive`: a bounded probe failed or timed out without distinguishing absence from a transient fault;
- `prerequisites-present`: startup and required installations, licenses, functions, and entrypoint presence were checked, but the target route itself was not run; and
- `verified`: the smallest reviewed target-relevant operation or entrypoint smoke test ran successfully.

Do not infer absence from one failed `which`, import, or launcher. A found runtime does not establish its packages, toolbox, license, entry point, or data compatibility.

For MATLAB, first establish MATLAB rather than Octave as the target-relevant author-native runtime. Select only a non-workspace MATLAB application or executable with a recognized installation layout and static MathWorks product identity; never execute an author-supplied launcher merely because it is named `matlab`. A `.mat` file alone identifies a data format, not the author runtime. Static discovery is not execution evidence. `--matlab-live-probe` is itself the explicit bounded launch action and must be invoked only after applying the permission policy; it should not create a second ceremonial approval step. The prerequisite helper starts in an empty temporary working directory and restores MATLAB's default path before machine/toolbox/license/function queries. It does not add author directories, and it verifies the exact entrypoint only as a Python-static regular non-symlink file; author code belongs only in the later reviewed route smoke. Use `--matlab-required-function` only for clean-default-path MATLAB or toolbox dependencies, never for the author entrypoint or an author helper. Otherwise absence from the deliberately clean path could be misread as missing capability and incorrectly authorize a fallback. MATLAB can still run the user's configured startup hooks before the batch expression begins, so do not claim that the helper suppresses or audits them. Accept required MATLAB/toolbox functions only when `exist(...,'file')` returns a file-class code (`2`, `3`, or `6`), never directory code `7`. Check exact required toolbox installations and, where relevant, supplied MATLAB license feature identifiers. Successful startup proves the base runtime can acquire its configured license; `ver` or a file-class `exist` result proves installation or visibility, not that a toolbox operation or author route runs. Treat these checks as prerequisites, then execute one reviewed target-relevant operation before calling the route verified. A failed or timed-out probe leaves the route inconclusive unless a target-relevant fallback reason already justifies a declared substitute; do not silently retry broadly or switch languages.

For ecosystems without a specialized probe, validate a reviewed absolute executable with the smallest safe route-specific command. Follow [permission-gates.md](permission-gates.md) before proprietary-runtime launch, dependency installation, or binaries with uncertain effects.

Prefer an existing compatible environment. Check host-provided bundled workspace runtime paths before provisioning another copy, then inspect only relevant task or user environments. If none works, create a project-local open-source environment only within permitted bounds. Never change global packages or install or activate proprietary software silently.

Keep queries, discarded sources, repository inventories, probe transcripts, machine-wide findings, and diagnostic logs in the transient workspace. The customer folder receives only the selected source/data identity, actual runtime and dependencies needed to rerun, material substitutions, rights, and unresolved capability limits.
