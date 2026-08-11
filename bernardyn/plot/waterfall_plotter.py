"""Waterfall plotter for Bernardyn.

Creates 3D waterfall (offset) plots where multiple 1D datasets
are stacked along the Z axis with an order-number-based offset.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class WaterfallPlotter:
    """Creates 3D waterfall plots for ordered 1D SAS datasets.

    Supports:
      - Multiple datasets stacked with Z-offset based on order number
      - Auto-scaling of Z offset to prevent overlap
      - Per-dataset styling (color, symbol)
    """

    def __init__(self):
        self._datasets: List[Dict[str, Any]] = []
        self._z_offset: float = 1.0  # Default Z offset per dataset

    def clear(self) -> None:
        """Clear all plot data."""
        self._datasets = []

    def add_dataset(
        self,
        x: np.ndarray,
        y: np.ndarray,
        order_number: Optional[int] = None,
        color: Optional[str] = None,
        symbol: Optional[str] = "o",
        x_label: str = "",
        y_label: str = "",
        title: str = "",
    ) -> Dict[str, Any]:
        """Add a dataset to the waterfall plot.

        Args:
            x: X values (e.g., Q)
            y: Y values (e.g., I)
            order_number: Order number for Z-offset calculation.
                If None, uses the dataset index position.
            color: Line color (auto-assigned if None)
            symbol: Marker symbol type
            x_label: Label for X axis
            y_label: Label for Y axis
            title: Dataset name/title

        Returns:
            Dict with the dataset info and computed Z offset.
        """
        from bernardyn.plot.plot_style import get_color

        idx = len(self._datasets)
        if order_number is not None:
            z_offset = float(order_number) * self._z_offset
        else:
            z_offset = float(idx) * self._z_offset

        if color is None:
            color = get_color(idx)

        entry = {
            "x": np.asarray(x, dtype=np.float64),
            "y": np.asarray(y, dtype=np.float64),
            "z_offset": z_offset,
            "order_number": order_number if order_number is not None else idx,
            "color": color,
            "symbol": symbol or "o",
            "x_label": x_label,
            "y_label": y_label,
            "title": title or f"Dataset {idx + 1}",
        }

        self._datasets.append(entry)
        return entry

    def set_z_offset(self, offset: float) -> None:
        """Set the Z offset multiplier.

        Args:
            offset: Multiplier for order number to compute Z position.
                Larger values spread datasets further apart vertically.
        """
        self._z_offset = float(offset)

    def get_z_offset(self) -> float:
        """Get the current Z offset multiplier."""
        return self._z_offset

    def get_plot_config(
        self,
        x_log: bool = False,
        y_log: bool = True,
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
                "y_label": "",
                "z_label": "Order Number",
                "x_range": (0, 1),
                "y_range": (0, 1),
                "z_range": (0, 1),
                "x_log": x_log,
                "y_log": y_log,
            }

        # Determine axis labels from first dataset
        first = self._datasets[0]
        x_label = first.get("x_label", "Q")
        y_label = first.get("y_label", "I")

        # Compute ranges from all data
        x_min = float(min(d["x"].min() for d in self._datasets))
        x_max = float(max(d["x"].max() for d in self._datasets))
        y_min = float(min(d["y"].min() for d in self._datasets))
        y_max = float(max(d["y"].max() for d in self._datasets))

        # Z range based on order numbers
        z_min = float(min(d["order_number"] for d in self._datasets))
        z_max = float(max(d["order_number"] for d in self._datasets))

        # Filter out zero/negative values for log scale
        if x_log:
            valid_x_mins = [float(d["x"].min()) for d in self._datasets if np.all(d["x"] > 0)]
            if valid_x_mins:
                x_min = max(x_min, min(valid_x_mins))
        if y_log:
            valid_y_mins = [float(d["y"].min()) for d in self._datasets if np.all(d["y"] > 0)]
            if valid_y_mins:
                y_min = max(y_min, min(valid_y_mins))

        return {
            "datasets": self._datasets,
            "x_label": x_label,
            "y_label": y_label,
            "z_label": "Order Number",
            "x_range": (x_min, x_max),
            "y_range": (y_min, y_max),
            "z_range": (z_min, z_max),
            "x_log": x_log,
            "y_log": y_log,
        }
