"""Heatmap plotter for Bernardyn.

Creates 2D color map (heatmap) plots where multiple 1D datasets
are arranged with X as horizontal axis, order number as vertical
axis, and intensity values mapped to color.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# Available color scales for heatmap display
HEATMAP_COLOR_SCALES = [
    "grayscale",
    "viridis",
    "jet",
    "hot",
    "cool",
    "spring",
    "summer",
    "autumn",
    "winter",
]

DEFAULT_HEATMAP_COLOR_SCALE = "viridis"


class HeatmapPlotter:
    """Creates 2D heatmap plots from ordered 1D SAS datasets.

    Supports:
      - Multiple datasets arranged with X horizontal, order number vertical
      - Intensity values mapped to color via configurable color scales
      - Auto-scaling of the color range
    """

    def __init__(self):
        self._datasets: List[Dict[str, Any]] = []
        self._color_scale: str = DEFAULT_HEATMAP_COLOR_SCALE

    def clear(self) -> None:
        """Clear all plot data."""
        self._datasets = []

    def set_color_scale(self, scale: str) -> None:
        """Set the color scale for heatmap display.

        Args:
            scale: Name of color scale from HEATMAP_COLOR_SCALES list.
        """
        if scale not in HEATMAP_COLOR_SCALES:
            logger.warning("Unknown color scale %r, using default", scale)
            scale = DEFAULT_HEATMAP_COLOR_SCALE
        self._color_scale = scale

    def add_dataset(
        self,
        x: np.ndarray,
        y: np.ndarray,
        order_number: Optional[int] = None,
        x_label: str = "",
        y_label: str = "",
    ) -> Dict[str, Any]:
        """Add a dataset to the heatmap.

        Args:
            x: X values (e.g., Q)
            y: Y values (intensity — mapped to color)
            order_number: Order number for vertical position.
                If None, uses the dataset index position.
            x_label: Label for X axis
            y_label: Label for Y axis

        Returns:
            Dict with the dataset info and computed vertical position.
        """
        idx = len(self._datasets)
        if order_number is not None:
            y_pos = float(order_number)
        else:
            y_pos = float(idx)

        entry = {
            "x": np.asarray(x, dtype=np.float64),
            "y": np.asarray(y, dtype=np.float64),
            "order_number": order_number if order_number is not None else idx,
            "x_label": x_label,
            "y_label": y_label,
        }

        self._datasets.append(entry)
        return entry

    def get_color_scales(self) -> List[str]:
        """Get list of available color scales."""
        return list(HEATMAP_COLOR_SCALES)

    def get_plot_config(
        self,
        x_log: bool = False,
        y_log: bool = False,
    ) -> Dict[str, Any]:
        """Get the complete plot configuration for rendering.

        Args:
            x_log: Use logarithmic X scale
            y_log: Use logarithmic Y scale

        Returns:
            Dict with all data and configuration needed for rendering.
        """
        if not self._datasets:
            return {
                "datasets": [],
                "x_label": "",
                "y_label": "Order Number",
                "color_label": "Intensity",
                "x_range": (0, 1),
                "y_range": (0, 1),
                "color_range": (0, 1),
                "x_log": x_log,
                "y_log": y_log,
                "color_scale": self._color_scale,
            }

        # Determine axis labels from first dataset
        first = self._datasets[0]
        x_label = first.get("x_label", "Q")

        # Compute ranges from all data
        x_min = float(min(d["x"].min() for d in self._datasets))
        x_max = float(max(d["x"].max() for d in self._datasets))

        y_min = float(min(d["order_number"] for d in self._datasets))
        y_max = float(max(d["order_number"] for d in self._datasets))

        # Color range from all Y values (intensity)
        all_y = np.concatenate([d["y"] for d in self._datasets])
        color_min = float(np.min(all_y)) if all_y.size > 0 else 0.0
        color_max = float(np.max(all_y)) if all_y.size > 0 else 1.0

        # Filter out zero/negative values for log scale
        if x_log:
            valid_x_mins = [float(d["x"].min()) for d in self._datasets if np.all(d["x"] > 0)]
            if valid_x_mins:
                x_min = max(x_min, min(valid_x_mins))

        return {
            "datasets": self._datasets,
            "x_label": x_label,
            "y_label": "Order Number",
            "color_label": "Intensity",
            "x_range": (x_min, x_max),
            "y_range": (y_min, y_max),
            "color_range": (color_min, color_max),
            "x_log": x_log,
            "y_log": y_log,
            "color_scale": self._color_scale,
        }
