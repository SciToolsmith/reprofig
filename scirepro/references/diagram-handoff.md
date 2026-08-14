# Terminal schematic handoff

Use this reference after a target is identified as a scientific semantic schematic. This is a terminal transfer to `sci-diagram-pptx`, not a SciRepro reproduction route.

## Classify the target

Hand off algorithm flowcharts, scientific workflows, technical routes, mechanism diagrams, system/model architectures, block diagrams, and conceptual schematics when meaning is encoded mainly by labelled objects, connectors, direction, grouping, nesting, containment, or topology.

Keep quantitative plots in SciRepro when meaning is encoded mainly by axes, scales, legends, samples, measurements, or data-driven geometry, even when callouts or explanatory boxes are present.

- Treat a process canvas containing a small photograph, spectrum, screenshot, or formula as one schematic; the receiver decides whether that content remains a raster inset.
- Route clearly separable peer panels independently while preserving parent figure and panel identity. Exclude transferred panels from SciRepro scientific execution and validation.
- Ask one concise scope question only when the panel boundary or required artifact is genuinely decision-changing. Do not begin SciRepro execution while waiting.

## Acquire only what transfer needs

When only a paper and figure reference are available, obtain the minimum readable target required by the receiver. Preserve the original upload or paper locator, figure/panel label, page, complete caption, and traceable crop/bounds. Read nearby text or equations only when they disambiguate visible wording, a target-relevant formula, arrow direction, grouping, or the selected panel.

Do not create a SciRepro target workspace, execution route, or validation record for the schematic. When every requested target is transferred, the companion owns its delivery and SciRepro creates no separate customer folder. In a mixed task, the task coordinator may later place only the companion's final artifacts in the common customer folder; SciRepro must not reinterpret or revalidate them. Do not continue source archaeology after the receiver has enough context.

## Ensure the pinned companion

Run:

```bash
python <skill-root>/scripts/ensure_diagram_companion.py
```

This standing exception may install only the user-level Codex skill from:

- repository: `SciToolsmith/sci-diagram-pptx`;
- path: `skills/sci-diagram-pptx`;
- commit: `26a2ae281df4209fa9687ca80d27a3aa7feb1ee3`;
- method: anonymous public download through the system `skill-installer`.

Do not ask merely because the valid destination is absent. Do not follow `main`, search for substitutes, use credentials, overwrite an existing destination, or install Python, Node, Office, LibreOffice, fonts, system packages, or companion runtime dependencies. Reuse a valid existing installation without modification and report it as user-managed. On conflict, missing installer, download failure, or failed validation, report the concrete blocker and stop rather than returning to SciRepro.

After installation or validation, read the companion's `SKILL.md` completely and only the references it directly routes to. Continue under `sci-diagram-pptx` in the same task.

## Transfer minimal ownership

Pass only:

- the unchanged uploaded target or traceable full-figure crop;
- selected panel bounds when applicable;
- paper path or DOI, figure/panel label, page, and complete caption when known;
- minimum nearby context needed for visible wording, formulas, connector semantics, and scientific meaning;
- the user's requested deliverable and constraints.

Pass no SciRepro route, environment probes, source-search history, validation machinery, internal manifests, or delivery structure. Once transfer succeeds, SciRepro instructions cease to govern that target.

The receiver may return a target once only when it determines that meaning is actually encoded by quantitative axes, scales, or data-driven geometry. Resolution, unreadable text, runtime availability, or PPTX authoring difficulty are not reasons to return ownership.

## Default terminal deliverable

When the user does not specify a format, request these customer-facing artifacts from the companion:

- one native editable PowerPoint (`.pptx`) containing the reconstructed schematic; and
- one PNG preview of the same final result for immediate inspection.

Do not add SVG, PDF, or multiple stylistic variants to the customer folder by default. The companion may create build source and QA artifacts internally under its own Skill contract; promote executable build source only when the user explicitly requests it and it is cleanly reproducible outside transient middleware: dependencies and commands are documented, local paths and internal tool metadata are removed, and the generated PPTX and preview have been verified. A user-requested downstream format or presentation context overrides the default.
