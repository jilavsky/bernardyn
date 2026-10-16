from dataclasses import replace
from pathlib import Path
from shutil import copy2

import h5py
import numpy as np
import pytest

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import AxisSpec, GenericCurve
from bernardyn.gui.dataset_filters import matches_dataset_filter
from bernardyn.io.results import (
    available_curve_kinds,
    discover_results,
    load_result_bundle,
    load_result_curve,
)

FIXTURE = Path(__file__).parents[1] / "testData" / "Al_Mg_Si__40C_0min_0498.h5"
RESULT_FIXTURES = Path(__file__).parents[1] / "testData"


def test_discovery_skips_result_groups_without_plot_arrays(tmp_path):
    source = tmp_path / "empty-results.h5"
    with h5py.File(source, "w") as handle:
        handle.create_group("entry/carbon_fit_results")
    assert discover_results(source) == []


def test_real_pyirena_result_fixture_exposes_r1_iq_bundles(tmp_path):
    source = tmp_path / FIXTURE.name
    copy2(FIXTURE, source)
    descriptors = discover_results(source)
    assert [(item.analysis, item.title) for item in descriptors] == [
        ("unified_fit", "Unified Fit"),
        ("size_distribution", "Size Distribution"),
        ("modeling", "Modeling"),
    ]
    saved = []
    for descriptor in descriptors[:2]:
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
        "number_distribution",
        "surface_distribution",
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
        "cumulative_number_distribution": "cumulative_number_density",
        "cumulative_surface_distribution": "cumulative_specific_surface",
    }
    assert [bundle.curve.y_unit for bundle in cumulative.values()] == [
        "volume_fraction",
        "1/cm^3",
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


@pytest.mark.parametrize(
    ("analysis", "filename", "roles"),
    [
        ("modeling", "Modeling_PP15.h5", ("fit", "population_1", "population_2")),
        ("simple_fits", "SimpleFits_Porod.h5", ("measured", "fit")),
        ("waxs_peakfit", "WAXS_Al_7075.h5", ("measured", "fit", "background")),
        ("carbon_fit", "Carbon_CE_1400.h5", ("measured", "fit", "grain_porod", "micropores", "diffraction")),
    ],
)
def test_pyirena_1_2_saved_results_are_plottable_and_portable(tmp_path, analysis, filename, roles):
    source = RESULT_FIXTURES / f"pyirena_1_2_{filename}"
    descriptors = discover_results(source)
    descriptor = next(item for item in descriptors if item.analysis == analysis)
    bundle = load_result_bundle(descriptor)
    assert tuple(record.metadata["bernardyn_result"]["role"] for record in bundle.records[:len(roles)]) == roles
    assert len(bundle.records) == len(bundle.styles)
    controller = ApplicationController()
    controller.add_datasets(tuple(record.to_dataset() for record in bundle.records), series_styles=bundle.styles)
    graph = controller.workspace.graphs[0]
    assert len(graph.series) == len(bundle.records)
    saved = controller.save(tmp_path / analysis)
    restored = ApplicationController()
    restored.open_package(saved)
    assert len(restored.workspace.graphs[0].series) == len(bundle.records)
    for record, series in zip(bundle.records, restored.workspace.graphs[0].series, strict=True):
        dataset = restored.workspace.datasets[series.dataset_id]
        np.testing.assert_allclose(dataset.q, record.q)
        np.testing.assert_allclose(dataset.intensity, record.intensity)
    if analysis != "modeling":
        residual = load_result_curve(descriptor, "residuals")
        assert residual.curve.point_count > 0
        assert matches_dataset_filter(residual.curve, f"{analysis}_residuals")


def _modeling(path):
    return next(item for item in discover_results(path) if item.analysis == "modeling")


def test_modeling_bundle_adds_the_primary_measured_curve():
    bundle = load_result_bundle(_modeling(FIXTURE))
    roles = [record.metadata["bernardyn_result"]["role"] for record in bundle.records]
    assert roles == ["measured", "fit", "population_1"]
    measured = bundle.records[0]
    assert measured.metadata["bernardyn_result"]["measured_source"] == "primary_scattering_data"
    assert measured.uncertainty is not None
    assert bundle.styles[0].symbol == "o" and bundle.styles[0].line_style == "none"


def test_modeling_without_primary_data_still_imports_its_model():
    bundle = load_result_bundle(_modeling(RESULT_FIXTURES / "pyirena_1_2_Modeling_PP15.h5"))
    roles = [record.metadata["bernardyn_result"]["role"] for record in bundle.records]
    assert roles == ["fit", "population_1", "population_2"]


def test_modeling_population_volume_distributions_integrate_to_their_volume_fraction():
    from bernardyn.io.results import _result, load_result_curves

    descriptor = _modeling(RESULT_FIXTURES / "pyirena_1_2_Modeling_PP15.h5")
    assert "volume_distribution" in available_curve_kinds(descriptor)
    (bundle,) = load_result_curves(descriptor, "volume_distribution")
    curve = bundle.curve
    assert (curve.x_unit, curve.y_unit) == ("angstrom", "volume_fraction/angstrom")
    scale = _result(descriptor)["populations"][0]["scale"]
    assert np.trapezoid(curve.y, curve.x) == pytest.approx(scale, rel=0.01)


def test_result_reads_are_cached_until_the_file_changes(tmp_path, monkeypatch):
    import os

    from bernardyn.io import results

    source = tmp_path / FIXTURE.name
    copy2(FIXTURE, source)
    reads = []
    original = results._read_result
    monkeypatch.setattr(results, "_read_result", lambda item: reads.append(item) or original(item))
    results.clear_result_cache()
    (descriptor, *_) = discover_results(source)
    available_curve_kinds(descriptor)
    load_result_bundle(descriptor)
    load_result_curve(descriptor, "residuals")
    assert len(reads) == 1
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    load_result_bundle(descriptor)
    assert len(reads) == 2


def test_survey_records_unreadable_files_instead_of_failing(tmp_path):
    from bernardyn.io.result_batch import load_result_batch, survey_results

    broken = tmp_path / "broken.h5"
    broken.write_text("not hdf5")
    survey = survey_results([FIXTURE, broken])
    assert [item.error is not None for item in survey.files] == [False, True]
    batch = load_result_batch(survey, "unified_fit", ("residuals",))
    assert len(batch.curves["residuals"]) == 1
    assert [path.name for path, _ in batch.skipped] == ["broken.h5"]


@pytest.mark.parametrize("loader_reads_residuals", [True, False])
def test_modeling_residuals_are_offered_when_the_file_stores_them(tmp_path, monkeypatch, loader_reads_residuals):
    from pyirena.io import nxcansas_modeling

    if not loader_reads_residuals:
        # Released pyIrena 1.2.0b3 returns no "residuals" key.
        original = nxcansas_modeling.load_modeling_results

        def older_loader(*args, **kwargs):
            result = original(*args, **kwargs)
            if result is not None:
                result.pop("residuals", None)
            return result

        monkeypatch.setattr(nxcansas_modeling, "load_modeling_results", older_loader)
    source = tmp_path / "with-residuals.h5"
    copy2(RESULT_FIXTURES / "pyirena_1_2_Modeling_PP15.h5", source)
    with h5py.File(source, "r+") as handle:
        group = handle["entry/modeling_results"]
        residuals = group.create_dataset("residuals", data=np.linspace(-2.0, 2.0, len(group["model_q"])))
        residuals.attrs["units"] = "dimensionless"
    descriptor = _modeling(source)
    assert "residuals" in available_curve_kinds(descriptor)
    curve = load_result_curve(descriptor, "residuals").curve
    assert (curve.x_unit, curve.y_unit, curve.y.min()) == ("1/angstrom", "dimensionless", -2.0)
    # Files saved before pyIrena stored Modeling residuals simply lack the kind.
    assert "residuals" not in available_curve_kinds(_modeling(RESULT_FIXTURES / "pyirena_1_2_Modeling_PP15.h5"))


@pytest.mark.parametrize("use_pyirena_reader", [True, False])
def test_number_distributions_use_irena_units_for_old_and_new_files(tmp_path, monkeypatch, use_pyirena_reader):
    from pyirena.io import _nxcansas_common

    from bernardyn.io.results import NUMBER_DIST_UNITS, _read_number_dist

    if not use_pyirena_reader:
        monkeypatch.delattr(_nxcansas_common, "read_number_dist", raising=False)
    path = tmp_path / "numbers.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("legacy", data=[1.0, 2.0]).attrs["units"] = "1/angstrom"
        handle.create_dataset("untagged", data=[1.0])
        handle.create_dataset("current", data=[3.0]).attrs["units"] = NUMBER_DIST_UNITS
    with h5py.File(path, "r") as handle:
        np.testing.assert_allclose(_read_number_dist(handle, "legacy"), [1e24, 2e24])
        np.testing.assert_allclose(_read_number_dist(handle, "untagged"), [1e24])
        np.testing.assert_allclose(_read_number_dist(handle, "current"), [3.0])
        assert _read_number_dist(handle, "missing") is None


def test_size_number_distribution_integrates_to_the_volume_based_number_density():
    from bernardyn.io.results import load_result_curve as curve_of

    descriptor = next(item for item in discover_results(FIXTURE) if item.analysis == "size_distribution")
    number = curve_of(descriptor, "number_distribution").curve
    volume = curve_of(descriptor, "volume_distribution").curve
    assert number.y_unit == "1/(cm^3 angstrom)"
    spheres_cm3 = 4 / 3 * np.pi * volume.x**3 * 1e-24
    assert np.trapezoid(number.y, number.x) == pytest.approx(
        np.trapezoid(volume.y / spheres_cm3, volume.x), rel=1e-6
    )
    cumulative = curve_of(descriptor, "cumulative_number_distribution").curve
    assert (cumulative.y_semantic, cumulative.y_unit) == ("cumulative_number_density", "1/cm^3")


def test_modeling_population_number_distribution_is_in_irena_units():
    from bernardyn.io.results import load_result_curves

    (bundle,) = load_result_curves(_modeling(FIXTURE), "number_distribution")
    assert bundle.curve.y_unit == "1/(cm^3 angstrom)"
    assert bundle.graph_title == "Modeling number distribution"
    assert bundle.curve.y.max() > 1e15  # per cm³, not per Å³


def test_modeling_result_curves_have_their_own_browser_categories():
    from bernardyn.gui.dataset_filters import dataset_category_label, result_category
    from bernardyn.io.results import load_result_curves

    descriptor = _modeling(FIXTURE)
    bundle = load_result_bundle(descriptor)
    categories = [result_category(record.to_dataset()) for record in bundle.records]
    assert categories == ["modeling_measured", "modeling_fit", "modeling_populations"]
    (volume,) = load_result_curves(descriptor, "volume_distribution")
    (number,) = load_result_curves(descriptor, "number_distribution")
    assert dataset_category_label(volume.curve) == "Modeling volume distribution"
    assert dataset_category_label(number.curve) == "Modeling number distribution"
