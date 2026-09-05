from dataclasses import replace

import numpy as np
import pytest

from bernardyn.core.models import Dataset, GraphDocument
from bernardyn.gui.graph_page import GraphPage
from bernardyn.gui.main_window import MainWindow
from bernardyn.renderers.opengl import OpenGLPlotWidget, opengl_available
from bernardyn.renderers.plot2d import Plot2DWidget


def test_main_window_starts_with_independent_graph_model(qapp):
    window = MainWindow()
    assert window.tabs.count() == 1
    assert len(window.controller.workspace.graphs) == 1
    assert window.inspector._graph.id == window.controller.workspace.graphs[0].id
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
