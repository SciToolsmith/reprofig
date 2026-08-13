# Target figure acquisition

Use this reference when execution or comparison needs stable target identity. Do not materialize targets for a read-only answer unless identity would otherwise remain ambiguous. For a semantic schematic, follow [diagram-handoff.md](diagram-handoff.md) and acquire only the readable source needed by the receiver.

## Identity by entry path

### Paper plus uploaded images

Preserve supplied bytes and normalize each image to a metadata-minimized PNG without changing aspect ratio. Bind the image to the paper using the complete caption, panels, axes, legends, annotations, and nearby context—not its filename. Use `scientific-reproduction` only after visual review establishes the binding; otherwise leave it unresolved or explicitly image-derived.

### Paper plus figure references

Treat the user’s label as opaque text: numeric figures, panels, supplements, Extended Data, localized labels, and descriptions need not share one parser. Use automatic extraction only when the helper represents the label and finds one unambiguous figure and complete caption. The bundled helper’s automatic PDF extraction is primarily for numeric references; use scientific judgment and a reviewed manual crop for panels, free-text labels, cross-page layouts, supplements, or ambiguous typography.

Include every requested panel, axis, legend, label, annotation, figure identifier, and complete wrapped caption needed to identify and interpret the target. Exclude neighboring figures and unrelated prose. Preserve page/crop provenance and never coerce an unsupported label into a different numeric figure.

### Images only

Preserve and normalize every image. Use `image-derived-reconstruction`; do not invent paper identity, original data/method, evidence role, or a scientific claim.

## Workspace and QA

Use `scripts/materialize_target_figures.py` for deterministic normalization, hashing, manifests, traceable replacement, and numeric PDF extraction:

```text
targets/
├── originals/
├── figures/
├── qa/
└── manifest.json
```

Record stable target ID, acquisition/workflow mode, exact requested label, paper/page/caption when known, source and normalized hashes, dimensions/DPI/crop, caption inclusion, provenance, QA state, and local/redistribution status. The normalized target hash is the reproduction-object identity; a later proxy or public asset never replaces it.

Visually inspect every target and any page overlay at readable resolution:

- `verified`: the requested object and relevant context are complete, readable, correctly bound, and hash-matched;
- `pending`: plausible but ambiguous, incomplete, unreviewed, or awaiting replacement/binding;
- `rejected`: confirmed wrong or unusable, with reason.

Execute only verified targets. Continue independently with a verified subset while retaining pending/rejected records in the acquisition ledger. If pixels change, preserve the prior version, refresh identity, and return only that target to pending.

## Deterministic operations

Resolve the skill root and task paths absolutely. The helper needs Python 3.10+, Pillow, and pdfplumber; automatic PDF rendering also needs Poppler `pdftoppm`. Use a compatible environment or a project-local one permitted by [permission-gates.md](permission-gates.md).

Before it creates a target workspace, the helper reads every image dimension, resolves requested PDF pages, totals input bytes, and estimates the peak acquisition disk footprint (preserved inputs, normalized images, temporary page renders, crops, and QA overlays). The default automatic preflight budget is 2 GiB. This is a conservative planning check, not a claim that runtime disk use is enforced. If a reviewed acquisition legitimately needs more, pass a positive finite `--max-output-bytes` value; the helper rejects values above its 64 GiB hard ceiling. A failed estimate leaves no target workspace or staging directory.

PDF rendering never executes `pdftoppm` found through the process `PATH`. Automatic resolution is limited to fixed system/Homebrew installation locations and validates the resolved regular executable. When automatic resolution is unavailable, pass the absolute, non-symlinked real executable path with `--pdftoppm-executable`; task, input, output, and other untrusted paths are rejected. The renderer receives a minimal environment, a 120-second page timeout, and redacted failure messages.

```bash
# Uploaded images or images-only targets
python <skill-root>/scripts/materialize_target_figures.py \
  --image target-a.png --image target-b.png --output targets

# Numeric figures from a PDF
python <skill-root>/scripts/materialize_target_figures.py \
  --paper paper.pdf --figures 1,3,5-8 --output targets

# Explicit trusted renderer and a reviewed 4 GiB preflight allowance
python <skill-root>/scripts/materialize_target_figures.py \
  --paper paper.pdf --figures 1,3 \
  --pdftoppm-executable /opt/homebrew/Cellar/poppler/<version>/bin/pdftoppm \
  --max-output-bytes 4294967296 --output targets

# Verify only after visual inspection
python <skill-root>/scripts/materialize_target_figures.py \
  --verify-manifest targets/manifest.json --verify-targets fig-01,fig-03

# Create a verified subset view when a downstream helper requires one
python <skill-root>/scripts/materialize_target_figures.py \
  --derive-subset-manifest targets/manifest.json \
  --subset-output targets/manifest.verified.json \
  --subset-target-set-id targets-verified
```

For a reviewed replacement, use `--replace-manifest`, `--replace-target`, and `--replacement-image`; do not edit normalized pixels in place. For a manual paper crop, acquire it as a paper-plus-image target, then bind its exact label, page, and complete caption with `--bind-manifest`; it remains pending until visual verification.

## Rights

Local analysis may retain a supplied or paper-extracted target. Redistribution is separate: include target pixels in a shareable result only with verified permission; otherwise preserve a rights-safe omission and durable source identity without leaking local paths, signed URLs, or restricted content. Never infer redistribution permission from possession, subscription, or public accessibility.
