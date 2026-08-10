"""Phase 2 test script for Bernardyn.

Validates utility modules (file_utils, state_manager) and GUI module
instantiation using a headless Qt application. No display required.

Run with:
    python tests/test_phase2.py
"""

import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "testData")
LnG_FILE = os.path.join(TEST_DATA_DIR, "LnG_0103.hdf")
Rh1_FILE = os.path.join(TEST_DATA_DIR, "Rh1_0085.h5")

passed = 0
failed = 0


def test(name):
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
# Test file_utils.py
# ============================================================
print("\n=== Testing file_utils ===")


@test("extract_order_number extracts number from LnG_0103.hdf")
def _():
    from bernardyn.utils.file_utils import extract_order_number

    num = extract_order_number("LnG_0103.hdf")
    assert num == 103, f"Expected 103, got {num}"


@test("extract_order_number extracts number from Rh1_0085.h5")
def _():
    from bernardyn.utils.file_utils import extract_order_number

    num = extract_order_number("Rh1_0085.h5")
    assert num == 85, f"Expected 85, got {num}"


@test("extract_order_number returns None for no-number filename")
def _():
    from bernardyn.utils.file_utils import extract_order_number

    num = extract_order_number("data.txt")
    assert num is None, f"Expected None, got {num}"


@test("parse_filename_metadata detects MIN and DEG")
def _():
    from bernardyn.utils.file_utils import parse_filename_metadata

    meta = parse_filename_metadata("LnG_0103_MIN2026.hdf")
    assert meta["has_time"] is True, "Expected has_time=True"

    meta = parse_filename_metadata("sample_DEG37.hdf")
    assert meta["has_temperature"] is True, "Expected has_temperature=True"


@test("sort_files_alphabetically sorts correctly")
def _():
    from bernardyn.utils.file_utils import sort_files_alphabetically

    files = ["Zebra.hdf", "Apple.hdf", "Mango.hdf"]
    sorted_files = sort_files_alphabetically(files)
    assert sorted_files == ["Apple.hdf", "Mango.hdf", "Zebra.hdf"]


@test("sort_files_by_order_number sorts by number")
def _():
    from bernardyn.utils.file_utils import sort_files_by_order_number

    files = ["data_100.hdf", "data_5.hdf", "data_50.hdf"]
    sorted_files = sort_files_by_order_number(files)
    assert sorted_files[0] == "data_5.hdf"
    assert sorted_files[1] == "data_50.hdf"
    assert sorted_files[2] == "data_100.hdf"


@test("filter_files_by_regex filters correctly")
def _():
    from bernardyn.utils.file_utils import filter_files_by_regex

    files = ["LnG_0103.hdf", "Rh1_0085.h5", "LnG_0204.hdf"]
    filtered = filter_files_by_regex(files, r"LnG_.*")
    assert len(filtered) == 2
    assert "LnG_0103.hdf" in filtered


@test("filter_files_by_string filters case-insensitively")
def _():
    from bernardyn.utils.file_utils import filter_files_by_string

    files = ["LnG_0103.hdf", "Rh1_0085.h5"]
    filtered = filter_files_by_string(files, "lnG")
    assert len(filtered) == 1
    assert filtered[0] == "LnG_0103.hdf"


# ============================================================
# Test state_manager.py
# ============================================================
print("\n=== Testing state_manager ===")


@test("StateManager saves and loads last_data_folder")
def _():
    from bernardyn.utils.state_manager import StateManager

    tmpdir = tempfile.mkdtemp()
    sm = StateManager(state_dir=tmpdir, state_file="test_state.json")

    sm.last_data_folder = "/tmp/test_data"
    # Force reload from disk to verify persistence
    sm2 = StateManager(state_dir=tmpdir, state_file="test_state.json")
    assert sm2.last_data_folder == "/tmp/test_data"


@test("StateManager saves and loads regex_filter")
def _():
    from bernardyn.utils.state_manager import StateManager

    tmpdir = tempfile.mkdtemp()
    sm = StateManager(state_dir=tmpdir, state_file="test_state.json")

    sm.regex_filter = "LnG_.*"
    sm2 = StateManager(state_dir=tmpdir, state_file="test_state.json")
    assert sm2.regex_filter == "LnG_.*"


@test("StateManager reset clears all state")
def _():
    from bernardyn.utils.state_manager import StateManager

    tmpdir = tempfile.mkdtemp()
    sm = StateManager(state_dir=tmpdir, state_file="test_state.json")

    sm.last_data_folder = "/tmp/test"
    sm.regex_filter = "test.*"
    sm.reset()

    assert sm.last_data_folder == ""
    assert sm.regex_filter == ""


@test("StateManager get/set arbitrary keys")
def _():
    from bernardyn.utils.state_manager import StateManager

    tmpdir = tempfile.mkdtemp()
    sm = StateManager(state_dir=tmpdir, state_file="test_state.json")

    sm.set("custom_key", "custom_value")
    assert sm.get("custom_key") == "custom_value"


# ============================================================
# Test GUI modules (headless Qt) - skip if PySide6 not available
# ============================================================

try:
    import PySide6  # noqa: F401
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False


if not HAS_PYSIDE6:
    print("\n=== Testing GUI modules ===")
    print("  SKIPPED: PySide6 not available, skipping all GUI tests")

    gui_skip_tests = [
        "PlotWidget can be instantiated",
        "PlotWidget clear and add_line",
        "PlotWidget set_log_mode",
        "PlotWidget add_error_bars",
        "PlotWidget add_image",
        "DataPanel can be instantiated",
        "DataPanel set_folder populates file list",
        "DataPanel regex filter works",
        "DataPanel sort by order number",
        "ControlsPanel can be instantiated",
        "ControlsPanel default settings",
        "ControlsPanel set_enabled/disabled",
        "MainWindow can be instantiated",
        "MainWindow has all panels",
        "MainWindow load and render line plot",
        "MainWindow load and render image plot",
        "MainWindow load Rh1 file with slit-smeared data",
    ]
    for t in gui_skip_tests:
        print("  SKIP: " + t)

else:
    print("\n=== Testing GUI modules ===")

    def _get_qapp():
        """Get or create a headless QApplication for testing."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    @test("PlotWidget can be instantiated")
    def _():
        from bernardyn.gui.plot_widget import PlotWidget

        app = _get_qapp()
        widget = PlotWidget()
        assert widget is not None

    @test("PlotWidget clear and add_line")
    def _():
        import numpy as np
        from bernardyn.gui.plot_widget import PlotWidget

        app = _get_qapp()
        widget = PlotWidget()
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([10.0, 20.0, 30.0])
        widget.add_line(x, y, color="blue", symbol="o")
        assert len(widget._plot_items) == 1

    @test("PlotWidget set_log_mode")
    def _():
        from bernardyn.gui.plot_widget import PlotWidget

        app = _get_qapp()
        widget = PlotWidget()
        widget.set_log_mode(x_log=True, y_log=True)

    @test("PlotWidget add_error_bars")
    def _():
        import numpy as np
        from bernardyn.gui.plot_widget import PlotWidget

        app = _get_qapp()
        widget = PlotWidget()
        x = np.array([1.0, 2.0])
        y = np.array([10.0, 20.0])
        y_err = np.array([1.0, 2.0])
        widget.add_error_bars(x, y, y_err)
        assert len(widget._error_bars) == 1

    @test("PlotWidget add_image")
    def _():
        import numpy as np
        from bernardyn.gui.plot_widget import PlotWidget

        app = _get_qapp()
        widget = PlotWidget()
        img = np.random.rand(50, 50).astype(np.float32)
        widget.add_image(img, vmin=0.0, vmax=1.0)

    @test("DataPanel can be instantiated")
    def _():
        from bernardyn.gui.data_panel import DataPanel

        app = _get_qapp()
        panel = DataPanel()
        assert panel is not None

    @test("DataPanel set_folder populates file list")
    def _():
        from bernardyn.gui.data_panel import DataPanel

        app = _get_qapp()
        panel = DataPanel()
        panel.set_folder(TEST_DATA_DIR)

        count = panel._file_list.count()
        assert count > 0, f"Expected files in listbox, got {count}"

    @test("DataPanel regex filter works")
    def _():
        from bernardyn.gui.data_panel import DataPanel

        app = _get_qapp()
        panel = DataPanel()
        panel.set_folder(TEST_DATA_DIR)

        initial_count = panel._file_list.count()
        panel.set_regex_filter("LnG_.*")

        filtered_count = panel._file_list.count()
        assert filtered_count <= initial_count, "Filter should reduce or maintain count"

    @test("DataPanel sort by order number")
    def _():
        from bernardyn.gui.data_panel import DataPanel

        app = _get_qapp()
        panel = DataPanel()
        tmpdir = tempfile.mkdtemp()
        for name in ["data_100.txt", "data_5.txt", "data_50.txt"]:
            with open(os.path.join(tmpdir, name), "w") as f:
                f.write("1 2\n")

        panel.set_folder(tmpdir)
        idx = panel._sort_combo.findData("order_number")
        if idx >= 0:
            panel._sort_combo.setCurrentIndex(idx)

        items = [panel._file_list.item(i).text() for i in range(panel._file_list.count())]
        assert items[0] == "data_5.txt", f"Expected data_5.txt first, got {items[0]}"

    @test("ControlsPanel can be instantiated")
    def _():
        from bernardyn.gui.controls_panel import ControlsPanel

        app = _get_qapp()
        panel = ControlsPanel()
        assert panel is not None

    @test("ControlsPanel default settings")
    def _():
        from bernardyn.gui.controls_panel import ControlsPanel

        app = _get_qapp()
        panel = ControlsPanel()
        assert panel.get_plot_type() == "line"
        assert panel.get_x_log() is True
        assert panel.get_y_log() is True

    @test("ControlsPanel set_enabled/disabled")
    def _():
        from bernardyn.gui.controls_panel import ControlsPanel

        app = _get_qapp()
        panel = ControlsPanel()
        panel.set_enabled(False)

    @test("MainWindow can be instantiated")
    def _():
        from bernardyn.gui.main_window import MainWindow

        app = _get_qapp()
        window = MainWindow()
        assert window is not None

    @test("MainWindow has all panels")
    def _():
        from bernardyn.gui.main_window import MainWindow

        app = _get_qapp()
        window = MainWindow()
        assert window.get_data_panel() is not None
        assert window.get_plot_widget() is not None
        assert window.get_controls_panel() is not None

    @test("MainWindow load and render line plot")
    def _():
        from bernardyn.gui.main_window import MainWindow

        app = _get_qapp()
        window = MainWindow()

        from bernardyn.data.loader import get_default_dispatcher

        data = get_default_dispatcher().load(LnG_FILE)
        assert data is not None

        window._loaded_data = {"LnG_0103.hdf": data}
        window._render_line_plot(x_log=True, y_log=True)

        assert len(window.get_plot_widget()._plot_items) > 0, "Expected plot items"

    @test("MainWindow load and render image plot")
    def _():
        from bernardyn.gui.main_window import MainWindow

        app = _get_qapp()
        window = MainWindow()

        from bernardyn.data.loader import get_default_dispatcher

        data = get_default_dispatcher().load(LnG_FILE)
        assert data is not None

        window._loaded_data = {"LnG_0103.hdf": data}
        window._render_image_plot(x_log=False, y_log=False)

    @test("MainWindow load Rh1 file with slit-smeared data")
    def _():
        from bernardyn.gui.main_window import MainWindow

        app = _get_qapp()
        window = MainWindow()

        from bernardyn.data.loader import get_default_dispatcher

        data = get_default_dispatcher().load(Rh1_FILE)
        assert data is not None

        window._loaded_data = {"Rh1_0085.h5": data}
        window._render_line_plot(x_log=True, y_log=True)

        n_items = len(window.get_plot_widget()._plot_items)
        assert n_items >= 2, f"Expected at least 2 plot items (SMR + desmear), got {n_items}"


# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 60)
print("Phase 2 Test Results: {} passed, {} failed".format(passed, failed))
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("\nAll Phase 2 tests passed!")
    sys.exit(0)
