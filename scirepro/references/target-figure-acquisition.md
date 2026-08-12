# Target figure acquisition

## Purpose

Phase 0 turns every requested reproduction object into a stable, reviewable target before scientific interpretation or feasibility assessment. Use the same target workspace whether the user supplies images, names figures in a paper, or supplies images without a paper.

Do not use screenshots scattered across temporary directories. Do not treat an automatically detected crop as verified until it has been visually inspected.

## Three entry paths

All paths accept one or many targets.

### Paper plus uploaded images

- Preserve every supplied paper and image byte-for-byte in the investigation workspace.
- Normalize each target image to a metadata-minimized PNG without changing aspect ratio.
- When the user supplies figure references, bind them in order to the uploaded images.
- When references are absent, compare each image against the paper, caption, panels, and nearby text during QA. Do not infer identity from filename alone.
- Assign workflow mode `scientific-reproduction` only after a reliable paper match. Reject or leave ambiguous unmatched images rather than silently associating them.

### Paper plus figure references

- Accept individual references, lists, and ranges such as `1,3,5-8`.
- Locate each figure caption in the supplied paper and render the source page at high resolution.
- Crop the complete figure as one artifact: all panels, legends, labels, annotations, figure number, and the complete caption, including wrapped lines.
- Exclude unrelated body text, headers, footers, and neighboring figures.
- Preserve the page number, crop box, render DPI, extracted caption, paper hash, and QA overlay.
- If a reference is absent, duplicated, ambiguous, or spans pages in a way the extractor cannot resolve safely, stop and perform a reviewed manual crop. Never guess.

### Images only

- Preserve and normalize every supplied image.
- Assign workflow mode `image-derived-reconstruction`.
- Describe target identity from user labels and visible content only.
- Do not manufacture a paper citation, caption, evidence role, original data source, method, or scientific claim.

## Target workspace

Create a new or empty directory for each target set:

```text
targets/
├── originals/       # byte-preserved paper/images supplied for acquisition
├── figures/         # normalized target PNGs
├── qa/              # rendered-page crop overlays and review evidence
└── manifest.json    # scirepro.targets/v1
```

Do not overwrite an earlier target set. Use a new target-set ID or versioned directory when the paper, images, target references, crop, or normalization changes.

Each target must have a unique stable ID. The manifest must record at least:

- acquisition and workflow modes;
- the user's requested label or figure reference;
- paper identity and page when applicable;
- extracted caption when applicable;
- normalized relative path and PNG media type;
- source and normalized SHA-256 hashes;
- pixel dimensions, DPI, and crop box when applicable;
- whether the caption is included;
- QA status and review notes;
- local-analysis and redistribution status.

Treat the normalized target hash as the target identity used by the report and approval gate. A later bundled or sanitized asset may have a different hash; never substitute that asset hash for the target hash.

## Visual QA

Inspect every target at readable resolution. For paper extractions, inspect the crop overlay against the rendered page.

Mark a target `verified` only when:

- it is the requested figure;
- all panels and panel labels are present;
- all plot legends, color bars, annotations, and axes are present;
- the figure number and complete caption are present when paper extraction is requested;
- no neighboring figure or unrelated prose is included;
- text remains readable and aspect ratio is preserved;
- its file exists and matches the recorded hash.

Use `needs-review` for a plausible but unreviewed target and `rejected` for an incorrect or incomplete target. Do not begin assessment while any requested target is missing, ambiguous, rejected, or unverified.

## Local and public use

The private/local target workspace may retain user-supplied and paper-extracted images for the user's analysis. The normal local decision report must display every verified target so the user can audit what will be reproduced.

Redistribution is a separate question:

- `local` report: embed a sanitized local copy of each target, including a local-analysis-only target; do not expose absolute source paths.
- `public` report: embed target bytes only when redistribution permission is verified. Otherwise omit the bytes and show a rights-boundary notice without leaking filenames, paths, signed URLs, or content.

Never infer redistribution permission from local possession, public web accessibility, a paper subscription, or the right to analyze the work locally.

## Commands

Use the bundled deterministic tool:

The tool requires Python 3.10+, Pillow, and pdfplumber. Paper-reference extraction also requires Poppler's `pdftoppm`. Probe existing environments first; if the open-source dependencies are absent, create a project-local isolated environment within the approved investigation budget rather than modifying a global environment.

```bash
python scripts/materialize_target_figures.py --paper paper.pdf \
  --image fig-1.png --image fig-2.png \
  --uploaded-figure-refs 1,2 --output targets

python scripts/materialize_target_figures.py --paper paper.pdf \
  --figures 1,3,5-8 --output targets

python scripts/materialize_target_figures.py \
  --image target-a.png --image target-b.png --output targets

python scripts/materialize_target_figures.py \
  --verify-manifest targets/manifest.json --verify-targets fig-01,fig-02
```

After visually reviewing the complete set, `--verify-all` is the explicit batch form. Omitting both `--verify-targets` and `--verify-all` is an error; target acquisition never turns an unreviewed set into a verified set by default.

For a reviewed uploaded paper figure that already includes its complete original caption, add `--verified-caption-included`. Automatic PDF extractions record caption inclusion themselves.

If an automatic crop fails QA, replace it through the traceable Phase 0 command and then review it again:

```bash
python scripts/materialize_target_figures.py \
  --replace-manifest targets/manifest.json \
  --replace-target fig-01 \
  --replacement-image reviewed-fig-01.png
```

The tool preserves the first acquisition, normalizes the replacement, refreshes its hashes, records the replacement, and returns the target to `needs-review`. Do not edit a verified normalized image silently.
