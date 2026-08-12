# Final run-bundle contract

Phase 2 produces exactly one terminal directory named `scirepro-run-<run-id>/`. The directory is the unit to inspect, archive, rerun, or share. Do not leave generated code, logs, figures, downloads, or reports beside it.

Use `<skill-root>/scripts/finalize_run_bundle.py`; do not handcraft `manifest.json`. The tool creates a hidden sibling staging directory, inventories every regular file, validates the result, and atomically renames it only after the bundle is terminal and consistent.

## Lifecycle

Initialize before execution:

```bash
python <skill-root>/scripts/finalize_run_bundle.py init \
  --output-root <output-parent> \
  --workspace-root <approved-workspace> \
  --run-id <run-id> \
  --report <report.json> \
  --target-manifest <targets/manifest.verified.json> \
  --approval <approval.json> \
  --gate-result <gate-result.json>
```

When a verified target manifest is supplied, omit `--target` to initialize every manifest target or repeat it to select a subset. Without a manifest/report, provide one or more `--target` values explicitly. Single- and multi-target runs always use the same `targets/<target-id>/` layout. An independent image-derived target may be declared as `--target <target-id>=image-derived-reconstruction`.

The tool validates the target-manifest canonical hash, target bytes, and `qaStatus: verified`. A report requires that manifest; an approval requires both; a supplied gate result requires all three. Approval initialization reruns `plan_gate.py`, requires the supplied result to equal the fresh result, selects exactly the gate-bound targets, and resolves `approval.outputPolicy.relativeRoot` below `--workspace-root`. It cannot be redirected elsewhere. `complete` and `partial` bundles require a successful gate; blocked, failed, and cancelled diagnostic bundles may be initialized without one.

Only selected plan records and normalized selected targets are copied during initialization; the Phase 0 workspace, paper, archives, and datasets are not copied wholesale. A `local-private` bundle keeps each normalized target at `targets/<target-id>/reference/target.png`. A `shareable` bundle includes it only with redistribution authority and otherwise records it in `omissions.json`.

Write only inside the printed `.scirepro-run-<run-id>.staging/` directory. Then finalize:

```bash
python <skill-root>/scripts/finalize_run_bundle.py finalize \
  --bundle <staging-directory> \
  --status complete \
  --result-report <phase-1-web-report-directory>

python <skill-root>/scripts/finalize_run_bundle.py validate \
  --bundle <output-parent>/scirepro-run-<run-id>
```

For `complete` or `partial`, `--result-report` is required. Supply the built Phase 1 web-report directory that was shown before execution. The finalizer validates that its report hash matches the approved report, checks its complete file inventory and local/public audience, copies it to `report/decision/`, then generates `report/index.html` and `report/run-results.json` from the terminal per-target result and validation records. The result page therefore shows actual Phase 2 outcomes instead of presenting the unchanged decision report as a result.

If execution cannot start or terminates early, still finalize the bundle. `failed`, `blocked`, and `cancelled` may terminalize pending targets when a concise `--reason` is supplied. They may omit `--result-report`; do not create an empty or misleading page merely to satisfy layout. They may include one when a useful decision report already exists. This preserves evidence and diagnostics without pretending that validation ran.

The staging state fixes ordered target IDs, workflow modes, target hashes, distribution class, and plan bindings. Renaming or replacing targets is rejected. Every tree member is checked with `lstat` before content is read; symlinks, FIFOs, sockets, and devices are rejected without opening them.

## Required and conditional layout

```text
scirepro-run-<run-id>/
├── README.md                                  # required human entry point
├── manifest.json                              # required; generated, never hand-edited
├── report/                                    # required for complete/partial; optional diagnostics
│   ├── index.html                             # generated terminal result page
│   ├── run-results.json                       # result/validation bindings
│   └── decision/                              # validated Phase 1 web report
├── shared/
│   ├── plan/                                  # conditional Phase 0/1 records
│   │   ├── report.json
│   │   ├── target-manifest.json
│   │   ├── approval.json
│   │   └── gate-result.json
│   ├── provenance/
│   │   ├── sources.json                       # required
│   │   └── omissions.json                     # conditional rights/size omissions
│   ├── environment/
│   │   ├── environment.json                   # required
│   │   └── lockfiles/                         # conditional
│   ├── execution/
│   │   ├── resource-usage.json                # required
│   │   ├── commands.jsonl                     # conditional when commands ran
│   │   └── run.log                            # conditional
│   ├── code/                                  # conditional code shared by targets
│   ├── config/                                # conditional shared configuration
│   ├── patches/                               # conditional minimal overlays/diffs
│   └── artifacts/                             # conditional shared generated artifacts
└── targets/
    └── <target-id>/
        ├── result.json                         # required
        ├── reference/
        │   └── target.png                      # conditional normalized target
        ├── outputs/                            # conditional generated figures/data
        ├── validation/
        │   ├── summary.json                    # required, even if not-run
        │   ├── metrics.json                    # conditional
        │   └── comparisons/                    # conditional overlays/diffs
        ├── derived/                            # conditional image-derived data
        ├── code/                               # conditional target-only code
        └── logs/                               # conditional target-only logs
```

Do not create empty conditional directories. Put an artifact used by two or more targets in `shared/` and reference it from each target result; do not copy it into every target. Keep target-specific artifacts under that target. Use descriptive lowercase names such as `reproduced-figure.png`, `digitized-series.csv`, and `overlay.png`; use `-001` only for true sequences. Avoid `final-final`, `new`, `misc`, and `tmp`.

`result.json.outputs[]` and `validation/summary.json.artifacts[]` contain existing bundle-relative POSIX paths. They cannot be absolute paths or prose objects. A target may reference only its own `outputs/`, `derived/`, `code/`, or declared `shared/` artifacts; validation may additionally reference its own `validation/` files. Parent traversal, another target's directory, and missing files are rejected.

## Three independent result dimensions

Never collapse execution, validation, and scientific interpretation into one success flag.

- Operational status: `complete`, `partial`, `failed`, `blocked`, or `cancelled`.
- Validation status: `passed`, `partially-passed`, `failed`, `inconclusive`, `not-run`, or `not-applicable`.
- Claim status: `supported`, `partially-supported`, `unsupported`, `inconclusive`, `not-tested`, or `not-applicable`.

An image-derived reconstruction must use claim status `not-applicable`. A completed target must have validation other than `not-run`. A failed command does not by itself show that a paper claim is unsupported.

A complete or partial target must contain generated output, captured environment information, and traceable sources. A complete or partial bundle must also contain the validated, updated result report described above. `supported` requires a complete scientific run with passed validation. The other claim states have similarly constrained execution/validation combinations. Aggregate bundle status must agree with all per-target operational states.

## Manifest and integrity

`manifest.json` uses `scirepro.run-bundle/v1`. It binds run ID, timestamps, terminal status, target and approval-gate scope, distribution class, and a sorted file inventory. Every regular file except `manifest.json` itself appears exactly once with its bundle-relative path, role, media type, byte size, and SHA-256. A canonical self-hash covers manifest metadata. Validation rejects missing, extra, changed, absolute, parent-traversing, symlinked or special-file content, empty directories, README disagreement, and plan/target metadata tampering.

Do not use absolute local paths in persisted bundle references. Use bundle-relative paths, public URLs, durable identifiers, hashes, or a non-sensitive locator description.

## Rights profiles

- `local-private` is for local research. Inclusion does not assert redistribution rights. Do not silently copy an entire paper, restricted dataset, author archive, model, or proprietary font merely to make the bundle self-contained.
- `shareable` may contain generated material and sources whose redistribution status is `permitted`, `generated`, or `public-domain`. Every non-contract artifact must be referenced as generated output/validation evidence or declared through `sources.json`; arbitrary files are rejected. Text is screened for obvious local absolute paths, secret assignments, private-key blocks, and suspicious secret filenames.

Record excluded resources in `shared/provenance/omissions.json` with identity, version, hash when known, size, license/access state, reason for omission, and lawful retrieval instructions. Record included and external sources in `sources.json`. Never hide a rights-sensitive copy under an uninformative filename.

## Minimum terminal record

Even a blocked or failed run contains:

- a README explaining outcome, rerun path, limits, and blocker;
- environment, sources, and resource-use records, using explicit `not-recorded` states where necessary;
- one `result.json` and validation `summary.json` per target;
- the plan/approval evidence that exists;
- errors and logs that help distinguish missing input, unavailable software, execution failure, validation failure, and contrary evidence;
- a validator-generated manifest.

The terminal directory is a terminal tamper-evident snapshot. Start a new run ID for another attempt rather than modifying a finalized bundle.
