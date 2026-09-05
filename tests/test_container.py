import base64
import json
from dataclasses import replace

import h5py
import numpy as np
import pytest

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import Annotation, AnnotationKind, Dataset
from bernardyn.io.container import (
    FORMAT_MAGIC,
    PackageValidationError,
    dataset_checksum,
    import_graphs,
    load_package,
)
from bernardyn.io.igor import export_datasets_to_h5xp

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def make_controller():
    controller = ApplicationController()
    first = Dataset(q=[0.1, 0.2, 0.3], intensity=[100, 20, 5], uncertainty=[5, 2, 1], label="one")
    second = Dataset(q=[0.1, 0.2, 0.3], intensity=[80, 15, 4], label="two")
    controller.add_dataset(first)
    controller.add_dataset(second)
    graph = controller.workspace.graphs[0]
    graph = replace(
        graph,
        title="Archived plot",
        annotations=(Annotation(AnnotationKind.TEXT, (0.2, 20), text="sample"),),
    )
    controller.update_graph(graph)
    controller.recompute_graph(graph.id)
    return controller


def test_single_graph_package_round_trip_without_sources(tmp_path):
    controller = make_controller()
    graph = controller.workspace.graphs[0]
    source = tmp_path / "source.dat"
    source.write_text("this file is not used by the package")
    path = controller.save(tmp_path / "graph", graph_ids=[graph.id], previews={graph.id: PNG})
    source.unlink()
    loaded = load_package(path)
    assert path.name.endswith(".bernardyn.h5")
    assert loaded.workspace.graphs[0] == graph
    assert len(loaded.workspace.datasets) == 2
    assert all(snapshot.archived for snapshot in loaded.snapshots[graph.id].values())
    with h5py.File(path, "r") as handle:
        assert handle.attrs["bernardyn_format"] == FORMAT_MAGIC
        assert handle.attrs["container_kind"] == "graph"


def test_workspace_deduplicates_shared_canonical_data(tmp_path):
    controller = make_controller()
    second_graph = controller.new_graph(title="Other")
    controller.add_dataset(next(iter(controller.workspace.datasets.values())), graph_id=second_graph.id)
    path = controller.save(tmp_path / "workspace")
    with h5py.File(path, "r") as handle:
        assert handle.attrs["container_kind"] == "workspace"
        assert len(handle["graphs"]) == 2
        assert len(handle["datasets"]) == 2


def test_graph_export_does_not_mark_unsaved_workspace_clean(tmp_path):
    controller = make_controller()
    graph = controller.workspace.graphs[0]
    assert controller.workspace.dirty
    controller.save(tmp_path / "graph-only", graph_ids=[graph.id])
    assert controller.workspace.dirty
    controller.save(tmp_path / "whole-workspace")
    assert not controller.workspace.dirty


def test_snapshot_checksum_failure_recomputes_from_canonical(tmp_path):
    controller = make_controller()
    path = controller.save(tmp_path / "bad-snapshot")
    graph = controller.workspace.graphs[0]
    series = graph.series[0]
    with h5py.File(path, "r+") as handle:
        handle[f"graphs/{graph.id}/series/{series.id}/snapshot/y"][0] = -999
    loaded = load_package(path)
    assert series.id not in loaded.snapshots[graph.id]
    assert any("snapshot checksum failed" in warning for warning in loaded.warnings)
    restored = ApplicationController()
    restored.open_package(path)
    assert series.id in restored.snapshots[graph.id]
    assert restored.workspace.dirty
    assert any("recomputed" in warning for warning in restored.graph_warnings(graph.id))


def test_transform_version_change_keeps_archived_snapshot(tmp_path):
    controller = make_controller()
    path = controller.save(tmp_path / "old-transform")
    graph = controller.workspace.graphs[0]
    series = graph.series[0]
    with h5py.File(path, "r+") as handle:
        handle[f"graphs/{graph.id}/series/{series.id}"].attrs["transform_version"] = "0.1"
    restored = ApplicationController()
    restored.open_package(path)
    snapshot = restored.snapshots[graph.id][series.id]
    assert snapshot.archived
    assert snapshot.transform_version == "0.1"
    assert any("current version" in warning for warning in restored.graph_warnings(graph.id))
    restored.recompute_graph(graph.id)
    assert not restored.snapshots[graph.id][series.id].archived
    assert not any("current version" in warning for warning in restored.graph_warnings(graph.id))


def test_corrupt_canonical_data_uses_valid_snapshot_read_only(tmp_path):
    controller = make_controller()
    path = controller.save(tmp_path / "bad-canonical")
    graph = controller.workspace.graphs[0]
    dataset_id = graph.series[0].dataset_id
    with h5py.File(path, "r+") as handle:
        handle[f"datasets/{dataset_id}/data/I"][0] = -999
    loaded = load_package(path)
    assert graph.id in loaded.read_only_graphs
    assert loaded.snapshots[graph.id]
    restored = ApplicationController()
    restored.open_package(path)
    with pytest.raises(PermissionError, match="canonical arrays"):
        restored.save(tmp_path / "must-not-rebless")


def test_external_links_are_rejected(tmp_path):
    controller = make_controller()
    path = controller.save(tmp_path / "external")
    other = tmp_path / "other.h5"
    with h5py.File(other, "w") as handle:
        handle["x"] = [1]
    with h5py.File(path, "r+") as handle:
        handle["bad-link"] = h5py.ExternalLink(str(other), "/x")
    with pytest.raises(PackageValidationError, match="external"):
        load_package(path)


def test_future_schema_opens_previews_read_only(tmp_path):
    controller = make_controller()
    graph = controller.workspace.graphs[0]
    path = controller.save(tmp_path / "future", previews={graph.id: PNG})
    with h5py.File(path, "r+") as handle:
        handle.attrs["schema_version"] = 999
    loaded = load_package(path)
    assert loaded.future_schema
    assert not loaded.workspace.graphs
    assert loaded.previews[graph.id] == PNG


def test_unknown_transform_uses_embedded_preview_without_discarding_state(tmp_path):
    controller = make_controller()
    graph = controller.workspace.graphs[0]
    series = graph.series[0]
    path = controller.save(tmp_path / "unknown", previews={graph.id: PNG})
    with h5py.File(path, "r+") as handle:
        document = handle[f"graphs/{graph.id}/document"]
        value = json.loads(document[()].decode("utf-8"))
        value["series"][0]["transform_id"] = "future-transform"
        document[()] = json.dumps(value)
        handle[f"graphs/{graph.id}/series/{series.id}"].attrs[
            "transform_id"
        ] = "future-transform"
    restored = ApplicationController()
    restored.open_package(path)
    assert restored.workspace.graphs[0].series[0].transform_id == "future-transform"
    assert graph.id in restored.preview_only_graphs


def test_import_remaps_conflicting_dataset_uuid(tmp_path):
    source = make_controller()
    path = source.save(tmp_path / "source")
    loaded = load_package(path)
    target = make_controller()
    incoming_id = next(iter(loaded.workspace.datasets))
    conflict = replace(target.workspace.datasets[next(iter(target.workspace.datasets))], id=incoming_id, intensity=np.array([1, 1, 1]))
    target.workspace.datasets[incoming_id] = conflict
    graph_map, snapshots = import_graphs(target.workspace, loaded, [loaded.workspace.graphs[0].id])
    imported = target.workspace.graph(next(iter(graph_map.values())))
    original_graph = loaded.workspace.graphs[0]
    original_series = next(series for series in original_graph.series if series.dataset_id == incoming_id)
    imported_series = imported.series[original_graph.series.index(original_series)]
    assert dataset_checksum(target.workspace.datasets[imported_series.dataset_id]) == dataset_checksum(loaded.workspace.datasets[incoming_id])
    assert snapshots[imported.id]


def test_import_selected_graph_copies_only_its_referenced_dataset(tmp_path):
    source = make_controller()
    first_dataset = next(iter(source.workspace.datasets.values()))
    second_graph = source.new_graph(title="Selected")
    source.add_dataset(first_dataset, graph_id=second_graph.id)
    path = source.save(tmp_path / "multi")
    loaded = load_package(path)
    target = ApplicationController()
    target.workspace.graphs.clear()
    target.workspace.active_graph_id = None
    graph_map, _ = import_graphs(target.workspace, loaded, [second_graph.id])
    assert len(graph_map) == 1
    assert len(target.workspace.datasets) == 1
    assert target.workspace.graphs[0].title == "Selected"


def test_atomic_save_failure_preserves_previous_package(tmp_path, monkeypatch):
    controller = make_controller()
    path = controller.save(tmp_path / "atomic")
    original_title = load_package(path).workspace.graphs[0].title
    controller.update_graph(replace(controller.workspace.graphs[0], title="not committed"))

    def fail_replace(source, destination):
        raise OSError("simulated interruption")

    monkeypatch.setattr("bernardyn.io.container.os.replace", fail_replace)
    with pytest.raises(OSError, match="interruption"):
        controller.save(path)
    assert load_package(path).workspace.graphs[0].title == original_title


def test_igor_h5xp_export_is_separate_and_readable(tmp_path):
    controller = make_controller()
    path = export_datasets_to_h5xp(tmp_path / "curves", controller.workspace)
    assert path.suffix == ".h5xp"
    with h5py.File(path, "r") as handle:
        assert "Packed Data" in handle
        assert "bernardyn_format" not in handle.attrs
