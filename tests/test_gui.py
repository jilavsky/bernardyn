from dataclasses import replace

import numpy as np
import pyqtgraph as pg
import pytest
from PySide6.QtCore import Qt

from bernardyn.core.models import Annotation, AnnotationKind, Dataset, GraphDocument, PlotSeries
from bernardyn.gui.dialogs import DataFileSelectorDialog, LocationDialog
from bernardyn.gui.graph_page import GraphPage
from bernardyn.gui.main_window import MainWindow
from bernardyn.io.file_browser import files_in_folder, make_file_matcher, sort_paths
from bernardyn.io.sources import ScatteringLocation
from bernardyn.renderers.opengl import OpenGLPlotWidget, opengl_available
from bernardyn.renderers.plot2d import Plot2DWidget, PublicationAxisItem


def test_main_window_starts_with_independent_graph_model(qapp):
    window = MainWindow()
    assert window.tabs.count() == 1
    assert len(window.controller.workspace.graphs) == 1
    assert window.inspector._graph.id == window.controller.workspace.graphs[0].id
    window.controller.workspace.dirty = False
    window.close()


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
    assert b"<svg" in svg.read_bytes()[:500]
    assert csv.read_text().startswith("series,x,y,dx,dy,source_index")
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
    assert any(isinstance(item, pg.TextItem) for item in page.renderer.getPlotItem().items)
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
    widget.update(graph, {snapshot.series_id: replacement})
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
