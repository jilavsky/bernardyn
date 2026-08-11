"""pyqtgraph-based plot display widget for Bernardyn.

Provides a Qt widget that renders line plots, error bar plots,
and 2D images using pyqtgraph. Supports log/lin scale toggling,
zooming, panning, and clipboard copy.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton

logger = logging.getLogger(__name__)


class PlotWidget(QWidget):
    """A Qt widget for displaying SAS data plots.

    Wraps a pyqtgraph PlotWidget with controls for:
      - Log/lin scale toggling (X axis, Y axis)
      - Grid and legend toggles
      - Zoom reset
      - Clipboard copy (Ctrl/Cmd+C)
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # Create pyqtgraph plot widget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel("left", "Intensity", units="[arb]")
        self._plot_widget.setLabel("bottom", "Q", units="[1/A]")
        self._plot_widget.setTitle("Bernardyn Plot")

        # Enable anti-aliasing for smoother lines
        self._plot_widget.setAntialiasing(True)

        # Default to log-log scale (SAS standard)
        self._plot_widget.setLogMode(x=True, y=True)

        # Grid and legend state
        self._show_grid_x: bool = False
        self._show_grid_y: bool = False
        self._show_legend: bool = False

        # Add zoom reset and copy buttons
        btn_layout = QHBoxLayout()
        self._reset_btn = QPushButton("Reset Zoom")
        self._reset_btn.clicked.connect(self.reset_zoom)
        btn_layout.addWidget(self._reset_btn)

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.clicked.connect(self.copy_to_clipboard)
        btn_layout.addWidget(self._copy_btn)

        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot_widget)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # Store plot items for management
        self._plot_items: List[pg.PlotDataItem] = []
        self._error_bars: List[Any] = []

    def clear(self) -> None:
        """Clear all plot data and items."""
        self._plot_widget.clear()
        self._plot_items = []
        self._error_bars = []

    def set_title(self, title: str) -> None:
        """Set the plot title."""
        self._plot_widget.setTitle(title)

    def set_x_label(self, label: str) -> None:
        """Set the X axis label."""
        self._plot_widget.setLabel("bottom", label)

    def set_y_label(self, label: str) -> None:
        """Set the Y axis label."""
        self._plot_widget.setLabel("left", label)

    def set_x_range(self, xmin: float, xmax: float) -> None:
        """Set the X axis range."""
        self._plot_widget.setXRange(xmin, xmax, padding=0)

    def set_y_range(self, ymin: float, ymax: float) -> None:
        """Set the Y axis range."""
        self._plot_widget.setYRange(ymin, ymax, padding=0)

    def set_log_mode(self, x_log: bool = True, y_log: bool = True) -> None:
        """Set logarithmic scale mode for axes."""
        self._plot_widget.setLogMode(x=x_log, y=y_log)

    def set_grid(self, show_x: bool = False, show_y: bool = False) -> None:
        """Show or hide grid lines on the plot.

        Args:
            show_x: Show vertical (X axis) grid lines
            show_y: Show horizontal (Y axis) grid lines
        """
        self._show_grid_x = show_x
        self._show_grid_y = show_y

        # pyqtgraph uses alpha values for grid transparency
        alpha_x = 80 if show_x else 0
        alpha_y = 80 if show_y else 0
        self._plot_widget.showGrid(x=show_x, y=show_y, alpha=0.5)

    def get_grid(self) -> tuple:
        """Get current grid state."""
        return (self._show_grid_x, self._show_grid_y)

    def set_legend(self, show: bool = True) -> None:
        """Show or hide the plot legend.

        Args:
            show: Whether to display the legend
        """
        self._show_legend = show
        if show:
            self._plot_widget.addLegend()
        else:
            # Remove legend by clearing the plot and re-adding items
            self._plot_widget.clear()
            # Re-add all stored plot items with their names for legend display
            for item in self._plot_items:
                if hasattr(item, 'name') and item.name():
                    self._plot_widget.addItem(item)

    def get_legend(self) -> bool:
        """Get current legend state."""
        return self._show_legend

    def add_line(
        self,
        x: np.ndarray,
        y: np.ndarray,
        color: Optional[str] = None,
        symbol: Optional[str] = None,
        linestyle: Optional[str] = None,
        linewidth: int = 1,
        name: Optional[str] = None,
    ) -> pg.PlotDataItem:
        """Add a line plot to the display.

        Args:
            x: X values
            y: Y values
            color: Line color (hex string or pyqtgraph color)
            symbol: Marker symbol ('o', 's', 't', etc.) or None for no markers
            linestyle: Line style ('-', '--', '-.', '.') or None for default
            linewidth: Line width in pixels
            name: Legend label

        Returns:
            The created PlotDataItem.
        """
        # Map linestyle to pyqtgraph pen
        pen = self._make_pen(color, linestyle, linewidth)

        # Map symbol to pyqtgraph symbol
        pg_symbol = self._map_symbol(symbol)

        item = self._plot_widget.plot(
            x, y,
            pen=pen,
            symbol=pg_symbol,
            symbolSize=6,
            symbolBrush=pg.mkBrush(color) if color else None,
            name=name,
        )

        self._plot_items.append(item)
        return item

    def add_error_bars(
        self,
        x: np.ndarray,
        y: np.ndarray,
        y_err: np.ndarray,
        color: Optional[str] = None,
    ) -> pg.ErrorBarItem:
        """Add error bars to the plot.

        Args:
            x: X values
            y: Y values (tips of error bars)
            y_err: Error magnitudes (symmetric)
            color: Error bar color

        Returns:
            The created ErrorBarItem.
        """
        error_item = pg.ErrorBarItem(
            x=x, y=y,
            height=y_err,
            beam=0.4,
            pen=color or "w",
        )
        self._plot_widget.addItem(error_item)
        self._error_bars.append(error_item)
        return error_item

    def add_image(self, data: np.ndarray, vmin: Optional[float] = None, vmax: Optional[float] = None) -> pg.ImageItem:
        """Add a 2D image to the plot.

        Args:
            data: 2D numpy array
            vmin: Minimum value for color mapping (auto if None)
            vmax: Maximum value for color mapping (auto if None)

        Returns:
            The created ImageItem.
        """
        image_item = pg.ImageItem(image=data)
        if vmin is not None:
            image_item.setLookupTable(pg.ColorMap([0, 1], ["black", "white"]).map(np.linspace(0, 1, 256), mode="qcolor"))
        self._plot_widget.addItem(image_item)

        if vmin is not None and vmax is not None:
            image_item.setLevels([vmin, vmax])

        return image_item

    def reset_zoom(self) -> None:
        """Reset zoom to show all data."""
        self._plot_widget.autoRange()

    def copy_to_clipboard(self) -> None:
        """Copy the current plot to clipboard as an image."""
        app = self._plot_widget.scene().parent() if self._plot_widget.scene() else None
        # Use pyqtgraph's built-in copy functionality
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        # Render plot to pixmap and copy
        pixmap = self._plot_widget.renderToPixmap()
        clipboard.setPixmap(pixmap)
        logger.info("Plot copied to clipboard")

    def _make_pen(self, color: Optional[str] = None, linestyle: Optional[str] = None, linewidth: int = 1) -> pg.mkPen:
        """Create a pyqtgraph pen from color and linestyle."""
        # Map linestyle to pyqtgraph DashStyle
        style_map = {
            "-": pg.QtCore.Qt.SolidLine,
            "--": pg.QtCore.Qt.DashLine,
            ".": pg.QtCore.Qt.DotLine,
            "-.": pg.QtCore.Qt.DashDotLine,
        }

        qcolor = None
        if color:
            try:
                qcolor = pg.mkColor(color)
            except Exception:
                pass

        pen_style = pg.QtCore.Qt.SolidLine
        if linestyle and linestyle in style_map:
            pen_style = style_map[linestyle]

        return pg.mkPen(color=qcolor, width=linewidth, style=pen_style)

    def _map_symbol(self, symbol: Optional[str]) -> Optional[str]:
        """Map a symbol name to pyqtgraph symbol character."""
        if not symbol:
            return None

        symbol_map = {
            "o": "o",   # circle
            "s": "s",   # square
            "t": "t",   # triangle
            "d": "d",   # diamond
            "+": "+",   # plus
            "x": "x",   # x-mark
            "*": "*",   # star
        }

        return symbol_map.get(symbol, "o")

    def get_plot_widget(self) -> pg.PlotWidget:
        """Get the underlying pyqtgraph PlotWidget."""
        return self._plot_widget
