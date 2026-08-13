# Final result folder

SciRepro has one persistent output format: `scirepro-run-<run-id>/`. It is a
post-execution evidence bundle, not a permission system. Safe, bounded local work
may begin after the route is reasoned through; do not create an execution contract,
gate result, approval receipt, or webpage first.

Use the finalizer rather than handcrafting a manifest:

```bash
python <skill-root>/scripts/finalize_run_bundle.py init \
  --output-root <parent> \
  --run-id <run-id> \
  --target-manifest <targets/manifest.verified.json>

# Execute only inside the printed .scirepro-run-<run-id>.staging directory.

python <skill-root>/scripts/finalize_run_bundle.py finalize \
  --bundle <staging-directory> \
  --status <complete|partial|failed|blocked|cancelled>

python <skill-root>/scripts/finalize_run_bundle.py validate \
  --bundle <parent>/scirepro-run-<run-id>
```

The finalizer rejects replacement of an existing destination, symlinks, special
files, unsafe paths, secret-like content, unverifiable hashes, rights violations,
and undeclared inventory changes. It publishes the validated folder atomically.

## Minimal executed-target record

Each `targets/<target-id>/result.json` records only the evidence needed to
understand and rerun that target:

- verified target identity and target SHA-256;
- that target's route and engine (different targets may use different engines);
- route kind, tested claim, unsupported claims, assumptions, and remaining discrepancies;
- the exact command as an argv array and a bundle-relative working directory;
- SHA-256 records for the actual source, input, code, configuration, and
  environment used by that command;
- the untouched first runnable output, `baselineV0`, or a terminal blocker when
  no useful V0 exists;
- acceptance criteria and results;
- independent operational, validation, and scientific-claim statuses.

An included frozen artifact is re-hashed from the bundle. A lawfully omitted
restricted artifact still needs its known hash, a non-secret locator, and
`omitted-restricted` rights status. Never substitute a convenient file for the
scientific input that was actually executed.

Record facts, not placeholder files. Every executed route includes its executable
code/implementation and target environment. Source, input, and configuration are
included only when the route actually uses them. An absent optional role needs a
`roleDispositions` entry with `status: not-applicable`, a reason, and a route
binding; a restricted real artifact instead uses `omitted-restricted`, a reason,
known hash, and formal locator. When one real artifact legitimately serves two
roles, declare `roleAlias` plus a scientific justification—the finalizer verifies
that both roles bind the same path and hash. Silent role substitution is invalid.

Keep target-specific files in their matching `sources/`, `inputs/`, `code/`,
`config/`, or `environment/` domain; only genuinely shared source/input/code/config
artifacts may use the corresponding `shared/` domain. A target image may be the
source evidence for an image-derived route. The target environment snapshot and
the shared environment record must both name the exact route engine/version used.
Every source record carries compact authority, version, license, and rights
provenance; an inapplicable source is explained through `roleDispositions`.

Persist only bundle-relative command paths. Absolute macOS/Linux paths, Windows
drive or UNC paths, home-relative paths, credential-bearing flags, bearer values,
and secret-shaped tokens make the bundle invalid. Use a public formal locator for
a lawfully omitted artifact; never turn a local path into a locator.

Calibration, comparisons, visual QA, V1, and V2 are conditional. Add them only
when a mismatch or presentation defect makes them useful. V0 is never overwritten.
Every output, including V0 and the selected output, belongs under that target's
`outputs/` directory. A scientific-reproduction output must not be the reference
image or a byte-for-byte copy.

## Layout

```text
scirepro-run-<run-id>/
├── README.md
├── manifest.json
├── shared/
│   ├── targets/manifest.json              # when target acquisition supplied one
│   ├── environment/environment.json
│   └── execution/resource-usage.json
└── targets/
    └── <target-id>/
        ├── result.json
        ├── reference/target.png            # rights permitting
        ├── inputs/                          # when bundled
        ├── code/                            # when target-specific
        ├── config/                          # when target-specific
        ├── outputs/baseline-v0.<format>
        ├── validation/                      # when performed
        └── logs/                            # when useful and secret-free
```

Create no empty optional directories. Shared artifacts belong under `shared/`
only when multiple targets use them.

## Status and resource truthfulness

Operational completion, acceptance/validation, and claim support answer different
questions and must not be collapsed into one verdict. An image-derived route always
uses `claimStatus: not-applicable`.

For scientific reproduction, the finalizer enforces one conservative status matrix:
`supported` requires operational `complete` with validation `passed`;
`partially-supported` requires operational `complete` or `partial` with validation
`partially-passed`; `unsupported` requires operational `complete` with validation
`failed`; and `inconclusive` requires an actual execution with operational
`complete`, `partial`, or `failed` and validation `inconclusive`. `not-tested` and
validation `not-run` imply each other. The first four claim outcomes require a
validated execution trace; a pre-execution blocker or absent validation cannot
become a scientific conclusion.

Resource caps must say whether they were `declared-only` or
`technically-enforced`; only the latter may name an enforcement mechanism. Measured
usage is recorded separately with its measurement method. A requested cap is not
evidence that the operating system enforced it.

If work is blocked before execution and there is no durable artifact worth keeping,
give the concise reason in chat and create no ceremonial folder. A blocked bundle is
appropriate only when the preserved target, source finding, or diagnostic record is
itself useful.
