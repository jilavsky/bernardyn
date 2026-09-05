# Bernardyn 1.0 rebuild status

This file replaces the superseded 0.1 module plan. The implemented design is
the model-driven pipeline:

`source adapter → canonical Dataset → PlotTransform → PlotSeries → Renderer`

The normative persistent-format specification is
[`../bernardyn/schemas/graph-package-v1.md`](../bernardyn/schemas/graph-package-v1.md),
and extension guidance is in
[`../bernardyn/EXTENDING.md`](../bernardyn/EXTENDING.md).

## Implemented for 1.0 beta

- PyIrena public discovery/loading and H5XP writer boundary with `qtplot` extra.
- Immutable canonical arrays and controller-owned graph/workspace state.
- Source browser actions for all NXcanSAS/simple-HDF5 entries, mapping fallback,
  and read-only two-to-four-column text import.
- Eleven requested Irena plotting views with masking and analytical uncertainty
  propagation.
- Independent graph tabs, dataset catalog, styling, annotations, axis/legend/
  typography/output controls, presets, templates, and undo/redo.
- Native `.bernardyn.h5` graph/workspace packages with deduplication, checksums,
  snapshots, previews, renderer data, atomic save, recovery, and compatibility
  behavior.
- Isolated OpenGL waterfall/surface rendering, shared-grid interpolation,
  metadata series positions, camera/projection persistence, palette colors, and
  raster export with 2D fallback.
- PNG/JPEG/SVG, clipboard, CSV, ITX, and separate Igor H5XP data export.
- Pytest/pytest-qt coverage, real PyIrena fixture round-trip, performance tests,
  diagnostics, CI matrix, wheel/sdist metadata checks, and Conda recipe.

## Deferred by scope

The post-1.0 detector milestone will add calibrated `IMAGE_2D` data, image and
contour renderers, masks/ROIs, and color-scale state without changing the root
container schema. Model fitting, reduction, destructive source edits, movies,
and PDF advertising remain outside 1.0.
