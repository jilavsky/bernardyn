"""Abstract base class and dispatcher for export formats.

Provides a unified interface for exporting plots to different
formats (image files, clipboard, container format).
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Exporter(ABC):
    """Abstract base class for all exporters."""

    @abstractmethod
    def get_format_name(self) -> str:
        """Return the format name identifier (e.g., 'png', 'svg', 'clipboard')."""
        ...

    @abstractmethod
    def export(self, plot_widget: Any, output_path: str) -> bool:
        """Export the plot to the specified format.

        Args:
            plot_widget: The pyqtgraph PlotWidget to export.
            output_path: Path for the exported file (or special value for clipboard).

        Returns:
            True if export succeeded, False otherwise.
        """
        ...


class ExportDispatcher:
    """Dispatches export operations to the appropriate exporter.

    Maintains a registry of exporters and selects the correct one
    based on file extension or format name.
    """

    def __init__(self):
        self._exporters: Dict[str, Exporter] = {}

    def register(self, exporter: Exporter) -> None:
        """Register an exporter for a specific format."""
        self._exporters[exporter.get_format_name()] = exporter

    def unregister(self, format_name: str) -> None:
        """Unregister an exporter by format name."""
        self._exporters.pop(format_name, None)

    def get_exporter(self, format_name: str) -> Optional[Exporter]:
        """Get an exporter by format name."""
        return self._exporters.get(format_name)

    def get_exporter_for_file(self, filepath: str) -> Optional[Exporter]:
        """Get the appropriate exporter for a file path based on extension.

        Args:
            filepath: Path to the output file.

        Returns:
            The appropriate Exporter, or None if no exporter supports the format.
        """
        import os
        ext = os.path.splitext(filepath)[1].lower()

        # Map extensions to format names
        ext_to_format = {
            '.png': 'png',
            '.jpg': 'jpeg',
            '.jpeg': 'jpeg',
            '.svg': 'svg',
            '.pdf': 'pdf',
        }

        format_name = ext_to_format.get(ext)
        if format_name:
            return self._exporters.get(format_name)

        # Try exact match
        return self._exporters.get(filepath.lower())

    def get_available_formats(self) -> List[str]:
        """Get list of available export format names."""
        return list(self._exporters.keys())

    def export(self, plot_widget: Any, output_path: str) -> bool:
        """Export a plot using the appropriate exporter.

        Args:
            plot_widget: The pyqtgraph PlotWidget to export.
            output_path: Path for the exported file (or 'clipboard' for clipboard).

        Returns:
            True if export succeeded, False otherwise.
        """
        # Check for clipboard format
        if output_path.lower() == 'clipboard':
            exporter = self._exporters.get('clipboard')
        else:
            exporter = self.get_exporter_for_file(output_path)

        if exporter is None:
            logger.error("No exporter available for: %s", output_path)
            return False

        try:
            logger.info("Exporting to %s with %s", output_path, type(exporter).__name__)
            return exporter.export(plot_widget, output_path)
        except Exception as e:
            logger.error("Error exporting to %s with %s: %s", output_path, type(exporter).__name__, e)
            return False


# Global export dispatcher with default exporters registered
_default_dispatcher = ExportDispatcher()

from bernardyn.export.image_exporter import ImageExporter  # noqa: E402
from bernardyn.export.clipboard_exporter import ClipboardExporter  # noqa: E402
from bernardyn.export.container_exporter import ContainerExporter  # noqa: E402

_default_dispatcher.register(ImageExporter())
_default_dispatcher.register(ClipboardExporter())
_default_dispatcher.register(ContainerExporter())


def get_exporter(format_name: str) -> Optional[Exporter]:
    """Get an exporter by format name from the global dispatcher."""
    return _default_dispatcher.get_exporter(format_name)


def get_default_dispatcher() -> ExportDispatcher:
    """Get the global default export dispatcher."""
    return _default_dispatcher
