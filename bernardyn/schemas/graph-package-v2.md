# Bernardyn graph package schema, version 2

Status: implemented. Native suffix: `.bernardyn.h5`.

Version 2 retains the v1 root, manifest, environment, graph-document,
snapshot, preview, renderer-data, checksum, atomic-write, and recovery rules.
It adds typed generic scientific curves without changing the established
meaning of scattering `Q` and `I` arrays.

## Root and compatibility

The required root attributes and groups are the same as
[version 1](graph-package-v1.md), except `schema_version` is `2`.

A v2 reader opens v1 packages as scattering curves. Opening never rewrites a
package. Saving a v1 workspace writes a v2 package with each prior curve
explicitly identified as `scattering_curve_v1`; its arrays remain `Q`, `I`,
`Idev`, and `Qdev`.

## Canonical curve records

Each `/datasets/<dataset-uuid>` has a `dataset_sha256` attribute and UTF-8 JSON
`/metadata`. `metadata.canonical_type` selects exactly one payload:

| Canonical type | Required arrays | Optional arrays | Required metadata meaning |
|---|---|---|---|
| `scattering_curve_v1` | `/data/Q`, `/data/I` | `Idev`, `Qdev` | v1 `kind`, Q/intensity labels and units |
| `generic_curve_v2` | `/data/x`, `/data/y` | `dx`, `dy` | `role`, X/Y semantic IDs, labels, units, uncertainty kind |

Arrays in each payload are one-dimensional, non-empty, float-compatible, and
aligned. Every numeric array has a SHA-256 checksum over dtype, shape, and
C-order bytes. The dataset checksum includes canonical type, every present
array, and the absence of optional arrays.

Generic curves preserve scientific meaning independently of presentation. The
R2 roles are `residual` and `distribution`. A generic curve does not use a
scattering transform; it resolves only through the raw identity view. A graph
with one therefore must use the raw view.

## Provenance and uncertainty

Both canonical types store source fingerprint, provenance, and arbitrary
namespaced metadata. Generic metadata additionally records the curve role,
semantic IDs, display labels, display units, and `uncertainty_kind`. Omitted
`dx` or `dy` means absent uncertainty; it is never serialized as zeros.

## Migration

The v1-to-v2 interpretation is pure and in-memory: a v1 record without a
canonical-type marker is read as `scattering_curve_v1`. Its payload is copied
unchanged on a subsequent v2 save. Unknown fields inside metadata remain
available as metadata but are not interpreted by the v2 reader.
