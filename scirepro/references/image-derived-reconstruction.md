# Image-derived reconstruction

Use `image-derived-reconstruction` when supplied target images lack reliable paper context. Reconstruct only identifiable content from pixels; do not imply recovery or validation of the original research process. If reliable paper context later establishes identity, create a new target and route rather than silently upgrading the result.

## Scope

Depending on the user's objective and visible evidence, reconstruct:

- panel layout, axes, ticks, legends, annotations, colors, typography, and relative geometry;
- visible curves, points, bars, contours, boundaries, or regions with stated uncertainty;
- approximate data series through calibrated digitization;
- rerunnable plotting code, editable vectors, or appearance/layout reconstruction.

Keep every derived value and styling decision traceable to the source image. Route work outside scientific chart/image reconstruction to the appropriate visual skill; semantic schematics belong terminally to `sci-diagram-pptx` under [diagram-handoff.md](diagram-handoff.md).

## Claim boundary

Pixels alone cannot establish raw data, hidden exact values, preprocessing, model, implementation, parameter history, experimental conditions, sample identity, seed, calibration, uncertainty procedure, figure role, or paper claim. Do not label digitized points as original observations or present an appearance fit as direct recomputation, mechanism reproduction, or alternative validation.

## Adaptive route

For each target:

1. Bind the verified target identity.
2. Describe only visible marks, coordinate systems, panels, labels, and relationships.
3. Identify resolution, line width, occlusion, compression, perspective, and antialiasing limits that matter to the requested artifact.
4. Define the artifact and visible/geometric observable it must preserve.
5. Select the smallest suitable method: calibrated digitization, measurement, tracing/vectorization, layout reconstruction, plotting-code regeneration, or appearance optimization.
6. State material assumptions, non-identifiability, uncertainty, and acceptance criteria before iterative fitting.

When axes permit calibration, quantify uncertainty from pixel resolution, mark width/size, and coordinate mapping. Without legible axes, restrict results to normalized or relative geometry.

Prioritize the first useful V0. Before expanding investigation with another search branch, delegated task, broad probe, or additional fitting run, name internally the visible discrepancy or unknown and continue only when resolving it can change the required artifact, validation, safety, or material cost. Normal reads and commands inside the chosen step need no per-call justification. Do not search for missing paper context or hidden data unless it can change the route. Use no fixed iteration count.

Validate only what the image can identify: coordinate mapping; panel, axes, legend, and annotation structure; geometry/topology; ordering, intersections, peaks, and visible trends; requested appearance; editability; and rerunnability. Use labelled comparisons or overlays only when they resolve a material acceptance question and target-pixel rights permit them. Never report fitted values as independent scientific evidence.

Stop when acceptance criteria pass or another change would only chase pixels without improving the required artifact. Preserve V0 and informative negative or failed attempts internally; do not expose redundant fitting versions in the customer folder.

## Customer language and delivery

Make the boundary prominent:

> This result reconstructs visible geometry, values, or appearance from the supplied image. It does not recover or validate the original data, method, experiment, or scientific conclusion.

Use [delivery-contract.md](delivery-contract.md) to assemble the customer folder. Include the selected reconstruction, rerun essentials when requested or useful, derived measurements needed to understand it, visible uncertainty, provenance, rights, and material limitations. Keep raw traces, QA overlays, internal manifests, search history, and intermediate fits in the transient workspace. Do not redistribute restricted target pixels.
