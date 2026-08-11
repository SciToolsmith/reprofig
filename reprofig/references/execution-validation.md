# Execution and validation

## Prepare the run

- Validate the approval with `scripts/plan_gate.py`. This is a stateless structural and integrity check, not a replay-prevention store.
- Before the first side effect, atomically claim `(reportSha256, approvalId, idempotencyKey)` in a persistent run ledger. Reject a previously claimed approval ID or idempotency key, including after process restart. Record the claim and terminal run status; never infer idempotency from a successful `plan_gate.py` exit alone.
- Freeze report hash, figure image hash, source artifact hash, selected route, parameters, resource limits, and authorized effects.
- Create a versioned run directory. Preserve original code and data read-only; place patches and generated files in separate paths.
- Capture environment versions, package/toolbox lists, hardware, random seeds, locale, and relevant numerical backend settings.

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

## Patches and deviations

- Keep compatibility patches as small overlays with diffs.
- Ask before changing algorithm semantics, data, preprocessing, or metric definitions.
- Record warnings, failed attempts, and discrepancies.
- If the plan changes materially, stop and regenerate the report and approval.

## Result manifest

Record:

- report and approval IDs/hashes;
- source URLs, versions, licenses, and hashes;
- environment and hardware;
- exact commands and parameters;
- inputs and derivations/assumptions;
- outputs and validation metrics;
- runtime, memory, disk, network, and cost;
- patches and deviations;
- claims supported, partially supported, unsupported, or not tested.
