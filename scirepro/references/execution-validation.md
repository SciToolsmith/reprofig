# Execution and validation

Execution continues the verified Phase 0 target set and the analysis established in Phase 1. Apply the acceptance model declared for each target's workflow mode. In `scientific-reproduction`, a route succeeds scientifically only when its implementation covers the declared generation chain and its outputs satisfy predefined scientific criteria. In `image-derived-reconstruction`, success is limited to the declared visual, geometric, digitization, or editability criteria; it cannot establish a paper claim.

## Prepare the run

- Validate the approval with `scripts/plan_gate.py --report <report.json> --approval <approval.json> --target-manifest <targets/manifest.json>`. This rechecks the current Phase 0 manifest and target bytes, but remains a stateless structural and integrity check rather than a replay-prevention store.
- Before the first side effect, atomically claim `(reportSha256, approvalId, idempotencyKey)` in a persistent run ledger. Reject a previously claimed approval ID or idempotency key, including after process restart. Record the claim and terminal run status; never infer idempotency from a successful `plan_gate.py` exit alone.
- Freeze report hash, target-manifest hash, verified target ID and normalized target hash, workflow mode, paper claim when applicable, generation or reconstruction chain, validation targets, source artifact hash, selected route, parameters, resource limits, and authorized effects.
- Create a versioned run directory. Preserve original code and data read-only; place patches and generated files in separate paths.
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

## Result manifest

Record:

- report, target-manifest, and approval IDs/hashes;
- target IDs, normalized target hashes, workflow modes, and target observations;
- scientific question, paper claim, and evidence role only when paper-grounded;
- source URLs, versions, licenses, and hashes;
- environment and hardware;
- exact commands and parameters;
- inputs and derivations/assumptions;
- generation-chain coverage and substituted, assumed, or uncovered stages;
- outputs and validation metrics;
- runtime, memory, disk, network, and cost;
- patches and deviations;
- claims supported, partially supported, unsupported, or not tested;
- discrepancy interpretation, sensitivity or robustness findings, and evidence limits;
- reusable artifacts and grounded follow-up research questions.
