# File Browser dock — implementation plan

Branch: `files-dock`. Status: phase 1 implemented (awaiting hands-on testing), phase 2 planned.

## Problem

Adding data from several folders (different collection dates, USAXS and SAXS
picked separately) means repeating *Open folder → native dialog → modal data
selector → Add* for every file. The selector closes after each Add and
forgets where you were, so correcting a wrong pick ("I wanted the file below
that one") is the full routine again.

## Chosen layout (option B)

A second dock, **File browser**, next to the existing *Data browser — active
graph* dock. It is an ordinary `QDockWidget`: it docks, tabs, floats (second
monitor), closes, and reopens from the View menu like the current panels.

```
┌─ File browser ───────────┬─ Data browser ─┬── graph tabs ──┬─ Inspector ─┐
│ [◂][▴][path………………][★][▾] │ (unchanged)    │                │             │
│ folder tree               │                │                │             │
│───────────────────────────│                │                │             │
│ type / sort / filter      │                │                │             │
│ file list                 │                │                │             │
│───────────────────────────│                │                │             │
│ I(Q) data ☑ …             │                │                │             │
│ Saved results ☐ …         │                │                │             │
│ ▸ Import options          │                │                │             │
│ [Add to graph] [Replace]  │                │                │             │
└───────────────────────────┴────────────────┴────────────────┴─────────────┘
```

## Phase 1

### 1. Shared selection widget (no duplicate implementation)

Move the body of `DataFileSelectorDialog` (file list, type/sort/filter, I(Q)
checklist, saved-results checklist, per-layout profiles, Q-unit and
uncertainty options) into `DataSelectorWidget(QWidget)` in `gui/dialogs.py`.

- `DataFileSelectorDialog` composes the widget and keeps every public and
  test-used attribute (`file_list`, `list`, `data_list`, `results_list`,
  `results_status`, `filter`, `q_unit`, `error_fraction`, `selected_*`,
  `preferences()`, `_select_all_visible`, `_accept_selection`) so existing
  callers and tests are unchanged.
- New widget methods: `set_folder(folder)`, `refresh()`,
  `set_iq_results_allowed(bool)`, `selection_problem() -> str | None` (the
  validation `_accept_selection` used to do inline, now shared),
  `adopt_shared_preferences(prefs)`.
- Signal `activated` on double-click / Enter in the file list.

### 2. `FileBrowserPanel` (`gui/file_browser_panel.py`)

- Navigation row: Back, Up, editable path field (type or paste a path,
  Enter goes there), ★ toggles the folder in Favorites, ▾ *Places* menu
  (Favorites, Recent folders, Home, *Choose folder…* native dialog).
- Folder tree: `QFileSystemModel` limited to folders (`AllDirs |
  NoDotAndDotDot | Drives`), name column only. Files are never listed by the
  tree model, and HDF5 files are opened only when one becomes current in the
  file list. This keeps SSHFS-Win network drives responsive.
- `DataSelectorWidget` below the tree in a vertical `QSplitter`.
- Buttons: **Add to graph** (also double-click / Enter) and **Replace
  selected series** (also Ctrl+R while the panel has focus), plus Refresh
  (F5) to re-list a folder that is still being written to.
- Dragging files out of the list carries file URLs plus a Bernardyn marker
  (see 5).
- Signals to the window: `addRequested(paths)`, `replaceRequested(paths)`,
  `folderChanged(folder)`. The panel never touches the controller; the
  window owns import and undo, exactly as for the dialog.

### 3. Persistence (user state, never the workspace file)

- `files_panel`: `folder`, `favorites`, `recent` (10), `file_type`,
  `sort_index`, `filter`, `splitter` sizes.
- `data_selector` (existing key, same format): the dialog and the panel share
  the learned per-layout I(Q) choices, checked result kinds, Q unit, and
  uncertainty, so a layout taught in one is known to the other.
- Saved on folder change, on every Add/Replace, and on window close.
- The first folder listing is deferred until after the window is shown, and
  a missing last folder falls back to the home folder, so an unreachable
  network drive cannot block startup.
- Dock position goes through the existing `saveState` in the workspace layout,
  which already ignores unknown dock names; old workspaces open unchanged and
  the saved-file format does not change.

### 4. Add and Replace (window side)

- **Add** = the dialog's accept path without a modal: validate with
  `selection_problem()` (message in the status bar and the panel), then
  `_queue_locations(...)` and `_import_result_selection(...)` for the active
  graph. The panel stays open and keeps its selection.
- After any I(Q) import the new series are **selected** in the Data browser.
  This sets up the correction loop: *Add → ↓ → Replace → ↓ → Replace*.
- **Replace selected series**: the I(Q) data of the chosen file(s) replace the
  series selected in the Data browser, pairwise in graph order. Counts must
  match (a clear message otherwise). Saved results are not used by Replace.
  - Kept: series id, slot in the plot order, style, multiplier, offset,
    Q range, visibility, view transform.
  - Changed: dataset, legend label (new dataset label; the old label named
    another sample), transform parameters (re-resolved from the new data's
    metadata; the existing per-series parameter prompt appears when a
    required value is missing, as on import).
  - The old dataset stays in the workspace catalog (same as Remove;
    *Remove unused data* cleans it up).
  - One undo step: `ApplicationController.replace_series_datasets()` (core,
    no Qt, all-or-nothing like `add_datasets`) driven by the existing
    `DatasetImportCommand`, which gains `replace_series_ids`.
- The transform-parameter prompt in `_worker_finished` moves into a helper
  shared by Add and Replace.
- `iq_results_allowed` follows the active graph's view (updated from
  `_sync_inspector`).

### 5. Drop onto a graph tab

Dropping files on a tab makes that graph current and adds them to it. Files
dragged from the File browser use the panel's current choices (no dialog).
Files dragged from Finder/Explorer go through the existing drop path (the
selector dialog), as a drop on the Data browser does today.

### 6. Menus and layout

- View → **Open File Browser** (Ctrl+Shift+B): shows the dock where it was
  last; if it is floating off every screen, docks it back.
- View → *Reset panel layout* also puts the File browser back at the left of
  the Data browser.
- Default placement: left dock area, split horizontally with the Data
  browser.

### 7. Tests (`tests/test_gui.py`, `tests/test_models_and_transforms.py`)

- Existing selector-dialog tests pass unchanged.
- Controller: `replace_series_datasets` keeps style/offset/multiplier/Q range
  and order, changes dataset and label, rejects count mismatch and unknown
  series without mutating state.
- Window: Replace through the panel is one undo step and undo restores the
  original dataset; Add from the panel selects the new series; panel state
  round-trips through `UserState`; navigation history (Back/Up), favorites,
  and missing-folder fallback; `iq_results_allowed` follows the graph view;
  drop on a tab targets that graph.

### 8. Docs

`CHANGELOG.md` (Unreleased → Added), `docs/user-guide.md` (File browser
section, the Add → ↓ → Replace loop).

## Phase 1b — first-level subfolders (implemented)

- "Include subfolders" lists files of the folder's direct subfolders (never
  deeper, hidden folders skipped) as `subfolder/file`; filter matches that
  text or the bare name. Optional "Group by folder" sort; otherwise interleaved.
- The folder's own files appear at once; subfolders are listed by a
  background `QRunnable` (one thread) and appended as each finishes. A
  generation counter drops results of a superseded listing. More than
  `SUBFOLDER_LIMIT` (50) subfolders: none listed, with a message.
- Rebuilding the list keeps the current file, selection, and scroll.
- A file with no learned layout and a single curve uses that curve even if it
  was never shown (needed for "Select all visible" → Add).
- macOS: `WA_MacAlwaysShowToolWindow` on the docks keeps floating panels
  visible when the app is inactive.

## Phase 2 — Preview (implemented)

Decisions taken while building it (the original plan follows):

- Preview is drawn in the graph's *current* view, with the parameters the
  file carries; a view that needs more (dimensionless Kratky: I0, Rg) shows a
  message instead. It follows later view/axis changes without reloading.
- Automatic axes widen to include the preview and are restored when it goes;
  fixed ranges are untouched. Autoscale includes an active preview.
- `Plot2DWidget.set_preview()` keeps the curves apart from the document,
  snapshots, and legend, re-adds them after every render, and hides them in
  every image capture (export, clipboard, print, package thumbnail). CSV/ITX
  export reads snapshots, so it never sees them. Other renderers: message.
- A newer request takes a queued older load back (`QThreadPool.tryTake`);
  results carry a token, stale ones are dropped.
- Add/Replace removes the preview just before queueing the real load.

### Original plan

A **Preview** toggle in the File browser: moving through the file list shows
the current file as a temporary, distinct (dashed, grey) curve in the active
graph. Enter / Add keeps it as a real series; anything else discards it.

- Temporary curve lives in the renderer only: never in `GraphDocument`, never
  on the undo stack, never saved.
- Loads are debounced (~300 ms), cancellable, and serial, on the same
  one-thread pool (concurrent HDF5 opens over SSHFS-Win fail).
- Uses the panel's current I(Q) profile for the file layout; a file with no
  choice yet shows nothing and says why.
- Open question for then: preview in the original I(Q) only, or in the
  graph's current view transform (needs parameters for Guinier and similar).
