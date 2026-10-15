# Changelog

This file records user-visible changes in Bernardyn. Update it, together with
the relevant user documentation, whenever a feature is added or an existing
behavior changes.

## Unreleased

### Added

- The `bernardyn` launcher accepts `--version`, `-version`, `--v`, and `-V`.
  The desktop app shows its version in the status bar and in **About Bernardyn**.
- A graph warns when its curves have different units (for example arbitrary
  and absolute intensity) and so are not on a common scale. Mixing is still
  allowed.
- **Add pyIrena results…** now handles many files at once with a single
  dialog. Choose the analysis and the curves you want; the dialog shows how
  many files offer each choice, where the curves will go, and which files will
  be skipped and why.
  - Each chosen curve kind becomes one comparison graph holding every file's
    curve, with one colour per file.
  - The whole import is one Undo step.
- Modeling imports include the file's primary scattering curve as the measured
  data, when the file has one.
- Modeling population volume distributions can be imported (one graph for all
  populations). The new `modeling_volume_distribution` recipe does the same
  from the Python API, CLI, and MCP.

### Changed

- Axis labels show compact units (`q [Å⁻¹]`, `Intensity·q² [cm⁻¹·Å⁻²]`,
  `Radius [Å]`). An empty graph takes its labels from the first curve added,
  unless you have typed your own labels.
- Saved pyIrena result curves take their units from the HDF5 file. A fitted
  model or component shares the units of the measured data it was fitted to.
- Size distribution curves are labelled with the stored units, e.g. volume
  distributions show `vol. fraction·Å⁻¹`.
- PySide6 6.10.x is excluded, matching pyIrena's Qt plotting extra.

### Fixed

- Changing the scientific view (Kratky, Porod, Guinier, …) no longer drops the
  units from both axis labels.
- WAXS Peak Fit data + fit graphs are labelled in arbitrary units rather than
  `cm⁻¹`.
- Simple Fits data and model curves are no longer shown in different units on
  one axis. pyIrena stores the model as `arb`, but it was fitted to the
  absolute data.
- Graph packages and templates written by a newer Bernardyn open instead of
  failing, and settings this version does not know are kept when the package
  is saved again. A damaged graph document is reported as an invalid package.
- A graph edit that fails, such as applying a Kratky template to a residual
  graph, now shows its error. It no longer leaves an empty Undo entry, and a
  multi-step change (for example a pyIrena result import) is rolled back
  completely.
- **Reset graph to defaults** keeps the graph's scientific view and labels its
  axes for that view, rather than showing Kratky data under I(Q) labels.
- The Python API and CLI reject an unsupported image file type before writing
  any output, so a failed request no longer leaves a package without its image.
- Importing residuals or distributions from several files no longer opens a
  separate graph for each file.
- The `dimensionless_kratky` recipe now takes I₀ and Rg from each dataset's own
  metadata when no explicit values are given, as documented.
- Error bars that reach zero or below on a logarithmic axis no longer emit
  numerical warnings; they were already hidden.
- Reading saved results is faster: each file is read once per import rather
  than once per curve kind.
- Estimated uncertainties are now recorded. Text files without an
  uncertainty column (errors set to a percentage of I) are marked "estimated"
  in saved packages. The dataset tooltip shows this, the graph warns while
  such error bars are shown, and ITX and H5XP exports note it.
- I₀ and Rg for the dimensionless Kratky view are taken only from top-level
  dataset metadata (as written for pyIrena Simple Fits Guinier results), never
  from nested values such as a second Unified Fit level. The graph notes when
  values came from the data.
- A package lock held by Bernardyn on another computer no longer expires after
  30 seconds. Opening or saving over a locked package names the lock's owner
  and offers **Break lock** for a lock left by a crash.
- Closing a graph tab activates its neighbour, and new graphs never repeat an
  existing "Scattering plot N" title.
- Saving a template whose file name already exists asks before replacing it.
- CSV and ITX exports are written atomically, so a failed export cannot leave
  a truncated file.

## 0.0.1b7 — 2026-10-02

### Added

- Saved pyIrena 1.2.0b2+ results for Modeling, Simple Fits, WAXS Peak Fit,
  and Carbon fitting can be imported in the GUI and plotted through the Python
  API, CLI, and MCP recipes. Modeling population curves, WAXS peaks and
  background, and Carbon fit components are included.
- Size Distribution imports now include stored number and surface distributions.

### Changed

- Saved-result discovery follows pyIrena's HDF5 schema; the minimum supported
  pyIrena version is 1.2.0b2.

## 0.0.1b6 — 2026-09-20

### Added

- Draggable, labelled one-decade power-law slope guides for log-log SAXS
  graphs, including editable arbitrary exponents and persistent annotations.
- **File → Recent workspaces** keeps the last ten full workspace packages and
  opens them in a new window or activates an existing one. **New window** and
  **Open workspace in new window…** support parallel experiments, including
  when a macOS app launcher permits only one Bernardyn process.
- The left **Data browser** and the Graph Inspector's **Datasets** tab now
  filter listed curves by ordinary SAS data and saved Unified Fit or Size
  Distribution result roles. The inspector list has a draggable height divider.
- The **View** menu now includes **Open Data Browser**, **Open Graph
  Inspector**, and **Reset panel layout** recovery commands.

### Changed

- Fixed Graph Inspector title font-size rendering; title font size and family
  now apply to the on-screen plot. **Canvas (px) → Set** sizes the displayed
  2-D canvas to the requested pixels, and error-bar controls now read
  **Show errors: Y / X**.
- Editable packages now hold a cross-process lock for the lifetime of their
  window. A second editor for the same package is refused to prevent silent
  last-save-wins data loss; **Save As** creates an independent workspace.
- Data-browser actions use two columns to keep a floating browser compact.
- The Data browser and Graph Inspector always reopen as visible, docked panels
  after a workspace layout is restored; they may still be floated during use.

## 0.0.1b5 — 2026-09-16

### Added

- **bernardyn-mcp** exposes five grouped local-MCP tools for data discovery,
  recipe-based package/preview creation, package inspection, and 2-D export.
  It confines agent output to an authorised root or a temporary cache and does
  not expose source mutation, fitting, raw HDF5 writing, or code execution.
- A typed public Python recipe facade and **bernardyn-plot** CLI now create
  validated raw I(Q), Porod, Kratky, data+fit, residual, and volume-
  distribution graph packages. Optional PNG/JPEG/SVG output is rendered
  offscreen through the same 2-D renderer used by the desktop application.
- **Add pyIrena results…** now also imports public-reader residuals and Size
  Distribution volume distributions as typed generic curves on separate graph
  tabs. Generic curves preserve their axis semantics, units, provenance, and
  optional uncertainty without being treated as scattering I(Q) data.
- Native graph packages now use schema v2 for typed generic curves while
  retaining full read compatibility with v1 scattering packages.
- **Add pyIrena results…** imports a selected saved Unified Fit or Size
  Distribution as a paired measured-data/model I(Q) overlay. Result roles,
  fit metadata, and source provenance are embedded in the graph package.
- Right-click selected datasets in the active-graph list to **Copy selected
  to…** or **Move selected to…** an existing graph or a newly created 2-D
  graph. Transfers are undoable and retain the workspace's shared data catalog.
- **New 2D graph** now has the Ctrl/Cmd+Shift+N shortcut.

### Fixed

- Graphs now retain their selected scientific view when data are added later;
  parameterized views obtain values independently for each imported dataset.
- Failed graph transformations and imports validate resolved data before
  changing the in-memory document, snapshots, warnings, or undo history.
- Asynchronous file imports are bound to their original workspace and graph,
  preserve selection order, and arrive as one undoable batch. Stale completions
  are discarded rather than redirected into a new workspace.
- Legend renames immediately update rendered and displayed-data export labels
  without recalculating archived numerical snapshots.
- Dataset removal, reordering, graph creation, and graph closing now participate
  in undo/redo with their associated plot snapshots.
- Graph templates retain boxed axes and background scope while preserving each
  target dataset's own transform parameters.
- Image export verifies the write before reporting success and preserves an
  existing artifact if the replacement fails.
- CSV and ITX displayed-data exports now omit hidden series by default.

## 0.0.1b4 — 2026-09-09

### Added

- An **Autoscale** button beside the automatic range controls. It enables both
  axes and immediately fits the displayed data.
- Independent legend-symbol sizing, alongside the other legend controls in
  the **Datasets** tab.
- Separate **Show X** (Q resolution) and **Show Y** (intensity uncertainty)
  error bars, with optional end caps and adjustable cap length. The default
  cap length is 0.5% of the relevant axis span.

### Fixed

- Switching to a 3D renderer no longer lets a missing or incompatible GLX
  configuration abort Bernardyn. A disposable preflight check now detects the
  problem and uses a 2D waterfall fallback with an explanatory warning.
- Windows package saves now open their temporary HDF5 file with a writable
  descriptor for the final disk-sync operation, as required by Windows.
- Bernardyn installations now include `six`, which PyIrena 1.1.0 currently
  requires for its public HDF5/shared scattering-data API. `bernardyn-doctor`
  shows the underlying import error and the repair command for older
  environments.
- Legends now inherit the selected graph font family and axis color, and their
  text scales with the rest of the graph in output preview, clipboard, and
  image export.
- Presentation-only graph controls no longer reset an interactive zoom or
  refit the axes.

### Changed

- Bernardyn now requires the stable PyIrena 1.1.0 shared API rather than its
  pre-release identifier.
- Legend controls are grouped with the datasets they describe rather than with
  the general graph settings.
- Dataset line, symbol, and error-width spin boxes now update while their arrow
  buttons are used, at the existing rate-limited maximum of five redraws per
  second.

## 0.0.1b3 — 2026-09-08

### Added

- **Copy graph image** support (Edit menu / Cmd/Ctrl+C) and **Print graph…**
  in the File menu.
- A graph reset control that restores default graph settings while preserving
  loaded curves and their styles.
- Background application choices: the whole canvas or only the plot area.
- Rectangle/box annotations with fill and outline, rendered behind plotted
  data.
- An on-demand **Preview output…** window showing the exact export pixel image,
  with independent copy and print controls.

### Changed

- Arrow-button edits to **Axes: Width** and **Legend columns** redraw live at
  a rate-limited maximum of five updates per second; Enter applies immediately.
- Output width, height, and DPI now determine the pixel dimensions of PNG/JPEG
  exports and clipboard images.
- The interactive 2-D canvas now previews the selected output aspect ratio
  using canvas-coloured padding rather than changing its absolute screen size.
- Typography size controls now redraw from their arrow buttons after a
  rate-limited 200 ms delay, and their fields are wider for readability.
- The Graph inspector combines background colour and scope on one row and
  places **Preview output…** beside **Reset graph to defaults…**.
- The interactive graph displays its current on-screen canvas pixel size.

### Fixed

- The cross-platform GitHub Actions test workflow no longer uses the
  unavailable `runner` context in job-level environment configuration.
- Boxed axes retain a right-side standoff so the right border is not obscured
  by an adjacent panel; the standoff now uses the graph canvas colour. Dense
  log tick labels are pruned more aggressively.
- Boxed right axes reserve a small internal graphics-view margin so their line
  is not clipped in the interactive window.

## 0.0.1b2 — 2026-09-06

### Added

- Drag-and-drop import of local files and folders onto **Datasets in active
  graph**, including an empty list. The normal data-selector dialog is used.
- Graph controls for a boxed plot (**Show top and right axes**) and for log
  axes (**Show minor tick labels**).
- Extended selection in **Datasets in graph**. Right-click a selection to
  **Check selected** or **Uncheck selected** curves in one operation.
- An **Update graph** button in the Graph annotation dialog. It applies the
  current annotation values without closing the dialog.
- A red **Documentation** button above the Graph Inspector. It opens the
  local `docs` folder in a source checkout and the GitHub documentation from
  a PyPI installation.
- A user guide covering importing, graph controls, annotations, saving, and
  exporting.
- Automatic reopening of the last successfully opened or saved workspace
  package at application startup. Single-graph package exports do not replace
  the remembered workspace.

### Changed

- HDF5/NXcanSAS curve labels use the sample component immediately before a
  `sasdata` group (for example, `PP15_25C_1min`); otherwise they use the
  filename rather than a long HDF5 path.
- The **Legend columns** control has a wider field.

### Fixed

- Legend controls now recreate the PyQtGraph legend correctly after rerendering.
- Log-axis labels no longer retain stale PyQtGraph SI scaling after a rerender;
  the ticks now always show the plotted data values.
- Dock widgets have stable IDs, so saved window layouts can restore without
  Qt's missing-`objectName` warnings.
