"""Regression tests for the 1D code review of November 2, 2026.

Each test names its finding (docs/code-review-1d-2026-11-02.md) and checks
the scientific or workflow invariant rather than the implementation.
"""

from dataclasses import replace

import h5py
import numpy as np
import pytest

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import (
    Annotation,
    AnnotationKind,
    AxisSpec,
    CurveRole,
    Dataset,
    GenericCurve,
    GraphDocument,
    SeriesView,
)
from bernardyn.core.transforms import builtin_transforms, resolve_series
from bernardyn.io.sources import ScatteringRecord, builtin_sources
from bernardyn.state import UserState

# ------------------------------------------------------------------ F03 units


@pytest.mark.parametrize(
    ("unit", "factor"),
    [("1/angstrom", 1.0), ("Å⁻¹", 1.0), ("1/nm", 10.0), ("nm^-1", 10.0), ("1/m", 1e10)],
)
def test_f03_equivalent_q_units_resolve_identically(unit, factor):
    q_angstrom = np.array([0.01, 0.02])
    dq_angstrom = np.array([0.001, 0.002])
    dataset = ScatteringRecord(
        q=q_angstrom * factor, intensity=np.array([2.0, 1.0]), dq=dq_angstrom * factor, q_unit=unit
    ).to_dataset()
    np.testing.assert_allclose(dataset.q, q_angstrom)
    np.testing.assert_allclose(dataset.dq, dq_angstrom)
    assert dataset.q_unit == "1/angstrom"


def test_f03_unknown_explicit_q_unit_is_refused():
    record = ScatteringRecord(q=np.array([1.0, 2.0]), intensity=np.array([2.0, 1.0]), q_unit="furlong")
    with pytest.raises(ValueError, match="not a recognised inverse length"):
        record.to_dataset()


def test_f03_hdf5_inverse_metres_are_converted(tmp_path):
    path = tmp_path / "metres.h5"
    with h5py.File(path, "w") as handle:
        entry = handle.create_group("entry")
        entry.attrs["NX_class"] = "NXentry"
        entry.attrs["default"] = "sasdata"
        data = entry.create_group("sasdata")
        data.attrs["NX_class"] = "NXdata"
        data.attrs["canSAS_class"] = "SASdata"
        data.attrs["signal"] = "I"
        data.attrs["I_axes"] = "Q"
        data.create_dataset("Q", data=[1e8, 2e8]).attrs["units"] = "1/m"
        data.create_dataset("I", data=[3.0, 2.0]).attrs["units"] = "1/cm"
    sources = builtin_sources(discover_plugins=False)
    location = sources.preferred_locations(path)[0]
    dataset = sources.load_location(location).to_dataset()
    np.testing.assert_allclose(dataset.q, [0.01, 0.02])


# ---------------------------------------------------------- F04 dimensionless


def test_f04_dimensionless_kratky_overlays_curves_with_different_rg():
    transform = builtin_transforms(discover_plugins=False).get("dimensionless_kratky")
    curves = []
    for rg in (10.0, 40.0):
        q = np.linspace(0.2, 3.0, 15) / rg  # identical qRg grid
        dataset = Dataset(
            q=q, intensity=5.0 * np.exp(-((q * rg) ** 2) / 3), dq=np.full(q.shape, 0.01 / rg)
        )
        view = SeriesView(
            dataset_id=dataset.id,
            transform_id=transform.id,
            transform_parameters={"I0": 5.0, "Rg": rg},
        )
        curves.append(transform.apply(dataset, view))
    first, second = curves
    np.testing.assert_allclose(first.x, second.x)
    np.testing.assert_allclose(first.y, second.y)
    np.testing.assert_allclose(first.dx, second.dx)
    assert first.x_unit == "dimensionless"


def test_f04_archived_version_1_snapshot_is_not_silently_recomputed(tmp_path):
    controller = ApplicationController()
    graph = controller.workspace.graphs[0]
    controller.add_datasets(
        (Dataset(q=[0.01, 0.02], intensity=[2.0, 1.0]),), graph_id=graph.id
    )
    controller.set_transform(graph.id, "dimensionless_kratky", {"I0": 2.0, "Rg": 10.0})
    snapshots = controller.snapshots[graph.id]
    controller.snapshots[graph.id] = {
        key: replace(value, transform_version="1.0") for key, value in snapshots.items()
    }
    path = controller.save(tmp_path / "old.bernardyn.h5")
    reopened = ApplicationController()
    reopened.open_package(path)
    graph_id = reopened.workspace.graphs[0].id
    assert all(s.transform_version == "1.0" for s in reopened.snapshots[graph_id].values())
    assert any("current version is 2.0" in w for w in reopened.graph_warnings(graph_id))


# ------------------------------------------------------ F05 missing errors


def test_f05_missing_uncertainty_keeps_the_measurement():
    dataset = Dataset(
        q=[1.0, 2.0, 3.0],
        intensity=[2.0, 3.0, 4.0],
        uncertainty=[0.2, np.nan, 0.4],
        dq=[np.nan, 0.1, 0.1],
    )
    view = SeriesView(dataset_id=dataset.id)
    result = resolve_series(dataset, view, builtin_transforms(discover_plugins=False))
    np.testing.assert_array_equal(result.source_indices, [0, 1, 2])
    assert np.isnan(result.dy[1]) and np.isnan(result.dx[0])
    assert any("no finite dY" in warning for warning in result.warnings)
    assert not any("non-finite and were masked" in warning for warning in result.warnings)


# ---------------------------------------------- F06 generic log after offset


def test_f06_generic_log_mask_uses_displayed_values():
    curve = GenericCurve(x=[1.0, 2.0, 3.0], y=[-2.0, 1.0, 2.0], role=CurveRole.RESIDUAL)
    view = SeriesView(dataset_id=curve.id, offset=3.0)
    shifted_up = ApplicationController._resolve_generic_curve(curve, view, x_log=False, y_log=True)
    np.testing.assert_allclose(shifted_up.y, [1.0, 4.0, 5.0])
    shifted_down = ApplicationController._resolve_generic_curve(
        curve, replace(view, offset=-2.0), x_log=False, y_log=True
    )
    assert np.all(shifted_down.y > 0)
    np.testing.assert_array_equal(shifted_down.source_indices, [])


# ---------------------------------------------- F07 transfer to a new graph


def _residual_graph(controller):
    residual = GenericCurve(
        x=[0.01, 0.02, 0.03, 0.04],
        y=[-1.5, 0.0, 2.0, -0.5],
        role=CurveRole.RESIDUAL,
        x_label="q",
        y_label="Normalised residual",
        x_unit="1/angstrom",
        y_unit="dimensionless",
    )
    source = controller.new_graph(title="Residuals")
    controller.update_graph(
        replace(
            source,
            x_axis=AxisSpec(label="q [Å⁻¹]", log=True),
            y_axis=AxisSpec(label="Normalised residual", log=False),
        )
    )
    controller.add_datasets((residual,), graph_id=source.id)
    return controller.workspace.graph(source.id)


def test_f07_copy_residual_to_new_graph_keeps_signed_values_and_labels():
    controller = ApplicationController()
    source = _residual_graph(controller)
    target = GraphDocument(title="Copy")
    controller.transfer_series_to_new_graph(
        source.id, target, [source.series[0].id], move=False
    )
    copied = controller.workspace.graph(target.id)
    assert copied.y_axis.log is False
    assert copied.y_axis.label == "Normalised residual"
    snapshot = next(iter(controller.snapshots[target.id].values()))
    assert len(snapshot.y) == 4 and snapshot.y.min() < 0


def test_f07_scattering_transfer_keeps_target_axes():
    controller = ApplicationController()
    graph = controller.workspace.graphs[0]
    controller.add_datasets((Dataset(q=[0.01, 0.02], intensity=[2.0, 1.0]),), graph_id=graph.id)
    graph = controller.workspace.graph(graph.id)
    target = GraphDocument(title="Copy")
    controller.transfer_series_to_new_graph(graph.id, target, [graph.series[0].id], move=False)
    assert controller.workspace.graph(target.id).y_axis == GraphDocument().y_axis


# --------------------------------------------------------- F12 axis limits


def test_f12_axis_range_problem_rejects_unusable_limits():
    assert AxisSpec(log=True, minimum=-1.0, maximum=10.0).range_problem("X axis")
    assert AxisSpec(minimum=float("nan")).range_problem()
    assert AxisSpec(maximum=float("inf")).range_problem()
    assert AxisSpec(log=True, minimum=0.1, maximum=10.0).range_problem() is None
    assert AxisSpec(log=False, minimum=-1.0, maximum=10.0).range_problem() is None
    assert AxisSpec(log=True, minimum=0.1).range_problem() is None


# ----------------------------------------------------------- renderer tests


def _rendered(qapp, graph_changes=None, dataset=None):
    from bernardyn.renderers.plot2d import Plot2DWidget

    controller = ApplicationController()
    graph = controller.workspace.graphs[0]
    controller.add_datasets(
        (dataset or Dataset(q=[1.0, 2.0, 3.0], intensity=[10.0, 20.0, 30.0]),), graph_id=graph.id
    )
    graph = controller.workspace.graph(graph.id)
    if graph_changes is not None:
        controller.update_graph(graph_changes(graph), recompute=True)
        graph = controller.workspace.graph(graph.id)
    widget = Plot2DWidget()
    widget.resize(600, 400)
    widget.render(graph, controller.snapshots[graph.id])
    qapp.processEvents()
    return widget, graph, controller


def test_f09_preview_does_not_change_exported_ranges(qapp):
    widget, graph, controller = _rendered(qapp)
    view_box = widget.getPlotItem().getViewBox()
    original = view_box.viewRange()
    preview = Dataset(q=[100.0, 200.0], intensity=[1.0, 2.0])
    view = SeriesView(dataset_id=preview.id)
    widget.set_preview([resolve_series(preview, view, controller.transforms, x_log=True, y_log=True)])
    widened = view_box.viewRange()
    assert widened[0][1] > original[0][1] + 1
    with widget._preview_hidden():
        np.testing.assert_allclose(view_box.viewRange(), original)
    np.testing.assert_allclose(view_box.viewRange(), widened)
    widget.close()


def test_f10_auto_range_includes_visible_error_bars(qapp):
    dataset = Dataset(q=[1.0, 2.0], intensity=[10.0, 20.0], uncertainty=[100.0, 100.0])

    def linear_with_errors(graph):
        return replace(
            graph,
            x_axis=replace(graph.x_axis, log=False),
            y_axis=replace(graph.y_axis, log=False),
            series=tuple(
                replace(view, style=replace(view.style, show_y_error_bars=True))
                for view in graph.series
            ),
        )

    widget, graph, _ = _rendered(qapp, linear_with_errors, dataset)
    _, (low, high) = widget._resolved_bounds(graph)
    assert low <= -90 and high >= 120
    hidden = replace(
        graph,
        series=tuple(
            replace(view, style=replace(view.style, show_y_error_bars=False))
            for view in graph.series
        ),
    )
    _, (low, high) = widget._resolved_bounds(hidden)
    assert low == pytest.approx(10) and high == pytest.approx(20)
    widget.close()


def test_f12_renderer_reports_invalid_and_applies_one_sided_limits(qapp):
    def invalid(graph):
        return replace(
            graph, x_axis=replace(graph.x_axis, auto_range=False, minimum=-1.0, maximum=10.0)
        )

    widget, _, _ = _rendered(qapp, invalid)
    assert any("Fixed X axis range not applied" in w for w in widget.render_warnings)
    widget.close()

    def one_sided(graph):
        return replace(graph, x_axis=replace(graph.x_axis, auto_range=False, minimum=0.5))

    widget, _, _ = _rendered(qapp, one_sided)
    (x_low, x_high), _ = widget.getPlotItem().getViewBox().viewRange()
    assert x_low == pytest.approx(np.log10(0.5))
    assert x_high == pytest.approx(np.log10(3.0))
    widget.close()


def test_f13_non_positive_annotation_on_log_axes_is_reported_not_moved(qapp):
    def with_annotation(graph):
        return replace(
            graph,
            annotations=(Annotation(kind=AnnotationKind.TEXT, text="origin", position=(0.0, 0.0)),),
        )

    widget, _, _ = _rendered(qapp, with_annotation)
    assert widget._annotation_items == []
    assert any("not positive on the logarithmic" in w for w in widget.render_warnings)
    widget.close()


def test_f15_context_menu_cannot_change_axes_outside_the_document(qapp):
    widget, _, _ = _rendered(qapp)
    plot = widget.getPlotItem()
    assert plot.menuEnabled() is False
    menu = plot.getViewBox().menu
    hidden = [
        action.menu().title()
        for action in menu.actions()
        if action.menu() is not None and not action.isVisible()
    ]
    assert hidden == ["X axis", "Y axis"]
    assert widget.scene().contextMenu == []
    widget.close()


# ---------------------------------------------------------------- GUI tests


def _window(tmp_path):
    from bernardyn.gui.main_window import MainWindow

    window = MainWindow()
    window.user_state = UserState(tmp_path / "preferences.json")
    return window


def test_f01_undo_after_save_marks_workspace_changed(qapp, tmp_path):
    window = _window(tmp_path)
    package = tmp_path / "work.bernardyn.h5"
    assert window._save_to(package)
    window._new_graph("plot2d")
    assert window.controller.workspace.dirty
    assert window._save_to(package)
    assert not window.controller.workspace.dirty
    window.undo_stack.undo()
    assert len(window.controller.workspace.graphs) == 1
    assert window.controller.workspace.dirty
    window.undo_stack.redo()
    assert not window.controller.workspace.dirty
    window.undo_stack.undo()
    window.undo_stack.undo()  # nothing more to undo: still the first save's content
    window.controller.workspace.dirty = False
    window.close()


def test_f01_graph_edit_undo_back_to_saved_state_is_clean(qapp, tmp_path):
    window = _window(tmp_path)
    assert window._save_to(tmp_path / "work.bernardyn.h5")
    graph = window._current_graph()
    window._queue_graph_change(replace(graph, title="Changed"), False, "Edit")
    assert window.controller.workspace.dirty
    window.undo_stack.undo()
    assert not window.controller.workspace.dirty
    window.close()


def test_f02_import_graph_has_its_own_undo_entry(qapp, tmp_path, monkeypatch):
    from bernardyn.gui import main_window

    other = ApplicationController()
    other.workspace.graphs[0] = replace(other.workspace.graphs[0], title="Imported")
    package = other.save(tmp_path / "other.bernardyn.h5")

    window = _window(tmp_path)
    window._new_graph("plot2d")
    monkeypatch.setattr(
        main_window.QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(package), "")
    )

    class AcceptAll:
        DialogCode = main_window.GraphSelectionDialog.DialogCode

        def __init__(self, graphs, parent=None):
            self._ids = [graph_id for graph_id, _ in graphs]

        def exec(self):
            return self.DialogCode.Accepted

        def selected_ids(self):
            return self._ids

    monkeypatch.setattr(main_window, "GraphSelectionDialog", AcceptAll)
    window._import_graph()
    assert len(window.controller.workspace.graphs) == 3
    assert window.undo_stack.undoText() == "Import graph"
    window.undo_stack.undo()
    assert len(window.controller.workspace.graphs) == 2
    window.undo_stack.redo()
    assert window.controller.workspace.graphs[-1].title == "Imported"
    window.controller.workspace.dirty = False
    window.close()


def test_f11_inspector_remove_can_empty_the_graph(qapp, tmp_path):
    window = _window(tmp_path)
    graph_id = window.controller.workspace.active_graph_id
    window.controller.add_datasets(
        (Dataset(q=[0.01, 0.02], intensity=[2.0, 1.0], label="only"),), graph_id=graph_id
    )
    window._rebuild_tabs()
    window.inspector.series_list.setCurrentRow(0)
    window.inspector._remove_series()
    assert window.controller.workspace.graph(graph_id).series == ()
    assert len(window.controller.workspace.datasets) == 1
    window.undo_stack.undo()
    assert len(window.controller.workspace.graph(graph_id).series) == 1
    window.controller.workspace.dirty = False
    window.close()


def test_f16_empty_graph_shows_its_selected_view(qapp, tmp_path):
    window = _window(tmp_path)
    graph = window._current_graph()
    window.controller.update_graph(replace(graph, view_transform_id="kratky"))
    window._sync_inspector()
    assert window.inspector.transform.currentData() == "kratky"
    window.controller.workspace.dirty = False
    window.close()


def test_f12_inspector_explains_refused_log_limits(qapp, tmp_path):
    window = _window(tmp_path)
    inspector = window.inspector
    before = window._current_graph()
    inspector.x_auto.setChecked(False)
    inspector.axis_x_min.setText("-1")
    inspector.axis_x_max.setText("10")
    inspector._edit_axes()
    assert window._current_graph().x_axis.minimum == before.x_axis.minimum
    assert not inspector.axis_message.isHidden()
    assert "positive" in inspector.axis_message.text()
    window.controller.workspace.dirty = False
    window.close()


def test_f08_filter_drops_hidden_files_from_selection(qapp, tmp_path):
    from bernardyn.gui.dialogs import DataSelectorWidget

    for name in ("alpha.h5", "beta.h5"):
        (tmp_path / name).touch()
    selector = DataSelectorWidget(tmp_path, lambda path: [])
    selector.file_list.selectAll()
    assert len(selector.selected_paths()) == 2
    selector.filter.setText("alpha")
    selector._apply_filter()
    assert [path.name for path in selector.selected_paths()] == ["alpha.h5"]
    assert "1 selected" in selector.count.text()


def test_f14_result_checkbox_refreshes_the_preview(qapp, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidgetItem

    from bernardyn.gui.file_browser_panel import FileBrowserPanel

    panel = FileBrowserPanel(lambda path: [], {}, {}, discover_results=None)
    panel.preview_box.setChecked(True)
    item = QListWidgetItem("Data + fit I(Q)")
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(Qt.CheckState.Unchecked)
    panel.selector.results_list.addItem(item)
    panel._preview_timer.stop()
    item.setCheckState(Qt.CheckState.Checked)
    assert panel._preview_timer.isActive()
    panel._preview_timer.stop()
    panel.selector.q_unit.setCurrentIndex(1)
    assert panel._preview_timer.isActive()
