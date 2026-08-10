"""Right panel: plot type, styles, axes controls for Bernardyn.

Provides the plot customization interface where users can:
  - Select plot type (line, image)
  - Toggle log/lin scales for X and Y axes
  - Set axis ranges
  - Add/remove datasets from the plot
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)


class ControlsPanel(QGroupBox):
    """Right panel for plot customization controls.

    Provides controls for:
      - Plot type selection (line, image)
      - Log/lin scale toggles for X and Y axes
      - Axis range inputs (min/max)
      - Generate plot button
    """

    # Signal emitted when user clicks "Generate Plot"
    generate_requested = Signal()

    def __init__(self, parent: Optional[Any] = None):
        super().__init__("Plot Controls", parent)

        self._plot_type: str = "line"  # 'line' or 'image'
        self._x_log: bool = True
        self._y_log: bool = True

        # Callbacks (set by main window)
        self._on_scale_changed: Optional[Any] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the UI layout."""
        layout = QVBoxLayout()

        # --- Plot Type section ---
        type_group = QGroupBox("Plot Type")
        type_layout = QVBoxLayout()

        self._plot_type_combo = QComboBox()
        self._plot_type_combo.addItem("Line Plot", "line")
        self._plot_type_combo.addItem("2D Image", "image")
        self._plot_type_combo.currentIndexChanged.connect(self._on_plot_type_changed)
        type_layout.addWidget(self._plot_type_combo)

        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        # --- Scale section (for line plots) ---
        scale_group = QGroupBox("Scale")
        scale_layout = QVBoxLayout()

        # X axis scale
        x_scale_layout = QHBoxLayout()
        self._x_log_check = QComboBox()
        self._x_log_check.addItem("Log", True)
        self._x_log_check.addItem("Lin", False)
        self._x_log_check.currentIndexChanged.connect(self._on_x_scale_changed)
        x_scale_layout.addWidget(QLabel("X axis:"))
        x_scale_layout.addWidget(self._x_log_check)
        scale_layout.addLayout(x_scale_layout)

        # Y axis scale
        y_scale_layout = QHBoxLayout()
        self._y_log_check = QComboBox()
        self._y_log_check.addItem("Log", True)
        self._y_log_check.addItem("Lin", False)
        self._y_log_check.currentIndexChanged.connect(self._on_y_scale_changed)
        y_scale_layout.addWidget(QLabel("Y axis:"))
        y_scale_layout.addWidget(self._y_log_check)
        scale_layout.addLayout(y_scale_layout)

        # Axis range inputs
        range_group = QGroupBox("Axis Ranges")
        range_layout = QVBoxLayout()

        x_range_layout = QHBoxLayout()
        x_range_layout.addWidget(QLabel("X min:"))
        self._x_min_spin = QDoubleSpinBox()
        self._x_min_spin.setRange(-1e30, 1e30)
        self._x_min_spin.setDecimals(6)
        x_range_layout.addWidget(self._x_min_spin)
        x_range_layout.addWidget(QLabel("X max:"))
        self._x_max_spin = QDoubleSpinBox()
        self._x_max_spin.setRange(-1e30, 1e30)
        self._x_max_spin.setDecimals(6)
        x_range_layout.addWidget(self._x_max_spin)
        range_layout.addLayout(x_range_layout)

        y_range_layout = QHBoxLayout()
        y_range_layout.addWidget(QLabel("Y min:"))
        self._y_min_spin = QDoubleSpinBox()
        self._y_min_spin.setRange(-1e30, 1e30)
        self._y_min_spin.setDecimals(6)
        y_range_layout.addWidget(self._y_min_spin)
        y_range_layout.addWidget(QLabel("Y max:"))
        self._y_max_spin = QDoubleSpinBox()
        self._y_max_spin.setRange(-1e30, 1e30)
        self._y_max_spin.setDecimals(6)
        y_range_layout.addWidget(self._y_max_spin)
        range_layout.addLayout(y_range_layout)

        # Auto-range button
        self._auto_range_btn = QPushButton("Auto Range")
        self._auto_range_btn.clicked.connect(self._on_auto_range)
        range_layout.addWidget(self._auto_range_btn)

        range_group.setLayout(range_layout)
        scale_layout.addWidget(range_group)

        scale_group.setLayout(scale_layout)
        layout.addWidget(scale_group)

        # --- Generate button ---
        self._generate_btn = QPushButton("Generate Plot")
        self._generate_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        self._generate_btn.clicked.connect(self.generate_requested.emit)
        layout.addWidget(self._generate_btn)

        # Spacer to push controls to top
        layout.addStretch(1)

        self.setLayout(layout)

    def _on_plot_type_changed(self, index: int) -> None:
        """Handle plot type changes."""
        self._plot_type = self._plot_type_combo.currentData()

    def _on_x_scale_changed(self, index: int) -> None:
        """Handle X axis scale changes."""
        self._x_log = self._x_log_check.currentData()
        if self._on_scale_changed:
            self._on_scale_changed("x", self._x_log)

    def _on_y_scale_changed(self, index: int) -> None:
        """Handle Y axis scale changes."""
        self._y_log = self._y_log_check.currentData()
        if self._on_scale_changed:
            self._on_scale_changed("y", self._y_log)

    def _on_auto_range(self) -> None:
        """Handle auto-range button click."""
        if self._on_scale_changed:
            self._on_scale_changed("auto", None)

    def set_on_scale_changed(self, callback: Any) -> None:
        """Set the callback for scale/range changes."""
        self._on_scale_changed = callback

    def get_plot_type(self) -> str:
        """Get the current plot type."""
        return self._plot_type

    def get_x_log(self) -> bool:
        """Get the X axis log scale state."""
        return self._x_log

    def get_y_log(self) -> bool:
        """Get the Y axis log scale state."""
        return self._y_log

    def set_x_range(self, xmin: float, xmax: float) -> None:
        """Set the X axis range spinboxes."""
        self._x_min_spin.setValue(xmin)
        self._x_max_spin.setValue(xmax)

    def set_y_range(self, ymin: float, ymax: float) -> None:
        """Set the Y axis range spinboxes."""
        self._y_min_spin.setValue(ymin)
        self._y_max_spin.setValue(ymax)

    def get_x_range(self) -> tuple:
        """Get the current X axis range."""
        return (self._x_min_spin.value(), self._x_max_spin.value())

    def get_y_range(self) -> tuple:
        """Get the current Y axis range."""
        return (self._y_min_spin.value(), self._y_max_spin.value())

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable all controls."""
        self._plot_type_combo.setEnabled(enabled)
        self._x_log_check.setEnabled(enabled)
        self._y_log_check.setEnabled(enabled)
        self._x_min_spin.setEnabled(enabled)
        self._x_max_spin.setEnabled(enabled)
        self._y_min_spin.setEnabled(enabled)
        self._y_max_spin.setEnabled(enabled)
        self._auto_range_btn.setEnabled(enabled)
        self._generate_btn.setEnabled(enabled)
