# Image-derived reconstruction

Use `image-derived-reconstruction` when supplied target images lack reliable paper context. It reconstructs identifiable content from pixels; it is not a claim about the original research process. If paper context later establishes identity, create a new target/route version rather than silently upgrading the result.

## Scope

Depending on the user’s objective and visible evidence, reconstruct:

- panel layout, axes, ticks, legends, annotations, colors, typography, and relative geometry;
- visible curves, points, bars, contours, boundaries, or regions with stated uncertainty;
- approximate data series through calibrated digitization;
- rerunnable plotting code, editable vectors, or appearance/layout reconstruction.

Keep every derived value and styling decision traceable to the source image. Prefer another visual skill when the requested deliverable is outside scientific chart/image reconstruction; semantic schematics belong to `sci-diagram-pptx`.

## Claim boundary

Pixels alone cannot establish the authors’ raw data, hidden exact values, preprocessing, model, implementation, parameter history, experimental conditions, sample identity, seed, calibration, uncertainty procedure, figure role, or paper claim. Do not label digitized points as original observations or present an appearance fit as direct recomputation, mechanism reproduction, or alternative validation.

## Route and validation

For each target:

1. Bind the verified target ID and hash.
2. Describe only visible marks, coordinate systems, panels, labels, and relationships.
3. Identify resolution, line width, occlusion, compression, perspective, and antialiasing limits.
4. Define the requested artifact and the visual/geometric observable it must preserve.
5. Select an appropriate method: calibrated digitization, measurement, tracing/vectorization, layout reconstruction, plotting-code regeneration, or appearance optimization.
6. State assumptions, non-identifiability, uncertainty, and acceptance criteria before iterative fitting.

When axes permit calibration, quantify uncertainty from pixel resolution, mark width/size, and coordinate calibration. Without legible axes, restrict results to normalized or relative geometry.

Validate only what the image can identify: coordinate mapping; panel, axes, legend, and annotation structure; geometry/topology; ordering, intersections, peaks, and visible trends; requested appearance; editability; and rerunnability. Use labelled side-by-side views or overlays for inspection, subject to target-pixel rights. Never report fitted values as independent scientific evidence.

Preserve the first meaningful V0. Iterate only on a concrete visible discrepancy with expected information gain, and stop when criteria pass or another change would only chase pixels without improving the required artifact.

## Delivery language

Make the mode and boundary prominent:

> This result reconstructs visible geometry, values, or appearance from the supplied image. It does not recover or validate the original data, method, experiment, or scientific conclusion.

Deliver the result within the single folder governed by [run-bundle-contract.md](run-bundle-contract.md). Include derived measurements, reconstruction source, outputs, labelled comparisons, uncertainty, environment evidence, and provenance. Keep it distinct from any later paper-grounded reproduction and do not redistribute restricted target pixels.
