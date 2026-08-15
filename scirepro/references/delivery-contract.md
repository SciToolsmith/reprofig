# Customer delivery contract

Use `<skill-root>/scripts/assemble_delivery.py` only after the scientific work is finished. It
creates one small customer folder from a fresh whitelist. It never copies the transient
workspace, internal plan, probe records, logs, QA tree, or search history.

## Command

```bash
python <skill-root>/scripts/assemble_delivery.py \
  --plan /path/to/delivery-plan.json \
  --output-root /path/to/customer-deliveries
```

Success creates `<output-root>/<slug>-reproduction/` once. Publication is staged and atomic;
an existing destination is never changed.

## Minimum customer set

Begin with no files and add only:

1. the primary result;
2. files that are indispensable to honestly rerun, open, or edit that result and cannot be
   reconstructed from another delivered file;
3. a reference only when rights permit it and direct comparison has customer value;
4. a supporting result only when the user requested it, needs it for downstream use, or it is
   the smallest non-redundant comparison that materially explains the conclusion; and
5. licenses required by included third-party or derivative material.

A file fails this test when it is merely evidence that the internal process occurred. Keep
validation JSON, environment/license probe records, iteration traces, sensitivity details,
raw logs, manifests, QA artifacts, temporary downloads, and tables deterministically regenerated
by the delivered command in the transient workspace by default. Summarize the few facts that
change interpretation in the README. Do not use a fixed file-count ceiling as a substitute for
this value test.

## Internal plan

The UTF-8 plan uses `scirepro.delivery-plan/v3` and is never delivered. v1/v2 plans are rejected;
regenerate them rather than inferring missing customer-value decisions during assembly.

```json
{
  "schemaVersion": "scirepro.delivery-plan/v3",
  "title": "Study figure reproduction",
  "slug": "study-figure",
  "distribution": "local-private",
  "conclusion": "The reported trend is supported; exact pointwise replay was outside scope.",
  "shared": [],
  "licenses": [],
  "targets": [
    {
      "id": "fig-01",
      "title": "Primary response curve",
      "kind": "quantitative",
      "operationalStatus": "complete",
      "validationStatus": "passed",
      "claimStatus": "supported",
      "route": "mechanism-reproduction",
      "stageDecisions": [
        {
          "stage": "input",
          "materialToClaim": true,
          "authorNative": "r",
          "selected": "r",
          "nativeCapability": "verified",
          "selectionBasis": "author-native",
          "reason": "The published R loader reproduced the declared input table.",
          "evidenceBoundary": null
        },
        {
          "stage": "method",
          "materialToClaim": true,
          "authorNative": "matlab",
          "selected": "matlab",
          "nativeCapability": "verified",
          "selectionBasis": "author-native",
          "reason": "The author method passed a target-relevant MATLAB smoke test.",
          "evidenceBoundary": null
        },
        {
          "stage": "visualization",
          "materialToClaim": false,
          "authorNative": "matlab",
          "selected": "python",
          "nativeCapability": "verified",
          "selectionBasis": "declared-fallback",
          "reason": "Python produced the requested portable final graphic.",
          "evidenceBoundary": null
        }
      ],
      "validationBasis": [
        "Peak ordering and response direction meet the declared target checks."
      ],
      "materialAssumptions": [
        "The unpublished realization was replaced by one fixed generated seed."
      ],
      "conclusion": "The declared direction and ordering agree; pointwise identity was not tested.",
      "mainResult": {
        "source": "work/result.png",
        "name": "result.png",
        "rights": "generated"
      },
      "reference": {
        "source": "work/target.png",
        "name": "reference.png",
        "rights": "local-only"
      },
      "rerunFiles": [
        {
          "source": "work/run_pipeline.sh",
          "name": "run_pipeline.sh",
          "rights": "generated"
        },
        {
          "source": "work/load_input.R",
          "name": "load_input.R",
          "rights": "included-permitted"
        },
        {
          "source": "work/method.m",
          "name": "method.m",
          "rights": "included-permitted"
        },
        {
          "source": "work/plot.py",
          "name": "plot.py",
          "rights": "generated"
        },
        {
          "source": "work/parameters.json",
          "name": "parameters.json",
          "rights": "generated"
        }
      ],
      "supportingResults": [],
      "rerunArgv": ["sh", "run_pipeline.sh", "parameters.json"],
      "dependencyNote": "R, MATLAB, and Python with the declared route prerequisites.",
      "limitations": ["The original random realization was not published."],
      "rights": "Generated files are deliverable; the reference is local-private."
    }
  ]
}
```

Single-target files are placed directly in the delivery root beside `README.md`. Multi-target
files use `figures/<target-id>/`; shared bytes appear once in `shared/`, and licenses appear only
when needed in `LICENSES/`. Therefore rerun paths in the internal plan must match the relevant
single- or multi-target layout.

`mainResult` is normally required. It may be `null` only for blocked/cancelled work or a failed
attempt with no useful output. `reference`, `rerunArgv`, `dependencyNote`, and `blocker` are
optional. `rerunFiles` and `supportingResults` are required arrays and may be empty. If rerun files
exist, provide exactly one portable `rerunArgv` and one concise `dependencyNote`; otherwise omit
both.

Each `supportingResults` entry is a normal artifact plus one required purpose:

```json
{
  "source": "work/digitized-series.csv",
  "name": "digitized-series.csv",
  "rights": "generated",
  "label": "Digitized visible series",
  "purpose": "downstream-use"
}
```

Allowed purposes are `requested-output`, `downstream-use`, and `material-comparison`. None means
"keep it just in case." A deterministically regenerated table or machine validation record is not
a supporting result unless the user actually requested it or needs it independently of rerunning.

## Scientific fields

Keep `route`, three statuses, `validationBasis`, and `materialAssumptions` in the internal plan so
the assembler can reject impossible scientific claims. The generated README translates them into
plain language; it does not expose schema vocabulary or repeat a single-target summary table.

Routes are `direct-recompute`, `mechanism-reproduction`, `alternative-validation`,
`image-derived-reconstruction`, `original-case-blocked`, and `semantic-diagram-handoff`.
`validationBasis` names the actual observable/check; any status other than `not-run` requires at
least one. `materialAssumptions` contains only assumptions capable of changing interpretation.
Keep those fields and `limitations` customer-concise (at most 12 one-line entries of 500 characters
each). A `not-run` target needs a concrete blocker.

Executed scientific targets require `stageDecisions`, with one unique entry for each used stage
among `input`, `preprocessing`, `method`, `aggregation`, and `visualization`. This represents a
mixed pipeline directly instead of forcing one target-wide primary engine. Each entry records
whether the stage is material to the tested claim; the author-native engine when one exists; the
actually selected engine and resolved native capability; the selection basis and reason; and an
`evidenceBoundary` when a claim-relevant stage is substituted.
At least one stage in an executed scientific target must be marked `materialToClaim: true`.

Allowed native capabilities are `missing`, `available-untested`, `prerequisites-present`,
`verified`, `authority-required`, `unavailable`, `inconclusive`, and `not-applicable`. A
claim-relevant substitute cannot replace an author-native stage that is available/untested, has
prerequisites present, or is verified unless the objective is explicitly portability or independent
implementation. If native execution is unavailable or inconclusive, `declared-fallback` is valid.
Selecting the author-native engine requires a verified stage smoke test. Replacing a non-material
visualization stage does not change the scientific evidence boundary and creates no customer-facing
README noise. The README reports only substitutions actually material to the tested claim, using
the mandatory `evidenceBoundary` and reason once.

For a stage with no author-native implementation, use `authorNative: null`,
`nativeCapability: not-applicable`, and `selectionBasis: no-author-native`. Blocked scientific
targets and non-scientific image/semantic targets use an empty `stageDecisions` list.

Every top-level `shared` artifact must be referenced by at least one target; `shared` is not an
escape hatch for internal archives. Obvious file paths in `rerunArgv`, including MATLAB/Simulink
files such as `.m`, `.mlx`, `.p`, and `.slx`, must resolve to whitelisted delivery files. An
author-native stage may never use `nativeCapability: not-applicable`.

Scientific targets use this consistency matrix:

| Claim | Operational | Validation |
|---|---|---|
| `supported` | `complete` | `passed` |
| `partially-supported` | `complete` or `partial` | `partially-passed` |
| `unsupported` | `complete` | `failed` |
| `inconclusive` | attempted | `inconclusive` |
| `not-tested` | truthful untested state | `not-run` |

Image-derived and semantic targets use `claimStatus: not-applicable`; their validation concerns
visible reconstruction or editability, never a paper claim. `original-case-blocked` requires
blocked execution and `not-run` validation.

## Artifacts, rights, and safety

An artifact contains `source`, one safe output `name`, `rights`, and an optional human `label`.
Rights are `generated`, `included-permitted`, `public-domain`, or `local-only`. A `shareable`
delivery accepts only the first three. A paper PDF or crop with uncertain rights stays out; cite it
in the conclusion instead.

Top-level `shared` and `licenses` use the same artifact form. If targets need identical bytes,
copy them once into `shared` and use `{"sharedRef":"name.ext"}`. Duplicate content is rejected.
Empty directories are never created.

The assembler rejects unsafe names, duplicate destinations/content, symlinks, special files,
secret-shaped text, oversized plans/files, private local paths, nonportable rerun arguments,
rights-incompatible public files, and attempts to copy the internal plan. ZIP and tar packages are
traversed within bounded member and expanded-size limits: every regular member is scanned;
sensitive names, duplicate/traversing/absolute paths, links, and special members fail closed. Other
compressed formats and nested compressed members are rejected rather than copied without inspection.
Customer-visible prose and labels reject local absolute paths while preserving ordinary HTTP(S)
links. It emits no customer manifest or webpage.
