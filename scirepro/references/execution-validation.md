# Execution and validation

Execution continues the verified Phase 0 target set and the analysis established in Phase 1. Apply the acceptance model declared for each target's workflow mode. In `scientific-reproduction`, a route succeeds scientifically only when its implementation covers the declared generation chain and its outputs satisfy predefined scientific criteria. In `image-derived-reconstruction`, success is limited to the declared visual, geometric, digitization, or editability criteria; it cannot establish a paper claim.

## Prepare the run

- When execution follows an approved Phase 1 route, validate it with `<skill-root>/scripts/plan_gate.py --report <report.json> --approval <approval.json> --target-manifest <targets/manifest.verified.json>`. This rechecks the admitted Phase 0 manifest and target bytes but is not a replay-prevention store.
- Preserve successful stdout as `gate-result.json`. The `scirepro.gate-result/v1` record binds the exact approval-file hash, report and target-manifest hashes, output policy, effects, and selected target/route/deliverable scope, including the validated non-secret parameter values for each selected target. Phase 2 tooling should consume this verified record instead of reparsing an untrusted approval as authority.
- Use a persistent approval/idempotency ledger only for gated, externally visible, costly, destructive, or otherwise non-idempotent effects. For a local create-only run, the new run ID, a non-existing output path, and the terminal run bundle are the idempotency boundary; do not build a global ledger solely for ceremony.
- Freeze the fields that affect the selected route: target identity and bytes, workflow mode, generation/reconstruction chain, validation targets, source identity, parameters, resource limits, and authorized effects. Bind report and approval hashes when they exist. Do not manufacture `not-required` records for concepts that cannot affect the route.
- Initialize the single staging directory defined by [run-bundle-contract.md](run-bundle-contract.md). Preserve original code and data read-only; place patches and generated files in their declared bundle paths.
- Capture environment versions, package/toolbox lists, hardware, random seeds, locale, and relevant numerical backend settings.

## Confirm chain coverage

- For `scientific-reproduction`, trace the selected source, configuration, and entry points to every generation-chain stage: input, selection, preprocessing or calibration, method or model, aggregation or statistics, and visual encoding.
- For `image-derived-reconstruction`, trace the target image through coordinate calibration, digitization or tracing, inferred geometry, appearance/layout reconstruction, and output encoding. Record that the chain begins with published pixels rather than original research inputs.
- Record each stage as reproduced, substituted, derived, assumed, uncovered, or not required. Preserve the evidence reference for that judgment.
- Confirm that actual input identity, parameter values, preprocessing, randomization, and output interfaces match the approved route.
- Treat every declared deliverable as a workspace write: an executable route with deliverables must declare `create-workspace-files`, and the approval gate must recheck that effect before execution.
- Stop and renew the report and approval when the target bytes, workflow mode, an uncovered or substituted stage, reproduction level, validation target, or supported claim changes materially.
- Freeze acceptance criteria before viewing final outputs where practical. In scientific mode, do not tune parameters solely to resemble the published figure. In image-derived mode, appearance may be the declared objective, but fitted pixels must never be reported as independent scientific evidence.

## Verify only relevant formulae, parameters, and assumptions

Treat the paper as primary evidence, not as an automatically correct specification. Audit only expressions and parameter choices that directly determine a selected target's input, preprocessing, method, plotted quantity, or acceptance criterion. Do not derive or review unrelated equations elsewhere in the paper.

For each relevant dependency:

1. Extract the expression, symbol definitions, indices, units, conditions, and parameter values from their local context.
2. Independently derive or justify the step far enough to test self-consistency. Apply only relevant checks: dimensions or units, matrix shapes, indices and summation ranges, normalization, signs, boundary/initial conditions, and limiting or simple known cases.
3. Cross-check the result against the implementation, appendix or cited primary source, and the target figure's axes, scale, order, trend, and feasible range.
4. Record the finding and implementation decision as evidence. A reported expression may be used as stated only after it survives the checks needed by this target.

When the paper omits a derivable step, preserve the derivation and use `use-derived`. When several readings remain defensible, freeze a transparent assumption or compare them as separate routes. When paper and author code materially differ, do not silently choose one: expose a paper-formula route and a code-implementation route, or block until the difference can be resolved. Never silently repair a confirmed error; identify the original expression, the correction, its basis, and the resulting claim boundary.

## Route-specific execution

### Direct recompute

Use the verified original or official input and implementation. Recompute the case and validate numerical or scientific outputs. Do not claim direct recomputation when the input identity is only probable.

### Mechanism reproduction

Implement or adapt the method from equations, code, and transparent assumptions. Validate the mechanism, trend, peaks, modes, or comparison that supports the paper claim. Clearly separate author-provided values from derived and assumed values.

### Alternative validation

Use a declared substitute dataset, implementation, or experiment. State the narrower transferable claim and why the substitute is relevant. Do not present it as the original case.

### Editable reconstruction

A pure workflow, architecture, mechanism diagram, or other semantic schematic must have left SciRepro through the terminal router before Phase 0. If one reaches Phase 2, stop without consuming the SciRepro approval or creating a SciRepro run bundle, then follow [diagram-handoff.md](diagram-handoff.md). Keep `editable-reconstruction` only as a legacy protocol value; do not create a new pure-schematic SciRepro route. Quantitative axes or data-driven geometry remain outside this legacy value.

### Original case blocked

Do not fabricate the missing original input. Deliver the verified blocker, checked sources, request path if lawful, and optional alternative route.

### Image-derived reconstruction

Use only when the target has no paper-grounded scientific context. Execute the approved digitization, tracing, layout, vectorization, or appearance-fitting route and quantify its declared geometric or visual error. Label all recovered values as image-derived. Do not claim recovery of the original data, method, experiment, uncertainty, or scientific conclusion. Follow [image-derived-reconstruction.md](image-derived-reconstruction.md).

## Figure-type routing

Pure semantic schematics should never reach this Phase 2 list; the terminal router owns that decision before Phase 0.

- Quantitative/statistical plots: code, data, protocol, numerical validation.
- Spectra/time series: sampling, preprocessing, scaling, windows, frequency axes, peaks, envelopes.
- Simulation figures: equations, discretization, boundary/initial conditions, parameters, solver, random seed.
- Machine-learning figures: exact split, preprocessing, model/config/checkpoint, seed, metric implementation.
- Microscopy/acquisition figures: raw images, instrument settings, calibration, segmentation/processing pipeline.
- Photographs: exact scene/specimen/device and acquisition conditions; do not treat visual recreation as experimental reproduction.
- Multi-panel figures: validate panels separately but report one aggregate figure result.

## Acceptance criteria

For `scientific-reproduction`, prioritize scientific fidelity:

1. variables, units, axes, scales, and sample counts;
2. qualitative phenomenon, topology, mode assignment, peaks, trends, or ordering;
3. quantitative values and uncertainty within a justified tolerance;
4. robustness across seeds or perturbations when randomness matters;
5. visual layout and styling only after the above.

Define tolerances before looking at final outputs where practical. Do not tune solely to mimic the published pixels.

For `image-derived-reconstruction`, validate coordinate calibration, visible geometry, topology, annotations, panel structure, appearance, and editability only as declared. Report uncertainty caused by raster resolution, line width, markers, occlusion, compression, and anti-aliasing.

## Compare and calibrate within a fixed budget

Preserve the first runnable output as V0 before any attempt to make it resemble the target. Compare V0 with the normalized target at two distinct levels. When the result will be shareable and the target pixels lack redistribution authority, make the comparison artifact metrics-only; never smuggle the restricted target into an overlay or screenshot.

- Scientific content: variables, axes, units, scale, trends, peaks, extrema, ordering, modes, magnitude and uncertainty.
- Presentation quality: palette, lines and markers, legend, typography, layout and export. Check explicitly for text-text, text-data and legend-data overlap; clipping; insufficient contrast; unreadable labels; and misleading axes.

Diagnose which data, formula, preprocessing, algorithm, parameter, randomization or plotting choice could explain each material difference. Keep scientific and presentation changes separate. A display change cannot cure or conceal a scientific discrepancy, and pixel similarity alone is not an acceptance criterion. In image-derived mode, visual similarity may be an approved objective, but it remains evidence about reconstruction accuracy rather than the paper's claim.

Use at most two rounds by default. V1 may change only scientifically justified inputs, data, formulae, preprocessing, implementation, parameters, randomness, numerical behavior, scientific axis scale, unit conversion, or range arising from the V0 diagnosis. Its typed change records must point to diagnosis, evidence, or a stated scientific basis; visual preference cannot masquerade as V1. V2 may change only expression and readability—axis labels and tick formatting, palette, line/marker style, legend, typography, layout, export, overlap, contrast, and readability—after the scientific interpretation is stable. A linear/log change, unit conversion, or scientific range truncation is V1, never V2. Record every performed change and its basis; omit an unneeded round rather than manufacturing its file. Stop as soon as the scientific criteria pass, remaining differences are non-critical, another change would improve only appearance, or two rounds reveal no new testable explanation. Continue to round 3 or later only for a new testable scientific hypothesis after explicit user approval bound to the target, exact prior-output hash, round, hypothesis, approval ID, idempotency key, timestamp, and bounded attempt count; never continue merely to chase resemblance.

Preserve V0, any performed version, the target-versus-output comparisons, the four-part difference summary and `scientificConclusion`, visual-QA status and issues, the typed adjustment log and the stop reason according to [run-bundle-contract.md](run-bundle-contract.md). The generated result webpage must label V0, V1, V2, approved later versions, and comparison roles explicitly; do not call every image merely “Output.”

## Interpret results and hand off research value

- In scientific mode, map each measured result to the target observation and paper claim. State whether the evidence supports, partially supports, does not support, or cannot test that claim.
- In image-derived mode, map results to the visible target and reconstruction criteria; restate that no paper claim was tested.
- Distinguish execution failure, implementation mismatch, input or protocol mismatch, stochastic or numerical variation, inconclusive evidence, and evidence that genuinely challenges a claim.
- Explain discrepancies using generation-chain coverage, recorded assumptions, parameter sensitivity, robustness checks, and ambiguities in the paper. Do not infer that a paper claim is false merely because one route failed.
- Identify reusable code, data transformations, parameterizations, validation procedures, and transferable method components, including the conditions under which they remain valid.
- Formulate follow-up questions, comparison experiments, or method extensions grounded in the observed results and unresolved uncertainties. Label them as hypotheses or research directions, not as established novelty or validated findings.

## Preserve negative reproduction and handle integrity signals cautiously

Failure to reproduce is not by itself evidence of fabrication. Before interpreting a contrary result, check the implementation trace, input identity, data version and subset, units, preprocessing, parameters, seeds, numerical precision, software behavior, plotting transform, and any defensible reading of an ambiguous expression. Use bounded sensitivity or robustness tests defined by scientific rationale; do not search indefinitely for values that make the output resemble the paper.

If a validated implementation still fails to produce the reported phenomenon, preserve the baseline, contrary outputs, diagnostics, tested alternatives, and acceptance results. Do not hide the result by selecting favorable runs, changing the method or data without disclosure, or substituting visual fitting. Assign exactly one claim status independently of operational success:

- `supported`: the declared key phenomenon passes its criteria;
- `partially-supported`: only a declared subset or condition passes;
- `unsupported`: the relevant route ran and was validated sufficiently to test the claim, but the claimed phenomenon did not hold;
- `inconclusive`: missing evidence, ambiguity, power, or unresolved implementation/input differences prevent a defensible decision;
- `not-tested`: no valid claim test was completed.

Use `unsupported` only when the test itself is valid; a crash, missing dataset, or unverified implementation is `inconclusive` or `not-tested`, not contrary scientific evidence.

Escalate to `potential research-integrity concern` only when an anomaly is independently reproducible and ordinary reproduction differences have been actively tested and cannot reasonably explain it. Relevant signals may include impossible physical or mathematical constraints, mutually inconsistent sample counts/statistics, unexplained duplicated noise or image regions, a verified original dataset that cannot map to the published figure, or hard-coded published results that bypass the declared method. Record the exact artifact, test, expected constraint, observed anomaly, repeatability, alternatives checked, and remaining uncertainty in a validation artifact such as `integrity-signals.json`.

Use neutral wording: “unexplained consistency anomaly” or “potential research-integrity concern.” Do not state that authors fabricated results, infer intent, or make a misconduct finding. Contacting authors or journals, filing a report, or publishing an allegation is a separate external action that requires explicit user authorization.

## Patches and deviations

- Keep compatibility patches as small overlays with diffs.
- Ask before changing algorithm semantics, data, preprocessing, or metric definitions.
- Record warnings, failed attempts, and discrepancies.
- If the plan changes materially, stop and regenerate the report and approval.

## Final run bundle

Finish every attempted route as exactly one directory governed by [run-bundle-contract.md](run-bundle-contract.md). Use `<skill-root>/scripts/finalize_run_bundle.py`; never write `manifest.json` by hand.

The bundle must preserve report/approval bindings that exist, target identities and workflow modes, sources and licenses, environment and hardware, commands and parameters, inputs and assumptions, generation-chain coverage, outputs, validation, resources, patches, deviations, discrepancies, reusable artifacts, and evidence limits. Put cross-target material in `shared/` and target-only material in `targets/<target-id>/`. For a `complete` or `partial` run, pass the Phase 1 web-report directory to `finalize --result-report`; the finalizer binds it to the approved report and generates the terminal result page from the actual result and validation records. Do not require a result page for a run that never produced a complete or partial result.

Operational, validation, and claim states are independent. Finalize blocked, failed, and cancelled attempts too; a terminal diagnostic bundle is preferable to scattered logs or an absent result. Only the validator may publish the staging directory to `scirepro-run-<run-id>/`.
