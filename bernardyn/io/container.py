"""Versioned, portable Bernardyn HDF5 graph and workspace packages."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable, Mapping

import h5py
import numpy as np

from bernardyn import __version__
from bernardyn.core.models import (
    Dataset,
    DatasetKind,
    GraphDocument,
    PlotSeries,
    SeriesView,
    Workspace,
    json_value,
    new_id,
)

FORMAT_MAGIC = "BERNARDYN_GRAPH_PACKAGE"
SCHEMA_VERSION = 1
MIN_READER_VERSION = "1.0.0b1"
DEFAULT_SUFFIX = ".bernardyn.h5"
UTF8 = h5py.string_dtype(encoding="utf-8")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PackageError(RuntimeError):
    """Base class for graph-package failures."""


class PackageValidationError(PackageError):
    """Raised when a package violates the published schema."""


@dataclass
class LoadedPackage:
    workspace: Workspace
    snapshots: dict[str, dict[str, PlotSeries]] = field(default_factory=dict)
    previews: dict[str, bytes] = field(default_factory=dict)
    renderer_data: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    read_only_graphs: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    future_schema: bool = False
    path: Path | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def environment_manifest() -> dict[str, Any]:
    return {
        "bernardyn": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "h5py": h5py.__version__,
        "pyirena": _package_version("pyirena"),
        "pyqtgraph": _package_version("pyqtgraph"),
        "pyside6": _package_version("PySide6"),
        "pyopengl": _package_version("PyOpenGL"),
        "renderer_versions": {
            "plot2d": "1.0",
            "opengl_waterfall": "1.0",
            "opengl_surface": "1.0",
        },
    }


def array_checksum(array: np.ndarray) -> str:
    """Return a stable checksum including dtype and shape."""
    contiguous = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(contiguous.dtype.str.encode("ascii"))
    digest.update(json.dumps(contiguous.shape).encode("ascii"))
    digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def dataset_checksum(dataset: Dataset) -> str:
    digest = hashlib.sha256()
    for name, array in (
        ("Q", dataset.q),
        ("I", dataset.intensity),
        ("Idev", dataset.uncertainty),
        ("Qdev", dataset.dq),
    ):
        digest.update(name.encode("ascii"))
        digest.update(b"NONE" if array is None else array_checksum(array).encode("ascii"))
    return digest.hexdigest()


def ensure_package_suffix(path: str | Path) -> Path:
    result = Path(path).expanduser()
    if not result.name.lower().endswith(DEFAULT_SUFFIX):
        result = result.with_name(result.name + DEFAULT_SUFFIX)
    return result


def _write_json(parent: h5py.Group, name: str, value: Any) -> None:
    parent.create_dataset(name, data=json.dumps(json_value(value), ensure_ascii=False), dtype=UTF8)


def _read_json(parent: h5py.Group, name: str) -> Any:
    if name not in parent:
        raise PackageValidationError(f"missing JSON dataset {parent.name}/{name}")
    raw = parent[name][()]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise PackageValidationError(f"invalid JSON in {parent.name}/{name}") from exc


def _create_numeric(parent: h5py.Group, name: str, array: np.ndarray) -> h5py.Dataset:
    contiguous = np.ascontiguousarray(array)
    options: dict[str, Any] = {}
    if contiguous.nbytes >= 4096:
        options.update(compression="gzip", compression_opts=4, shuffle=True)
    result = parent.create_dataset(name, data=contiguous, **options)
    result.attrs["sha256"] = array_checksum(contiguous)
    return result


def _read_numeric(parent: h5py.Group, name: str, *, required: bool = True) -> tuple[np.ndarray | None, bool]:
    if name not in parent:
        if required:
            raise PackageValidationError(f"missing numeric dataset {parent.name}/{name}")
        return None, True
    dataset = parent[name]
    if not isinstance(dataset, h5py.Dataset) or dataset.dtype.kind not in "iufb":
        raise PackageValidationError(f"{dataset.name} must be a numeric dataset")
    value = np.asarray(dataset[()])
    expected = str(dataset.attrs.get("sha256", ""))
    valid = bool(expected) and expected == array_checksum(value)
    return value, valid


def _write_dataset(parent: h5py.Group, dataset: Dataset) -> None:
    group = parent.create_group(dataset.id)
    group.attrs["dataset_sha256"] = dataset_checksum(dataset)
    data_group = group.create_group("data")
    _create_numeric(data_group, "Q", dataset.q)
    _create_numeric(data_group, "I", dataset.intensity)
    if dataset.uncertainty is not None:
        _create_numeric(data_group, "Idev", dataset.uncertainty)
    if dataset.dq is not None:
        _create_numeric(data_group, "Qdev", dataset.dq)
    _write_json(group, "metadata", dataset.metadata_dict())


def _write_snapshot(parent: h5py.Group, snapshot: PlotSeries) -> None:
    group = parent.create_group(snapshot.series_id)
    group.attrs["dataset_id"] = snapshot.dataset_id
    group.attrs["transform_id"] = snapshot.transform_id
    group.attrs["transform_version"] = snapshot.transform_version
    data_group = group.create_group("snapshot")
    _create_numeric(data_group, "x", snapshot.x)
    _create_numeric(data_group, "y", snapshot.y)
    _create_numeric(data_group, "source_indices", snapshot.source_indices)
    if snapshot.dx is not None:
        _create_numeric(data_group, "dx", snapshot.dx)
    if snapshot.dy is not None:
        _create_numeric(data_group, "dy", snapshot.dy)
    _write_json(
        group,
        "metadata",
        {
            "label": snapshot.label,
            "x_label": snapshot.x_label,
            "y_label": snapshot.y_label,
            "x_unit": snapshot.x_unit,
            "y_unit": snapshot.y_unit,
            "warnings": snapshot.warnings,
            "archived": True,
        },
    )


def _check_no_external_links(handle: h5py.File) -> None:
    external: list[str] = []

    def walk(group: h5py.Group) -> None:
        for name in group.keys():
            link = group.get(name, getlink=True)
            full_name = f"{group.name.rstrip('/')}/{name}"
            if isinstance(link, h5py.ExternalLink):
                external.append(full_name)
                continue
            if isinstance(link, h5py.SoftLink):
                continue
            value = group.get(name, getclass=False)
            if isinstance(value, h5py.Group):
                walk(value)

    walk(handle)
    if external:
        raise PackageValidationError(
            "external HDF5 links are not permitted: " + ", ".join(external)
        )


def _validate_structure(handle: h5py.File) -> None:
    magic = handle.attrs.get("bernardyn_format", "")
    if isinstance(magic, bytes):
        magic = magic.decode("utf-8", errors="replace")
    if magic != FORMAT_MAGIC:
        raise PackageValidationError("not a Bernardyn graph package")
    if handle.attrs.get("container_kind") not in ("graph", "workspace"):
        raise PackageValidationError("container_kind must be 'graph' or 'workspace'")
    for group in ("manifest", "environment", "datasets", "graphs"):
        if group not in handle or not isinstance(handle[group], h5py.Group):
            raise PackageValidationError(f"missing required group /{group}")
    _check_no_external_links(handle)


def save_package(
    path: str | Path,
    workspace: Workspace,
    snapshots: Mapping[str, Mapping[str, PlotSeries]],
    *,
    graph_ids: Iterable[str] | None = None,
    previews: Mapping[str, bytes] | None = None,
    renderer_data: Mapping[str, Mapping[str, np.ndarray]] | None = None,
) -> Path:
    """Atomically save one graph or a graph collection with embedded data."""
    workspace.validate()
    destination = ensure_package_suffix(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    chosen_ids = list(graph_ids) if graph_ids is not None else [graph.id for graph in workspace.graphs]
    if not chosen_ids:
        raise ValueError("at least one graph must be saved")
    chosen_graphs = [workspace.graph(graph_id) for graph_id in chosen_ids]
    referenced_ids = {
        series.dataset_id for graph in chosen_graphs for series in graph.series
    }
    for graph in chosen_graphs:
        missing = [series.id for series in graph.series if series.id not in snapshots.get(graph.id, {})]
        if missing:
            raise ValueError(f"graph {graph.title!r} has unresolved series: {', '.join(missing)}")

    temp_file = tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
    )
    temp_path = Path(temp_file.name)
    temp_file.close()
    try:
        created_utc = _utc_now()
        if destination.exists():
            try:
                with h5py.File(destination, "r") as previous:
                    if previous.attrs.get("bernardyn_format") == FORMAT_MAGIC:
                        created_utc = str(previous.attrs.get("created_utc", created_utc))
            except OSError:
                pass
        with h5py.File(temp_path, "w", libver="latest", track_order=True) as handle:
            now = _utc_now()
            handle.attrs["bernardyn_format"] = FORMAT_MAGIC
            handle.attrs["schema_version"] = np.int32(SCHEMA_VERSION)
            handle.attrs["container_kind"] = "graph" if len(chosen_graphs) == 1 else "workspace"
            handle.attrs["content_uuid"] = workspace.id
            handle.attrs["created_utc"] = created_utc
            handle.attrs["updated_utc"] = now
            handle.attrs["created_with"] = __version__
            handle.attrs["minimum_reader_version"] = MIN_READER_VERSION

            manifest = handle.create_group("manifest")
            _write_json(
                manifest,
                "document",
                {
                    "workspace_id": workspace.id,
                    "title": workspace.title,
                    "description": workspace.description,
                    "graph_ids": chosen_ids,
                    "dataset_ids": sorted(referenced_ids),
                    "active_graph_id": (
                        workspace.active_graph_id
                        if workspace.active_graph_id in chosen_ids
                        else chosen_ids[0]
                    ),
                    "layout_state": workspace.layout_state if len(chosen_graphs) > 1 else None,
                },
            )
            environment = handle.create_group("environment")
            _write_json(environment, "document", environment_manifest())
            data_root = handle.create_group("datasets")
            for dataset_id in sorted(referenced_ids):
                _write_dataset(data_root, workspace.datasets[dataset_id])

            graphs_root = handle.create_group("graphs")
            for graph in chosen_graphs:
                graph_group = graphs_root.create_group(graph.id)
                graph_group.attrs["renderer_id"] = graph.renderer_id
                graph_group.attrs["renderer_version"] = str(
                    graph.renderer_config.get("renderer_version", "1.0")
                )
                _write_json(graph_group, "document", graph.to_dict())
                series_group = graph_group.create_group("series")
                for series in graph.series:
                    _write_snapshot(series_group, snapshots[graph.id][series.id])
                preview = (previews or {}).get(graph.id)
                if preview:
                    if not preview.startswith(PNG_SIGNATURE):
                        raise ValueError(f"preview for graph {graph.id} is not a PNG image")
                    preview_ds = graph_group.create_dataset(
                        "preview", data=np.frombuffer(preview, dtype=np.uint8), compression="gzip"
                    )
                    preview_ds.attrs["mime_type"] = "image/png"
                    preview_ds.attrs["sha256"] = hashlib.sha256(preview).hexdigest()
                graph_renderer_data = (renderer_data or {}).get(graph.id, {})
                if graph_renderer_data:
                    renderer_group = graph_group.create_group("renderer-data")
                    for name, value in graph_renderer_data.items():
                        if "/" in name or not name:
                            raise ValueError(f"invalid renderer-data name {name!r}")
                        _create_numeric(renderer_group, name, np.asarray(value))
            handle.flush()
        with temp_path.open("rb") as stream:
            os.fsync(stream.fileno())
        validated = load_package(temp_path)
        if validated.warnings:
            raise PackageValidationError(
                "new package failed validation: " + "; ".join(validated.warnings)
            )
        os.replace(temp_path, destination)
        try:
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # Directory fsync is unavailable on some supported platforms.
            pass
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return destination


def _read_dataset(group: h5py.Group, warnings: list[str]) -> tuple[Dataset, bool]:
    metadata = _read_json(group, "metadata")
    data_group = group.get("data")
    if not isinstance(data_group, h5py.Group):
        raise PackageValidationError(f"missing data group in {group.name}")
    q, q_ok = _read_numeric(data_group, "Q")
    intensity, i_ok = _read_numeric(data_group, "I")
    uncertainty, e_ok = _read_numeric(data_group, "Idev", required=False)
    dq, dq_ok = _read_numeric(data_group, "Qdev", required=False)
    valid = q_ok and i_ok and e_ok and dq_ok
    expected = str(group.attrs.get("dataset_sha256", ""))
    dataset = Dataset(
        id=str(metadata.get("id", group.name.rsplit("/", 1)[-1])),
        kind=DatasetKind(metadata.get("kind", DatasetKind.CURVE_1D.value)),
        q=q,
        intensity=intensity,
        uncertainty=uncertainty,
        dq=dq,
        label=str(metadata.get("label", "Dataset")),
        q_unit=str(metadata.get("q_unit", "1/angstrom")),
        intensity_unit=str(metadata.get("intensity_unit", "1/cm")),
        metadata=metadata.get("metadata", {}),
        provenance=metadata.get("provenance", {}),
        source_fingerprint=metadata.get("source_fingerprint"),
    )
    valid &= bool(expected) and expected == dataset_checksum(dataset)
    if not valid:
        warnings.append(f"canonical dataset checksum failed for {dataset.label}")
    return dataset, valid


def _read_snapshot(group: h5py.Group, warnings: list[str]) -> PlotSeries | None:
    data_group = group.get("snapshot")
    if not isinstance(data_group, h5py.Group):
        warnings.append(f"missing snapshot group {group.name}")
        return None
    x, x_ok = _read_numeric(data_group, "x")
    y, y_ok = _read_numeric(data_group, "y")
    indices, indices_ok = _read_numeric(data_group, "source_indices")
    dx, dx_ok = _read_numeric(data_group, "dx", required=False)
    dy, dy_ok = _read_numeric(data_group, "dy", required=False)
    if not all((x_ok, y_ok, indices_ok, dx_ok, dy_ok)):
        warnings.append(f"snapshot checksum failed for {group.name}")
        return None
    metadata = _read_json(group, "metadata")
    return PlotSeries(
        series_id=group.name.rsplit("/", 1)[-1],
        dataset_id=str(group.attrs["dataset_id"]),
        x=x,
        y=y,
        dx=dx,
        dy=dy,
        source_indices=np.asarray(indices, dtype=np.int64),
        label=str(metadata.get("label", "")),
        x_label=str(metadata.get("x_label", "")),
        y_label=str(metadata.get("y_label", "")),
        x_unit=str(metadata.get("x_unit", "")),
        y_unit=str(metadata.get("y_unit", "")),
        transform_id=str(group.attrs.get("transform_id", "raw")),
        transform_version=str(group.attrs.get("transform_version", "1.0")),
        warnings=tuple(metadata.get("warnings", [])),
        archived=True,
    )


def _read_previews(handle: h5py.File) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    graphs = handle.get("graphs")
    if not isinstance(graphs, h5py.Group):
        return result
    for graph_id, graph_group in graphs.items():
        if isinstance(graph_group, h5py.Group) and "preview" in graph_group:
            value = np.asarray(graph_group["preview"][()], dtype=np.uint8).tobytes()
            expected = str(graph_group["preview"].attrs.get("sha256", ""))
            if value.startswith(PNG_SIGNATURE) and (
                not expected or hashlib.sha256(value).hexdigest() == expected
            ):
                result[graph_id] = value
    return result


def load_package(path: str | Path) -> LoadedPackage:
    source = Path(path).expanduser().resolve()
    warnings: list[str] = []
    with h5py.File(source, "r") as handle:
        _validate_structure(handle)
        schema_version = int(handle.attrs.get("schema_version", 0))
        manifest = _read_json(handle["manifest"], "document")
        previews = _read_previews(handle)
        if schema_version > SCHEMA_VERSION:
            workspace = Workspace(
                id=str(manifest.get("workspace_id", new_id())),
                title=str(manifest.get("title", source.stem)),
                description=str(manifest.get("description", "")),
            )
            return LoadedPackage(
                workspace=workspace,
                previews=previews,
                warnings=[
                    f"package schema {schema_version} is newer than supported schema {SCHEMA_VERSION}"
                ],
                future_schema=True,
                path=source,
            )
        if schema_version < 1:
            raise PackageValidationError(f"unsupported package schema {schema_version}")

        datasets: dict[str, Dataset] = {}
        valid_datasets: dict[str, bool] = {}
        for dataset_id in manifest.get("dataset_ids", []):
            if dataset_id not in handle["datasets"]:
                raise PackageValidationError(f"manifest references missing dataset {dataset_id}")
            dataset, valid = _read_dataset(handle["datasets"][dataset_id], warnings)
            datasets[dataset.id] = dataset
            valid_datasets[dataset.id] = valid

        graphs: list[GraphDocument] = []
        snapshots: dict[str, dict[str, PlotSeries]] = {}
        renderer_data: dict[str, dict[str, np.ndarray]] = {}
        read_only_graphs: set[str] = set()
        for graph_id in manifest.get("graph_ids", []):
            if graph_id not in handle["graphs"]:
                raise PackageValidationError(f"manifest references missing graph {graph_id}")
            group = handle["graphs"][graph_id]
            graph = GraphDocument.from_dict(_read_json(group, "document"))
            graphs.append(graph)
            graph_snapshots: dict[str, PlotSeries] = {}
            series_root = group.get("series")
            if not isinstance(series_root, h5py.Group):
                raise PackageValidationError(f"missing series group for graph {graph_id}")
            for series in graph.series:
                snapshot_group = series_root.get(series.id)
                snapshot = (
                    _read_snapshot(snapshot_group, warnings)
                    if isinstance(snapshot_group, h5py.Group)
                    else None
                )
                if snapshot is not None:
                    if snapshot.dataset_id != series.dataset_id:
                        warnings.append(f"snapshot dataset reference failed for {series.id}")
                        snapshot = None
                    elif snapshot.transform_id != series.transform_id:
                        warnings.append(f"snapshot transform reference failed for {series.id}")
                        snapshot = None
                if snapshot is not None:
                    graph_snapshots[series.id] = snapshot
                if not valid_datasets.get(series.dataset_id, False) and snapshot is not None:
                    read_only_graphs.add(graph.id)
                if not valid_datasets.get(series.dataset_id, False) and snapshot is None:
                    raise PackageValidationError(
                        f"graph {graph.title!r} has neither valid canonical data nor a valid snapshot"
                    )
            snapshots[graph.id] = graph_snapshots
            renderer_group = group.get("renderer-data")
            if isinstance(renderer_group, h5py.Group):
                renderer_data[graph.id] = {}
                for name, value in renderer_group.items():
                    if not isinstance(value, h5py.Dataset):
                        raise PackageValidationError(
                            f"renderer data {value.name} must be numeric"
                        )
                    array, valid = _read_numeric(renderer_group, name)
                    if not valid:
                        warnings.append(f"renderer-data checksum failed for {value.name}")
                    elif array is not None:
                        renderer_data[graph.id][name] = array

        workspace = Workspace(
            id=str(manifest.get("workspace_id", handle.attrs.get("content_uuid", new_id()))),
            title=str(manifest.get("title", source.stem)),
            description=str(manifest.get("description", "")),
            datasets=datasets,
            graphs=graphs,
            active_graph_id=manifest.get("active_graph_id"),
            layout_state=manifest.get("layout_state"),
            dirty=False,
        )
    return LoadedPackage(
        workspace=workspace,
        snapshots=snapshots,
        previews=previews,
        renderer_data=renderer_data,
        read_only_graphs=read_only_graphs,
        warnings=warnings,
        path=source,
    )


def import_graphs(
    target: Workspace,
    loaded: LoadedPackage,
    graph_ids: Iterable[str],
) -> tuple[dict[str, str], dict[str, dict[str, PlotSeries]]]:
    """Import graphs and referenced datasets, remapping conflicting UUIDs."""
    dataset_map: dict[str, str] = {}
    graph_map: dict[str, str] = {}
    imported_snapshots: dict[str, dict[str, PlotSeries]] = {}
    chosen = [loaded.workspace.graph(graph_id) for graph_id in graph_ids]
    referenced = {series.dataset_id for graph in chosen for series in graph.series}
    for dataset_id in referenced:
        incoming = loaded.workspace.datasets[dataset_id]
        if dataset_id not in target.datasets:
            target.add_dataset(incoming)
            dataset_map[dataset_id] = dataset_id
        elif dataset_checksum(target.datasets[dataset_id]) == dataset_checksum(incoming):
            dataset_map[dataset_id] = dataset_id
        else:
            replacement_id = new_id()
            target.add_dataset(replace(incoming, id=replacement_id))
            dataset_map[dataset_id] = replacement_id

    existing_graph_ids = {graph.id for graph in target.graphs}
    for graph in chosen:
        replacement_graph_id = graph.id if graph.id not in existing_graph_ids else new_id()
        graph_map[graph.id] = replacement_graph_id
        new_series: list[SeriesView] = []
        snapshot_map: dict[str, PlotSeries] = {}
        for series in graph.series:
            replacement_series_id = new_id()
            new_series.append(
                replace(
                    series,
                    id=replacement_series_id,
                    dataset_id=dataset_map[series.dataset_id],
                )
            )
            old_snapshot = loaded.snapshots.get(graph.id, {}).get(series.id)
            if old_snapshot is not None:
                snapshot_map[replacement_series_id] = replace(
                    old_snapshot,
                    series_id=replacement_series_id,
                    dataset_id=dataset_map[series.dataset_id],
                )
        target.add_graph(
            replace(graph, id=replacement_graph_id, series=tuple(new_series))
        )
        imported_snapshots[replacement_graph_id] = snapshot_map
        existing_graph_ids.add(replacement_graph_id)
    return graph_map, imported_snapshots
