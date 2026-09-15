# Bernardyn review — 2026-09-14

## Scope and conclusion

Reviewed **`/Users/ilavsky/GitHub/Bernardyn`**, commit `7d45d8d`, package
version `0.0.1b4`. Its working tree was clean at the start. This was a review
and planning exercise: no application fixes were made.

Bernardyn has a sound foundation for the next stage. Keep its separation of
models, transforms, and renderers. Invest first in graph-state correctness,
then in generic scientific curves and a small public application API. There is
no reason to rebuild the GUI or create a separate interface for each analysis.

The task initially supplied an older checkout in `Documents/ChatGPT/Bernardyn`.
That checkout and its test failures are **excluded from this review**. Findings
below were rechecked against the main GitHub checkout. The main checkout already
corrects the auxiliary-HDF5 selection and raster sizing issues seen in that copy.

## Verification

From the main repository:

```sh
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 \
  /opt/miniconda3/envs/pyirena/bin/python -B -m pytest -q -p no:cacheprovider
/opt/miniconda3/envs/pyirena/bin/ruff check --no-cache bernardyn tests
```

- **91 passed, 3 skipped**, in 4.47 seconds; lint passed.
- Python 3.13.13, PySide6 6.11.1, PyQtGraph 0.14.0, NumPy 2.4.6.
- Confirmed imports from the main Bernardyn checkout and the local pyIrena
  checkout; the public scattering API imported successfully.
- pyIrena editable-install metadata reported `1.1.0`; source HEAD was
  `675c8e0` (`Release 1.1.1`). This is a development-environment result,
  not verification of a fresh PyPI installation.
- Additional temporary Python probes exercised the real controller, renderer,
  and Qt edit paths below. No regression tests were added in this session.

The passing suite is a useful baseline, not proof that all editing sequences
work. This review did not verify a live desktop session, Windows/Linux runtime,
hardware OpenGL rendering, a clean installation, or an Aida integration.

## Confirmed findings

P1 indicates scientific correctness or inconsistent application state to address
before expanding the workflow. P2 indicates a concrete behavior defect for the
next reliability increment. IDs are referenced by the roadmap.

### B1 — P1: newly added data do not inherit the graph's transform

**Trigger:** plot a curve, select Kratky, then load another curve. The new
`SeriesView` defaults to `raw`, while the axes still describe Kratky.

**Reproduced:** the first series had transform `kratky` and Y `[10, 80, 270]`;
the second had transform `raw` and Y `[5, 6, 7]`, under the same axis labels.

**Plan:** persist the graph's intended view and apply it to compatible additions.
Request per-dataset parameters when needed. Explicitly handle mixed graphs;
blindly copying the first series is not sufficient. Cover choosing a view before
loading any data too.

Evidence: [controller.py](../bernardyn/core/controller.py), `add_dataset`,
lines 102–112, and the defaults in [models.py](../bernardyn/core/models.py).

### B2 — P1: failed numerical edits leave changed documents

`update_graph()` replaces the graph before recomputing its snapshots. A failure
leaves the graph document and displayed arrays describing different operations.

**Reproduced:** requesting `dimensionless_kratky` without I₀/Rg raised a
`ValueError`; the document retained that transform while its snapshot retained
the previous transform. Saving subsequently failed package validation. The
atomic writer protected the file, but the in-memory graph remained inconsistent.

**Plan:** resolve and validate candidates before committing the graph, snapshots,
warnings, dirty state, and undo command together. Apply the same rule to imports
and public API requests. This is especially important before agent access.

Evidence: [controller.py](../bernardyn/core/controller.py), `update_graph` and
`recompute_graph`, lines 129–150.

### B3 — P2: late imports can populate a different workspace

`_source_loaded()` redirects a result to the active graph if the original target
has disappeared. Jobs do not carry a workspace identity checked on completion.

**Reproduced:** create a new workspace, then deliver a record with the old graph
ID; it is inserted into the new workspace. This simulates a completion callback,
rather than relying on a timing-sensitive disk operation.

**Plan:** attach workspace generation, graph, batch ID, and selection ordinal to
jobs. Reject obsolete completions; preserve selection order rather than worker
completion order. Insert a batch as one undoable action. Clear stale pending
render IDs during workspace/graph lifecycle changes.

Evidence: [main_window.py](../bernardyn/gui/main_window.py),
`_queue_locations` and `_source_loaded`, lines 737–774.

### B4 — P2: legend renaming retains the old plotted label

The inspector changes `SeriesView.legend_label` without recomputation. The
renderer uses `PlotSeries.label` from the old snapshot.

**Reproduced:** the view said `New legend`; both snapshot and plotted item still
said `First`.

**Plan:** resolve presentation labels from current graph state, or refresh
snapshot presentation metadata without recalculating arrays. Check the canvas,
preview, CSV/ITX, and package reopen. Label edits must not silently recompute
an archived transform from a different version.

Evidence: [inspector.py](../bernardyn/gui/inspector.py), `_edit_series_label`,
lines 959–966; [plot2d.py](../bernardyn/renderers/plot2d.py), line 382.

### B5 — P2: dataset-list removal bypasses undo

Removal from the left dataset list calls the controller directly; other edits
use whole-document undo commands.

**Reproduced:** edit the title, remove the only series from the left list, then
Undo. The command was still `Edit title`; undo restored the removed series
inside the document, but its snapshot had already been removed.

**Plan:** use consistent commands for import, removal, reordering, closing graphs,
and graph edits, with coherent snapshot restoration. Test mixed edit sequences.
Define workspace versus per-graph undo explicitly.

Evidence: [main_window.py](../bernardyn/gui/main_window.py), `GraphEditCommand`,
`_remove_datasets` (lines 802–811), and `_dataset_list_reordered`.

### B6 — P2: templates omit newer presentation settings

`template_document()` serializes the graph, but `apply_template()` restores a
hand-written subset, omitting `box_axes` and `background_scope`, among others.

**Reproduced:** a template saved with boxed axes left the target graph unboxed.

**Plan:** define the reusable field set centrally and test that contract.
Preserve target data and identity. Separate appearance from sample-specific
parameters: currently the first series' I₀/Rg can be copied to every target
series. Resolve this before templates become the primary agent interface.

Evidence: [graph_templates.py](../bernardyn/template/graph_templates.py),
`template_document` and `apply_template`.

### B7 — P2: raster export can return success without writing a file

The return value of `QImage.save()` is ignored.

**Reproduced:** exporting to a nonexistent parent directory returned a PNG path
without raising, although the file did not exist. An existing directory chosen
in the GUI avoids that example, but write failures and API paths remain relevant.

**Plan:** report success only after a successful write, propagate useful errors,
and protect existing outputs from incomplete replacement.

Evidence: [plot2d.py](../bernardyn/renderers/plot2d.py), `save_image`, line 834.

## Product gaps and decisions, separate from confirmed bugs

- **Catalog lifetime:** removing a series retains its canonical dataset in
  memory, but full workspace save writes only graph-referenced datasets. A
  two-dataset catalog with one unreferenced dataset reopened with one dataset.
  Recommendation: retain the catalog on workspace save; keep single-graph
  export limited to its data. Add an optional “Add from workspace” action.
- **Displayed-data exports:** CSV/ITX include hidden series. An isolated
  hidden-series probe exported two rows. Recommend visible series by default,
  with an explicit all-series option. Add units/provenance in a versioned export
  contract rather than silently changing CSV columns.
- **Uncertainty:** generic data need missing/estimated/measured distinctions.
  Do not apply synthesized percentage errors from text-scattering import to
  model curves, residuals, or table columns.
- **Compatibility:** v1 Q/I arrays have specific scientific meanings. Existing
  parsers are not a general unknown-field-preserving migration system. Implement
  and test that behavior when adding v2.
- **Usability:** output preview, autoscale, independent errors, remembered
  workspace, and the current inspector are useful advances. Add result choices
  at import time and reuse these controls. Avoid a permanent panel per tool.

## pyIrena integration evidence

Read the local source at `675c8e0`:

- [Result registry](../../pyirena/pyirena/io/schema.py): tool IDs, result paths,
  curve semantics, units, scalar definitions, and repeating subgroups.
- [High-level loader](../../pyirena/pyirena/io/results.py): `load_result`
  supports Unified Fit and Size Distribution, not every registered tool.
- [Data Explorer readers](../../pyirena/pyirena/gui/hdf5viewer/pyirena_readers.py):
  useful extraction behavior currently located under a GUI package.
- [Tabulation API](../../pyirena/pyirena/api/aggregate.py): rows contain source
  path, sample, scan number, file modification time, value, and standard deviation.
  Current X choices are scan number, file modification time, and name. Arbitrary
  temperature/time columns need a wider contract. File modification time is not
  acquisition time.
- [Size-result I/O](../../pyirena/pyirena/io/nxcansas_sizes.py): radius centers,
  distributions, cumulative arrays, and optional uncertainty. The inspected
  writer does not store an explicit bin-edge array.
- [Feature integration guide](../../pyirena/docs/developer_adding_features.md):
  relationships among the registry, I/O, Data Selector, and Data Explorer.

A read-only scan of local pyIrena testData found saved Unified Fit, Size
Distribution, Modeling, and Data Merge groups. These supply starting fixtures,
not coverage of every tool/version. Result array names differ between tools;
some files contain only subsets. Discovery must check actual availability and
distinguish absent results from failed reads.

No generic `discover_result_curves`/`load_result_curve` public pair was found.
Promoting a supported result contract remains real upstream work, even though
much of the extraction knowledge exists.

## Recommended decision

Adopt the [revised roadmap](bernardyn-plan.md): R0 reliability; agree the R1/R2
contract before adding result UI; deliver Unified Fit and Size Distribution
as the first useful result slice; then headless recipes and local MCP for Aida.
Prepare generic axis semantics and row provenance now for later parameter
plots, without building a spreadsheet application.
