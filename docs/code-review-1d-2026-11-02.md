# Bernardyn 1.1.0: code review and 1D completion plan

Review date: November 2, 2026  
Reviewed revision: `0716199` (`main`, tag `v1.1.0`)  
Scope: read-only review of application code; this document is the only repository addition.

The priority should be to make existing 1D workflows reliable before adding more graph types. The code already provides substantial functionality: scattering views, saved fit and distribution results, independent graph tabs, non-destructive transforms, portable packages, templates, and image/data export. The remaining work is primarily correctness at workflow boundaries and clearer interaction, rather than a missing plotting engine.

I found **16 actionable defects: 4 high priority, 11 medium priority, and 1 low priority**. The highest priorities are lost work around Undo, incorrect handling of unrecognized Q units, and the definition of the dimensionless Kratky view. Passing tests currently miss these cases.

Here, **1D** means curves such as I(Q), residuals, and size distributions. These are drawn by the existing `plot2d` renderer. Its implementation name does not put it outside this review. Calibrated 2D detector workflows, new surface/waterfall functionality, and further 3D development are deferred.

## Evidence and limits

The review covered the domain models and controller, all built-in transforms, source/result loading, graph/workspace persistence, templates, the main window, inspector, file selector/browser, 1D rendering and export, and the Python/CLI recipe path. Existing documentation, release notes, and tests were used to establish intended behavior.

Validation performed:

- `/opt/miniconda3/envs/bernardyn/bin/python -m pytest -q`: **254 passed, 3 skipped**, in 9.19 seconds. The three skips concern OpenGL coverage. Two NumPy-related deprecation warnings arose in PyQtGraph annotation rendering.
- `/opt/miniconda3/envs/bernardyn/bin/python -m ruff check bernardyn tests`: **passed**.
- Isolated reproduction scripts exercised the controller and real Qt widgets with `QT_QPA_PLATFORM=offscreen`. They used temporary packages/preferences and did not modify application code or test fixtures.
- A real Unified Fit residual fixture confirmed the transfer problem in F07. An actual temporary HDF5 file confirmed the unit conversion problem in F03.

Environment: macOS arm64, Python 3.13.15, Bernardyn 1.1.0, NumPy 2.5.3, PySide6 6.9.3, PyQtGraph 0.14.0, pyIrena 1.2.0, h5py 3.16.0.

This was not an interactive user acceptance session or a Windows/network-drive validation. Recommendations about responsiveness and discoverability below follow from code inspection; they are distinguished from reproduced defects. Source line numbers refer to the reviewed revision.

Priority definitions: **P1** = address before treating 1D as finished, because work or scientific interpretation can be lost; **P2** = correct during 1D stabilization; **P3** = lower-impact polish.

## Confirmed defects

### F01 — P1: Undo after Save can suppress the unsaved-changes prompt

**Location:** [main_window.py](../bernardyn/gui/main_window.py), `WorkspaceEditCommand.undo()` at lines 366–368 and `_restore_controller_state()` at 1179–1195; [controller.py](../bernardyn/core/controller.py), `save()` at 929–931.

**Reproduce:** Save a workspace with one graph, create a second graph, Save again, then Undo. Memory now contains one graph while the saved package contains two. In the reproduction, `workspace.dirty` was `False` and `_confirm_discard()` allowed closing without asking to save.

The undo snapshot contains the old `dirty` flag. Restoring that historical flag does not establish whether the restored content matches the most recent successful save. Dataset import commands use the same restoration mechanism.

**Needed:** Track the saved content/Undo position separately from undoable workspace content. Mark the undo stack clean after a successful workspace save and derive changed state consistently, including mutations that do not currently use commands. Do not restore historical save status as document content.

**Acceptance:** Save → edit → save → undo prompts on close; redo to the saved state becomes clean. Exercise graph creation, close, duplication, data import/replacement, and ordinary graph edits.

### F02 — P1: Import graph bypasses Undo and can disappear when an earlier action is undone

**Location:** [main_window.py](../bernardyn/gui/main_window.py), `_import_graph()` at 2181–2200, especially the direct controller mutation at 2197.

**Reproduce:** Create a new graph, import a graph from another package, and press Undo. The Undo label still says “New graph.” The operation restores the entire earlier workspace, removing both the newly created graph and the subsequently imported graph. This was reproduced through the actual `_import_graph()` path with only the file/selection dialogs substituted.

The imported graph has no command of its own, while earlier commands restore whole workspace snapshots. This makes Undo affect content outside the named operation.

**Needed:** Wrap package graph import in `WorkspaceEditCommand`, including catalog, snapshots, warnings, and archival status. Audit workspace title/description and other direct content mutations for the same mismatch.

**Acceptance:** Import has its own Undo entry; one Undo removes only the import; Redo restores it. Undoing a preceding operation must not silently discard unrelated later content.

### F03 — P1: Unknown Q units are relabeled as Å⁻¹ without conversion or a visible warning

**Location:** [sources.py](../bernardyn/io/sources.py), `Q_UNIT_SCALE` at 33–49 and `ScatteringRecord.to_dataset()` at approximately 167–193.

**Reproduce:** Load an HDF5 curve with Q values `[1e8, 2e8]` and `units="1/m"`. Bernardyn produces `[1e8, 2e8]` labeled `1/angstrom`; the correct converted values are `[0.01, 0.02]`. The graph reports no warning. This was verified through normal discovery and loading with the installed pyIrena.

An unrecognized unit sets a metadata flag, uses scale 1, and is then replaced by the canonical unit string. That flag is not surfaced by graph warnings. This also affects unsupported spellings of otherwise familiar units.

**Needed:** Normalize supported unit spellings and add missing conversions, including inverse metres. Reject or visibly resolve an explicitly supplied but unknown unit. Keep the existing user-selected assumption workflow for genuinely missing units, with provenance and a visible note.

**Acceptance:** Equivalent Å⁻¹, nm⁻¹, and m⁻¹ input curves resolve identically, including dQ. Unknown explicit units cannot silently become canonical units.

### F04 — P1: “Dimensionless Kratky” leaves its X axis dimensional

**Location:** [transforms.py](../bernardyn/core/transforms.py), lines 232–240; existing expectations in [test_models_and_transforms.py](../tests/test_models_and_transforms.py) also encode the present behavior.

The Y expression is normalized, but X uses `_q`, X uncertainty uses `_dq`, and the label/unit remain `q` and inverse length. With q = 0.1 Å⁻¹, Rg = 10 Å, and dQ = 0.01 Å⁻¹, the current output is X = 0.1 and dX = 0.01. A conventional dimensionless view uses X = qRg = 1 and dX = Rg·dQ = 0.1, treating Rg as fixed.

The conventional graph is `(qRg)² I(q)/I₀` versus `qRg`, as specified in the primary publication [Kieffer et al., “New data analysis for BioSAXS at the ESRF”](https://journals.iucr.org/s/issues/2022/05/00/ju5045/). Leaving X unnormalized prevents the expected size-normalized comparison between samples with different Rg.

**Needed:** Implement qRg on X, with a dimensionless label/unit and corresponding dX. If the existing normalized-Y-versus-q view is intentional, retain it under a distinct name. Bump the affected transform version so archived snapshots retain their original meaning until explicitly recomputed.

**Acceptance:** Synthetic Guinier curves with different Rg but identical normalized shape overlay in dimensionless coordinates. Saved older plots do not silently change when opened.

### F05 — P2: Missing optional uncertainty values remove otherwise valid curve points

**Location:** [transforms.py](../bernardyn/core/transforms.py), lines 96–110.

**Reproduce:** Use Q `[1,2,3]`, I `[2,3,4]`, and uncertainty `[0.2, NaN, 0.4]`, with error bars disabled. The resolved curve contains only source rows 0 and 2. A NaN in dQ has the same effect.

The mask for valid X/Y data also requires every optional uncertainty to be finite. A warning says a transformed point was non-finite, but the actual coordinates were valid. This can remove peaks or alter displayed-data exports because an unused error value is missing.

**Needed:** Preserve finite curve coordinates independently of error-bar validity. Mask unavailable errors when drawing bars, and report their absence separately. Apply a consistent policy to scattering and generic curves.

**Acceptance:** Toggling error bars does not alter the curve's valid data rows. Missing uncertainty excludes the relevant bar, not the measurement.

### F06 — P2: Residual/distribution logarithmic masking occurs before multiplier and offset

**Location:** [controller.py](../bernardyn/core/controller.py), `_resolve_generic_curve()` at 701–734.

**Reproduce:** For generic Y `[-2,1,2]`, use a logarithmic Y axis and offset +3. Expected displayed values are `[1,4,5]`; Bernardyn discards the first point and returns `[4,5]`. With offset −2 it instead returns `[-1,0]`, despite the log axis requiring positive displayed values.

Ordinary scattering curves apply axis validity after scaling/offset, whereas generic curves test the original Y first. As a result, the renderer and CSV/ITX snapshots can disagree about which points are actually drawable.

**Needed:** Form displayed Y first, then apply finite/log-domain checks and update source indices, errors, and warnings together. Use shared resolution rules where possible.

**Acceptance:** Generic curves and raw scattering curves with equivalent values, multiplier, offset, and axes retain equivalent rows. Exported log-axis snapshots contain no non-positive displayed coordinates.

### F07 — P2: Copy/Move to a new graph gives residuals and distributions scattering axes

**Location:** [controller.py](../bernardyn/core/controller.py), `_prepare_series_transfer()` around 398–444, particularly line 431; [main_window.py](../bernardyn/gui/main_window.py), `_transfer_selected_series()` at 1428–1474.

The new destination is a default log–log I(Q) graph. Transfer appends views without adopting the incoming curve's quantities or appropriate axes.

**Reproduce:** Copy a signed residual curve to “Create new 2D graph.” With the real Unified Fit residual from `testData/Al_Mg_Si__40C_0min_0498.h5`, the source had **517 points**, including **226 negative values**. The destination retained **291 points**, used logarithmic Y, and labeled it `Intensity [cm⁻¹]`. A radius distribution likewise inherits a Q label.

**Needed:** Initialize an untouched destination from the incoming curve's semantics. Residuals require linear Y; preserve appropriate X behavior for the result type. Apply the same initialization when copying into an existing empty default graph, while respecting deliberately customized axes.

**Acceptance:** Copy/Move preserves signed residual data and meaningful quantities. New distribution graphs label radius and distribution values correctly. Scattering-to-scattering transfers still use the target scientific view.

### F08 — P2: Filtered-out files can still be added or used for replacement

**Location:** [dialogs.py](../bernardyn/gui/dialogs.py), `_apply_filter()` at 464–475 and `selected_paths()` at 483–484.

**Reproduce:** Select `alpha.h5` and `beta.h5`, then filter for `alpha`. The list reports one visible file, but `selected_paths()` still returns both. Add and Replace consume that list.

Hiding a QListWidget row does not clear its selection. The visible list therefore understates the operation's inputs; Replace can fail its count check or use unexpected files.

**Needed:** Define the contract explicitly: preferably operate on selected visible files, or clear hidden selections when filtering. Display the selected/eligible count beside Add and Replace. Apply the same policy to dragging files.

**Acceptance:** Select → filter → Add/Replace/drag uses exactly the files indicated by the visible selection and count.

### F09 — P2: Temporary preview affects exported graph ranges

**Location:** [plot2d.py](../bernardyn/renderers/plot2d.py), `_draw_preview()` at 392–420 and `_preview_hidden()` at 422–432; image and package-preview capture call the latter context.

Preview deliberately widens automatic ranges. During export, only the preview items are hidden; the widened ViewBox range remains.

**Reproduce:** Plot Q `[1,2,3]`, then preview Q `[100,200]`. Inside the context used by export, the preview curve is invisible, but the log-X view still extends to about 2.35 rather than the original 0.49. The saved image can contain substantial empty space and compressed real curves. Package previews are affected by the same mechanism.

**Needed:** Capture output against the graph's non-preview viewport, then restore the interactive preview and its viewport. Preserve deliberate zoom/fixed ranges according to a documented output policy.

**Acceptance:** With graph settings and zoom held constant, enabling a preview does not change the exported image's axes or composition. Preview state is restored afterward.

### F10 — P2: Automatic ranges ignore visible error-bar extents

**Location:** [plot2d.py](../bernardyn/renderers/plot2d.py), `_resolved_bounds()` at 931–963.

**Reproduce:** On linear axes, show Y `[10,20]` with uncertainty `[100,100]`. Error bars span −90 to 120, but Auto Y uses roughly 9.8 to 20.2. Most of the bars are clipped, including in output.

Bounds are calculated only from point centers. Error bars are added independently and persistent PyQtGraph autorange is disabled.

**Needed:** Include enabled, drawable X/Y error extents in automatic bounds. Fixed ranges should remain fixed. Keep a defined policy for errors crossing a log-domain boundary.

**Acceptance:** Autoscale includes the visible error bars selected by the user. Disabled error directions do not expand ranges.

### F11 — P2: Inspector Remove cannot remove the last series

**Location:** [inspector.py](../bernardyn/gui/inspector.py), `_remove_series()` at 1148–1153; [main_window.py](../bernardyn/gui/main_window.py), `_queue_graph_change()` at 1229–1238.

**Reproduce:** Add one curve and press Remove in the inspector. The graph still has one curve. The main Data browser's removal path works.

The inspector emits an intentionally empty series tuple, but the main window's protection against a stale empty inspector document unconditionally replaces it with the original series. This creates contradictory behavior between two controls for the same graph.

**Needed:** Distinguish an intentional series edit from presentation-only edits, or send an explicit remove command. Keep stale-document protection without blocking a legitimate empty graph.

**Acceptance:** Both removal controls can empty a graph, retain its catalog data, and undo/redo correctly.

### F12 — P2: Invalid logarithmic axis limits are accepted and then ignored

**Location:** [models.py](../bernardyn/core/models.py), `AxisSpec.__post_init__()` at 347–349; [inspector.py](../bernardyn/gui/inspector.py), `_edit_axes()` at 795–833; [plot2d.py](../bernardyn/renderers/plot2d.py), lines 911–924.

**Reproduce:** With Log X enabled, disable Auto X and enter limits −1 to 10. The graph model stores those limits, but the renderer skips applying them because they are not positive. The controls claim a fixed range that is not displayed. A partial range with one endpoint missing also receives no fixed-range application.

**Needed:** Validate finite positive limits for log axes. Either support one-sided limits or make the two-endpoint requirement explicit. Show an inline explanation for invalid input instead of silently reverting or ignoring it. Reuse the validation in GUI, API, and deserialization boundaries as appropriate.

**Acceptance:** Entered fixed ranges either apply exactly or produce a clear, actionable validation message. NaN/infinite limits are rejected too.

### F13 — P2: Non-positive annotation coordinates on log axes are drawn at different data values

**Location:** [plot2d.py](../bernardyn/renderers/plot2d.py), `_plot_position()` at 800–807.

**Reproduce:** Add a text annotation at stored data coordinates `(0,0)` on a log–log graph. Its rendered plot coordinates are `(0,0)`, which correspond to data `(1,1)`. No warning is produced when that location is visible. A negative coordinate is likewise treated as a log-space coordinate instead of being rejected.

**Needed:** Validate the coordinates needed by each annotation type against the current axes. Report or omit an annotation outside the mathematical domain; never reinterpret its coordinates. Horizontal/vertical rules only need validity on the axis that determines their position.

**Acceptance:** Zero/negative positions on logarithmic axes cannot silently move to another physical location. Changing an existing graph to log axes explains any annotations that become invalid.

### F14 — P2: Changing checked saved results does not refresh the current preview

**Location:** [file_browser_panel.py](../bernardyn/gui/file_browser_panel.py), preview signal connections at 174–180.

**Reproduce:** With a file current and Preview enabled, check or uncheck “Data + fit I(Q).” The selected result set changes, but no preview timer starts. The preview remains stale until another file is selected or Preview is toggled. This was verified with the real widget's checkbox signal and timer.

Only file-current and I(Q)-checkbox changes schedule a preview. Saved-result checkboxes and import-option changes do not.

**Needed:** Refresh for every input affecting the preview: result choices, Q-unit assumptions, and estimated-error settings. Preserve debounce/token cancellation. Refresh should also clear previews when the selected data become ineligible.

**Acceptance:** Changing any relevant selection/option updates or removes the preview for the current file without requiring a file-navigation workaround.

### F15 — P2: The renderer context menu can change a graph outside the document model

**Location:** [plot2d.py](../bernardyn/renderers/plot2d.py), the unrestricted PyQtGraph menu enabled at line 193.

**Reproduce:** On a linear-Y graph, use the plot's right-click Transforms menu to enable logarithmic Y. Exercising that menu's actual `logYCheck` control changed the curve's log mode to `True`, while `Plot2DWidget._graph.y_axis.log` remained `False`. No Bernardyn graph-change command is involved.

The inspector, archived settings, resolved snapshots, and Undo history can consequently disagree with the displayed graph. A subsequent rerender or reopen can reset the menu change. The menu also exposes other presentation/processing controls without a corresponding Bernardyn command path.

**Needed:** Restrict the built-in menu to operations that do not bypass document state, or route its supported changes through the same controller commands as the inspector. Audit its export action for the same preview/output isolation contract as Bernardyn's export actions.

**Acceptance:** Every supported axis/style change is reflected in the inspector, dirty status, Undo, and saved document. Controls that alter displayed data cannot silently bypass snapshot resolution and export semantics.

### F16 — P3: An empty transformed graph displays the wrong view in the inspector

**Location:** [inspector.py](../bernardyn/gui/inspector.py), lines 571–572.

**Reproduce:** Select Kratky on an empty graph. The model's `view_transform_id` becomes `kratky`, but after synchronization the combo displays General I(Q). Adding data still uses Kratky.

The inspector infers the view from the first series and substitutes `raw` when none exists, despite the graph having explicit view intent.

**Needed:** Display `graph.view_transform_id` consistently. Handle legacy per-series differences explicitly if required.

**Acceptance:** Empty graphs show the selected view before data are added, including after save/reopen.

## Features and usability work worth doing next

These are recommendations, not additional reproduced defects. They are ordered for completing 1D work; none requires new 2D detector or 3D functionality.

| Priority | Improvement | Why it matters and suggested completion criterion |
|---|---|---|
| Next | Shared graph compatibility rules | `raw` currently means both scattering and arbitrary typed curves. Add/Replace/Copy/Move/workspace import should share rules based on X/Y semantics, units, and result role. The preview already has some semantic checks that normal Add lacks. Warn or route incompatible inputs to a suitable graph; allow an explicit informed override where meaningful. |
| Next | Make batch intent visible | Show selected file count, eligible dataset/result count, and target graph beside Add. For Replace, show the pairing order inline, especially for several files. Report successes and failures together with Retry rather than one modal message per failed source. |
| Next | Keep file inspection and result loading responsive | `_file_selected()` synchronously discovers I(Q) and results; `_results_for()` calls a survey whose available-kind discovery reads results. `_import_result_selection()` also surveys/loads on the UI thread. Move expensive discovery/import to cancellable background jobs using the existing serial loading policy. The current one-thread pool covers source loads and previews, not every HDF5 read. Confirm with actual SSHFS-Win data before claiming the concurrency issue is fully addressed. |
| Next | Edit several selected curves consistently | The inspector supports extended selection, but style, multiplier, offset, and range editing act on the current series; only visibility has a dedicated batch path. Offer “Apply to selected (N)” with mixed-value indicators, and one Undo step per user action. |
| Next | Make view parameters inspectable | I₀/Rg can be supplied or obtained from metadata, but the persistent per-series editor has no direct parameter fields. Show the current values, units, and origin, and allow editing them without reselecting the entire graph view. Keep values sample-specific. |
| Next | Preserve sample/fit grouping when recoloring | Result imports intentionally use one sample color for measured/fit/component curves. Generic presets assign colors per series and can erase that relationship. Offer coloring by sample/result group while preserving role-specific symbols and line patterns. Keep a per-series option for users who want it. |
| Next | Clarify axis interaction | Distinguish automatic data bounds, interactive zoom, and stored fixed limits. Add “Use current zoom as limits” and an obvious reset action. Avoid requiring users to retype the bounds of a view they already positioned. |
| Next | Add a data cursor | A lightweight cursor should identify the curve, source row, displayed X/Y, units, and available uncertainties. This would make scientific checks practical without exporting CSV and would help explain masked points. There is no dedicated point-inspection path in the current renderer. |
| Later in 1D | Reduce duplicate controls and layout friction | The Data browser and Inspector both contain dataset lists and related actions. Make their selection relationship explicit, synchronize where useful, and label whether an action affects the current row or all selected rows. Provide a compact “1D essentials” inspector and a large-graph workspace layout. Test laptop-size windows and keyboard navigation. |
| Later in 1D | Make output typography predictable | Current export scales the live graphics scene. Establish whether selected font sizes mean physical output points or proportions of the live canvas, then verify output after window resizing and between GUI/headless paths. For publication output, rendering a dedicated output scene would give a clearer contract. This needs visual validation; no font-size defect is claimed here. |
| Later in 1D | Make templates safer to apply | Templates currently replace title, labels, annotations, description, and notes as well as style. Offer presentation-only application or a clear selection of what is applied. Reusing a publication style should not unexpectedly replace sample-specific explanatory text. |
| Later in 1D | Bring text-input options to automation | GUI imports expose Q-unit assumptions and missing-error percentages; `ScatteringInput` and CLI requests do not expose equivalent options and load with defaults. Add per-input settings to Python/CLI/MCP so text data in nm⁻¹ can be plotted reproducibly without manual conversion. |
| Optional | Paired data/fit and residual inspection | A linked pair of 1D panels or linked tabs would make fit review easier. Treat this as a usability addition after the defects above, not a prerequisite for correctness or an invitation to add fitting. |

Existing duplicate-graph, workspace reuse, removal of unused catalog data, batch results, continuous palettes, error-direction controls, and exact-pixel output preview should be retained. Their implementations already address much of the requested 1D workflow. A rewrite would risk losing that progress.

## Suggested implementation sequence

1. **Protect work and scientific meaning.** Fix F01–F04 first. Establish one save/Undo contract, one unit-conversion boundary, and versioned scientific transform definitions. Include graph import in the same mutation/Undo model.
2. **Make all existing curve paths agree.** Fix F05–F08 and F10. Share data-domain rules and graph compatibility/initialization across Add, Replace, Copy/Move, result import, and workspace reuse. Signed residuals and uncertainty handling should behave consistently everywhere.
3. **Finish preview, axes, and inspector behavior.** Fix F09 and F11–F16. Then implement visible batch intent, parameter editing, and selected-series styling.
4. **Validate the complete 1D workflow with scientists.** Run the acceptance matrix below on macOS and Windows, including a network-drive session. Resolve remaining friction before extending 2D/3D features.

Prefer focused changes to the present architecture. The most useful structural work is a common graph-input compatibility policy, a common resolved-curve validity policy, and a consistent command/save-state boundary. Splitting large GUI modules can follow those boundaries as needed; module size alone is not a reason to rewrite them.

## Acceptance matrix for calling 1D complete

| Workflow | Required evidence |
|---|---|
| Scientific views | Independently derived synthetic curves for every built-in view. Include constant Porod/modified-Porod cases, known Guinier slopes, and dimensionless overlay for different Rg. Check labels, units, masks, and uncertainty behavior as well as values. |
| Units and incomplete errors | Equivalent Q/dQ in Å⁻¹, nm⁻¹, and m⁻¹ resolve identically. Unknown units are explained. Missing dI/dQ values preserve usable measurements. |
| Signed results | Import, copy, move, replace where supported, export, save/reopen, and recompute residuals containing positive, zero, and negative values. Appropriate axes preserve their meaning. |
| Catalog and graph semantics | Distributions retain radius/density labels; residuals retain residual labels. Incompatible additions are explained or routed. Customized graph labels are respected. |
| File selection | Select/filter/sort/subfolders/drag/Add/Replace all use the shown inputs in a predictable order. A batch failure or cancellation gives a coherent outcome and report. |
| Undo and persistence | Save/edit/undo/redo/close across every content-changing command, including graph import, replacement, graph lifecycle, and workspace properties. Verify dirty status against actual saved content. |
| Alternate controls | Supported right-click menu actions and inspector actions update the same document state, Undo history, snapshots, and saved output. |
| Preview isolation | Preview never changes stored arrays, Undo history, legend, image/data exports, or archival composition. Selection changes refresh promptly; stale work cannot appear after switching workspaces or graphs. |
| Publication output | PNG/JPEG/SVG/clipboard/print and saved package previews use the intended axes and composition. Verify error bars, annotations, legend, physical dimensions, and typography visually. |
| Portable archive | Reopen a styled multi-graph workspace after removing access to original sources. Compare documents and snapshots; verify editing/export and old-transform version behavior. |
| Real working session | Recent USAXS/SAXS/WAXS curves plus saved fits/distributions, on macOS and Windows, including slow/shared storage. Test ordinary laptop window sizes, keyboard selection, and repeated Add/Replace correction. |

Existing tests are a useful baseline, but several current expectations explicitly reproduce the implementation, including the dimensionless Kratky X behavior. New regression cases should assert scientific or workflow invariants independently. The defects above were found without changing application code; they remain open at the end of this review.
