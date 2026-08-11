"""Plot engine for Bernardyn.

Abstract base class and dispatcher for different plot types.
Routes rendering requests to the appropriate plotter.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Plotter(ABC):
    """Abstract base class for all plotters."""

    @abstractmethod
    def get_plot_type(self) -> str:
        """Return the plot type identifier (e.g., 'line', 'image')."""
        ...

    @abstractmethod
    def get_plot_config(self, **kwargs) -> Dict[str, Any]:
        """Get the rendering configuration for this plotter."""
        ...


class PlotEngine:
    """Dispatches plotting to the appropriate plotter based on data type.

    Maintains plotters for different visualization types and selects
    the right one based on the data being plotted.
    """

    def __init__(self):
        self._plotters: Dict[str, Plotter] = {}

    def register(self, plotter: Plotter) -> None:
        """Register a plotter for a specific plot type."""
        self._plotters[plotter.get_plot_type()] = plotter

    def unregister(self, plot_type: str) -> None:
        """Unregister a plotter by type."""
        self._plotters.pop(plot_type, None)

    def get_plotter(self, plot_type: str) -> Optional[Plotter]:
        """Get a plotter by type name."""
        return self._plotters.get(plot_type)

    def get_available_types(self) -> list:
        """Get list of available plot type names."""
        return list(self._plotters.keys())

    def create_plot_config(
        self,
        plot_type: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Create a plot configuration using the appropriate plotter.

        Args:
            plot_type: Type of plot ('line', 'image', etc.)
            **kwargs: Additional arguments passed to the plotter

        Returns:
            Plot configuration dict, or None if plot type not found.
        """
        plotter = self._plotters.get(plot_type)
        if plotter is None:
            logger.error("No plotter registered for type: %s", plot_type)
            return None

        try:
            return plotter.get_plot_config(**kwargs)
        except Exception as e:
            logger.error("Error creating plot config for type %s: %s", plot_type, e)
            return None


class LinePlotterAdapter(Plotter):
    """Adapter that wraps LinePlotter as a Plotter interface implementation."""

    def __init__(self, line_plotter):
        self._plotter = line_plotter

    def get_plot_type(self) -> str:
        return "line"

    def get_plot_config(self, **kwargs):
        x_log = kwargs.get("x_log", True)
        y_log = kwargs.get("y_log", True)
        return self._plotter.get_plot_config(x_log=x_log, y_log=y_log)


class ImagePlotterAdapter(Plotter):
    """Adapter that wraps ImagePlotter as a Plotter interface implementation."""

    def __init__(self, image_plotter):
        self._plotter = image_plotter

    def get_plot_type(self) -> str:
        return "image"

    def get_plot_config(self, **kwargs):
        return self._plotter.get_plot_config()


class WaterfallPlotterAdapter(Plotter):
    """Adapter that wraps WaterfallPlotter as a Plotter interface implementation."""

    def __init__(self, waterfall_plotter):
        self._plotter = waterfall_plotter

    def get_plot_type(self) -> str:
        return "waterfall"

    def get_plot_config(self, **kwargs):
        x_log = kwargs.get("x_log", False)
        y_log = kwargs.get("y_log", True)
        return self._plotter.get_plot_config(x_log=x_log, y_log=y_log)


class HeatmapPlotterAdapter(Plotter):
    """Adapter that wraps HeatmapPlotter as a Plotter interface implementation."""

    def __init__(self, heatmap_plotter):
        self._plotter = heatmap_plotter

    def get_plot_type(self) -> str:
        return "heatmap"

    def get_plot_config(self, **kwargs):
        x_log = kwargs.get("x_log", False)
        y_log = kwargs.get("y_log", False)
        return self._plotter.get_plot_config(x_log=x_log, y_log=y_log)


# Global plot engine with default plotters registered
_default_engine = PlotEngine()

from bernardyn.plot.line_plotter import LinePlotter  # noqa: E402
from bernardyn.plot.image_plotter import ImagePlotter  # noqa: E402
from bernardyn.plot.waterfall_plotter import WaterfallPlotter  # noqa: E402
from bernardyn.plot.heatmap_plotter import HeatmapPlotter  # noqa: E402

_default_engine.register(LinePlotterAdapter(LinePlotter()))
_default_engine.register(ImagePlotterAdapter(ImagePlotter()))
_default_engine.register(WaterfallPlotterAdapter(WaterfallPlotter()))
_default_engine.register(HeatmapPlotterAdapter(HeatmapPlotter()))


def get_plotter(plot_type: str):
    """Get a plotter by type from the global engine."""
    return _default_engine.get_plotter(plot_type)


def get_default_engine() -> PlotEngine:
    """Get the global default plot engine."""
    return _default_engine
