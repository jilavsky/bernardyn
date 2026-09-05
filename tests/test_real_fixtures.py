import shutil
from pathlib import Path

from bernardyn.core.controller import ApplicationController


def test_real_pyirena_hdf_fixture_reopens_after_source_deletion(tmp_path):
    fixture = Path(__file__).parents[1] / "testData" / "Rh1_0085.h5"
    source = tmp_path / fixture.name
    shutil.copy2(fixture, source)
    controller = ApplicationController()
    locations = controller.sources.discover_path(source)
    assert len(locations) == 2
    for location in locations:
        controller.load_location(location)
    expected_lengths = sorted(len(dataset.q) for dataset in controller.workspace.datasets.values())
    package = controller.save(tmp_path / "portable-workspace")
    source.unlink()

    restored = ApplicationController()
    restored.open_package(package)
    assert sorted(len(dataset.q) for dataset in restored.workspace.datasets.values()) == expected_lengths
    assert len(restored.workspace.graphs[0].series) == 2
    assert not any(
        Path(dataset.provenance.get("source_path", "")).exists()
        for dataset in restored.workspace.datasets.values()
    )
