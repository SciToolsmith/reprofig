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

The tool validates the target-manifest canonical hash, target bytes, and `qaStatus: verified`. A report requires that manifest; an approval requires both; a supplied gate result requires all three. Approval initialization reruns `plan_gate.py`, requires the supplied result to equal the fresh result, selects exactly the gate-bound targets, and resolves `approval.outputPolicy.relativeRoot` below `--workspace-root`. It cannot be redirected elsewhere. Final validation independently reconstructs that authority: selected figure/target/route, parameter values, deliverables, authorized effects, and required acknowledgements must agree exactly across the archived report, approval, gate result, and target manifest. Recomputing file, inventory, gate, or manifest hashes cannot turn an undeclared parameter/effect into approved authority. Every existing component below the resolved workspace root is checked with `lstat`; a symlinked ancestor is rejected before any staging directory is created. `complete` and `partial` bundles require a successful gate; blocked, failed, and cancelled diagnostic bundles may be initialized without one.

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

For `complete` or `partial`, `--result-report` is required. Approval always binds the exact local Phase 1 report shown before execution. A `local-private` result therefore supplies that same built report and must match its approved SHA-256. A `shareable` result supplies a separately built public report from the same Phase 1 source and verified target manifest. Its exact report hash differs because audience-only metadata, local filenames, and restricted target pixels are removed; the finalizer compares an audience-neutral decision digest so every scientific statement, candidate route, parameter, assumption, permission, cost, and target identity must still match the approved local report. This permits rights-safe sharing without weakening the local approval gate. The finalizer checks the complete report inventory and audience, copies it to `report/decision/`, then generates `report/index.html` and `report/run-results.json` from terminal per-target results and validation records.

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
        ├── adjustments.json                    # required after a complete/partial figure run
        ├── reference/
        │   └── target.png                      # conditional normalized target
        ├── outputs/                            # conditional; required complete/partial
        │   ├── baseline-v0.<image>             # required complete/partial baseline
        │   ├── calibrated-v1.<image>           # conditional scientific correction
        │   └── final-v2.<image>                 # conditional presentation/quality correction
        ├── validation/
        │   ├── summary.json                    # required, even if not-run
        │   ├── metrics.json                    # conditional
        │   ├── difference-summary.json         # required complete/partial comparison record
        │   ├── visual-quality-check.json       # required complete/partial plot QA
        │   └── comparisons/
        │       ├── original-vs-v0.<image>      # required complete/partial comparison
        │       └── original-vs-final.<image>   # required when selected output is not V0
        ├── derived/                            # conditional image-derived data
        ├── code/                               # conditional target-only code
        └── logs/                               # conditional target-only logs
```

Do not create empty conditional directories. Put an artifact used by two or more targets in `shared/` and reference it from each target result; do not copy it into every target. Keep target-specific artifacts under that target. Use descriptive lowercase names such as `reproduced-figure.png`, `digitized-series.csv`, and `overlay.png`; use `-001` only for true sequences. Avoid `final-final`, `new`, `misc`, and `tmp`.

## Bounded comparison and calibration

Preserve the first runnable figure as `outputs/baseline-v0.<image>`, where `<image>` is PNG, JPEG, SVG, or WebP. PDF is not a versioned figure format in this contract; include a PDF only as an additional declared deliverable. V0 must reflect the verified route before tuning toward the published appearance; never overwrite it. Compare it with the normalized target and record axes, units and scale; trends, peaks and magnitude; colors, line styles and legends; and layout and typography. Treat pixel similarity as diagnostic evidence, never as the scientific objective.

Each comparison is an object rather than a bare path. It binds `comparisonId`, the compared `output`, `mode`, `artifact`, and `targetPixelRights`. `side-by-side` means the artifact contains target pixels and therefore requires `{included: true, sourceId, redistributionStatus}` matching a declared target source. A shareable bundle accepts those pixels only when their status is `permitted`, `public-domain`, or `generated`. When that authority is unavailable, use `metrics-only`: the comparison image contains generated metrics/trends but no target pixels, and rights must be exactly `{included: false, sourceId: null, redistributionStatus: "not-included"}`. This makes a useful shareable comparison possible without redistributing the paper figure.

By default, perform at most two adjustment rounds:

1. `calibrated-v1.<image>` is conditional. Use it only for a scientifically justified correction or sensitivity test arising from the V0 difference diagnosis. Scientific change domains are input, data, formula, preprocessing, algorithm, parameter, randomization, numerical behavior, axis scale, unit conversion, and scientific range selection. Every change records subject, before, after, reason, and at least one diagnosis reference, evidence reference, or scientific basis. A palette, legend, typography, or other visual reason cannot justify V1.
2. `final-v2.<image>` is conditional. Use it only after the scientific interpretation is stable, for axis labels, tick formatting, palette, line/marker styles, legend, typography, layout, export quality, clipping/overlap, contrast, and readability. Axis scale (`linear`/`log`), unit conversion, and truncating or expanding the scientific range belong in V1 because they can alter interpretation. V2 cannot change inputs, data, formulae, preprocessing, algorithm behavior, parameters, randomness, numerical settings, scientific units, scales, or range. Do not reproduce a defect in the published figure when a clearer rendering preserves its meaning.

If a round is unnecessary, omit both its file and its round record; do not create placeholders. Stop when the scientific acceptance criteria pass, remaining differences are non-critical, another iteration would improve only appearance/pixel similarity, or two rounds produce no new testable explanation. A third or later round is permitted only for a new testable scientific hypothesis and must include a matching `validation/calibration-round-<n>-approval.json` using `scirepro.calibration-approval/v2`. It binds a unique `approvalId` and `idempotencyKey`, exact `targetId`, integer `round`, `decision: approve`, exact `hypothesis`, timezone-aware `approvedAt`, the prior output path and SHA-256, and a bounded `maxAttempts` from 1 to 10. Its output is `outputs/calibrated-v<n>.<image>`. Reusing an approval or changing the prior output invalidates it.

A complete or partial target records this set in `result.json.calibration`:

- `baselineV0`, nullable `scientificV1`, nullable `presentationV2`, and `selectedOutput`;
- `comparisons`, including structured `original-vs-v0` and, when a calibrated version is selected, `original-vs-final` records;
- `differenceSummary`, `visualQualityCheck`, and `adjustments` bundle-relative paths.

`difference-summary.json` uses `scirepro.difference-summary/v2`. It binds `targetId`, `baseline`, `selected`, a concise assessment for `axesUnitsScale`, `trendsPeaksMagnitude`, `colorsLinesLegends`, and `layoutTypography`, plus `scientificConclusion` and `remainingDifferences`. `visual-quality-check.json` uses `scirepro.visual-quality-check/v2` and records `status`, checks for `textOverlap`, `legendDataOverlap`, `clipping`, `contrast`, and `readability`, plus `issuesRemaining`. `adjustments.json` uses `scirepro.adjustments/v2`; it binds `targetId`, ordered performed `rounds`, `selectedOutput`, and a non-empty `stopReason`. Round numbers are strict integers (JSON booleans are invalid). Round records contain only the declared fields, and every change is a non-empty typed object following the V1/V2 separation above.

`result.json.outputs[]` and `validation/summary.json.artifacts[]` contain existing bundle-relative POSIX paths. They cannot be absolute paths or prose objects. A target may reference only its own `outputs/`, `derived/`, `code/`, or declared `shared/` artifacts; validation may additionally reference its own `validation/` files. Parent traversal, another target's directory, and missing files are rejected.

## Three independent result dimensions

Never collapse execution, validation, and scientific interpretation into one success flag.

- Operational status: `complete`, `partial`, `failed`, `blocked`, or `cancelled`.
- Validation status: `passed`, `partially-passed`, `failed`, `inconclusive`, or `not-run`.
- Claim status: `supported`, `partially-supported`, `unsupported`, `inconclusive`, `not-tested`, or `not-applicable`.

An image-derived reconstruction must use claim status `not-applicable`. A completed target must have validation other than `not-run`. A failed command does not by itself show that a paper claim is unsupported.

A complete or partial target must contain generated output, captured environment information, traceable sources, and a `resource-usage.json` whose `measurementStatus` is `recorded` or `partial`. Record at least one non-negative measurement (for example wall time, peak memory, disk, network, or a structured cost value); do not leave a completed run as `not-recorded`. A complete or partial bundle must also contain the validated, updated result report described above. `supported` requires a complete scientific run with passed validation. The other claim states have similarly constrained execution/validation combinations. Aggregate bundle status must agree with all per-target operational states.

For scientific complete/partial results, preserve neutral evidence language. A negative or unexplained result may be labelled a **potential research-integrity concern** after ordinary implementation, data, environment, randomness, and numerical explanations have been checked. `result.summary` and `difference-summary.json.scientificConclusion` must not directly accuse authors of fabrication, falsification, fraud, or misconduct; external allegations require a separate future workflow and explicit authorization.

## Manifest and integrity

`manifest.json` uses `scirepro.run-bundle/v2`. Target results, validation summaries, result reports, difference/quality/adjustment records, and calibration approvals likewise use their `scirepro.*/*v2` schemas. The previous v1 run-bundle/calibration records are not silently upgraded: regenerate them with the current finalizer. Phase 0/1 report namespaces such as `reprofig.report/v3` remain unchanged. The manifest binds run ID, timestamps, terminal status, target and approval-gate scope, distribution class, and a sorted file inventory. Every regular file except `manifest.json` itself appears exactly once with its bundle-relative path, role, media type, byte size, and SHA-256. A canonical self-hash covers manifest metadata. Validation rejects missing, extra, changed, absolute, parent-traversing, symlinked or special-file content, empty directories, README disagreement, and plan/target metadata tampering.

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
