"""Line plotter for Bernardyn.

Creates line plots, error bar plots with support for log-log,
log-lin, and lin-lin scale combinations.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class LinePlotter:
    """Creates line plots and error bar plots for 1D SAS data.

    Supports:
      - Single or multiple datasets overlaid
      - Error bars (Y uncertainty)
      - Log-log, log-lin, lin-log, and lin-lin scales
      - Auto-styling for multiple datasets (colors, symbols, line styles)
    """

    def __init__(self):
        self._plot_data: List[Dict[str, Any]] = []

    def clear(self) -> None:
        """Clear all plot data."""
        self._plot_data = []

    def add_dataset(
        self,
        x: np.ndarray,
        y: np.ndarray,
        y_err: Optional[np.ndarray] = None,
        x_label: str = "",
        y_label: str = "",
        title: str = "",
        color: Optional[str] = None,
        symbol: Optional[str] = None,
        linestyle: Optional[str] = None,
        index: int = 0,
    ) -> Dict[str, Any]:
        """Add a dataset to the plot.

        Args:
            x: X values (e.g., Q)
            y: Y values (e.g., I)
            y_err: Y uncertainties for error bars (optional)
            x_label: Label for X axis
            y_label: Label for Y axis
            title: Plot title / dataset name
            color: Override color (auto-assigned if None)
            symbol: Override symbol type (auto-assigned if None)
            linestyle: Override line style (auto-assigned if None)
            index: Dataset index for auto-styling

        Returns:
            Dict with the dataset info and computed style.
        """
        from bernardyn.plot.plot_style import auto_style

        style = auto_style(index)
        if color:
            style["color"] = color
        if symbol:
            style["symbol"] = symbol
        if linestyle:
            style["linestyle"] = linestyle

        entry = {
            "x": x,
            "y": y,
            "y_err": y_err,
            "x_label": x_label,
            "y_label": y_label,
            "title": title,
            **style,
        }

        self._plot_data.append(entry)
        return entry

    def get_plot_config(
        self,
        x_log: bool = True,
        y_log: bool = True,
    ) -> Dict[str, Any]:
        """Get the complete plot configuration for rendering.

        Args:
            x_log: Use logarithmic X scale
            y_log: Use logarithmic Y scale

        Returns:
            Dict with all data and configuration needed for rendering.
        """
        if not self._plot_data:
            return {"datasets": [], "x_log": x_log, "y_log": y_log}

        # Determine axis labels from first dataset
        first = self._plot_data[0]
        x_label = first.get("x_label", "X")
        y_label = first.get("y_label", "Y")

        # Determine axis ranges from all data
        x_min = float(min(d["x"].min() for d in self._plot_data))
        x_max = float(max(d["x"].max() for d in self._plot_data))
        y_min = float(min(d["y"].min() for d in self._plot_data))
        y_max = float(max(d["y"].max() for d in self._plot_data))

        # Filter out zero/negative values for log scale
        if x_log:
            valid_x_mins = [float(d["x"].min()) for d in self._plot_data if np.all(d["x"] > 0)]
            if valid_x_mins:
                x_min = max(x_min, min(valid_x_mins))
        if y_log:
            valid_y_mins = [float(d["y"].min()) for d in self._plot_data if np.all(d["y"] > 0)]
            if valid_y_mins:
                y_min = max(y_min, min(valid_y_mins))

        return {
            "datasets": self._plot_data,
            "x_label": x_label,
            "y_label": y_label,
            "x_range": (x_min, x_max),
            "y_range": (y_min, y_max),
            "x_log": x_log,
            "y_log": y_log,
        }

    def get_scale_type(self) -> str:
        """Get the scale type string (e.g., 'log-log', 'lin-lin')."""
        # This is a helper; actual scale type comes from config
        return "log-log"  # default for SAS data
