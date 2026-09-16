import asyncio
from pathlib import Path
from shutil import copy2

import pytest

from bernardyn.mcp import tools
from bernardyn.mcp.paths import PathSecurityError, output_path

FIXTURE = Path(__file__).parents[1] / "testData" / "Al_Mg_Si__40C_0min_0498.h5"


def test_mcp_surface_stays_at_five_grouped_tools():
    assert tools.TOOL_GROUPS == {
        "discovery": ("bernardyn_inspect_data", "bernardyn_list_plot_recipes"),
        "create": ("bernardyn_create_plot",),
        "package": ("bernardyn_describe_package", "bernardyn_export_plot"),
    }


def test_fastmcp_server_registers_only_the_five_public_tools():
    pytest.importorskip("mcp.server.fastmcp")
    from bernardyn.mcp.server import mcp

    assert [item.name for item in asyncio.run(mcp.list_tools())] == [
        "bernardyn_inspect_data",
        "bernardyn_list_plot_recipes",
        "bernardyn_create_plot",
        "bernardyn_describe_package",
        "bernardyn_export_plot",
    ]


def test_mcp_creates_describes_and_exports_result_artifacts(qapp, tmp_path, monkeypatch):
    source = tmp_path / FIXTURE.name
    copy2(FIXTURE, source)
    output = tmp_path / "artifacts"
    monkeypatch.setenv("BERNARDYN_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("BERNARDYN_OUTPUT_ROOT", str(output))

    inspected = tools.inspect_data(source.name)
    assert any(item["analysis"] == "unified_fit" for item in inspected["results"])
    created = tools.create_plot_artifact(
        "unified_fit_residuals",
        result_path=source.name,
        output_name="residuals",
        width_px=640,
        height_px=480,
        dpi=100,
    )
    package = Path(created["package_path"])
    preview = Path(created["preview_path"])
    assert package.is_file() and preview.is_file()
    assert created["diagnostics"]["masked_points"] == 0

    description = tools.describe_package(str(package))
    graph = description["graphs"][0]
    assert graph["recipe"] == {"id": "unified_fit_residuals", "version": "1"}
    assert graph["series"][0]["y_semantic"] == "normalised_residual"

    exported = tools.export_plot(
        str(package), graph["id"], output_name="residuals-copy", image_format="svg", width_px=500
    )
    assert Path(exported["path"]).is_file()
    assert exported["width_px"] == 500


def test_mcp_rejects_output_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("BERNARDYN_OUTPUT_ROOT", str(tmp_path / "out"))
    with pytest.raises(PathSecurityError, match="simple filename"):
        output_path("../outside", ".png")
