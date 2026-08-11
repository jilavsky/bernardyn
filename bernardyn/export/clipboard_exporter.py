"""Clipboard exporter for Bernardyn.

Exports plots to the system clipboard as an image, supporting
Ctrl/Cmd+C keyboard shortcut for quick copying.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ClipboardExporter:
    """Exports plots to the system clipboard as an image.

    Supports:
      - Copying plot as PNG image to clipboard
      - Works with Ctrl+C / Cmd+C keyboard shortcut
      - Compatible with most image editors and document processors
    """

    def get_format_name(self) -> str:
        """Return the format name identifier."""
        return "clipboard"

    def export(self, plot_widget: Any, output_path: str = "clipboard") -> bool:
        """Export the plot to the system clipboard.

        Args:
            plot_widget: The pyqtgraph PlotWidget to export.
            output_path: Ignored for clipboard format (always "clipboard").

        Returns:
            True if export succeeded, False otherwise.
        """
        try:
            from PySide6.QtWidgets import QApplication

            # Get the underlying pyqtgraph PlotWidget
            if hasattr(plot_widget, 'get_plot_widget'):
                pg_widget = plot_widget.get_plot_widget()
            else:
                pg_widget = plot_widget

            # Render to pixmap
            pixmap = pg_widget.renderToPixmap()

            # Copy to clipboard
            app = QApplication.instance()
            if app is None:
                logger.error("No QApplication instance found")
                return False

            clipboard = app.clipboard()
            clipboard.setPixmap(pixmap)

            logger.info("Plot copied to clipboard")
            return True

        except Exception as e:
            logger.error("Failed to copy plot to clipboard: %s", e)
            return False
