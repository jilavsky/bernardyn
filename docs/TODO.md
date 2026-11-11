# Bernardyn — open work

The single list of what is not done yet. It replaces the earlier review and
plan documents (1D review of 2026-11-02, review of 2026-11-09, the roadmap to
1.0, the File browser dock plan, the 1.0 release checklist and the original
specification); they are in git history before the commit that added this
file. Finished work is recorded in [`../CHANGELOG.md`](../CHANGELOG.md), not
here. Remove an item when it ships.

## 1. Testing now — branch `fix/issue-1-code-review` (issue #1)

Every finding of the 2026-11-09 review (B01–B17, D1–D5) is implemented and
has a regression test in `tests/test_code_review_2026_11.py`. Still to check
by hand before merging and closing #1:

- [ ] **Exported images on Windows** (including fractional display scaling)
      and macOS: PNG, SVG, clipboard and print look right; text size is
      physical (12 pt = 1/6 inch), identical for any window size.
- [ ] **Match output** (Graph tab, beside Canvas → Set) gives the on-screen
      canvas the output's text proportions on each platform.
- [ ] **Older-version snapshots**: open a package saved before 1.2 with a
      Dimensionless Kratky graph (or Guinier with multiplier ≠ 1). The note
      shows; Add/Replace/multiplier edits are refused with a clear message;
      Remove and Undo work; **Recompute with current version** clears it.
- [ ] **Guinier multiplier**: slope (Rg) unchanged by the multiplier.
- [ ] **Small numbers**: multiplier `2.5e-9`, annotation at `3.2e-10`.
- [ ] **SSHFS-Win drive at the beamline**: File browser, preview and loading
      many files with the new single source-file lock; check the GUI never
      hangs for long and no spurious "group not found" errors appear.
- [ ] **Generic HDF5**: a plain group with `q`/`intensity` loads; an unknown
      layout opens **Map HDF5 arrays**.
- [ ] Uncaught errors appear in a dialog and in `~/.bernardyn/logs/bernardyn.log`
      (Windows has no console).
- [ ] Then: bump to **1.2.0** (multiplier and image output change results),
      merge, close #1.

## 2. Defects and partial fixes still open

- **File reads on the GUI thread** (rest of B13). Reads are now serialised by
  one lock, but discovery and result surveys still run on the GUI thread,
  once per selected file, so a slow drive can still freeze the window for a
  file read. Move discovery and surveys into cancellable jobs on the
  one-thread pool; confirm on the real SSHFS-Win drive.
- **Small GUI items** (Q11): a new graph from Copy/Move can get a duplicate
  default title (`main_window._transfer_selected_series` uses `len + 1`);
  cancelling the parameter prompt skips pending renders; each import renders
  twice; one modal dialog per failed file instead of one summary with Retry;
  exporting an image without a suffix fails on Linux.
- **Text reader** (Q10): zero/negative uncertainties loaded through pyIrena
  are kept and labelled measured (should be partly estimated);
  semicolon/decimal-comma CSV fails with "no numeric rows" instead of a
  specific message.
- **MCP errors** (Q09): tools raise exceptions instead of returning
  `{"ok": false, "error", "hint"}` (unknown graph id in `export_plot` is a
  `KeyError`); API diagnostics print raw units such as
  `[[cm2/cm3]·(1/angstrom)⁴]` instead of `axis_label` text.
- **`AxisSpec.grid_minor`** (Q02) is saved but never read; minor grid lines
  are always drawn. Wire it (with N05) or drop it from the docs.

## 3. Housekeeping (separate, behaviour-neutral passes)

- **Dead code** (Q01): `Plot2DWidget.export_csv` (superseded, not atomic);
  compatibility packages `bernardyn/plot`, `data`, `export`, `utils` and
  `main.py`; dialog aliases `self.list`, `_refresh`; the `Q_UNIT_SCALE` table
  that `inverse_angstrom_scale` covers.
- **`render` shadows `QWidget.render`** (Q03) in `Plot2DWidget`,
  `OpenGLPlotWidget` and `GraphPage`; rename to `render_graph`
  (`EXTENDING.md` is already corrected).
- **Split `main_window.py`** (Q04, ~2,700 lines, 68 % coverage): undo
  commands, load workers and batching, workspace lock, preview logic into
  their own modules. Mechanical moves only; later stop rebuilding every tab
  on each workspace command.
- **Layering contract test** (Q05): no PySide6/pyqtgraph import at module
  level outside `gui/`, `renderers/`, `app.py`.
- **Broad `except Exception`** (Q06, ~53): narrow or log with
  `exc_info=True`; `_results_for` turns a read failure into "No saved pyIrena
  results"; `sources.py` defines `log` and never uses it.
- **Version consistency** (Q07): test that `pyproject.toml`, `__init__.py`
  and `recipe/meta.yaml` agree; the conda recipe lacks the `bernardyn-plot`
  and `bernardyn-mcp` entry points and the PySide6 exclusions.
- **Repository conventions** (Q08): add `CLAUDE.md`/`AGENTS.md`; add
  `pytest-timeout`; `__all__` in the remaining modules; templates live in
  `QStandardPaths.AppDataLocation` while state lives in `~/.bernardyn` —
  pick one folder and migrate templates without losing any.
- Optional: a `gui/_qt.py` import shim (house standard).
- `ruff format` would reformat ~40 files; CI does not run it.

## 4. Small features (ranked by value)

- **N01** PDF (vector) and TIFF export, also in API/CLI/MCP (`QPdfWriter`,
  page = `width_in × height_in`). Journals ask for PDF/EPS/TIFF.
- **N02** **Use current zoom as limits** button and an obvious reset; a mouse
  zoom is lost on save/reopen and absent from headless output.
- **N03** Open a package from the command line, by double-click
  (`QFileOpenEvent` on macOS), and by dropping it on the window.
- **N04** Cursor read-out in the status bar (X/Y in data units); later the
  nearest point's series, source row and uncertainties.
- **N05** Publication tick labels: uniform `10ⁿ` on log axes, a common
  exponent on linear axes; wire `grid_minor`.
- **N06** Apply style, multiplier, offset, range to all selected series, with
  mixed-value indicators, one Undo step.
- **N07** Per-series view parameters (I₀, Rg) in the inspector, with value,
  unit and origin.
- **N08** Free legend position: store the dragged offset in `LegendSpec`.
- **N09** Open symbols and more shapes (×, star, triangle variants).
- **N10** `q_unit` and `error_fraction` per input in API/CLI/MCP;
  `bernardyn-plot --version`; a displayed-data CSV output.
- **N11** Auto-refresh of the File browser list while data are collected.
- **N12** Apply only a template's style (not title, labels, annotations,
  notes), or choose what is applied.
- **N13** Merge live spin-box edits into one Undo step (`mergeWith`).
- **N14** Result summary in the inspector: χ², timestamp, program and key
  scalars from `bernardyn_result` metadata.
- Show batch intent beside Add: file count, eligible data/results, target
  graph; for Replace, the pairing order.
- Shared graph-compatibility rules for Add/Replace/Copy/Move/workspace
  import, based on X/Y semantics, units and result role (preview already has
  some); warn or route incompatible inputs.
- Recolour by sample/result group so presets keep a file's data, fit and
  components in one colour.
- Reduce duplicate controls between Data browser and Inspector; a compact
  "1D essentials" inspector; test laptop-size windows and keyboard use.
- Optional, after feedback: linked data/fit + residual panels.

## 5. Larger planned features

- **pyIrena hand-off**: "Send to Bernardyn" in pyIrena calls the public
  `PlotRequest` facade through an optional lazy import; pyIrena never writes
  Bernardyn HDF5 groups.
- **M3 Aida/MCP production checks**: real Aida smoke test (start, negotiate,
  create a graph, usable preview); idempotency policy for retried requests;
  timeouts/cancellation that clean up partial output and the offscreen Qt
  worker; concurrency policy; clean-install docs for Windows/macOS/Linux.
  Validate against the agents that use pyIrena's MCP surface; do not grow a
  per-recipe tool catalog. Remote HTTP and live GUI control stay deferred.
- **Distribution bars** (blocked upstream): needs authoritative bin edges;
  pyIrena stores only `r_grid` centres. Values never change, unequal widths
  allowed, cumulative data stay curves, no zero baseline on log Y.
  Radius→diameter as an explicit conversion (density values and units change
  with the axis).
- **R4 tables and parameter trends**: table selection → generic curves; named
  columns with units/uncertainty, row IDs, source identity; missing ≠ zero;
  joins by key; no X invented from row order. First case: Rg ± σ against
  temperature across files.
- More results: SAXS Morph and Data Merge (in pyIrena's `TOOL_REGISTRY`, not
  in `_ANALYSES`).
- **Raw 2-D detector images** (from the original specification): image view
  with linear/log colour scales and a selectable colour map; first 2-D
  dataset under `/entry/data/` as fallback. Needs its own schema design;
  `DatasetKind.IMAGE_2D` is reserved only.
- Check the per-graph colour-map choice for the 3-D surface view.
- A pure `vN → vN+1` package migration helper, when the first migration that
  changes semantics is needed.

## 6. Upstream (pyIrena)

- Simple Fits writer and schema label `I_model` as `arb`; Bernardyn already
  inherits the measured unit.
- `read_number_dist` is private (`pyirena.io._nxcansas_common`); make it
  public.
- Al_Mg_Si fixture: stored `cumul_num_dist` ends at 5.28×10¹³ cm⁻³ but
  ∫N(r)dr = 7.68×10¹³ cm⁻³; check pyIrena's cumulative number integration.
- Distribution bin edges (see §5).

## 7. Acceptance checks for calling 1D complete

Run on macOS and Windows, with a network-drive session:

- Every built-in view against independently derived synthetic curves
  (constant Porod, known Guinier slope, dimensionless overlay for different
  Rg): values, labels, units, masks, uncertainties.
- Q/dQ in Å⁻¹, nm⁻¹ and m⁻¹ resolve identically; unknown units explained;
  missing dI/dQ keep the measurement.
- Residuals with positive, zero and negative values through import, copy,
  move, export, save/reopen and recompute.
- Select/filter/sort/subfolders/drag/Add/Replace use the shown inputs in a
  predictable order; a failed or cancelled batch gives one coherent report.
- Save/edit/undo/redo/close across every content-changing command; dirty
  status matches the saved content.
- Preview never changes stored arrays, Undo, legend, exports or packages.
- Publication output (PNG/JPEG/SVG/clipboard/print/package preview):
  error bars, annotations, legend, physical size and typography.
- Reopen a styled multi-graph workspace without the source files; edit and
  export; older transform versions behave as documented.
- A real session with recent USAXS/SAXS/WAXS data, fits and distributions on
  a laptop-size window, keyboard selection, repeated Add/Replace correction.
