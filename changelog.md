# Changelog

This file records user-visible changes in Bernardyn. Update it, together with
the relevant user documentation, whenever a feature is added or an existing
behavior changes.

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
- **Copy graph image** support (Edit menu / Cmd/Ctrl+C) and **Print graph…**
  in the File menu.
- A graph reset control that restores default graph settings while preserving
  loaded curves and their styles.
- Background application choices: the whole canvas or only the plot area.
- Rectangle/box annotations with fill and outline, rendered behind plotted
  data.

### Changed

- HDF5/NXcanSAS curve labels use the sample component immediately before a
  `sasdata` group (for example, `PP15_25C_1min`); otherwise they use the
  filename rather than a long HDF5 path.
- The **Legend columns** control has a wider field.
- Arrow-button edits to **Axes: Width** and **Legend columns** redraw live at
  a rate-limited maximum of ten updates per second; Enter applies immediately.
- Output width, height, and DPI now determine the pixel dimensions of PNG/JPEG
  exports and clipboard images.

### Fixed

- Legend controls now recreate the PyQtGraph legend correctly after rerendering.
- Log-axis labels no longer retain stale PyQtGraph SI scaling after a rerender;
  the ticks now always show the plotted data values.
- Dock widgets have stable IDs, so saved window layouts can restore without
  Qt's missing-`objectName` warnings.
- Boxed axes retain a right-side standoff so the right border is not obscured
  by an adjacent panel. Dense log tick labels are pruned more aggressively.
