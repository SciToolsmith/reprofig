# Target figure acquisition

Phase 0 gives every requested object a stable target ID, normalized image, hash, provenance, and review state before scientific assessment. All entry paths accept one or many targets.

## Three entry paths

### Paper plus uploaded images

- Preserve every supplied paper and image byte-for-byte; normalize images to metadata-minimized PNG without changing aspect ratio.
- Match each image to the paper through caption, panels, axes, labels, and nearby text. Filename alone is insufficient.
- Assign `scientific-reproduction` only after a reliable paper binding. Otherwise keep the item pending or use an explicitly limited image-derived route.

### Paper plus figure references

- Treat requested labels as opaque user identifiers. Accept numeric lists/ranges and free text such as `Fig. 2a`, `S3`, `Extended Data 4`, `图 5`, or a panel description.
- Use automatic extraction only when the bundled tool parses the identifier and finds one unambiguous complete caption/crop.
- Crop the graphic, every panel/legend/label/annotation, figure number, and complete wrapped caption; exclude unrelated prose and neighboring figures.
- If automatic extraction cannot represent the label, caption location, cross-page object, or layout safely, create a reviewed manual crop. Preserve the original label, paper/page/caption binding, crop provenance, and QA evidence; never coerce it into a different numeric reference.

### Images only

- Preserve and normalize every image; use user labels and visible content for identity.
- Assign `image-derived-reconstruction`. Do not manufacture a paper citation, original method/data, evidence role, or scientific claim.

## Workspace and identity

Create a new/versioned directory; never overwrite an earlier target set:

```text
targets/
├── originals/       # byte-preserved supplied sources
├── figures/         # normalized PNG targets used by report/analysis
├── qa/              # page/crop overlays and review evidence
└── manifest.json    # scirepro.targets/v1
```

For each target record acquisition/workflow mode, requested label, stable ID, paper/page/caption when known, normalized relative path/media type, source and target SHA-256, dimensions/DPI/crop box, caption inclusion, QA status/notes, and local/redistribution status.

The normalized target hash is the report and approval identity. A later sanitized or public asset has its own asset hash and never replaces the target hash.

## Visual QA and partial admission

Inspect every target at readable resolution and compare paper crops with their page overlay. Mark:

- `verified`: correct requested object; all relevant panels, legends, axes, labels, annotations, figure number/caption when requested, readable pixels, preserved aspect ratio, and matching hash;
- `pending`: plausible but unreviewed, ambiguous, incomplete, unmatched, or awaiting a manual replacement;
- `rejected`: confirmed incorrect target or unusable crop, with reason.

Assessment may continue for any verified subset. Pending/rejected targets stay in the original manifest and in a separate local acquisition summary beside the report or in chat; they do not block unrelated verified targets. The current report and approval schemas bind only admitted verified target IDs/hashes. Never execute pending or rejected targets.

If a replacement changes pixels, preserve the former acquisition in provenance, refresh hashes, and return that target to `pending`; do not invalidate unrelated verified targets.

## Local and public use

The local workspace/report may retain and display paper-extracted or user-supplied targets for the user's analysis without exposing absolute paths. Redistribution is separate:

- local report: show every admitted verified target; keep unresolved-item status in the separate acquisition summary beside it;
- public report: include target bytes only with verified redistribution permission; otherwise show a rights notice without paths, filenames, signed URLs, or content.

Never infer redistribution permission from possession, public accessibility, or a paper subscription.

## Deterministic helper

Resolve the skill directory and invoke its scripts with absolute task paths. The helper requires Python 3.10+, Pillow, and pdfplumber; automatic PDF extraction also requires Poppler `pdftoppm`. Prefer existing compatible environments, otherwise create a project-local open-source environment within budget.

```bash
# Paper + uploaded images with numeric references
python <skill-root>/scripts/materialize_target_figures.py --paper paper.pdf \
  --image fig-1.png --image fig-2.png \
  --uploaded-figure-refs 1,2 --output targets

# Paper + numeric references/ranges
python <skill-root>/scripts/materialize_target_figures.py --paper paper.pdf \
  --figures 1,3,5-8 --output targets

# Images only
python <skill-root>/scripts/materialize_target_figures.py \
  --image target-a.png --image target-b.png --output targets

# Verify only after visual review
python <skill-root>/scripts/materialize_target_figures.py \
  --verify-manifest targets/manifest.json --verify-targets fig-01,fig-02

# Continue with a verified subset without copying target bytes
python <skill-root>/scripts/materialize_target_figures.py \
  --derive-subset-manifest targets/manifest.json \
  --subset-output targets/manifest.verified.json \
  --subset-target-set-id targets-verified
```

Use `targets/manifest.verified.json` as the report and approval-gate manifest, including when all original-manifest targets were admitted. The original `manifest.json` remains the complete acquisition ledger.

Use `--verify-all` only after reviewing the entire set. For an uploaded paper figure that already includes its original caption, use `--verified-caption-included` when the binding has been reviewed.

If an existing target crop fails QA, replace it traceably and review again:

```bash
python <skill-root>/scripts/materialize_target_figures.py \
  --replace-manifest targets/manifest.json \
  --replace-target fig-01 --replacement-image reviewed-fig-01.png
```

For a free-text reference that automatic extraction cannot create safely, acquire the reviewed crop as a paper-plus-image target, then bind its identity without editing the normalized PNG in place:

```bash
python <skill-root>/scripts/materialize_target_figures.py \
  --bind-manifest targets/manifest.json --bind-target uploaded-01 \
  --paper-figure-label "Fig. S1" --paper-page 12 \
  --paper-caption "Complete reviewed caption from the paper."
```

Binding remains pending until visual verification. Keep the exact user label, page, complete caption, target hash, and QA record.
