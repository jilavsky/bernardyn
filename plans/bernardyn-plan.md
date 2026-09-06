# Bernardyn roadmap and rebuild status

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
- The `0.0.1b1` package has been published to PyPI and successfully installed
  and exercised on a separate user computer.

## Deferred by scope

The post-1.0 detector milestone will add calibrated `IMAGE_2D` data, image and
contour renderers, masks/ROIs, and color-scale state without changing the root
container schema. Model fitting, reduction, destructive source edits, movies,
and PDF advertising remain outside 1.0.

## Next priority: PyIrena result plotting

### Feasibility decision

There is no rendering or package-format obstacle to plotting PyIrena results.
Bernardyn already renders resolved generic `x`/`y` `PlotSeries`, supports several
series in one graph, and archives their data and presentation. The limitation is
earlier in the pipeline: the canonical `Dataset` currently assumes every 1D
curve is `q` versus `intensity` and every range is a Q range.

That assumption is correct for measured scattering, fitted intensity, model
components, and calculated background. It is not semantically correct for size
distributions, residuals, correlation functions, spectral density, or future
result curves. These must not be represented by pretending that radius is Q and
that a distribution is intensity.

| PyIrena result | Bernardyn readiness | Required work |
|---|---|---|
| Measured and fitted I(Q) | High | Import and grouping UI; existing transforms and renderer can be reused |
| Model components and background I(Q) | High | Import roles, default styles, and relationship metadata |
| Residuals versus Q | Medium | Generic curve semantics and appropriate default axes |
| Size/number/cumulative distributions versus radius | Medium | Generic curve semantics, units, uncertainty, and result-specific graph defaults |
| Correlation and spectral curves | Medium | Same generic curve support; no new renderer is required |
| Scalar fit parameters and uncertainties | Different concern | Preserve as metadata; later offer tables, annotations, or across-sample parameter plots |

### PyIrena public boundary

Bernardyn must consume a small public PyIrena result API instead of importing
private plotting helpers or duplicating each tool's HDF5 paths. PyIrena already
has a `TOOL_REGISTRY` whose plot specifications describe X/Y paths, units,
labels, and plot types. Promote that knowledge through typed public calls such
as:

- `discover_result_curves(path) -> list[ResultCurveLocation]`
- `load_result_curve(location) -> ResultCurveRecord`

`ResultCurveRecord` should include immutable X/Y and optional dX/dY arrays,
axis semantic IDs, units and labels, result/tool ID, curve role, relationship
or result-group ID, source provenance, and suggested presentation metadata.
The public API should support registry additions without requiring a Bernardyn
release for every new PyIrena analysis tool.

Add to the PyIrena roadmap a separate exporter that can create a Bernardyn
package from any PyIrena graph/result selection. That exporter should call a
documented headless Bernardyn API; PyIrena must not construct Bernardyn HDF5
groups directly.

### Bernardyn model evolution

Add explicit scientific semantics rather than a collection of special cases:

- A generic immutable 1D curve representation with `x`, `y`, optional `dx` and
  `dy`, axis semantic IDs, labels, and units.
- Stable curve roles such as `measured`, `fit`, `component`, `background`,
  `residual`, `distribution`, and `derived`.
- A relationship/group ID so data, total fit, components, residuals, and fit
  metadata remain associated after import and package round trips.
- Transform applicability declarations. Scattering linearizations apply to
  Q/I curves, while generic curves initially use the identity transform.
- Rename model concepts such as `q_range` to `visible_x_range` at the public
  boundary, with migration support for existing graph documents.
- Evolve the native package schema deliberately (expected schema v2), with a
  pure v1-to-v2 migration and continued read support for all beta packages.
  Do not silently change the meaning of the v1 `Q` and `I` datasets.

### Result-oriented user workflow

- The source browser shows a file's primary scattering data and a separate
  **PyIrena results** tree grouped by analysis and saved result.
- Users can select one curve, several result curves, or a convenient
  **Data + fit** bundle.
- Data, fit, background, and components receive recognizable default styles but
  remain independently editable.
- Result bundles may create a primary I(Q) graph and a residual/distribution
  graph in one operation; users can override that choice.
- Scalar fit results are carried as graph/package metadata even before a scalar
  table or parameter-series UI is implemented.

### Delivery increments

1. **R1 — I(Q) result overlays (small/medium).** Add the PyIrena public result
   discovery contract; import data, total fit, background, and model components;
   preserve roles/relationships; add numerical and package round-trip tests.
2. **R2 — Generic 1D scientific curves (medium/large).** Generalize the
   canonical model, transform compatibility, inspector terminology, source
   browser, and package schema. Add distributions, residuals, correlation, and
   spectral curves.
3. **R3 — Result workflow polish (medium).** Add result bundles, linked default
   styles, scalar metadata display, templates, documentation, and cross-platform
   GUI acceptance tests.

R1 offers immediate value and can precede the larger model migration. R2 should
be completed before many non-I(Q) result types are added; otherwise temporary
Q/intensity aliases will become persistent technical debt.

## AI and MCP strategy

### Product decision

An MCP interface is useful if it exposes a small set of scientific plotting
intentions, not every GUI control. A single tool with dozens of styling fields
would be difficult for models to select correctly, difficult to version, and
hard for users to review. Templates plus stable transform IDs make a much
better contract.

The first useful AI workflow is deliberately narrow: select datasets or
PyIrena results, request a known view such as `porod`, apply a named template,
and create a preview, image, or self-contained Bernardyn package. This directly
fills gaps such as generating a Porod plot from PyIrena data without teaching
the agent every PyQtGraph setting.

### Headless API before protocol adapter

First extract a documented, GUI-independent application service used by the
GUI, Python callers, command line, PyIrena export, and eventually MCP. A request
should describe intent and return a structured result, for example:

```text
inspect source -> select curve IDs -> create graph from recipe
               -> validate -> save package and/or export preview
```

The service owns discovery, loading, transforms, templates, graph documents,
validation, and atomic package writing. The MCP server is then a thin adapter;
it must not automate widgets or maintain a second graph-building architecture.

### Proposed narrow MCP surface

- `inspect_data`: list files, datasets, result curves, units, sizes, and
  warnings without returning full scientific arrays.
- `list_plot_recipes`: list stable views and compatible named templates.
- `create_plot`: create one graph from selected curve IDs, a recipe/template,
  and a few safe overrides such as title and physical dimensions.
- `create_result_overlay`: create a data/fit/components plot from a PyIrena
  result group.
- `describe_package`: return the graph manifest, series roles, transforms,
  provenance, and preview links.
- `export_plot`: render an existing package graph to a supported 2D format.

MCP resources can expose package manifests, schema documentation, templates,
and previews by URI. Tools perform discovery and creation. Full arrays should
remain in source/package files unless explicitly requested, keeping model
context small.

### Safety and scope

- Restrict file access to user-authorized roots and resolve paths before use.
- Do not overwrite an existing output unless the request explicitly permits it.
- Return validation warnings and the exact selected curves/recipe for review.
- Keep initial rendering 2D and deterministic. Defer OpenGL/3D MCP rendering
  until offscreen behavior is reliable on all supported platforms.
- Require explicit user approval at the client for state-changing tool calls.
- Do not expose fitting or source-file mutation through the Bernardyn MCP
  server; those remain PyIrena responsibilities.

### MCP delivery increments

1. **M0 — Headless facade (medium).** Define typed plot requests/results and
   refactor the GUI to use the same service where practical.
2. **M1 — Local recipes (small).** Add a CLI/Python API for inspection, Porod
   and other standard views, named templates, package creation, and 2D export.
3. **M2 — MCP prototype (small/medium after M0/M1).** Wrap the narrow tools and
   resources above; test prompts against ambiguous multi-entry files and confirm
   deterministic selections.
4. **M3 — Stabilization (medium).** Add permissions guidance, structured error
   recovery, documentation, client compatibility tests, and packaged-server
   installation tests.

The result importer has very high near-term user value. The template/recipe MCP
surface has high value for repeatable AI-assisted and batch plotting at moderate
cost. Free-form AI control of every GUI option and live GUI manipulation have
lower value and are not planned until real usage demonstrates a need.

### Indicative effort and value

These are engineering estimates for one experienced agent working in the
existing repositories, including focused tests and documentation. They are
planning ranges, not release-date commitments.

| Increment | Indicative effort | User value | Dependency |
|---|---:|---|---|
| R1: I(Q) data/model overlays | 3–5 engineering days | Very high | Small PyIrena public API addition |
| R2: generic 1D curves and schema migration | 7–10 engineering days | Very high | Schema/design review before implementation |
| R3: result workflow polish | 3–5 engineering days | High | R1 and most of R2 |
| M0–M1: headless API and local recipes | 5–8 engineering days | High even without MCP | Result/curve contracts should be stable |
| M2: narrow MCP prototype | 2–4 engineering days | High for AI users | M0–M1 |
| M3: production hardening | 4–7 engineering days | Medium/high | Real prompt and client testing |

The recommended order is R1, the R2 data model/schema design, R2
implementation, then M0–M2. This lets the MCP layer expose both scattering and
result curves through one stable vocabulary. R3 and M3 can then be guided by
feedback rather than guesses about every desired option.

## Acceptance criteria for the next roadmap

- A PyIrena result file can add measured data and its total fitted I(Q) to one
  Bernardyn graph without manual HDF5 mapping.
- A saved overlay reopens without the original PyIrena file and preserves curve
  roles, grouping, metadata, styles, canonical arrays, and snapshots.
- Radius distributions retain radius/distribution semantics and units throughout
  loading, inspection, rendering, export, and package round trip.
- A newly registered PyIrena result curve can be discovered through the public
  result API without adding an HDF5 path to Bernardyn.
- A headless recipe can generate a Porod graph package and preview with no Qt
  widget interaction.
- The MCP prototype can perform the same operation using a short request with a
  transform ID and template ID, and returns a compact manifest plus artifact
  paths rather than flooding model context with arrays.
- Existing `.bernardyn.h5` v1 packages and current scattering-data workflows
  remain readable and behaviorally unchanged.
