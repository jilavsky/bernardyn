# Future integration work

## PyIrena → Bernardyn package export

Add a supported PyIrena-facing path to export graphs/data prepared in PyIrena
as a native Bernardyn `.bernardyn.h5` package. The exported package must carry
the canonical data, provenance, and enough graph configuration to open as an
editable Bernardyn graph without the original source files.

Design this as an additive shared API and avoid a PyIrena → Bernardyn runtime
dependency cycle. Bernardyn should remain the owner of its graph-document
schema and native package writer; PyIrena should expose the stable public
records/export inputs that Bernardyn can package.

Status: planned; not part of the current Bernardyn implementation.
