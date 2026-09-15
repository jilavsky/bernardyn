"""Regression coverage for the R0 editing-workflow reliability fixes."""

from dataclasses import replace

import numpy as np
import pytest

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import Dataset
from bernardyn.gui.main_window import MainWindow, SourceLoadWorker
from bernardyn.io.curve_export import export_displayed_csv, export_displayed_itx
from bernardyn.io.sources import ScatteringLocation, ScatteringRecord
from bernardyn.template.graph_templates import apply_template, template_document


def test_graph_view_intent_applies_before_and_after_import():
    controller = ApplicationController()
    graph = controller.workspace.graphs[0]
    controller.set_transform(graph.id, "kratky")
    first = Dataset(q=[1, 2, 3], intensity=[10, 20, 30])
    controller.add_dataset(first)
    assert controller.workspace.graph(graph.id).view_transform_id == "kratky"
    assert controller.workspace.graph(graph.id).series[0].transform_id == "kratky"
    np.testing.assert_allclose(
        controller.snapshots[graph.id][controller.workspace.graph(graph.id).series[0].id].y,
        [10, 80, 270],
    )


def test_failed_transform_commit_leaves_document_and_snapshot_unchanged():
    controller = ApplicationController()
    controller.add_dataset(Dataset(q=[1, 2], intensity=[3, 4]))
    graph = controller.workspace.graphs[0]
    snapshot = controller.snapshots[graph.id]
    dirty = controller.workspace.dirty
    broken = replace(
        graph,
        view_transform_id="dimensionless_kratky",
        series=tuple(replace(view, transform_id="dimensionless_kratky") for view in graph.series),
    )
    with pytest.raises(ValueError, match="requires"):
        controller.update_graph(broken, recompute=True)
    assert controller.workspace.graph(graph.id) is graph
    assert controller.snapshots[graph.id] is snapshot
    assert controller.workspace.dirty is dirty


def test_label_edit_refreshes_presentation_without_recomputing_arrays(tmp_path):
    controller = ApplicationController()
    controller.add_dataset(Dataset(q=[1, 2], intensity=[3, 4], label="old"))
    graph = controller.workspace.graphs[0]
    view = graph.series[0]
    old_snapshot = replace(
        controller.snapshots[graph.id][view.id], archived=True, transform_version="old"
    )
    controller.snapshots[graph.id][view.id] = old_snapshot
    controller.update_graph(
        graph.replace_series((replace(view, legend_label="new"),)), recompute=False
    )
    snapshot = controller.snapshots[graph.id][view.id]
    assert snapshot.label == "new"
    assert snapshot.archived and snapshot.transform_version == "old"
    np.testing.assert_array_equal(snapshot.x, old_snapshot.x)
    np.testing.assert_array_equal(snapshot.y, old_snapshot.y)
    csv_path = export_displayed_csv(tmp_path / "data.csv", controller.workspace.graph(graph.id), controller.snapshots[graph.id])
    itx_path = export_displayed_itx(tmp_path / "data.itx", controller.workspace.graph(graph.id), controller.snapshots[graph.id])
    assert csv_path.read_text(encoding="utf-8").splitlines()[1].startswith("new,")
    assert "Bernardyn series: new" in itx_path.read_text(encoding="utf-8")


def test_displayed_exports_skip_hidden_series_by_default(tmp_path):
    controller = ApplicationController()
    controller.add_dataset(Dataset(q=[1], intensity=[2], label="visible"))
    controller.add_dataset(Dataset(q=[1], intensity=[3], label="hidden"))
    graph = controller.workspace.graphs[0]
    graph = graph.replace_series(
        (graph.series[0], replace(graph.series[1], visible=False))
    )
    controller.update_graph(graph)
    contents = export_displayed_csv(tmp_path / "displayed.csv", graph, controller.snapshots[graph.id]).read_text()
    assert "visible" in contents
    assert "hidden" not in contents


def test_template_copies_complete_presentation_but_not_series_parameters():
    source = ApplicationController()
    source.add_dataset(Dataset(q=[1, 2], intensity=[3, 4]))
    graph = replace(
        source.workspace.graphs[0], box_axes=True, background_scope="plot"
    )
    source.update_graph(graph)
    target = ApplicationController()
    target.add_dataset(Dataset(q=[1, 2], intensity=[5, 6]))
    before = target.workspace.graphs[0]
    target_view = replace(before.series[0], transform_parameters={"I0": 10, "Rg": 2})
    applied = apply_template(
        before.replace_series((target_view,)), template_document(graph, "style")
    )
    assert applied.box_axes and applied.background_scope == "plot"
    assert applied.series[0].transform_parameters == {"I0": 10, "Rg": 2}


def test_late_load_completion_cannot_target_a_new_workspace(qapp, tmp_path):
    window = MainWindow()
    old_workspace = window.controller.workspace
    location = ScatteringLocation(path=tmp_path / "late.dat", adapter_id="text", display_name="late")
    worker = SourceLoadWorker(
        window.controller, location, old_workspace.graphs[0].id, "1/A", 0.05,
        old_workspace.id, window.controller.workspace_generation, 1, 0,
    )
    window._load_batches[1] = {
        "workspace_id": old_workspace.id,
        "workspace_generation": window.controller.workspace_generation,
        "graph_id": old_workspace.graphs[0].id,
        "workers": {worker},
        "finished": set(),
        "records": {},
    }
    window.controller.new_workspace()
    window._source_loaded(ScatteringRecord(q=[1], intensity=[2], label="late"), worker)
    window._worker_finished(worker)
    assert not window.controller.workspace.graphs[0].series
    window.controller.workspace.dirty = False
    window.close()


def test_dataset_removal_and_reorder_use_undo(qapp):
    window = MainWindow()
    window.controller.add_dataset(Dataset(q=[1], intensity=[2], label="one"))
    window.controller.add_dataset(Dataset(q=[1], intensity=[3], label="two"))
    window._refresh_dataset_list()
    first = window.dataset_list.takeItem(0)
    window.dataset_list.insertItem(1, first)
    window._dataset_list_reordered()
    reordered = [view.dataset_id for view in window.controller.workspace.graphs[0].series]
    window.dataset_list.setCurrentRow(0)
    window._remove_datasets()
    window.undo_stack.undo()
    assert [view.dataset_id for view in window.controller.workspace.graphs[0].series] == reordered
    window.undo_stack.undo()
    assert [view.dataset_id for view in window.controller.workspace.graphs[0].series] == list(reversed(reordered))
    window.controller.workspace.dirty = False
    window.close()
