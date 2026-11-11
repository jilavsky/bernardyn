# Bernardyn graph package schema, version 3

Status: implemented by Bernardyn 1.0.0 (first written by 0.0.1b6). Native suffix: `.bernardyn.h5`.

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
future schema and do not rewrite it. From Bernardyn 1.2 on, a package with a
newer schema opens with no package path and no edit lock, so **Save** always
asks for a new file and can never overwrite it.

## Values added within version 3 (from Bernardyn 1.2)

New annotation kinds and curve roles do not need a schema bump. A 1.2 reader:

- keeps an annotation whose `kind` it does not know as its raw JSON object,
  does not draw it, and writes it back unchanged (after the known
  annotations) when the graph is saved;
- loads a generic curve whose `role` it does not know as a plain X/Y curve
  and writes the role string back unchanged.

Both are reported as notices when the package opens. Readers before 1.2
refuse such a package as invalid (they do not check
`minimum_reader_version`, which is informational), so a writer that adds a
kind or role should record `1.2.0` there. A change that alters the meaning of
existing fields still needs a new schema version.
