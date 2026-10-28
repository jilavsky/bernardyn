from pathlib import Path

import numpy as np
import pytest

from bernardyn.api import (
    PlotRequest,
    Presentation,
    ResultInput,
    ScatteringInput,
    create_plot,
    inspect_data,
    list_recipes,
)
from bernardyn.cli import main as cli_main
from bernardyn.core.models import GenericCurve, GraphDocument
from bernardyn.io.container import load_package
from bernardyn.template.graph_templates import save_template

DATA = Path(__file__).parents[1] / "testData" / "Rh1_0085.h5"
RESULT = Path(__file__).parents[1] / "testData" / "Al_Mg_Si__40C_0min_0498.h5"
RESULT_FIXTURES = Path(__file__).parents[1] / "testData"


def test_public_recipe_creates_portable_porod_package_and_offscreen_png(qapp, tmp_path):
    package = tmp_path / "porod"
    image = tmp_path / "porod.png"
    result = create_plot(
        PlotRequest(
            recipe_id="porod",
            inputs=(ScatteringInput(DATA),),
            presentation=Presentation(title="API Porod", width_px=640, height_px=480, dpi=100),
            package_path=package,
            image_path=image,
        )
    )
    assert result.package_path is not None and result.package_path.is_file()
    assert image.is_file() and image.stat().st_size > 0
    assert result.graph.title == "API Porod"
    assert result.graph.view_transform_id == "porod"
    assert result.graph.renderer_config["recipe"] == {"id": "porod", "version": "1"}
    assert result.diagnostics.loaded_points > 0
    assert result.diagnostics.plotted_points > 0
    assert (result.diagnostics.width_px, result.diagnostics.height_px, result.diagnostics.dpi) == (640, 480, 100)
    restored = load_package(result.package_path)
    graph = restored.workspace.graphs[0]
    assert graph.view_transform_id == "porod"
    assert restored.snapshots[graph.id]


def test_public_recipe_creates_typed_result_curve_without_qt(tmp_path):
    result = create_plot(
        PlotRequest(
            recipe_id="unified_fit_residuals",
            result=ResultInput(RESULT, "unified_fit"),
            package_path=tmp_path / "residuals",
        )
    )
    dataset = next(iter(result.controller.workspace.datasets.values()))
    assert isinstance(dataset, GenericCurve)
    assert dataset.y_semantic == "normalised_residual"
    assert not result.graph.y_axis.log
    assert np.any(dataset.y < 0)
    assert result.diagnostics.masked_points == 0


def test_public_recipe_keeps_dimensionless_kratky_parameters_per_series(tmp_path):
    result = create_plot(
        PlotRequest(
            recipe_id="dimensionless_kratky",
            inputs=(ScatteringInput(DATA),),
            series_parameters=({"I0": 100.0, "Rg": 12.0},),
            package_path=tmp_path / "dimensionless",
        )
    )
    view = result.graph.series[0]
    assert view.transform_parameters == {"I0": 100.0, "Rg": 12.0}
    assert result.diagnostics.plotted_points > 0


def test_public_recipe_records_a_compatible_template(tmp_path):
    template = save_template(
        tmp_path / "porod-template",
        GraphDocument(title="Template title", view_transform_id="porod"),
        "API Porod template",
    )
    result = create_plot(
        PlotRequest(
            recipe_id="porod",
            inputs=(ScatteringInput(DATA),),
            presentation=Presentation(template_path=template),
            package_path=tmp_path / "templated",
        )
    )
    assert result.graph.renderer_config["template"] == {
        "name": "API Porod template",
        "schema_version": 1,
    }


def test_public_inspection_and_recipe_catalog_are_serializable():
    names = {recipe.id for recipe in list_recipes()}
    assert {
        "raw_iq",
        "porod",
        "unified_fit_residuals",
        "size_distribution_cumulative_surface_distribution",
    }.issubset(names)
    inspected = inspect_data(RESULT)
    assert any(item["analysis"] == "unified_fit" for item in inspected["results"])


@pytest.mark.parametrize(
    ("analysis", "filename"),
    [
        ("modeling", "Modeling_PP15.h5"),
        ("simple_fits", "SimpleFits_Porod.h5"),
        ("waxs_peakfit", "WAXS_Al_7075.h5"),
        ("carbon_fit", "Carbon_CE_1400.h5"),
    ],
)
def test_new_result_recipes_discover_and_create_packages(tmp_path, analysis, filename):
    source = RESULT_FIXTURES / f"pyirena_1_2_{filename}"
    assert any(item["analysis"] == analysis for item in inspect_data(source)["results"])
    result = create_plot(PlotRequest(
        recipe_id=f"{analysis}_data_fit",
        result=ResultInput(source, analysis),
        package_path=tmp_path / analysis,
    ))
    assert result.package_path.is_file()
    assert result.diagnostics.plotted_points > 0
    assert result.graph.x_axis.log is (analysis != "waxs_peakfit")
    assert result.graph.y_axis.log is (analysis != "waxs_peakfit")
    if analysis != "modeling":
        residual = create_plot(PlotRequest(
            recipe_id=f"{analysis}_residuals",
            result=ResultInput(source, analysis),
            package_path=tmp_path / f"{analysis}-residuals",
        ))
        assert residual.package_path.is_file()
        assert not residual.graph.y_axis.log
        assert residual.graph.x_axis.log is (analysis != "waxs_peakfit")


def test_cli_routes_carbon_result_recipe_by_catalog(tmp_path, capsys):
    source = RESULT_FIXTURES / "pyirena_1_2_Carbon_CE_1400.h5"
    assert cli_main([
        "create", "--recipe", "carbon_fit_residuals", "--input", str(source),
        "--package", str(tmp_path / "carbon-residuals"),
    ]) == 0
    assert (tmp_path / "carbon-residuals.bernardyn.h5").is_file()
    assert "graph_id" in capsys.readouterr().out


def test_cli_result_recipe_writes_a_package(tmp_path, capsys):
    destination = tmp_path / "from-cli"
    assert (
        cli_main(
            [
                "create",
                "--recipe",
                "size_distribution_volume_distribution",
                "--input",
                str(RESULT),
                "--package",
                str(destination),
            ]
        )
        == 0
    )
    assert destination.with_name(destination.name + ".bernardyn.h5").is_file()
    assert "graph_id" in capsys.readouterr().out


def test_unsupported_image_suffix_is_rejected_before_any_output(tmp_path):
    request = PlotRequest(
        "raw_iq",
        inputs=(ScatteringInput(DATA),),
        package_path=tmp_path / "graph",
        image_path=tmp_path / "graph.tif",
    )
    with pytest.raises(ValueError, match="image_path"):
        create_plot(request)
    assert list(tmp_path.iterdir()) == []


def test_modeling_volume_distribution_recipe_puts_each_population_on_one_graph(tmp_path):
    result = create_plot(PlotRequest(
        "modeling_volume_distribution",
        result=ResultInput(RESULT_FIXTURES / "pyirena_1_2_Modeling_PP15.h5", "modeling"),
        package_path=tmp_path / "populations",
    ))
    assert len(result.graph.series) == 1
    assert result.graph.y_axis.label == "Volume fraction density [vol. fraction·Å⁻¹]"
    assert load_package(result.package_path).workspace.graphs[0].title == "Modeling volume distribution"


def test_dimensionless_kratky_falls_back_to_each_datasets_own_metadata(tmp_path, monkeypatch):
    from bernardyn.api import PlotService
    from bernardyn.core.models import Dataset

    samples = iter((
        Dataset(q=[0.01, 0.02], intensity=[2.0, 1.0], label="a", metadata={"I0": 2.0, "Rg": 10.0}),
        Dataset(q=[0.01, 0.02], intensity=[4.0, 3.0], label="b", metadata={"I0": 5.0, "Rg": 20.0}),
    ))
    monkeypatch.setattr(PlotService, "_load_scattering", lambda self, controller, selection: next(samples))
    result = create_plot(PlotRequest(
        "dimensionless_kratky",
        inputs=(ScatteringInput(DATA), ScatteringInput(DATA)),
        package_path=tmp_path / "dk",
    ))
    assert [series.transform_parameters for series in result.graph.series] == [
        {"I0": 2.0, "Rg": 10.0}, {"I0": 5.0, "Rg": 20.0},
    ]


def test_series_preset_spans_a_continuous_scale_and_sets_legend_and_ranges(tmp_path):
    from bernardyn.core.colorscales import sample_scale

    result = create_plot(PlotRequest(
        "raw_iq",
        inputs=tuple(ScatteringInput(DATA, label=f"t = {minute} min") for minute in (0, 10, 20)),
        presentation=Presentation(
            series_preset="rainbow", show_legend=False, x_range=(0.002, 0.3), y_range=(1e-2, 1e5)
        ),
        package_path=tmp_path / "series",
    ))
    graph = load_package(result.package_path).workspace.graphs[0]
    assert [view.style.color for view in graph.series] == sample_scale("rainbow", 3)
    assert [view.legend_label for view in graph.series] == ["t = 0 min", "t = 10 min", "t = 20 min"]
    assert not graph.legend.visible
    assert (graph.x_axis.minimum, graph.x_axis.maximum, graph.x_axis.auto_range) == (0.002, 0.3, False)


def test_presentation_rejects_unknown_preset_and_bad_ranges(tmp_path):
    with pytest.raises(ValueError, match="series_preset"):
        Presentation(series_preset="jet")
    with pytest.raises(ValueError, match="min < max"):
        Presentation(x_range=(1.0, 0.1))
    with pytest.raises(ValueError, match="logarithmic"):
        create_plot(PlotRequest(
            "raw_iq",
            inputs=(ScatteringInput(DATA),),
            presentation=Presentation(x_range=(0.0, 0.3)),
            package_path=tmp_path / "bad",
        ))


def test_result_recipe_compares_one_curve_kind_across_files(tmp_path):
    from shutil import copy2

    from bernardyn.core.controller import PALETTE

    second = tmp_path / "second.h5"
    copy2(RESULT, second)
    result = create_plot(PlotRequest(
        "unified_fit_residuals",
        results=(ResultInput(RESULT, "unified_fit"), ResultInput(second, "unified_fit")),
        package_path=tmp_path / "compare",
    ))
    assert [view.style.color for view in result.graph.series] == [PALETTE[0], PALETTE[1]]
    with pytest.raises(ValueError, match="one result file"):
        create_plot(PlotRequest(
            "unified_fit_data_fit",
            results=(ResultInput(RESULT, "unified_fit"), ResultInput(second, "unified_fit")),
            package_path=tmp_path / "fits",
        ))


def test_inspection_lists_the_recipes_each_saved_result_supports():
    (unified,) = [item for item in inspect_data(RESULT)["results"] if item["analysis"] == "unified_fit"]
    assert "residuals" in unified["curve_kinds"]
    assert {"unified_fit_data_fit", "unified_fit_residuals"} <= set(unified["recipes"])


def test_cli_accepts_series_preset_labels_and_several_result_files(tmp_path, capsys):
    assert cli_main([
        "create", "--recipe", "raw_iq", "--input", str(DATA), "--input", str(DATA),
        "--label", "first", "--label", "second", "--series-preset", "bw", "--no-legend",
        "--package", str(tmp_path / "bw"),
    ]) == 0
    graph = load_package(tmp_path / "bw.bernardyn.h5").workspace.graphs[0]
    assert [view.style.line_style for view in graph.series] == ["solid", "dash"]
    assert not graph.legend.visible
    assert cli_main([
        "create", "--recipe", "unified_fit_residuals", "--input", str(RESULT), "--input", str(RESULT),
        "--package", str(tmp_path / "two"),
    ]) == 0
    assert len(load_package(tmp_path / "two.bernardyn.h5").workspace.graphs[0].series) == 2
