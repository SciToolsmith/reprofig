<p align="center">
  <picture>
    <source media="(max-width: 640px)" srcset="docs/assets/scirepro-hero-mobile.en.svg">
    <img src="docs/assets/scirepro-hero.en.svg" alt="SciRepro: from published figures back to the research process" width="100%">
  </picture>
</p>

<p align="center">
  <a href="README.md">简体中文</a> · <strong>English</strong> · <a href="#start-in-30-seconds">Quick start</a> · <a href="scirepro/SKILL.md">Full specification</a>
</p>

SciRepro is a scientific-figure reproduction skill for Codex. It first materializes every target as a verifiable object, then interprets the figures, traces their generation chains, investigates reproduction conditions, and produces a local report containing the targets. It executes and validates only the route you approve.

> **Verify the targets. Investigate the routes. Validate the scientific result.**

## Start in 30 seconds

**Install**

```text
Use $skill-installer to install https://github.com/SciToolsmith/scirepro/tree/main/scirepro
```

**Invoke: every entry path accepts one or many figures**

```text
# Paper + figure references (the skill extracts complete targets)
Use $scirepro to analyze Figures 6, 7, and 11 from this paper.

# Paper + uploaded target image set
Use $scirepro to analyze this paper and these uploaded target images.

# Images only
Use $scirepro to reconstruct the visible curves, data, and layout in these images.
```

Every path first creates a `targets/` workspace with preserved sources, normalized PNGs, crop QA, and a hash manifest. Targets reliably matched to the paper and verified by QA use `scientific-reproduction`; images-only work uses the explicitly bounded `image-derived-reconstruction` mode.

## What you receive

- **Verified target set** — source, page or user label, crop metadata, QA status, and hash for every target.
- **Local investigation report** — all target images, interpretations, generation chains, routes, gaps, and local capabilities in one page.
- **Reproduction routes** — explicit data, methods, protocols, assumptions, gaps, local conditions, and scientific validation criteria.
- **Traceable results** — rerunnable code, generated figures, configuration, validation results, logs, and provenance.

## Report first. Execute second.

**Before approval:** verify the targets, investigate evidence, formulate routes, and generate a local report. The report displays every reproduction target and separates what is verified, derivable, transparently assumable, and genuinely missing.

**After approval:** execute only the selected figures and routes. If the data, algorithm, environment, budget, or supported claim changes materially, SciRepro stops and asks again.

## Two modes, two claim boundaries

- **With a paper: scientific reproduction.** Reconstruct the data–method–protocol–plot chain and validate predefined trends, peaks, frequencies, modes, statistics, or mechanism relationships.
- **Images only: image-derived reconstruction.** Trace, digitize, fit visible geometry, or rebuild layout, but claim only visible geometry and appearance—not recovery of the original data, method, experiment, or paper conclusion.

The local report must display every target directly. A public/shareable report embeds image bytes only when redistribution rights are verified; otherwise it shows a rights notice without exposing local paths or content.

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
