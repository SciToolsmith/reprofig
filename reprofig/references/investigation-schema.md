# Investigation schema

Use this contract as the single source of truth for the report, approval draft, and Phase 2 gate. Keep summaries concise and store evidence in structured fields.

## Report root

```json
{
  "schemaVersion": "reprofig.report/v1",
  "reportId": "rpt-unique-id",
  "generatedAt": "2026-08-11T12:00:00Z",
  "generator": {"name": "reprofig", "version": "0.1.0"},
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
    "overallLevel": "conditional",
    "oneLine": "One concise conclusion",
    "figureCount": 1
  },
  "environment": [],
  "sources": [],
  "figures": [],
  "approvalPolicy": {}
}
```

`sourcePath` is input-only and is always removed from the published report. The builder does not bundle the paper or source archives automatically. Link to their verified public source, or manage a separately approved redistribution step.

## Environment

```json
{
  "environmentId": "matlab-r2025a",
  "label": "MATLAB R2025a",
  "status": "verified",
  "version": "25.1",
  "detail": "Executable and required toolbox functions were probed.",
  "evidenceRefs": ["src-env-audit"]
}
```

Allowed status values: `verified`, `available`, `unknown`, `missing`.

## Source

```json
{
  "sourceId": "src-official-code",
  "kind": "official-code",
  "title": "Official implementation",
  "publisher": "Author repository",
  "url": "https://example.org/resource",
  "access": {
    "state": "local",
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

License states: `verified`, `declared`, `unknown`, `restricted`.

## Figure

```json
{
  "figureId": "fig-07",
  "label": "Fig. 7",
  "page": 6,
  "section": "III-A Simulation A",
  "caption": "Original caption",
  "image": {
    "sourcePath": "/local/path/to/fig-07.png",
    "redistributionAllowed": true,
    "mediaType": "image/png",
    "sha256": "..."
  },
  "role": "result evidence",
  "summary": "What the figure shows and why the paper uses it.",
  "reproduction": {
    "level": "mechanism-reproduction",
    "verdict": "Mechanism can be reproduced with reconstructed simulation input",
    "confidence": "medium",
    "assessment": "Evidence-backed feasibility explanation.",
    "recommendedRouteId": "route-fig07-matlab"
  },
  "requirements": [],
  "routes": [],
  "sourceRefs": ["src-paper", "src-official-code"]
}
```

`redistributionAllowed` must be exactly `true` before `build_report.py` will copy an image. The image must declare `mediaType: "image/png"` and be a non-symlinked PNG inside the approved `--asset-root`, no larger than 25 MiB. The builder emits only allowlisted PNG chunks and replaces `sourcePath` with a generated `assets/...` path. JPEG and SVG are not accepted in public bundles; convert them to PNG in a trusted image editor first, then repeat the rights and content check. If redistribution is not authorized, omit `sourcePath` and show a verified, fragment-free HTTPS source link instead of bundling the image.

Keep one stable `figureId` for multi-panel figures. Add optional `panels` only when panels have meaningfully different dependencies.

## Requirement

Use five requirements in this order: `environment`, `input`, `method`, `protocol`, `validation`.

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

`missing` means an essential condition cannot currently be supplied or defensibly inferred. Use `assumable` for a declared, scientifically reasonable choice that changes uncertainty but does not invalidate the route.

## Route

```json
{
  "routeId": "route-fig07-matlab",
  "label": "Reconstruct simulation and run official MATLAB method",
  "status": "conditional",
  "recommended": true,
  "engine": "MATLAB R2025a",
  "environmentIds": ["matlab-r2025a"],
  "requirementIds": ["req-fig07-input"],
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

Route status: `ready`, `conditional`, `blocked`. Do not place shell, MATLAB, or Python commands in route fields.

Parameter types: `string`, `number`, `integer`, `boolean`, `enum`, `relative-path`. Parameter origins: `paper`, `code`, `derived`, `assumption`, `user`.

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

The approval draft may select only IDs, parameters, deliverables, and effects already declared in the report. Never execute commands or new URLs from an approval file.

`outputPolicy.mode: "overwrite-approved"` is valid only when every approved overwrite is named in `explicitFiles`, the selected route declares the gated `overwrite` effect, and that effect is separately acknowledged. A `create-only` approval must not select a route that requires overwrite. The bundled static report exports `create-only` approvals only; use a separately reviewed approval workflow when explicit-file overwrite is genuinely required.

`approvalId` and `idempotencyKey` are required ASCII identifiers: 8–128 characters, beginning with an alphanumeric character and continuing with alphanumerics, `.`, `_`, or `-`. The gate validates their syntax only. Phase 2 must atomically persist consumed approval IDs and idempotency keys before side effects and reject replay; a stateless gate result is not evidence of one-time consumption.

## Integrity rules

- Require one to three unique figures per report.
- Require every reference to resolve to a declared source, environment, requirement, or route.
- Require every recommended route to exist and be non-blocked.
- Require every route effect to be declared by `approvalPolicy`.
- Remove `integrity.reportSha256` before deterministic JSON hashing, then restore the digest.
- Rebuild the report if a source artifact, figure image, route, environment, assumption, budget, or reproduction level changes.
