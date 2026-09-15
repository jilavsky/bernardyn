from pathlib import Path
from shutil import copy2

import numpy as np

from bernardyn.core.controller import ApplicationController
from bernardyn.io.results import discover_results, load_result_bundle

FIXTURE = Path(__file__).parents[1] / "testData" / "Al_Mg_Si__40C_0min_0498.h5"


def test_real_pyirena_result_fixture_exposes_r1_iq_bundles(tmp_path):
    source = tmp_path / FIXTURE.name
    copy2(FIXTURE, source)
    descriptors = discover_results(source)
    assert [(item.analysis, item.title) for item in descriptors] == [
        ("unified_fit", "Unified Fit"),
        ("size_distribution", "Size Distribution"),
    ]
    saved = []
    for descriptor in descriptors:
        bundle = load_result_bundle(descriptor)
        measured, fitted = bundle.records
        assert len(measured.q) == len(fitted.q) > 0
        assert measured.uncertainty is not None
        assert bundle.metadata["chi_squared"] is not None
        assert measured.metadata["bernardyn_result"]["role"] == "measured"
        assert fitted.metadata["bernardyn_result"]["role"] == "fit"
        controller = ApplicationController()
        controller.add_datasets(
            (measured.to_dataset(), fitted.to_dataset()), series_styles=bundle.styles
        )
        graph = controller.workspace.graphs[0]
        assert graph.x_axis.log and graph.y_axis.log
        assert graph.series[0].style.line_style == "none"
        assert graph.series[1].style.symbol is None
        path = controller.save(tmp_path / descriptor.analysis)
        saved.append((path, fitted))
    source.unlink()
    for path, fitted in saved:
        restored = ApplicationController()
        restored.open_package(path)
        restored_graph = restored.workspace.graphs[0]
        np.testing.assert_allclose(
            restored.snapshots[restored_graph.id][restored_graph.series[1].id].y,
            fitted.intensity,
        )
