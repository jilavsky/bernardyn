import base64
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pyqtgraph as pg
import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QAction, QDropEvent, QImage
from PySide6.QtWidgets import QAbstractItemView, QDockWidget

from bernardyn import __version__
from bernardyn import app as bernardyn_app
from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import (
    Annotation,
    AnnotationKind,
    AxisSpec,
    Dataset,
    GenericCurve,
    GraphDocument,
    LegendSpec,
    PlotSeries,
    TypographySpec,
)
from bernardyn.gui import main_window
from bernardyn.gui.dialogs import AnnotationDialog, DataFileSelectorDialog, LocationDialog
from bernardyn.gui.graph_page import GraphPage
from bernardyn.gui.main_window import DatasetListWidget, MainWindow, _documentation_url
from bernardyn.io.file_browser import files_in_folder, make_file_matcher, sort_paths
from bernardyn.io.sources import ScatteringLocation
from bernardyn.renderers.opengl import OpenGLPlotWidget, opengl_available
from bernardyn.renderers.plot2d import DraggablePowerLawGuide, Plot2DWidget, PublicationAxisItem
from bernardyn.state import UserState


def test_main_window_starts_with_independent_graph_model(qapp):
    window = MainWindow()
    assert window.tabs.count() == 1
    assert len(window.controller.workspace.graphs) == 1
    assert window.inspector._graph.id == window.controller.workspace.graphs[0].id
    assert window.workspace_indicator.text() == "Workspace: Untitled workspace (unsaved)"
    window.controller.workspace.dirty = False
    window.close()


@pytest.mark.parametrize("flag", ["--version", "-version", "--v", "-V"])
def test_version_flag_exits_before_starting_gui(flag, monkeypatch, capsys):
    def fail_if_gui_starts(*args, **kwargs):
        raise AssertionError("version flag must not create a QApplication")

    monkeypatch.setattr(bernardyn_app, "QApplication", fail_if_gui_starts)
    assert bernardyn_app.main([flag]) == 0
    assert capsys.readouterr().out == f"Bernardyn {__version__}\n"


def test_gui_shows_version_and_about_action(qapp, monkeypatch):
    window = MainWindow()
    assert window.version_indicator.text() == f"Bernardyn {__version__}"
    assert window.about_action.menuRole() == QAction.MenuRole.AboutRole
    shown = []
    monkeypatch.setattr(main_window.QMessageBox, "about", lambda *args: shown.append(args))
    window.about_action.trigger()
    assert shown == [(window, "About Bernardyn", f"Bernardyn {__version__}")]
    window.controller.workspace.dirty = False
    window.close()


def test_new_2d_graph_has_a_portable_shortcut(qapp):
    window = MainWindow()
    assert window.new_2d_action.shortcut().toString() == "Ctrl+Shift+N"
    window.controller.workspace.dirty = False
    window.close()


def test_pyirena_distribution_import_creates_a_typed_linear_graph(qapp, monkeypatch):
    fixture = Path(__file__).parents[1] / "testData" / "Al_Mg_Si__40C_0min_0498.h5"
    window = MainWindow()
    monkeypatch.setattr(
        main_window.QFileDialog,
        "getOpenFileNames",
        lambda *args: ([str(fixture)], ""),
    )
    window._import_result_selection([fixture], {"size_distribution": ("volume_distribution",)})
    assert len(window.controller.workspace.graphs) == 2
    graph = window.controller.workspace.graphs[-1]
    assert graph.x_axis.label == "Radius [Å]"
    assert not graph.x_axis.log and not graph.y_axis.log
    dataset = window.controller.workspace.datasets[graph.series[0].dataset_id]
    assert isinstance(dataset, GenericCurve)
    assert dataset.y_semantic == "volume_fraction_density_per_radius"
    window.undo_stack.undo()
    assert len(window.controller.workspace.graphs) == 1
    window.controller.workspace.dirty = False
    window.close()


def test_pyirena_waxs_import_uses_linear_axes_and_includes_peaks(qapp, monkeypatch):
    fixture = Path(__file__).parents[1] / "testData" / "pyirena_1_2_WAXS_Al_7075.h5"
    window = MainWindow()
    monkeypatch.setattr(
        main_window.QFileDialog,
        "getOpenFileNames",
        lambda *args: ([str(fixture)], ""),
    )
    window._import_result_selection([fixture], {"waxs_peakfit": ("iq",)})
    graph = window.controller.workspace.graphs[0]
    assert not graph.x_axis.log and not graph.y_axis.log
    assert len(graph.series) == 10
    assert len({series.style.color for series in graph.series}) > 2
    window.undo_stack.undo()
    assert not window.controller.workspace.graphs[0].series
    window.controller.workspace.dirty = False
    window.close()


def test_2d_canvas_previews_output_aspect_with_canvas_coloured_right_standoff(qapp):
    graph = GraphDocument(
        width_px=800,
        height_px=400,
        width_in=8,
        height_in=4,
        dpi=100,
        background=(220, 230, 240, 255),
    )
    page = GraphPage(graph)
    page.resize(800, 400)
    page.show()
    page.render(graph, {})
    qapp.processEvents()
    assert page.renderer.geometry().right() < page.canvas.width() - 1
    assert page.canvas.palette().color(page.canvas.backgroundRole()).getRgb() == (220, 230, 240, 255)
    # The graph fills the requested 2:1 shape, while the canvas keeps a clear
    # right-side background margin for the boxed right axis.
    geometry = page.renderer.geometry()
    assert geometry.width() / geometry.height() == pytest.approx(2.0, rel=0.01)
    assert page.canvas.width() - geometry.right() - 1 >= page.canvas.RIGHT_STANDOFF_PX
    assert page.canvas.size_badge.text() == f"Display: {geometry.width()} × {geometry.height()} px"
    page.close()


def test_last_workspace_is_remembered_on_save_and_restored(qapp, tmp_path, monkeypatch):
    state_path = tmp_path / "preferences.json"
    package_path = tmp_path / "saved-workspace.bernardyn.h5"
    window = MainWindow()
    window.user_state = UserState(state_path)
    monkeypatch.setattr(window, "_collect_artifacts", lambda: ({}, {}))

    assert window._save_to(package_path)
    assert window.user_state.get("last_workspace_path") == str(package_path.resolve())
    assert window.user_state.get("recent_workspace_paths") == [str(package_path.resolve())]
    assert window.workspace_indicator.text() == "Workspace: saved-workspace.bernardyn.h5"
    assert str(package_path.resolve()) in window.workspace_indicator.toolTip()
    window.controller.workspace.dirty = False
    window.close()

    restored = MainWindow()
    restored.user_state = UserState(state_path)
    restored.restore_last_workspace()
    assert restored.controller.package_path == package_path.resolve()
    assert restored.controller.workspace.title == "Untitled workspace"
    assert restored.workspace_indicator.text() == "Workspace: saved-workspace.bernardyn.h5"
    restored.controller.workspace.dirty = False
    restored.close()


def test_recent_workspaces_are_deduplicated_and_emit_the_selected_path(qapp, tmp_path):
    first = tmp_path / "first.bernardyn.h5"
    second = tmp_path / "second.bernardyn.h5"
    first.touch()
    second.touch()
    window = MainWindow()
    window.user_state = UserState(tmp_path / "preferences.json")
    window._remember_workspace(first)
    window._remember_workspace(second)
    window._remember_workspace(first)
    selected = []
    window.openWorkspaceRequested.connect(selected.append)

    window._populate_recent_workspaces_menu()
    actions = window.recent_workspaces_menu.actions()
    assert window.user_state.get("recent_workspace_paths") == [str(first.resolve()), str(second.resolve())]
    actions[0].trigger()
    assert selected == [first.resolve()]
    window.controller.workspace.dirty = False
    window.close()


def test_workspace_lock_prevents_a_second_editor(qapp, tmp_path):
    package_path = tmp_path / "locked.bernardyn.h5"
    first = MainWindow()
    first.user_state = UserState(tmp_path / "first-preferences.json")
    assert first._save_to(package_path)

    second = MainWindow()
    second.user_state = UserState(tmp_path / "second-preferences.json")
    assert not second.open_workspace(package_path, show_errors=False)

    first.controller.workspace.dirty = False
    first.close()
    assert second.open_workspace(package_path, show_errors=False)
    second.controller.workspace.dirty = False
    second.close()


def test_lock_from_another_computer_is_only_broken_when_asked(qapp, tmp_path, monkeypatch):
    import os

    package_path = tmp_path / "shared.bernardyn.h5"
    writer = MainWindow()
    writer.user_state = UserState(tmp_path / "writer-preferences.json")
    assert writer._save_to(package_path)
    writer._release_workspace_lock()
    writer.controller.workspace.dirty = False
    writer.close()
    # A live-looking lock from a process on another host, an hour old.
    lock_path = Path(f"{package_path.resolve()}.lock")
    lock_path.write_text("4242\nbernardyn\nbeamline-pc\n")
    os.utime(lock_path, (lock_path.stat().st_atime - 3600, lock_path.stat().st_mtime - 3600))

    window = MainWindow()
    window.user_state = UserState(tmp_path / "preferences.json")
    owners = []
    monkeypatch.setattr(window, "_ask_break_lock", lambda target, owner: owners.append(owner) or False)
    assert not window.open_workspace(package_path)
    assert owners == ["bernardyn (process 4242) on beamline-pc"]
    assert lock_path.read_text().startswith("4242")

    monkeypatch.setattr(window, "_ask_break_lock", lambda target, owner: True)
    assert window.open_workspace(package_path)
    assert lock_path.read_text().startswith(str(os.getpid()))
    window.controller.workspace.dirty = False
    window.close()


def test_documentation_button_is_present(qapp):
    window = MainWindow()
    assert "#c62828" in window.documentation_button.styleSheet()
    assert window.documentation_button.text() == "Documentation"
    assert "local" in window.documentation_button.toolTip()
    assert window.documentation_button.parent() is not window.menuBar()
    assert window.findChild(QDockWidget, "datasetsDock") is not None
    assert window.findChild(QDockWidget, "graphInspectorDock") is not None
    window.controller.workspace.dirty = False
    window.close()


def test_primary_docks_are_recovered_after_layout_restore(qapp):
    window = MainWindow()
    window.show()
    qapp.processEvents()
    window.datasets_dock.hide()
    window.inspector_dock.setFloating(True)
    window.inspector_dock.hide()

    window.controller.workspace.layout_state = json.dumps(
        {
            "window_state": base64.b64encode(window.saveState()).decode("ascii"),
            "geometry": base64.b64encode(window.saveGeometry()).decode("ascii"),
        }
    )
    window._restore_layout()
    qapp.processEvents()

    assert window.datasets_dock.isVisible()
    assert window.inspector_dock.isVisible()
    assert not window.datasets_dock.isFloating()
    assert not window.inspector_dock.isFloating()
    assert window.dockWidgetArea(window.datasets_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.dockWidgetArea(window.inspector_dock) == Qt.DockWidgetArea.RightDockWidgetArea
    window.controller.workspace.dirty = False
    window.close()


def test_dataset_filters_apply_to_the_browser_and_inspector(qapp):
    window = MainWindow()
    ordinary = Dataset(q=[1, 2], intensity=[3, 4], label="ordinary")
    measured = Dataset(
        q=[1, 2],
        intensity=[3, 4],
        label="measured",
        metadata={"bernardyn_result": {"analysis": "unified_fit", "role": "measured"}},
    )
    model = Dataset(
        q=[1, 2],
        intensity=[3, 4],
        label="model",
        metadata={"bernardyn_result": {"analysis": "unified_fit", "role": "fit"}},
    )
    window.controller.add_datasets((ordinary, measured, model))
    window._rebuild_tabs()

    window.dataset_filter.setCurrentIndex(window.dataset_filter.findData("unified_fit_measured"))
    assert window.dataset_list.count() == 1
    assert "measured" in window.dataset_list.item(0).text()
    window.dataset_filter.setCurrentIndex(window.dataset_filter.findData("unified_fit_fit"))
    assert window.dataset_list.count() == 1
    assert "model" in window.dataset_list.item(0).text()
    assert not window.dataset_list.dragEnabled()
    window.inspector.series_filter.setCurrentIndex(
        window.inspector.series_filter.findData("unified_fit_fit")
    )
    assert window.inspector.series_list.count() == 1
    assert window.inspector.series_splitter.count() == 2
    window.controller.workspace.dirty = False
    window.close()


def test_typography_spin_boxes_update_after_a_rate_limited_arrow_change(qapp):
    window = MainWindow()
    inspector = window.inspector
    original = window.controller.workspace.graphs[0].typography.title_size
    assert inspector.title_font_size.minimumWidth() >= 88
    inspector.title_font_size.setValue(original + 1)
    assert inspector._live_update_timer.isActive()
    inspector._flush_live_edit()
    assert window.controller.workspace.graphs[0].typography.title_size == original + 1
    window.controller.workspace.dirty = False
    window.close()


def test_title_font_size_and_display_canvas_action(qapp):
    """Title typography must reach QtGraph; Set sends the requested pixels."""
    window = MainWindow()
    inspector = window.inspector
    inspector.title_font_size.setValue(26)
    inspector._flush_live_edit()
    page = window.tabs.currentWidget()
    assert isinstance(page, GraphPage)
    assert page.renderer.getPlotItem().titleLabel.opts["size"] == "26pt"
    # QFontComboBox resolves unavailable families differently across platforms
    # (Windows CI commonly returns "Sans Serif" for the default Arial).
    assert page.renderer.getPlotItem().titleLabel.opts["family"] == (
        window.controller.workspace.graphs[0].typography.family
    )
    requested = []
    inspector.displayCanvasRequested.connect(lambda width, height: requested.append((width, height)))
    window.show()
    qapp.processEvents()
    inspector.canvas_width.setValue(640)
    inspector.canvas_height.setValue(480)
    inspector.set_display_canvas.click()
    for _ in range(5):
        qapp.processEvents()
    assert requested == [(640, 480)]
    assert page.renderer.size().toTuple() == (640, 480)
    window.controller.workspace.dirty = False
    window.close()


def test_documentation_url_uses_github_when_local_docs_are_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(main_window, "DOCUMENTATION_DIRECTORY", tmp_path / "missing")
    assert _documentation_url().toString() == main_window.DOCUMENTATION_URL


def test_location_dialog_uses_qt_check_state_enums(qapp, tmp_path):
    locations = [
        ScatteringLocation(path=tmp_path / "one.h5", adapter_id="hdf5", display_name="one"),
        ScatteringLocation(path=tmp_path / "two.h5", adapter_id="hdf5", display_name="two"),
    ]
    dialog = LocationDialog(locations)
    assert dialog.selected() == locations
    dialog.close()


def test_folder_selector_uses_pyirena_style_type_filter_and_sort(qapp, tmp_path):
    (tmp_path / "sample_30C_02.h5").touch()
    (tmp_path / "sample_20C_01.h5").touch()
    (tmp_path / "notes.txt").touch()
    (tmp_path / "archived.bernardyn.h5").touch()
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "curve.dat").touch()
    assert {path.name for path in files_in_folder(tmp_path, "hdf5")} == {
        "sample_30C_02.h5", "sample_20C_01.h5"
    }
    assert [path.name for path in sort_paths(files_in_folder(tmp_path, "hdf5"), 2)] == [
        "sample_20C_01.h5", "sample_30C_02.h5"
    ]
    assert make_file_matcher("20C|notes")("sample_20C_01.h5")
    assert make_file_matcher("20C|notes")("notes.txt")
    assert not make_file_matcher("20C|notes")("sample_30C_02.h5")
    def discover(path):
        return [
            ScatteringLocation(
                path=path,
                adapter_id="hdf5",
                internal_path="entry/blank/sasdata",
                display_name=f"{path.name}: blank",
            ),
            ScatteringLocation(
                path=path,
                adapter_id="hdf5",
                internal_path="entry/sample/sasdata",
                display_name=f"{path.name}: sample",
            ),
        ]

    dialog = DataFileSelectorDialog(tmp_path, discover)
    dialog.filter.setText("20C")
    visible = [
        dialog.list.item(index).text()
        for index in range(dialog.list.count())
        if not dialog.list.item(index).isHidden()
    ]
    assert visible == ["sample_20C_01.h5"]
    dialog._select_all_visible()
    assert [path.name for path in dialog.selected_paths()] == ["sample_20C_01.h5"]
    dialog.file_list.setCurrentRow(0)
    assert dialog.data_list.count() == 2
    assert all(
        dialog.data_list.item(index).checkState() == Qt.CheckState.Unchecked
        for index in range(dialog.data_list.count())
    )
    dialog.data_list.item(1).setCheckState(Qt.CheckState.Checked)
    assert [location.display_name for location in dialog.selected_locations()] == [
        "sample_20C_01.h5: sample"
    ]
    dialog.filter.clear()
    dialog.file_list.setCurrentRow(1)
    assert dialog.data_list.item(1).checkState() == Qt.CheckState.Checked
    dialog.close()
    direct = DataFileSelectorDialog(tmp_path, discover, paths=[tmp_path / "sample_20C_01.h5"])
    assert direct.file_list.count() == 1
    direct.close()


def test_folder_selector_records_the_visible_single_curve_default(qapp, tmp_path):
    path = tmp_path / "sample.h5"
    path.touch()
    locations = [
        ScatteringLocation(
            path=path,
            adapter_id="hdf5",
            internal_path="/entry/sample/sasdata",
            display_name="sample.h5: sasdata",
        )
    ]
    dialog = DataFileSelectorDialog(tmp_path, lambda _: locations, paths=[path])
    dialog.file_list.item(0).setSelected(True)
    dialog.file_list.setCurrentRow(0)
    assert dialog.data_list.item(0).checkState() == Qt.CheckState.Checked
    assert dialog.selected_locations() == locations
    dialog.close()


def test_active_graph_dataset_list_removes_series_and_preserves_catalog(qapp):
    window = MainWindow()
    first = Dataset(q=[1, 2], intensity=[3, 4], label="first")
    second = Dataset(q=[1, 2], intensity=[5, 6], label="second")
    window.controller.add_dataset(first)
    window.controller.add_dataset(second)
    window._refresh_dataset_list()
    first_item = window.dataset_list.takeItem(0)
    window.dataset_list.insertItem(1, first_item)
    window._dataset_list_reordered()
    assert [series.dataset_id for series in window.controller.workspace.graphs[0].series] == [
        second.id,
        first.id,
    ]
    window.dataset_list.setCurrentRow(0)
    window._remove_datasets()
    assert len(window.controller.workspace.graphs[0].series) == 1
    assert {first.id, second.id} <= set(window.controller.workspace.datasets)
    window.controller.workspace.dirty = False
    window.close()


def test_2d_page_renders_and_exports_png_and_svg(qapp, tmp_path):
    window = MainWindow()
    dataset = Dataset(q=np.geomspace(0.001, 1, 100), intensity=np.geomspace(1000, 1, 100), label="sample")
    window.controller.add_dataset(dataset)
    graph = window.controller.workspace.graphs[0]
    graph = replace(graph, width_px=640, height_px=480, width_in=6.4, height_in=4.8, dpi=100)
    window.controller.update_graph(graph, recompute=False)
    window._render_graph(graph.id)
    page = window.tabs.currentWidget()
    assert isinstance(page, GraphPage)
    png = tmp_path / "plot.png"
    svg = tmp_path / "plot.svg"
    csv = tmp_path / "plot.csv"
    itx = tmp_path / "plot.itx"
    page.save_image(png)
    page.save_image(svg)
    page.export_csv(csv)
    page.export_itx(itx)
    assert png.stat().st_size > 100
    assert QImage(str(png)).size().width() == 640
    assert QImage(str(png)).size().height() == 480
    assert page.output_preview_image().size().width() == 640
    assert page.output_preview_image().size().height() == 480
    assert b"<svg" in svg.read_bytes()[:500]
    assert "\nseries,x,y,dx,dy,source_index\n" in csv.read_text(encoding="utf-8")
    assert itx.read_text().startswith("IGOR\n")
    assert len(page.capture_preview()) > 100
    window.controller.workspace.dirty = False
    window.close()


def test_2d_auto_range_is_calculated_once_not_left_in_live_feedback(qapp):
    window = MainWindow()
    window.controller.add_dataset(
        Dataset(q=np.geomspace(0.001, 1, 10_000), intensity=np.geomspace(1e5, 1, 10_000))
    )
    graph = window.controller.workspace.graphs[0]
    window._render_graph(graph.id)
    page = window.tabs.currentWidget()
    assert isinstance(page, GraphPage)
    assert isinstance(page.renderer, Plot2DWidget)
    qapp.processEvents()
    initial_range = page.renderer.getPlotItem().vb.viewRange()
    assert page.renderer.getPlotItem().vb.autoRangeEnabled() == [False, False]
    for _ in range(10):
        qapp.processEvents()
    assert page.renderer.getPlotItem().vb.viewRange() == initial_range
    window.controller.workspace.dirty = False
    window.close()


def test_2d_auto_range_includes_new_data_outside_previous_view(qapp):
    window = MainWindow()
    window.controller.add_dataset(Dataset(q=[0.001, 0.01], intensity=[100, 10]))
    graph = window.controller.workspace.graphs[0]
    window._render_graph(graph.id)
    window.controller.add_dataset(Dataset(q=[10, 100], intensity=[2, 1]))
    window._render_graph(graph.id)
    page = window.tabs.currentWidget()
    assert isinstance(page, GraphPage)
    x_range = page.renderer.getPlotItem().vb.viewRange()[0]
    # Log10(100) is 2. The second series must be visible despite clip-to-view.
    assert x_range[1] >= 2
    window.controller.workspace.dirty = False
    window.close()


def test_initial_layout_refreshes_width_dependent_peak_downsampling(qapp):
    """A graph first drawn in a narrow new tab must not keep duplicate-x bins."""
    controller = ApplicationController()
    controller.add_dataset(
        Dataset(
            q=np.geomspace(1e-4, 1, 1_000),
            intensity=np.geomspace(1e5, 1, 1_000),
        )
    )
    graph = controller.workspace.graphs[0]
    snapshot = next(iter(controller.snapshots[graph.id].values()))
    widget = Plot2DWidget()
    widget.resize(80, 400)
    widget.show()
    widget.render(graph, controller.snapshots[graph.id])
    qapp.processEvents()

    # A fresh GraphPage is initially this narrow until its tab has been laid
    # out. Peak downsampling represents each bin with a repeated x position.
    # After the final canvas width is known, all source points fit and the
    # display cache must be rebuilt without those artificial pairs.
    widget.resize(1_400, 400)
    qapp.processEvents()
    item = next(iter(widget._curve_items.values()))
    displayed_x, _ = item.getData()
    assert displayed_x is not None
    assert len(displayed_x) == len(snapshot.x)
    assert np.all(np.diff(displayed_x) > 0)
    widget.close()


def test_publication_axis_uses_direct_numbers_before_scientific_notation(qapp):
    axis = PublicationAxisItem("bottom")
    assert axis.tickStrings([0.0001, 0.1, 1000, 10000], 1.0, 0.0001) == [
        "0.0001",
        "0.1",
        "1000",
        "1.000e+04",
    ]
    assert axis.tickStrings([10, 100, 1000], 1.0, 10) == ["10", "100", "1000"]
    assert not axis.autoSIPrefix


def test_log_axis_keeps_minor_ticks_but_not_minor_labels_by_default(qapp):
    axis = PublicationAxisItem("bottom")
    levels = axis.logTickValues(-4.0, -1.0, 400, [])
    assert levels[0][1] == [-4.0, -3.0, -2.0, -1.0]
    assert levels[1][1]  # 2–9 ticks remain available as unlabelled minor ticks.
    axis.show_minor_tick_labels = True
    assert axis.logTickValues(-4.0, -1.0, 400, []) != levels


def test_log_axis_labels_do_not_keep_stale_si_scaling_after_rerender(qapp):
    controller = ApplicationController()
    controller.add_dataset(
        Dataset(
            q=np.geomspace(1e-4, 0.3, 200),
            intensity=np.geomspace(1e9, 1, 200),
        )
    )
    graph = controller.workspace.graphs[0]
    widget = Plot2DWidget()
    # The second render previously reused the first view's SI scale, causing
    # x labels 1000x too large and y labels 1e-9 too small.
    widget.render(graph, controller.snapshots[graph.id])
    widget.render(graph, controller.snapshots[graph.id])
    x_axis = widget.getPlotItem().getAxis("bottom")
    y_axis = widget.getPlotItem().getAxis("left")
    assert x_axis.autoSIPrefixScale == 1.0
    assert y_axis.autoSIPrefixScale == 1.0
    assert x_axis.tickStrings([-4, -3, -2, -1], 1.0, 1.0) == [
        "0.0001", "0.001", "0.01", "0.1"
    ]
    assert y_axis.tickStrings([0, 3, 6, 9], 1.0, 1.0) == [
        "1", "10³", "10⁶", "10⁹"
    ]
    widget.close()


def test_legend_is_recreated_after_an_initial_empty_render(qapp):
    """A later data load must not reuse the detached empty-plot legend."""
    window = MainWindow()
    graph = window.controller.workspace.graphs[0]
    window._render_graph(graph.id)
    window.controller.add_dataset(Dataset(q=[1, 2], intensity=[3, 4], label="sample"))
    window._render_graph(graph.id)
    page = window.tabs.currentWidget()
    assert isinstance(page, GraphPage)
    assert page.renderer._legend is page.renderer.getPlotItem().legend
    assert len(page.renderer._legend.items) == 1
    window.controller.workspace.dirty = False
    window.close()


def test_legend_uses_graph_typography_axis_colour_and_own_symbol_size(qapp):
    controller = ApplicationController()
    controller.add_dataset(Dataset(q=[1, 2, 3], intensity=[3, 2, 1], label="sample"))
    original = controller.workspace.graphs[0]
    graph = replace(
        original,
        x_axis=replace(original.x_axis, color=(15, 80, 150, 255)),
        legend=LegendSpec(symbol_size=16),
        typography=TypographySpec(family="Arial", legend_size=12),
    )
    widget = Plot2DWidget()
    widget.render(graph, controller.snapshots[original.id])
    legend = widget._legend
    assert legend is not None
    sample, label = legend.items[0]
    assert label.opts["family"] == "Arial"
    assert label.opts["size"] == "12pt"
    assert label.opts["color"].getRgb() == (15, 80, 150, 255)
    assert sample.item.opts["legend_symbol_size"] == 16
    ignores_transform = bool(
        legend.flags() & legend.GraphicsItemFlag.ItemIgnoresTransformations
    )
    assert ignores_transform
    assert not widget.capture_output_image().isNull()
    assert bool(legend.flags() & legend.GraphicsItemFlag.ItemIgnoresTransformations)
    widget.close()


def test_presentation_change_does_not_reset_the_interactive_view_range(qapp):
    controller = ApplicationController()
    controller.add_dataset(Dataset(q=[1, 2, 3, 4], intensity=[1, 4, 9, 16]))
    graph = controller.workspace.graphs[0]
    widget = Plot2DWidget()
    widget.render(graph, controller.snapshots[graph.id])
    widget.getPlotItem().vb.setRange(xRange=(1.5, 2.5), yRange=(3, 6), padding=0)
    before = widget.getPlotItem().vb.viewRange()
    changed = replace(graph, x_axis=replace(graph.x_axis, minor_tick_labels=True))
    widget.render(changed, controller.snapshots[graph.id])
    after = widget.getPlotItem().vb.viewRange()
    assert after[0] == pytest.approx(before[0])
    assert after[1] == pytest.approx(before[1])
    widget.close()


def test_minor_tick_label_control_does_not_recompute_or_refit_the_graph(qapp):
    window = MainWindow()
    window.controller.add_dataset(Dataset(q=[1, 2, 3, 4], intensity=[1, 4, 9, 16]))
    graph = window.controller.workspace.graphs[0]
    window._render_graph(graph.id)
    page = window.tabs.currentWidget()
    assert isinstance(page, GraphPage)
    page.renderer.getPlotItem().vb.setRange(xRange=(1.5, 2.5), yRange=(3, 6), padding=0)
    before = page.renderer.getPlotItem().vb.viewRange()
    snapshots = window.controller.snapshots[graph.id]
    window.inspector.minor_tick_labels.setChecked(True)
    after = page.renderer.getPlotItem().vb.viewRange()
    assert after[0] == pytest.approx(before[0])
    assert after[1] == pytest.approx(before[1])
    assert window.controller.snapshots[graph.id] is snapshots
    window.controller.workspace.dirty = False
    window.close()


def test_error_bars_can_independently_show_x_y_and_caps(qapp):
    controller = ApplicationController()
    controller.add_dataset(
        Dataset(q=[1, 2, 3], intensity=[3, 2, 1], dq=[0.1, 0.1, 0.1], uncertainty=[0.2, 0.2, 0.2])
    )
    original = controller.workspace.graphs[0]
    series = original.series[0]
    graph = original.replace_series((
        replace(
            series,
            style=replace(series.style, show_error_bars=True, error_caps=True),
        ),
    ))
    widget = Plot2DWidget()
    widget.render(graph, controller.snapshots[original.id])
    errors = widget._error_items[series.id]
    assert len(errors) == 2
    assert any(error.opts["top"] is not None and error.opts["beam"] > 0 for error in errors)
    assert any(error.opts["left"] is not None and error.opts["beam"] > 0 for error in errors)
    y_only = graph.replace_series((
        replace(
            series,
            style=replace(
                series.style,
                show_error_bars=True,
                show_x_error_bars=False,
                show_y_error_bars=True,
            ),
        ),
    ))
    widget.render(y_only, controller.snapshots[original.id])
    assert len(widget._error_items[series.id]) == 1
    assert widget._error_items[series.id][0].opts["top"] is not None
    widget.close()


def test_dataset_style_spin_boxes_update_after_a_rate_limited_arrow_change(qapp):
    window = MainWindow()
    window.controller.add_dataset(Dataset(q=[1, 2], intensity=[3, 4]))
    window._render_graph(window.controller.workspace.graphs[0].id)
    window._sync_inspector()
    inspector = window.inspector
    original = window.controller.workspace.graphs[0].series[0].style.symbol_size
    inspector.symbol_size.setValue(original + 1)
    assert inspector._live_update_timer.isActive()
    inspector._flush_live_edit()
    assert window.controller.workspace.graphs[0].series[0].style.symbol_size == original + 1
    window.controller.workspace.dirty = False
    window.close()


def test_legend_controls_are_grouped_with_datasets_and_autoscale_is_available(qapp):
    window = MainWindow()
    inspector = window.inspector
    assert inspector.autoscale.text() == "Autoscale"
    assert inspector.legend.parent().title() == "Legend"
    assert inspector.legend.parent().parent().title() == "Datasets in graph"
    window.controller.workspace.dirty = False
    window.close()


def test_box_axes_and_minor_label_preference_survive_graph_round_trip():
    graph = GraphDocument(
        box_axes=True,
        x_axis=AxisSpec(label="q", minor_tick_labels=True),
        y_axis=AxisSpec(label="I", minor_tick_labels=True),
    )
    restored = GraphDocument.from_dict(graph.to_dict())
    assert restored.box_axes
    assert restored.x_axis.minor_tick_labels
    assert restored.y_axis.minor_tick_labels


def test_dataset_list_emits_local_file_drops(qapp, tmp_path):
    data_path = tmp_path / "curve.h5"
    data_path.touch()
    widget = DatasetListWidget()
    dropped = []
    widget.pathsDropped.connect(dropped.append)
    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(str(data_path))])
    event = QDropEvent(
        QPointF(),
        Qt.DropAction.CopyAction,
        mime_data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # Finder drops land on QListWidget's viewport, even when it is empty.
    assert widget.viewportEvent(event)
    assert dropped == [[data_path]]
    assert event.isAccepted()
    widget.close()


def test_dropped_data_uses_the_profile_aware_import_dialog(qapp, tmp_path, monkeypatch):
    folder = tmp_path / "folder"
    folder.mkdir()
    data_path = tmp_path / "curve.h5"
    data_path.touch()
    window = MainWindow()
    calls = []
    monkeypatch.setattr(window, "_open_file_selector", lambda *args: calls.append(args))
    window._dropped_data_paths([folder, data_path])
    assert calls == [(folder,), (tmp_path, [data_path])]
    window.controller.workspace.dirty = False
    window.close()


def test_dataset_inspector_bulk_visibility_uses_extended_selection(qapp):
    window = MainWindow()
    for label in ("one", "two", "three"):
        window.controller.add_dataset(Dataset(q=[1, 2], intensity=[3, 4], label=label))
    window._sync_inspector()
    series_list = window.inspector.series_list
    assert series_list.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    series_list.item(0).setSelected(True)
    series_list.item(2).setSelected(True)
    window.inspector._set_selected_series_visibility(False)
    graph = window.controller.workspace.graphs[0]
    assert [series.visible for series in graph.series] == [False, True, False]
    assert [series_list.item(index).checkState() for index in range(3)] == [
        Qt.CheckState.Unchecked,
        Qt.CheckState.Checked,
        Qt.CheckState.Unchecked,
    ]
    window.controller.workspace.dirty = False
    window.close()


def test_dataset_visibility_toggle_preserves_inspector_list_scroll_position(qapp):
    window = MainWindow()
    for index in range(40):
        window.controller.add_dataset(Dataset(q=[1, 2], intensity=[3, 4], label=f"curve {index}"))
    window.resize(1200, 800)
    window.show()
    window._sync_inspector()
    qapp.processEvents()

    series_list = window.inspector.series_list
    item = series_list.item(32)
    series_list.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
    qapp.processEvents()
    scroll_position = series_list.verticalScrollBar().value()
    assert scroll_position > 0

    item.setCheckState(Qt.CheckState.Unchecked)

    assert series_list.verticalScrollBar().value() == scroll_position
    assert series_list.item(32).checkState() == Qt.CheckState.Unchecked
    window.controller.workspace.dirty = False
    window.close()


def test_inspector_tabs_and_annotations_default_inside_data_and_render(qapp):
    window = MainWindow()
    window.controller.add_dataset(Dataset(q=[10, 20], intensity=[100, 200]))
    graph = window.controller.workspace.graphs[0]
    graph = replace(
        graph,
        x_axis=replace(graph.x_axis, log=False),
        y_axis=replace(graph.y_axis, log=False),
    )
    window.controller.update_graph(graph, recompute=True)
    window._render_graph(graph.id)
    window._sync_inspector()
    assert window.inspector.tabs.count() == 4
    position, end = window.inspector._annotation_defaults()
    assert position == (15, 150)
    assert end == (17, 170)
    graph = replace(graph, annotations=(Annotation(AnnotationKind.TEXT, position, text="sample"),))
    window.controller.update_graph(graph)
    window._render_graph(graph.id)
    page = window.tabs.currentWidget()
    assert isinstance(page, GraphPage)
    text_items = [item for item in page.renderer.getPlotItem().items if isinstance(item, pg.TextItem)]
    assert len(text_items) == 1
    # Above every curve, and offset by the annotation's own z_order.
    assert text_items[0].zValue() == 100_010  # base overlay z + default z_order
    window.controller.workspace.dirty = False
    window.close()


def test_annotation_defaults_use_the_plotted_snapshot(qapp):
    """Defaults must follow visible renderer data, not a stale re-resolution."""
    window = MainWindow()
    dataset = Dataset(q=[1, 2], intensity=[1000, 2000])
    window.controller.add_dataset(dataset)
    graph = window.controller.workspace.graphs[0]
    series = graph.series[0]
    snapshot = PlotSeries(
        series_id=series.id,
        dataset_id=dataset.id,
        x=[10, 20],
        y=[100, 200],
        source_indices=[0, 1],
        label="visible data",
        transform_id="raw",
        transform_version="1.0",
    )
    window.controller.snapshots[graph.id] = {series.id: snapshot}
    window._sync_inspector()
    position, _ = window.inspector._annotation_defaults()
    assert position == pytest.approx((14.14213562, 141.42135624))
    window.controller.workspace.dirty = False
    window.close()


def test_2d_update_replaces_recomputed_snapshot_data(qapp):
    window = MainWindow()
    dataset = Dataset(q=[1, 2], intensity=[3, 4])
    window.controller.add_dataset(dataset)
    graph = window.controller.workspace.graphs[0]
    snapshot = window.controller.snapshots[graph.id][graph.series[0].id]
    widget = Plot2DWidget()
    widget.render(graph, {snapshot.series_id: snapshot})
    replacement = replace(snapshot, y=np.array([30.0, 40.0]))
    widget.apply_graph(graph, {snapshot.series_id: replacement})
    np.testing.assert_allclose(widget._curve_items[snapshot.series_id].yData, [30, 40])
    widget.close()
    window.controller.workspace.dirty = False
    window.close()


def test_opengl_page_falls_back_without_eager_failure(qapp):
    window = MainWindow()
    graph = window.controller.workspace.graphs[0]
    graph = type(graph).from_dict(
        {**graph.to_dict(), "renderer_id": "opengl_waterfall"}
    )
    window.controller.update_graph(graph)
    page = GraphPage(graph, renderers=window.renderers)
    page.render(graph, {})
    assert page.renderer is not None
    page.close()
    window.controller.workspace.dirty = False
    window.close()


def test_opengl_context_failure_uses_safe_2d_fallback(qapp, monkeypatch):
    monkeypatch.setattr(
        "bernardyn.gui.graph_page.opengl_available",
        lambda: (False, "Qt could not create a usable OpenGL/GLX context"),
    )
    graph = GraphDocument(renderer_id="opengl_waterfall")
    page = GraphPage(graph)
    page.render(graph, {})
    assert isinstance(page.renderer, Plot2DWidget)
    assert page.fallback_reason == "Qt could not create a usable OpenGL/GLX context"
    page.close()


def test_opengl_surface_uses_common_non_extrapolated_grid(qapp):
    available, reason = opengl_available()
    if not available:
        pytest.skip(reason)
    window = MainWindow()
    first = Dataset(q=[1, 2, 3], intensity=[1, 4, 9], label="one")
    second = Dataset(q=[2, 3, 4], intensity=[2, 6, 12], label="two")
    window.controller.add_dataset(first)
    window.controller.add_dataset(second)
    graph = window.controller.workspace.graphs[0]
    graph = replace(
        graph,
        renderer_id="opengl_surface",
        x_axis=replace(graph.x_axis, log=False),
        y_axis=replace(graph.y_axis, log=False),
        renderer_config={
            "mode": "surface",
            "surface_samples": 32,
            "spacing": 2,
            "normalization": "none",
            "show_grid": False,
            "camera": {},
        },
    )
    window.controller.update_graph(graph, recompute=True)
    renderer = OpenGLPlotWidget()
    renderer.render(graph, window.controller.snapshots[graph.id])
    data = renderer.renderer_data()
    assert data["surface_z"].shape == (32, 2)
    assert data["surface_colors"].shape == (32, 2, 4)
    assert data["surface_x"][0] == pytest.approx(2)
    assert data["surface_x"][-1] == pytest.approx(3)
    np.testing.assert_allclose(data["surface_y"], [0, 2])
    renderer.close()
    window.controller.workspace.dirty = False
    window.close()


def test_opengl_framebuffer_capture_when_context_is_available(qapp, tmp_path):
    available, reason = opengl_available()
    if not available:
        pytest.skip(reason)
    renderer = OpenGLPlotWidget()
    renderer.resize(640, 480)
    renderer.show()
    qapp.processEvents()
    if not renderer.view.isValid():
        renderer.close()
        pytest.skip("the Qt platform has no hardware-capable OpenGL context")
    graph = GraphDocument(
        renderer_id="opengl_waterfall",
        renderer_config={"mode": "waterfall", "show_grid": True, "camera": {}},
    )
    renderer.render(graph, {})
    qapp.processEvents()
    preview = renderer.capture_preview(640)
    assert preview.startswith(b"\x89PNG")
    jpeg = tmp_path / "three-d.jpg"
    renderer.save_image(jpeg, 640)
    assert jpeg.read_bytes().startswith(b"\xff\xd8")
    renderer.close()


def test_annotation_dialog_returns_real_enum_kinds(qapp):
    """Qt hands back a str-based enum from item data as a plain str.

    ``QComboBox.addItem(label, AnnotationKind.TEXT)`` stores a QVariant, and
    ``currentData()`` returns ``"text"`` -- so every ``kind is
    AnnotationKind.TEXT`` test downstream silently failed and the renderer
    drew nothing at all, while the annotation sat in the document looking
    perfectly correct.
    """
    for kind in AnnotationKind:
        dialog = AnnotationDialog(default_position=(1.0, 2.0), default_end=(2.0, 3.0))
        dialog.kind.setCurrentIndex(dialog.kind.findData(kind.value))
        annotation = dialog.value()
        assert isinstance(annotation.kind, AnnotationKind)
        assert annotation.kind is kind
        dialog.close()


def test_annotation_dialog_update_button_emits_current_annotation(qapp):
    original = Annotation(AnnotationKind.TEXT, (1.0, 2.0), text="before")
    dialog = AnnotationDialog(original)
    updates = []
    dialog.previewRequested.connect(updates.append)
    dialog.x.setValue(3.5)
    dialog.text.setText("after")
    dialog.update_button.click()
    assert len(updates) == 1
    assert updates[0].id == original.id
    assert updates[0].position == (3.5, 2.0)
    assert updates[0].text == "after"
    dialog.close()


def test_every_annotation_kind_reaches_the_canvas(qapp):
    """Each kind must produce scene items -- no branch may fall through.

    The kind is deliberately passed as the bare string Qt yields from combo
    box item data, not as an enum member: that is the shape the Add button
    actually produced, and the renderer used to draw nothing for it.
    """
    dataset = Dataset(q=[1.0, 2.0, 3.0], intensity=[10.0, 20.0, 30.0])
    for kind in AnnotationKind:
        window = MainWindow()
        window.controller.add_dataset(dataset)
        graph = window.controller.workspace.graphs[0]
        graph = replace(
            graph,
            x_axis=replace(graph.x_axis, log=False),
            y_axis=replace(graph.y_axis, log=False),
            annotations=(
                Annotation(str(kind.value), (2.0, 20.0), end=(2.5, 25.0), text="sample"),
            ),
        )
        window.controller.update_graph(graph, recompute=True)
        window._render_graph(graph.id)
        page = window.tabs.currentWidget()
        assert isinstance(page, GraphPage)
        drawn = [
            item
            for item in page.renderer.getPlotItem().items
            if not isinstance(item, pg.PlotDataItem)
        ]
        assert drawn, f"{kind} produced no scene item"
        assert page.render_warnings == []
        assert graph.annotations[0].kind is kind
        window.controller.workspace.dirty = False
        window.close()


def test_power_law_annotation_is_a_one_decade_draggable_reference_guide(qapp):
    annotation = Annotation(AnnotationKind.POWER_LAW, (0.1, 100), slope=4)
    widget = Plot2DWidget()
    widget.render(GraphDocument(annotations=(annotation,)), {})
    guide = next(
        item for item in widget.getPlotItem().items if isinstance(item, DraggablePowerLawGuide)
    )
    assert guide.flags() & guide.GraphicsItemFlag.ItemIsMovable
    curve = next(item for item in guide.childItems() if isinstance(item, pg.PlotCurveItem))
    x, y = curve.getData()
    np.testing.assert_allclose(x, [-1.5, -0.5])
    np.testing.assert_allclose(y, [4, 0], atol=1e-12)
    moved = []
    widget.powerLawMoved.connect(lambda annotation_id, position: moved.append((annotation_id, position)))
    guide._moved(1, 1)
    assert moved == [(annotation.id, pytest.approx((1.0, 1000.0)))]
    widget.close()


def test_power_law_dialog_uses_a_readable_label_font_default(qapp):
    dialog = AnnotationDialog(default_position=(0.1, 100))
    dialog.kind.setCurrentIndex(dialog.kind.findData(AnnotationKind.POWER_LAW.value))
    assert dialog.font_size_label.text() == "Slope label font size:"
    assert dialog.font_size.value() == 14
    assert dialog.value().font_size == 14
    dialog.close()


def _residual_curve():
    return GenericCurve(
        x=[0.01, 0.02, 0.03], y=[-1.0, 0.5, 2.0], label="res", role="residual",
        x_semantic="scattering_q", y_semantic="normalised_residual", x_label="q",
        y_label="Normalised residual", x_unit="1/angstrom", y_unit="dimensionless",
    )


def test_failed_template_leaves_no_undo_entry_and_no_change(qapp, monkeypatch, tmp_path):
    from bernardyn.template.graph_templates import save_template

    window = MainWindow()
    graph_id = window.controller.workspace.active_graph_id
    window.controller.add_dataset(_residual_curve(), graph_id=graph_id)
    # A Kratky template cannot apply to a residual curve.
    kratky = ApplicationController()
    kratky.set_transform(kratky.workspace.active_graph_id, "kratky")
    template = save_template(tmp_path / "kratky", kratky.workspace.graphs[0], "kratky")
    monkeypatch.setattr(window, "_choose_template", lambda title: template)
    warnings = []
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *args: warnings.append(args))
    before = window.controller.workspace.graph(graph_id)
    count = window.undo_stack.count()

    window._apply_template()

    assert warnings and "raw view" in warnings[0][2]
    assert window.undo_stack.count() == count
    assert window.controller.workspace.graph(graph_id) == before


def test_failed_multi_step_workspace_edit_is_rolled_back(qapp, monkeypatch):
    window = MainWindow()
    graphs = list(window.controller.workspace.graphs)
    count = window.undo_stack.count()
    warnings = []
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *args: warnings.append(args))

    def action():
        window.controller.new_graph(title="half done")
        raise ValueError("second step failed")

    command = main_window.WorkspaceEditCommand(window, "Two steps", action)
    assert not window._push_edit(command, "Two steps")
    assert warnings[0][2] == "second step failed"
    assert window.controller.workspace.graphs == graphs
    assert window.tabs.count() == len(graphs)
    assert window.undo_stack.count() == count


def test_reset_graph_defaults_keeps_the_scientific_view(qapp, monkeypatch):
    window = MainWindow()
    graph_id = window.controller.workspace.active_graph_id
    window.controller.add_dataset(
        Dataset(q=[0.01, 0.02], intensity=[2.0, 1.0], label="s"), graph_id=graph_id
    )
    window.controller.set_transform(graph_id, "kratky")
    monkeypatch.setattr(
        main_window.QMessageBox, "question", lambda *args: main_window.QMessageBox.StandardButton.Yes
    )
    window._reset_graph_defaults()
    graph = window.controller.workspace.graph(graph_id)
    assert graph.view_transform_id == "kratky"
    assert (graph.x_axis.label, graph.y_axis.label) == ("q [Å⁻¹]", "Intensity·q² [cm⁻¹·Å⁻²]")
    assert not graph.y_axis.log


def test_batch_result_import_groups_each_kind_into_one_graph(qapp, monkeypatch, tmp_path):
    from shutil import copy2

    source = Path(__file__).parents[1] / "testData"
    files = [
        copy2(source / "Al_Mg_Si__40C_0min_0498.h5", tmp_path / "first.h5"),
        copy2(source / "Al_Mg_Si__40C_0min_0498.h5", tmp_path / "second.h5"),
        copy2(source / "pyirena_1_2_SimpleFits_Porod.h5", tmp_path / "other.h5"),
    ]
    window = MainWindow()
    skipped = []
    monkeypatch.setattr(main_window.QMessageBox, "information", lambda *args: skipped.append(args[2]))
    count = window.undo_stack.count()

    window._import_result_selection(files, {"unified_fit": ("iq", "residuals")})

    iq_graph, residual_graph = window.controller.workspace.graphs
    assert len(iq_graph.series) == 4  # data + fit for each of two files
    assert len(residual_graph.series) == 2
    assert residual_graph.title == "Unified Fit residuals"
    # One colour per file on both graphs; the fit is drawn as a line.
    assert len({series.style.color for series in iq_graph.series}) == 2
    assert {series.style.color for series in residual_graph.series} == {
        series.style.color for series in iq_graph.series
    }
    assert skipped and "other.h5" in skipped[0]
    assert window.undo_stack.count() == count + 1
    window.undo_stack.undo()
    assert len(window.controller.workspace.graphs) == 1
    assert not window.controller.workspace.graphs[0].series
    window.controller.workspace.dirty = False
    window.close()


def test_several_analyses_arrive_in_one_undo_step(qapp, monkeypatch):
    fixture = Path(__file__).parents[1] / "testData" / "Al_Mg_Si__40C_0min_0498.h5"
    window = MainWindow()
    count = window.undo_stack.count()
    window._import_result_selection(
        [fixture],
        {"unified_fit": ("residuals",), "size_distribution": ("residuals", "volume_distribution")},
    )
    titles = [graph.title for graph in window.controller.workspace.graphs[1:]]
    assert titles == [
        "Unified Fit residuals", "Size Distribution residuals", "Size Distribution volume distribution"
    ]
    # No data + fit: the first new graph is shown.
    assert window._current_graph().title == "Unified Fit residuals"
    assert window.undo_stack.count() == count + 1
    window.undo_stack.undo()
    assert len(window.controller.workspace.graphs) == 1
    window.controller.workspace.dirty = False
    window.close()


def test_duplicate_graph_and_remove_unused_data_are_undoable(qapp, monkeypatch):
    window = MainWindow()
    graph_id = window.controller.workspace.active_graph_id
    window.controller.add_datasets(
        (Dataset(q=[0.01, 0.02], intensity=[2.0, 1.0], label="kept"),
         Dataset(q=[0.01, 0.02], intensity=[3.0, 1.0], label="dropped")),
        graph_id=graph_id,
    )
    window._rebuild_tabs()
    window._duplicate_graph()
    assert window.tabs.count() == 2
    window.undo_stack.undo()
    assert window.tabs.count() == 1

    graph = window.controller.workspace.graph(graph_id)
    window.controller.remove_series(graph_id, graph.series[1].id)
    monkeypatch.setattr(
        main_window.QMessageBox, "question", lambda *args: main_window.QMessageBox.StandardButton.Yes
    )
    window._remove_unused_data()
    assert [item.label for item in window.controller.workspace.datasets.values()] == ["kept"]
    window.undo_stack.undo()
    assert len(window.controller.workspace.datasets) == 2
    window.controller.workspace.dirty = False
    window.close()


def test_data_selector_lists_iq_data_and_results_side_by_side(qapp, tmp_path):
    from shutil import copy2

    source = Path(__file__).parents[1] / "testData"
    for name, target in (
        ("Al_Mg_Si__40C_0min_0498.h5", "a_sample.h5"),
        ("Al_Mg_Si__40C_0min_0498.h5", "b_sample.h5"),
        ("Rh1_0085.h5", "c_plain.h5"),
    ):
        copy2(source / name, tmp_path / target)
    controller = ApplicationController()
    dialog = DataFileSelectorDialog(
        tmp_path,
        controller.sources.discover_path,
        discover_results=main_window._results_in_file,
        iq_results_allowed=False,
    )
    first = dialog.file_list.findItems("a_sample.h5", Qt.MatchFlag.MatchExactly)[0]
    dialog.file_list.setCurrentItem(first)
    labels = [dialog.results_list.item(i).text() for i in range(dialog.results_list.count())]
    assert "Unified Fit · Residuals" in labels
    assert "Size Distribution · Volume distribution" in labels
    data_fit = dialog.results_list.findItems("Unified Fit · Data + fit I(Q)", Qt.MatchFlag.MatchExactly)[0]
    assert not data_fit.flags() & Qt.ItemFlag.ItemIsEnabled  # graph is not in the I(Q) view
    residuals = dialog.results_list.findItems("Unified Fit · Residuals", Qt.MatchFlag.MatchExactly)[0]
    residuals.setCheckState(Qt.CheckState.Checked)
    # The checked kind applies to every selected file; files without it add nothing.
    dialog._select_all_visible()
    assert dialog.selected_results() == {"unified_fit": ("residuals",)}
    # Results alone are enough to accept, although these files hold two I(Q)
    # curves each and none is checked.
    dialog._accept_selection()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.preferences()["result_kinds"] == ["unified_fit/residuals"]
    plain = dialog.file_list.findItems("c_plain.h5", Qt.MatchFlag.MatchExactly)[0]
    dialog.file_list.setCurrentItem(plain)
    assert dialog.results_list.count() == 0
    assert dialog.results_status.text() == "No saved pyIrena results in this file."
    dialog.close()


def test_data_selector_hands_iq_and_results_to_their_loaders(qapp, monkeypatch, tmp_path):
    selected = [tmp_path / "sample.h5"]

    class Choice:
        DialogCode = DataFileSelectorDialog.DialogCode
        q_unit = type("Unit", (), {"currentText": staticmethod(lambda: "1/A")})()
        error_fraction = type("Fraction", (), {"value": staticmethod(lambda: 5.0)})()

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return self.DialogCode.Accepted

        def preferences(self):
            return {}

        def selected_paths(self):
            return selected

        def selected_locations(self):
            return ["location"]

        def selected_results(self):
            return {"unified_fit": ("residuals",)}

    window = MainWindow()
    window.user_state = UserState(tmp_path / "preferences.json")
    queued, imported = [], []
    monkeypatch.setattr(main_window, "DataFileSelectorDialog", Choice)
    monkeypatch.setattr(window, "_queue_locations", lambda locations, *args: queued.append(locations))
    monkeypatch.setattr(window, "_import_result_selection", lambda paths, results: imported.append((paths, results)))
    window._open_file_selector(tmp_path)
    assert queued == [["location"]]
    assert imported == [(selected, {"unified_fit": ("residuals",)})]
    window.controller.workspace.dirty = False
    window.close()


def test_add_from_workspace_offers_loaded_results_that_fit_the_view(qapp, monkeypatch):
    fixture = Path(__file__).parents[1] / "testData" / "Al_Mg_Si__40C_0min_0498.h5"
    window = MainWindow()
    window._import_result_selection([fixture], {"unified_fit": ("iq", "residuals")})
    # A new, empty I(Q) graph can take every loaded result curve.
    window._new_graph("plot2d")
    offered = []

    from PySide6.QtWidgets import QDialog

    class AcceptAll:
        DialogCode = QDialog.DialogCode

        def __init__(self, title, prompt, items, **kwargs):
            offered.append([label for _, label in items])
            self.ids = [item_id for item_id, _ in items]

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selected_ids(self):
            return self.ids

    monkeypatch.setattr(main_window, "ChecklistDialog", AcceptAll)
    window._add_from_workspace()
    labels = offered[-1]
    assert any("Unified Fit residuals" in label for label in labels)
    assert any("Unified Fit model" in label for label in labels)
    graph = window.controller.workspace.graphs[-1]
    assert len(graph.series) == 3
    # In a Kratky view only scattering curves are offered.
    window._new_graph("plot2d")
    window.controller.set_transform(window.controller.workspace.active_graph_id, "kratky")
    window._add_from_workspace()
    assert not any("residuals" in label for label in offered[-1])
    window.controller.workspace.dirty = False
    window.close()


def test_new_and_duplicated_graphs_become_the_current_tab(qapp):
    window = MainWindow()
    window._new_graph("plot2d")
    assert window._current_graph().id == window.controller.workspace.graphs[-1].id
    window._duplicate_graph()
    assert window._current_graph().title.endswith("(copy)")
    window.controller.workspace.dirty = False
    window.close()
