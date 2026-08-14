# Execution and validation

Execute the selected route as a scientific test of declared observables. A successful command is not sufficient validation, and image similarity is not independent evidence for a paper claim.

## Prepare the transient run

- Work inside one dedicated, create-only internal workspace under system temporary storage or a hidden `.scirepro-work/<task-id>/` root. Never place it beside the customer folder as a second visible delivery. Preserve supplied originals read-only and keep target acquisition, search notes, probes, intermediate code, raw logs, QA, and manifests there.
- Freeze internally the target identity, selected route and scientific scope, actual source/input/configuration, implementation and runtime, parameters or seeds, acceptance criteria, permitted effects, resource declarations, and intended customer deliverables.
- Treat declared resource caps as planning authority, not enforcement evidence. Record internally which limits were enforced and which resources were measured.
- Trace only the target-relevant executable chain: input and selection, preprocessing/calibration, method/model, aggregation/statistics, and visual encoding. Mark material stages reproduced, substituted, derived, assumed, uncovered, or not required.
- Ask only when a genuinely new route, scientific choice, or authority decision appears. Normal reads and commands, harmless formatting changes, and evidence-preserving compatibility fixes inside the chosen step need no separate justification; expansion beyond that step still passes the global cost governor.

Do not initialize the customer folder before useful persistent results exist. Do not create a pre-execution webpage, contract, approval receipt, or gate artifact.

## Execute the honest route

- `direct-recompute`: use verified original or official input and implementation. Do not use it when input identity is only probable.
- `mechanism-reproduction`: reconstruct the reported mechanism from code, equations, and transparent assumptions; validate the phenomenon it is meant to produce.
- `alternative-validation`: use a declared substitute dataset, implementation, or experiment to test a narrower transferable claim.
- `image-derived-reconstruction`: validate only the declared visual, geometric, digitization, or editability objective.
- `original-case-blocked`: do not fabricate missing input or method. Preserve the blocker and lawful reopening condition.

Verify formulas and parameters only as far as the target and acceptance decision require. Preserve derivations, ambiguities, and material paper-code differences. A semantic scientific schematic that reaches execution was misrouted; return it to [diagram-handoff.md](diagram-handoff.md) without creating a SciRepro result for that target.

## Handle unknowns by scientific consequence

The role of an unknown is target-dependent. Classify it by whether plausible choices can change a declared observable, acceptance decision, or supported claim:

- **Claim-defining or otherwise material:** resolve, derive, or bound it. If plausible choices could reverse the conclusion, use the smallest discriminating comparison; block only the requested claim that still depends on unavailable information.
- **Nuisance but consequential:** choose a value constrained by the paper, author code, visible observables, or a defensible domain convention, mark it `assumed`, and test a small alternative only when acceptance could change.
- **Incidental:** fix a non-critical seed, another reproducible value, or a reasonable presentation choice once and continue. Do not search for the author's exact seed or realization when it cannot affect the scientific decision.

Choose assumptions before final comparison where practical and state their basis and claim boundary. Never describe an assumption as recovered from the authors, tune it solely for visual resemblance, or select seeds, inputs, runs, or parameter combinations because they look favorable. Multiple plausible assumptions producing the same declared phenomenon can support a mechanism result; materially conflicting outcomes require a bounded sensitivity check or an inconclusive conclusion.

Treat any target feature used to estimate, select, or calibrate an assumed parameter as calibration evidence, not independent validation. Validate on another predeclared observable, held-out region or condition, or an external constraint; when none exists, narrow the claim to a calibrated reconstruction or mark the scientific test inconclusive.

## Define acceptance

For scientific reproduction, evaluate in this order when relevant:

1. variables, samples, units, axes, scales, and domain;
2. qualitative phenomenon, topology, modes, peaks, ordering, or trend;
3. quantitative values and uncertainty within justified tolerance;
4. robustness only when the claim or negative interpretation depends on it;
5. visual encoding and presentation needed to preserve meaning and readability.

Set tolerances before inspecting final outputs where practical. For image-derived work, validate only identifiable coordinate calibration, geometry/topology, annotations, panels, appearance, or editability, including uncertainty from resolution, marks, occlusion, compression, and antialiasing.

## Reach the first useful V0

Produce and preserve the first scientifically meaningful output as V0 as soon as the route is defensible. Do not delay V0 for broad source archaeology, exhaustive environment inventory, speculative parameter search, or cosmetic planning.

For a small local target whose actual computation is expected to take seconds or minutes, aim to reach the first honest V0 within roughly 10–15 minutes. Treat this as a planning checkpoint, not a universal deadline. If it passes without V0, stop expanding investigation and either run the strongest defensible route or state the concrete blocker.

Compare V0 at two levels:

- scientific: variables, units, scale, trends, peaks, extrema, ordering, magnitude, uncertainty, and relevant robustness;
- presentation: fix semantic encoding, overlap, clipping, contrast, or unreadable labels when needed; treat exact palette, typography, spacing, and rendering details as secondary unless the declared objective makes them material.

Once the scientific content is stable, correct only presentation defects that hide or misstate it. Stop when the figure communicates the accepted observables clearly; do not reopen scientific tuning merely to improve cosmetic resemblance.

Diagnose each material discrepancy. Before expanding investigation with another search branch, subagent, broad probe, or additional scientific run, name internally the unknown or hypothesis and how its answer can change the route, claim, safety, material cost, or required deliverable. This branch-level check needs no ledger, artifact, or user-facing narration. Record scientifically meaningful changes and predictions internally; do not preserve unnecessary cosmetic versions.

Run sensitivity analysis only when acceptance of the claim or interpretation of a negative result depends on stability across seeds, perturbations, parameters, or numerics. Use the smallest design that can answer that question; do not run a default grid.

Stop when criteria pass, remaining differences are non-critical, another action would only chase pixels, repeated tests add no explanation, or expected information gain no longer justifies cost or risk. There is no fixed universal iteration count.

## Interpret results honestly

Report operational, validation, and claim states independently. Use `supported`, `partially-supported`, `unsupported`, `inconclusive`, or `not-tested` for scientific claims; image-derived work uses `not-applicable`. `Unsupported` requires a valid implementation and test that actually exercises the claim. A crash, missing input, or absent validation does not establish an unsupported claim.

Preserve negative results, contrary outputs, informative failed attempts, relevant sensitivity evidence, and remaining uncertainty. Before interpreting an anomaly, check only relevant data identity, implementation trace, units, preprocessing, parameters, seeds, numerical behavior, environment, and plotting transforms. Do not search indefinitely for favorable settings.

Failure to reproduce is not by itself evidence of fabrication. Record a potential integrity concern only when a specific anomaly is independently repeatable and relevant ordinary differences have been actively tested without explaining it. State facts and uncertainty neutrally; contacting authors, journals, or other third parties requires explicit authorization.

## Assemble the customer folder

After execution, use [delivery-contract.md](delivery-contract.md) to plan and assemble exactly one customer folder from the transient workspace. Invoke `python <skill-root>/scripts/assemble_delivery.py --plan <plan.json> --output-root <parent>` only after the delivery plan names the selected customer artifacts. Promote only the plain-language result, selected outputs, rerun essentials, target/source boundary, material assumptions, validation evidence, rights, and unresolved differences required to understand or reuse the work.

Do not expose raw search traces, broad environment inventories, QA overlays, internal manifests, debugging logs, middleware metadata, or redundant attempts as customer deliverables. Summarize a material fact or promote a purpose-built evidence artifact instead. Keep multi-target outcomes isolated so one target's failure cannot alter another's result.
