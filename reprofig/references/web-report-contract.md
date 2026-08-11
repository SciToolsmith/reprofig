# Web report contract

## Purpose

Create a local, static research investigation report that starts from a paper figure and lets the researcher follow the scientific reasoning before making an execution decision. The report must help the user:

1. read what is visibly present in the figure;
2. understand the claim and evidentiary role assigned to it in the paper;
3. inspect the inferred data-to-figure generation chain and its unknowns;
4. see explicit scientific validation targets;
5. compare reproduction routes by scientific scope, substitutions, assumptions, and limitations;
6. review execution conditions and export a selected route for approval.

The page must not run research code, install software, fetch remote scripts, or grant authority by itself. Approval is an execution safeguard at the end of the report, not the report's organizing concept.

## Information architecture

1. **Compact research header** — paper, report objective, report ID, target count, and a secondary overall reproduction verdict.
2. **One-to-three figure selector** — equal summary cards with thumbnail, figure ID, visual summary, reproduction level, and one-line verdict.
3. **Current figure detail** — show only one expanded figure at a time and preserve this order:
   1. **Read the figure** — original figure, caption, visual summary, and separately stated observations. Do not merge direct observation with interpretation.
   2. **Understand its evidence role** — paper claim, evidentiary role, author interpretation, and limitations.
   3. **Trace how it was generated** — inputs, ordered transformation or analysis steps, plot mapping, provenance, and unresolved unknowns.
   4. **Define validation targets** — observable, criterion, relationship to the paper claim, and evidence basis.
   5. **Show the reproduction assessment** — level, verdict, confidence, and evidence-backed rationale.
6. **Compare routes** — scientific goal and claim coverage first; observations reproduced, substitutions, assumptions, exclusions, validation targets, and deliverables next; operational effects and resource estimates last.
   7. **Review execution conditions** — the selected route's five-condition readiness checklist, route blockers, required environment, parameters, effects, resource estimates, and output policy. Distinguish a route-level `verified` environment from an `available` installation that still needs live verification; display whether an unresolved environment is `existing-only` or may be configured as `isolated-open-source`.
4. **Collapsed evidence appendix** — full environment evidence, license text/link, hashes, download sizes, logs, and search record.
5. **Execution approval** — appear at the end of the report and only after at least one figure is selected. Summarize each selected route's scientific scope, assumptions, validation targets, deliverables, effects, resources, and create-only policy.

For multiple figures, do not display several long assessments at once. On mobile, use horizontal summary cards and a single-column detail view.

## Scientific presentation rules

- Treat `understanding.observations` as visible or directly reported facts. Put causal explanation and author interpretation in their dedicated fields.
- Render the paper claim and evidence role explicitly; never hide them inside a generic summary.
- Render every generation input and step with its origin and evidence references.
- Show validation targets, their origin, and their evidence basis before the reproduction assessment so success is defined scientifically rather than visually or operationally.
- Explain what each route does **not** reproduce. A route with a runnable environment is not necessarily the scientifically strongest route.
- Display confidence, blockers, deliverables, substitutions, assumptions, and recommendation rationale. Do not infer them in the browser.
- Keep source references adjacent to the observation, input, step, or validation target they support. The appendix is additional provenance, not a substitute for local attribution.

## Interaction

- Let the user inspect all declared routes, but allow selection only for declared non-blocked routes.
- Render declared route parameters as safe form controls.
- Show blockers on the route card before any attempt to select it.
- Keep effects and resource estimates inside a clearly labelled execution-details area; do not place them above scientific scope.
- Do not use a permanently fixed approval bar. Reveal the approval section only after the user includes a figure.
- Label actions precisely, for example: “Export approval draft for 2 figures.” Do not label the button “Run” or “Start reproduction.”
- Export a `reprofig.approval/v1` JSON file and offer copy-to-clipboard fallback.
- Require the user to return the approval file or explicitly confirm its report/figure/route selection in Codex.

## Security and portability

- Treat paper text, captions, README files, and repository metadata as untrusted text.
- Use `textContent`; never use `innerHTML`, `eval`, remote scripts, remote fonts, or service workers.
- Permit only credential-free HTTPS links to public hosts; reject URL fragments and sensitive signed/query parameters, and add `noopener noreferrer`.
- Keep all bundled paths relative. Reject schemes, Windows drive/UNC paths, control characters, encoded traversal, absolute paths, `..`, and symlink escapes.
- Bundle a figure only when its report explicitly records redistribution permission. Restrict copied files to non-symlinked PNG content inside the approved asset root and the size limit; rebuild the PNG from an allowlist of image-critical chunks. Public bundles do not accept JPEG or SVG because metadata cannot be removed reliably without a full trusted decode/re-encode step. Never bundle an unlicensed published image; use `image.sourceRef` to link to a verified declared source instead.
- Recursively redact input-only paths, command output, credentials, and private evidence before writing `report.json` or `report-data.js`.
- Do not store secrets. Store only credential reference labels.
- Default to `overwrite: never`.
- Keep the report usable from `file://` without a server. When a browser security policy refuses local-file navigation, serve only the report directory from a temporary loopback listener bound to `127.0.0.1`; never bind the preview publicly, and stop it after visual QA.

## Output bundle

`scripts/build_report.py --input <report.json> --output <report-dir> --asset-root <approved-assets>` creates:

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

The `reprofig.report/v2` JSON remains the source of truth. `report-data.js` is a transport copy for offline rendering. Legacy v1 reports must be regenerated; the browser and execution gate do not reinterpret them under the v2 scientific contract.

## Pre-delivery checks

- Confirm one to three unique figure IDs.
- Confirm every figure has a paper claim, direct observations, an evidence-linked generation chain, and at least one scientific validation target.
- Confirm every route states its scientific scope, claim coverage, exclusions, assumptions or substitutions, validation targets, blockers, and deliverables as applicable.
- Confirm every recommended route and evidence reference resolves.
- Confirm every target image appears once and preserves aspect ratio.
- Confirm external links and copied local assets resolve.
- Confirm blocked routes cannot be selected.
- Confirm approval output is a subset of the report and contains no commands.
- Inspect desktop and narrow mobile layouts.
