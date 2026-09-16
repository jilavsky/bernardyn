"""Public, widget-independent plot recipes for scripts and future integrations.

The facade owns recipe selection, source/result resolution, validation, native
package output, and optional offscreen 2-D rendering.  It deliberately does
not fit or modify scientific source files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import AxisSpec, Dataset, GenericCurve, GraphDocument, PlotSeries
from bernardyn.io.container import ensure_package_suffix
from bernardyn.io.results import (
    ResultBundle,
    ResultCurveBundle,
    ResultDescriptor,
    discover_results,
    load_result_bundle,
    load_result_curve,
)
from bernardyn.io.sources import ScatteringLocation
from bernardyn.template.graph_templates import apply_template, load_template


@dataclass(frozen=True)
class ScatteringInput:
    """An exact scattering-curve selection, or a file's preferred primary curve."""

    path: Path
    internal_path: str | None = None
    adapter_id: str | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path).expanduser().resolve())


@dataclass(frozen=True)
class ResultInput:
    """An exact public pyIrena result selection."""

    path: Path
    analysis: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path).expanduser().resolve())


@dataclass(frozen=True)
class Presentation:
    """Limited, recipe-safe appearance overrides."""

    title: str | None = None
    width_px: int | None = None
    height_px: int | None = None
    dpi: int | None = None
    template_path: Path | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("width_px", self.width_px),
            ("height_px", self.height_px),
            ("dpi", self.dpi),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.template_path is not None:
            object.__setattr__(self, "template_path", Path(self.template_path).expanduser().resolve())


@dataclass(frozen=True)
class PlotRequest:
    """A complete reproducible request to create one recipe graph.

    Source recipes use ``inputs``.  Saved-result recipes use ``result``.  A
    parameter row corresponds to the same-position scattering input, making
    parameters such as I0/Rg explicitly per series rather than inherited.
    """

    recipe_id: str
    inputs: tuple[ScatteringInput, ...] = ()
    result: ResultInput | None = None
    series_parameters: tuple[Mapping[str, float], ...] = ()
    presentation: Presentation = Presentation()
    package_path: Path | None = None
    image_path: Path | None = None
    overwrite: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "series_parameters", tuple(dict(row) for row in self.series_parameters))
        if self.package_path is not None:
            object.__setattr__(self, "package_path", Path(self.package_path).expanduser().resolve())
        if self.image_path is not None:
            object.__setattr__(self, "image_path", Path(self.image_path).expanduser().resolve())


@dataclass(frozen=True)
class RecipeDescriptor:
    id: str
    name: str
    description: str
    transform_id: str | None = None
    result_analysis: str | None = None
    result_kind: str | None = None
    version: str = "1"


RECIPES = (
    RecipeDescriptor("raw_iq", "Raw I(Q)", "Primary scattering curves in the General I(Q) view.", "raw"),
    RecipeDescriptor("guinier", "Guinier", "Primary scattering curves in the Guinier view.", "guinier"),
    RecipeDescriptor("guinier_rod", "Guinier rod", "Primary scattering curves in the Guinier rod view.", "guinier_rod"),
    RecipeDescriptor("guinier_sheet", "Guinier sheet", "Primary scattering curves in the Guinier sheet view.", "guinier_sheet"),
    RecipeDescriptor("porod", "Porod", "Primary scattering curves in the Porod view.", "porod"),
    RecipeDescriptor("kratky", "Kratky", "Primary scattering curves in the Kratky view.", "kratky"),
    RecipeDescriptor(
        "dimensionless_kratky",
        "Dimensionless Kratky",
        "Primary scattering curves using explicit per-series I0 and Rg.",
        "dimensionless_kratky",
    ),
    RecipeDescriptor("porod2", "Modified Porod 2", "Primary scattering curves in the modified Porod 2 view.", "porod2"),
    RecipeDescriptor("porod3", "Modified Porod 3", "Primary scattering curves in the modified Porod 3 view.", "porod3"),
    RecipeDescriptor("zimm", "Zimm", "Primary scattering curves in the Zimm view.", "zimm"),
    RecipeDescriptor("debye_bueche", "Debye–Bueche", "Primary scattering curves in the Debye–Bueche view.", "debye_bueche"),
    RecipeDescriptor(
        "unified_fit_data_fit", "Unified Fit data + fit", "Saved Unified Fit measured I(Q) and fit.",
        result_analysis="unified_fit", result_kind="data_fit",
    ),
    RecipeDescriptor(
        "unified_fit_residuals", "Unified Fit residuals", "Saved Unified Fit normalised residuals.",
        result_analysis="unified_fit", result_kind="residuals",
    ),
    RecipeDescriptor(
        "size_distribution_data_fit", "Size Distribution data + fit", "Saved Size Distribution I(Q) and fit.",
        result_analysis="size_distribution", result_kind="data_fit",
    ),
    RecipeDescriptor(
        "size_distribution_residuals", "Size Distribution residuals", "Saved Size Distribution residuals.",
        result_analysis="size_distribution", result_kind="residuals",
    ),
    RecipeDescriptor(
        "size_distribution_volume_distribution",
        "Size Distribution volume distribution",
        "Saved volume-fraction density P(r).",
        result_analysis="size_distribution",
        result_kind="volume_distribution",
    ),
)


@dataclass(frozen=True)
class PlotArtifact:
    kind: str
    path: Path


@dataclass(frozen=True)
class PlotDiagnostics:
    graph_id: str
    loaded_points: int
    plotted_points: int
    masked_points: int
    quantities: tuple[str, ...]
    warnings: tuple[str, ...]
    width_px: int
    height_px: int
    dpi: int


@dataclass
class PlotResult:
    """Created graph state plus stable artifact references and diagnostics."""

    controller: ApplicationController
    graph: GraphDocument
    artifacts: tuple[PlotArtifact, ...]
    diagnostics: PlotDiagnostics

    @property
    def package_path(self) -> Path | None:
        return next((item.path for item in self.artifacts if item.kind == "package"), None)


def list_recipes() -> tuple[RecipeDescriptor, ...]:
    return RECIPES


def inspect_data(path: str | Path) -> dict[str, object]:
    """Inspect supported scattering and saved-result choices without loading curves."""
    controller = ApplicationController()
    source = Path(path).expanduser().resolve()
    warnings: list[str] = []
    try:
        locations = controller.sources.discover_path(source)
    except Exception as exc:
        locations = []
        warnings.append(f"scattering discovery: {exc}")
    try:
        results = discover_results(source)
    except Exception as exc:
        results = []
        warnings.append(f"result discovery: {exc}")
    return {
        "path": str(source),
        "scattering": tuple(
            {
                "id": item.id,
                "adapter_id": item.adapter_id,
                "internal_path": item.internal_path,
                "display_name": item.display_name,
                "variant": item.variant,
            }
            for item in locations
        ),
        "results": tuple({"analysis": item.analysis, "title": item.title} for item in results),
        "warnings": tuple(warnings),
    }


class PlotService:
    """Create validated graph recipes without constructing a main window."""

    def create_plot(self, request: PlotRequest) -> PlotResult:
        recipe = _recipe(request.recipe_id)
        self._validate_request(request, recipe)
        controller = ApplicationController()
        graph = controller.workspace.graphs[0]
        if recipe.transform_id is not None:
            graph = self._create_scattering_graph(controller, graph, recipe, request)
        else:
            graph = self._create_result_graph(controller, graph, recipe, request)
        graph = self._apply_presentation(controller, graph, recipe, request.presentation)
        artifacts = self._write_artifacts(controller, graph, request)
        snapshots = controller.snapshots[graph.id]
        loaded = sum(_point_count(controller.workspace.datasets[view.dataset_id]) for view in graph.series)
        plotted = sum(len(snapshot.x) for snapshot in snapshots.values())
        diagnostics = PlotDiagnostics(
            graph_id=graph.id,
            loaded_points=loaded,
            plotted_points=plotted,
            masked_points=loaded - plotted,
            quantities=tuple(
                f"{snapshot.x_label} [{snapshot.x_unit}] vs {snapshot.y_label} [{snapshot.y_unit}]"
                for snapshot in snapshots.values()
            ),
            warnings=tuple(controller.graph_warnings(graph.id)),
            width_px=graph.width_px,
            height_px=graph.height_px,
            dpi=graph.dpi,
        )
        return PlotResult(controller=controller, graph=graph, artifacts=artifacts, diagnostics=diagnostics)

    def _validate_request(self, request: PlotRequest, recipe: RecipeDescriptor) -> None:
        if recipe.transform_id is not None:
            if not request.inputs or request.result is not None:
                raise ValueError(f"{recipe.id} requires one or more scattering inputs")
            if request.series_parameters and len(request.series_parameters) != len(request.inputs):
                raise ValueError("series_parameters must contain one row per scattering input")
        elif request.result is None or request.inputs:
            raise ValueError(f"{recipe.id} requires one saved result input")
        elif request.result.analysis != recipe.result_analysis:
            raise ValueError(f"{recipe.id} requires {recipe.result_analysis!r} results")
        destinations = [
            item
            for item in (
                ensure_package_suffix(request.package_path) if request.package_path is not None else None,
                request.image_path,
            )
            if item is not None
        ]
        if not destinations:
            raise ValueError("request a package_path, image_path, or both")
        for destination in destinations:
            if destination.exists() and not request.overwrite:
                raise FileExistsError(f"output already exists: {destination}")

    def _create_scattering_graph(
        self,
        controller: ApplicationController,
        graph: GraphDocument,
        recipe: RecipeDescriptor,
        request: PlotRequest,
    ) -> GraphDocument:
        controller.set_transform(graph.id, recipe.transform_id or "raw")
        graph = replace(controller.workspace.graph(graph.id), title=recipe.name)
        controller.update_graph(graph)
        datasets = tuple(self._load_scattering(controller, selection) for selection in request.inputs)
        parameters = request.series_parameters or tuple({} for _ in datasets)
        controller.add_datasets(datasets, graph_id=graph.id, transform_parameters=parameters)
        return controller.workspace.graph(graph.id)

    def _load_scattering(self, controller: ApplicationController, selection: ScatteringInput) -> Dataset:
        locations = controller.sources.discover_path(selection.path)
        chosen: list[ScatteringLocation]
        if selection.internal_path is None:
            chosen = controller.sources.select_preferred_locations(locations)
        else:
            chosen = [item for item in locations if item.internal_path == selection.internal_path]
        if selection.adapter_id is not None:
            chosen = [item for item in chosen if item.adapter_id == selection.adapter_id]
        if len(chosen) != 1:
            raise ValueError(
                f"selection {selection.path.name!r} did not resolve to exactly one scattering curve"
            )
        dataset = controller.sources.load_location(chosen[0]).to_dataset()
        return replace(dataset, label=selection.label) if selection.label else dataset

    def _create_result_graph(
        self,
        controller: ApplicationController,
        graph: GraphDocument,
        recipe: RecipeDescriptor,
        request: PlotRequest,
    ) -> GraphDocument:
        assert request.result is not None
        descriptor = _result_descriptor(request.result)
        if recipe.result_kind == "data_fit":
            bundle: ResultBundle = load_result_bundle(descriptor)
            controller.update_graph(
                replace(graph, title=f"{bundle.descriptor.title} data + fit")
            )
            controller.add_datasets(
                tuple(record.to_dataset() for record in bundle.records),
                graph_id=graph.id,
                series_styles=bundle.styles,
            )
            return controller.workspace.graph(graph.id)
        bundle = load_result_curve(descriptor, recipe.result_kind or "")
        assert isinstance(bundle, ResultCurveBundle)
        graph = replace(
            graph,
            title=bundle.graph_title,
            x_axis=AxisSpec(label=_axis_label(bundle.curve.x_label, bundle.curve.x_unit), log=bundle.x_log),
            y_axis=AxisSpec(label=_axis_label(bundle.curve.y_label, bundle.curve.y_unit), log=bundle.y_log),
        )
        controller.update_graph(graph)
        controller.add_datasets((bundle.curve,), graph_id=graph.id, series_styles=(bundle.style,))
        return controller.workspace.graph(graph.id)

    def _apply_presentation(
        self,
        controller: ApplicationController,
        graph: GraphDocument,
        recipe: RecipeDescriptor,
        presentation: Presentation,
    ) -> GraphDocument:
        template_identity: dict[str, str | int] | None = None
        if presentation.template_path is not None:
            template = load_template(presentation.template_path)
            template_transform = str(template.get("transform_id", "raw"))
            if template_transform != graph.view_transform_id:
                raise ValueError(
                    "template scientific view must match the recipe; templates cannot change data meaning"
                )
            graph = apply_template(graph, template)
            template_identity = {
                "name": str(template.get("name", presentation.template_path.stem)),
                "schema_version": int(template.get("schema_version", 0)),
            }
        width_px = presentation.width_px or graph.width_px
        height_px = presentation.height_px or graph.height_px
        dpi = presentation.dpi or graph.dpi
        graph = replace(
            graph,
            title=presentation.title or graph.title,
            width_px=width_px,
            height_px=height_px,
            width_in=width_px / dpi,
            height_in=height_px / dpi,
            dpi=dpi,
            renderer_config={
                **graph.renderer_config,
                "recipe": {"id": recipe.id, "version": recipe.version},
                **({"template": template_identity} if template_identity is not None else {}),
            },
        )
        controller.update_graph(graph, recompute=True)
        return controller.workspace.graph(graph.id)

    def _write_artifacts(
        self, controller: ApplicationController, graph: GraphDocument, request: PlotRequest
    ) -> tuple[PlotArtifact, ...]:
        artifacts: list[PlotArtifact] = []
        if request.package_path is not None:
            destination = ensure_package_suffix(request.package_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            artifacts.append(PlotArtifact("package", controller.save(destination, graph_ids=(graph.id,))))
        if request.image_path is not None:
            destination = request.image_path
            if destination.suffix.lower() not in {".png", ".jpg", ".jpeg", ".svg"}:
                raise ValueError("image_path must end in .png, .jpg, .jpeg, or .svg")
            destination.parent.mkdir(parents=True, exist_ok=True)
            render_2d_image(graph, controller.snapshots[graph.id], destination)
            artifacts.append(PlotArtifact("image", destination))
        return tuple(artifacts)


def create_plot(request: PlotRequest) -> PlotResult:
    """Create one reproducible plot request through the default service."""
    return PlotService().create_plot(request)


def render_2d_image(
    graph: GraphDocument, snapshots: Mapping[str, PlotSeries], destination: str | Path
) -> Path:
    """Render one 2-D graph offscreen without creating a Bernardyn main window."""
    if graph.renderer_id != "plot2d":
        raise ValueError("headless image output currently supports only 2-D graphs")
    # Must happen before the first QApplication is constructed.  Existing GUI
    # callers keep their own platform integration and can reuse this helper.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from bernardyn.renderers.plot2d import Plot2DWidget

    app = QApplication.instance() or QApplication(["bernardyn-headless"])
    widget = Plot2DWidget()
    widget.resize(graph.width_px, graph.height_px)
    try:
        widget.render(graph, snapshots)
        app.processEvents()
        return widget.save_image(destination)
    finally:
        widget.close()
        widget.deleteLater()


def _recipe(recipe_id: str) -> RecipeDescriptor:
    for recipe in RECIPES:
        if recipe.id == recipe_id:
            return recipe
    raise ValueError(f"unknown recipe {recipe_id!r}")


def _result_descriptor(selection: ResultInput) -> ResultDescriptor:
    for descriptor in discover_results(selection.path):
        if descriptor.analysis == selection.analysis:
            return descriptor
    raise ValueError(f"{selection.analysis!r} result is not available in {selection.path.name}")


def _axis_label(label: str, unit: str) -> str:
    return f"{label} [{unit}]" if unit else label


def _point_count(dataset: Dataset | GenericCurve) -> int:
    return dataset.point_count
