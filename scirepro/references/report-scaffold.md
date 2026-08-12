# Compact report authoring

Use `scirepro.compact-report/v1` when a verified Phase 0 target set needs a local decision report and a full hand-authored v3 object would waste context. The compact file contains only shared evidence/environment records plus each target's scientific interpretation, generation chain, validation criteria, single candidate route, and five readiness conditions. The helper deterministically expands target metadata, hashes, IDs, cross-references, workflow fields, and approval policy.

This saves authoring tokens. It does not replace reading the target, paper, code, or data; checking the local environment; or making a supported scientific judgement.

## 1. Initialize compact authoring JSON

```bash
python <skill-root>/scripts/init_report.py init \
  --target-manifest /absolute/path/targets/manifest.verified.json \
  --output /absolute/path/scirepro-compact.json \
  --mode compact --audience local
```

The command is atomic and create-only. It copies no target bytes. Every `TODO::...` value is unresolved, not a suggested conclusion. Replace all TODOs with evidence-backed content. Leave the root `sources` and `environment` arrays shared; do not duplicate them per target. Per-item `sourceIds` may be omitted to cite the verified paper or target set automatically.

Compact authoring intentionally supports one route and one condition in each readiness category per target. Use the full v3 schema instead when genuinely distinct routes or several independent conditions within a category materially affect the decision.

The single compact route may be `blocked`. In that case, provide concrete blockers, leave its execution-only plan and deliverables empty when they are not yet knowable, and allow expansion to emit `recommendedRouteId: null`. Keep the target's declared workflow mode and reproduction level unchanged; in particular, an image-only target remains `image-derived-reconstruction`.

## 2. Check scientific and structural completeness

```bash
python <skill-root>/scripts/init_report.py validate-ready \
  --input /absolute/path/scirepro-compact.json \
  --target-manifest /absolute/path/targets/manifest.verified.json
```

This rejects every remaining TODO, verifies that the compact file still binds the same target manifest, expands it in memory, and runs the full v3 validator. It never treats missing information as verified.

## 3. Expand to the report-builder input

```bash
python <skill-root>/scripts/init_report.py expand \
  --input /absolute/path/scirepro-compact.json \
  --target-manifest /absolute/path/targets/manifest.verified.json \
  --output /absolute/path/scirepro-report.json
```

Expansion is also atomic and create-only. The resulting `reprofig.report/v3` JSON—not the compact authoring file—is passed to `build_report.py`.

Keep compact prose short and evidence-linked. Add alternative routes only by switching to the full schema, and only when they change scientific scope, cost, risk, or expected evidence.
