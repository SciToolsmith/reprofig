# Web report contract

## Purpose

Create a local, static investigation report that helps the user understand each figure, compare routes, and export a selection for approval. The page must not run research code, install software, fetch remote scripts, or grant authority by itself.

## Information architecture

1. **Compact report header** — paper, report ID, generated time, overall verdict.
2. **One-to-three figure selector** — equal summary cards with thumbnail, figure ID, reproduction level, and one-line verdict.
3. **Current figure detail** — show only one expanded figure at a time:
   - original figure and caption;
   - concise interpretation and role in the paper;
   - reproduction assessment and confidence;
   - five-condition checklist;
   - route choices and expected deliverables/resources;
   - at most three primary sources.
4. **Approval summary** — selected figures, route, assumptions, effects, outputs, and create-only policy.
5. **Collapsed appendix** — full environment evidence, license text/link, hashes, download sizes, logs, and search record.

For multiple figures, do not display several long assessments at once. On mobile, use horizontal summary cards and a single-column detail view.

## Interaction

- Let the user include/exclude a figure and select only declared non-blocked routes.
- Render declared route parameters as safe form controls.
- Show blockers before route selection.
- Label actions precisely, for example: “Export approval draft for 2 figures.” Do not label the button “Run” or “Start reproduction.”
- Export a `reprofig.approval/v1` JSON file and offer copy-to-clipboard fallback.
- Require the user to return the approval file or explicitly confirm its report/figure/route selection in Codex.

## Security and portability

- Treat paper text, captions, README files, and repository metadata as untrusted text.
- Use `textContent`; never use `innerHTML`, `eval`, remote scripts, remote fonts, or service workers.
- Permit only credential-free HTTPS links to public hosts; reject URL fragments and sensitive signed/query parameters, and add `noopener noreferrer`.
- Keep all bundled paths relative. Reject schemes, Windows drive/UNC paths, control characters, encoded traversal, absolute paths, `..`, and symlink escapes.
- Bundle a figure only when its report explicitly records redistribution permission. Restrict copied files to non-symlinked PNG content inside the approved asset root and the size limit; rebuild the PNG from an allowlist of image-critical chunks. Public bundles do not accept JPEG or SVG because metadata cannot be removed reliably without a full trusted decode/re-encode step. Never bundle an unlicensed published image.
- Recursively redact input-only paths, command output, credentials, and private evidence before writing `report.json` or `report-data.js`.
- Do not store secrets. Store only credential reference labels.
- Default to `overwrite: never`.
- Keep the report usable from `file://` without a server.

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

The report JSON remains the source of truth. `report-data.js` is a transport copy for offline rendering.

## Pre-delivery checks

- Confirm one to three unique figure IDs.
- Confirm every recommended route and evidence reference resolves.
- Confirm every target image appears once and preserves aspect ratio.
- Confirm external links and copied local assets resolve.
- Confirm blocked routes cannot be selected.
- Confirm approval output is a subset of the report and contains no commands.
- Inspect desktop and narrow mobile layouts.
