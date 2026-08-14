# Target figure acquisition

Use this reference only when stable target identity is required for execution or comparison. Do not materialize targets for a read-only answer unless ambiguity can change the answer. For a semantic schematic, follow [diagram-handoff.md](diagram-handoff.md) and acquire only the readable source needed for terminal transfer.

Before expanding acquisition with another extraction/search branch, delegated task, broad probe, or replacement cycle, name internally the target-identity unknown and the route, claim, safety, cost, or deliverable decision it can change. Normal reads, renders, and helper commands inside the chosen branch need no per-call justification. Stop once every executable target is sufficiently identified; do not continue paper or source archaeology for completeness.

## Three entry paths

### Paper plus uploaded target images

Preserve supplied bytes and normalize each image to a metadata-minimized PNG without changing aspect ratio. Bind it to the paper through the complete caption, panel labels, axes, legends, annotations, and only necessary nearby context—not its filename. Use scientific reproduction only after visual review establishes the binding; otherwise leave the target unresolved or explicitly image-derived.

### Paper plus figure references

Treat each user label as opaque text. Numeric figures, panels, supplements, Extended Data, localized labels, and descriptions need not share one parser. Use automatic extraction only when the helper represents the label and finds one unambiguous figure with its complete caption. Use a reviewed manual crop for panels, free-text labels, cross-page layouts, supplements, or ambiguous typography.

Include every requested panel, axis, legend, label, annotation, figure identifier, and complete wrapped caption needed to identify and interpret the target. Exclude neighboring figures and unrelated prose. Preserve page/crop provenance; never coerce an unsupported label into a different numeric figure.

### Target images alone

Preserve and normalize every image. Use `image-derived-reconstruction`; do not invent paper identity, original data or method, evidence role, or a scientific claim.

## Multi-target identity and QA

Track every requested target separately with a stable ID, requested label, acquisition mode, workflow mode, source/normalized hashes, dimensions and crop, caption/paper binding when known, rights state, and QA status. Preserve parent figure and panel relationships. Verified targets may proceed independently while unresolved targets remain isolated.

Use these states internally:

- `verified`: the requested object and necessary context are complete, readable, correctly bound, and hash-matched;
- `pending`: plausible but ambiguous, incomplete, unreviewed, or awaiting replacement/binding;
- `rejected`: confirmed wrong or unusable, with a reason.

Execute only verified targets. If pixels change, preserve the prior identity internally, refresh the hash, and return only that target to pending.

The normalized hash is the reproduction-object identity. A public proxy or later download does not replace it.

## Transient acquisition workspace

Use `scripts/materialize_target_figures.py` for deterministic normalization, hashing, traceable replacement, numeric PDF extraction, and internal QA:

```text
targets/
├── originals/
├── figures/
├── qa/
└── manifest.json
```

This tree belongs inside the transient workspace. It is not the customer delivery structure. Raw originals, page renders, overlays, manifests, and rejected/pending targets stay internal unless a specific rights-safe artifact is required to understand or rerun the selected result.

## Deterministic operations

Resolve the skill root and task paths absolutely. The helper needs Python 3.10+, Pillow, and pdfplumber; automatic PDF rendering also needs Poppler `pdftoppm`. Before creating an environment, inspect host-provided bundled workspace runtimes and existing task or user environments. Reuse a compatible one; create a project-local environment under [permission-gates.md](permission-gates.md) only when none is suitable.

Before creating a workspace, the helper inspects image dimensions, resolves requested PDF pages, totals input bytes, and estimates peak acquisition disk. The default automatic preflight allowance is 2 GiB; it is a planning check, not runtime enforcement. A reviewed task may pass a larger positive `--max-output-bytes` value up to the helper's 64 GiB ceiling. Failed preflight leaves no target workspace.

PDF rendering does not execute `pdftoppm` from arbitrary `PATH`. Automatic resolution is limited to fixed trusted installation locations; otherwise pass a reviewed absolute, non-symlinked executable with `--pdftoppm-executable`. The helper constrains the rendering environment and timeout and redacts unsafe failure details.

```bash
# Uploaded images or image-only targets
python <skill-root>/scripts/materialize_target_figures.py \
  --image target-a.png --image target-b.png --output targets

# Numeric figures from a paper
python <skill-root>/scripts/materialize_target_figures.py \
  --paper paper.pdf --figures 1,3,5-8 --output targets

# Verify only after visual inspection
python <skill-root>/scripts/materialize_target_figures.py \
  --verify-manifest targets/manifest.json --verify-targets fig-01,fig-03
```

For a reviewed replacement, use `--replace-manifest`, `--replace-target`, and `--replacement-image`; do not edit normalized pixels in place. For a manual paper crop, bind its exact label, page, and complete caption with `--bind-manifest`; keep it pending until visual verification.

## Rights and customer boundary

Local analysis may retain a supplied or paper-extracted target. Redistribution is a separate decision: include target pixels in a customer folder only with verified permission. Otherwise provide a rights-safe omission and durable source identity without local paths, signed URLs, or restricted content. Never infer redistribution permission from possession, subscription, or public accessibility.
