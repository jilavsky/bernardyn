# Bernardyn graph package schema, version 1

Status: implemented by Bernardyn 0.0.1b1. Native suffix: `.bernardyn.h5`.

## Principles

A package is self-contained. Source paths are provenance only. Numeric arrays
are ordinary portable HDF5 datasets, structured configuration is UTF-8 JSON,
and references are UUID strings. Pickles, executable recreation instructions,
and HDF5 external links are forbidden.

The same schema represents one graph or a workspace. Shared canonical datasets
appear once; graph-specific resolved snapshots remain separate.

## Root

Required root attributes:

| Attribute | Type | Meaning |
|---|---|---|
| `bernardyn_format` | UTF-8 string | Exact magic `BERNARDYN_GRAPH_PACKAGE` |
| `schema_version` | integer | `1` |
| `container_kind` | enum string | `graph` or `workspace` |
| `content_uuid` | UUID string | Workspace/content identity |
| `created_utc` | ISO-8601 string | Initial package creation time |
| `updated_utc` | ISO-8601 string | Last save time |
| `created_with` | string | Bernardyn version |
| `minimum_reader_version` | string | Minimum compatible Bernardyn version |

Required root groups are `/manifest`, `/environment`, `/datasets`, and
`/graphs`.

## Manifest and environment

`/manifest/document` is UTF-8 JSON with `workspace_id`, `title`, `description`,
ordered `graph_ids`, `dataset_ids`, `active_graph_id`, and optional
`layout_state`. Layout state may describe multiple graph tabs and dock/window
state; it is not required to interpret a graph.

`/environment/document` is UTF-8 JSON recording the creating versions of
Bernardyn, PyIrena, NumPy, h5py, PySide6, PyQtGraph, PyOpenGL, Python, and the
operating system.

## Canonical datasets

Each `/datasets/<dataset-uuid>` has:

- attribute `dataset_sha256`, covering all canonical arrays including absence;
- `/data/Q` and `/data/I`, normally float64, with the same non-zero length;
- optional `/data/Idev` and `/data/Qdev`, matching that length;
- `/metadata`, UTF-8 JSON containing the UUID, `kind`, label, canonical Q and
  intensity units, sample metadata, provenance, original source/internal HDF5
  location, source fingerprint, and conversion/cleaning report.

The version-1 `kind` enum is `curve_1d`; `image_2d` is reserved for the detector
milestone. Q is canonicalized to inverse ångström by Bernardyn on import. NaN or
infinite source values may be retained for provenance, but transforms must mask
them and report the mask; shapes and checksums are always validated.

Every numeric dataset has a `sha256` attribute calculated over dtype, shape,
and C-order bytes. Gzip level 4 plus shuffle is used where beneficial and no
nonstandard compression filter is required.

## Graph documents and snapshots

Each `/graphs/<graph-uuid>` has:

- attribute `renderer_id`;
- `/document`, UTF-8 JSON serialization of `GraphDocument`;
- `/series/<series-uuid>/snapshot` with required `x`, `y`, `source_indices` and
  optional `dx`, `dy` numeric datasets;
- `/series/<series-uuid>` attributes `dataset_id`, `transform_id`, and
  `transform_version`, plus JSON `metadata` for labels, units, warnings, and
  archival state;
- optional `/preview`, gzip-compressed PNG bytes with MIME type and checksum;
- optional `/renderer-data/<name>` numeric arrays with checksums.

`GraphDocument` contains ordered `SeriesView` values, axis range/log/grid/style
state, full RGBA colors, font family and sizes, legend state, graph pixel and
physical inch dimensions plus output DPI,
text/arrows/horizontal/vertical annotations with coordinates and
z-order, descriptions and notes, plus opaque renderer configuration. A 3D
configuration records mode, spacing, normalization, common-grid sample count,
series-axis mapping, grid visibility, projection, and camera state.

## Opening and recovery

The archived snapshot is the authoritative initial display. Style-only changes
continue from it. A transform version mismatch is shown as archival-snapshot
mode until the user explicitly requests recomputation. A missing or corrupt
snapshot is recomputed from valid embedded canonical arrays with a warning. If
canonical data fail validation but snapshots are valid, the affected graph is
read-only. If both are unusable, opening fails.

Unknown transforms and renderers remain in JSON and use the PNG preview when
available. A schema newer than the reader opens in preview/inspection mode and
is never rewritten automatically.

## Writes, imports, and migrations

Writers create a temporary file in the destination directory, flush and fully
validate it, then atomically replace the destination. Readers never migrate a
file in place. Future migrations are ordered pure `vN → vN+1` transformations,
retain unknown fields, and write a new file before replacement.

Graph import copies only referenced datasets. An existing dataset is reused
only when UUID and canonical checksum agree. UUID collisions with unequal
content are remapped along with all graph/series references.

This schema is Bernardyn-native. `.h5xp` remains a separate PyIrena/Igor data
export and does not carry Bernardyn graph formatting.
