# Image-derived reconstruction

Use `image-derived-reconstruction` when supplied target images lack reliable paper context. This is not research-process reproduction: reconstruct only content identifiable from pixels, and do not imply recovery or validation of the original data, method, experiment, or paper claim. If reliable paper context later establishes identity, create a new target and route rather than silently upgrading the result.

## Scope

Depending on the user's objective and visible evidence, reconstruct:

- panel layout, axes, ticks, legends, annotations, colors, typography, and relative geometry;
- visible curves, points, bars, contours, boundaries, or regions with stated uncertainty;
- approximate data series through calibrated digitization;
- rerunnable plotting code, editable vectors, or appearance/layout reconstruction.

Keep every derived value and styling decision traceable to the source image. Route work outside scientific chart/image reconstruction to the appropriate visual skill; semantic schematics belong terminally to `sci-diagram-pptx` under [diagram-handoff.md](diagram-handoff.md).

## Claim boundary

Pixels alone cannot establish raw data, hidden exact values, preprocessing, model, implementation, parameter history, experimental conditions, sample identity, seed, calibration, uncertainty procedure, figure role, or paper claim. Do not label digitized points as original observations or present an appearance fit as direct recomputation, mechanism reproduction, or alternative validation.

## Identifiability gate

Before reconstruction, decide what the supplied pixels can support. Do not infer recoverability from chart type alone: a line or bar chart may still have unreadable scale type, legend mapping, marks, overlap, or resolution.

1. **Digitizable visible data.** Proceed with calibrated axes or coordinate mapping and digitization only when relevant scale type and units, series identity, and marks or boundaries are sufficiently readable to meet the requested tolerance. State the pixel-derived uncertainty. If the pixels cannot support that tolerance, narrow the result to a partially identifiable subset or block it. Digitized values must not be presented as original data or observations.
2. **Partially identifiable content.** Reconstruct only the identifiable subset of panels, series, geometry, labels, or relative trends. Preserve missing, occluded, and ambiguous content as unknown rather than completing it by inference.
3. **Appearance-only content.** Use tracing, layout reconstruction, or styling only when the user explicitly seeks visual, geometric, or editable reconstruction. Label the output `appearance reconstruction`; do not use it as a scientific route.
4. **Essentially non-identifiable content.** Choose `original-case-blocked` immediately when the requested data, coordinate mapping, or generation method cannot be identified from pixels and is necessary for the user's requested reproduction. State the smallest additional material that could change the route, such as the paper and figure reference, a higher-resolution original, readable axis metadata, source data, plotting code, method description, or parameter values. Do not search broadly or fit guessed data merely to avoid a blocker.
5. **Semantic schematic.** Hand off terminally under [diagram-handoff.md](diagram-handoff.md) when meaning is carried mainly by labelled objects, connectors, formulas, grouping, containment, or topology.

Image-derived reconstruction covers the first three outcomes only. The fourth is a precise blocker, not a failed attempt at image reconstruction.

An unqualified request to "reproduce this image" is not permission to downgrade a non-identifiable scientific target to appearance-only work. Offer appearance reconstruction as a distinct option only when it would satisfy the user's actual objective.

Never present a pixel-derived reconstruction as a scientific conclusion or paper claim.

## Adaptive route

For each target:

1. Bind the verified target identity.
2. Describe only visible marks, coordinate systems, panels, labels, and relationships.
3. Identify resolution, line width, occlusion, compression, perspective, and antialiasing limits that matter to the requested artifact.
4. Apply the identifiability gate and define the artifact and visible/geometric observable it must preserve.
5. Select the smallest suitable method: calibrated digitization, measurement, tracing/vectorization, layout reconstruction, plotting-code regeneration, or appearance optimization.
6. State material assumptions, non-identifiability, uncertainty, and acceptance criteria before iterative fitting.

When axes permit calibration, quantify uncertainty from pixel resolution, mark width/size, and coordinate mapping. Without legible axes, restrict results to normalized or relative geometry.

Prioritize the first useful V0. Before expanding investigation with another search branch, delegated task, broad probe, or additional fitting run, name internally the visible discrepancy or unknown and continue only when resolving it can change the required artifact, validation, safety, or material cost. Normal reads and commands inside the chosen step need no per-call justification. Do not reverse-search an unidentified image merely to avoid a blocker. Search for paper context only when a concrete visible identifier or user-supplied candidate makes the check bounded and identity resolution can change the route. Use no fixed iteration count.

Validate only what the image can identify: coordinate mapping; panel, axes, legend, and annotation structure; geometry/topology; ordering, intersections, peaks, and visible trends; requested appearance; editability; and rerunnability. Use labelled comparisons or overlays only when they resolve a material acceptance question and target-pixel rights permit them. Never report fitted values as independent scientific evidence.

Stop when acceptance criteria pass or another change would only chase pixels without improving the required artifact. Preserve V0 and informative negative or failed attempts internally; do not expose redundant fitting versions in the customer folder.

## Customer language and delivery

For digitized or partial results, make the boundary prominent:

> This result redraws only geometry or values observable from the supplied image, with stated uncertainty. It does not recover or validate the original data, method, experiment, or scientific conclusion.

For appearance-only work, say that it is an appearance reconstruction. For an `original-case-blocked` outcome, state the missing identifiable element and the minimum material needed to change the route; do not supply a speculative reconstruction as if it were a result.

Use [delivery-contract.md](delivery-contract.md) to assemble the customer folder. Include the selected reconstruction, rerun essentials when requested or useful, derived measurements needed to understand it, visible uncertainty, provenance, rights, and material limitations. Keep raw traces, QA overlays, internal manifests, search history, and intermediate fits in the transient workspace. Do not redistribute restricted target pixels.
