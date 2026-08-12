---
name: scirepro
description: Analyze, assess, and reproduce one or many scientific figures through an evidence-first, report-before-execution workflow. Use when Codex receives a paper with uploaded target images, a paper with figure references that must be acquired, or target images alone for explicitly limited image-derived reconstruction. Interpret what each target shows, reconstruct its data-to-figure chain, investigate only relevant code/data/environments, present a local report containing the target images, obtain scope-bound approval, then execute and validate approved routes. Route scientific flowcharts and conceptual schematics to sci-diagram-pptx when available.
---

# SciRepro

## Invariants

- Accept one or many targets; keep a stable ID, hash, mode, assessment, and result for each.
- Use one of three entry paths: paper + uploaded images, paper + figure references, or images only.
- Assign each target one mode: `scientific-reproduction` with reliable paper context, otherwise `image-derived-reconstruction`.
- Never present tracing, digitization, or visual fitting as reproduction of the original data, method, experiment, or claim.
- Define target observables and acceptance criteria before route selection or execution. Visual similarity and exit code alone are not scientific validation.
- Preserve provenance and never silently change the target, input, algorithm, mode, reproduction level, claim, or approved effects.
- For an actual reproduction request, show a local decision report before execution. The report must display every target admitted to assessment.
- Prefer compatible existing environments. Create only project-local open-source environments within budget; never silently install proprietary software, accept terms, log in, purchase access, upload private artifacts, or contact third parties.

## Choose the smallest sufficient workflow

1. **Explain or assess** — answer a read-only question about meaning, generation logic, missing evidence, or likely feasibility. Materialize targets only when identity must be stabilized. Do not invent an approval ceremony or execute a reproduction.
2. **Compact local report** — use for an actual reproduction with verified targets, one clear low-risk route, bounded local R0/R1 effects, and no unresolved access, license, privacy, proprietary-runtime, or large-resource issue. Keep evidence and alternatives concise; export a scope-bound approval receipt before execution.
3. **Full audited report** — use when source retrieval or installation is needed, routes compete, evidence is uncertain, a target is blocked, or any R2/R3 action, proprietary tool, large resource, private artifact, publication, or redistribution is involved. Use the full investigation and approval fields.

Do not lower scientific standards in a compact report; lower only ceremony and irrelevant detail. A user request to “start now” does not bypass report-first execution, but a compact report may require only one short confirmation or exported receipt.

## Phase 0 — Acquire and verify targets

Create a dedicated `targets/` workspace with byte-preserved `originals/`, normalized targets in `figures/`, QA evidence in `qa/`, and `manifest.json`. Use `scripts/materialize_target_figures.py`, not scattered screenshots. Resolve scripts relative to this skill directory and use absolute task paths.

- **Paper + uploaded images:** preserve all images; match each to paper identity, caption, panels, and nearby text before assigning scientific mode.
- **Paper + references:** accept one or many labels. Numeric lists/ranges may use automatic extraction; labels such as `Fig. 2a`, `S3`, `Extended Data 4`, `图 5`, or other free text remain opaque identifiers and may require a reviewed manual crop.
- **Images only:** preserve and normalize every image; visible evidence may support image-derived reconstruction or appearance fitting, but not a paper claim.

If automatic acquisition cannot represent or safely crop a target, add a reviewed user/manual crop through the traceable acquisition path, retain its original label and paper/page/caption binding when known, and keep it pending until identity and hash are verified. Never coerce a free-text label into the wrong number or silently edit a normalized target.

Visually inspect readable targets and QA overlays. A target is `verified`, `pending`, or `rejected`; record the reason. Continue with any verified subset the user requested for assessment. Keep pending or rejected targets in the original manifest and summarize them separately beside the report or in chat; they do not block unrelated verified targets. Never execute an unresolved target.

Before report construction, derive the admitted verified view as `targets/manifest.verified.json` with `--derive-subset-manifest`, even when every requested target is admitted. For a mixed manifest this excludes unresolved records without deleting them or copying target bytes into a second workspace.

Read [target-figure-acquisition.md](references/target-figure-acquisition.md) only when acquiring, replacing, or verifying targets. Read [image-derived-reconstruction.md](references/image-derived-reconstruction.md) only for images-only or deliberately image-derived routes.

## Evidence and route model

For scientific mode, assign each target the most defensible current level: `direct-recompute`, `mechanism-reproduction`, `alternative-validation`, `editable-reconstruction`, or `original-case-blocked`. Candidate routes serve that level; if a materially different route would change the level or supported claim, present it as a clearly separated alternative and renew the assessment before execution. Images-only work uses `image-derived-reconstruction`.

Cover all five route categories—`input`, `method`, `protocol`, `validation`, and `environment`—but do not manufacture exactly five checklist rows. Each category may contain one or many concrete conditions; use `not-required` when a category genuinely does not apply.

Track two independent axes:

- **Evidence certainty:** `verified`, `derivable`, `assumable`, `missing`, or `not-required`.
- **Execution readiness:** `ready`, `conditional`, `blocked`, or `not-required`.

A transparent derivation or explicitly frozen defensible assumption can be execution-ready while remaining less certain than verified evidence. Missing original-case evidence may block `direct-recompute` while leaving a mechanism or alternative route ready. State what every route can and cannot support.

## Phase 1 — Build the decision report

For a compact report, run `scripts/init_report.py init` to create `scirepro.compact-report/v1`, replace every `TODO::` value from evidence, run `validate-ready`, then use `expand` to create the complete v3 input for `build_report.py`. Read [report-scaffold.md](references/report-scaffold.md) only when using this helper. The scaffold reduces structural repetition but never supplies scientific conclusions.

For each admitted target:

1. Interpret the caption, axes, legends, panels, nearby text, equations, methods, and evidence role; separate observation from author interpretation.
2. Reconstruct input, preprocessing/calibration, method/model, aggregation/statistics, and visual encoding. Mark every link `paper`, `code`, `derived`, `assumption`, or `user`.
3. Freeze observable acceptance criteria, then form the minimum useful candidate routes with stable IDs, assumptions, blockers, effects, resource estimates, and outputs.
4. Audit only sources, data, runtimes, packages/toolboxes, licenses, and hardware required to decide those routes. Do not inventory the machine or web broadly.
5. Write `scirepro-report.json`, build the local static report with the verified-subset target manifest, inspect it visually, present its location, and stop for approval. If the product browser refuses `file://`, serve only that report directory on a temporary `127.0.0.1` listener and stop it after QA.

Keep the report decision-dense:

- Default to one minimum useful route per target; add another only when its scientific scope, evidence level, or validation claim materially differs.
- Default to 1–3 observations and 1–3 validation targets per figure. Add more only when distinct panels or claims require them.
- Keep each prose field to 1–3 sentences. Reference shared sources and environments by ID instead of retelling them, and state the same gap only once.
- For multiple targets, record shared paper, code, data, and environment evidence once, then reuse references. Do not paste raw paper text, source files, logs, or search transcripts into the report.
- Preserve every required scientific field; compactness removes repetition and irrelevant alternatives, not evidence, boundaries, or acceptance criteria.

Read [investigation-schema.md](references/investigation-schema.md) only while authoring or validating report JSON. Read [source-environment-audit.md](references/source-environment-audit.md) only when a route depends on external code/data or uncertain local capability. Read [web-report-contract.md](references/web-report-contract.md) only while building or checking the web report.

Build the local report with:

```bash
python <skill-root>/scripts/build_report.py --input scirepro-report.json \
  --target-manifest targets/manifest.verified.json --audience local --output report
```

Display verified target images directly. Put unresolved target IDs and exclusion reasons in a short acquisition summary beside the report or in chat; the current report schema contains only admitted targets. A public bundle is separate: include target bytes only with verified redistribution permission and never leak local paths.

## Permissions and approval

Read [permission-gates.md](references/permission-gates.md) before any download, installation, code execution, external effect, or Phase 2 run. Apply the default bounded R1 budget unless the user supplied another one; ask before R2/R3 and block R4.

A compact approval receipt still binds report and manifest hashes, target/route IDs, target hashes, accepted assumptions, modes/levels, budget, effects, and output policy. A full audited report uses the detailed approval draft. Validate either with:

```bash
python <skill-root>/scripts/plan_gate.py --report report/report.json \
  --approval approval.json --target-manifest targets/manifest.verified.json
```

Renew approval only after a material change to target identity, route, scientific scope, accepted assumption, restricted source, effect, budget, or output policy—not for harmless formatting or an equivalent retry inside the approved envelope.

## Phase 2 — Execute approved scope

Read [execution-validation.md](references/execution-validation.md) only after approval. Read [run-bundle-contract.md](references/run-bundle-contract.md) when creating or finalizing the run output.

1. Freeze target, report, approval, source, environment, input, and validation hashes; claim the idempotency key.
2. Work in a versioned run directory and preserve originals read-only. Execute only approved targets, one target at a time; one failure must not corrupt completed targets.
3. Trace implementation to declared generation links. Stop for renewed approval only on a material substitution or newly gated effect.
4. Smoke test, run, export, and validate against predefined scientific or image-derived criteria. Keep compatibility fixes documented and semantic changes separately approved.
5. Finalize exactly one run-bundle directory with status, per-target outputs and validation, reusable code/configuration, environment, commands, resource use, provenance, licenses, assumptions, and patches. A `complete` or `partial` reproduction must include an updated local result report; a `failed`, `blocked`, or `cancelled` diagnostic bundle may omit it. Restricted resources are referenced, not redistributed.

Report execution status, validation status, and scientific-claim status separately. Preserve diagnostic manifests and logs even for partial, failed, blocked, or cancelled runs.

## Specialized routing

- For quantitative plots and data/computation-derived figures, continue here.
- For workflow, architecture, mechanism, or editable conceptual schematics, use `sci-diagram-pptx` when installed; otherwise point to its official project without claiming installation.
- For mixed panels, audit panels separately while retaining one target identity and aggregate conclusion.
