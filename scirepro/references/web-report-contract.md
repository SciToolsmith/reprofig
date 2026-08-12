# Web report contract

## Purpose

Create a local-first, static investigation report for one or more Phase 0 target figures. The report must show the exact reproduction objects before it asks the researcher to choose an execution route. It supports two intentionally distinct workflows:

- **Scientific reproduction** starts from a paper and target figures, reconstructs their data-to-figure generation process, and defines evidence-based scientific validation.
- **Image-derived reconstruction** starts from target images without sufficient paper context and may recover visible geometry, plotted values, or appearance. It must not claim to recover the original data, method, author interpretation, or scientific result.

The report must help the researcher:

1. verify which target images SciRepro will reproduce;
2. read what is visibly present in each target;
3. understand the paper claim and evidentiary role when paper evidence exists;
4. inspect the inferred data-to-figure generation chain and its unknowns;
5. see explicit validation targets;
6. compare reproduction routes by scientific scope, substitutions, assumptions, and limitations;
7. review execution conditions and export a target-bound route selection for approval.

The page must not run research code, install software, fetch remote scripts, or grant authority by itself. Approval is an execution safeguard at the end of the report, not the report's organizing concept.

## Phase 0 input modes

The report accepts any non-empty target set up to the defensive technical maximum of 256. There is no product-level one-to-three limit. A target set may use one or more of these acquisition modes:

- `paper-with-images`: a paper and one or more user-supplied target images;
- `paper-with-figure-references`: a paper and one or more requested figure numbers or ranges; SciRepro extracts complete figure objects during Phase 0;
- `images-only`: one or more target images without a paper.

Every target must be materialized into the target workspace, normalized to PNG, hashed, visually verified, and recorded in the Phase 0 manifest before report construction. The report root binds that manifest through `targetSet.manifestSha256`; every figure binds one target through `target.targetSha256`.

## Information architecture

1. **Compact research header** — paper when present, report objective, report ID, target count, report audience, and a secondary overall assessment.
2. **Scrollable target selector** — a horizontal sequence of fixed-size summary cards for every target. It must scale from one target to the technical limit without enlarging sparse target sets or rendering all long details at once. Keep exactly one current target detail active.
3. **Current target detail** — preserve this order:
   1. **00 · Reproduction target** — visibly render the Phase 0 image, complete caption when available, requested reference, acquisition mode, workflow mode, page/DPI/crop provenance, QA state, target digest, and report distribution state. This section is mandatory and precedes interpretation.
   2. **01 · Read the figure** — visual summary and separately stated observations. Do not merge direct observation with interpretation.
   3. **02 · Understand its evidence role** — for scientific reproduction, show the paper claim, evidentiary role, author interpretation, and limitations. For image-derived reconstruction, show a clear paper-context boundary rather than fabricated paper fields.
   4. **03 · Trace how it was generated** — inputs, ordered transformation or analysis steps, plot mapping, provenance, and unresolved unknowns.
   5. **04 · Define validation targets** — observable, criterion, relationship to the paper claim or visual-reconstruction scope, and evidence basis.
   6. **05 · Show the reproduction assessment** — level, verdict, confidence, and evidence-backed rationale.
   7. **06 · Compare routes** — scientific or reconstruction goal first; observations reproduced, substitutions, assumptions, exclusions, validation targets, and deliverables next; operational effects and resource estimates last.
   8. **07 · Review execution conditions** — the selected route's requirements grouped under the five readiness categories, blockers, required environment, parameters, effects, resource estimates, and output policy. A category may contain several concrete conditions; do not manufacture one row per category. Distinguish evidence certainty from execution readiness, and show any frozen derivation or accepted assumption without relabeling it verified. Distinguish a route-level `verified` environment from an `available` installation that still needs live verification; display whether an unresolved environment is `existing-only` or may be configured as `isolated-open-source`.
4. **Collapsed evidence appendix** — environment summaries, checked access state and notes, license identity or link, archived artifact name/size/hash, and target/report asset hashes. Keep raw logs and search transcripts in the local workspace rather than inflating the decision page.
5. **Execution approval** — appear at the end only after at least one eligible target is selected. Summarize each selected route's scope, assumptions, validation targets, deliverables, effects, resources, and create-only policy.

On narrow screens, keep the selector horizontally scrollable and render the current detail in one column. Do not replace absent targets with oversized cards or empty layout fillers.

## Target image and audience rules

`target.targetSha256` identifies the normalized Phase 0 reproduction object. `image.sha256` identifies the sanitized PNG stored in a built report. They are separate integrity domains and may differ after report-safe rewriting. When a target exceeds the report budget, the builder may set `image.displayProxy: true` and embed a downsampled report-only proxy; approval and Phase 2 still bind the full Phase 0 target hash.

- A `local` report must visibly embed every Phase 0 target and set `image.bundleState` to `embedded-local`. Unknown redistribution rights do not hide the target from the researcher's own local investigation report.
- A `public` report may embed a target only when `redistributionAllowed` is exactly `true`, using `embedded-public`. Otherwise it must omit the bytes, private path, and asset hash, use `omitted-rights`, and render an explicit rights notice in section 00.
- A target omitted from a public bundle cannot be selected for approval from that bundle.
- Never expose the Phase 0 workspace path, original source path, or other local filesystem paths in either built audience.

The builder accepts only non-symlinked normalized PNG targets inside the approved target workspace. A target may be larger than the report asset limit; in that case the builder creates a metadata-free, bounded visual proxy rather than rejecting the scientifically valid Phase 0 object. It gives each bundled asset its own digest. JPEG and SVG inputs must be normalized in Phase 0 rather than copied directly into the report.

## Scientific presentation rules

- Treat `understanding.observations` as visible or directly reported facts. Put causal explanation and author interpretation in their dedicated fields.
- In `scientific-reproduction`, require a paper plus non-null paper claim, evidence role, and author interpretation.
- In `image-derived-reconstruction`, permit a null paper root and require null paper claim and author interpretation. State that visual matching or digitization does not establish the original scientific process.
- Render every generation input and step with its origin and evidence references.
- Render verified environment evidence only from a hashed `environment-audit` artifact; do not let a generic paper or documentation link visually stand in for a live capability probe.
- Show validation targets, origin, and evidence basis before the reproduction assessment so success is defined explicitly rather than inferred from appearance or runtime.
- Explain what each route does **not** reproduce. A runnable environment is not necessarily the scientifically strongest route.
- Display confidence, blockers, deliverables, substitutions, assumptions, and recommendation rationale. Do not infer them in the browser.
- Keep source references adjacent to the observation, input, step, or validation target they support. The appendix is additional provenance, not a substitute for local attribution.

## Interaction and approval

- Let the user inspect every declared route, but allow selection only for declared non-blocked routes whose target image is present, whose scientific requirements are runnable, and whose download, disk, runtime, and cost estimates are finite.
- If every candidate route is blocked, render the report as a local blocked assessment with no recommendation or selectable route. Preserve the target's workflow mode and reproduction level; an image-derived target remains `image-derived-reconstruction` rather than being relabelled `original-case-blocked`.
- Render declared route parameters as safe form controls.
- Show blockers on the route card before selection.
- Keep effects and resource estimates inside a clearly labelled execution-details area; do not place them above scientific scope.
- Do not use a permanently fixed approval bar. Reveal approval only after the user includes at least one eligible target.
- Label actions precisely, for example: “Export approval draft for 12 targets.” Do not label the button “Run” or “Start reproduction.”
- Export a `reprofig.approval/v1` JSON file. If the browser blocks local downloads, present the generated JSON in chat rather than claiming an unavailable clipboard control.
- Set every `selectedFigures[].sourceImageSha256` to the selected figure's `target.targetSha256`, never to `image.sha256`.
- Require the user to return the approval file or explicitly confirm its report/figure/route selection in Codex.

## Security and portability

- Treat paper text, captions, README files, repository metadata, uploaded image metadata, and OCR as untrusted text.
- Use `textContent`; never use `innerHTML`, `eval`, remote scripts, remote fonts, or service workers.
- Permit only credential-free HTTPS links to public hosts; reject URL fragments and sensitive signed/query parameters, and add `noopener noreferrer`.
- Keep all bundled paths relative. Reject schemes, Windows drive/UNC paths, control characters, encoded traversal, absolute paths, `..`, and symlink escapes.
- Recursively redact input-only paths, command output, credentials, and private evidence before writing `report.json` or `report-data.js`.
- Do not store secrets. Store only credential reference labels.
- Default to `overwrite: never`.
- Keep the report usable from `file://` without a server. When a browser security policy refuses local-file navigation, serve only the report directory from a temporary loopback listener bound to `127.0.0.1`; never bind the preview publicly, and stop it after visual QA.

## Output bundle

`<skill-root>/scripts/build_report.py --input <report.json> --target-manifest <targets/manifest.verified.json> --audience <local|public> --output <report-dir>` creates:

```text
report-dir/
├── index.html
├── app.js
├── styles.css
├── report-data.js
├── report.json
├── manifest.json
└── assets/
```

The builder stages the complete bundle in a hidden sibling directory and publishes it atomically only after validation and hashing succeed. A failed build must not leave a partial report tree.

The `reprofig.report/v3` JSON is the source of truth. The `reprofig.*` prefix is a compatibility protocol namespace retained after the product became SciRepro; it is not the display name. `report-data.js` is an offline transport copy using `window.__SCIREPRO_REPORT__`. Reports using v1 or v2 must be regenerated with the current Phase 0 and Phase 1 workflow; the browser and execution gate do not reinterpret them under v3.

## Pre-delivery checks

- Confirm 1–256 unique figure IDs and target IDs, with counts matching `targetSet` and the Phase 0 manifest.
- Confirm section 00 visibly displays every target in a local report. In a public report, confirm every omitted target has an explicit rights notice and no bundled bytes or private path.
- Confirm target and report-asset hashes are recorded and validated independently.
- Confirm every scientific target has paper fields, while image-derived targets do not fabricate paper claims or author interpretation.
- Confirm every figure has direct observations, an evidence-linked generation chain, and at least one validation target.
- Confirm every route states its scope, claim coverage or reconstruction boundary, exclusions, assumptions or substitutions, validation targets, blockers, and deliverables as applicable.
- Confirm every recommended route and evidence reference resolves.
- Confirm selector cards remain fixed-size, scroll horizontally, and activate only one detail view.
- Confirm external links and copied local assets resolve.
- Confirm blocked routes and public omitted-rights targets cannot be selected.
- Confirm conditional routes with unresolved scientific requirements and routes with unknown execution resource bounds cannot be selected.
- Confirm approval target digests equal `target.targetSha256`, the approval output is a subset of the report, and it contains no commands.
- Inspect desktop and narrow mobile layouts.
