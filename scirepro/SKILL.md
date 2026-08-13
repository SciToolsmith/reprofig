---
name: scirepro
description: Reproduce and scientifically assess one or many research figures from a paper plus target images, a paper plus figure references, or target images alone. Use when Codex must acquire and interpret targets, reconstruct the relevant data-to-figure chain, choose and run the strongest honest route, validate scientific observables, preserve negative results, and deliver rerunnable evidence. Route semantic scientific schematics to sci-diagram-pptx instead of reproducing them as quantitative figures.
---

# SciRepro

Recover the smallest defensible process that can regenerate or test what a scientific figure shows. Optimize for a useful, rerunnable result or a precise blocker—not for pixel resemblance or exhaustive paper review.

## Route ownership first

Classify each requested target before SciRepro analysis:

- Hand a semantic schematic to `sci-diagram-pptx` when meaning is carried mainly by nodes, connectors, labels, formulas, grouping, containment, or topology. Read [diagram-handoff.md](references/diagram-handoff.md), transfer only the target and necessary scientific context, and end SciRepro ownership.
- Keep a target when meaning is carried mainly by quantitative axes, scales, samples, legends, measurements, images, or data-driven geometry.
- Route clearly separable panels independently; otherwise treat the whole figure as one target.

Use an installed companion when valid. If it is missing, the pinned public companion may be bootstrapped automatically under the narrow exception in [permission-gates.md](references/permission-gates.md). Fail closed on conflicts or validation failure, and never install its runtimes or system dependencies implicitly.

## Core workflow

1. **Stabilize the target when needed.** Acquire a readable figure, caption, paper binding, nearby context, and stable identity. Use [target-figure-acquisition.md](references/target-figure-acquisition.md) for fragile extraction, normalization, hashing, replacement, QA, or multi-target tracking. Never execute an unresolved target.
2. **Understand the observable.** Separate visible observation from author interpretation. Reconstruct only the target-dependent chain: input, selection/preprocessing, method, parameters and randomness, aggregation/statistics, plotted quantity, and visual encoding.
3. **Choose the strongest honest route.** Use `direct-recompute`, `mechanism-reproduction`, `alternative-validation`, or `original-case-blocked`. Without reliable paper context, use `image-derived-reconstruction` and read [image-derived-reconstruction.md](references/image-derived-reconstruction.md). State what the route tests and what it cannot support.
4. **Resolve decision-changing unknowns.** Check only sources, data identity, formulas, parameters, runtime capabilities, and permissions that can change feasibility, claim scope, material cost, or safety. Read [source-environment-audit.md](references/source-environment-audit.md) when external artifacts or uncertain execution capability matter.
5. **Bound the run internally.** Before execution, settle target and route identity, inputs, implementation/runtime, parameters or seeds, assumptions, acceptance criteria, effects, resource declarations, and expected deliverables. Keep this assessment proportional to the task; it is reasoning context, not a user-facing artifact.
6. **Execute or stop.** Run bounded, create-only local work directly when scientifically defensible and permitted. Consolidate currently known material questions into one decision request when practical. If a later discovery creates a new material scientific or permission decision, ask then; do not stretch earlier authority. If every defensible route is blocked, stop with the evidence checked and the condition that would reopen it.
7. **Run and validate.** Preserve the first scientifically meaningful output as V0. Compare scientific content before presentation. Follow [execution-validation.md](references/execution-validation.md); iterate only on a stated diagnosis or testable hypothesis with expected information gain, and stop when criteria pass or another run cannot materially improve the scientific conclusion.
8. **Deliver one result folder.** Finalize exactly one create-only run folder containing shared provenance and isolated per-target results. Follow [run-bundle-contract.md](references/run-bundle-contract.md). A block before execution may remain chat-only when no durable artifact helps continuation.

For read-only interpretation or feasibility questions, answer directly. Do not manufacture execution artifacts.

## Scientific judgment

- Treat the author’s native code, data format, and runtime as the default evidence-preserving route when they serve the user’s objective. A requested independent implementation, derivation, portable deliverable, or cross-check may justify another route. Never substitute silently; document compatibility checks and the changed evidence boundary.
- Treat paper equations, parameters, and code as candidate specifications. Derive or verify only target-relevant units, dimensions, indices, signs, normalization, assumptions, boundary conditions, and values. Record ambiguities and paper–code differences; never silently repair them.
- Define acceptance criteria before tuning where practical. Scientific fidelity—variables, units, scale, phenomenon, magnitude, uncertainty, and robustness—outranks styling. Pixel similarity alone validates only a declared image-derived objective.
- Preserve V0, contrary results, failed attempts that explain the outcome, compatibility patches, and remaining discrepancies. Never cherry-pick randomness, conceal negative evidence, or weaken criteria after seeing the output.
- Keep operational status, validation status, and claim status independent. A crash does not refute a paper; `unsupported` requires a valid test of the claim.
- Reproduction failure alone is not evidence of misconduct. Escalate only a repeatable anomaly that remains unexplained after relevant ordinary differences are tested. Use neutral language and never contact authors, journals, or third parties without separate authorization.

## Interaction and safety

Read [permission-gates.md](references/permission-gates.md) before downloads, installation, code execution, proprietary-runtime use, or external effects. Do not create a pre-execution webpage or approval ceremony; assessment remains internal, and genuine decisions are asked concisely in chat.

Resource caps in a plan are declarations unless the execution mechanism actually enforces or measures them. Never describe a declared limit as sandboxed, enforced, or observed without corresponding evidence.
