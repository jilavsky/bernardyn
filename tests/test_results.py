from dataclasses import replace
from pathlib import Path
from shutil import copy2

import numpy as np

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import AxisSpec, GenericCurve
from bernardyn.io.results import (
    available_curve_kinds,
    discover_results,
    load_result_bundle,
    load_result_curve,
)

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


def test_real_pyirena_result_fixture_exposes_r2_generic_curves_and_round_trips(tmp_path):
    source = tmp_path / FIXTURE.name
    copy2(FIXTURE, source)
    descriptors = {item.analysis: item for item in discover_results(source)}
    unified = load_result_curve(descriptors["unified_fit"], "residuals")
    sized = load_result_curve(descriptors["size_distribution"], "volume_distribution")
    cumulative = {
        kind: load_result_curve(descriptors["size_distribution"], kind)
        for kind in (
            "cumulative_volume_distribution",
            "cumulative_number_distribution",
            "cumulative_surface_distribution",
        )
    }
    assert available_curve_kinds(descriptors["unified_fit"]) == ("residuals",)
    assert available_curve_kinds(descriptors["size_distribution"]) == (
        "residuals",
        "volume_distribution",
        "cumulative_volume_distribution",
        "cumulative_number_distribution",
        "cumulative_surface_distribution",
    )
    assert unified.curve.role.value == "residual"
    assert unified.curve.y_semantic == "normalised_residual"
    assert unified.curve.y_unit == "dimensionless"
    assert np.any(unified.curve.y < 0)
    assert sized.curve.role.value == "distribution"
    assert sized.curve.x_semantic == "particle_radius"
    assert sized.curve.y_semantic == "volume_fraction_density_per_radius"
    assert sized.curve.point_count == 201
    assert sized.curve.dy is None
    assert {
        kind: bundle.curve.y_semantic for kind, bundle in cumulative.items()
    } == {
        "cumulative_volume_distribution": "cumulative_volume_fraction",
        "cumulative_number_distribution": "cumulative_number_fraction",
        "cumulative_surface_distribution": "cumulative_specific_surface",
    }
    assert [bundle.curve.y_unit for bundle in cumulative.values()] == [
        "volume_fraction",
        "dimensionless",
        "1/angstrom",
    ]
    for bundle in cumulative.values():
        assert bundle.curve.point_count == 201
        assert np.all(np.diff(bundle.curve.y) >= 0)

    controller = ApplicationController()
    graph = controller.workspace.graphs[0]
    graph = replace(
        graph,
        x_axis=AxisSpec(label="q [1/angstrom]", log=True),
        y_axis=AxisSpec(label="Normalised residual [dimensionless]", log=False),
    )
    controller.update_graph(graph)
    controller.add_datasets((unified.curve,), series_styles=(unified.style,))
    snapshot = controller.snapshots[graph.id][controller.workspace.graph(graph.id).series[0].id]
    np.testing.assert_allclose(snapshot.y, unified.curve.y)
    path = controller.save(tmp_path / "residuals")
    source.unlink()
    restored = ApplicationController()
    restored.open_package(path)
    restored_curve = next(iter(restored.workspace.datasets.values()))
    assert isinstance(restored_curve, GenericCurve)
    assert restored_curve.role == unified.curve.role
    assert restored_curve.x_semantic == unified.curve.x_semantic
    np.testing.assert_allclose(restored_curve.x, unified.curve.x)
    np.testing.assert_allclose(restored_curve.y, unified.curve.y)
