# Investigation schema

Use this contract as the single source of truth for the static investigation report, approval draft, and Phase 2 gate. The schema keeps scientific reasoning explicit while preserving a narrow execution approval boundary. Keep summaries concise and attach evidence at the smallest supported unit.

## Contents

- [Report root](#report-root)
- [Environment](#environment)
- [Source](#source)
- [Figure](#figure)
- [Requirement](#requirement)
- [Route](#route)
- [Approval policy](#approval-policy)
- [Approval draft](#approval-draft)
- [Integrity rules](#integrity-rules)

## Report root

```json
{
  "schemaVersion": "reprofig.report/v3",
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
  "audience": "local",
  "targetSet": {
    "targetSetId": "targets-paper-figures",
    "manifestSha256": "...",
    "targetCount": 1,
    "acquisitionModes": ["paper-with-figure-references"]
  },
  "paper": {
    "paperId": "paper-id",
    "title": "Paper title",
    "doi": null,
    "citation": "Citation",
    "sourcePath": "/local/path/to/paper.pdf",
    "sourceSha256": "...",
    "pageCount": 12
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

`summary.objective` states the researcher's reproduction objective; it is not a feasibility verdict. `summary.oneLine` is the concise overall assessment and remains secondary in the page header. `summary.overallLevel` is the target's reproduction level for a one-target report. Use `mixed` when a multi-target report contains different levels; otherwise use the common level. `summary.figureCount` and `targetSet.targetCount` must equal the number of figure objects.

`reprofig.report/v3` adds a mandatory Phase 0 target set, explicit acquisition and workflow modes, local/public report audiences, and target-bound approval. The `reprofig.*` prefix is retained as a stable protocol namespace from the product's former ReproFig name; it is not the current product name. Reports using `reprofig.report/v1` or `reprofig.report/v2` must be regenerated. The builder and Phase 2 gate reject them rather than silently reinterpreting them under the v3 contract.

`audience` is exactly `local` or `public`:

- `local` is the normal investigation report. Every Phase 0 target must be visibly embedded, including a paper figure whose redistribution rights are unknown, because the bundle remains local to the researcher.
- `public` is a deliberately shareable derivative. A target may be embedded only when `redistributionAllowed` is exactly `true`; otherwise its bytes and private path are omitted and the report records `bundleState: "omitted-rights"`.

`targetSet` binds the report to one Phase 0 manifest. It contains one or more targets and is limited only by the defensive technical maximum of 256—not by a product-level one-to-three rule. `manifestSha256` is the canonical manifest digest. `acquisitionModes` is the unique set of modes present across its targets:

- `paper-with-images`: a paper plus one or more user-supplied target images;
- `paper-with-figure-references`: a paper plus one or more requested figure numbers or ranges, materialized from the paper by SciRepro;
- `images-only`: one or more target images without a paper.

Each target also declares one workflow mode. `scientific-reproduction` uses the paper and other evidence to reconstruct and test a scientific generation process. `image-derived-reconstruction` works from visible image evidence only; it may trace geometry, digitize visible values, or fit appearance, but it must not claim to recover the original data, method, or scientific result.

`paper` is nullable only when every target uses `images-only` acquisition and `image-derived-reconstruction`. Any target using `scientific-reproduction` requires a complete paper object. `paper.sourcePath` is input-only and is always removed from the built report. During target binding, the builder overwrites `paper.sourceSha256` and `paper.pageCount` from the verified Phase 0 manifest; the execution gate rechecks both values against that manifest. The builder does not bundle the paper or source archives automatically. Link to their verified public source, or manage a separately approved redistribution step.

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

Every `verified` environment must cite at least one `environment-audit` source with a local hashed artifact in `evidenceRefs`. The artifact should contain the redacted route-specific probe result, not secrets or unrestricted logs. A paper, README, static product page, or unarchived discovery claim cannot establish execution; keep those cases `available` or `unknown`.

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

Source kinds: `paper`, `official-code`, `third-party-code`, `dataset`, `documentation`, `skill`, `target-image`, `environment-audit`. Use `environment-audit` only for a redacted, route-specific local capability probe whose artifact is hashed and read by the builder.

Access states: `local`, `downloadable`, `login-required`, `request-required`, `controlled`, `unavailable`, `not-found`.

`access` describes the current upstream retrieval or reacquisition route. A populated `artifact` records a separately verified local copy, so a source may legitimately have both a local artifact and `access.state: login-required`. Use `local` when the source is available only as a user-provided or local artifact and no upstream retrieval state applies. Before building, every artifact must include a real non-symlinked `sourcePath`, file name, media type, exact byte size, and lowercase SHA-256; the builder reads the file and rejects a missing, resized, or hash-mismatched artifact. `sourcePath` is removed from the built report.

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
  "target": {
    "targetId": "target-fig-07",
    "acquisitionMode": "paper-with-figure-references",
    "workflowMode": "scientific-reproduction",
    "requestedRef": "Fig. 7",
    "targetSha256": "...",
    "materialization": {
      "method": "pdf-extraction",
      "qaStatus": "verified",
      "page": 6,
      "renderDpi": 300,
      "captionIncluded": true,
      "sourceFileName": "paper.pdf",
      "figureReference": "Fig. 7",
      "cropBoxPdfPoints": [72.0, 210.0, 540.0, 612.0],
      "width": 1950,
      "height": 1675
    }
  },
  "image": {
    "sourcePath": "/local/path/to/fig-07.png",
    "sourceRef": "src-paper",
    "redistributionAllowed": true,
    "bundleState": null,
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

`target` is the immutable scientific object selected in Phase 0. It has exactly these fields: `targetId`, `acquisitionMode`, `workflowMode`, nullable `requestedRef`, `targetSha256`, and `materialization`. `targetSha256` binds the normalized Phase 0 PNG and is the digest used by approval. The exact `materialization` fields are:

- `method`: for example `pdf-extraction` or `user-upload`;
- `qaStatus`: must be `verified` before report construction;
- nullable `page`, plus `renderDpi`, `captionIncluded`, `sourceFileName`, nullable `figureReference`, nullable `cropBoxPdfPoints`, `width`, and `height`.

Phase 0 preserves the uploaded or extracted original separately from the normalized target and records its own provenance in the target manifest. Do not substitute a later report asset for this target identity.

`image` describes report transport, not target identity. Before building, `sourcePath` points to the verified normalized target. The builder writes a sanitized PNG and records its independent asset digest in `image.sha256`; this value may differ from `target.targetSha256` because sanitization or re-encoding may change the bytes. Never use the bundled asset hash as the approval identity.

For `audience: "local"`, every target must be copied and rendered with `bundleState: "embedded-local"`, irrespective of redistribution permission. For `audience: "public"`, the builder uses `bundleState: "embedded-public"` only when `redistributionAllowed` is exactly `true`; otherwise it removes the path and asset digest, sets `bundleState: "omitted-rights"`, and displays a rights notice. An omitted target cannot be approved from that public bundle. The image must declare `mediaType: "image/png"` and be a non-symlinked PNG inside the approved target workspace, no larger than 25 MiB. The builder emits only allowlisted PNG chunks and replaces private `sourcePath` with generated relative `assets/...` output. JPEG and SVG inputs must first be normalized to PNG during Phase 0.

Keep one stable `figureId` for multi-panel figures. Describe panel-specific observations with `location`; create separate figure objects only when panels have meaningfully different routes or dependencies.

In `scientific-reproduction`, `paperClaim`, `evidenceRole`, and `authorInterpretation` are required non-empty strings and the report root must contain a paper. In `image-derived-reconstruction`, `paperClaim` and `authorInterpretation` must be `null`; `evidenceRole` may be `null` or a narrowly worded visual-reconstruction scope. This prevents an image-only route from inventing paper context.

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

`generationLogic.formulaAudit` is optional and should be present only when a formula, parameter, or theoretical assumption directly controls the target's generation chain or acceptance criteria. It is not a request to review every equation in the paper.

```json
{
  "scope": "target-chain-only",
  "included": ["Eq. (12) update rule", "normalization parameter beta"],
  "excluded": ["Unrelated convergence proof in Section IV"],
  "rationale": "These dependencies determine the plotted response and its peak positions.",
  "items": [
    {
      "checkId": "formula-eq12",
      "label": "Response update",
      "dependency": "Directly computes the vertical-axis response.",
      "sourceStatement": "Paper Eq. (12); implementation function update_response.",
      "checks": ["derivation", "dimensions", "boundary-cases", "code-cross-check", "figure-trend"],
      "status": "paper-code-divergence",
      "finding": "The code normalizes before thresholding while the printed equation normalizes afterwards.",
      "implementationDecision": "split-routes",
      "routeBindings": [
        {"routeId": "route-fig12-paper", "interpretation": "paper-formula"},
        {"routeId": "route-fig12-code", "interpretation": "code-implementation"}
      ],
      "evidenceRefs": ["src-paper", "src-official-code"]
    }
  ]
}
```

Allowed checks are `derivation`, `self-consistency`, `dimensions`, `units`, `boundary-cases`, `matrix-shape`, `code-cross-check`, `source-cross-check`, and `figure-trend`; select only those relevant to the dependency. Status is one of `verified`, `derived`, `ambiguous`, `paper-code-divergence`, `invalid`, or `not-checkable`. Implementation decision is one of `use-as-stated`, `use-derived`, `split-routes`, `freeze-assumption`, or `block`.

Use this status-to-decision mapping:

| Status | Legal decisions |
| --- | --- |
| `verified` | `use-as-stated` |
| `derived` | `use-derived` |
| `ambiguous` | `freeze-assumption`, `split-routes`, `block` |
| `paper-code-divergence` | `split-routes`, `block` |
| `invalid` | `use-derived`, `block` |
| `not-checkable` | `freeze-assumption`, `block` |

Every non-blocking decision binds its same-figure route through structured `routeBindings` entries shaped as `{"routeId": "...", "interpretation": "..."}`. Interpretations are `paper-formula`, `code-implementation`, `alternative-derived`, `as-stated`, `derived`, and `assumed`; they must agree with the implementation decision. `use-derived` also requires an explicit `derivation` check. `split-routes` binds at least two distinct, existing, scientifically distinct route definitions with distinct interpretations. Any non-empty `paper-code-divergence` binding set must include at least one `paper-formula` route and one different `code-implementation` route; repeated IDs, cloned routes, or IDs from another figure do not count. This is what keeps paper and code interpretations machine-visible instead of silently choosing one.

For `block`, non-empty `routeBindings` may name only routes already marked `blocked`. An empty list means a figure-wide block and is legal only when every candidate route is blocked. A blocked `paper-code-divergence` must cover every candidate route; otherwise express the alternatives with `split-routes`. A derivation or correction is evidence, not a silent rewrite: state its basis, preserve uncertainty, and make any resulting change in claim scope explicit.

### Validation target

Kinds: `qualitative-pattern`, `quantitative`, `comparative`, `structural`, `visual-fidelity`.

Every figure requires at least one validation target. A target must define the observable result, the success criterion, exactly what paper claim the result would or would not support, and whether that criterion comes from the paper, code, a derivation, a transparent assumption, or the user. Pixel similarity alone is not a sufficient scientific criterion. It may be used only as a declared visual-fidelity criterion in `image-derived-reconstruction` or an editable reconstruction route, without implying scientific equivalence.

## Requirement

Every route must cover all five readiness categories: `input`, `method`, `protocol`, `validation`, and `environment`. Do not force one row per category: a route may reference several concrete requirements in a category when that is scientifically useful. These conditions summarize whether the selected plan can be executed; they do not replace `understanding`, `generationLogic`, or `validationTargets`. Environment is an execution constraint, not the starting point for scientific understanding.

The figure-level `requirements` array is a catalog. A route's `requirementIds` selects the concrete conditions that apply to that route and must cover every category at least once. Reuse an item only when the underlying condition is genuinely shared between routes.

```json
{
  "requirementId": "req-fig07-input",
  "category": "input",
  "label": "Simulation input",
  "state": "derivable",
  "blocking": false,
  "detail": "Equations and principal parameters support an independently generated input.",
  "resolution": {
    "status": "frozen",
    "basis": "Use the paper equations and the declared deterministic seed 2026."
  },
  "evidenceRefs": ["src-paper"]
}
```

States: `verified`, `derivable`, `assumable`, `missing`, `not-required`.

`missing` means an essential condition cannot currently be supplied or defensibly inferred and must use `blocking: true`. Use `assumable` for a declared, scientifically reasonable choice that changes uncertainty but does not invalidate the route. A `derivable` condition becomes execution-ready only when `resolution.status: "frozen"` records the exact derivation basis; an `assumable` condition becomes execution-ready only when `resolution.status: "accepted"` records the accepted basis. The evidence state remains derivable or assumable—it is not relabeled verified. A `verified` requirement must cite evidence. A derivable or assumable requirement must cite evidence or carry its documented resolution. Render both `blocking` and any resolution explicitly.

Figure reproduction levels are `direct-recompute`, `mechanism-reproduction`, `alternative-validation`, `editable-reconstruction`, `image-derived-reconstruction`, and `original-case-blocked`. Each figure has exactly one level; candidate routes describe how they serve that level rather than declaring another level. Use `image-derived-reconstruction` only when the target's workflow mode has that same value. `recommendedRouteId` identifies one non-blocked route whenever any non-blocked candidate exists. Set it to `null` only when every declared route is blocked. A blocked image-derived assessment remains `image-derived-reconstruction`; route readiness never changes it into `original-case-blocked`.

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

Route status: `ready`, `conditional`, `blocked`. Every non-blocked route must already have runnable scientific requirements: each referenced requirement is `verified`, `not-required`, a `derivable` condition with a frozen resolution, or an `assumable` condition with an accepted resolution. `ready` additionally requires every referenced environment to be route-level verified. Use `conditional` only for an authorized operational prerequisite such as preparing an isolated open-source environment or implementing the already specified adapter; it cannot defer an unresolved data, method, protocol, or validation decision to execution. Show blockers on the route card. Do not place shell, MATLAB, or Python commands in route fields.

A `ready` route may reference only environments with status `verified`; detecting an installation as `available` is not enough. An `available` environment keeps a route `conditional` until route-level live verification succeeds. A `conditional` route may reference an `unknown` or `missing` environment only when its provisioning policy is `isolated-open-source` and the route declares the gated `install` effect. An unresolved `existing-only` environment makes the route `blocked` until the user supplies or verifies it outside the installation workflow. SciRepro never downloads proprietary installers, accepts licenses, or turns static product metadata into a runnable claim.

Parameter types: `string`, `number`, `integer`, `boolean`, `enum`, `relative-path`. Parameter and generation origins: `paper`, `code`, `derived`, `assumption`, `user`.

Effect IDs use a closed registry. Bounded automatic effects are `run-local-code` and `create-workspace-files`. Gated effects are `network`, `install`, `login`, `payment`, `upload`, `overwrite`, `gpu`, `shared-license`, and `external-publish`; every gated effect used by a route must appear in `consentRequiredEffects` and must never appear in `allowedEffects`. Use `shared-license` only when execution consumes a floating, institutional, or otherwise shared license; a local dedicated license can remain ordinary local execution. Declare all five estimate fields. A blocked analysis route may use `null` for an amount that cannot yet be bounded. Every ready or conditional route must freeze non-negative finite values for download bytes, disk bytes, runtime minutes, and cost before it can be selected; `gpu` is always boolean and must agree with the `gpu` effect. Network routes therefore require a finite download bound, a positive download requires `network`, and a positive cost requires `payment`.

## Approval policy

```json
{
  "minFigures": 1,
  "maxFigures": 1,
  "defaultOutputPolicy": "create-only",
  "allowedEffects": ["run-local-code", "create-workspace-files"],
  "consentRequiredEffects": ["network", "install", "login", "payment", "upload", "overwrite", "gpu", "shared-license", "external-publish"],
  "ttlMinutes": 1440
}
```

`maxFigures` is a report-specific approval bound and must not exceed the number of materialized targets. It is not a product input limit. The report may contain from 1 through the defensive maximum of 256 targets, while a report author may choose a smaller approval batch for operational clarity.

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

The approval draft may select only IDs, parameters, deliverables, and effects already declared in the report. `selectedFigures[].sourceImageSha256` must equal the selected figure's `target.targetSha256`, not the sanitized report asset's `image.sha256`. The target hash binds approval to the exact normalized Phase 0 reproduction object, while the report hash binds the selected route to its scientific scope, validation targets, assumptions, blockers, and execution estimates. The approval gate rejects credential-shaped parameter values and copies only validated values into the matching `gate-result.selectedTargets[].parameters`; Phase 2 consumes that record rather than reparsing approval input. Never execute commands or new URLs from an approval file.

`outputPolicy.mode: "overwrite-approved"` is valid only when every approved overwrite is named in `explicitFiles`, the selected route declares the gated `overwrite` effect, and that effect is separately acknowledged. A `create-only` approval must not select a route that requires overwrite. The bundled static report exports `create-only` approvals only; use a separately reviewed approval workflow when explicit-file overwrite is genuinely required.

`approvalId` and `idempotencyKey` are required ASCII identifiers: 8–128 characters, beginning with an alphanumeric character and continuing with alphanumerics, `.`, `_`, or `-`. The gate validates their syntax only. Phase 2 must atomically persist consumed approval IDs and idempotency keys before side effects and reject replay; a stateless gate result is not evidence of one-time consumption.

## Integrity rules

- Require 1–256 unique figure and target IDs, with the target count matching `targetSet.targetCount`.
- Require every target to bind a verified Phase 0 materialization and a valid acquisition/workflow pair.
- Require a research objective, structured understanding, at least one observation, a non-empty generation chain, and at least one validation target for every figure.
- Require a complete paper plus non-null paper claim, evidence role, and author interpretation for `scientific-reproduction`. Permit a null root paper only for paperless `images-only` targets, and require null paper claim and author interpretation for `image-derived-reconstruction`.
- Require every observation, input, generation step, validation target, requirement, environment, and figure evidence reference to resolve to a declared source.
- When `formulaAudit` is present, require `scope: "target-chain-only"`, at least one named dependency and check item, resolved evidence references, a legal status-to-decision pairing, and valid same-figure route bindings. Do not require a formula audit when no expression or parameter directly controls the target.
- Require every scientific-scope observation and validation reference to resolve within the same figure.
- Require every recommended route to exist and be non-blocked.
- Require a recommendation when any non-blocked route exists; permit a null recommendation only when every candidate route is blocked.
- Require every route effect to be declared by `approvalPolicy`.
- Remove `integrity.reportSha256` before deterministic JSON hashing, then restore the digest.
- Require `audience: "local"` bundles to embed every target. Permit `omitted-rights` only in a public bundle and do not allow an omitted target to enter approval.
- Bind `selectedFigures[].sourceImageSha256` to `target.targetSha256`; validate a bundled asset digest independently when the asset exists.
- Rebuild the report if the target manifest, target bytes, source artifact, report asset, scientific interpretation, generation step, validation target, route scope, environment, assumption, budget, or reproduction level changes.
