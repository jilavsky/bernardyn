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

Status: Bernardyn now provides the headless [`PlotRequest` recipe facade and
CLI](headless-recipes.md), including public pyIrena result readers. A
PyIrena-side exporter or handoff remains planned; it must call that public
facade rather than write Bernardyn HDF5 groups directly.

## Local MCP recipe adapter

Bernardyn now also provides a five-tool local stdio
[MCP server](mcp.md) over that same facade. Next validation is with the local
agents that consume pyIrena's grouped MCP surface; do not grow Bernardyn into
a per-recipe/per-renderer tool catalog. Live GUI control and remote transport
remain deferred.
