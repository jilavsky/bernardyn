from dataclasses import replace
from pathlib import Path

import pytest

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import Dataset, GenericCurve
from bernardyn.core.units import axis_label, format_unit, units_equivalent
from bernardyn.io.results import discover_results, load_result_bundle

FIXTURES = Path(__file__).parents[1] / "testData"


@pytest.mark.parametrize(
    ("unit", "shown"),
    [
        ("1/angstrom", "Å⁻¹"),
        ("1/A", "Å⁻¹"),
        ("angstrom^-1", "Å⁻¹"),
        ("1/cm", "cm⁻¹"),
        ("[cm2/cm3]", "cm⁻¹"),
        ("arb", "arb. units"),
        ("dimensionless", ""),
        ("(1/angstrom)⁴", "Å⁻⁴"),
        ("1/cm·(1/angstrom)²", "cm⁻¹·Å⁻²"),
        ("[cm2/cm3]·(1/angstrom)²", "cm⁻¹·Å⁻²"),
        ("1/(1/cm)", "cm"),
        ("volume_fraction/angstrom", "vol. fraction·Å⁻¹"),
        ("1/(cm^3 angstrom)", "cm⁻³·Å⁻¹"),
        ("1 / cm", "cm⁻¹"),
        # Unrecognised units are shown as written, never reinterpreted.
        ("counts/s/pixel", "counts/s/pixel"),
    ],
)
def test_format_unit(unit, shown):
    assert format_unit(unit) == shown


def test_axis_label_omits_brackets_for_dimensionless_quantities():
    assert axis_label("q", "1/angstrom") == "q [Å⁻¹]"
    assert axis_label("Normalised residual", "dimensionless") == "Normalised residual"


def test_units_equivalent_ignores_spelling_but_not_scale():
    assert units_equivalent("1/A", "1/angstrom")
    assert units_equivalent("cm2/cm3", "1/cm")
    assert not units_equivalent("arb", "1/cm")
    assert not units_equivalent("1/nm", "1/angstrom")


def _dataset(label="sample", intensity_unit="1/cm"):
    return Dataset(q=[0.01, 0.02, 0.03], intensity=[3.0, 2.0, 1.0], label=label, intensity_unit=intensity_unit)


def test_every_view_keeps_units_in_axis_labels():
    controller = ApplicationController()
    graph_id = controller.workspace.active_graph_id
    controller.add_dataset(_dataset(), graph_id=graph_id)
    controller.set_transform(graph_id, "kratky")
    graph = controller.workspace.graph(graph_id)
    assert (graph.x_axis.label, graph.y_axis.label) == ("q [Å⁻¹]", "Intensity·q² [cm⁻¹·Å⁻²]")
    controller.set_transform(graph_id, "raw")
    graph = controller.workspace.graph(graph_id)
    assert (graph.x_axis.label, graph.y_axis.label) == ("q [Å⁻¹]", "Intensity [cm⁻¹]")


def test_view_chosen_before_data_is_labelled_with_default_units():
    controller = ApplicationController()
    graph_id = controller.workspace.active_graph_id
    controller.set_transform(graph_id, "porod")
    graph = controller.workspace.graph(graph_id)
    assert (graph.x_axis.label, graph.y_axis.label) == ("q⁴ [Å⁻⁴]", "Intensity·q⁴ [cm⁻¹·Å⁻⁴]")


def test_first_curve_relabels_an_empty_graph_with_its_own_units():
    controller = ApplicationController()
    graph_id = controller.workspace.active_graph_id
    controller.add_dataset(_dataset(intensity_unit="arb"), graph_id=graph_id)
    assert controller.workspace.graph(graph_id).y_axis.label == "Intensity [arb. units]"


def test_first_curve_does_not_replace_a_user_label():
    controller = ApplicationController()
    graph = controller.workspace.graphs[0]
    custom = replace(graph, y_axis=replace(graph.y_axis, label="Scattered intensity (a.u.)"))
    controller.update_graph(custom)
    controller.add_dataset(_dataset(intensity_unit="arb"), graph_id=graph.id)
    assert controller.workspace.graph(graph.id).y_axis.label == "Scattered intensity (a.u.)"


def test_generic_curve_relabels_an_empty_graph():
    controller = ApplicationController()
    graph_id = controller.workspace.active_graph_id
    curve = GenericCurve(
        x=[10.0, 20.0], y=[0.1, 0.2], x_label="Radius", y_label="Volume fraction density",
        x_unit="angstrom", y_unit="volume_fraction/angstrom",
        x_semantic="particle_radius", y_semantic="volume_fraction_density_per_radius",
    )
    controller.add_dataset(curve, graph_id=graph_id)
    graph = controller.workspace.graph(graph_id)
    assert (graph.x_axis.label, graph.y_axis.label) == (
        "Radius [Å]", "Volume fraction density [vol. fraction·Å⁻¹]"
    )


def test_mixed_intensity_units_are_reported_but_allowed():
    controller = ApplicationController()
    graph_id = controller.workspace.active_graph_id
    controller.add_datasets(
        (_dataset("absolute"), _dataset("relative", "arb"), _dataset("same", "cm2/cm3")),
        graph_id=graph_id,
    )
    warnings = controller.graph_warnings(graph_id)
    assert len(warnings) == 1
    assert "relative" in warnings[0] and "arb. units vs cm⁻¹" in warnings[0]


def test_simple_fits_model_takes_the_measured_data_units():
    (descriptor,) = discover_results(FIXTURES / "pyirena_1_2_SimpleFits_Porod.h5")
    bundle = load_result_bundle(descriptor)
    units = {
        record.metadata["bernardyn_result"]["role"]: (
            record.intensity_unit, record.metadata["bernardyn_result"]["intensity_unit_source"]
        )
        for record in bundle.records
    }
    # The file labels I_model "arb", but it was fitted to absolute data.
    assert units == {"measured": ("1/cm", "file"), "fit": ("1/cm", "measured_data")}


def test_waxs_curves_keep_their_stored_arbitrary_units():
    (descriptor,) = discover_results(FIXTURES / "pyirena_1_2_WAXS_Al_7075.h5")
    bundle = load_result_bundle(descriptor)
    assert {record.intensity_unit for record in bundle.records} == {"arb"}
