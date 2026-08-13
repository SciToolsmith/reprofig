# Token-efficient report authoring

Use the `scirepro.compact-report/v1` authoring scaffold when one minimum useful route per verified Phase 0 target is enough to express the decision. The schema name is retained for compatibility; it is only an internal token-saving format and does not change the workflow, report contract, or evidence standard. The authoring file contains shared evidence/environment records plus each target's scientific interpretation, generation chain, validation criteria, route, and five readiness conditions. The helper deterministically expands target metadata, hashes, IDs, cross-references, workflow fields, and approval policy into the same v3 report contract used by every SciRepro assessment.

This saves authoring tokens. It does not replace reading the target, paper, code, or data; checking the local environment; or making a supported scientific judgement.

## 1. Initialize authoring JSON

```bash
python <skill-root>/scripts/init_report.py init \
  --target-manifest /absolute/path/targets/manifest.verified.json \
  --output /absolute/path/scirepro-compact.json \
  --mode compact --audience local
```

The command is atomic and create-only. It copies no target bytes. Every `TODO::...` value is unresolved, not a suggested conclusion. Replace all TODOs with evidence-backed content. Leave the root `sources` and `environment` arrays shared; do not duplicate them per target. Per-item `sourceIds` may be omitted to cite the verified paper or target set automatically.

The scaffold intentionally supports one route and one condition in each readiness category per target. Author the v3 object directly when genuinely distinct routes or several independent conditions materially change feasibility, scientific scope, cost, risk, permission, or expected evidence. This is a representation choice inside one unified workflow, not a reason to broaden the investigation.

`generation.formulaAudit` is optional and absent from the initialized scaffold, so targets without a relevant formula pay no authoring cost. When one target-chain formula check affects the single compact route, add the audit without `checkId`, `routeBindings`, or `evidenceRefs`; optional `sourceIds` works like the other compact records. Expansion creates a stable check ID and a deterministic structured binding: `as-stated`, `derived`, or `assumed` according to the decision. A blocking item stays unbound and therefore requires the compact route itself to be blocked. A `split-routes` decision cannot be represented by the one-route scaffold: `validate-ready` rejects it with a request to author full `reprofig.report/v3` alternatives with explicit `routeBindings` instead of dropping the divergence.

```json
{
  "formulaAudit": {
    "scope": "target-chain-only",
    "included": ["Eq. (4) coordinate transform"],
    "excluded": ["Unrelated convergence proof"],
    "rationale": "The transform controls the plotted coordinates.",
    "items": [{
      "label": "Coordinate transform",
      "dependency": "Maps the computed state to both axes.",
      "sourceStatement": "Paper Eq. (4)",
      "checks": ["derivation", "dimensions", "boundary-cases"],
      "status": "derived",
      "finding": "The target-scoped derivation is dimensionally consistent.",
      "implementationDecision": "use-derived"
    }]
  }
}
```

The single route may be `blocked`. In that case, provide concrete blockers, leave its execution-only plan and deliverables empty when they are not yet knowable, and allow expansion to emit `recommendedRouteId: null`. Keep the target's declared workflow mode and reproduction level unchanged; in particular, an image-only target remains `image-derived-reconstruction`.

## 2. Check scientific and structural completeness

```bash
python <skill-root>/scripts/init_report.py validate-ready \
  --input /absolute/path/scirepro-compact.json \
  --target-manifest /absolute/path/targets/manifest.verified.json
```

This rejects every remaining TODO, verifies that the authoring file still binds the same target manifest, expands it in memory, and runs the v3 validator. It never treats missing information as verified.

## 3. Expand to the report-builder input

```bash
python <skill-root>/scripts/init_report.py expand \
  --input /absolute/path/scirepro-compact.json \
  --target-manifest /absolute/path/targets/manifest.verified.json \
  --output /absolute/path/scirepro-report.json
```

Expansion is also atomic and create-only. The resulting `reprofig.report/v3` JSON—not the intermediate authoring file—is passed to `build_report.py`.

Keep prose short and evidence-linked. Add alternative routes only when they materially change feasibility, scientific scope, cost, risk, permission, or expected evidence. Stop investigating when the report can already support a route that tests the stated objective at its declared reproduction level, or a concrete blocked judgment.
