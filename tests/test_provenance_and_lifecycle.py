"""Uncertainty provenance, parameter sources, and graph lifecycle details."""

from dataclasses import replace

import pytest

from bernardyn.core.controller import (
    ApplicationController,
    describe_uncertainty,
    metadata_parameter,
)
from bernardyn.core.models import Dataset
from bernardyn.io.container import load_package
from bernardyn.io.curve_export import export_displayed_csv, export_displayed_itx


def _load_text(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    controller = ApplicationController()
    (location,) = controller.sources.select_preferred_locations(controller.sources.discover_path(path))
    return controller.sources.load_location(location).to_dataset()


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("0.01 10\n0.02 5\n", "estimated"),
        ("0.01 10 1\n0.02 5 0.5\n", "measured"),
    ],
)
def test_text_files_record_whether_uncertainty_was_measured(tmp_path, text, kind):
    dataset = _load_text(tmp_path, "sample.dat", text)
    assert dataset.uncertainty_kind == kind


def test_uncertainty_kind_survives_a_package_round_trip(tmp_path):
    controller = ApplicationController()
    dataset = _load_text(tmp_path, "two.dat", "0.01 10\n0.02 5\n")
    controller.add_dataset(dataset)
    saved = controller.save(tmp_path / "workspace.bernardyn.h5")
    (restored,) = load_package(saved).workspace.datasets.values()
    assert restored.uncertainty_kind == "estimated"
    assert describe_uncertainty(restored) == "Uncertainty: estimated as 5% of I, not measured"


def test_visible_estimated_error_bars_are_reported_and_noted_in_itx(tmp_path):
    controller = ApplicationController()
    graph_id = controller.workspace.active_graph_id
    view = controller.add_dataset(_load_text(tmp_path, "two.dat", "0.01 10\n0.02 5\n"), graph_id=graph_id)
    assert not controller.estimated_uncertainty_notes(graph_id)  # error bars are off by default
    graph = controller.workspace.graph(graph_id)
    shown = replace(view, style=replace(view.style, show_error_bars=True))
    controller.update_graph(graph.replace_series((shown,)))
    notes = controller.estimated_uncertainty_notes(graph_id)
    assert notes == {view.id: "two error bars: estimated as 5% of I, not measured"}
    assert notes[view.id] in controller.graph_warnings(graph_id)
    itx = export_displayed_itx(
        tmp_path / "graph.itx",
        controller.workspace.graph(graph_id),
        controller.snapshots[graph_id],
        uncertainty_notes=notes,
    ).read_text(encoding="utf-8")
    assert 'X Note two_dy, "Bernardyn: two error bars: estimated as 5% of I, not measured"' in itx


def test_text_exports_leave_no_temporary_files(tmp_path):
    controller = ApplicationController()
    graph_id = controller.workspace.active_graph_id
    controller.add_dataset(Dataset(q=[0.01, 0.02], intensity=[2.0, 1.0], label="s"), graph_id=graph_id)
    graph = controller.workspace.graph(graph_id)
    export_displayed_csv(tmp_path / "a.csv", graph, controller.snapshots[graph_id])
    export_displayed_itx(tmp_path / "a.itx", graph, controller.snapshots[graph_id])
    assert sorted(path.name for path in tmp_path.iterdir()) == ["a.csv", "a.itx"]


def test_only_top_level_metadata_supplies_view_parameters():
    nested = Dataset(q=[0.01], intensity=[1.0], metadata={"unified_fit": {"level_2": {"Rg": 80.0}}})
    top = Dataset(q=[0.01], intensity=[1.0], metadata={"rg": 30.0, "I0": 5.0})
    assert metadata_parameter(nested, "Rg") is None
    assert metadata_parameter(top, "Rg") == 30.0


def test_parameters_taken_from_metadata_are_reported():
    controller = ApplicationController()
    graph_id = controller.workspace.active_graph_id
    controller.set_transform(graph_id, "dimensionless_kratky")
    dataset = Dataset(
        q=[0.01, 0.02], intensity=[2.0, 1.0], label="guinier sample",
        metadata={"I0": 2.0, "Rg": 10.0, "pyirena_simple_fit": {"model": "Guinier"}},
    )
    controller.add_dataset(dataset, graph_id=graph_id)
    assert controller.parameter_source_notes(graph_id) == [
        "guinier sample: I0 = 2, Rg = 10 taken from its pyIrena Simple Fits result"
    ]
    controller.add_dataset(
        replace(Dataset(q=[0.01], intensity=[1.0], label="explicit"), metadata={}),
        graph_id=graph_id,
        transform_parameters={"I0": 3.0, "Rg": 4.0},
    )
    assert len(controller.parameter_source_notes(graph_id)) == 1


def test_closing_a_graph_activates_its_neighbour_and_titles_stay_unique():
    controller = ApplicationController()
    first = controller.workspace.graphs[0]
    second = controller.new_graph()
    third = controller.new_graph()
    controller.workspace.active_graph_id = second.id
    controller.close_graph(second.id)
    assert controller.workspace.active_graph_id == third.id
    controller.workspace.active_graph_id = first.id
    controller.close_graph(third.id)
    assert controller.workspace.active_graph_id == first.id
    assert controller.new_graph().title == "Scattering plot 2"
    titles = [graph.title for graph in controller.workspace.graphs]
    assert len(titles) == len(set(titles))
