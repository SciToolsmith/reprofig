# Execution and validation

Execute the frozen route as a scientific test of declared observables. A successful command is not sufficient validation, and image similarity is not independent evidence for a paper claim.

## Prepare and trace the run

- Initialize the single create-only staging folder through [run-bundle-contract.md](run-bundle-contract.md). Preserve originals read-only.
- Freeze target bytes, workflow mode, selected route kind and scientific scope, source/input/config identity, implementation and runtime, parameters or seeds, acceptance criteria, declared resource bounds, permitted effects, and expected deliverables.
- Treat declared resource caps as planning authority, not enforcement evidence. Record which limits the runner enforced and which resources were measured.
- Trace the executable path through every target-relevant stage: input and selection, preprocessing/calibration, method/model, aggregation/statistics, and visual encoding. Mark stages reproduced, substituted, derived, assumed, uncovered, or not required.
- Ask only when a new material route or permission decision appears. Equivalent retries, harmless formatting changes, and evidence-preserving compatibility fixes inside scope may proceed and must be recorded.

For image-derived work, trace from published pixels through coordinate calibration, digitization/tracing, inferred geometry, layout/appearance reconstruction, and output encoding. This chain cannot become independent evidence about the original research process.

## Execute the honest route

- `direct-recompute`: use verified original/official input and implementation. Do not use this route when input identity is only probable.
- `mechanism-reproduction`: reconstruct the reported mechanism from code, equations, and transparent assumptions; validate the phenomenon the mechanism is meant to produce.
- `alternative-validation`: use a declared substitute dataset, implementation, or experiment to test a narrower transferable claim.
- `original-case-blocked`: do not fabricate missing input or method. Preserve the blocker and lawful reopening path.
- `image-derived-reconstruction`: validate only the declared visual, geometric, digitization, or editability objective.

Verify target-relevant formulas and parameters far enough to test self-consistency and implementation correspondence. Preserve derivations, ambiguities, and paper–code differences. A scientific semantic schematic that reaches this phase was misrouted; return to [diagram-handoff.md](diagram-handoff.md) without creating a SciRepro result for it.

## Define acceptance

For scientific reproduction, evaluate in this order when relevant:

1. variables, sample definitions, units, axes, scales, and domain;
2. qualitative phenomenon, topology, modes, peaks, ordering, or trend;
3. quantitative values and uncertainty within a justified tolerance;
4. robustness across seeds, perturbations, or numerical settings;
5. visual encoding and presentation.

Set tolerances before inspecting final outputs where practical. For image-derived work, instead validate coordinate calibration, visible geometry/topology, annotations, panel structure, appearance, or editability as declared, including uncertainty from resolution, line width, markers, occlusion, compression, and antialiasing.

## Preserve V0 and iterate for information

Preserve the first scientifically meaningful output as V0 before tuning toward the target. Compare V0 at two levels:

- scientific: variables, units, scale, trends, peaks, extrema, ordering, magnitude, uncertainty, and robustness;
- presentation: palette, marks, legend, typography, layout, clipping, overlap, contrast, and readability.

Diagnose every material discrepancy. Continue only when the next run tests a named, evidence-based diagnosis or hypothesis and is expected to change the scientific conclusion, resolve route validity, or materially improve a required deliverable. Record the change, evidence, prediction, result, and whether it increased information.

Separate scientific changes—input, preprocessing, formula, algorithm, parameter, randomness, numerics, scale, units, or scientific range—from presentation repairs. Never use styling to conceal a scientific discrepancy. Preserve every scientifically meaningful version; omit unnecessary cosmetic versions.

Stop when acceptance criteria pass, remaining differences are non-critical, the next change would only chase pixels, repeated tests add no new explanation, or the expected information gain no longer justifies cost/risk. There is no fixed universal iteration count; narrower user or resource bounds still apply, and a newly material effect requires a new decision.

## Interpret and preserve results

Report operational, validation, and claim states independently. Use `supported`, `partially-supported`, `unsupported`, `inconclusive`, or `not-tested` for scientific claims; image-derived work uses `not-applicable`. `Unsupported` requires a valid implementation and test that actually exercises the claim. An actually attempted test that crashes or remains unresolved may be inconclusive when its validation is recorded as such; a pre-execution missing input or absent validation is not tested.

Keep the states semantically aligned: `supported` maps to complete/passed,
`partially-supported` to complete-or-partial/partially-passed, `unsupported` to a
complete/failed negative test, and `inconclusive` to an actually executed
complete, partial, or failed run with inconclusive validation. `not-tested` maps
exactly to validation `not-run`. Never use an operational failure as an unsupported
scientific result.

Preserve negative results, contrary outputs, relevant failed attempts, sensitivity checks, and remaining uncertainty. Before interpreting an anomaly, check relevant data identity, implementation trace, units, preprocessing, parameters, seeds, numerical behavior, environment, and plotting transforms. Do not search indefinitely for favorable settings.

Failure to reproduce is not by itself evidence of fabrication. Record a potential research-integrity concern only when a specific anomaly is independently repeatable and ordinary differences have been actively tested without explaining it. State the exact constraint, artifact, observation, repeatability, alternatives checked, and remaining uncertainty. Never infer intent or directly allege fraud or misconduct; contacting authors or journals, filing a report, or publishing about third parties requires explicit user authorization.

## Finalize

Finish all persistent work in exactly one validated result folder. Preserve target identities, source and license records, selected runtime and substitutions, code/configuration, commands, parameters/seeds, declared and measured resources, V0 and later evidence, comparisons, acceptance results, discrepancies, and rerun instructions. Store shared evidence once and isolate per-target results so one failure cannot corrupt another.
