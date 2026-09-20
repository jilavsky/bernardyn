# Bernardyn graph package schema, version 3

Status: implemented by Bernardyn 0.0.1b6. Native suffix: `.bernardyn.h5`.

Version 3 retains every version-2 rule for datasets, graph documents,
snapshots, previews, checksums, and atomic writes. It adds persisted
power-law slope annotations for log-log scattering graphs.

## Annotation extension

`GraphDocument.annotations` may contain a `power_law` annotation. Its
`position` is the geometric centre of the guide, and `slope` is the finite
power `P` in `I = B q^-P`. The renderer derives `B` from the centre position,
draws one decade in Q, and may persist a user-selected label size and position.

## Compatibility

A v3 reader opens v1 and v2 packages unchanged. Because version-2 readers do
not recognize the new annotation kind or its `slope` field, all v3 writers set
`minimum_reader_version` to `0.0.1b6`. Older readers treat a v3 package as a
future schema and do not rewrite it.
