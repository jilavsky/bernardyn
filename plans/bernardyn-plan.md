# Bernardyn roadmap to 1.0

Updated 2026-10-14 after a status review of `main` at `622861d`
(package `0.0.1b7` + unreleased `--version` work).

This file merges and replaces the earlier `bernardyn-plan.md` (2026-09-14),
`bernardyn-review-2026-09-14.md`, and `r2-generic-curve-contract.md`. Their
completed items are summarised in §1 only; everything left below is open work.
The original product brief stays in [specifications.txt](specifications.txt).

## 1. Status

Verified in the `bernardyn` conda env (Python 3.13, PySide6 6.9.3,
pyqtgraph 0.14.0, NumPy 2.5.3):

- `pytest`: **143 passed, 3 skipped** (all three need a hardware OpenGL context).
- `ruff check bernardyn tests` passes with the repo's own config. Under the house
  rule set (`E,F,W,I,UP,B`) it reports 26 findings; see F15.

**Done since the September plan.** Each item was checked against the code:

| Old ID | Item | Shipped |
|---|---|---|
| B1–B7 | R0 reliability: graph view intent, atomic validate-then-commit, workspace-bound load jobs, live legend labels, undoable remove/reorder/graph lifecycle, template fields, verified image writes | 0.0.1b5 |
| R0 contracts | Workspace save keeps the catalog; single-graph export keeps only referenced data; **Add from workspace…**; CSV/ITX omit hidden series | 0.0.1b5 |
| R1 | Unified Fit + Size Distribution data + fit overlays with result roles and provenance | 0.0.1b5 |
| R2 | `GenericCurve`, residuals, volume P(r), package schema v2 (v1 readable) | 0.0.1b5 |
| M0/M1 | `PlotRequest`/`PlotService` facade, `bernardyn-plot` CLI, offscreen 2-D rendering | 0.0.1b5 |
| M2 | Five-tool local stdio `bernardyn-mcp` with authorised roots | 0.0.1b5 |
| — | Power-law slope guides (schema v3), recent workspaces, multi-window, package edit lock | 0.0.1b6 |
| R2 follow-on | Modeling, Simple Fits, WAXS Peak Fit, Carbon results; number/surface/cumulative distributions | 0.0.1b7 |

The September review's evidence and the R2 contract are in git history
(`git show 622861d:plans/bernardyn-review-2026-09-14.md`). The normative file
format is [graph-package-v3.md](../bernardyn/schemas/graph-package-v3.md).

## 2. 1.0 release gate

1.0 is a promise about the file format and about scientific labelling. Before
the version moves from `0.0.1bN` to `1.0.0`:

1. No open **P1** items in §3 (F1–F3 done).
2. The package reader tolerates unknown fields (F7, done). After 1.0, every 1.x
   minor release will add presentation fields, and today an older reader
   crashes on them.
3. Every axis in a saved or exported figure shows its quantity and its unit
   (F1, F2).
4. A stable pyIrena release meets the dependency floor. `pyirena[qtplot]>=1.2.0b2`
   is a pre-release pin, so the 1.0 wheel should depend on a stable `1.2.x`.
5. CI runs the MCP tests (F13). Release docs match the real default branch (F14).
6. A short manual usability pass with real beamline data, from the old
   §7 gate:
   - I(Q) with no extra decisions.
   - Data + fit with no manual paths.
   - Distributions with correct axes.
   - A multi-file batch with one undo.
   - Save, delete the sources, reopen and edit.

## 3. Bugs and fixes

Severity: **P1** = scientifically wrong or misleading output; **P2** = incorrect
behaviour or state; **P3** = robustness/hygiene. "Verified" means reproduced
during this review.

### P1

**F1–F3 — done (unreleased).** Shared helper `bernardyn/core/units.py`:
- Every view's axis labels carry units.
- An empty graph takes its labels from its first curve.
- Mixed units in one graph give a warning.
- Result units are read from the HDF5 file, and fits and components inherit
  the units of the measured data.

Tests are in `tests/test_units.py`.

One upstream item remains: pyIrena's Simple Fits writer and schema still label
`I_model` as `arb`. Fix that in pyIrena. Bernardyn already records
`intensity_unit_source: "measured_data"` for the inherited unit.

### P2

**F4 — done (unreleased), mostly.** Modeling "Data + fit" now adds the file's
primary NXcanSAS curve as the measured data, when the file has one. It is
marked `measured_source: primary_scattering_data`, and the full data range is
kept, not trimmed to the fit range. Each population's `volume_dist` is offered
as a volume-fraction-density curve: ∫P(r)dr equals the population's volume
fraction, which was verified on the fixtures.

Still open:
- Modeling residuals. pyIrena does not store them, and Bernardyn does not
  recompute model curves.
- Modeling `number_dist`. It has no stored or documented absolute units, so
  ask pyIrena to write a `units` attribute for both arrays.

**F5 — done (unreleased).** A Qt-free planner, `bernardyn/io/result_batch.py`,
surveys the files, loads the selection, and groups the curves. One dialog,
`ResultImportDialog`, covers the whole batch:
- Each chosen kind makes one graph, with one colour per file; components are
  dashed when there are several files.
- Skipped files are reported.
- The import is one Undo step.

**F6 — done (unreleased).** A command whose first `redo()` fails marks
itself obsolete and rolls back, so no phantom Undo entry is left.
`_push_edit` reports the error. **Reset graph to defaults** now keeps the
scientific view, which was a related silent mislabel. Tests are in
`tests/test_gui.py`.

**F7 — done (unreleased).** The serialised models (graph, axes, typography,
legend, series, style, annotation, dataset metadata) carry an `extras` mapping:
- Unknown keys are kept on read and written back on save.
- Files without unknown keys are byte-for-byte the same as before.
- Released 0.0.1b7 opens the new packages.

Malformed graph JSON now raises `PackageValidationError`. A frozen package
written by 0.0.1b7 (`tests/fixtures/workspace-0.0.1b7.h5`) and injected future
fields are tested in `tests/test_forward_compat.py`.

**F8 — done (unreleased).** The image suffix is validated before any output
is written.

**F9 — done (unreleased).** `Dataset.uncertainty_kind` is `measured`,
`estimated` or `partly_estimated`, or None for packages written before
0.0.1b8. Each loader states it; for text files, columns are counted because
pyIrena does not flag the errors it generates. It is saved in package
metadata (older readers ignore it) and shown in the dataset tooltip. The graph
warns while estimated error bars are visible, and ITX/H5XP exports carry a
note.

Not changed: estimated errors are still synthesised by default (5%). Making
"no synthetic errors" the default would change behaviour and is your call.
The CSV header comes with I5.

### P3

**F10 — done (unreleased).** `metadata_parameter` reads only top-level keys.
`parameter_source_notes` reports when a series' I₀/Rg came from its own
metadata.

**F11 — done (unreleased).** `setStaleLockTime(0)`. A held lock names its
owner (program, PID, host) and offers **Break lock**. This is tested with a
simulated lock from another host. Not yet tried on the real beamline share.

**F12 — done (unreleased).**
- Closing a graph activates its neighbour.
- Default graph titles stay unique.
- The template overwrite prompt is in place.
- The v2 schema text describes the actual dataset checksum.
- CSV/ITX writes are atomic.

**F13–F15 — done (unreleased), except as noted.**
- CI and the release workflow install `.[dev,mcp]`.
- Ruff uses the house rule set, with all findings fixed (`zip(strict=True)`
  throughout).
- `changelog.md` was renamed to `CHANGELOG.md`.
- `Claude outputs/` was removed.
- PySide6 is pinned `!=6.10.*` like pyIrena. The core-dependency deviation is
  documented in `pyproject.toml`.
- `docs/releasing.md` reminds you to check the default branch.

Still open:
- Reinstall the local editable pyIrena so its metadata reports ≥ 1.2.0b2.
- Optional: a `gui/_qt.py` import shim. That is a mechanical refactor of every
  GUI module, left for its own change.

## 4. Simple, valuable improvements to do now

Each is small (≤ ½ day) and independent:

- **I1 Template management.** The spec asks for delete *and rename*. Add
  **Rename template…**, an overwrite warning (F12), and a list showing each
  template's view and output size.
- **I2 Multi-select "Add from workspace".** It is a single-item `QInputDialog`
  today. Use a checkable list, so comparisons don't re-read files.
- **I3 Duplicate graph.** One command that copies a graph with fresh series IDs
  and the same catalog datasets. It was planned in old §7.
- **I4 Remove unused data from workspace…** Today the catalog only grows. Purge
  datasets that no graph references, with confirmation. This is the "remove vs
  permanently delete" distinction from old R0.
- **I5 Self-describing exports.** CSV: add a `# bernardyn-export v1` header with
  the graph title, axis labels and units, and transform id/version. ITX: add
  `SetScale d` units per wave. Use `zip(strict=True)`.
- ~~**I6 Cheaper result reading.**~~ Done: results and units are cached per
  file identity, and the provenance code is shared.
- **I7 Doctor checks.** Report a pyIrena version below the floor, a missing
  `mcp` extra, and the PySide6 build in use.

## 5. Planned features not yet implemented

Merged from the old roadmap (R3, M3, R4, §6, §12), `docs/TODO.md`, and
`specifications.txt`:

### R3: result workflow polish
- ~~One batch result dialog with grouping preview and skipped-file explanations
  (F5).~~ Done.
- A compact result summary in the inspector: χ², fit-quality, key scalars from
  `bernardyn_result` metadata, and accessible provenance, without a permanent
  editable panel per tool.
- Modeling completeness (F4): done, except residuals and number distributions
  (upstream). Optional: SAXS Morph and Data Merge results that
  are in pyIrena's `TOOL_REGISTRY` but not in `_ANALYSES`.
- Optional, only after user feedback: a shared-axis residual subpanel under
  I(Q). Separate tabs remain the default.

### Distribution presentation (blocked upstream)
- Step/bar presentation for distributions needs authoritative bin edges.
  pyIrena still stores only `r_grid` centres, so agree an edge convention
  upstream first. If edges are inferred, mark them `inferred`.
- Rules carried over:
  - Presentation never changes the values.
  - Bars support unequal widths.
  - Cumulative data stay curves, not bars.
  - A zero baseline is not drawn on a log-Y axis.
- Radius→diameter as an explicit scientific conversion: density values and
  units change together with the axis.

### pyIrena hand-off (docs/TODO.md)
- "Send to Bernardyn" in pyIrena calls the public `PlotRequest` facade through
  an optional, lazy import. pyIrena never writes Bernardyn HDF5 groups itself.

### M3: Aida/MCP production checks
- A real Aida smoke test: start the server, negotiate, create a graph, and get
  back a usable preview.
- An idempotency/collision policy for retried requests. `overwrite` exists;
  there is no request-ID reuse yet.
- Timeouts and cancellation that clean up partial outputs and the offscreen Qt
  worker. A policy for concurrent requests.
- Clean-environment install docs for Windows/macOS/Linux.
- Remote HTTP and live GUI control remain deferred.

### Format stability
- ~~Unknown-field preservation (F7)~~ — done, with a frozen 0.0.1b7 fixture.
- An explicit pure `vN → vN+1` migration helper, written when the first
  migration that changes semantics is needed. v1→v3 is currently read
  directly, which is acceptable.

### R4: tables and parameter trends
- Data Explorer / Data Selector / table file → table selection → generic curves.
- Old §10 contract:
  - Named columns with units and uncertainty, plus row IDs and source identity.
  - Explicit grouping.
  - Missing values are not zero.
  - Joins use keys, never list position.
  - No X values invented from row order.
- First acceptance case: Rg ± σ against a known temperature column across files,
  keeping level identity and missing results.

### From the original specification, not yet started
- Raw 2-D detector image view (`DatasetKind.IMAGE_2D` is reserved only), with
  linear/log colour scales and a selectable colour map. This needs its own
  schema design and is not a 1.0 requirement.
- Waterfall/surface rendering exists; per-graph colour-map choice for the
  surface view is worth checking against the spec.

## 6. Recommended order

| Step | Work | Size | Why now |
|---|---|---|---|
| 1 | ~~F1 + F2 + F3~~ — done; pyIrena `I_model` unit fix remains upstream | — | — |
| 2 | ~~F7~~ — done | — | — |
| 3 | ~~F6, F8~~ — done | — | — |
| 4 | ~~F13–F15~~ — done (default branch is `main`); local pyIrena reinstall remains | — | — |
| 5 | ~~F5 + I6, F4~~ — done; Modeling residuals and number-distribution units need pyIrena | — | — |
| 6 | ~~F9–F12~~ — done; synthetic-error default left unchanged | — | — |
| 7 | **I1–I5, I7** quick improvements | 1–2 d | Visible polish, low risk |
| 8 | Usability pass with beamline data (§2.6), then release **1.0.0rc1** | — | Gate |
| 9 | After 1.0: M3 Aida checks → pyIrena hand-off → distribution bars (when edges exist) → R4 tables → 2-D detector images | — | Feature growth on a stable format |

Update `CHANGELOG.md` and the user guide as each step ships, not when it is
planned.
