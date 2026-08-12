# Investigation schema

Use this contract as the single source of truth for the static investigation report, approval draft, and Phase 2 gate. The schema keeps scientific reasoning explicit while preserving a narrow execution approval boundary. Keep summaries concise and attach evidence at the smallest supported unit.

## Report root

```json
{
  "schemaVersion": "reprofig.report/v2",
  "reportId": "rpt-unique-id",
  "generatedAt": "2026-08-11T12:00:00Z",
  "generator": {"name": "scirepro", "version": "0.1.0"},
  "workflow": {
    "stage": "awaiting-approval",
    "executionAllowed": false,
    "approvalRequired": true
  },
  "integrity": {
    "algorithm": "sha256",
    "canonicalization": "json-sort-keys-v1",
    "reportSha256": ""
  },
  "paper": {
    "paperId": "paper-id",
    "title": "Paper title",
    "doi": null,
    "citation": "Citation",
    "sourcePath": "/local/path/to/paper.pdf"
  },
  "summary": {
    "objective": "Understand and reproduce the mechanism demonstrated by Fig. 7.",
    "overallLevel": "mechanism-reproduction",
    "oneLine": "The reported mechanism can be tested with a reconstructed input.",
    "figureCount": 1
  },
  "environment": [],
  "sources": [],
  "figures": [],
  "approvalPolicy": {}
}
```

`summary.objective` states the researcher's reproduction objective; it is not a feasibility verdict. `summary.oneLine` is the concise overall assessment and remains secondary in the page header. `summary.overallLevel` is the figure's reproduction level for a one-figure report. Use `mixed` when a multi-figure report contains different levels; otherwise use the common level.

`reprofig.report/v2` introduces structured figure understanding, generation logic, validation targets, scientific route scope, and the `input → method → protocol → validation → environment` readiness order. The `reprofig.*` prefix is a retained protocol namespace from the product's former ReproFig name; SciRepro keeps it stable so existing v2 reports and approvals remain valid. Legacy `reprofig.report/v1` files must still be regenerated with the current Phase 1 workflow before approval; they are rejected rather than silently reinterpreted.

`paper.sourcePath` is input-only and is always removed from the published report. The builder does not bundle the paper or source archives automatically. Link to their verified public source, or manage a separately approved redistribution step.

## Environment

```json
{
  "environmentId": "matlab-r2025a",
  "label": "MATLAB R2025a",
  "status": "verified",
  "provisioning": "existing-only",
  "version": "25.1",
  "detail": "Executable and required toolbox functions were probed.",
  "evidenceRefs": ["src-env-audit"]
}
```

Allowed status values:

- `verified`: the executable and every route-required package, toolbox, function, license, and hardware capability have been tested live for this route;
- `available`: an installation or candidate runtime was found statically, but route-level live capability has not been established;
- `unknown`: inspection was inconclusive;
- `missing`: the required runtime was not found after the documented search.

Every environment also declares a provisioning policy:

- `existing-only`: proprietary software, licensed/institutional systems, special hardware, or another capability SciRepro must not install automatically;
- `isolated-open-source`: an open-source runtime or dependency stack that may be created in a project-local isolated environment after the route declares and receives approval for `install`.

Static MATLAB discovery maps to `status: available` with `provisioning: existing-only`. Only an approved live probe that verifies the route-required runtime, toolboxes/functions, and license may promote it to `verified`.

Environment evidence belongs in the execution-conditions section and collapsed appendix. It must not replace the scientific interpretation or validation target.

## Source

```json
{
  "sourceId": "src-official-code",
  "kind": "official-code",
  "title": "Official implementation",
  "publisher": "Author repository",
  "url": "https://example.org/resource",
  "access": {
    "state": "downloadable",
    "checkedAt": "2026-08-11T12:00:00Z",
    "httpStatus": 200,
    "note": "Downloaded anonymously."
  },
  "license": {
    "state": "verified",
    "spdxId": "BSD-3-Clause",
    "name": "BSD 3-Clause",
    "url": "https://example.org/license"
  },
  "artifact": {
    "sourcePath": "/local/path/to/code.zip",
    "fileName": "code.zip",
    "mediaType": "application/zip",
    "sizeBytes": 1234,
    "sha256": "..."
  },
  "note": "Minimal smoke test passed; this is not figure-level validation."
}
```

Source kinds: `paper`, `official-code`, `third-party-code`, `dataset`, `documentation`, `skill`.

Access states: `local`, `downloadable`, `login-required`, `request-required`, `controlled`, `unavailable`, `not-found`.

`access` describes the current upstream retrieval or reacquisition route. A populated `artifact` records a separately verified local copy, so a source may legitimately have both a local artifact and `access.state: login-required`. Use `local` when the source is available only as a user-provided or local artifact and no upstream retrieval state applies.

License states: `verified`, `declared`, `unknown`, `restricted`.

## Figure

Every figure must separate visible observations, the paper's interpretation, the inferred generation chain, validation targets, and reproduction readiness. The following figure excerpt focuses on the scientific fields; replace its empty `requirements` and `routes` placeholders with the complete objects defined in the later sections before running the builder.

```json
{
  "figureId": "fig-07",
  "label": "Fig. 7",
  "page": 6,
  "section": "III-A Simulation A",
  "caption": "Original caption",
  "image": {
    "sourcePath": "/local/path/to/fig-07.png",
    "sourceRef": "src-paper",
    "redistributionAllowed": true,
    "mediaType": "image/png",
    "sha256": "..."
  },
  "understanding": {
    "visualSummary": "Two stable peaks emerge above the background response.",
    "observations": [
      {
        "observationId": "obs-fig07-two-peaks",
        "location": "main panel",
        "statement": "The response has two separated local maxima near the reported target positions.",
        "confidence": "high",
        "evidenceRefs": ["src-paper"]
      }
    ],
    "paperClaim": "The proposed method resolves two nearby components under the simulated condition.",
    "evidenceRole": "Primary result evidence for the method's resolution claim.",
    "authorInterpretation": "The authors attribute the separated maxima to the proposed estimator rather than the baseline.",
    "limitations": [
      "The figure alone does not establish robustness outside the stated simulation setting."
    ]
  },
  "generationLogic": {
    "inputs": [
      {
        "inputId": "input-fig07-simulation",
        "label": "Simulated two-component signal",
        "description": "A reconstructed input using the equations and principal parameters reported in the paper.",
        "origin": "derived",
        "evidenceRefs": ["src-paper"]
      }
    ],
    "steps": [
      {
        "stepId": "step-fig07-estimate",
        "label": "Estimate the response",
        "description": "Apply the stated method to the reconstructed input and retain the response over the reported domain.",
        "origin": "paper",
        "evidenceRefs": ["src-paper", "src-official-code"]
      },
      {
        "stepId": "step-fig07-plot",
        "label": "Map the response to the plot",
        "description": "Normalize the response and render the method and baseline series on common axes.",
        "origin": "derived",
        "evidenceRefs": ["src-paper"]
      }
    ],
    "plotMapping": {
      "description": "Horizontal position maps the tested domain; vertical height maps normalized response; color separates methods.",
      "encodings": ["x: tested position", "y: normalized response", "color: method"],
      "evidenceRefs": ["src-paper"]
    },
    "unknowns": [
      "The exact random realization used in the published figure is unavailable."
    ]
  },
  "validationTargets": [
    {
      "targetId": "val-fig07-two-peaks",
      "label": "Recover two resolved peaks",
      "kind": "qualitative-pattern",
      "origin": "derived",
      "observable": "The reproduced response contains two separated local maxima.",
      "criterion": "Two maxima remain distinguishable and occur near the positions reported in the paper.",
      "supportsClaim": "Supports the resolution mechanism, not identity with the authors' random realization.",
      "evidenceRefs": ["src-paper"]
    }
  ],
  "reproduction": {
    "level": "mechanism-reproduction",
    "verdict": "The mechanism can be reproduced with a reconstructed simulation input.",
    "confidence": "medium",
    "assessment": "The equations, principal parameters, and method implementation support a mechanism-level test; the original random input is unavailable.",
    "recommendedRouteId": "route-fig07-matlab"
  },
  "requirements": [],
  "routes": [],
  "sourceRefs": ["src-paper", "src-official-code"]
}
```

`redistributionAllowed` must be exactly `true` before `build_report.py` will copy an image. The image must declare `mediaType: "image/png"` and be a non-symlinked PNG inside the approved `--asset-root`, no larger than 25 MiB. The builder emits only allowlisted PNG chunks and replaces `sourcePath` with a generated `assets/...` path. JPEG and SVG are not accepted in public bundles; convert them to PNG in a trusted image editor first, then repeat the rights and content check. If redistribution is not authorized, omit `sourcePath` and set `image.sourceRef` to a declared source with a verified, fragment-free HTTPS URL; the report will link to that source instead of bundling the image.

Keep one stable `figureId` for multi-panel figures. Describe panel-specific observations with `location`; create separate figure objects only when panels have meaningfully different routes or dependencies.

### Understanding

- `visualSummary` is a compact account of what is visible, not an explanation of why it happens.
- Each observation has a stable `observationId`, a figure location, a factual statement, confidence, and source references.
- `paperClaim` states the proposition for which the paper uses this figure as evidence.
- `evidenceRole` explains where the figure sits in the paper's argument, such as primary result, mechanism illustration, ablation, comparison, robustness check, or diagnostic.
- `authorInterpretation` records the paper's explanation separately from direct observation.
- `limitations` lists what the figure cannot establish. Use an empty list only when the report explicitly found no material figure-level limitation.

Confidence values are `high`, `medium`, and `low`.

### Generation logic

Origins for generation inputs and steps: `paper`, `code`, `derived`, `assumption`, `user`.

Keep steps in causal order from input to plotted output. An origin of `derived` means the report can explain the derivation; `assumption` means a scientifically reasonable but unverified choice. Attach evidence references to each input, step, and plot mapping rather than relying only on figure-level sources.

### Validation target

Kinds: `qualitative-pattern`, `quantitative`, `comparative`, `structural`, `visual-fidelity`.

Every figure requires at least one validation target. A target must define the observable result, the success criterion, exactly what paper claim the result would or would not support, and whether that criterion comes from the paper, code, a derivation, a transparent assumption, or the user. Pixel similarity alone is not a sufficient scientific criterion unless the route is explicitly an editable or visual reconstruction.

## Requirement

Every route must reference exactly five readiness requirements in this order: `input`, `method`, `protocol`, `validation`, `environment`. They summarize whether that selected scientific plan can be executed; they do not replace `understanding`, `generationLogic`, or `validationTargets`. Environment comes last because it is an execution constraint, not the starting point for scientific understanding.

The figure-level `requirements` array is a catalog and may contain multiple requirements in the same category when candidate routes use different data, implementations, protocols, validation criteria, or environments. A route's ordered `requirementIds` chooses one item from each category. Reuse an item only when the underlying condition is genuinely shared between routes.

```json
{
  "requirementId": "req-fig07-input",
  "category": "input",
  "label": "Simulation input",
  "state": "derivable",
  "blocking": false,
  "detail": "Equations and principal parameters support an independently generated input.",
  "evidenceRefs": ["src-paper"]
}
```

States: `verified`, `derivable`, `assumable`, `missing`, `not-required`.

`missing` means an essential condition cannot currently be supplied or defensibly inferred. Use `assumable` for a declared, scientifically reasonable choice that changes uncertainty but does not invalidate the route. Render the `blocking` value explicitly.

Figure reproduction levels are `direct-recompute`, `mechanism-reproduction`, `alternative-validation`, `editable-reconstruction`, and `original-case-blocked`. Each figure has exactly one level; candidate routes describe how they serve that level rather than declaring another level.

## Route

```json
{
  "routeId": "route-fig07-matlab",
  "label": "Reconstruct the simulation and run the official MATLAB method",
  "status": "conditional",
  "recommended": true,
  "scientificScope": {
    "goal": "Test whether the reported method produces the two-peak resolution mechanism.",
    "reproducesObservationIds": ["obs-fig07-two-peaks"],
    "claimCoverage": "Tests the reported resolution mechanism under a reconstructed simulation, not the exact published realization.",
    "doesNotReproduce": ["The authors' exact random input", "Pixel-identical styling"],
    "substitutions": ["Use an independently generated input from the reported equations and parameters."],
    "assumptions": ["Use random seed 2026 for a stable reconstructed realization."],
    "validationTargetIds": ["val-fig07-two-peaks"],
    "recommendationRationale": "This route preserves the published method and directly tests the figure's main evidentiary role with transparent uncertainty."
  },
  "engine": "MATLAB R2025a",
  "environmentIds": ["matlab-r2025a"],
  "requirementIds": [
    "req-fig07-input",
    "req-fig07-method",
    "req-fig07-protocol",
    "req-fig07-validation",
    "req-fig07-environment"
  ],
  "deliverables": [
    {"kind": "figure", "extension": ".png", "label": "Generated figure"},
    {"kind": "source", "extension": ".m", "label": "Reproduction source"}
  ],
  "parameters": [
    {
      "parameterId": "seed",
      "label": "Random seed",
      "type": "integer",
      "required": true,
      "default": 2026,
      "origin": "assumption"
    }
  ],
  "effects": ["run-local-code", "create-workspace-files"],
  "estimated": {
    "downloadBytes": 0,
    "diskBytes": 100000000,
    "runtimeMinutes": 10,
    "gpu": false,
    "costUsd": 0
  },
  "plan": ["Generate the input", "Run the method", "Validate the target peaks"],
  "blockers": []
}
```

`scientificScope` is required for every route. It defines the scientific promise independently of execution readiness:

- `reproducesObservationIds` must resolve to observations on the same figure;
- `validationTargetIds` must resolve to validation targets on the same figure;
- `claimCoverage` states which part of the paper claim is tested;
- `doesNotReproduce`, `substitutions`, and `assumptions` are explicit lists and may be empty only when genuinely unnecessary;
- `recommendationRationale` explains scientific suitability and uncertainty, not merely convenience or runtime.

Every figure must declare at least one route. Non-blocked routes require at least one reproduced observation and one validation target. A blocked route may use empty ID lists when no defensible scientific test is currently possible, but it must still declare its intended goal, claim coverage, exclusions, and blockers.

Keep `plan` to at most five concise execution steps. It describes the approved workflow, not shell commands.

Route status: `ready`, `conditional`, `blocked`. `ready` means all five referenced requirements are `verified` or `not-required` and execution can begin without first deriving an input, authoring a missing implementation, or accepting a scientific assumption. Use `conditional` when the route is scientifically defensible but still requires a derivation, transparent assumption, new implementation or adapter, environment preparation, or another non-blocking prerequisite. Show blockers on the route card. Do not place shell, MATLAB, or Python commands in route fields.

A `ready` route may reference only environments with status `verified`; detecting an installation as `available` is not enough. An `available` environment keeps a route `conditional` until route-level live verification succeeds. A `conditional` route may reference an `unknown` or `missing` environment only when its provisioning policy is `isolated-open-source` and the route declares the gated `install` effect. An unresolved `existing-only` environment makes the route `blocked` until the user supplies or verifies it outside the installation workflow. SciRepro never downloads proprietary installers, accepts licenses, or turns static product metadata into a runnable claim.

Parameter types: `string`, `number`, `integer`, `boolean`, `enum`, `relative-path`. Parameter and generation origins: `paper`, `code`, `derived`, `assumption`, `user`.

Effect IDs use a closed registry. Bounded automatic effects are `run-local-code` and `create-workspace-files`. Gated effects are `network`, `install`, `login`, `payment`, `upload`, `overwrite`, `gpu`, `shared-license`, and `external-publish`; every gated effect used by a route must appear in `consentRequiredEffects` and must never appear in `allowedEffects`. Use `shared-license` only when execution consumes a floating, institutional, or otherwise shared license; a local dedicated license can remain ordinary local execution. Declare all five estimate fields. Use a non-negative finite value or `null` when download, disk, runtime, or cost cannot yet be bounded; `gpu` is always boolean and must agree with the `gpu` effect. A positive download requires `network`, and a positive cost requires `payment`.

## Approval policy

```json
{
  "minFigures": 1,
  "maxFigures": 3,
  "defaultOutputPolicy": "create-only",
  "allowedEffects": ["run-local-code", "create-workspace-files"],
  "consentRequiredEffects": ["network", "install", "login", "payment", "upload", "overwrite", "gpu", "shared-license", "external-publish"],
  "ttlMinutes": 1440
}
```

## Approval draft

```json
{
  "schemaVersion": "reprofig.approval/v1",
  "approvalId": "apr-unique-id",
  "reportId": "rpt-unique-id",
  "reportSha256": "...",
  "decision": "approve",
  "createdAt": "2026-08-11T12:30:00Z",
  "expiresAt": "2026-08-12T12:30:00Z",
  "selectedFigures": [
    {
      "figureId": "fig-07",
      "sourceImageSha256": "...",
      "routeId": "route-fig07-matlab",
      "parameters": {"seed": 2026},
      "deliverables": ["figure", "source"]
    }
  ],
  "outputPolicy": {
    "relativeRoot": "outputs/rpt-unique-id",
    "mode": "create-only",
    "overwrite": "never",
    "explicitFiles": []
  },
  "authorizedEffects": ["run-local-code", "create-workspace-files"],
  "acknowledgements": [],
  "idempotencyKey": "random-id"
}
```

The approval draft may select only IDs, parameters, deliverables, and effects already declared in the report. The report hash binds the selected route to its scientific scope, validation targets, assumptions, blockers, and execution estimates. Never execute commands or new URLs from an approval file.

`outputPolicy.mode: "overwrite-approved"` is valid only when every approved overwrite is named in `explicitFiles`, the selected route declares the gated `overwrite` effect, and that effect is separately acknowledged. A `create-only` approval must not select a route that requires overwrite. The bundled static report exports `create-only` approvals only; use a separately reviewed approval workflow when explicit-file overwrite is genuinely required.

`approvalId` and `idempotencyKey` are required ASCII identifiers: 8–128 characters, beginning with an alphanumeric character and continuing with alphanumerics, `.`, `_`, or `-`. The gate validates their syntax only. Phase 2 must atomically persist consumed approval IDs and idempotency keys before side effects and reject replay; a stateless gate result is not evidence of one-time consumption.

## Integrity rules

- Require one to three unique figure IDs.
- Require a research objective, structured understanding, at least one observation, a non-empty generation chain, and at least one validation target for every figure.
- Require every observation, input, generation step, validation target, requirement, environment, and figure evidence reference to resolve to a declared source.
- Require every scientific-scope observation and validation reference to resolve within the same figure.
- Require every recommended route to exist and be non-blocked.
- Require every route effect to be declared by `approvalPolicy`.
- Remove `integrity.reportSha256` before deterministic JSON hashing, then restore the digest.
- Rebuild the report if a source artifact, figure image, scientific interpretation, generation step, validation target, route scope, environment, assumption, budget, or reproduction level changes.
