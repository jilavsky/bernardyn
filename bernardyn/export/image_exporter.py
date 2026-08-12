"""Image file exporter for Bernardyn.

Exports plots to PNG, JPG, SVG, and PDF formats using pyqtgraph's
built-in export functionality with resolution control.
"""

import logging
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap

logger = logging.getLogger(__name__)


class ImageExporter:
    """Exports plots to image file formats (PNG, JPG, SVG, PDF).

    Supports:
      - PNG export with configurable resolution (DPI)
      - JPG/JPEG export with quality control
      - SVG vector graphics export
      - PDF export for print-quality output
    """

    def get_format_name(self) -> str:
        """Return the format name identifier."""
        return "image"

    def export(self, plot_widget: Any, output_path: str) -> bool:
        """Export the plot to an image file.

        Args:
            plot_widget: The pyqtgraph PlotWidget to export.
            output_path: Path for the exported file (e.g., 'output.png').

        Returns:
            True if export succeeded, False otherwise.
        """
        try:
            import os

            ext = os.path.splitext(output_path)[1].lower()

            # Get the underlying pyqtgraph PlotWidget
            if hasattr(plot_widget, 'get_plot_widget'):
                pg_widget = plot_widget.get_plot_widget()
            else:
                pg_widget = plot_widget

            # Use pyqtgraph's export functionality
            if ext in ('.png', '.jpg', '.jpeg'):
                # Raster formats - use renderToPixmap with DPI control
                from PySide6.QtGui import QPixmap
                from PySide6.QtCore import QSize

                # Get plot dimensions
                width = pg_widget.width()
                height = pg_widget.height()

                # Scale for higher resolution (2x for retina)
                scale = 2.0
                pixmap = pg_widget.renderToPixmap(
                    QSize(int(width * scale), int(height * scale))
                )

                # Save with appropriate format
                if ext in ('.jpg', '.jpeg'):
                    # JPG doesn't support alpha, convert to RGB
                    rgb_pixmap = QPixmap(pixmap.size())
                    rgb_pixmap.fill(Qt.GlobalColor.white)
                    painter = QPainter(rgb_pixmap)
                    painter.drawPixmap(0, 0, pixmap)
                    painter.end()
                    rgb_pixmap.save(output_path, "JPEG", 95)  # 95% quality
                else:
                    pixmap.save(output_path, "PNG")

            elif ext == '.svg':
                # Vector format - use writeSvg
                pg_widget.writeSvg(output_path)

            elif ext == '.pdf':
                # PDF format - use writePdf
                pg_widget.writePdf(output_path)

            else:
                # Fallback to renderToPixmap for unknown formats
                pixmap = pg_widget.renderToPixmap()
                pixmap.save(output_path)

            logger.info("Exported plot to %s", output_path)
            return True

        except Exception as e:
            logger.error("Failed to export plot to %s: %s", output_path, e)
            return False
