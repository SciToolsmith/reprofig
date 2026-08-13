# Terminal schematic handoff

Use this reference only after a target is provisionally identified as a scientific semantic schematic. This is a terminal router, not a SciRepro reproduction route.

## Classification

Hand off algorithm flowcharts, scientific workflows, technical routes, mechanism diagrams, system or model architectures, block diagrams, and conceptual schematics when visible meaning is encoded mainly by labelled objects, connectors, direction, grouping, nesting, containment, or topology.

Keep quantitative plots in SciRepro when meaning is encoded mainly by axes, scales, legends, samples, or data-driven geometry, even if the plot contains callout arrows or explanatory boxes.

- A process canvas containing a small photograph, spectrum, screenshot, or formula is one schematic. Hand off the whole target; the receiving skill decides whether that content remains a raster inset.
- Clearly separable peer panels may be routed independently while retaining their parent figure and panel labels. Exclude handed-off panels from SciRepro execution and its final result folder.
- When the panel boundary or requested deliverable is genuinely unclear, ask one concise scope question. Do not begin SciRepro acquisition or execution while waiting.

## Acquire only what routing needs

When only a paper and figure reference are available, obtain the minimum readable target needed for handoff. Preserve the original paper or upload, figure label, page, full caption, and a traceable crop or panel bounding box. Read nearby text or equations only when they disambiguate wording, formulas, arrow direction, grouping, or the selected panel.

Do not create a SciRepro target workspace or result folder for this limited acquisition.

## Ensure the companion without asking

Run:

```bash
python <skill-root>/scripts/ensure_diagram_companion.py
```

This is a standing, narrowly bounded bootstrap exception. It may install only the user-level Codex skill from:

- repository: `SciToolsmith/sci-diagram-pptx`;
- path: `skills/sci-diagram-pptx`;
- commit: `26a2ae281df4209fa9687ca80d27a3aa7feb1ee3`;
- method: anonymous public download through the system `skill-installer`.

Do not ask for confirmation when the destination is absent. Do not follow `main`, search for a substitute, use Git credentials, overwrite an existing destination, or install Python, Node, Office, LibreOffice, fonts, system packages, or any runtime dependency. A valid existing installation is reused without modification and reported as user-managed; do not falsely assign the pinned commit to it. An invalid or conflicting destination, missing system installer, download failure, or failed post-install validation is terminal: report the concrete blocker and stop rather than continuing in SciRepro.

The helper returns the absolute companion directory. After a successful install or validation, read that directory's `SKILL.md` completely and read only the references it routes to. Continue under `sci-diagram-pptx` in the same task; do not wait for skill discovery on a later turn.

## Transfer of ownership

Pass only the material the receiving skill needs:

- the unchanged uploaded target, or the traceable full-figure crop;
- a selected panel bounding box when applicable;
- paper path or DOI, figure and panel label, page, and complete caption when known;
- the minimum nearby context needed to preserve visible wording, formulas, connector semantics, and scientific meaning;
- the user's original requested deliverable and constraints.

Pass no SciRepro route, environment, validation, or result-folder machinery. Once the transfer succeeds, SciRepro instructions cease to govern that target.

The receiver may return a target once only when it determines that meaning is actually encoded by quantitative axes, scales, or data-driven geometry. The return must state that reason. Resolution, unreadable text, runtime availability, or PPTX authoring limitations are not reasons to return ownership.
