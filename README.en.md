<h1 align="center">SciRepro</h1>

<p align="center"><strong>From a scientific figure back to a research process that can run, compare, and be tested</strong></p>
<p align="center"><a href="README.md">简体中文</a> · English · <a href="scirepro/SKILL.md">Skill specification</a></p>

SciRepro is a scientific-figure reproduction Skill for Codex. It accepts a paper with target images, a paper with figure references, or target images alone; traces the target-relevant data–method–parameter–plot chain; executes the best-supported route; and validates the result against predefined scientific observables.

Its goal is not closer pixel imitation. It delivers rerunnable evidence: a successful reproduction, an honestly bounded alternative validation, a useful negative result, or a precise blocker with a path to resolution.

## Quick start

```text
Use $skill-installer to install https://github.com/SciToolsmith/scirepro/tree/main/scirepro
```

```text
Use $scirepro to reproduce Figures 1, 6, and 7 from this paper.
```

Three entry paths are supported:

- a paper plus uploaded target images;
- a paper plus figure or panel references, with target acquisition and verification by the Skill;
- target images alone for explicitly labelled image-derived reconstruction, never presented as recovery of the original experiment or data.

Algorithm flowcharts, mechanism diagrams, technical routes, and scientific architectures are handed to `sci-diagram-pptx`. A missing companion Skill may be deployed from a pinned public commit within a strict boundary; this never installs its runtimes or system software and never overwrites an existing installation.

## How it works

```text
Lock target → understand the scientific observable → trace the relevant generation chain
→ choose an honest route → run and preserve V0 → validate and iterate from evidence
→ one result folder
```

- Author-native implementations are the default evidence-preserving preference, but the user’s objective determines the route. An independent implementation, derivation, port, or cross-check may be the right choice; substitutions are always explicit.
- Only formulas, parameters, data, and environments capable of changing the target result or conclusion are investigated.
- Safe, create-only, bounded local routes run directly. The user is asked only for material effects such as login, payment, shared licenses, GPU or cloud use, overwrite, upload, or publication.
- Planned resource caps are declarations by default. They are described as enforced or measured only when the execution mechanism provides that evidence.
- The untuned V0 is preserved. Later runs require a concrete diagnosis or testable hypothesis and stop when they can no longer add meaningful scientific information.
- Execution failure, validation failure, and lack of support for a paper claim remain distinct. Reproduction failure alone is not a finding of misconduct.

## Final delivery

Once persistent work exists, SciRepro delivers one `scirepro-run-<id>/` folder containing target and source boundaries, rerunnable code and commands, inputs and parameters, environment evidence, V0 and any justified later versions, comparisons and validation, assumptions, licenses, logs, and remaining differences. Shared evidence is stored once, while each target’s success, failure, or blocker remains isolated.

## License

SciRepro is released under the [MIT License](LICENSE). Papers, datasets, third-party code, and generated artifacts retain their respective rights, access conditions, and licenses.
