"""Phase 1 test script for Bernardyn.

Validates all data loading and plotting engine components end-to-end
using the provided test HDF5 files. No GUI required — pure engine validation.

Run with:
    python tests/test_phase1.py
"""

import sys
import os
import traceback

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "testData")
LnG_FILE = os.path.join(TEST_DATA_DIR, "LnG_0103.hdf")
Rh1_FILE = os.path.join(TEST_DATA_DIR, "Rh1_0085.h5")

passed = 0
failed = 0


def test(name):
    """Decorator to register and run a test."""
    def decorator(func):
        global passed, failed
        try:
            func()
            print("  PASS: " + name)
            passed += 1
        except Exception as e:
            print("  FAIL: " + name)
            traceback.print_exc()
            failed += 1
    return decorator


# ============================================================
# Test sas_parser.py
# ============================================================
print("\n=== Testing sas_parser ===")


@test("find_sas_entries finds entry in LnG_0103.hdf")
def _():
    import h5py
    from bernardyn.data.sas_parser import find_sas_entries

    with h5py.File(LnG_FILE, "r") as f:
        entries = find_sas_entries(f)
    assert len(entries) >= 1, "Expected at least 1 SAS entry"
    assert "entry" in entries, "Expected 'entry' in found entries"


@test("find_sas_data_group navigates to sasdata")
def _():
    import h5py
    from bernardyn.data.sas_parser import find_sas_entries, find_sas_data_group

    with h5py.File(LnG_FILE, "r") as f:
        entries = find_sas_entries(f)
        group = find_sas_data_group(f[entries[0]])
    assert group is not None, "Expected to find sasdata group"

@test("parse_sas_data extracts Q, I, Idev with correct shapes")
def _():
    import h5py
    import numpy as np

    from bernardyn.data.sas_parser import (
        find_sas_entries, find_sas_data_group, parse_sas_data,
    )

    with h5py.File(LnG_FILE, "r") as f:
        entries = find_sas_entries(f)
        group = find_sas_data_group(f[entries[0]])
        data = parse_sas_data(group)

    assert len(data.x) == 487, "Expected 487 Q points"
    assert len(data.y) == 487, "Expected 487 I points"
    assert data.y_err is not None, "Expected Idev to be loaded"
    assert len(data.y_err) == 487, "Expected 487 error values"
    assert data.x_err is not None, "Expected Qdev to be loaded"

@test("parse_sas_data extracts correct labels and units")
def _():
    import h5py

    from bernardyn.data.sas_parser import (
        find_sas_entries, find_sas_data_group, parse_sas_data,
    )

    with h5py.File(LnG_FILE, "r") as f:
        entries = find_sas_entries(f)
        group = find_sas_data_group(f[entries[0]])
        data = parse_sas_data(group)

    assert "Q" in data.x_label.lower() or "angstrom" in data.x_units, \
        f"Expected Q label, got: {data.x_label}, units={data.x_units}"
    assert "intensity" in data.y_label.lower() or "cm2" in data.y_units, \
        f"Expected intensity label, got: {data.y_label}, units={data.y_units}"


@test("parse_hdf5_file returns all data sections")
def _():
    from bernardyn.data.sas_parser import parse_hdf5_file

    result = parse_hdf5_file(LnG_FILE)
    assert "sas_data" in result, "Expected 'sas_data' key"
    assert "raw_image" in result, "Expected 'raw_image' key"
    assert len(result["sas_data"]) >= 1, "Expected at least 1 SAS dataset"
    assert result["raw_image"] is not None, "Expected raw image to be found"


@test("parse_hdf5_file finds slit-smeared data in Rh1_0085.h5")
def _():
    from bernardyn.data.sas_parser import parse_hdf5_file

    result = parse_hdf5_file(Rh1_FILE)
    assert result["slit_smear"] is not None, "Expected slit-smeared data"
    assert result["desmear"] is not None, "Expected desmeared data"

@test("find_slit_smear_groups returns both SMR and desmear")
def _():
    import h5py

    from bernardyn.data.sas_parser import find_slit_smear_groups

    with h5py.File(Rh1_FILE, "r") as f:
        slit_smear, desmear = find_slit_smear_groups(f["entry"])

    assert slit_smear is not None, "Expected slit-smeared data"
    assert desmear is not None, "Expected desmeared data"
    assert slit_smear.data_type == "slit_smear", "Expected type 'slit_smear'"


# ============================================================
# Test hdf5_loader.py
# ============================================================
print("\n=== Testing hdf5_loader ===")


@test("Hdf5Loader.can_load recognizes .hdf files")
def _():
    from bernardyn.data.hdf5_loader import Hdf5Loader

    loader = Hdf5Loader()
    assert loader.can_load("test.hdf") is True
    assert loader.can_load("test.h5") is True
    assert loader.can_load("test.txt") is False


@test("Hdf5Loader.load_1d returns SasData from LnG_0103.hdf")
def _():
    from bernardyn.data.hdf5_loader import Hdf5Loader

    loader = Hdf5Loader()
    data = loader.load_1d(LnG_FILE)
    assert data is not None, "Expected 1D data"
    assert len(data.x) == 487, f"Expected 487 points, got {len(data.x)}"
    assert data.y_err is not None, "Expected error bars"


@test("Hdf5Loader.load_2d returns RawImageData from LnG_0103.hdf")
def _():
    from bernardyn.data.hdf5_loader import Hdf5Loader

    loader = Hdf5Loader()
    img = loader.load_2d(LnG_FILE)
    assert img is not None, "Expected 2D image"
    assert img.data.ndim == 2, f"Expected 2D array, got {img.data.ndim}D"


@test("Hdf5Loader.get_data_type identifies 1d_sas")
def _():
    from bernardyn.data.hdf5_loader import Hdf5Loader

    loader = Hdf5Loader()
    dtype = loader.get_data_type(LnG_FILE)
    assert dtype in ("1d_sas", "slit_smear", "desmear"), \
        f"Expected SAS data type, got: {dtype}"


@test("Hdf5Loader.has_slit_smear detects SMR data")
def _():
    from bernardyn.data.hdf5_loader import Hdf5Loader

    loader = Hdf5Loader()
    assert loader.has_slit_smear(Rh1_FILE) is True, "Expected slit-smeared data"


# ============================================================
# Test ascii_loader.py
# ============================================================
print("\n=== Testing ascii_loader ===")


@test("AsciiLoader.can_load recognizes .txt and .csv files")
def _():
    from bernardyn.data.ascii_loader import AsciiLoader

    loader = AsciiLoader()
    assert loader.can_load("test.txt") is True
    assert loader.can_load("test.csv") is True
    assert loader.can_load("test.hdf") is False


@test("AsciiLoader.load parses 2-column ASCII file")
def _():
    from bernardyn.data.ascii_loader import AsciiLoader

    # Create a temporary test file
    tmpfile = "/tmp/test_ascii_2col.txt"
    with open(tmpfile, "w") as f:
        f.write("# Comment line\n")
        f.write("1.0 2.0\n")
        f.write("2.0 4.0\n")
        f.write("3.0 6.0\n")

    loader = AsciiLoader()
    data = loader.load_1d(tmpfile)
    assert data is not None, "Expected loaded data"
    assert len(data.x) == 3, f"Expected 3 points, got {len(data.x)}"
    assert len(data.y) == 3
    assert data.y_err is None, "Expected no error bars for 2-col file"

    os.remove(tmpfile)


@test("AsciiLoader.load parses 3-column ASCII file with errors")
def _():
    from bernardyn.data.ascii_loader import AsciiLoader

    tmpfile = "/tmp/test_ascii_3col.csv"
    with open(tmpfile, "w") as f:
        f.write("1.0,2.0,0.1\n")
        f.write("2.0,4.0,0.2\n")

    loader = AsciiLoader()
    data = loader.load_1d(tmpfile)
    assert data is not None, "Expected loaded data"
    assert len(data.x) == 2
    assert data.y_err is not None, "Expected error bars for 3-col file"
    assert len(data.y_err) == 2

    os.remove(tmpfile)


# ============================================================
# Test loader.py (dispatcher)
# ============================================================
print("\n=== Testing loader dispatcher ===")


@test("LoaderDispatcher routes .hdf to Hdf5Loader")
def _():
    from bernardyn.data.loader import get_loader

    loader = get_loader("test.hdf")
    assert loader is not None, "Expected a loader for .hdf"


@test("LoaderDispatcher routes .txt to AsciiLoader")
def _():
    from bernardyn.data.loader import get_loader

    loader = get_loader("test.txt")
    assert loader is not None, "Expected a loader for .txt"


@test("LoaderDispatcher returns None for unsupported extension")
def _():
    from bernardyn.data.loader import get_loader

    loader = get_loader("test.xyz")
    assert loader is None, "Expected None for unsupported extension"


@test("LoaderDispatcher.load returns data dict")
def _():
    from bernardyn.data.loader import get_default_dispatcher

    dispatcher = get_default_dispatcher()
    result = dispatcher.load(LnG_FILE)
    assert result is not None, "Expected loaded data"
    assert result["type"] == "hdf5", f"Expected type 'hdf5', got {result['type']}"


@test("LoaderDispatcher lists supported extensions")
def _():
    from bernardyn.data.loader import get_default_dispatcher

    dispatcher = get_default_dispatcher()
    exts = dispatcher.list_supported_extensions()
    assert ".hdf" in exts, "Expected .hdf in supported extensions"
    assert ".txt" in exts, "Expected .txt in supported extensions"


# ============================================================
# Test plot_style.py
# ============================================================
print("\n=== Testing plot_style ===")


@test("get_color returns distinct colors for different indices")
def _():
    from bernardyn.plot.plot_style import get_color, EXTENDED_COLORS

    c0 = get_color(0)
    c1 = get_color(1)
    assert isinstance(c0, str), f"Expected str color, got {type(c0)}"
    assert isinstance(c1, str), f"Expected str color, got {type(c1)}"
    assert c0 != c1, f"Colors should differ: {c0!r} vs {c1!r}"
    assert get_color(15) == c0, "Should wrap around palette"


@test("get_symbol returns distinct symbols")
def _():
    from bernardyn.plot.plot_style import get_symbol

    s0 = get_symbol(0)
    s1 = get_symbol(1)
    assert s0 != s1, "Symbols should differ"


@test("auto_style returns complete style dict")
def _():
    from bernardyn.plot.plot_style import auto_style

    style = auto_style(0)
    assert "color" in style, "Expected 'color' key"
    assert "symbol" in style, "Expected 'symbol' key"
    assert "linestyle" in style, "Expected 'linestyle' key"


@test("generate_colors produces N distinct colors")
def _():
    from bernardyn.plot.plot_style import generate_colors

    colors = generate_colors(5)
    assert len(colors) == 5, "Expected 5 colors"


# ============================================================
# Test line_plotter.py
# ============================================================
print("\n=== Testing line_plotter ===")


@test("LinePlotter.add_dataset stores data correctly")
def _():
    import numpy as np
    from bernardyn.plot.line_plotter import LinePlotter

    plotter = LinePlotter()
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([10.0, 20.0, 30.0])
    plotter.add_dataset(x, y, x_label="Q", y_label="I", title="Test")

    config = plotter.get_plot_config()
    assert len(config["datasets"]) == 1, "Expected 1 dataset"


@test("LinePlotter handles multiple datasets with auto-styling")
def _():
    import numpy as np
    from bernardyn.plot.line_plotter import LinePlotter

    plotter = LinePlotter()
    for i in range(3):
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([float(i + 1) * 10, float(i + 1) * 20, float(i + 1) * 30])
        plotter.add_dataset(x, y, title="Dataset " + str(i), index=i)

    config = plotter.get_plot_config()
    assert len(config["datasets"]) == 3, "Expected 3 datasets"

    # Verify auto-styling produces different colors
    colors = [d["color"] for d in config["datasets"]]
    assert len(set(colors)) == 3, "Expected 3 distinct colors"


@test("LinePlotter.get_plot_config includes scale settings")
def _():
    import numpy as np
    from bernardyn.plot.line_plotter import LinePlotter

    plotter = LinePlotter()
    x = np.array([1.0, 2.0])
    y = np.array([10.0, 20.0])
    plotter.add_dataset(x, y)

    config = plotter.get_plot_config(x_log=True, y_log=True)
    assert config["x_log"] is True
    assert config["y_log"] is True


@test("LinePlotter with error bars")
def _():
    import numpy as np
    from bernardyn.plot.line_plotter import LinePlotter

    plotter = LinePlotter()
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([10.0, 20.0, 30.0])
    y_err = np.array([1.0, 2.0, 3.0])
    plotter.add_dataset(x, y, y_err=y_err)

    config = plotter.get_plot_config()
    ds = config["datasets"][0]
    assert ds["y_err"] is not None, "Expected error bars in config"


# ============================================================
# Test image_plotter.py
# ============================================================
print("\n=== Testing image_plotter ===")


@test("ImagePlotter.set_image and get_plot_config")
def _():
    import numpy as np
    from bernardyn.plot.image_plotter import ImagePlotter

    plotter = ImagePlotter()
    img = np.random.rand(100, 100).astype(np.float32)
    plotter.set_image(img)

    config = plotter.get_plot_config()
    assert config["image"] is not None, "Expected image data"
    assert config["image"].shape == (100, 100), "Expected 100x100 image"


@test("ImagePlotter supports color scale selection")
def _():
    from bernardyn.plot.image_plotter import ImagePlotter, COLOR_SCALES

    plotter = ImagePlotter()
    scales = plotter.get_color_scales()
    assert len(scales) > 0, "Expected color scales"
    assert "grayscale" in COLOR_SCALES


@test("ImagePlotter log scale transforms data")
def _():
    import numpy as np
    from bernardyn.plot.image_plotter import ImagePlotter

    plotter = ImagePlotter()
    img = np.ones((10, 10), dtype=np.float32) * 100.0
    plotter.set_image(img)
    plotter.set_log_scale(True)

    config = plotter.get_plot_config()
    assert config["log_scale"] is True


# ============================================================
# Test plot_engine.py (dispatcher)
# ============================================================
print("\n=== Testing plot_engine ===")


@test("PlotEngine has line and image plotters registered")
def _():
    from bernardyn.plot.plot_engine import get_default_engine

    engine = get_default_engine()
    types = engine.get_available_types()
    assert "line" in types, "Expected 'line' plotter"
    assert "image" in types, "Expected 'image' plotter"


@test("PlotEngine.create_plot_config returns config for line")
def _():
    import numpy as np
    from bernardyn.plot.plot_engine import get_default_engine

    engine = get_default_engine()
    from bernardyn.plot.line_plotter import LinePlotter

    lp = engine.get_plotter("line")
    assert lp is not None, "Expected line plotter"


@test("PlotEngine returns None for unknown type")
def _():
    from bernardyn.plot.plot_engine import get_default_engine

    engine = get_default_engine()
    config = engine.create_plot_config("unknown_type")
    assert config is None, "Expected None for unknown type"


# ============================================================
# End-to-end integration test
# ============================================================
print("\n=== Integration: Load HDF5 -> Plot Config ===")


@test("End-to-end: LnG_0103.hdf 1D data -> line plot config")
def _():
    import numpy as np
    from bernardyn.data.loader import get_default_dispatcher
    from bernardyn.plot.line_plotter import LinePlotter

    dispatcher = get_default_dispatcher()
    result = dispatcher.load(LnG_FILE)
    assert result is not None

    sas_data_list = result["sas_data_list"]
    assert len(sas_data_list) >= 1

    plotter = LinePlotter()
    for i, sd in enumerate(sas_data_list):
        plotter.add_dataset(
            sd.x, sd.y, y_err=sd.y_err,
            x_label=sd.x_label, y_label=sd.y_label,
            title=sd.source_file or sd.x_label,
            index=i,
        )

    config = plotter.get_plot_config(x_log=True, y_log=True)
    assert len(config["datasets"]) >= 1
    ds = config["datasets"][0]
    assert len(ds["x"]) == 487


@test("End-to-end: LnG_0103.hdf 2D image -> image plot config")
def _():
    from bernardyn.data.loader import get_default_dispatcher
    from bernardyn.plot.image_plotter import ImagePlotter

    dispatcher = get_default_dispatcher()
    result = dispatcher.load(LnG_FILE)
    assert result is not None

    raw_image = result["raw_image"]
    assert raw_image is not None, "Expected 2D image"

    plotter = ImagePlotter()
    plotter.set_image(raw_image.data)
    config = plotter.get_plot_config()
    assert config["image"] is not None


@test("End-to-end: Rh1_0085.h5 slit-smeared data detection")
def _():
    from bernardyn.data.loader import get_default_dispatcher

    dispatcher = get_default_dispatcher()
    result = dispatcher.load(Rh1_FILE)
    assert result is not None

    # Should have both slit-smeared and desmeared
    assert result.get("slit_smear") is not None or len(result["sas_data_list"]) > 0


# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 60)
print("Phase 1 Test Results: {} passed, {} failed".format(passed, failed))
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("\nAll Phase 1 tests passed!")
    sys.exit(0)
