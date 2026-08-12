<p align="center">
  <picture>
    <source media="(max-width: 640px)" srcset="docs/assets/scirepro-hero-mobile.en.svg">
    <img src="docs/assets/scirepro-hero.en.svg" alt="SciRepro: from published figures back to the research process" width="100%">
  </picture>
</p>

<p align="center">
  <a href="README.md">简体中文</a> · <strong>English</strong> · <a href="#start-in-30-seconds">Quick start</a> · <a href="scirepro/SKILL.md">Full specification</a>
</p>

SciRepro is a scientific-figure reproduction skill for Codex. Give it a paper and target figures; it explains which claims they support, reconstructs their input-to-figure generation chains, proposes evidence-backed reproduction routes, and executes and validates only the route you approve.

> **It reproduces the research process and key scientific phenomena—not the pixels of the published image.**

## Start in 30 seconds

**Install**

```text
Use $skill-installer to install https://github.com/SciToolsmith/scirepro/tree/main/scirepro
```

**Invoke**

```text
Use $scirepro to analyze Figures 6, 7, and 11 from this paper.
First give me their evidential roles, generation chains, candidate routes,
and validation criteria. Generate the local report, then wait for my route selection.
```

## What you receive

- **Evidence map** — what is observable, which paper claim it supports, and what it cannot establish.
- **Reproduction routes** — explicit data, methods, protocols, assumptions, gaps, local conditions, and scientific validation criteria.
- **Traceable results** — rerunnable code, generated figures, configuration, validation results, logs, and provenance.

## Report first. Execute second.

**Before approval:** interpret the figure, investigate evidence, formulate routes, and generate a local report. The report separates what is verified, derivable, transparently assumable, and genuinely missing.

**After approval:** execute only the selected figures and routes. If the data, algorithm, environment, budget, or supported claim changes materially, SciRepro stops and asks again.

## Scientific reproduction, not visual reconstruction

- It does not trace or fit curves from the published image and present them as numerical results.
- It does not present substitute data, third-party implementations, or transparent assumptions as the authors' original case.
- It does not equate “the program ran” with “the paper's claim was reproduced.”

SciRepro validates predefined trends, peaks, frequencies, modes, statistics, or mechanism relationships, then states **what the result supports, what it cannot support, and what remains missing**.

<p align="center">
  <a href="scirepro/SKILL.md#evidence-model">Reproduction levels</a> ·
  <a href="scirepro/SKILL.md#approval-gate">Approval boundary</a> ·
  <a href="scirepro/SKILL.md#deliverables">Complete deliverables</a>
</p>

<details>
<summary><strong>Manual installation and migration</strong></summary>

```bash
git clone https://github.com/SciToolsmith/scirepro.git
mkdir -p ~/.codex/skills
cp -R ./scirepro/scirepro ~/.codex/skills/scirepro
```

When migrating from ReproFig, confirm that `$scirepro` works before removing or disabling `~/.codex/skills/reprofig`.

</details>

## Open source and license

SciRepro is released under the [MIT License](LICENSE). Papers, datasets, third-party code, and generated artifacts retain their respective rights and licenses.
