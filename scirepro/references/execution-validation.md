# Execution and validation

Execution continues the verified Phase 0 target set and the analysis established in Phase 1. Apply the acceptance model declared for each target's workflow mode. In `scientific-reproduction`, a route succeeds scientifically only when its implementation covers the declared generation chain and its outputs satisfy predefined scientific criteria. In `image-derived-reconstruction`, success is limited to the declared visual, geometric, digitization, or editability criteria; it cannot establish a paper claim.

## Prepare the run

- When execution follows an approved Phase 1 route, validate it with `<skill-root>/scripts/plan_gate.py --report <report.json> --approval <approval.json> --target-manifest <targets/manifest.verified.json>`. This rechecks the admitted Phase 0 manifest and target bytes but is not a replay-prevention store.
- Preserve successful stdout as `gate-result.json`. The `scirepro.gate-result/v1` record binds the exact approval-file hash, report and target-manifest hashes, output policy, effects, and selected target/route/deliverable scope; Phase 2 tooling should consume this verified record instead of reparsing an untrusted approval as authority.
- Use a persistent approval/idempotency ledger only for gated, externally visible, costly, destructive, or otherwise non-idempotent effects. For a local create-only run, the new run ID, a non-existing output path, and the terminal run bundle are the idempotency boundary; do not build a global ledger solely for ceremony.
- Freeze the fields that affect the selected route: target identity and bytes, workflow mode, generation/reconstruction chain, validation targets, source identity, parameters, resource limits, and authorized effects. Bind report and approval hashes when they exist. Do not manufacture `not-required` records for concepts that cannot affect the route.
- Initialize the single staging directory defined by [run-bundle-contract.md](run-bundle-contract.md). Preserve original code and data read-only; place patches and generated files in their declared bundle paths.
- Capture environment versions, package/toolbox lists, hardware, random seeds, locale, and relevant numerical backend settings.

## Confirm chain coverage

- For `scientific-reproduction`, trace the selected source, configuration, and entry points to every generation-chain stage: input, selection, preprocessing or calibration, method or model, aggregation or statistics, and visual encoding.
- For `image-derived-reconstruction`, trace the target image through coordinate calibration, digitization or tracing, inferred geometry, appearance/layout reconstruction, and output encoding. Record that the chain begins with published pixels rather than original research inputs.
- Record each stage as reproduced, substituted, derived, assumed, uncovered, or not required. Preserve the evidence reference for that judgment.
- Confirm that actual input identity, parameter values, preprocessing, randomization, and output interfaces match the approved route.
- Stop and renew the report and approval when the target bytes, workflow mode, an uncovered or substituted stage, reproduction level, validation target, or supported claim changes materially.
- Freeze acceptance criteria before viewing final outputs where practical. In scientific mode, do not tune parameters solely to resemble the published figure. In image-derived mode, appearance may be the declared objective, but fitted pixels must never be reported as independent scientific evidence.

## Route-specific execution

### Direct recompute

Use the verified original or official input and implementation. Recompute the case and validate numerical or scientific outputs. Do not claim direct recomputation when the input identity is only probable.

### Mechanism reproduction

Implement or adapt the method from equations, code, and transparent assumptions. Validate the mechanism, trend, peaks, modes, or comparison that supports the paper claim. Clearly separate author-provided values from derived and assumed values.

### Alternative validation

Use a declared substitute dataset, implementation, or experiment. State the narrower transferable claim and why the substitute is relevant. Do not present it as the original case.

### Editable reconstruction

Use only for workflows, architectures, mechanism diagrams, and other semantic schematics. Prefer `sci-diagram-pptx` when installed. Validate node text, grouping, connections, directions, formulas, and editability. Do not use this route for quantitative axes or data-driven geometry.

### Original case blocked

Do not fabricate the missing original input. Deliver the verified blocker, checked sources, request path if lawful, and optional alternative route.

### Image-derived reconstruction

Use only when the target has no paper-grounded scientific context. Execute the approved digitization, tracing, layout, vectorization, or appearance-fitting route and quantify its declared geometric or visual error. Label all recovered values as image-derived. Do not claim recovery of the original data, method, experiment, uncertainty, or scientific conclusion. Follow [image-derived-reconstruction.md](image-derived-reconstruction.md).

## Figure-type routing

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

## Interpret results and hand off research value

- In scientific mode, map each measured result to the target observation and paper claim. State whether the evidence supports, partially supports, does not support, or cannot test that claim.
- In image-derived mode, map results to the visible target and reconstruction criteria; restate that no paper claim was tested.
- Distinguish execution failure, implementation mismatch, input or protocol mismatch, stochastic or numerical variation, inconclusive evidence, and evidence that genuinely challenges a claim.
- Explain discrepancies using generation-chain coverage, recorded assumptions, parameter sensitivity, robustness checks, and ambiguities in the paper. Do not infer that a paper claim is false merely because one route failed.
- Identify reusable code, data transformations, parameterizations, validation procedures, and transferable method components, including the conditions under which they remain valid.
- Formulate follow-up questions, comparison experiments, or method extensions grounded in the observed results and unresolved uncertainties. Label them as hypotheses or research directions, not as established novelty or validated findings.

## Patches and deviations

- Keep compatibility patches as small overlays with diffs.
- Ask before changing algorithm semantics, data, preprocessing, or metric definitions.
- Record warnings, failed attempts, and discrepancies.
- If the plan changes materially, stop and regenerate the report and approval.

## Final run bundle

Finish every attempted route as exactly one directory governed by [run-bundle-contract.md](run-bundle-contract.md). Use `<skill-root>/scripts/finalize_run_bundle.py`; never write `manifest.json` by hand.

The bundle must preserve report/approval bindings that exist, target identities and workflow modes, sources and licenses, environment and hardware, commands and parameters, inputs and assumptions, generation-chain coverage, outputs, validation, resources, patches, deviations, discrepancies, reusable artifacts, and evidence limits. Put cross-target material in `shared/` and target-only material in `targets/<target-id>/`. For a `complete` or `partial` run, pass the Phase 1 web-report directory to `finalize --result-report`; the finalizer binds it to the approved report and generates the terminal result page from the actual result and validation records. Do not require a result page for a run that never produced a complete or partial result.

Operational, validation, and claim states are independent. Finalize blocked, failed, and cancelled attempts too; a terminal diagnostic bundle is preferable to scattered logs or an absent result. Only the validator may publish the staging directory to `scirepro-run-<run-id>/`.
