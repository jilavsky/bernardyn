"""Template management, graph duplication, catalog clean-up, exports, doctor."""

import re
from pathlib import Path

import pytest

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import Annotation, Dataset
from bernardyn.diagnostics import MINIMUM_PYIRENA, _pyside6_supported, _version_key
from bernardyn.io.curve_export import export_displayed_csv
from bernardyn.template.graph_templates import (
    load_template,
    rename_template,
    save_template,
    template_file_name,
    template_summary,
)


def _controller_with_data():
    controller = ApplicationController()
    graph_id = controller.workspace.active_graph_id
    controller.add_dataset(Dataset(q=[0.01, 0.02], intensity=[2.0, 1.0], label="a"), graph_id=graph_id)
    controller.add_dataset(Dataset(q=[0.01, 0.02], intensity=[4.0, 3.0], label="b"), graph_id=graph_id)
    return controller, graph_id


def test_template_rename_moves_the_file_and_keeps_its_content(tmp_path):
    controller, graph_id = _controller_with_data()
    controller.set_transform(graph_id, "kratky")
    path = save_template(tmp_path / template_file_name("Old name"), controller.workspace.graph(graph_id), "Old name")
    renamed = rename_template(path, "Paper figure")
    assert renamed.name == "Paper figure.bernardyn-template.json"
    assert not path.exists()
    document = load_template(renamed)
    assert document["name"] == "Paper figure"
    assert template_summary(document) == "Kratky view · 1950×1350 px at 300 dpi · 2 series styles"


def test_template_rename_refuses_to_replace_another_template(tmp_path):
    controller, graph_id = _controller_with_data()
    graph = controller.workspace.graph(graph_id)
    first = save_template(tmp_path / template_file_name("first"), graph, "first")
    save_template(tmp_path / template_file_name("second"), graph, "second")
    with pytest.raises(FileExistsError):
        rename_template(first, "second")
    assert first.exists()


def test_duplicate_graph_is_independent_and_shares_catalog_data():
    controller, graph_id = _controller_with_data()
    graph = controller.workspace.graph(graph_id)
    controller.update_graph(
        graph.__class__(**{**graph.__dict__, "annotations": (Annotation(kind="text", position=(0.01, 1.0)),)})
    )
    original = controller.workspace.graph(graph_id)
    copy = controller.duplicate_graph(graph_id)
    assert copy.title == f"{original.title} (copy)"
    assert [view.dataset_id for view in copy.series] == [view.dataset_id for view in original.series]
    assert not {view.id for view in copy.series} & {view.id for view in original.series}
    assert copy.annotations[0].id != original.annotations[0].id
    assert set(controller.snapshots[copy.id]) == {view.id for view in copy.series}
    assert len(controller.workspace.datasets) == 2
    controller.remove_series(copy.id, copy.series[0].id)
    assert len(controller.workspace.graph(graph_id).series) == 2


def test_remove_unused_datasets_keeps_plotted_data(tmp_path):
    controller, graph_id = _controller_with_data()
    graph = controller.workspace.graph(graph_id)
    controller.remove_series(graph_id, graph.series[0].id)
    assert [controller.workspace.datasets[item].label for item in controller.unused_dataset_ids()] == ["a"]
    assert controller.remove_unused_datasets() == 1
    assert [dataset.label for dataset in controller.workspace.datasets.values()] == ["b"]
    assert controller.remove_unused_datasets() == 0
    controller.save(tmp_path / "clean.bernardyn.h5")


def test_csv_export_describes_graph_axes_and_series(tmp_path):
    controller, graph_id = _controller_with_data()
    controller.set_transform(graph_id, "porod")
    path = export_displayed_csv(
        tmp_path / "porod.csv",
        controller.workspace.graph(graph_id),
        controller.snapshots[graph_id],
        uncertainty_notes={controller.workspace.graph(graph_id).series[0].id: "a error bars: estimated"},
    )
    lines = path.read_text(encoding="utf-8").splitlines()
    comments = [line for line in lines if line.startswith("#")]
    assert comments[0] == "# format = bernardyn-displayed-data-csv v1"
    assert "# x_axis = q⁴ [Å⁻⁴]" in comments
    assert "# series a = view porod 1.0; x q⁴ [Å⁻⁴]; y Intensity·q⁴ [cm⁻¹·Å⁻⁴]; a error bars: estimated" in comments
    assert lines[len(comments)] == "series,x,y,dx,dy,source_index"


def test_doctor_floor_matches_pyproject():
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'"pyirena\[qtplot\]>=([^,"]+)', pyproject)
    assert match and match.group(1) == MINIMUM_PYIRENA


def test_doctor_version_ordering_and_pyside_exclusions():
    assert _version_key("1.1.1") < _version_key("1.2.0b2") < _version_key("1.2.0") < _version_key("1.10.0")
    assert _version_key("1.2.0rc1") < _version_key("1.2.0")
    assert _pyside6_supported("6.9.3") and _pyside6_supported("6.11.1")
    assert not _pyside6_supported("6.9.1") and not _pyside6_supported("6.10.2")
