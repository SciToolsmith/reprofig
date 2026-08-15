<h1 align="center">SciRepro</h1>

<p align="center"><strong>From a scientific figure back to a research process that can run, compare, and be tested</strong></p>
<p align="center"><a href="README.md">简体中文</a> · English · <a href="scirepro/SKILL.md">Skill specification</a></p>

SciRepro is a scientific-figure reproduction Skill for Codex. It traces only the data–method–parameter–plot chain relevant to the requested targets, runs the best-supported route as soon as it is defensible, and judges the result by scientific observables rather than closer imitation of published pixels.

The outcome may be a successful reproduction, an honestly bounded alternative validation, a useful negative result, or a precise blocker with a path to resolution. A successful command does not by itself support a paper claim.

It handles two kinds of work with different evidence boundaries: when paper context and target-relevant evidence are sufficient, it can reproduce or test the research process that generated a figure; with images alone, it reconstructs only content reliably identifiable in the image. The latter is not a reproduction of the original experiment, data, or paper conclusion.

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
- target images alone, first assessed for whether their pixels contain enough identifiable information for an image-derived reconstruction; otherwise the Skill returns a precise blocker.

Different targets may use different implementations or runtimes. Their successes, failures, and blockers remain independent.

## What kinds of reproduction it performs

The first two inputs support **research-process reproduction or assessment**. SciRepro combines the paper, target figure, and available code, data, and parameters to trace the target-relevant data–method–parameter–plot chain. This research-process reproduction may be a recomputation under original conditions, a mechanism reproduction, an alternative validation, or a blocker when key evidence is absent; one successful run is never presented as proof of every paper claim.

When a paper omits details, SciRepro does not treat every missing value as a blocker. It asks whether the unknown can change the target scientific observables or conclusion: claim-defining unknowns are resolved, derived, or tested over the smallest useful range; non-critical controls receive a justified, explicit, rerunnable assumption, with a small comparison only when plausible choices could change acceptance; incidental random realizations and non-scientific styling are fixed once. When authoritative evidence shows that the original case cannot be recomputed exactly but its mechanism can still be tested, the Skill switches early to mechanism reproduction instead of extending archaeology or pursuing 1:1 pixels. Assumptions are never presented as author-recovered values or selected after the fact merely to match the image.

The third input supports **image-derived reconstruction**, which is not conflated with research-process reproduction. SciRepro first assesses identifiability:

- when axes, ticks, legends, and marks are clear enough, it can digitize and redraw visible data within a stated pixel-derived uncertainty;
- when only some information is identifiable, it reconstructs only the identifiable curves, layout, relative trends, or annotations and preserves what remains unknown;
- when only appearance is identifiable, it delivers an appearance or layout reconstruction only when that is the user's objective, and labels it accordingly;
- when essential data, coordinate mapping, or the generating method cannot be identified from pixels and the requested result depends on that information, it states which reproduction cannot be completed and the minimum additional material needed, without guessing missing content;
- semantic flowcharts and mechanism schematics are terminally handed to `sci-diagram-pptx`.

Thus, redrawing data visible in an image, reconstructing its appearance, and reproducing the research process that generated it are distinct outcomes. SciRepro labels which one was actually achieved.

## How it works

```text
Confirm target → understand the scientific observable → trace the relevant generation chain
→ choose an honest route → reach and preserve the first useful V0 → validate scientifically
→ one customer folder
```

- SciRepro first determines whether author-native code actually participates in the target-producing stage. When it does, native execution would change the evidence level, and a local runtime is detected, the Skill first performs a bounded startup, license/dependency-prerequisite, and minimal native-run check. `Detected but untested` is not a reason to port. A declared port becomes primary only after installation, license, or required capability is confirmed unavailable, or when portability or independent validation is itself the objective.
- Missingness alone does not trigger network discovery. SciRepro uses the paper, target, and supplied materials first; it searches only for unresolved facts that can change the route, conclusion, safety, material cost, or deliverable, and cancels obsolete searches after each material result.
- Safe, create-only, bounded local work proceeds without a pre-execution webpage or approval ceremony. Login, payment, restricted resources, upload, overwrite, publication, or a material scientific choice still requires the user.
- The first scientifically useful V0 is produced and preserved early. Investigation expands to another search branch, delegation, broad probe, or scientific run only when it can resolve a named unknown that changes a decision.
- Sensitivity analysis is used only when the claim or interpretation of a negative result depends on robustness. There is no fixed universal iteration count.
- Informative failures and contrary results are retained. Random seeds are not cherry-picked to resemble the target, and reproduction failure alone is not treated as research misconduct.

## Flowcharts and mechanism schematics

Algorithm flowcharts, mechanism diagrams, technical routes, and scientific architectures are terminally handed to `sci-diagram-pptx` rather than treated as quantitative reproductions. When no format is specified, the default deliverable is one native editable PPTX plus a PNG preview. Build source is included only when explicitly requested and cleanly reproducible.

A missing companion Skill may be deployed only from a pinned public commit within a narrow boundary. This never overwrites an existing installation or silently installs its runtime, Office, fonts, or system software.

## What the customer receives

When persistent work exists, SciRepro assembles one concise customer folder from a transient internal workspace. It is the finished result plus the materials needed to produce it, not an archive of Codex's work. By default it contains:

- the final figure, editable artifact, or other primary result;
- the actual final code or editable source that produces it, not working drafts;
- configuration, data, model weights, checkpoints, calibration files, or other inputs that the code actually reads and cannot regenerate from delivered material;
- the minimum dependency declaration or environment file and licenses required by included third-party material; and
- a short README containing the conclusion, one exact rerun command, required inputs and dependencies, and only limitations or rights that affect interpretation or reuse.

Required data or models that are too large, access-controlled, or not redistributable are not silently omitted: the delivery gives a lawful, pinned acquisition method, version, and an available checksum, and states that the folder is not fully self-contained. Numeric tables, comparisons, or other extras are included only when explicitly requested, needed downstream, or independently valuable.

Validation JSON, runtime/license probe records, iteration traces, sensitivity details, regenerated CSV files, raw search history, debugging logs, QA overlays, internal manifests, V0, reference crops, and irrelevant intermediate versions stay in the transient workspace by default. Only facts that materially change the conclusion enter the short README. Final code produces only the primary result by default; diagnostics and data exports require explicit options. Before delivery, SciRepro runs the README command in a clean copy containing only the proposed customer files and checks for local paths, caches, undeclared inputs, and rerun noise; the check record is not delivered. If blocked work has no durable reusable result, SciRepro answers in chat instead of manufacturing a folder.

## License

SciRepro is released under the [MIT License](LICENSE). Papers, datasets, third-party code, and generated artifacts retain their respective rights, access conditions, and licenses.
