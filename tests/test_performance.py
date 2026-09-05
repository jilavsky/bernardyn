import time
from dataclasses import replace

import numpy as np
import pytest

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import Dataset, SeriesView
from bernardyn.renderers.opengl import OpenGLPlotWidget, opengl_available
from bernardyn.renderers.plot2d import Plot2DWidget


@pytest.mark.performance
def test_twenty_large_curves_initial_render_and_style_update_targets(qapp):
    controller = ApplicationController()
    graph = controller.workspace.graphs[0]
    q = np.geomspace(1e-4, 1, 10_000)
    views = []
    for index in range(20):
        dataset = Dataset(q=q, intensity=(index + 1) * q ** (-3.5), label=f"curve {index}")
        controller.workspace.add_dataset(dataset)
        views.append(SeriesView(dataset_id=dataset.id, legend_label=dataset.label))
    graph = graph.replace_series(views)
    controller.workspace.replace_graph(graph)
    widget = Plot2DWidget()

    started = time.perf_counter()
    snapshots = controller.recompute_graph(graph.id)
    widget.render(graph, snapshots)
    qapp.processEvents()
    initial_elapsed = time.perf_counter() - started

    changed = replace(
        graph,
        series=(
            replace(graph.series[0], style=replace(graph.series[0].style, line_width=3.0)),
            *graph.series[1:],
        ),
    )
    started = time.perf_counter()
    widget.apply_graph(changed, snapshots)
    qapp.processEvents()
    style_elapsed = time.perf_counter() - started
    widget.close()

    assert initial_elapsed < 2.0
    assert style_elapsed < 0.25


@pytest.mark.performance
def test_waterfall_preparation_target(qapp):
    available, reason = opengl_available()
    if not available:
        pytest.skip(reason)
    controller = ApplicationController()
    graph = controller.workspace.graphs[0]
    q = np.geomspace(1e-3, 1, 2_000)
    views = []
    for index in range(30):
        dataset = Dataset(q=q, intensity=(index + 1) / (1 + q**4), label=f"curve {index}")
        controller.workspace.add_dataset(dataset)
        views.append(SeriesView(dataset_id=dataset.id))
    graph = replace(
        graph.replace_series(views),
        renderer_id="opengl_waterfall",
        renderer_config={
            "mode": "waterfall",
            "spacing": 1.0,
            "normalization": "maximum",
            "show_grid": True,
            "camera": {},
        },
    )
    controller.workspace.replace_graph(graph)
    snapshots = controller.recompute_graph(graph.id)
    widget = OpenGLPlotWidget()
    started = time.perf_counter()
    widget.render(graph, snapshots)
    qapp.processEvents()
    elapsed = time.perf_counter() - started
    data = widget.renderer_data()
    widget.close()

    assert data["waterfall_lengths"].shape == (30,)
    assert elapsed < 2.0
