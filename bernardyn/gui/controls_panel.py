"""Right panel: plot type, styles, axes controls for Bernardyn.

Provides the plot customization interface where users can:
  - Select plot type (line, image, waterfall, heatmap)
  - Toggle log/lin scales for X and Y axes
  - Set axis ranges
  - Add/remove datasets from the plot
  - Toggle grid and legend display
  - Manage per-dataset styling (color, symbol, line style)
  - Edit legend names for each dataset
  - Toggle slit-smeared/desmeared data display
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from bernardyn.template.manager import TemplateManager, get_default_manager
from bernardyn.plot.plot_style import DEFAULT_COLORS, DEFAULT_LINE_STYLES, DEFAULT_SYMBOLS

logger = logging.getLogger(__name__)


class ControlsPanel(QGroupBox):
    """Right panel for plot customization controls.

    Provides controls for:
      - Plot type selection (line, image, waterfall, heatmap)
      - Log/lin scale toggles for X and Y axes
      - Axis range inputs (min/max)
      - Grid, legend, error bars toggles
      - Per-dataset styling (color, symbol, line style) with editable legends
      - Slit-smeared/desmeared data toggle
      - Generate plot button
    """

    # Signal emitted when user clicks "Generate Plot"
    generate_requested = Signal()

    # Signal emitted when a dataset style is changed
    dataset_style_changed = Signal(int, dict)

    # Signal emitted when a legend name is changed
    legend_changed = Signal(int, str)

    def __init__(self, parent: Optional[Any] = None):
        super().__init__("Plot Controls", parent)

        self._plot_type: str = "line"  # 'line', 'image', 'waterfall', 'heatmap'
        self._x_log: bool = True
        self._y_log: bool = True

        # Waterfall-specific controls
        self._z_offset_spin: Optional[QDoubleSpinBox] = None

        # Heatmap/image color scale
        self._color_scale_combo: Optional[QComboBox] = None
        self._log_scale_check: Optional[QCheckBox] = None

        # Display state flags
        self._show_grid_x: bool = False
        self._show_grid_y: bool = False
        self._show_legend: bool = True
        self._show_slit_smear: bool = False
        self._show_error_bars: bool = True

        # Per-dataset styling: list of dicts with 'color', 'symbol', 'linestyle'
        self._dataset_styles: List[Dict[str, str]] = []

        # Track dataset count to avoid unnecessary resets
        self._current_dataset_count: int = 0

        # Legend name inputs (one per dataset)
        self._legend_inputs: List[QLineEdit] = []
        self._legend_rows: List[QHBoxLayout] = []

        # Callbacks (set by main window)
        self._on_scale_changed: Optional[Any] = None
        self._on_template_applied: Optional[Any] = None
        self._on_save_template: Optional[Any] = None
        self._on_manage_templates_callback: Optional[Any] = None

        # Template manager reference (set by main window)
        self._template_manager: Optional[TemplateManager] = None

        # Reference to slit smear availability flag
        self._has_slit_smear_data: bool = False

        self._setup_ui()
        # Apply initial visibility based on default plot type (line)
        self._apply_visibility_for_plot_type()

    def _setup_ui(self) -> None:
        """Build the UI layout with new organization."""
        main_layout = QVBoxLayout()

        # ===================================================================
        # 1. Plot Type widget (top)
        # ===================================================================
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

        # ===================================================================
        # 2. Scale widget (under Plot Type)
        # ===================================================================
        scale_group = QGroupBox("Scale")
        scale_layout = QVBoxLayout()

        # X and Y axis log/lin choices on one line (50% each)
        axis_scale_row = QHBoxLayout()

        x_scale_layout = QHBoxLayout()
        x_scale_layout.addWidget(QLabel("X axis:"))
        self._x_log_check = QComboBox()
        self._x_log_check.addItem("Log", True)
        self._x_log_check.addItem("Lin", False)
        self._x_log_check.currentIndexChanged.connect(self._on_x_scale_changed)
        x_scale_layout.addWidget(self._x_log_check, 1)
        axis_scale_row.addLayout(x_scale_layout)

        y_scale_layout = QHBoxLayout()
        y_scale_layout.addWidget(QLabel("Y axis:"))
        self._y_log_check = QComboBox()
        self._y_log_check.addItem("Log", True)
        self._y_log_check.addItem("Lin", False)
        self._y_log_check.currentIndexChanged.connect(self._on_y_scale_changed)
        y_scale_layout.addWidget(self._y_log_check, 1)
        axis_scale_row.addLayout(y_scale_layout)

        scale_layout.addLayout(axis_scale_row)

        # Axis range inputs
        range_group = QGroupBox("Axis Ranges")
        range_layout = QVBoxLayout()

        x_range_layout = QHBoxLayout()
        x_range_layout.addWidget(QLabel("X min:"))
        self._x_min_spin = QDoubleSpinBox()
        self._x_min_spin.setRange(-1e30, 1e30)
        self._x_min_spin.setDecimals(6)
        self._x_min_spin.valueChanged.connect(self._on_x_range_changed)
        x_range_layout.addWidget(self._x_min_spin)
        x_range_layout.addWidget(QLabel("X max:"))
        self._x_max_spin = QDoubleSpinBox()
        self._x_max_spin.setRange(-1e30, 1e30)
        self._x_max_spin.setDecimals(6)
        self._x_max_spin.valueChanged.connect(self._on_x_range_changed)
        x_range_layout.addWidget(self._x_max_spin)
        range_layout.addLayout(x_range_layout)

        y_range_layout = QHBoxLayout()
        y_range_layout.addWidget(QLabel("Y min:"))
        self._y_min_spin = QDoubleSpinBox()
        self._y_min_spin.setRange(-1e30, 1e30)
        self._y_min_spin.setDecimals(6)
        self._y_min_spin.valueChanged.connect(self._on_y_range_changed)
        y_range_layout.addWidget(self._y_min_spin)
        y_range_layout.addWidget(QLabel("Y max:"))
        self._y_max_spin = QDoubleSpinBox()
        self._y_max_spin.setRange(-1e30, 1e30)
        self._y_max_spin.setDecimals(6)
        self._y_max_spin.valueChanged.connect(self._on_y_range_changed)
        y_range_layout.addWidget(self._y_max_spin)
        range_layout.addLayout(y_range_layout)

        # Auto-range button
        self._auto_range_btn = QPushButton("Auto Range")
        self._auto_range_btn.clicked.connect(self._on_auto_range)
        range_layout.addWidget(self._auto_range_btn)

        range_group.setLayout(range_layout)
        scale_layout.addWidget(range_group)

        # Color scale selector (for image and heatmap plots) - initially hidden
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
        color_scale_group.setVisible(False)  # Hidden by default for line plots
        scale_layout.addWidget(color_scale_group)

        # Z Offset section (for waterfall plots) - initially hidden
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
        z_offset_group.setVisible(False)  # Hidden by default for line plots
        scale_layout.addWidget(z_offset_group)

        scale_group.setLayout(scale_layout)
        main_layout.addWidget(scale_group)

        # ===================================================================
        # 3. Display widget (under Scale)
        # ===================================================================
        display_group = QGroupBox("Display")
        display_layout = QVBoxLayout()

        self._grid_x_check = QCheckBox("X Grid")
        self._grid_x_check.stateChanged.connect(self._on_grid_changed)
        display_layout.addWidget(self._grid_x_check)

        self._grid_y_check = QCheckBox("Y Grid")
        self._grid_y_check.stateChanged.connect(self._on_grid_changed)
        display_layout.addWidget(self._grid_y_check)

        self._legend_check = QCheckBox("Show Legend")
        self._legend_check.setChecked(True)
        self._legend_check.stateChanged.connect(self._on_legend_changed)
        display_layout.addWidget(self._legend_check)

        # Slit-smeared toggle (initially disabled)
        self._slit_smear_check = QCheckBox("Show Slit-Smeared")
        self._slit_smear_check.setEnabled(False)
        self._slit_smear_check.stateChanged.connect(self._on_slit_smear_changed)
        display_layout.addWidget(self._slit_smear_check)

        # Error bars toggle (initially enabled)
        self._error_bars_check = QCheckBox("Show Error Bars")
        self._error_bars_check.setChecked(True)
        self._error_bars_check.stateChanged.connect(self._on_error_bars_changed)
        display_layout.addWidget(self._error_bars_check)

        display_group.setLayout(display_layout)
        main_layout.addWidget(display_group)

        # ===================================================================
        # 4. Dataset Styles widget (Color, Symbol, Line on one line)
        # ===================================================================
        style_group = QGroupBox("Dataset Styles")
        style_layout = QVBoxLayout()
        self._style_group = style_group

        # Dataset selector row
        ds_select_layout = QHBoxLayout()
        ds_select_layout.addWidget(QLabel("Dataset:"))
        self._dataset_combo = QComboBox()
        self._dataset_combo.currentIndexChanged.connect(self._on_dataset_selected)
        ds_select_layout.addWidget(self._dataset_combo, 1)
        style_layout.addLayout(ds_select_layout)

        # Color, Symbol, Line on one line (33% each)
        self._style_row = QHBoxLayout()

        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        self._color_combo = QComboBox()
        for c in DEFAULT_COLORS:
            # Create color preview icon
            pixmap = QPixmap(20, 20)
            pixmap.fill(QColor(c))
            icon = QIcon(pixmap)
            # Add item with text and explicit data using setItemData
            self._color_combo.addItem(icon, c)
            idx = self._color_combo.count() - 1
            self._color_combo.setItemData(idx, c, Qt.UserRole + 1)
        self._color_combo.currentIndexChanged.connect(self._on_style_changed)
        color_layout.addWidget(self._color_combo, 1)
        self._style_row.addLayout(color_layout)

        symbol_layout = QHBoxLayout()
        symbol_layout.addWidget(QLabel("Symbol:"))
        self._symbol_combo = QComboBox()
        for s in DEFAULT_SYMBOLS:
            self._symbol_combo.addItem(s, s)
        self._symbol_combo.currentIndexChanged.connect(self._on_style_changed)
        symbol_layout.addWidget(self._symbol_combo, 1)
        self._style_row.addLayout(symbol_layout)

        linestyle_layout = QHBoxLayout()
        linestyle_layout.addWidget(QLabel("Line:"))
        self._linestyle_combo = QComboBox()
        for ls in DEFAULT_LINE_STYLES:
            self._linestyle_combo.addItem(ls, ls)
        self._linestyle_combo.currentIndexChanged.connect(self._on_style_changed)
        linestyle_layout.addWidget(self._linestyle_combo, 1)
        self._style_row.addLayout(linestyle_layout)

        style_layout.addLayout(self._style_row)

        # Legend name inputs (one per dataset, added dynamically)
        self._legend_label = QLabel("Legend Names:")
        style_layout.addWidget(self._legend_label)
        self._legends_scroll = QVBoxLayout()
        style_layout.addLayout(self._legends_scroll)

        # Add/remove dataset buttons on one line (50% each)
        btn_row = QHBoxLayout()
        self._add_ds_btn = QPushButton("Add Dataset")
        self._add_ds_btn.clicked.connect(self._on_add_dataset)
        btn_row.addWidget(self._add_ds_btn, 1)

        self._remove_ds_btn = QPushButton("Remove Selected")
        self._remove_ds_btn.clicked.connect(self._on_remove_dataset)
        btn_row.addWidget(self._remove_ds_btn, 1)

        style_layout.addLayout(btn_row)

        style_group.setLayout(style_layout)
        main_layout.addWidget(style_group)

        # ===================================================================
        # 5. Templates widget (bottom, buttons on one line)
        # ===================================================================
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

        # Save and Manage buttons on one line (50% each)
        btn_row = QHBoxLayout()
        self._save_template_btn = QPushButton("Save Current as Template...")
        self._save_template_btn.clicked.connect(self._on_save_current_as_template)
        btn_row.addWidget(self._save_template_btn, 1)

        self._manage_templates_btn = QPushButton("Manage Templates...")
        self._manage_templates_btn.clicked.connect(self._on_manage_templates)
        btn_row.addWidget(self._manage_templates_btn, 1)

        template_layout.addLayout(btn_row)

        template_group.setLayout(template_layout)
        main_layout.addWidget(template_group)

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
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(color))
        return QIcon(pixmap), text

    def _apply_visibility_for_plot_type(self) -> None:
        """Show/hide widgets based on current plot type."""
        is_image_or_heatmap = self._plot_type in ("image", "heatmap")
        is_waterfall = self._plot_type == "waterfall"

        # Color scale group (image/heatmap only)
        if hasattr(self, '_color_scale_combo') and self._color_scale_combo is not None:
            self._color_scale_combo.setVisible(is_image_or_heatmap)
        if hasattr(self, '_log_scale_check') and self._log_scale_check is not None:
            self._log_scale_check.setVisible(is_image_or_heatmap)
        # Show/hide the entire color scale group
        if hasattr(self, 'color_scale_group'):
            self.color_scale_group.setVisible(is_image_or_heatmap)

        # Z offset group (waterfall only)
        if hasattr(self, '_z_offset_spin') and self._z_offset_spin is not None:
            self._z_offset_spin.setVisible(is_waterfall)
        if hasattr(self, 'z_offset_group'):
            self.z_offset_group.setVisible(is_waterfall)

        # Dataset styling (line and waterfall only)
        is_stylable = self._plot_type in ("line", "waterfall")
        if hasattr(self, '_dataset_combo') and self._dataset_combo is not None:
            self._dataset_combo.setVisible(is_stylable)
        if hasattr(self, '_style_row') and self._style_row is not None:
            self._style_row.setVisible(is_stylable)
        if hasattr(self, '_legend_label') and self._legend_label is not None:
            self._legend_label.setVisible(is_stylable)
        if hasattr(self, '_legends_scroll') and self._legends_scroll is not None:
            self._legends_scroll.setVisible(is_stylable)
        if hasattr(self, '_style_group') and self._style_group is not None:
            self._style_group.setVisible(is_stylable)

    def _on_plot_type_changed(self, index: int) -> None:
        """Handle plot type changes — show/hide relevant controls."""
        self._plot_type = self._plot_type_combo.currentData()
        self._apply_visibility_for_plot_type()

        # Notify scale changes for log mode updates
        if self._on_scale_changed:
            self._on_scale_changed("x", self._x_log)
            self._on_scale_changed("y", self._y_log)

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

    def _on_error_bars_changed(self, state: int) -> None:
        """Handle error bars toggle changes."""
        self._show_error_bars = self._error_bars_check.isChecked()
        if self._on_scale_changed:
            self._on_scale_changed("error_bars", self._show_error_bars)

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

    def _on_x_range_changed(self, value: float) -> None:
        """Handle X axis range changes."""
        if self._on_scale_changed:
            xmin = self._x_min_spin.value()
            xmax = self._x_max_spin.value()
            self._on_scale_changed("x_range", (xmin, xmax))

    def _on_y_range_changed(self, value: float) -> None:
        """Handle Y axis range changes."""
        if self._on_scale_changed:
            ymin = self._y_min_spin.value()
            ymax = self._y_max_spin.value()
            self._on_scale_changed("y_range", (ymin, ymax))

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
        if 0 <= index < len(self._dataset_styles):
            self._update_style_controls(self._dataset_styles[index])

    def _on_style_changed(self, index: int) -> None:
        """Handle per-dataset style changes."""
        ds_index = self._dataset_combo.currentIndex()
        if ds_index < 0 or ds_index >= len(self._dataset_styles):
            return

        # Get the actual color value - use itemData with UserRole+1 where we stored it
        color = self._color_combo.itemData(self._color_combo.currentIndex(), Qt.UserRole + 1)
        if not color:
            # Fallback to text (which is the hex string)
            color = self._color_combo.currentText() or DEFAULT_COLORS[0]
        symbol = self._symbol_combo.currentData() or DEFAULT_SYMBOLS[0]
        linestyle = self._linestyle_combo.currentData() or DEFAULT_LINE_STYLES[0]

        style = {
            "color": color,
            "symbol": symbol,
            "linestyle": linestyle,
        }
        self._dataset_styles[ds_index] = style
        # Emit signal to update plot items in place (no full re-render)
        self.dataset_style_changed.emit(ds_index, style)

    def _on_legend_input_changed(self, index: int, new_text: str) -> None:
        """Handle legend name change for a dataset."""
        self.legend_changed.emit(index, new_text)

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

        # Add legend input for new dataset
        self._add_legend_input(idx, name)

        # Update style controls to match new dataset
        self._update_style_controls(default_style)

    def _on_remove_dataset(self) -> None:
        """Remove the selected dataset from the style manager."""
        idx = self._dataset_combo.currentIndex()
        if idx < 0:
            return

        # Preserve existing legend names before rebuilding
        old_legend_names = self.get_legend_names()

        # Remove from styles list
        self._dataset_styles.pop(idx)

        # Remove legend input
        self._remove_legend_input(idx)

        # Rebuild remaining dataset styles with auto-styles
        for i in range(len(self._dataset_styles)):
            from bernardyn.plot.plot_style import auto_style
            self._dataset_styles[i] = auto_style(i)

        # Rebuild combo box names
        self._dataset_combo.clear()
        for i in range(len(self._dataset_styles)):
            self._dataset_combo.addItem(f"Dataset {i + 1}")

        # Rebuild all legend inputs preserving existing names
        self._clear_all_legend_inputs()
        for i in range(len(self._dataset_styles)):
            # Preserve name if it exists for this index (skip removed one)
            if i < len(old_legend_names):
                preserved_name = old_legend_names[i]
                # If we're after the removed index, shift names down
                if i >= idx:
                    # Names are already shifted by removal, just use as-is
                    default_name = preserved_name if preserved_name.strip() else f"Dataset {i + 1}"
                else:
                    default_name = preserved_name if preserved_name.strip() else f"Dataset {i + 1}"
            else:
                default_name = f"Dataset {i + 1}"
            self._add_legend_input(i, default_name)

        if self._dataset_combo.count() > 0:
            self._dataset_combo.setCurrentIndex(0)
            self._update_style_controls(self._dataset_styles[0])

    def _add_legend_input(self, index: int, default_name: str) -> None:
        """Add a legend name input line for the given dataset index."""
        row_layout = QHBoxLayout()
        row_layout.addWidget(QLabel(f"  {index + 1}. "))

        legend_input = QLineEdit(default_name)
        legend_input.setPlaceholderText(f"Legend for dataset {index + 1}")
        legend_input.textChanged.connect(
            lambda text, idx=index: self._on_legend_input_changed(idx, text)
        )
        row_layout.addWidget(legend_input, 1)

        self._legends_scroll.addLayout(row_layout)
        self._legend_inputs.append(legend_input)
        self._legend_rows.append(row_layout)

    def _remove_legend_input(self, index: int) -> None:
        """Remove the legend input for the given dataset index."""
        if 0 <= index < len(self._legend_inputs):
            legend_input = self._legend_inputs.pop(index)
            row_layout = self._legend_rows.pop(index)
            
            # Remove the row layout from the scroll layout
            self._legends_scroll.removeItem(row_layout)
            # Delete the layout and its widgets
            while row_layout.count():
                child = row_layout.takeAt(0)
                if child.widget():
                    child.widget().setParent(None)
                    child.widget().deleteLater()
            
            legend_input.setParent(None)
            legend_input.deleteLater()

    def _clear_all_legend_inputs(self) -> None:
        """Clear all legend input widgets from the layout."""
        # Clear in reverse order to avoid index issues
        for i in range(len(self._legend_inputs) - 1, -1, -1):
            row_layout = self._legend_rows[i]
            legend_input = self._legend_inputs[i]
            
            # Remove the row layout from the scroll layout
            self._legends_scroll.removeItem(row_layout)
            # Delete the layout and its widgets
            while row_layout.count():
                child = row_layout.takeAt(0)
                if child.widget():
                    child.widget().setParent(None)
                    child.widget().deleteLater()
        
        self._legend_inputs.clear()
        self._legend_rows.clear()

    def _rebuild_legend_inputs(self, count: int) -> None:
        """Rebuild all legend input widgets to match the given dataset count.

        Clears existing inputs and creates new ones with preserved text where possible.
        """
        # Save current texts before clearing
        old_texts = [inp.text() for inp in self._legend_inputs]

        # Clear all existing inputs
        self._clear_all_legend_inputs()

        # Rebuild with preserved or default names
        for i in range(count):
            default_name = f"Dataset {i + 1}"
            if i < len(old_texts) and old_texts[i]:
                default_name = old_texts[i]
            self._add_legend_input(i, default_name)

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

    def _update_legend_inputs_from_styles(self, count: int) -> None:
        """Update legend inputs to match the current dataset count.

        Preserves existing user-entered legend names when possible.
        """
        # Get current legend texts before rebuilding
        old_texts = [inp.text() for inp in self._legend_inputs]

        # Clear existing inputs
        self._clear_all_legend_inputs()

        # Rebuild with preserved or default names
        for i in range(count):
            default_name = f"Dataset {i + 1}"
            if i < len(old_texts) and old_texts[i]:
                default_name = old_texts[i]
            self._add_legend_input(i, default_name)

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
        self._y_max_spin.setEnabled(enabled)
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
        # Enable/disable legend inputs
        for inp in self._legend_inputs:
            inp.setEnabled(enabled)

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
        if dataset_styles:
            self._dataset_styles = list(dataset_styles)
            self._update_legend_inputs_from_styles(len(dataset_styles))

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
        # Collect legend names from inputs
        legend_names = [inp.text() for inp in self._legend_inputs]

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
            "legend_names": legend_names,
            "slit_smear_enabled": self._show_slit_smear,
            "error_bars_enabled": self._show_error_bars,
        }

    def set_slit_smear_available(self, available: bool) -> None:
        """Enable or disable the slit-smeared toggle."""
        self._has_slit_smear_data = available
        self._slit_smear_check.setEnabled(available)

    def set_dataset_count_if_changed(self, count: int) -> None:
        """Update the dataset combo box with the correct number of entries.

        Only rebuilds if count has changed to preserve user-defined styles.
        This is the primary method for updating dataset count without unnecessary resets.
        """
        if count == self._current_dataset_count:
            return  # No change, preserve existing styles

        # Save current user-defined styles before rebuilding
        old_styles = list(self._dataset_styles) if self._current_dataset_count > 0 else []

        # Clear and rebuild
        self._dataset_combo.clear()
        self._dataset_styles = []

        from bernardyn.plot.plot_style import auto_style, DEFAULT_COLORS, DEFAULT_SYMBOLS, DEFAULT_LINE_STYLES

        for i in range(count):
            # Try to preserve existing style if available, otherwise use auto
            if i < len(old_styles):
                style = old_styles[i]
            else:
                style = auto_style(i)
            self._dataset_styles.append(style)
            self._dataset_combo.addItem(f"Dataset {i + 1}")

        if count > 0:
            self._dataset_combo.setCurrentIndex(0)
            self._update_style_controls(self._dataset_styles[0])

        # Update legend inputs to match new count
        self._update_legend_inputs_from_styles(count)

        # Update current count tracker
        self._current_dataset_count = count

    def set_dataset_count(self, count: int) -> None:
        """Update the dataset combo box with the correct number of entries.

        Only rebuilds if count has changed to preserve user-defined styles.
        """
        self.set_dataset_count_if_changed(count)

    def get_dataset_styles(self) -> List[Dict[str, str]]:
        """Get the current per-dataset style list."""
        return list(self._dataset_styles)

    def get_legend_names(self) -> List[str]:
        """Get the current legend names from input fields."""
        return [inp.text() for inp in self._legend_inputs]

    def get_show_error_bars(self) -> bool:
        """Get the current error bars visibility state."""
        return self._show_error_bars

    def set_show_error_bars(self, show: bool) -> None:
        """Set the error bars visibility state."""
        self._show_error_bars = show
        if hasattr(self, '_error_bars_check'):
            self._error_bars_check.setChecked(show)
