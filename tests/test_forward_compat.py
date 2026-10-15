"""Packages and templates written by other Bernardyn versions stay readable."""

import json
from pathlib import Path
from shutil import copy2

import h5py
import pytest

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import AnnotationKind, GraphDocument, SeriesView, new_id
from bernardyn.io.container import (
    PackageValidationError,
    _read_json,
    _write_json,
    dataset_checksum,
    load_package,
)
from bernardyn.template.graph_templates import apply_template, load_template, save_template

# Written by the released 0.0.1b7 code (git e404ca6), never regenerated.
FROZEN_B7 = Path(__file__).parent / "fixtures" / "workspace-0.0.1b7.h5"


def _rewrite_json(path: Path, group_path: str, edit) -> None:
    with h5py.File(path, "r+") as handle:
        group = handle[group_path]
        document = _read_json(group, "document" if "document" in group else "metadata")
        name = "document" if "document" in group else "metadata"
        edit(document)
        del group[name]
        _write_json(group, name, document)


def test_frozen_b7_workspace_opens_unchanged():
    controller = ApplicationController()
    loaded = controller.open_package(FROZEN_B7)
    assert loaded.warnings == []
    assert not controller.read_only_graphs
    titles = [graph.title for graph in controller.workspace.graphs]
    assert titles == ["Frozen b7 graph", "Residuals"]
    kratky, residuals = controller.workspace.graphs
    assert kratky.view_transform_id == "kratky"
    assert kratky.box_axes
    assert [item.kind for item in kratky.annotations] == [AnnotationKind.TEXT, AnnotationKind.POWER_LAW]
    assert kratky.series[0].legend_label == "A renamed"
    assert controller.snapshots[kratky.id][kratky.series[0].id].label == "A renamed"
    assert controller.snapshots[residuals.id][residuals.series[0].id].y.min() < 0
    assert not controller.workspace.dirty


def test_frozen_b7_workspace_resaves_without_changing_its_documents(tmp_path):
    before = load_package(FROZEN_B7)
    controller = ApplicationController()
    controller.open_package(FROZEN_B7)
    after = load_package(controller.save(tmp_path / "resaved.bernardyn.h5"))
    assert [graph.to_dict() for graph in after.workspace.graphs] == [
        graph.to_dict() for graph in before.workspace.graphs
    ]
    assert {key: dataset_checksum(value) for key, value in after.workspace.datasets.items()} == {
        key: dataset_checksum(value) for key, value in before.workspace.datasets.items()
    }


def test_fields_from_a_newer_writer_are_kept_through_open_and_save(tmp_path):
    source = tmp_path / "future.h5"
    copy2(FROZEN_B7, source)
    original = load_package(FROZEN_B7)
    graph_id = original.workspace.graphs[0].id
    dataset_id = original.workspace.graphs[0].series[0].dataset_id

    def add_future_fields(document):
        document["future_graph_option"] = {"mode": "new"}
        document["x_axis"]["future_tick_style"] = "inward"
        document["legend"]["future_shadow"] = True
        document["typography"]["future_weight"] = 600
        document["series"][0]["future_series_flag"] = 3
        document["series"][0]["style"]["future_glow"] = 0.5
        document["annotations"][0]["future_halo"] = [1, 2]

    _rewrite_json(source, f"/graphs/{graph_id}", add_future_fields)
    _rewrite_json(source, f"/datasets/{dataset_id}", lambda document: document.update(future_tag="x"))

    controller = ApplicationController()
    loaded = controller.open_package(source)
    assert loaded.warnings == []
    resaved = controller.save(tmp_path / "resaved.bernardyn.h5")

    with h5py.File(resaved, "r") as handle:
        graph = _read_json(handle[f"/graphs/{graph_id}"], "document")
        dataset = _read_json(handle[f"/datasets/{dataset_id}"], "metadata")
    assert graph["future_graph_option"] == {"mode": "new"}
    assert graph["x_axis"]["future_tick_style"] == "inward"
    assert graph["legend"]["future_shadow"] is True
    assert graph["typography"]["future_weight"] == 600
    assert graph["series"][0]["future_series_flag"] == 3
    assert graph["series"][0]["style"]["future_glow"] == 0.5
    assert graph["annotations"][0]["future_halo"] == [1, 2]
    assert dataset["future_tag"] == "x"
    assert "extras" not in json.dumps(graph) and "extras" not in dataset


def test_documents_without_newer_fields_do_not_gain_keys():
    graph = GraphDocument(series=(SeriesView(dataset_id=new_id()),))
    document = graph.to_dict()
    assert "extras" not in json.dumps(document)
    assert GraphDocument.from_dict(document) == graph


def test_malformed_graph_document_is_a_validation_error(tmp_path):
    source = tmp_path / "broken.h5"
    copy2(FROZEN_B7, source)
    graph_id = load_package(FROZEN_B7).workspace.graphs[0].id
    _rewrite_json(source, f"/graphs/{graph_id}", lambda document: document.pop("id"))
    with pytest.raises(PackageValidationError, match="invalid graph document"):
        load_package(source)


def test_template_with_newer_style_fields_still_applies(tmp_path):
    controller = ApplicationController()
    controller.open_package(FROZEN_B7)
    graph = controller.workspace.graphs[0]
    path = save_template(tmp_path / "styled", graph, "styled")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert "extras" not in json.dumps(document)
    document["series_styles"][0]["future_glow"] = 0.5
    path.write_text(json.dumps(document), encoding="utf-8")
    applied = apply_template(graph, load_template(path))
    assert applied.series[0].style.extras == {"future_glow": 0.5}
    assert applied.series[0].style.color == graph.series[0].style.color
