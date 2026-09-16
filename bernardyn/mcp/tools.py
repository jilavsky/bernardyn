"""Five narrow MCP operations backed exclusively by Bernardyn's public API."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Mapping

from bernardyn.api import (
    PlotRequest,
    Presentation,
    ResultInput,
    ScatteringInput,
    create_plot,
    render_2d_image,
)
from bernardyn.api import (
    inspect_data as _inspect_data,
)
from bernardyn.api import (
    list_recipes as _list_recipes,
)
from bernardyn.core.controller import ApplicationController
from bernardyn.io.container import load_package
from bernardyn.mcp.paths import output_path, resolve_input

TOOL_GROUPS = {
    "discovery": ("bernardyn_inspect_data", "bernardyn_list_plot_recipes"),
    "create": ("bernardyn_create_plot",),
    "package": ("bernardyn_describe_package", "bernardyn_export_plot"),
}


def inspect_data(path: str) -> dict[str, Any]:
    """Discovery group: list a file's scattering/result capabilities and warnings."""
    return _inspect_data(resolve_input(path))


def list_plot_recipes() -> dict[str, Any]:
    """Discovery group: list stable recipe IDs grouped by scattering/result use."""
    recipes = [asdict(item) for item in _list_recipes()]
    return {
        "tool_groups": TOOL_GROUPS,
        "recipes": recipes,
        "guidance": (
            "Call bernardyn_inspect_data first. Use bernardyn_create_plot for all graph "
            "creation; result recipes need result_path, scattering recipes need input_paths."
        ),
    }


def create_plot_artifact(
    recipe_id: str,
    input_paths: list[str] | None = None,
    result_path: str | None = None,
    internal_paths: list[str] | None = None,
    series_parameters: list[Mapping[str, float]] | None = None,
    output_name: str = "bernardyn-plot",
    image_format: str = "png",
    title: str | None = None,
    width_px: int = 1600,
    height_px: int = 1000,
    dpi: int = 250,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create group: make one validated package plus PNG/JPEG/SVG preview.

    ``output_name`` is a filename stem inside ``BERNARDYN_OUTPUT_ROOT`` (or
    the temporary Bernardyn MCP cache). It cannot address arbitrary paths.
    """
    recipe = next((item for item in _list_recipes() if item.id == recipe_id), None)
    if recipe is None:
        raise ValueError(f"unknown recipe {recipe_id!r}")
    extension = image_format.lower().lstrip(".")
    if extension not in {"png", "jpg", "jpeg", "svg"}:
        raise ValueError("image_format must be png, jpg, jpeg, or svg")
    package_path = output_path(output_name, ".bernardyn.h5")
    image_path = output_path(output_name, f".{extension}")
    if recipe.result_analysis is not None:
        if result_path is None:
            raise ValueError(f"{recipe_id} requires result_path")
        result = ResultInput(resolve_input(result_path), recipe.result_analysis)
        inputs = ()
    else:
        if not input_paths:
            raise ValueError(f"{recipe_id} requires one or more input_paths")
        internal = internal_paths or []
        if len(internal) > len(input_paths):
            raise ValueError("internal_paths cannot contain more items than input_paths")
        inputs = tuple(
            ScatteringInput(resolve_input(path), internal_path=internal[index] if index < len(internal) else None)
            for index, path in enumerate(input_paths)
        )
        result = None
    request = PlotRequest(
        recipe_id=recipe_id,
        inputs=inputs,
        result=result,
        series_parameters=tuple(series_parameters or ()),
        presentation=Presentation(title=title, width_px=width_px, height_px=height_px, dpi=dpi),
        package_path=package_path,
        image_path=image_path,
        overwrite=overwrite,
    )
    created = create_plot(request)
    return {
        "recipe": {"id": recipe.id, "version": recipe.version},
        "graph_id": created.graph.id,
        "package_path": str(created.package_path),
        "preview_path": str(image_path),
        "diagnostics": asdict(created.diagnostics),
        "warnings": list(created.diagnostics.warnings),
    }


def describe_package(path: str) -> dict[str, Any]:
    """Package group: inspect graph/dataset semantics without returning arrays."""
    loaded = load_package(resolve_input(path))
    graphs = []
    for graph in loaded.workspace.graphs:
        series = []
        for view in graph.series:
            dataset = loaded.workspace.datasets[view.dataset_id]
            semantic = (
                {
                    "canonical_type": "generic_curve_v2",
                    "role": dataset.role.value,
                    "x_semantic": dataset.x_semantic,
                    "y_semantic": dataset.y_semantic,
                    "x_unit": dataset.x_unit,
                    "y_unit": dataset.y_unit,
                }
                if hasattr(dataset, "role")
                else {
                    "canonical_type": "scattering_curve_v1",
                    "q_unit": dataset.q_unit,
                    "intensity_unit": dataset.intensity_unit,
                }
            )
            series.append(
                {
                    "series_id": view.id,
                    "dataset_id": dataset.id,
                    "label": dataset.label,
                    "transform_id": view.transform_id,
                    "visible": view.visible,
                    "points": dataset.point_count,
                    **semantic,
                }
            )
        graphs.append(
            {
                "id": graph.id,
                "title": graph.title,
                "renderer_id": graph.renderer_id,
                "recipe": graph.renderer_config.get("recipe"),
                "x_axis": {"label": graph.x_axis.label, "log": graph.x_axis.log},
                "y_axis": {"label": graph.y_axis.label, "log": graph.y_axis.log},
                "series": series,
            }
        )
    return {
        "path": str(loaded.path),
        "workspace": {"id": loaded.workspace.id, "title": loaded.workspace.title},
        "graphs": graphs,
        "warnings": loaded.warnings,
        "read_only_graph_ids": sorted(loaded.read_only_graphs),
    }


def export_plot(
    package_path: str,
    graph_id: str,
    output_name: str = "bernardyn-export",
    image_format: str = "png",
    width_px: int | None = None,
    height_px: int | None = None,
    dpi: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Package group: render one archived 2-D graph to an authorised output path."""
    extension = image_format.lower().lstrip(".")
    if extension not in {"png", "jpg", "jpeg", "svg"}:
        raise ValueError("image_format must be png, jpg, jpeg, or svg")
    destination = output_path(output_name, f".{extension}")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {destination}")
    controller = ApplicationController()
    loaded = controller.open_package(resolve_input(package_path))
    graph = controller.workspace.graph(graph_id)
    if graph.id in loaded.read_only_graphs:
        raise PermissionError("cannot export a graph whose canonical data failed validation")
    width = width_px or graph.width_px
    height = height_px or graph.height_px
    output_dpi = dpi or graph.dpi
    graph = replace(
        graph,
        width_px=width,
        height_px=height,
        width_in=width / output_dpi,
        height_in=height / output_dpi,
        dpi=output_dpi,
    )
    render_2d_image(graph, controller.snapshots.get(graph.id, {}), destination)
    return {
        "graph_id": graph.id,
        "path": str(destination),
        "width_px": graph.width_px,
        "height_px": graph.height_px,
        "dpi": graph.dpi,
        "warnings": loaded.warnings,
    }
