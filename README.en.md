<h1 align="center">SciRepro</h1>

<p align="center"><strong>From a scientific figure back to a research process that can run, compare, and be tested</strong></p>
<p align="center"><a href="README.md">简体中文</a> · English · <a href="scirepro/SKILL.md">Skill specification</a></p>

SciRepro is a scientific-figure reproduction Skill for Codex. It traces only the data–method–parameter–plot chain relevant to the requested targets, runs the best-supported route as soon as it is defensible, and judges the result by scientific observables rather than closer imitation of published pixels.

The outcome may be a successful reproduction, an honestly bounded alternative validation, a useful negative result, or a precise blocker with a path to resolution. A successful command does not by itself support a paper claim.

## Install and invoke

```text
Use $skill-installer to install https://github.com/SciToolsmith/scirepro/tree/main/scirepro
```

```text
Use $scirepro to reproduce Figures 1, 6, and 7 from this paper.
```

Three input paths are supported, including multiple targets in one task:

- a paper plus uploaded target images;
- a paper plus figure or panel references, with target acquisition and verification by the Skill;
- target images alone for explicitly labelled image-derived reconstruction, never presented as recovery of the original experiment, data, or paper conclusion.

Different targets may use different implementations or runtimes. Their successes, failures, and blockers remain independent.

## How it works

```text
Confirm target → understand the scientific observable → trace the relevant generation chain
→ choose an honest route → reach and preserve the first useful V0 → validate scientifically
→ one customer folder
```

- Author-native code, data formats, and runtimes are preferred when they best preserve evidence for the objective. An independent derivation, port, or cross-check may be the right route; every substitution is explicit.
- Only sources, formulas, parameters, data, and environment facts capable of changing the route, conclusion, safety, material cost, or deliverable are investigated. Investigation stops when more evidence cannot change a decision.
- Safe, create-only, bounded local work proceeds without a pre-execution webpage or approval ceremony. Login, payment, restricted resources, upload, overwrite, publication, or a material scientific choice still requires the user.
- The first scientifically useful V0 is produced and preserved early. Investigation expands to another search branch, delegation, broad probe, or scientific run only when it can resolve a named unknown that changes a decision.
- Sensitivity analysis is used only when the claim or interpretation of a negative result depends on robustness. There is no fixed universal iteration count.
- Informative failures and contrary results are retained. Random seeds are not cherry-picked to resemble the target, and reproduction failure alone is not treated as research misconduct.

## Flowcharts and mechanism schematics

Algorithm flowcharts, mechanism diagrams, technical routes, and scientific architectures are terminally handed to `sci-diagram-pptx` rather than treated as quantitative reproductions. When no format is specified, the default deliverable is one native editable PPTX plus a PNG preview. Build source is included only when explicitly requested and cleanly reproducible.

A missing companion Skill may be deployed only from a pinned public commit within a narrow boundary. This never overwrites an existing installation or silently installs its runtime, Office, fonts, or system software.

## What the customer receives

When persistent work exists, SciRepro assembles one concise customer folder from a transient internal workspace. It contains:

- a start document that leads with the scientific outcome and then its limits;
- the primary figure or editable artifact for each target, plus only necessary comparison and validation evidence;
- the code, configuration, command, and actual dependencies needed to rerun the selected work;
- material assumptions, substitutions, negative results, remaining discrepancies, and rights boundaries.

Raw search history, debugging logs, QA overlays, internal manifests, broad machine inventories, and irrelevant intermediate versions are not customer deliverables. Material facts are summarized and required evidence is promoted into purpose-built files.

## License

SciRepro is released under the [MIT License](LICENSE). Papers, datasets, third-party code, and generated artifacts retain their respective rights, access conditions, and licenses.
