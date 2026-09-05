# Data flow and file formats

## Data flow

```text
Source file
  → source adapter discovers selectable entries
  → canonical Dataset (Q, I, optional dI/dQ, units, provenance)
  → SeriesView (transform, range, multiplier/offset, style)
  → resolved PlotSeries snapshot (displayed x/y/dx/dy arrays)
  → 2D or 3D renderer
```

Widgets send editing commands to the workspace model. They do not own the
scientific arrays or reconstruct a graph from PyQtGraph objects.

Canonical `Dataset` arrays are never overwritten by a graph operation. A
linearization, visible-Q range, multiplier, or offset produces a new resolved
`PlotSeries` for that graph. This keeps source data intact while preserving the
exact plotted values in an archive.

## Input formats

| File type | Role in Bernardyn |
|---|---|
| `.h5`, `.hdf5`, `.nxs` | Source HDF5/NXcanSAS data. Bernardyn discovers selectable 1-D entries and does not modify the file. |
| `.dat`, `.txt`, `.csv` | Source text data with two to four columns. |
| `.bernardyn.h5` | Native portable graph or workspace package. Open with **File → Open package…**. |
| `.h5xp` | Igor/PyIrena data export only; not a Bernardyn graph package. |
| `.bernardyn-template.json` | Data-free formatting template. |

## Native `.bernardyn.h5` contents

The native package is an ordinary HDF5 file with UTF-8 JSON configuration and
portable numeric datasets. It contains:

- `/datasets`: canonical scientific arrays and metadata, stored once per UUID;
- `/graphs`: graph documents and graph-specific resolved snapshots;
- `/manifest`: graph order, active graph, workspace title/description, and
  optional window layout;
- `/environment`: creating software versions;
- optional graph previews and renderer-specific 3D arrays.

Source paths are retained only as provenance. A package must reopen even when
the original files were moved or deleted. Checksums validate canonical arrays
and resolved snapshots. The full version-1 contract is in
[`graph-package-v1.md`](../bernardyn/schemas/graph-package-v1.md).

## Export formats

Image and data exports are not packages:

- PNG/JPEG/SVG export an image of the graph (SVG is available for 2D only).
- CSV and Igor ITX export displayed curve data.
- Igor `.h5xp` exports canonical datasets for Igor/PyIrena interoperability.
  It does not reproduce Bernardyn graph formatting in Igor.
