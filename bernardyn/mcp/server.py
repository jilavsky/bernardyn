"""Stdio MCP server for the five-tool Bernardyn recipe surface."""

from __future__ import annotations

import logging
import sys
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised in minimal installs
    raise ImportError(
        "Bernardyn MCP support requires the mcp 1.x SDK. Install with: "
        "pip install 'bernardyn[mcp]'"
    ) from exc

from bernardyn.mcp import tools

mcp = FastMCP(
    "bernardyn",
    instructions=(
        "Create portable Bernardyn scientific-plot packages through a small local tool surface. "
        "Start with bernardyn_inspect_data, then bernardyn_list_plot_recipes, and use "
        "bernardyn_create_plot for all graph creation. The five tools are grouped as discovery "
        "(inspect/list), create, and package (describe/export). Inputs are read-only; outputs are "
        "confined to BERNARDYN_OUTPUT_ROOT or the temporary Bernardyn MCP cache."
    ),
)


@mcp.tool()
def bernardyn_inspect_data(path: str) -> dict[str, Any]:
    """Discovery: list one data file's scattering/result capabilities and warnings."""
    return tools.inspect_data(path)


@mcp.tool()
def bernardyn_list_plot_recipes() -> dict[str, Any]:
    """Discovery: list recipe IDs, tool groups, and concise guidance."""
    return tools.list_plot_recipes()


@mcp.tool()
def bernardyn_create_plot(
    recipe_id: str,
    input_paths: list[str] | None = None,
    result_path: str | None = None,
    internal_paths: list[str] | None = None,
    series_parameters: list[dict[str, float]] | None = None,
    output_name: str = "bernardyn-plot",
    image_format: str = "png",
    title: str | None = None,
    width_px: int = 1600,
    height_px: int = 1000,
    dpi: int = 250,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create: write one portable package and matching 2-D preview image."""
    return tools.create_plot_artifact(
        recipe_id,
        input_paths=input_paths,
        result_path=result_path,
        internal_paths=internal_paths,
        series_parameters=series_parameters,
        output_name=output_name,
        image_format=image_format,
        title=title,
        width_px=width_px,
        height_px=height_px,
        dpi=dpi,
        overwrite=overwrite,
    )


@mcp.tool()
def bernardyn_describe_package(path: str) -> dict[str, Any]:
    """Package: inspect graphs, curve semantics, recipes, and warnings without arrays."""
    return tools.describe_package(path)


@mcp.tool()
def bernardyn_export_plot(
    package_path: str,
    graph_id: str,
    output_name: str = "bernardyn-export",
    image_format: str = "png",
    width_px: int | None = None,
    height_px: int | None = None,
    dpi: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Package: render one stored 2-D graph to PNG, JPEG, or SVG."""
    return tools.export_plot(
        package_path,
        graph_id,
        output_name=output_name,
        image_format=image_format,
        width_px=width_px,
        height_px=height_px,
        dpi=dpi,
        overwrite=overwrite,
    )


def main() -> None:
    """Run over stdio; logging is deliberately routed only to stderr."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
