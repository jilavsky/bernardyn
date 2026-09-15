# R2 generic-curve and package-v2 contract

Status: implementation contract for R2, prepared 2026-09-15.

This contract enables pyIrena residuals and size distributions without
misrepresenting either as scattering `Q/I` data. It is based on
`testData/Al_Mg_Si__40C_0min_0498.h5` and pyIrena's public
`pyirena.io.results.load_result` reader.

## R2 acceptance set

| Result | Public reader arrays | Graph recipe | R2 decision |
|---|---|---|---|
| Unified Fit residuals | `Q`, `residuals` | Q versus normalised residual, linear Y, zero reference | supported |
| Size Distribution residuals | `Q`, `residuals` | Q versus normalised residual, linear Y, zero reference | supported |
| Size Distribution P(r) | `r_grid`, `distribution`, optional `distribution_std` | radius versus volume-fraction density, line/centre points | supported |
| Number/surface/cumulative distributions | producer-specific arrays outside the public result record | undecided | excluded |
| Modeling result | no supported generic pyIrena result reader | — | excluded |

The fixture stores 201 radius centres but no authoritative bin edges. R2 will
therefore use a line/centre-point presentation. It will not claim histogram
widths, infer a density conversion, or draw bars.

## Canonical curve record

The v2 canonical record is a `GenericCurve` independent of scattering data.
It has read-only, aligned arrays `x`, `y`, optional `dx`, optional `dy`; stable
UUID identity; label; role; semantic identifiers; display labels and units;
uncertainty meaning; metadata; and provenance. Resolved plot snapshots carry
their source-index mapping.

Required R2 values are:

| Field | Residual | P(r) |
|---|---|---|
| `x_semantic` | `scattering_q` | `particle_radius` |
| `y_semantic` | `normalised_residual` | `volume_fraction_density_per_radius` |
| `x_unit` | `1/angstrom` | `angstrom` |
| `y_unit` | `dimensionless` | `1/angstrom` |
| role | `residual` | `distribution` |
| uncertainty meaning | `absent` | `measured` when pyIrena supplies `distribution_std`, otherwise `absent` |

No missing uncertainty is converted to zero. Values with invalid X or Y are
masked independently of missing uncertainty. Normalised residuals retain
negative values and must use a linear Y axis.

Scattering `Dataset` remains a separate v1-compatible canonical type. Only it
may be offered scattering transforms. Generic curves initially support the
identity view only; a graph rejects a non-identity scattering transform for a
generic curve.

## Package version 2

Version 2 keeps the root and graph layout of v1. Each dataset metadata document
declares exactly one canonical type:

- `scattering_curve_v1`: existing `/data/Q`, `/data/I`, optional `Idev` and
  `Qdev`; this preserves the scientific meanings and byte-level values of v1.
- `generic_curve_v2`: `/data/x`, `/data/y`, optional `dx` and `dy`; metadata
  contains curve role, axis semantic IDs, labels, units, uncertainty meaning,
  result identity, and provenance.

Dataset checksums include the type tag, every present canonical array, and the
absence of optional arrays. Snapshots remain resolved display values and retain
their existing checksum/recovery behaviour.

Opening a v1 package creates the same in-memory scattering datasets and does
not write to disk. Saving that workspace in v2 stores those datasets as
`scattering_curve_v1`; no Q/I field is renamed or reinterpreted. An explicit
pure `v1_to_v2` in-memory migration helper will be tested independently. Future
unknown generic fields are preserved in metadata but are not interpreted.

## Result membership and provenance

Every curve produced from one result carries the same namespaced result identity:
source fingerprint; analysis (`unified_fit` or `size_distribution`); public
reader identifier/version; result timestamp/program; role; and public fit
summary. This relates I(Q), residual, and P(r) curves without fabricating a
producer run ID.

R2 result import will offer only the actual public-reader capabilities in a
source file: **Data + fit**, **Residuals**, and (for Size Distribution)
**Distribution**. It will create separate graphs for residuals and P(r), and
each selected file batch remains one undoable operation.
