"""Qt-independent application controller for workspaces and graph packages."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from bernardyn.core.models import (
    Dataset,
    GraphDocument,
    PlotSeries,
    SeriesStyle,
    SeriesView,
    Workspace,
)
from bernardyn.core.transforms import TransformRegistry, builtin_transforms, resolve_series
from bernardyn.io.container import LoadedPackage, import_graphs, load_package, save_package
from bernardyn.io.sources import ScatteringLocation, SourceRegistry, builtin_sources

PALETTE = (
    (31, 119, 180, 255),
    (214, 39, 40, 255),
    (44, 160, 44, 255),
    (148, 103, 189, 255),
    (255, 127, 14, 255),
    (23, 190, 207, 255),
    (140, 86, 75, 255),
    (227, 119, 194, 255),
)


class ApplicationController:
    def __init__(
        self,
        *,
        transforms: TransformRegistry | None = None,
        sources: SourceRegistry | None = None,
    ) -> None:
        self.transforms = transforms or builtin_transforms()
        self.sources = sources or builtin_sources()
        self.workspace = Workspace()
        self.snapshots: dict[str, dict[str, PlotSeries]] = {}
        self.previews: dict[str, bytes] = {}
        self.renderer_data: dict[str, dict[str, Any]] = {}
        self.read_only_graphs: set[str] = set()
        self.preview_only_graphs: set[str] = set()
        self._graph_warnings: dict[str, list[str]] = {}
        self.package_path: Path | None = None
        self.warnings: list[str] = []
        self.new_graph()

    def new_workspace(self, title: str = "Untitled workspace") -> None:
        self.workspace = Workspace(title=title)
        self.snapshots.clear()
        self.previews.clear()
        self.renderer_data.clear()
        self.read_only_graphs.clear()
        self.preview_only_graphs.clear()
        self._graph_warnings.clear()
        self.package_path = None
        self.warnings.clear()
        self.new_graph()

    def new_graph(self, renderer_id: str = "plot2d", title: str | None = None) -> GraphDocument:
        number = len(self.workspace.graphs) + 1
        graph = GraphDocument(
            title=title or f"Scattering plot {number}",
            renderer_id=renderer_id,
            renderer_config={
                "mode": "surface" if renderer_id == "opengl_surface" else "waterfall",
                "renderer_version": "1.0",
                "spacing": 1.0,
                "normalization": "none",
                "surface_samples": 512,
                "series_axis_key": "",
                "series_positions": {},
                "projection": "perspective",
                "show_grid": True,
                "camera": {"distance": 40.0, "elevation": 25.0, "azimuth": -45.0},
            }
            if renderer_id.startswith("opengl")
            else {"renderer_version": "1.0"},
        )
        self.workspace.add_graph(graph)
        self.snapshots[graph.id] = {}
        return graph

    def close_graph(self, graph_id: str) -> None:
        self.workspace.graphs = [graph for graph in self.workspace.graphs if graph.id != graph_id]
        self.snapshots.pop(graph_id, None)
        self.previews.pop(graph_id, None)
        self.renderer_data.pop(graph_id, None)
        self.read_only_graphs.discard(graph_id)
        self.preview_only_graphs.discard(graph_id)
        self._graph_warnings.pop(graph_id, None)
        if not self.workspace.graphs:
            self.new_graph()
        self.workspace.active_graph_id = self.workspace.graphs[-1].id
        self.workspace.dirty = True

    def add_dataset(self, dataset: Dataset, *, graph_id: str | None = None) -> SeriesView:
        self.workspace.add_dataset(dataset)
        graph = self.workspace.graph(graph_id or self.workspace.active_graph_id or "")
        series = SeriesView(
            dataset_id=dataset.id,
            legend_label=dataset.label,
            style=SeriesStyle(color=PALETTE[len(graph.series) % len(PALETTE)]),
        )
        self.workspace.replace_graph(graph.replace_series((*graph.series, series)))
        self.recompute_graph(graph.id)
        return series

    def load_location(
        self,
        location: ScatteringLocation,
        *,
        graph_id: str | None = None,
        q_unit: str = "1/A",
        error_fraction: float = 0.05,
    ) -> Dataset:
        record = self.sources.load_location(
            location, q_unit=q_unit, error_fraction=error_fraction
        )
        dataset = record.to_dataset()
        self.add_dataset(dataset, graph_id=graph_id)
        return dataset

    def update_graph(self, graph: GraphDocument, *, recompute: bool = False) -> None:
        if graph.id in self.read_only_graphs:
            raise PermissionError("this graph is read-only because its canonical data are invalid")
        self.workspace.replace_graph(graph)
        if recompute:
            self.recompute_graph(graph.id)

    def recompute_graph(self, graph_id: str) -> dict[str, PlotSeries]:
        if graph_id in self.read_only_graphs:
            raise PermissionError("cannot recompute a graph with invalid canonical data")
        graph = self.workspace.graph(graph_id)
        resolved: dict[str, PlotSeries] = {}
        for view in graph.series:
            dataset = self.workspace.datasets[view.dataset_id]
            resolved[view.id] = resolve_series(
                dataset,
                view,
                self.transforms,
                x_log=graph.x_axis.log,
                y_log=graph.y_axis.log,
            )
        self.snapshots[graph_id] = resolved
        self._graph_warnings[graph_id] = [
            warning
            for warning in self._graph_warnings.get(graph_id, [])
            if "current version" not in warning and "was recomputed" not in warning
        ]
        self.workspace.dirty = True
        return resolved

    def set_transform(
        self,
        graph_id: str,
        transform_id: str,
        parameters: Mapping[str, float] | None = None,
    ) -> None:
        graph = self.workspace.graph(graph_id)
        transform = self.transforms.get(transform_id)
        series = tuple(
            replace(
                item,
                transform_id=transform_id,
                transform_parameters=dict(parameters or {}),
            )
            for item in graph.series
        )
        graph = replace(
            graph,
            series=series,
            x_axis=replace(
                graph.x_axis,
                label=transform.default_x_label,
                log=transform.default_x_log,
                auto_range=True,
            ),
            y_axis=replace(
                graph.y_axis,
                label=transform.default_y_label,
                log=transform.default_y_log,
                auto_range=True,
            ),
        )
        self.update_graph(graph, recompute=True)

    def remove_series(self, graph_id: str, series_id: str) -> None:
        graph = self.workspace.graph(graph_id)
        self.update_graph(
            graph.replace_series(item for item in graph.series if item.id != series_id),
            recompute=True,
        )

    def move_series(self, graph_id: str, series_id: str, offset: int) -> None:
        graph = self.workspace.graph(graph_id)
        items = list(graph.series)
        old = next(index for index, item in enumerate(items) if item.id == series_id)
        new = max(0, min(len(items) - 1, old + offset))
        items.insert(new, items.pop(old))
        self.update_graph(graph.replace_series(items), recompute=False)

    def open_package(self, path: str | Path) -> LoadedPackage:
        loaded = load_package(path)
        self.workspace = loaded.workspace
        self.snapshots = loaded.snapshots
        self.previews = loaded.previews
        self.renderer_data = loaded.renderer_data
        self.read_only_graphs = loaded.read_only_graphs
        self.preview_only_graphs.clear()
        self._graph_warnings.clear()
        self.package_path = loaded.path
        self.warnings = loaded.warnings
        recovered = False
        for graph in self.workspace.graphs:
            graph_warnings = self._graph_warnings.setdefault(graph.id, [])
            for view in graph.series:
                archived = self.snapshots.get(graph.id, {}).get(view.id)
                try:
                    transform = self.transforms.get(view.transform_id)
                except KeyError:
                    graph_warnings.append(
                        f"Unknown transform {view.transform_id!r}; showing the archived preview when available"
                    )
                    if graph.id in self.previews:
                        self.preview_only_graphs.add(graph.id)
                    continue
                if archived is not None and archived.transform_version != transform.version:
                    graph_warnings.append(
                        f"{transform.name} snapshot uses version {archived.transform_version}; "
                        f"current version is {transform.version}. Use Recompute with Current Version explicitly."
                    )
                    continue
                if archived is None:
                    dataset = self.workspace.datasets[view.dataset_id]
                    self.snapshots.setdefault(graph.id, {})[view.id] = resolve_series(
                        dataset,
                        view,
                        self.transforms,
                        x_log=graph.x_axis.log,
                        y_log=graph.y_axis.log,
                    )
                    graph_warnings.append(
                        f"Missing or corrupt snapshot for {dataset.label!r} was recomputed from embedded data"
                    )
                    recovered = True
        if recovered:
            self.workspace.dirty = True
        return loaded

    def import_from_package(
        self, path: str | Path, graph_ids: Iterable[str] | None = None
    ) -> dict[str, str]:
        loaded = load_package(path)
        selected = list(graph_ids) if graph_ids is not None else [g.id for g in loaded.workspace.graphs]
        graph_map, snapshots = import_graphs(self.workspace, loaded, selected)
        self.snapshots.update(snapshots)
        for old_id, new_id in graph_map.items():
            if old_id in loaded.previews:
                self.previews[new_id] = loaded.previews[old_id]
            if old_id in loaded.renderer_data:
                self.renderer_data[new_id] = loaded.renderer_data[old_id]
            if old_id in loaded.read_only_graphs:
                self.read_only_graphs.add(new_id)
        self.warnings.extend(loaded.warnings)
        return graph_map

    def save(
        self,
        path: str | Path | None = None,
        *,
        graph_ids: Iterable[str] | None = None,
        previews: Mapping[str, bytes] | None = None,
        renderer_data: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> Path:
        destination = Path(path) if path is not None else self.package_path
        if destination is None:
            raise ValueError("a destination path is required for the first save")
        chosen = list(graph_ids) if graph_ids is not None else None
        selected_graph_ids = chosen or [graph.id for graph in self.workspace.graphs]
        read_only = self.read_only_graphs.intersection(selected_graph_ids)
        if read_only:
            raise PermissionError(
                "cannot save graphs whose canonical arrays failed validation; "
                "retain the original package as the archival copy"
            )
        for graph_id in selected_graph_ids:
            graph = self.workspace.graph(graph_id)
            missing = [
                series.id
                for series in graph.series
                if series.id not in self.snapshots.get(graph_id, {})
            ]
            if missing and graph_id not in self.read_only_graphs:
                self.recompute_graph(graph_id)
        saved = save_package(
            destination,
            self.workspace,
            self.snapshots,
            graph_ids=chosen,
            previews=previews or self.previews,
            renderer_data=renderer_data or self.renderer_data,
        )
        if chosen is None:
            self.package_path = saved
            self.workspace.dirty = False
        return saved

    def graph_warnings(self, graph_id: str) -> list[str]:
        return self._graph_warnings.get(graph_id, []) + [
            warning
            for snapshot in self.snapshots.get(graph_id, {}).values()
            for warning in snapshot.warnings
        ]
