"""Main window for Bernardyn.

Wires together the data panel (left), plot widget (center), and
controls panel (right) into a functional GUI. Handles the data
loading pipeline: file selection -> load -> plot display.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QSplitter,
    QMessageBox,
)

from bernardyn.data.loader import get_default_dispatcher
from bernardyn.gui.controls_panel import ControlsPanel
from bernardyn.gui.data_panel import DataPanel
from bernardyn.gui.plot_widget import PlotWidget

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window for Bernardyn.

    Layout:
      - Left dock: DataPanel (file browser, listbox, sort/filter)
      - Center: PlotWidget (pyqtgraph plot display)
      - Right dock: ControlsPanel (plot type, scales, ranges)

    The window wires signals between panels to create a complete
    data loading and plotting pipeline.
    """

    def __init__(self, parent: Optional[Any] = None):
        super().__init__(parent)

        self.setWindowTitle("Bernardyn")
        self.resize(1400, 900)

        # Data loader dispatcher
        self._loader = get_default_dispatcher()

        # Current loaded data (for re-rendering)
        self._loaded_data: Dict[str, Any] = {}

        # Build the UI
        self._setup_ui()
        self._wire_signals()

    def _setup_ui(self) -> None:
        """Build the main window layout."""
        # Central widget with splitter for plot area
        self._plot_widget = PlotWidget()
        self.setCentralWidget(self._plot_widget)

        # Left dock: Data panel
        self._data_panel = DataPanel()
        self._data_dock = QDockWidget("Data Files", self)
        self._data_dock.setWidget(self._data_panel)
        self._data_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._data_dock)

        # Right dock: Controls panel
        self._controls_panel = ControlsPanel()
        self._controls_dock = QDockWidget("Plot Controls", self)
        self._controls_dock.setWidget(self._controls_panel)
        self._controls_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, self._controls_dock)

    def _wire_signals(self) -> None:
        """Connect signals between UI components."""
        # Data panel -> load and plot selected files
        self._data_panel.files_selected.connect(self._on_files_selected)

        # Controls panel -> update plot scales
        self._controls_panel.generate_requested.connect(self._on_generate_plot)

    def _on_files_selected(self, filepaths: List[str]) -> None:
        """Handle file selection from the data panel."""
        if not filepaths:
            return

        # Load all selected files
        self._loaded_data = {}
        for filepath in filepaths:
            try:
                data = self._loader.load(filepath)
                if data is not None:
                    basename = filepath.split("/")[-1]
                    self._loaded_data[basename] = data
            except Exception as e:
                logger.error("Error loading %s: %s", filepath, e)
                QMessageBox.warning(
                    self,
                    "Load Error",
                    f"Failed to load {filepath}:\n{str(e)}",
                )

        # Auto-generate plot with loaded data
        if self._loaded_data:
            self._on_generate_plot()

    def _on_generate_plot(self) -> None:
        """Generate the plot from loaded data based on current controls."""
        self._plot_widget.clear()

        if not self._loaded_data:
            return

        plot_type = self._controls_panel.get_plot_type()
        x_log = self._controls_panel.get_x_log()
        y_log = self._controls_panel.get_y_log()

        if plot_type == "image":
            self._render_image_plot(x_log, y_log)
        else:
            self._render_line_plot(x_log, y_log)

    def _render_line_plot(self, x_log: bool, y_log: bool) -> None:
        """Render a line plot from loaded 1D SAS data."""
        self._plot_widget.set_log_mode(x_log=x_log, y_log=y_log)

        dataset_index = 0
        all_x_min = float("inf")
        all_x_max = float("-inf")
        all_y_min = float("inf")
        all_y_max = float("-inf")

        for basename, data in self._loaded_data.items():
            # Process 1D SAS datasets
            for sas_data in data.get("sas_data_list", []):
                x = sas_data.x
                y = sas_data.y

                # Skip datasets with non-positive values for log scale
                if (x_log and np.any(x <= 0)) or (y_log and np.any(y <= 0)):
                    continue

                from bernardyn.plot.plot_style import get_color, DEFAULT_SYMBOLS
                color = get_color(dataset_index)
                symbol = DEFAULT_SYMBOLS[dataset_index % len(DEFAULT_SYMBOLS)]

                self._plot_widget.add_line(
                    x, y,
                    color=color,
                    symbol=symbol,
                    linewidth=1.5,
                    name=basename,
                )

                # Add error bars if available
                if sas_data.y_err is not None:
                    self._plot_widget.add_error_bars(x, y, sas_data.y_err, color=color)

                # Track ranges
                all_x_min = min(all_x_min, float(x.min()))
                all_x_max = max(all_x_max, float(x.max()))
                all_y_min = min(all_y_min, float(y.min()))
                all_y_max = max(all_y_max, float(y.max()))

                dataset_index += 1

            # Process slit-smeared data
            slit_smear = data.get("slit_smear")
            if slit_smear is not None:
                x = slit_smear.x
                y = slit_smear.y

                if (x_log and np.any(x <= 0)) or (y_log and np.any(y <= 0)):
                    continue

                from bernardyn.plot.plot_style import get_color, DEFAULT_SYMBOLS
                color = get_color(dataset_index)
                self._plot_widget.add_line(
                    x, y, color=color, symbol="^", linewidth=1.5,
                    name=f"{basename} (SMR)",
                )

                all_x_min = min(all_x_min, float(x.min()))
                all_x_max = max(all_x_max, float(x.max()))
                all_y_min = min(all_y_min, float(y.min()))
                all_y_max = max(all_y_max, float(y.max()))

                dataset_index += 1

            # Process desmeared data
            desmear = data.get("desmear")
            if desmear is not None:
                x = desmear.x
                y = desmear.y

                if (x_log and np.any(x <= 0)) or (y_log and np.any(y <= 0)):
                    continue

                from bernardyn.plot.plot_style import get_color, DEFAULT_SYMBOLS
                color = get_color(dataset_index)
                self._plot_widget.add_line(
                    x, y, color=color, symbol="v", linewidth=1.5,
                    name=f"{basename} (desmear)",
                )

                all_x_min = min(all_x_min, float(x.min()))
                all_x_max = max(all_x_max, float(x.max()))
                all_y_min = min(all_y_min, float(y.min()))
                all_y_max = max(all_y_max, float(y.max()))

                dataset_index += 1

        # Set axis ranges
        if all_x_min != float("inf"):
            self._plot_widget.set_x_range(all_x_min, all_x_max)
        if all_y_min != float("inf"):
            self._plot_widget.set_y_range(all_y_min, all_y_max)

        # Update axis labels from first dataset
        for basename, data in self._loaded_data.items():
            for sas_data in data.get("sas_data_list", []):
                if len(sas_data.x) > 0:
                    self._plot_widget.set_x_label(sas_data.x_label or "X")
                    self._plot_widget.set_y_label(sas_data.y_label or "Y")
                    break

        # Update controls panel ranges
        if all_x_min != float("inf"):
            self._controls_panel.set_x_range(all_x_min, all_x_max)
        if all_y_min != float("inf"):
            self._controls_panel.set_y_range(all_y_min, all_y_max)

        # Enable controls
        self._controls_panel.set_enabled(True)

    def _render_image_plot(self, x_log: bool, y_log: bool) -> None:
        """Render a 2D image plot from loaded data."""
        self._plot_widget.set_log_mode(x_log=False, y_log=False)

        for basename, data in self._loaded_data.items():
            raw_image = data.get("raw_image")
            if raw_image is not None and raw_image.data.size > 0:
                img = raw_image.data
                vmin = float(np.percentile(img[img > 0], 1)) if np.any(img > 0) else float(img.min())
                vmax = float(np.percentile(img[img > 0], 99)) if np.any(img > 0) else float(img.max())

                self._plot_widget.add_image(img, vmin=vmin, vmax=vmax)
                self._plot_widget.set_title(f"{basename} - Raw Image")
                break

        # Enable controls
        self._controls_panel.set_enabled(True)

    def get_plot_widget(self) -> PlotWidget:
        """Get the plot widget for external access."""
        return self._plot_widget

    def get_data_panel(self) -> DataPanel:
        """Get the data panel for external access."""
        return self._data_panel

    def get_controls_panel(self) -> ControlsPanel:
        """Get the controls panel for external access."""
        return self._controls_panel
