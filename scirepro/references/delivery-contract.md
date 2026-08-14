# Customer delivery contract

Use `<skill-root>/scripts/assemble_delivery.py` only after the scientific work is finished. It creates a
small customer folder from an explicit internal whitelist; it does not copy the transient
workspace, a report site, a log tree, or the plan itself.

## Contents

- [Command](#command)
- [Plan](#plan)
- [Artifact entries](#artifact-entries)
- [Customer layout](#customer-layout)
- [Selection rule](#selection-rule)

## Command

```bash
python <skill-root>/scripts/assemble_delivery.py \
  --plan /path/to/delivery-plan.json \
  --output-root /path/to/customer-deliveries
```

The only successful output is `<output-root>/<slug>-reproduction/`. Publication is
create-only. The assembler writes a sibling staging directory, validates it, and performs an
atomic no-replace rename. It never updates or repairs an existing delivery.

## Plan

The UTF-8 JSON plan uses `scirepro.delivery-plan/v2` and remains internal:

Plans using `scirepro.delivery-plan/v1` lack route and scientific-basis fields and are
intentionally rejected; regenerate the internal plan rather than inferring those facts during
assembly. Existing customer folders need no migration.

```json
{
  "schemaVersion": "scirepro.delivery-plan/v2",
  "title": "Study figure reproduction",
  "slug": "study-figures",
  "distribution": "local-private",
  "conclusion": "The declared trend and ordering are supported; exact pointwise replay was outside scope.",
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
      "validationBasis": [
        "Peak ordering and response direction agree with the declared target observables."
      ],
      "materialAssumptions": [
        "The unpublished random realization was replaced by a fixed generated seed."
      ],
      "conclusion": "The declared direction and ordering agree; pointwise identity was not an acceptance criterion.",
      "mainResult": {
        "source": "work/result.png",
        "name": "result.png",
        "rights": "generated"
      },
      "reference": {
        "source": "work/target.png",
        "name": "target.png",
        "rights": "local-only"
      },
      "implementation": [
        {
          "source": "work/reproduce.py",
          "name": "reproduce.py",
          "rights": "generated"
        }
      ],
      "parameters": [
        {
          "source": "work/parameters.json",
          "name": "parameters.json",
          "rights": "generated"
        }
      ],
      "evidence": [
        {
          "source": "work/evidence.csv",
          "name": "evidence.csv",
          "rights": "generated"
        }
      ],
      "dependencies": [
        {
          "source": "work/requirements.txt",
          "name": "requirements.txt",
          "rights": "generated"
        }
      ],
      "rerunArgv": [
        "python3",
        "figures/fig-01/reproduce.py",
        "--config",
        "figures/fig-01/parameters.json"
      ],
      "limitations": ["The original random realization was not published."],
      "rights": "Generated files are deliverable; the paper crop is private reference only."
    }
  ]
}
```

`reference`, `dependencyNote`, `rerunArgv`, and `blocker` are optional. The four artifact-list
fields may be empty. `route`, `validationBasis`, and `materialAssumptions` are required plan
fields but add no customer artifact. Keep each list item to one short statement:

- `route` identifies what was actually done: `direct-recompute`, `mechanism-reproduction`,
  `alternative-validation`, `image-derived-reconstruction`, `original-case-blocked`, or
  `semantic-diagram-handoff`;
- `validationBasis` names the tested observable and check that supports the validation status,
  such as trend, peak location, numeric tolerance, visible geometry, or editability; and
- `materialAssumptions` records only assumptions capable of changing interpretation. Use an
  empty list when none were material; never invent an assumption to fill the field.

Every validation result other than `not-run` needs at least one `validationBasis` item. A
`not-run` target may keep that list empty but must provide a concise `blocker`. Do not require a
separate evidence file merely to restate these fields. If `implementation` is nonempty, provide
exactly one `rerunArgv` and either a dependency artifact or one concise `dependencyNote`, such
as `Python standard library only.` If implementation is empty, omit the command. Re-run
arguments are interpreted from the delivery root and must use portable relative paths.

`mainResult` is normally required. It may be `null` only for a `blocked` or `cancelled` target,
or a failed attempt that produced no useful artifact. The README reports `No result`; the
assembler does not create a fake placeholder or an empty target directory. Complete and
partial targets must provide a real main result.

Allowed target kinds are `quantitative`, `image-derived`, `semantic-diagram`, and `other`.
Operational, validation, and scientific-claim statuses are deliberately separate. Do not
upgrade a claim merely because a program ran or a visual check passed. Quantitative and other
scientific targets use this compact consistency matrix:

| Claim | Operational | Validation |
|---|---|---|
| `supported` | `complete` | `passed` |
| `partially-supported` | `complete` or `partial` | `partially-passed` |
| `unsupported` | `complete` | `failed` |
| `inconclusive` | attempted: `complete`, `partial`, or `failed` | `inconclusive` |
| `not-tested` | any truthful operational state | `not-run` |

`not-tested` and `not-run` occur together. Image-derived reconstructions and semantic diagrams
use `claimStatus: not-applicable`; their validation status describes reconstruction or
editability checks, not support for a scientific claim. For those targets, `passed` requires
complete execution; `partially-passed` requires complete or partial execution; `failed` and
`inconclusive` require a real attempt; and `not-run` is reserved for blocked, cancelled, or
failed-before-validation work. The generated README inserts the appropriate evidence-boundary
statement automatically.

Keep route ownership consistent with the target. Quantitative and other scientific targets use
the three scientific execution routes or `original-case-blocked`; image-derived targets use
`image-derived-reconstruction` or `original-case-blocked`; semantic diagrams use
`semantic-diagram-handoff`. `original-case-blocked` requires blocked execution and `not-run`
validation. These checks prevent a status-only success from hiding what was actually tested,
without forcing a larger report or evidence bundle.

## Artifact entries

A copied artifact is an explicit whitelist entry:

```json
{
  "source": "internal/path/to/file",
  "name": "customer-name.ext",
  "rights": "generated",
  "label": "Optional human label"
}
```

`source` may be absolute or relative to the plan. `name` is one safe basename, not a path.
Rights must be one of:

- `generated`
- `included-permitted`
- `public-domain`
- `local-only`

Every file in a `shareable` delivery must use the first three statuses. A paper PDF or crop
with uncertain rights stays out of a shareable plan; cite it in the human conclusion instead.

Top-level `shared` and `licenses` entries use the same artifact form and become `shared/` and
`LICENSES/`. These directories are omitted when empty.

When multiple targets need identical bytes, copy them once in `shared` and refer to the
canonical output name instead of adding another source:

```json
{"sharedRef": "common-requirements.txt", "label": "Shared Python dependencies"}
```

`sharedRef` may appear wherever a target artifact appears. Any repeated SHA-256 among copied
entries is rejected rather than silently duplicated. A target directory is created only when
that target has a local copied artifact; blocked or shared-only targets do not create empty
directories and remain fully represented in the README.

## Customer layout

```text
<slug>-reproduction/
├── README.md
├── figures/
│   ├── fig-01/
│   └── fig-02/
├── shared/       # only when declared and nonempty
└── LICENSES/     # only when declared and nonempty
```

The generated README leads with the overall conclusion, links every main result, keeps the
three statuses distinct, and concisely states each target's route, validation basis, material
assumptions, blocker when applicable, limitations, and rights. It contains one shell-quoted
copyable command for each executable target.

The assembler never inventories the delivery and never emits a manifest. Adding `.DS_Store`
or another customer-side file later therefore cannot invalidate an immutable file list.

## Selection rule

Whitelist only files that help the customer understand, inspect, edit, or rerun the result:

- the main result and, when permitted, its reference;
- the implementation, actual parameters or configuration used, actionable dependencies, and smallest evidence that
  supports the final conclusion;
- shared inputs or source actually used; and
- applicable license notices.

Do not include intermediate webpages, route-search material, raw logs, temporary downloads,
QA overlays, renderer dumps, old revisions, or machine inventories. A log, QA result, or data
manifest may enter only when intentionally placed in `evidence` because it is itself necessary
customer evidence.

The assembler rejects unsafe names, duplicate destinations, duplicate content, symlinks,
special files, secret-shaped text (including inspected text members inside ZIP-based Office
packages), oversized plans/files/deliveries, nonportable re-run paths, private user-directory
paths in customer prose or commands, and rights-incompatible shareable files.
