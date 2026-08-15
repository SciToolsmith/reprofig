# Customer delivery contract

Use `<skill-root>/scripts/assemble_delivery.py` only after the scientific work is finished. It
creates one customer folder from a fresh whitelist. The folder is the finished work plus the
production materials needed to rerun, edit, or continue it—not a record of Codex's investigation.

```bash
python <skill-root>/scripts/assemble_delivery.py \
  --plan /path/to/delivery-plan.json \
  --output-root /path/to/customer-deliveries
```

Success creates `<output-root>/<slug>-reproduction/` atomically. An existing destination is never
changed. The internal plan is validated but never copied.

## Selection rule

Start with an empty folder and include only:

1. the final result;
2. the final source or editable production file that actually creates it;
3. configuration that source really reads;
4. non-regenerable input data and model files actually required by the route;
5. the smallest dependency or environment declaration needed to rerun it;
6. an additional output only when the user explicitly requested it or needs it independently
   downstream; and
7. licenses and notices required by included third-party material.

Do not deliver environment/license probes, validation JSON, audit manifests, iteration traces,
sensitivity details, QA reports, raw logs, search/download caches, failed drafts, or tables that the
final command deterministically regenerates. They remain transient even when they were important
internally. A file is not customer material merely because it proves that the process occurred.

`inputFiles` and `modelFiles` are conditional, not boilerplate. Include them only when the delivered
route actually reads them and they cannot be reconstructed by the delivered source. For an
image-derived route, the supplied image is an input when rerunning genuinely requires its pixels
and redistribution rights permit inclusion. A paper crop used only for internal comparison is not
an input to a paper-backed mechanism reproduction and normally stays out.

If a large, licensed, private, or otherwise restricted input/model cannot be redistributed, do not
claim that the folder is self-contained. State the exact requirement and fixed source/version in
`dependencyNote` or a material limitation. A small reviewed downloader may be a `sourceFiles`
entry when redistribution terms permit downloading.

## v4 plan

The UTF-8 plan uses `scirepro.delivery-plan/v4`. Older plans are rejected; regenerate them rather
than translating broad evidence buckets into customer roles automatically.

```json
{
  "schemaVersion": "scirepro.delivery-plan/v4",
  "title": "Study figure reproduction",
  "slug": "study-figure",
  "distribution": "local-private",
  "conclusion": "The reported trend is supported within the tested scope.",
  "common": [],
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
          "stage": "method",
          "materialToClaim": true,
          "authorNative": "matlab",
          "selected": "matlab",
          "nativeCapability": "verified",
          "selectionBasis": "author-native",
          "reason": "The author method passed a target-relevant MATLAB smoke test.",
          "evidenceBoundary": null
        }
      ],
      "validationBasis": ["Peak ordering and direction passed the declared checks."],
      "materialAssumptions": ["The unpublished realization was replaced by a fixed seed."],
      "conclusion": "Direction and ordering agree; pointwise identity was not tested.",
      "mainResult": {
        "source": "work/result.png",
        "name": "result.png",
        "rights": "generated"
      },
      "sourceFiles": [
        {"source": "work/reproduce.m", "name": "reproduce.m", "rights": "generated"}
      ],
      "configFiles": [
        {"source": "work/parameters.json", "name": "parameters.json", "rights": "generated"}
      ],
      "inputFiles": [],
      "modelFiles": [],
      "environmentFiles": [],
      "requestedExtras": [],
      "entrypoint": "reproduce.m",
      "rerunArgv": ["matlab", "-batch", "run('reproduce.m')"],
      "rerunOutputs": ["result.png"],
      "dependencyNote": "MATLAB with the target-relevant toolbox named in the source header.",
      "limitations": ["The original random realization was not published."],
      "rights": "The delivered files contain no redistributed paper figure."
    }
  ]
}
```

`mainResult` is the primary customer-facing result. It is normally required and may be `null` only
for blocked/cancelled work or a failed attempt with no useful output. Do not invoke the assembler
for one target when it has neither a result nor reusable production material; return that blocker
in chat. A blocked member of a useful multi-target delivery may still be summarized in the shared
README. Common PNG, JPEG, WebP, and SVG results are embedded in the README; PDF, PPTX, and other
artifacts are linked.

The six artifact roles are deliberately narrow:

- `sourceFiles`: final code, scripts, notebooks, or build source used to produce the result;
- `configFiles`: parameters/configuration actually read by that source;
- `inputFiles`: indispensable, non-regenerable inputs actually read by the route;
- `modelFiles`: weights, checkpoints, vocabularies, or calibration models actually used;
- `environmentFiles`: minimal dependency declarations such as `requirements.txt`, `environment.yml`,
  `pyproject.toml`, `package.json`, `Dockerfile`, `Cargo.toml`, `go.mod`, `pixi.toml`, or a lock
  file—not a probe result or installed-package snapshot;
- `requestedExtras`: additional customer results with purpose `requested-output` or `downstream-use`.

Every array is required and may be empty. `requestedExtras` entries add a required `purpose`; there
is no generic comparison/evidence purpose. Validation records, probes, traces, V0, reference crops,
and other process evidence cannot be relabelled as a result, production material, or requested
extra in the standard customer folder.

An executed scientific target with `complete` or `partial` operational status must deliver at least
one real `sourceFiles` entry and a runnable final `entrypoint`. `entrypoint`, `rerunArgv`,
`rerunOutputs`, and `dependencyNote` occur together. The entrypoint must be one of the target's
delivered source paths and must be invoked by the command. `rerunOutputs` names only the main result
and explicitly requested additional outputs, and must include the main result. Diagnostics and
regenerated tables should require an explicit optional flag and must not appear during the default
rerun.

A completed image-derived or semantic reconstruction may omit a runnable entrypoint only when its
main result is itself an editable production artifact (for example PPTX, SVG, or Draw.io). A lone
raster screenshot is not an editable-source exception.

Single-target deliveries are flat beside `README.md` and may not use `common/`. Multi-target
deliveries use `<target-id>/` directly under the root—not `figures/<target-id>/`. Bytes genuinely
used by at least two distinct targets appear once in `common/` and are referenced as
`{"commonRef":"name.ext"}`. Target IDs may not collide with `common`, `LICENSES`, or `README.md`.
Licenses appear in `LICENSES/` only when required by included third-party material. Empty
directories are never created.

## Scientific consistency remains internal

Keep `route`, operational/validation/claim statuses, `validationBasis`, `materialAssumptions`, and
`stageDecisions` in the plan so the assembler can reject impossible claims and silent native-engine
substitution. The README does not print raw statuses, individual validation checks, probe results,
or internal schema vocabulary. It reports only the conclusion, primary result, rerun command,
required production materials, material assumptions/limits, blockers, and claim-relevant
implementation boundaries.

Scientific status/route rules and stage-decision semantics are unchanged from v3: selected
author-native stages require verified target-relevant smoke tests; a claim-relevant substitution
requires a valid objective or declared fallback and an explicit evidence boundary; image-derived
and semantic targets use `claimStatus: not-applicable`; and `original-case-blocked` requires blocked
execution with validation `not-run`.

## Rights and safety

An artifact contains `source`, one safe output `name`, `rights`, and an optional label. Rights are
`generated`, `included-permitted`, `public-domain`, or `local-only`. A `shareable` delivery accepts
only the first three. Ordinary generated-file boilerplate is not shown in the README. A rights
section appears only when included target material is not generated; required license files are
listed separately.

The assembler preserves the existing fail-closed protections for unsafe names, duplicate
destinations/content, symlinks, special files, secret-shaped text, oversized plans/files, private
local paths, nonportable rerun arguments, rights-incompatible public files, and the internal plan.
ZIP and tar packages are traversed with bounded member/expanded-size limits; nested or unsupported
compressed packages fail closed. It emits no customer manifest or webpage.
