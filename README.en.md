<h1 align="center">SciRepro</h1>

<p align="center"><strong>From paper figures back to a research process that can be tested</strong></p>
<p align="center">Turn target figures into verified objects, approval-ready reproduction routes, and testable scientific results.</p>
<p align="center"><a href="README.md">简体中文</a> · <strong>English</strong> · <a href="#quick-start">Quick start</a> · <a href="scirepro/SKILL.md">Full specification</a></p>

## Quick start

**Install**

```text
Use $skill-installer to install https://github.com/SciToolsmith/scirepro/tree/main/scirepro
```

**Invoke**

```text
Use $scirepro to reproduce Figures 6 and 7 from this paper.
```

Use paper references, a paper with uploaded images, or images alone. Single- and multi-target requests follow the same workflow.

Algorithm flowcharts, mechanism diagrams, technical routes, and scientific architectures are handed directly to `sci-diagram-pptx` at the entry point and never enter SciRepro assessment, reporting, or approval. If the companion Skill is absent, SciRepro installs it from a pinned official public commit into the user-level Skills directory and continues; it never auto-installs the companion's runtimes or system software.

## Review the report before execution

**Verify targets → trace the generation chain → form a reproduction route → local decision report → researcher approval → execution and scientific validation**

Before execution, SciRepro generates a local web report containing the target figures and then stops. The report explains what each figure shows, how it was produced, what can be reproduced on the current computer, what is missing, and what each route can and cannot support.

[![Example SciRepro local decision report showing the paper, target figure, and reproduction assessment](docs/assets/report-preview.webp)](docs/assets/report-preview.webp)

<p align="center"><sub>Real report output · click to view at full size</sub></p>

SciRepro executes only after you approve the targets, route, assumptions, resource limits, and permission boundary.

## What you receive

- **Before approval:** a verified target set and a reviewable local decision report.
- **After approval:** one rerunnable result directory containing code, configuration, figures, validation, logs, sources, and hashes.
- **For every target:** separate records for execution status, validation status, and support for the paper's claim.

## Scientific boundaries

> **Code completion does not mean the figure passed validation; figure-level validation does not automatically support the paper's claim.**

- **With a paper:** reconstruct the data–method–protocol–plot chain and validate predefined scientific phenomena or metrics.
- **Images only:** reconstruct visible curves, geometry, and layout without claiming recovery of the original data, experiment, method, or paper conclusion.
- Equations, parameters, and author code are primary evidence, not presumed truth; SciRepro checks only what the target directly depends on.
- Preserve the untuned baseline and valid negative results; never substitute pixel similarity for scientific validation.
- Login, payment, large downloads, GPU use, overwrite, upload, and publication require explicit approval.

## Documentation and license

[Reproduction levels](scirepro/SKILL.md#evidence-and-route-model) ·
[Approval boundary](scirepro/SKILL.md#permissions-and-approval) ·
[Run-bundle contract](scirepro/references/run-bundle-contract.md)

SciRepro is released under the [MIT License](LICENSE). Papers, datasets, third-party code, and generated artifacts retain their respective rights and licenses.
