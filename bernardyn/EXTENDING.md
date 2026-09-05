# Extending Bernardyn

Bernardyn's runtime pipeline is:

`SourceAdapter → Dataset → PlotTransform → PlotSeries → Renderer`

Qt controls submit immutable `GraphDocument` changes to the controller. They do
not own scientific arrays or reconstruct state from rendered items.

## Source adapters

Implement the `SourceAdapter` protocol in `bernardyn.io.sources`: a stable
`id`, supported `suffixes`, `discover(path)`, and `load(location, ...)`. Publish
an instance or zero-argument class under the `bernardyn.sources` Python entry
point group. Loading must be read-only and return `ScatteringRecord`.

## Plot transforms

Implement the `PlotTransform` protocol in `bernardyn.core.transforms`. A
transform declares its stable ID, component version, labels, default axes, and
`ParameterSpec` values. `apply()` returns a `PlotSeries` with source-index
mapping, uncertainty propagation, units, and warnings. Publish it under
`bernardyn.transforms`.

Transforms are pure numerical operations. They must never mutate a `Dataset`.
Add numerical tests for the valid domain, every uncertainty derivative, and
NaN/zero/negative edge cases.

## Renderers

Publish a `RendererRegistration` under `bernardyn.renderers`. Its factory
creates a QWidget implementing:

```python
update(graph_document, snapshots)
capture_snapshot(width=1200) -> bytes
save_image(path, width=None) -> Path
```

Renderer IDs and versions are persisted. Unknown renderers are retained and
opened from their embedded PNG preview when available. Renderer-specific
numeric arrays belong under `/graphs/<uuid>/renderer-data`, never inside
executable or pickled state.

## Compatibility rules

- Keep stable IDs forever once released.
- Increment a component version when its numerical or visual interpretation
  changes.
- Preserve unknown JSON keys when implementing a schema migration.
- Do not store Python pickles, callable names used as recreation code, HDF5
  external links, or absolute paths required for package opening.
- Treat templates as dataset-free configuration; portable packages are the
  only archival graph format.
