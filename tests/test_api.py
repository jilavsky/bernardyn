from pathlib import Path

import numpy as np

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
