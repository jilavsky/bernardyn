"""Right panel: plot type, styles, axes controls for Bernardyn.

Provides the plot customization interface where users can:
  - Select plot type (line, image)
  - Toggle log/lin scales for X and Y axes
  - Set axis ranges
  - Add/remove datasets from the plot
  - Toggle grid and legend display
  - Manage per-dataset styling (color, symbol, line style)
  - Toggle slit-smeared/desmeared data display
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from bernardyn.template.manager import TemplateManager, get_default_manager

logger = logging.getLogger(__name__)


class ControlsPanel(QGroupBox):
    """Right panel for plot customization controls.

    Provides controls for:
      - Plot type selection (line, image)
      - Log/lin scale toggles for X and Y axes
      - Axis range inputs (min/max)
      - Grid and legend toggles
      - Per-dataset styling (color, symbol, line style)
      - Slit-smeared/desmeared data toggle
      - Generate plot button
    """

    # Signal emitted when user clicks "Generate Plot"
    generate_requested = Signal()

    # Signal emitted when a dataset style is changed
    dataset_style_changed = Signal(int, dict)

    def __init__(self, parent: Optional[Any] = None):
        super().__init__("Plot Controls", parent)

        self._plot_type: str = "line"  # 'line', 'image', 'waterfall', 'heatmap'
        self._x_log: bool = True
        self._y_log: bool = True

        # Waterfall-specific controls
        self._z_offset_spin: Optional[QDoubleSpinBox] = None

        # Heatmap/image color scale
        self._color_scale_combo: Optional[QComboBox] = None
        self._show_grid_x: bool = False
        self._show_grid_y: bool = False
        self._show_legend: bool = True
        self._show_slit_smear: bool = False

        # Per-dataset styling: list of dicts with 'color', 'symbol', 'linestyle'
        self._dataset_styles: List[Dict[str, str]] = []

        # Callbacks (set by main window)
        self._on_scale_changed: Optional[Any] = None
        self._on_template_applied: Optional[Any] = None
        self._on_save_template: Optional[Any] = None
        self._on_manage_templates_callback: Optional[Any] = None

        # Template manager reference (set by main window)
        self._template_manager: Optional[TemplateManager] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the UI layout."""
        main_layout = QVBoxLayout()

        # --- Template section ---
        template_group = QGroupBox("Templates")
        template_layout = QVBoxLayout()

        # Template selector combo box
        tmpl_select_layout = QHBoxLayout()
        tmpl_select_layout.addWidget(QLabel("Template:"))
        self._template_combo = QComboBox()
        self._template_combo.addItem("(none)", "")
        self._template_combo.currentIndexChanged.connect(self._on_template_selected)
        tmpl_select_layout.addWidget(self._template_combo, 1)
        template_layout.addLayout(tmpl_select_layout)

        # Save current as template button
        self._save_template_btn = QPushButton("Save Current as Template...")
        self._save_template_btn.clicked.connect(self._on_save_current_as_template)
        template_layout.addWidget(self._save_template_btn)

        # Manage templates button
        self._manage_templates_btn = QPushButton("Manage Templates...")
        self._manage_templates_btn.clicked.connect(self._on_manage_templates)
        template_layout.addWidget(self._manage_templates_btn)

        template_group.setLayout(template_layout)
        main_layout.addWidget(template_group)

        # --- Plot Type section ---
        type_group = QGroupBox("Plot Type")
        type_layout = QVBoxLayout()

        self._plot_type_combo = QComboBox()
        self._plot_type_combo.addItem("Line Plot", "line")
        self._plot_type_combo.addItem("2D Image", "image")
        self._plot_type_combo.addItem("Waterfall Plot", "waterfall")
        self._plot_type_combo.addItem("Heatmap Plot", "heatmap")
        self._plot_type_combo.currentIndexChanged.connect(self._on_plot_type_changed)
        type_layout.addWidget(self._plot_type_combo)

        type_group.setLayout(type_layout)
        main_layout.addWidget(type_group)

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

        # Color scale selector (for image and heatmap plots)
        color_scale_group = QGroupBox("Color Scale")
        color_scale_layout = QVBoxLayout()

        self._color_scale_combo = QComboBox()
        from bernardyn.plot.image_plotter import COLOR_SCALES
        for scale in COLOR_SCALES:
            self._color_scale_combo.addItem(scale, scale)
        self._color_scale_combo.currentIndexChanged.connect(self._on_color_scale_changed)
        color_scale_layout.addWidget(self._color_scale_combo)

        # Log scale toggle for image/heatmap
        self._log_scale_check = QCheckBox("Log Scale")
        self._log_scale_check.stateChanged.connect(self._on_log_scale_changed)
        color_scale_layout.addWidget(self._log_scale_check)

        color_scale_group.setLayout(color_scale_layout)
        main_layout.addWidget(color_scale_group)

        # --- Z Offset section (for waterfall plots) ---
        z_offset_group = QGroupBox("Z Offset")
        z_offset_layout = QVBoxLayout()

        self._z_offset_spin = QDoubleSpinBox()
        self._z_offset_spin.setRange(0.01, 1000.0)
        self._z_offset_spin.setValue(1.0)
        self._z_offset_spin.setDecimals(3)
        self._z_offset_spin.setSingleStep(0.1)
        self._z_offset_spin.valueChanged.connect(self._on_z_offset_changed)
        z_offset_layout.addWidget(self._z_offset_spin)

        z_offset_group.setLayout(z_offset_layout)
        main_layout.addWidget(z_offset_group)

        # --- Scale section (for line plots) ---
        scale_group = QGroupBox("Scale")
        display_layout = QVBoxLayout()

        self._grid_x_check = QCheckBox("X Grid")
        self._grid_x_check.stateChanged.connect(self._on_grid_changed)
        display_layout.addWidget(self._grid_x_check)

        self._grid_y_check = QCheckBox("Y Grid")
        self._grid_y_check.stateChanged.connect(self._on_grid_changed)
        display_layout.addWidget(self._grid_y_check)

        self._legend_check = QCheckBox("Legend")
        self._legend_check.setChecked(True)
        self._legend_check.stateChanged.connect(self._on_legend_changed)
        display_layout.addWidget(self._legend_check)

        # Slit-smeared toggle (initially disabled)
        self._slit_smear_check = QCheckBox("Show Slit-Smeared")
        self._slit_smear_check.setEnabled(False)
        self._slit_smear_check.stateChanged.connect(self._on_slit_smear_changed)
        display_layout.addWidget(self._slit_smear_check)

        display_group.setLayout(display_layout)
        scale_layout.addWidget(display_group)

        scale_group.setLayout(scale_layout)
        main_layout.addWidget(scale_group)

        # --- Dataset Styling section ---
        style_group = QGroupBox("Dataset Styles")
        style_layout = QVBoxLayout()

        # Dataset selector
        ds_select_layout = QHBoxLayout()
        ds_select_layout.addWidget(QLabel("Dataset:"))
        self._dataset_combo = QComboBox()
        self._dataset_combo.currentIndexChanged.connect(self._on_dataset_selected)
        ds_select_layout.addWidget(self._dataset_combo, 1)
        style_layout.addLayout(ds_select_layout)

        # Color selector
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        self._color_combo = QComboBox()
        from bernardyn.plot.plot_style import DEFAULT_COLORS
        for c in DEFAULT_COLORS:
            self._color_combo.addItem(self._make_color_item(c, c))
        self._color_combo.currentIndexChanged.connect(self._on_style_changed)
        color_layout.addWidget(self._color_combo, 1)
        style_layout.addLayout(color_layout)

        # Symbol selector
        symbol_layout = QHBoxLayout()
        symbol_layout.addWidget(QLabel("Symbol:"))
        self._symbol_combo = QComboBox()
        from bernardyn.plot.plot_style import DEFAULT_SYMBOLS
        for s in DEFAULT_SYMBOLS:
            self._symbol_combo.addItem(s, s)
        self._symbol_combo.currentIndexChanged.connect(self._on_style_changed)
        symbol_layout.addWidget(self._symbol_combo, 1)
        style_layout.addLayout(symbol_layout)

        # Line style selector
        linestyle_layout = QHBoxLayout()
        linestyle_layout.addWidget(QLabel("Line:"))
        self._linestyle_combo = QComboBox()
        from bernardyn.plot.plot_style import DEFAULT_LINE_STYLES
        for ls in DEFAULT_LINE_STYLES:
            self._linestyle_combo.addItem(ls, ls)
        self._linestyle_combo.currentIndexChanged.connect(self._on_style_changed)
        linestyle_layout.addWidget(self._linestyle_combo, 1)
        style_layout.addLayout(linestyle_layout)

        # Add/remove dataset buttons
        btn_row = QHBoxLayout()
        self._add_ds_btn = QPushButton("Add Dataset")
        self._add_ds_btn.clicked.connect(self._on_add_dataset)
        btn_row.addWidget(self._add_ds_btn)

        self._remove_ds_btn = QPushButton("Remove Selected")
        self._remove_ds_btn.clicked.connect(self._on_remove_dataset)
        btn_row.addWidget(self._remove_ds_btn)

        style_layout.addLayout(btn_row)

        style_group.setLayout(style_layout)
        main_layout.addWidget(style_group)

        # --- Generate button ---
        self._generate_btn = QPushButton("Generate Plot")
        self._generate_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        self._generate_btn.clicked.connect(self.generate_requested.emit)
        main_layout.addWidget(self._generate_btn)

        # Spacer to push controls to top
        main_layout.addStretch(1)

        self.setLayout(main_layout)

    def _make_color_item(self, color: str, text: str) -> Any:
        """Create a combo box item with a color preview."""
        from PySide6.QtGui import QIcon, QPixmap, QColor
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(color))
        return QIcon(pixmap), text

    def _on_plot_type_changed(self, index: int) -> None:
        """Handle plot type changes — show/hide relevant controls."""
        self._plot_type = self._plot_type_combo.currentData()

        # Show/hide scale controls (line plots only)
        is_line = self._plot_type == "line"
        for widget in [self._x_log_check, self._y_log_check]:
            if hasattr(self, '_scale_group'):
                pass  # handled below

        # Show/hide color scale controls (image and heatmap)
        is_image_or_heatmap = self._plot_type in ("image", "heatmap")
        if hasattr(self, '_color_scale_combo'):
            self._color_scale_combo.setVisible(is_image_or_heatmap)
        if hasattr(self, '_log_scale_check'):
            self._log_scale_check.setVisible(is_image_or_heatmap)

        # Show/hide z offset controls (waterfall only)
        is_waterfall = self._plot_type == "waterfall"
        if hasattr(self, '_z_offset_spin'):
            self._z_offset_spin.setVisible(is_waterfall)

        # Show/hide dataset styling (line and waterfall only)
        is_stylable = self._plot_type in ("line", "waterfall")
        if hasattr(self, '_dataset_combo'):
            self._dataset_combo.setVisible(is_stylable)

    def _on_template_selected(self, index: int) -> None:
        """Handle template selection from the combo box."""
        if index <= 0:
            return  # "(none)" selected

        template_name = self._template_combo.currentData()
        if template_name and self._on_template_applied:
            self._on_template_applied(template_name)

    def _on_save_current_as_template(self) -> None:
        """Handle 'Save Current as Template' button click."""
        if self._on_save_template:
            self._on_save_template()

    def _on_manage_templates(self) -> None:
        """Handle 'Manage Templates' button click."""
        if self._on_manage_templates_callback:
            self._on_manage_templates_callback()

    def _on_color_scale_changed(self, index: int) -> None:
        """Handle color scale changes."""
        if self._on_scale_changed:
            self._on_scale_changed("color_scale", self._color_scale_combo.currentData())

    def _on_log_scale_changed(self, state: int) -> None:
        """Handle log scale toggle changes."""
        if self._on_scale_changed:
            self._on_scale_changed("log_scale", self._log_scale_check.isChecked())

    def _on_z_offset_changed(self, value: float) -> None:
        """Handle Z offset changes."""
        if self._on_scale_changed:
            self._on_scale_changed("z_offset", value)

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

    def _on_grid_changed(self, state: int) -> None:
        """Handle grid toggle changes."""
        self._show_grid_x = self._grid_x_check.isChecked()
        self._show_grid_y = self._grid_y_check.isChecked()
        if self._on_scale_changed:
            self._on_scale_changed("grid", (self._show_grid_x, self._show_grid_y))

    def _on_legend_changed(self, state: int) -> None:
        """Handle legend toggle changes."""
        self._show_legend = self._legend_check.isChecked()
        if self._on_scale_changed:
            self._on_scale_changed("legend", self._show_legend)

    def _on_slit_smear_changed(self, state: int) -> None:
        """Handle slit-smeared toggle changes."""
        self._show_slit_smear = self._slit_smear_check.isChecked()
        if self._on_scale_changed:
            self._on_scale_changed("slit_smear", self._show_slit_smear)

    def _on_dataset_selected(self, index: int) -> None:
        """Handle dataset selection change in the combo box."""
        pass

    def _on_style_changed(self, index: int) -> None:
        """Handle per-dataset style changes."""
        ds_index = self._dataset_combo.currentIndex()
        if ds_index < 0 or ds_index >= len(self._dataset_styles):
            return

        style = {
            "color": self._color_combo.currentData(),
            "symbol": self._symbol_combo.currentData(),
            "linestyle": self._linestyle_combo.currentData(),
        }
        self._dataset_styles[ds_index] = style
        self.dataset_style_changed.emit(ds_index, style)

    def _on_add_dataset(self) -> None:
        """Add a new dataset entry to the style manager."""
        from bernardyn.plot.plot_style import auto_style

        idx = len(self._dataset_styles)
        default_style = auto_style(idx)
        self._dataset_styles.append(default_style)

        # Add to combo box
        name = f"Dataset {idx + 1}"
        self._dataset_combo.addItem(name)
        self._dataset_combo.setCurrentIndex(idx)

        # Update style controls to match new dataset
        self._update_style_controls(default_style)

    def _on_remove_dataset(self) -> None:
        """Remove the selected dataset from the style manager."""
        idx = self._dataset_combo.currentIndex()
        if idx < 0:
            return

        self._dataset_styles.pop(idx)
        self._dataset_combo.removeItem(idx)

        # Update remaining dataset styles to reassign auto-styles
        for i in range(len(self._dataset_styles)):
            from bernardyn.plot.plot_style import auto_style
            self._dataset_styles[i] = auto_style(i)

        # Update combo box names
        self._dataset_combo.clear()
        for i in range(len(self._dataset_styles)):
            self._dataset_combo.addItem(f"Dataset {i + 1}")

        if self._dataset_combo.count() > 0:
            self._dataset_combo.setCurrentIndex(0)
            self._update_style_controls(self._dataset_styles[0])

    def _update_style_controls(self, style: Dict[str, str]) -> None:
        """Update the style controls to reflect a given style dict."""
        # Set color
        color = style.get("color", DEFAULT_COLORS[0])
        for i in range(self._color_combo.count()):
            item_text = self._color_combo.itemText(i)
            if item_text == color:
                self._color_combo.setCurrentIndex(i)
                break

        # Set symbol
        symbol = style.get("symbol", DEFAULT_SYMBOLS[0])
        sym_idx = self._symbol_combo.findData(symbol)
        if sym_idx >= 0:
            self._symbol_combo.setCurrentIndex(sym_idx)

        # Set line style
        linestyle = style.get("linestyle", DEFAULT_LINE_STYLES[0])
        ls_idx = self._linestyle_combo.findData(linestyle)
        if ls_idx >= 0:
            self._linestyle_combo.setCurrentIndex(ls_idx)

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

    def get_show_grid(self) -> tuple:
        """Get the current grid display state."""
        return (self._show_grid_x, self._show_grid_y)

    def get_show_legend(self) -> bool:
        """Get the current legend display state."""
        return self._show_legend

    def get_show_slit_smear(self) -> bool:
        """Get the current slit-smeared display state."""
        return self._show_slit_smear

    def get_color_scale(self) -> str:
        """Get the current color scale."""
        if self._color_scale_combo is not None:
            return self._color_scale_combo.currentData() or "grayscale"
        return "grayscale"

    def get_log_scale(self) -> bool:
        """Get the current log scale state."""
        if self._log_scale_check is not None:
            return self._log_scale_check.isChecked()
        return False

    def get_z_offset(self) -> float:
        """Get the current Z offset value."""
        if self._z_offset_spin is not None:
            return self._z_offset_spin.value()
        return 1.0

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
        self._grid_x_check.setEnabled(enabled)
        self._grid_y_check.setEnabled(enabled)
        self._legend_check.setEnabled(enabled)
        self._slit_smear_check.setEnabled(enabled and self._has_slit_smear_data)
        if hasattr(self, '_color_scale_combo') and self._color_scale_combo is not None:
            self._color_scale_combo.setEnabled(enabled)
        if hasattr(self, '_log_scale_check') and self._log_scale_check is not None:
            self._log_scale_check.setEnabled(enabled)
        if hasattr(self, '_z_offset_spin') and self._z_offset_spin is not None:
            self._z_offset_spin.setEnabled(enabled)
        if hasattr(self, '_template_combo') and self._template_combo is not None:
            self._template_combo.setEnabled(enabled)
        if hasattr(self, '_save_template_btn') and self._save_template_btn is not None:
            self._save_template_btn.setEnabled(enabled)
        if hasattr(self, '_manage_templates_btn') and self._manage_templates_btn is not None:
            self._manage_templates_btn.setEnabled(enabled)
        self._dataset_combo.setEnabled(enabled)
        self._color_combo.setEnabled(enabled)
        self._symbol_combo.setEnabled(enabled)
        self._linestyle_combo.setEnabled(enabled)
        self._add_ds_btn.setEnabled(enabled)
        self._remove_ds_btn.setEnabled(enabled)
        self._auto_range_btn.setEnabled(enabled)
        self._generate_btn.setEnabled(enabled)

    def set_template_manager(self, manager: TemplateManager) -> None:
        """Set the template manager for this controls panel.

        Args:
            manager: TemplateManager instance to use for template operations.
        """
        self._template_manager = manager

    def refresh_templates(self) -> None:
        """Refresh the template combo box with current templates."""
        if self._template_combo is None or self._template_manager is None:
            return

        # Save current selection
        current_data = self._template_combo.currentData()

        # Clear and rebuild
        self._template_combo.clear()
        self._template_combo.addItem("(none)", "")

        templates = self._template_manager.list_templates()
        for name in templates:
            self._template_combo.addItem(name, name)

        # Restore selection if it still exists
        if current_data:
            idx = self._template_combo.findData(current_data)
            if idx >= 0:
                self._template_combo.setCurrentIndex(idx)

    def apply_template(self, name: str) -> bool:
        """Apply a template to the current controls.

        Args:
            name: Template name to apply.

        Returns:
            True if applied successfully, False otherwise.
        """
        if self._template_manager is None:
            return False

        data = self._template_manager.load_template(name)
        if data is None:
            return False

        # Apply template settings to controls
        self._plot_type = data.get("plot_type", "line")

        # Set plot type combo
        idx = self._plot_type_combo.findData(self._plot_type)
        if idx >= 0:
            self._plot_type_combo.setCurrentIndex(idx)

        # Set scale controls
        x_log = data.get("x_log", True)
        y_log = data.get("y_log", True)

        x_idx = self._x_log_check.findData(x_log)
        if x_idx >= 0:
            self._x_log_check.setCurrentIndex(x_idx)

        y_idx = self._y_log_check.findData(y_log)
        if y_idx >= 0:
            self._y_log_check.setCurrentIndex(y_idx)

        # Set grid/legend
        self._show_grid_x = data.get("show_grid_x", False)
        self._show_grid_y = data.get("show_grid_y", False)
        self._show_legend = data.get("show_legend", True)

        if hasattr(self, '_grid_x_check'):
            self._grid_x_check.setChecked(self._show_grid_x)
        if hasattr(self, '_grid_y_check'):
            self._grid_y_check.setChecked(self._show_grid_y)
        if hasattr(self, '_legend_check'):
            self._legend_check.setChecked(self._show_legend)

        # Set color scale (for image/heatmap)
        if hasattr(self, '_color_scale_combo'):
            color_scale = data.get("color_scale", "grayscale")
            idx = self._color_scale_combo.findData(color_scale)
            if idx >= 0:
                self._color_scale_combo.setCurrentIndex(idx)

        # Set Z offset (for waterfall)
        if hasattr(self, '_z_offset_spin'):
            z_offset = data.get("z_offset", 1.0)
            self._z_offset_spin.setValue(z_offset)

        # Set axis ranges
        x_range = data.get("x_range", [0.0, 1.0])
        y_range = data.get("y_range", [0.0, 1.0])
        if len(x_range) >= 2:
            self._x_min_spin.setValue(x_range[0])
            self._x_max_spin.setValue(x_range[1])
        if len(y_range) >= 2:
            self._y_min_spin.setValue(y_range[0])
            self._y_max_spin.setValue(y_range[1])

        # Set dataset styles
        dataset_styles = data.get("dataset_styles", [])
        self.set_dataset_count(len(dataset_styles))
        if dataset_styles:
            self._dataset_styles = list(dataset_styles)

        # Set slit smear toggle
        self._show_slit_smear = data.get("slit_smear_enabled", False)
        if hasattr(self, '_slit_smear_check'):
            self._slit_smear_check.setChecked(self._show_slit_smear)

        # Update plot type visibility
        self._on_plot_type_changed(self._plot_type_combo.currentIndex())

        return True

    def get_current_template_data(self) -> Dict[str, Any]:
        """Get the current plot state as a template data dictionary.

        Returns:
            Dictionary with all current control settings suitable for saving as a template.
        """
        return {
            "plot_type": self._plot_type,
            "x_log": self._x_log,
            "y_log": self._y_log,
            "show_grid_x": self._show_grid_x,
            "show_grid_y": self._show_grid_y,
            "show_legend": self._show_legend,
            "color_scale": self.get_color_scale(),
            "z_offset": self.get_z_offset(),
            "x_range": [self._x_min_spin.value(), self._x_max_spin.value()],
            "y_range": [self._y_min_spin.value(), self._y_max_spin.value()],
            "dataset_styles": list(self._dataset_styles),
            "slit_smear_enabled": self._show_slit_smear,
        }

    def set_slit_smear_available(self, available: bool) -> None:
        """Enable or disable the slit-smeared toggle."""
        self._has_slit_smear_data = available
        self._slit_smear_check.setEnabled(available)

    def set_dataset_count(self, count: int) -> None:
        """Update the dataset combo box with the correct number of entries."""
        # Clear and rebuild
        self._dataset_combo.clear()
        self._dataset_styles = []

        from bernardyn.plot.plot_style import auto_style, DEFAULT_COLORS, DEFAULT_SYMBOLS, DEFAULT_LINE_STYLES

        for i in range(count):
            style = auto_style(i)
            self._dataset_styles.append(style)
            self._dataset_combo.addItem(f"Dataset {i + 1}")

        if count > 0:
            self._dataset_combo.setCurrentIndex(0)
            self._update_style_controls(self._dataset_styles[0])

    def get_dataset_styles(self) -> List[Dict[str, str]]:
        """Get the current per-dataset style list."""
        return list(self._dataset_styles)
