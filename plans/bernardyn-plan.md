# Bernardyn roadmap

Updated 2026-09-14 after review of `/Users/ilavsky/GitHub/Bernardyn`,
commit `7d45d8d`, release `0.0.1b4`.

**Status: planning proposal; implementation is not authorized by this document.**
The accompanying [review](bernardyn-review-2026-09-14.md) records verification,
confirmed defects, and limitations. This roadmap supersedes the earlier rebuild
summary while retaining the existing R1–R3 and M0–M3 milestone identifiers.

## 1. Direction and decisions

Bernardyn should make scientifically correct, publication-quality figures from
existing data and results, with portable editable graph packages. New scientific
inputs should reuse the plotting workflow rather than add a separate application
inside Bernardyn.

The recommended sequence is:

```text
R0 reliability
  → agree result/curve contracts and v2 migration design
  → R1 measured-data/fit overlays
  → R2 generic curves, residuals, and distributions
  → M0/M1 public API and headless recipes
  → M2 local MCP for Aida
  → R3/M3 refinement from real usage
  → R4 tables and parameter trends
```

Contract design for M0 starts with R1/R2. An early Python package-creation
facade can be developed sooner if useful; result delivery need not wait for MCP.
R3 usability essentials belong in R1/R2, not in a distant polish release.

### Confirmed direction from this planning session

- Keep the GUI simple as the range of scientific data expands.
- Start from well-defined pyIrena results saved in NeXus/HDF5 files.
- Support ordinary X–Y curves and consider bars for size distributions.
- Prepare for Data Explorer/Data Selector tabulations and other table data later.
- **Aida's first use is creating figures and portable graph packages from
  existing data/results. Live control of the open GUI is deferred.**
- This session changes planning documents only, not application code.

### Recommended design choices, still open to revision

- Use one generic 1D curve model with explicit scientific semantics.
- Use existing 2D rendering for lines, symbols, and errors; add a per-series
  bar/step presentation rather than a new top-level graph application.
- First result acceptance set: Unified Fit and Size Distribution. Simple Fits
  can follow in the same increment if representative fixtures are ready.
- Use separate graph tabs for incompatible axes or quantities. Shared-axis
  residual subpanels are optional later work.
- Use one application service for GUI, Python, CLI, pyIrena handoff, and MCP.
- Use local stdio MCP initially, subject to a real Aida compatibility test.

## 2. Current state

The existing pipeline is:

`SourceAdapter → Dataset → PlotTransform → PlotSeries → Renderer`

Implemented and worth retaining:

- Read-only HDF5/NXcanSAS and two-to-four-column text loading through pyIrena
  with fallbacks; primary-data selection, file sorting/filtering, drag-and-drop.
- Immutable numeric arrays, controller-owned graph documents, independent graph
  tabs, and an in-memory dataset catalog.
- Eleven scattering views, masks, source indices, uncertainty propagation,
  per-series styling, and presentation editing with partial undo coverage.
- Native `.bernardyn.h5` packages, embedded canonical arrays and resolved
  snapshots, checksums, deduplication, atomic writes, recovery, and previews.
- PNG/JPEG/SVG, clipboard/print, output preview, CSV/ITX, and separate H5XP export.
- Output dimensions, typography, annotations including boxes, background scope,
  autoscale, independent X/Y errors, legend controls, and workspace restoration.
- Optional OpenGL waterfall/surface rendering with a guarded 2D fallback.
- Tests, cross-platform CI configuration, diagnostics, packaging and user docs.

The reviewed checkout passes **91 tests with 3 skipped** and passes lint in the
local test environment. Seven additional defects were reproduced; passing tests
do not close those issues. See the review for evidence and environment details.

The public release version is `0.0.1b4`; “1.0 beta” in earlier plans described
an architectural target, not the current package number. Result plotting, a
public headless facade, and MCP remain planned.

The normative current file format is
[graph-package-v1.md](../bernardyn/schemas/graph-package-v1.md); current extension
interfaces are in [EXTENDING.md](../bernardyn/EXTENDING.md). This document proposes
future contracts and does not change those specifications.

## 3. R0 — stabilize the existing editing workflow

Address these before adding more data types or exposing mutations to agents:

| Review ID | Work | Completion evidence |
|---|---|---|
| B1 | Persist graph view intent and apply compatible transforms on import | Add data before/after choosing Porod/Kratky; every curve has correct values and axes; required parameters are handled per series |
| B2 | Validate/resolve candidate state before atomic in-memory commit | Failed transform/import leaves document, snapshots, warnings, dirty state, and undo unchanged |
| B3 | Bind load jobs to workspace generation, graph, batch, and selection order | Close graph/new workspace/cancel during loading; no redirected records, stale callbacks, or reordered input |
| B4 | Keep presentation labels current without numerical recomputation | Renaming agrees across canvas, legend, preview, package reopen, CSV and ITX |
| B5 | Make removal/reorder/import and graph lifecycle coherent with undo | Mixed add/style/remove/undo/redo sequences restore both documents and snapshots |
| B6 | Define reusable template fields and parameter policy | Box axes/background/legend/error settings round-trip; sample-specific parameters are not silently reused |
| B7 | Verify image writes and report failures | Failed output raises a structured error and never reports a nonexistent artifact as success |

Also settle two small product contracts:

- **Workspace save retains the workspace catalog; graph export includes only
  graph-referenced data.** Provide “Add from workspace” for reusing loaded data.
  Distinguish this from permanently deleting a dataset.
- **Displayed-data export defaults to visible series.** An explicit all-series
  option can retain broader export behavior. Version any CSV/header change and
  document whether the export contains transformed values, axis clipping, or
  all points within the selected data range.

R0 tests should exercise user sequences and failure recovery, not only widget
existence. Keep the existing numerical, archive, and output-dimension checks.
Do not turn R0 into an unrelated rewrite.

## 4. Scientific data contract for R1/R2

### 4.1 Separate geometry, meaning, and presentation

Most requested results are geometrically X–Y curves. Their scientific meaning
must remain explicit throughout import, transforms, GUI, export, and persistence.
A radius distribution must never be canonicalized as inverse-ångström Q.

Proposed record concepts (names are illustrative, not a released API):

| Concept | Required information |
|---|---|
| Curve identity | Stable record ID, result-group ID, tool ID/version, curve key and role |
| Numeric data | Read-only `x`, `y`; optional `dx`, `dy`; optional bin edges; aligned source indices/row IDs |
| Axis meaning | Semantic IDs, display labels, units, and optional unit conversion provenance |
| Error meaning | Measured/estimated/derived/absent; standard deviation versus Q resolution; supported uncertainty convention |
| Curve role | measured, fit, component, background, residual, distribution, cumulative, or derived |
| Provenance | Source fingerprint, file/group/array identifiers, result timestamp/configuration when available, adapter version, warnings |
| Suggestions | Default scales, presentation and grouping; suggestions remain user-overridable |

Use one representation, not a parallel dataclass per fitting tool. Preserve
scientific roles separately from rendering style. Keep scalar parameters and
fit-quality summaries in a result record shared by related curves. Use explicit
membership so bundles can span an I(Q) graph and a residual/distribution graph.

Do not invent stable fit-run IDs where a producer overwrites one saved group;
record the producer identity/timestamp and content fingerprint available.

### 4.2 Transform compatibility and range semantics

- Scattering transforms require compatible Q/intensity semantics, not merely
  two numeric arrays or a curve role named “fit.”
- Generic curves start with identity plotting; they do not offer Guinier/Porod.
- Graphs reject or separate incompatible axes/units. Allow convertible units
  only with explicit, recorded conversion; do not silently overlay arbitrary
  intensity and absolute intensity as the same quantity.
- Keep **source-X selection range**, **post-transform axis display limits**, and
  **scientific fit range** distinct. Rename `q_range` to an explicit source-X
  concept at the new boundary, rather than the ambiguous `visible_x_range`.
- Per-series I₀/Rg or other numerical parameters are resolved for each dataset.
  An appearance template must not quietly copy another sample's normalization.
- Preserve negative residuals with a linear Y axis. Log-axis exclusions should
  be counted and visible, never silently converted into positive values.
- Missing error values do not mean zero; a missing error for one point should
  not automatically remove an otherwise valid X/Y point. Mask invalid X/Y
  separately from unsupported or missing uncertainty.

### 4.3 Generic curves are enough now; tables need a later input layer

R2 should reserve row-level provenance so a future parameter curve can identify
its source file, result, level/population/peak, and table row for every point.
That does not require building a table editor now. Later table adapters will
produce the same canonical curves and graph documents.

## 5. pyIrena owns result discovery and scientific interpretation

Use pyIrena's registry and public readers. Do not copy every HDF5 path into
Bernardyn or import Data Explorer's private GUI helpers as its runtime API.

The inspected `pyirena.io.schema.TOOL_REGISTRY` already describes result plots,
units, scalars, and subgroups. Data Explorer contains extraction knowledge.
However, the generic public result discovery/loading pair proposed below does
not exist yet, and `load_result` covers only Unified Fit and Size Distribution.
The registry also lacks a complete generic contract for errors and bin edges.

### Proposed upstream contract

```text
discover_results(path) -> result groups and available curve descriptors
load_result_curve(descriptor) -> canonical scientific curve record
load_result_metadata(result_id) -> parameters, uncertainties, fit quality
```

Requirements:

- Discovery reads structure/metadata, not every large array. Use exact descriptors
  for file, entry, result group, subgroup and curve; never “first matching array.”
- Report actual available curves. Differentiate no result, partial result,
  corrupt file, unsupported version, and missing dependency.
- Load read-only detached arrays, with shape validation, correct labels/units,
  error meanings, and result/source relationships.
- Prefer stored arrays. Derived curves are opt-in, identified and versioned;
  Bernardyn does not rerun a fit or silently rebuild a model.
- Use file units and documented producer rules. Report conflicts between file
  metadata and registry defaults rather than masking them.
- Preserve measured data associated with the saved fit, which may differ in
  range or preprocessing from the file's current primary scattering curve.
- Contract tests cover the minimum supported pyIrena release and a current
  release. Choose the new minimum only when the public API ships.
- New tools fitting existing semantic contracts should work through registration.
  New geometry or scientific semantics may still need a Bernardyn extension.

Bernardyn remains the owner of graph schema, recipes, presentation, and native
package writing. A future optional “Send to Bernardyn” exporter in pyIrena should
call Bernardyn's public API. Keep that import optional/lazy so there is no
mandatory dependency cycle, and do not have pyIrena write Bernardyn HDF5 groups.

## 6. R1/R2 result scope and defaults

| Input/result | First presentation | Milestone and boundary |
|---|---|---|
| Unified Fit measured data + total fit | Log-log I(Q), data symbols and model line | R1 acceptance fixture |
| Stored background/components | Optional subordinate lines | R1 when actually saved and unambiguously paired |
| Size Distribution measured data + fit | Same I(Q) recipe | R1 acceptance fixture |
| Stored normalized residuals | Q versus residual, linear Y, zero reference | R2; no reused intensity units or invented errors |
| Volume distribution P(r) | Radius versus density, initially line/step; optional bars | R2 acceptance fixture |
| Stored number/cumulative distributions | Correct units; cumulative curves use lines | R2 after producer semantics and fixtures are verified |
| Simple Fits data/model | I(Q) recipe, model-dependent metadata | R1/R2 follow-on; calculation-only results may have no fitted curve |
| Modeling/WAXS components, correlation/spectral curves | Existing compatible XY recipe | Later R2/R3 registrations with fixtures, not a first-release requirement |
| Scalar parameters versus sample/time/temperature | Parameter trend | R4, using table-to-curve conversion |

R1 may store I(Q) roles/relationships as namespaced metadata in v1 temporarily,
but it must use the agreed R2 concepts. It must not introduce fake Q/I mappings
for non-scattering results.

### Distribution bars need scientific rules

A size distribution is not automatically a histogram of counts. Preserve whether
Y represents density per radius, density per log-radius, or a value per bin.
Changing line/step/bar presentation must not change the scientific values.

- Prefer explicit producer-supplied bin edges; preserve them as canonical data.
- Current inspected pyIrena size files store centers and grid settings rather
  than explicit edges. Agree a public edge convention upstream. If edges are
  inferred, store the rule and mark them inferred; do not claim unique true edges.
- Until widths are trustworthy, line or center-point display is sufficient.
- Support unequal/log-spaced widths; do not render every bin at one arbitrary
  data-space width. A logarithmic X axis does not automatically convert density
  to density per log-X.
- Keep cumulative curves as curves, not density bars. Never silently renormalize
  to sum one or change a stored volume fraction.
- Radius-to-diameter conversion is a scientific conversion: density values and
  units must transform consistently, not just the axis coordinates.
- A zero bar baseline is incompatible with a logarithmic Y axis. Define an
  explicit display policy, or use a compatible line/step presentation.

## 7. Keep the GUI small

### Default user path

1. Use the current **Add data** / file selector.
2. Default to primary scattering data, preserving the existing simple path.
3. Choose **pyIrena results** when wanted; show only available analyses in
   selected files and a compact set of choices: **Data + fit**, **Residuals**,
   **Distribution**. Put components and detailed metadata behind expansion.
4. Show the proposed graph grouping and any skipped/incompatible inputs, then
   add the selection as one operation.
5. Use the same Graph and Datasets inspector, output preview, and export actions.

This is contextual disclosure inside the import workflow, not a global expert
mode. Do not expose raw HDF5 mappings as the normal result interface.

### Behavior that avoids extra decisions

- Data + fit starts with measured symbols and a model line; share sample identity
  through color, with role distinguished by style. Avoid one legend entry for
  every component by default; allow independent editing when expanded.
- Residuals and distributions open separate appropriate graphs. Never combine
  intensity and residuals on one misleading axis merely to reduce tab count.
- Graph titles/axes come from the chosen quantities. Units remain visible.
- Show only transforms applicable to selected data and bar controls applicable
  to distributions. Unsupported options should not fill the inspector.
- Apply appearance templates without overriding scientific identity or silently
  inheriting another sample's fit parameters.
- Show a compact result summary and accessible provenance rather than every
  parameter as a permanent editable field.
- Preserve exact source selection for reuse. Add “Duplicate graph” / “Add from
  workspace” when implementing catalog reuse so comparisons do not require rereading.

### Usability gate for R1/R2

Run these with representative users/data, not just automated widget tests:

- Existing scattering file → normal I(Q): no additional required decision.
- Selected result file → measured data + fit: no manual paths or column mapping.
- Size result → distribution: correct axes immediately; representation change
  does not alter units or values.
- Several files → comparable results: understandable labels/order, one batch
  undo, and an explanation of missing results.
- Save → move/delete source copies → reopen and edit: no scientific information
  required from the original files.

## 8. Package schema and reproducibility

Plan a **schema v2** for generic curves. Reuse the root organization, but do not
silently reinterpret v1 `/data/Q` and `/data/I`. Reserving `IMAGE_2D` in an enum
is not implementation of calibrated images or a general schema migration.

Before writing the v2 specification, settle:

- Canonical x/y/errors/edges, axis semantics, quantity units, and result metadata.
- Stable result-group membership and row provenance; graph/series references.
- Snapshot meanings and transform/adapter/component versions.
- Catalog persistence versus graph-only export.
- Unknown fields/components and unsupported scientific geometry.

Acceptance:

- Pure, explicit v1 → v2 migration, operating on copies/in memory; no migration
  writes to a source file during opening. Retain support for current beta v1 files.
- Old files preserve numerical values, uncertainty, axes, styles, output size,
  annotations, and archived snapshot behavior.
- New packages embed every array and metadata item needed to reopen independently.
- Checksums, deduplication, atomic write validation, collision remapping, and
  invalid-canonical-data recovery continue to work.
- Newer files opened by old readers degrade to supported preview/inspection;
  verify this with a frozen old-reader fixture. Never promise editable backward
  compatibility where the older reader cannot understand the new semantics.
- Unknown JSON keys are retained by migrations; current dataclass parsing alone
  does not provide this guarantee.
- A preview must disclose unsupported rendering rather than imply a successful
  recreation of a different scientific view.

## 9. M0–M3: headless service and Aida MCP

### Headless API and MCP are related, but different layers

The API creates/validates graphs independently of widgets. MCP lets Aida invoke
that capability. A public API is useful to scripts and pyIrena even without MCP;
MCP should be a thin protocol adapter, not another graph-building implementation.

```text
GUI actions ───────────┐
Python / CLI ──────────┼→ application service → model / transforms / package writer
pyIrena handoff ───────┤                    └→ 2D rendering worker → images
Aida → MCP adapter ────┘
```

The existing Qt-independent `ApplicationController` is a useful starting point,
not yet a complete public contract. R0 addresses several mutation weaknesses.

### M0 — typed facade and shared validation

Define requests with exact selected curve descriptors, recipe ID/version,
per-series scientific parameters, template ID/version, limited presentation
overrides, dimensions and output destinations. Return graph/package IDs,
resolved selections, warnings, provenance, and artifact details.

Separate numeric work from rendering. Discovery, transformation, package
inspection and package writing should not require a QApplication. For 2D image
output, initially reuse the existing renderer in a controlled offscreen Qt
worker without opening the main window. “No visible GUI” does not mean “no Qt
runtime.” Test fonts, dimensions, layout settling, timeouts and worker cleanup.
Do not create a second Matplotlib styling system unless evidence warrants it.

### M1 — Python/CLI recipes

First recipes: raw I(Q), Porod/Kratky and other supported scattering views,
data + fit, residuals, and size distribution. Use the same defaults as the GUI.
Recipes define scientific intent and bundle layout; templates define appearance.

Return compact diagnostics: loaded/plotted/masked point counts, exact quantities
and units, missing errors, assumptions, chosen template and physical output size.
Reject incompatible requests before output. Provide a preview for visual review;
validation cannot prove that every label is aesthetically well placed.

Reproducibility means identical scientific selections, numerical results and
configuration. Pixel-identical output across platforms is not guaranteed because
fonts/renderers differ; record them and use tolerances for visual comparisons.

### M2 — narrow local MCP

Proposed tools (final names/schema to be defined with M0):

| Tool | Purpose |
|---|---|
| `inspect_data` | Discover primary/results data, identifiers, units, capabilities and warnings |
| `list_plot_recipes` | List compatible recipes and named templates |
| `create_plot` | Validate a recipe request, create graph(s), package and preview |
| `describe_package` | Inspect manifest, graph identities, roles, provenance and warnings |
| `export_plot` | Export selected graph(s) from an existing package |

Use `create_plot` with a data/fit recipe rather than a separate tool for every
analysis. Resources may expose manifests, previews, templates and documentation.
Keep large scientific arrays in files/records, outside routine model context.
Do not expose arbitrary code execution or raw HDF5 writing as plotting tools.

Prefer a local subprocess over stdio initially. The
[MCP transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
describes client-launched stdio servers; it also requires protocol-only stdout,
with logs on stderr. Select a supported SDK/protocol version at implementation
and verify it with Aida rather than pinning this roadmap to a speculative release.

Use authorized input/output roots and an explicit overwrite policy. Client
consent follows the user's configured authorization; do not require a new human
approval for every routine action already authorized in an Aida job. No source
mutation or fitting belongs in this server.

### M3 — production integration checks

- Aida starts the server in the documented environment, negotiates capabilities,
  creates a graph and receives a usable preview/package reference.
- A small instruction such as “Porod plot of these selected curves using this
  template” produces the same scientific result as the Python/CLI recipe.
- Test ambiguous multi-entry files, missing results, unsupported units, invalid
  parameters, empty masks, output failures, and malformed requests.
- Repeated/retried requests have an explicit artifact collision/idempotency
  policy; they do not overwrite files or accumulate hidden workspaces by accident.
- Cancellation/timeouts clean up workers and partial outputs. Concurrent requests
  use isolated graph state and respect Qt thread/process constraints.
- Document installation, dependencies and error recovery; run clean-environment
  and cross-platform checks. Remote HTTP and live GUI control remain later work.

## 10. R4 — tables and parameter trends

The future route is:

`Data Explorer / Data Selector / table file → table selection → generic curves`

Start with file or in-memory table handoff; add a “Send to Bernardyn” action once
both public APIs are stable. A table is an input/provenance object; Bernardyn
need not become a spreadsheet editor or duplicate pyIrena's analysis tools.

Minimum future table contract:

- Named columns with stable IDs, types, labels, units and optional uncertainty
  relationships; row IDs and source file/result/subgroup identities.
- Choose X, one or more Y columns, optional error columns, and a grouping column.
  Offer known defaults when the producer supplies them.
- Preserve missing values distinctly from zero, duplicates and row order. Sort
  deliberately and carry the row mapping; never silently average replicates.
- Preserve acquisition time, elapsed time, temperature, scan number, filename
  and file modification time as different concepts. Do not manufacture physical
  X values from arbitrary ordering; row index is an explicitly labelled fallback.
- Join X and Y from separate extracts by stable row/source keys, not list position.
  Report unmatched rows and duplicate keys.
- Level/population/peak numbers describe stored structure, not guaranteed physical
  correspondence across fits. Require an explicit mapping/grouping choice where
  correspondence is ambiguous.
- Start with numeric X. Categorical labels and richer time-axis formatting can
  follow without changing numeric curve storage.
- The saved package embeds selected columns/curves and enough row provenance to
  inspect each plotted point after the source table disappears.

First acceptance example: Rg with its uncertainty versus a known temperature
column across selected files, preserving missing results and level identity.
The existing `tabulate_parameter` API is a useful bridge, but its current
scan-number/mtime/name choices do not fully implement this workflow.

## 11. Delivery and effort

Estimates are broad engineering effort ranges including focused tests/docs,
not elapsed-time promises or autonomous-agent speed predictions. Upstream API
agreement, fixtures, cross-platform Qt work and feedback are the main uncertainties.

| Increment | Deliverable | Rough effort | Dependency / release gate |
|---|---|---|---|
| R0 | Reliable editing, imports, templates and exports | 4–8 days | Reproductions B1–B7 become regression checks |
| Contract design | Public result records and v2 design note | 2–4 days | Review with pyIrena producer behavior and real files |
| R1 | Unified/Size data + fit overlays | 3–6 days | Public pyIrena reader and R0; source-free round-trip |
| R2 | Generic XY, residuals, distributions, migration | 7–12 days | Signed-off semantics; bar-edge policy; migration fixtures |
| R3 | Result selection/bundles, metadata, templates, docs | 3–5 days | Essential simplicity already delivered in R1/R2 |
| M0–M1 | API, local recipes, offscreen image output | 5–9 days | Contracts stable; output parity with GUI |
| M2 | Aida-compatible local MCP prototype | 2–4 days | Working service and actual Aida smoke test |
| M3 | Installation, retries, concurrency and compatibility | 4–7 days | Feedback from prototype usage |
| R4 | Table handoff and parameter trends | 5–10 days | R2 and agreed table/row-provenance contract |

Do not sum overlapping design/service work into a release-date promise.
Re-estimate after R0 and the first producer/consumer fixture round-trip.

### First implementation session after planning

1. Implement R0 in small reviewable changes, starting with B1/B2.
2. Write a concrete result-record/v2 design with one Unified Fit and one Size
   Distribution file; settle unknown fields, uncertainty and distribution widths.
3. Implement one vertical slice: discover → select data + fit → render → save →
   reopen without original sources. Reuse it as the headless recipe fixture.
4. Add residuals and distributions through generic semantics, not temporary aliases.
5. Add the narrow service and MCP only after the same request works in Python.

## 12. Deferred work and open design details

Deferred: fitting/reduction, source edits, live GUI automation, remote multiuser
service, calibrated detector images/ROIs/contours, movies, arbitrary formula
languages, a full spreadsheet editor, and broad new export formats.

A previous statement promised detector support without changing the root schema.
The root layout is reusable, but calibrated image semantics and versioning need
their own design; they are not a constraint on R2 or a commitment of this plan.

Resolve during contract work, not by adding configuration controls prematurely:

- Which representative Simple Fits, Modeling and WAXS files join the first two
  acceptance families, including calculation-only/partial/older results?
- Can pyIrena expose authoritative size-bin edges, or should R2 first ship curves
  and add bar widths after that contract is settled?
- Which result metadata and uncertainty conventions are stable across versions?
- Does early user feedback justify a residual subpanel, or are separate tabs enough?
- What exact Aida transport/artifact handling and optional server packaging are
  supported? These were not inspected or tested during this review.

Maintain one source of roadmap truth here. Link specific follow-on design notes
and update [docs/TODO.md](../docs/TODO.md) when integration work actually starts.
Update release notes/user docs when behavior ships, not when a proposal is written.
