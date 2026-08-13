# Image-derived reconstruction

## When this mode applies

Use `image-derived-reconstruction` when one or many target images are supplied without a paper that can establish their scientific context. This mode is a legitimate reconstruction service with a deliberately narrower claim boundary; it is not a degraded or speculative scientific reproduction.

If a paper is later supplied and the targets are reliably matched, create a new target/report version and reassess them under `scientific-reproduction`. Do not silently upgrade the existing assessment.

## What may be reconstructed

Depending on visible evidence and resolution, candidate routes may include:

- chart type, panel layout, axes, ticks, legends, annotations, colors, typography, and relative geometry;
- curve, point, bar, contour, boundary, or region digitization with stated uncertainty;
- visual tracing or vectorization;
- approximate data series inferred from visible marks;
- code that regenerates an appearance-matched chart from the derived geometry;
- editable layout or appearance reconstruction when the target type permits it.

Keep derived numeric values, layout measurements, and styling parameters traceable to the target image and record every assumption.

## What this mode cannot establish

Without independent evidence, do not claim to have recovered or validated:

- the authors' original raw data or exact numeric values hidden by rasterization;
- the original preprocessing, model, algorithm, implementation, or parameter history;
- experimental conditions, sample identity, random seed, calibration, or uncertainty procedure;
- the figure's role in a paper or the paper claim it was intended to support;
- the correctness, reproducibility, or scientific validity of the underlying research.

Do not label digitized points as observed experimental data. Do not present an appearance fit as `direct-recompute`, `mechanism-reproduction`, or `alternative-validation`.

## Analysis and routes

For each target:

1. Record the verified target ID and hash.
2. Describe only visible marks, axes, labels, panels, and relationships.
3. Identify resolution, occlusion, compression, perspective, or anti-aliasing limits.
4. Define the requested output: editable vector, approximate data, plotting code, layout reconstruction, or another explicit artifact.
5. Select a method such as manual measurement, calibrated digitization, vector tracing, layout reconstruction, or appearance optimization.
6. State assumptions, non-identifiability, uncertainty, and what the route cannot recover.
7. Define visual/geometric acceptance criteria before execution.

When the axes provide usable calibration, report digitized values with uncertainty justified by pixel resolution, line width, marker size, and calibration error. When axes are absent or illegible, restrict claims to normalized or relative geometry.

## Validation

Validate against image-derived criteria, not paper claims:

- correct canvas, panel count, coordinate mapping, axes, legend, and annotations;
- curve/mark geometry within a declared pixel or calibrated-coordinate tolerance;
- topology, ordering, intersections, peaks, and relative trends visible in the target;
- color and typography within a declared appearance tolerance when requested;
- editable structure or rerunnable generation code when required;
- no claim beyond what the supplied pixels can identify.

Use side-by-side views or transparent overlays only for inspection. Keep the reference and reconstruction visibly labeled. Never optimize against the image while reporting the fitted values as independent scientific evidence.

## Report language

Make the workflow mode prominent. Use language such as:

> This route reconstructs visible geometry and appearance from the supplied image. It does not recover or validate the original data, method, experiment, or scientific conclusion.

The local report must display every verified target. It should show the reconstruction objective, observable primitives, route, uncertainties, expected outputs, and acceptance criteria. Paper-claim and evidence-role sections must be absent or explicitly marked not available—not invented.

## Handoff

Deliver one terminal run bundle governed by [run-bundle-contract.md](run-bundle-contract.md). Put derived measurements, reconstruction source, outputs, labelled comparison/overlay artifacts, uncertainty notes, environment evidence, and provenance in its declared shared/per-target locations. Keep image-derived results separate from any later paper-grounded reproduction run, and reference restricted target bytes instead of redistributing them in a shareable bundle.
