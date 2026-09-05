import h5py
import numpy as np

from bernardyn.io.sources import (
    HDF5SourceAdapter,
    ScatteringRecord,
    TextSourceAdapter,
    builtin_sources,
)


def test_text_source_reads_headers_units_and_missing_errors(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text("instrument output\n# q,I,dI\n1,10,1\n2,20\n3,30,-1\n", encoding="utf-8")
    adapter = TextSourceAdapter()
    location = adapter.discover(path)[0]
    record = adapter.load(location, q_unit="1/nm", error_fraction=0.1)
    np.testing.assert_allclose(record.q, [0.1, 0.2, 0.3])
    np.testing.assert_allclose(record.uncertainty, [1, 2, 3])
    assert record.metadata["rows_skipped"] == 1
    assert record.provenance["q_unit_assumed"] == "1/nm"


def test_text_source_preserves_nonpositive_values_for_transform_masking(tmp_path):
    path = tmp_path / "sample.dat"
    path.write_text("0 10\n1 -2\n2 3\n", encoding="utf-8")
    record = TextSourceAdapter().load(TextSourceAdapter().discover(path)[0])
    np.testing.assert_allclose(record.intensity, [10, -2, 3])


def test_hdf5_source_discovers_multiple_groups_and_loads_units(tmp_path):
    path = tmp_path / "multi.h5"
    with h5py.File(path, "w") as handle:
        for name in ("entry/data", "entry/data_SMR"):
            group = handle.create_group(name)
            q = group.create_dataset("Q", data=[0.1, 0.2])
            intensity = group.create_dataset("I", data=[10.0, 5.0])
            group.create_dataset("Idev", data=[1.0, 0.5])
            q.attrs["units"] = "1/angstrom"
            intensity.attrs["units"] = "1/cm"
    locations = HDF5SourceAdapter().discover(path)
    assert len(locations) == 2
    assert {location.variant for location in locations} == {"default", "slit-smeared"}
    record = HDF5SourceAdapter().load(locations[0])
    np.testing.assert_allclose(record.q, [0.1, 0.2])
    assert record.q_unit == "1/angstrom"


def test_record_normalizes_inverse_nanometres_to_inverse_angstroms():
    record = ScatteringRecord(
        q=np.array([1.0, 2.0]),
        intensity=np.array([10.0, 5.0]),
        dq=np.array([0.1, 0.2]),
        q_unit="nm^-1",
    )
    dataset = record.to_dataset()
    np.testing.assert_allclose(dataset.q, [0.1, 0.2])
    np.testing.assert_allclose(dataset.dq, [0.01, 0.02])
    assert dataset.q_unit == "1/angstrom"
    assert dataset.metadata["q_unit_conversion"]["scale"] == 0.1


def test_source_registry_routes_supported_suffixes(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("1 2\n")
    registry = builtin_sources()
    assert registry.adapter_for(path).id == "text"
    assert registry.discover_path(path)[0].path == path.resolve()
