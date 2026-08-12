# Execution and validation

Execution continues the paper-evidence analysis established in Phase 1. A route succeeds scientifically only when its implementation covers the declared generation chain and its outputs satisfy predefined validation criteria; a successful command, plausible image, or close visual match is not sufficient.

## Prepare the run

- Validate the approval with `scripts/plan_gate.py`. This is a stateless structural and integrity check, not a replay-prevention store.
- Before the first side effect, atomically claim `(reportSha256, approvalId, idempotencyKey)` in a persistent run ledger. Reject a previously claimed approval ID or idempotency key, including after process restart. Record the claim and terminal run status; never infer idempotency from a successful `plan_gate.py` exit alone.
- Freeze report hash, figure image hash, target paper claim, generation chain, validation targets, source artifact hash, selected route, parameters, resource limits, and authorized effects.
- Create a versioned run directory. Preserve original code and data read-only; place patches and generated files in separate paths.
- Capture environment versions, package/toolbox lists, hardware, random seeds, locale, and relevant numerical backend settings.

## Confirm generation-chain coverage

- Trace the selected source, configuration, and entry points to every generation-chain stage: input, selection, preprocessing or calibration, method or model, aggregation or statistics, and visual encoding.
- Record each stage as reproduced, substituted, derived, assumed, uncovered, or not required. Preserve the evidence reference for that judgment.
- Confirm that actual input identity, parameter values, preprocessing, randomization, and output interfaces match the approved route.
- Stop and renew the report and approval when an uncovered or substituted stage materially changes the reproduction level, validation target, or claim the route can support.
- Freeze acceptance criteria before viewing final outputs where practical. Do not tune parameters solely to resemble the published figure.

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

## Figure-type routing

- Quantitative/statistical plots: code, data, protocol, numerical validation.
- Spectra/time series: sampling, preprocessing, scaling, windows, frequency axes, peaks, envelopes.
- Simulation figures: equations, discretization, boundary/initial conditions, parameters, solver, random seed.
- Machine-learning figures: exact split, preprocessing, model/config/checkpoint, seed, metric implementation.
- Microscopy/acquisition figures: raw images, instrument settings, calibration, segmentation/processing pipeline.
- Photographs: exact scene/specimen/device and acquisition conditions; do not treat visual recreation as experimental reproduction.
- Multi-panel figures: validate panels separately but report one aggregate figure result.

## Acceptance criteria

Prioritize scientific fidelity:

1. variables, units, axes, scales, and sample counts;
2. qualitative phenomenon, topology, mode assignment, peaks, trends, or ordering;
3. quantitative values and uncertainty within a justified tolerance;
4. robustness across seeds or perturbations when randomness matters;
5. visual layout and styling only after the above.

Define tolerances before looking at final outputs where practical. Do not tune solely to mimic the published pixels.

## Interpret results and hand off research value

- Map each measured result to the target observation and paper claim. State whether the evidence supports, partially supports, does not support, or cannot test that claim.
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

- report and approval IDs/hashes;
- scientific question, paper claim, figure evidence role, and target observations;
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
