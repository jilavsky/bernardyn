"""Image plotter for Bernardyn.

Creates 2D color map plots for area detector images and heatmap
representations of multiple 1D datasets.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# Available color scales for 2D images
COLOR_SCALES = [
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

DEFAULT_COLOR_SCALE = "grayscale"


class ImagePlotter:
    """Creates 2D image plots and heatmap plots.

    Supports:
      - Raw 2D detector images with color scale selection
      - Heatmap representation of multiple 1D datasets
    """

    def __init__(self):
        self._image_data: Optional[np.ndarray] = None
        self._color_scale: str = DEFAULT_COLOR_SCALE
        self._log_scale: bool = False

    def set_image(self, data: np.ndarray) -> None:
        """Set the 2D image data to display.

        Args:
            data: 2D numpy array (detector image)
        """
        self._image_data = np.asarray(data)

    def set_color_scale(self, scale: str) -> None:
        """Set the color scale for image display.

        Args:
            scale: Name of color scale from COLOR_SCALES list
        """
        if scale not in COLOR_SCALES:
            logger.warning("Unknown color scale %r, using default", scale)
            scale = DEFAULT_COLOR_SCALE
        self._color_scale = scale

    def set_log_scale(self, enabled: bool) -> None:
        """Enable or disable logarithmic color scale."""
        self._log_scale = enabled

    def get_plot_config(self) -> Dict[str, Any]:
        """Get the complete plot configuration for rendering.

        Returns:
            Dict with image data and display settings.
        """
        if self._image_data is None:
            return {
                "image": None,
                "color_scale": self._color_scale,
                "log_scale": self._log_scale,
            }

        data = self._image_data.copy()

        # Apply log scale to image data
        if self._log_scale:
            data = np.where(data > 0, np.log10(np.maximum(data, 1e-30)), 0)

        # Compute display range
        valid = data[data > 0] if self._log_scale else data
        if valid.size > 0:
            vmin = float(valid.min())
            vmax = float(valid.max())
        else:
            vmin = float(data.min())
            vmax = float(data.max())

        return {
            "image": data,
            "vmin": vmin,
            "vmax": vmax,
            "color_scale": self._color_scale,
            "log_scale": self._log_scale,
        }

    def get_color_scales(self) -> List[str]:
        """Get list of available color scales."""
        return list(COLOR_SCALES)
