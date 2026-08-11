"""Main window for Bernardyn.

Wires together the data panel (left), plot widget (center), and
controls panel (right) into a functional GUI. Handles the data
loading pipeline: file selection -> load -> plot display.

Supports multi-graph layouts, per-dataset styling, grid/legend
toggles, and slit-smeared/desmeared data display.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QAction,
    QMenuBar,
)

from bernardyn.data.loader import get_default_dispatcher
from bernardyn.gui.controls_panel import ControlsPanel
from bernardyn.gui.data_panel import DataPanel
from bernardyn.gui.plot_widget import PlotWidget
from bernardyn.template.manager import TemplateManager, get_default_manager

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window for Bernardyn.

    Layout:
      - Menu bar with File, Graph, and Template menus
      - Left dock: DataPanel (file browser, listbox, sort/filter)
      - Center: QTabWidget of PlotWidgets (multi-graph support)
      - Right dock: ControlsPanel (plot type, scales, ranges, styles, templates)

    The window wires signals between panels to create a complete
    data loading and plotting pipeline.
    """

    def __init__(self, parent: Optional[Any] = None):
        super().__init__(parent)

        self.setWindowTitle("Bernardyn")
        self.resize(1400, 900)

        # Data loader dispatcher
        self._loader = get_default_dispatcher()

        # Template manager
        self._template_manager = get_default_manager()

        # Current loaded data (for re-rendering)
        self._loaded_data: Dict[str, Any] = {}

        # Multi-graph support: list of (name, plot_widget, controls) tuples
        self._graphs: List[tuple] = []

        # Build the UI
        self._setup_ui()
        self._wire_signals()

    def _setup_ui(self) -> None:
        """Build the main window layout."""
        # --- Menu bar ---
        self._setup_menu_bar()

        # Central widget: QTabWidget for multi-graph support
        self._tab_widget = QTabWidget()
        self.setCentralWidget(self._tab_widget)

        # Create the first graph tab by default
        self._create_new_graph("Graph 1")

        # Left dock: Data panel
        self._data_panel = DataPanel()
        self._data_dock = QDockWidget("Data Files", self)
        self._data_dock.setWidget(self._data_panel)
        self._data_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._data_dock)

        # Right dock: Controls panel
        self._controls_panel = ControlsPanel()
        self._controls_dock = QDockWidget("Plot Controls", self)
        self._controls_dock.setWidget(self._controls_panel)
        self._controls_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, self._controls_dock)

    def _setup_menu_bar(self) -> None:
        """Build the menu bar with File and Graph menus."""
        menubar = self.menuBar()

        # --- File menu ---
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open File...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_action)

        open_folder_action = QAction("Open Folder...", self)
        open_folder_action.setShortcut("Ctrl+Shift+O")
        open_folder_action.triggered.connect(self._on_open_folder)
        file_menu.addAction(open_folder_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Graph menu ---
        graph_menu = menubar.addMenu("Graph")

        add_graph_action = QAction("New Graph...", self)
        add_graph_action.setShortcut("Ctrl+T")
        add_graph_action.triggered.connect(self._on_new_graph)
        graph_menu.addAction(add_graph_action)

        close_graph_action = QAction("Close Graph", self)
        close_graph_action.setShortcut("Ctrl+W")
        close_graph_action.triggered.connect(self._on_close_graph)
        graph_menu.addAction(close_graph_action)

        graph_menu.addSeparator()

        # Graph list submenu
        self._graph_list_menu = QMenu("Switch to Graph", self)
        graph_menu.addMenu(self._graph_list_menu)

        # --- Template menu ---
        template_menu = menubar.addMenu("Template")

        save_template_action = QAction("Save Current as Template...", self)
        save_template_action.setShortcut("Ctrl+Shift+S")
        save_template_action.triggered.connect(self._on_save_current_as_template)
        template_menu.addAction(save_template_action)

        manage_templates_action = QAction("Manage Templates...", self)
        manage_templates_action.setShortcut("Ctrl+M")
        manage_templates_action.triggered.connect(self._on_manage_templates)
        template_menu.addAction(manage_templates_action)

        # --- Export menu ---
        export_menu = menubar.addMenu("Export")

        export_png_action = QAction("Export as PNG...", self)
        export_png_action.setShortcut("Ctrl+Shift+E")
        export_png_action.triggered.connect(lambda: self._on_export_file("png"))
        export_menu.addAction(export_png_action)

        export_svg_action = QAction("Export as SVG...", self)
        export_svg_action.triggered.connect(lambda: self._on_export_file("svg"))
        export_menu.addAction(export_svg_action)

        export_pdf_action = QAction("Export as PDF...", self)
        export_pdf_action.triggered.connect(lambda: self._on_export_file("pdf"))
        export_menu.addAction(export_pdf_action)

        export_menu.addSeparator()

        copy_clipboard_action = QAction("Copy to Clipboard", self)
        copy_clipboard_action.setShortcut("Ctrl+C")
        copy_clipboard_action.triggered.connect(self._on_copy_to_clipboard)
        export_menu.addAction(copy_clipboard_action)

        export_menu.addSeparator()

        save_project_action = QAction("Save Project...", self)
        save_project_action.setShortcut("Ctrl+Shift+S")
        save_project_action.triggered.connect(self._on_save_project)
        export_menu.addAction(save_project_action)

    def _create_new_graph(self, name: str) -> tuple:
        """Create a new graph tab with its own plot widget and controls.

        Returns:
            Tuple of (name, plot_widget, controls_panel).
        """
        plot_widget = PlotWidget()
        controls = ControlsPanel()

        # Wire this graph's controls to the plot widget
        controls.set_on_scale_changed(
            lambda kind, value: self._on_graph_control_changed(name, kind, value)
        )
        controls.generate_requested.connect(
            lambda: self._on_graph_generate(name)
        )

        # Wire template callbacks for this graph's controls
        controls.set_template_manager(self._template_manager)
        controls._on_template_applied = lambda tmpl_name: self._on_apply_template(name, tmpl_name)
        controls._on_save_template = lambda: self._on_save_current_as_template()
        controls._on_manage_templates_callback = lambda: self._on_manage_templates()

        # Add tab
        idx = self._tab_widget.addTab(plot_widget, name)
        self._tab_widget.setCurrentIndex(idx)

        graph_info = (name, plot_widget, controls)
        self._graphs.append(graph_info)

        # Update graph list menu
        self._update_graph_list_menu()

        return graph_info

    def _get_current_graph(self) -> Optional[tuple]:
        """Get the currently active graph tuple."""
        if not self._graphs:
            return None
        current_idx = self._tab_widget.currentIndex()
        if 0 <= current_idx < len(self._graphs):
            return self._graphs[current_idx]
        # Fallback: last graph
        return self._graphs[-1] if self._graphs else None

    def _get_current_plot_widget(self) -> PlotWidget:
        """Get the plot widget for the currently active graph."""
        graph = self._get_current_graph()
        if graph:
            return graph[1]
        # Fallback to first graph's plot widget
        if self._graphs:
            return self._graphs[0][1]
        return PlotWidget()

    def _get_current_controls(self) -> ControlsPanel:
        """Get the controls panel for the currently active graph."""
        graph = self._get_current_graph()
        if graph:
            return graph[2]
        return self._controls_panel

    def _wire_signals(self) -> None:
        """Connect signals between UI components."""
        # Data panel -> load and plot selected files (applied to current graph)
        self._data_panel.files_selected.connect(self._on_files_selected)

    def _update_graph_list_menu(self) -> None:
        """Update the graph list submenu in the menu bar."""
        self._graph_list_menu.clear()
        for i, (name, plot_widget, controls) in enumerate(self._graphs):
            action = self._graph_list_menu.addAction(name)
            action.triggered.connect(lambda checked, idx=i: self._switch_to_graph(idx))

    def _switch_to_graph(self, index: int) -> None:
        """Switch the active graph tab to the given index."""
        if 0 <= index < len(self._graphs):
            self._tab_widget.setCurrentIndex(index)

    def _on_open_file(self) -> None:
        """Handle File > Open File menu action."""
        from PySide6.QtWidgets import QFileDialog

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Data File", "",
            "HDF5 Files (*.hdf *.h5);;ASCII Files (*.txt *.csv);;All Files (*)",
        )
        if filepath:
            self._data_panel.set_folder("/".join(filepath.split("/")[:-1]))
            # Select the file in the listbox and trigger loading
            self._data_panel.set_regex_filter("^" + filepath.split("/")[-1] + "$")
            self._on_files_selected([filepath])

    def _on_open_folder(self) -> None:
        """Handle File > Open Folder menu action."""
        from PySide6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(
            self, "Select Data Folder",
            self._data_panel.get_current_folder() or "/home",
        )
        if folder:
            self._data_panel.set_folder(folder)

    def _on_new_graph(self) -> None:
        """Handle Graph > New Graph menu action."""
        # Name the new graph based on existing count
        idx = len(self._graphs) + 1
        self._create_new_graph(f"Graph {idx}")

    def _on_close_graph(self) -> None:
        """Handle Graph > Close Graph menu action."""
        if len(self._graphs) <= 1:
            QMessageBox.information(
                self, "Close Graph",
                "Cannot close the last graph tab.",
            )
            return

        current_idx = self._tab_widget.currentIndex()
        if 0 <= current_idx < len(self._graphs):
            name, plot_widget, controls = self._graphs.pop(current_idx)
            plot_widget.deleteLater()
            controls.deleteLater()
            self._tab_widget.removeTab(current_idx)
            self._update_graph_list_menu()

    def _on_files_selected(self, filepaths: List[str]) -> None:
        """Handle file selection from the data panel."""
        if not filepaths:
            return

        # Load all selected files
        self._loaded_data = {}
        for filepath in filepaths:
            try:
                data = self._loader.load(filepath)
                if data is not None:
                    basename = filepath.split("/")[-1]
                    self._loaded_data[basename] = data
            except Exception as e:
                logger.error("Error loading %s: %s", filepath, e)
                QMessageBox.warning(
                    self,
                    "Load Error",
                    f"Failed to load {filepath}:\n{str(e)}",
                )

        # Auto-generate plot with loaded data on the current graph
        if self._loaded_data:
            current_graph = self._get_current_graph()
            if current_graph:
                name, plot_widget, controls = current_graph
                self._on_graph_generate(name)

    def _on_graph_control_changed(self, graph_name: str, kind: str, value: Any) -> None:
        """Handle control changes for a specific graph."""
        plot_widget = self._get_current_plot_widget()

        if kind == "x":
            plot_widget.set_log_mode(x_log=value, y_log=plot_widget._show_grid_x)
        elif kind == "y":
            plot_widget.set_log_mode(x_log=plot_widget._show_grid_x, y_log=value)
        elif kind == "grid":
            plot_widget.set_grid(show_x=value[0], show_y=value[1])
        elif kind == "legend":
            plot_widget.set_legend(show=value)
        elif kind == "slit_smear":
            # Re-render with slit-smeared toggle state
            self._on_graph_generate(graph_name)

    def _on_apply_template(self, graph_name: str, template_name: str) -> None:
        """Apply a template to the current graph's controls.

        Args:
            graph_name: Name of the target graph tab.
            template_name: Name of the template to apply.
        """
        controls = self._get_current_controls()
        if controls.apply_template(template_name):
            # Re-render the plot with the applied template settings
            self._on_graph_generate(graph_name)

    def _on_save_current_as_template(self) -> None:
        """Handle 'Save Current as Template' menu action."""
        from PySide6.QtWidgets import QInputDialog

        controls = self._get_current_controls()
        template_data = controls.get_current_template_data()

        name, ok = QInputDialog.getText(
            self, "Save Template", "Template name:",
        )

        if ok and name:
            # Sanitize name
            import os
            safe_name = name.replace("/", "_").replace("\\", "_")

            if self._template_manager.save_template(safe_name, template_data):
                # Refresh the template combo in all controls panels
                for _, _, ctrl in self._graphs:
                    ctrl.refresh_templates()

                QMessageBox.information(
                    self, "Template Saved",
                    f"Template '{safe_name}' saved successfully.",
                )
            else:
                QMessageBox.warning(
                    self, "Save Failed",
                    f"Failed to save template '{safe_name}'.",
                )

    def _on_manage_templates(self) -> None:
        """Handle 'Manage Templates' menu action."""
        from bernardyn.gui.template_dialog import TemplateDialog

        dialog = TemplateDialog(
            parent=self,
            template_manager=self._template_manager,
        )

        def on_template_selected(name: str) -> None:
            """Handle template selection in the dialog."""
            controls = self._get_current_controls()
            if controls.apply_template(name):
                # Re-render the plot with the applied template settings
                self._on_graph_generate(self._get_current_graph()[0] if self._get_current_graph() else "Graph 1")

        dialog.template_selected.connect(on_template_selected)
        dialog.exec()

    def _on_export_file(self, fmt: str = "png") -> None:
        """Handle 'Export as ...' menu action.

        Args:
            fmt: Default file format ('png', 'svg', 'pdf').
        """
        from PySide6.QtWidgets import QFileDialog

        ext_map = {
            "png": ("PNG Files (*.png)", "*.png"),
            "svg": ("SVG Files (*.svg)", "*.svg"),
            "pdf": ("PDF Files (*.pdf)", "*.pdf"),
        }

        filter_str, default_ext = ext_map.get(fmt, ("All Files (*.*)", "*.*"))
        default_name = f"bernardyn_plot.{default_ext[1:]}"

        filepath, _ = QFileDialog.getSaveFileName(
            self, f"Export Plot as {fmt.upper()}", default_name, filter_str,
        )

        if filepath:
            from bernardyn.export.exporter import get_default_dispatcher

            plot_widget = self._get_current_plot_widget()
            dispatcher = get_default_dispatcher()
            success = dispatcher.export(plot_widget, filepath)

            if success:
                QMessageBox.information(
                    self, "Export Successful",
                    f"Plot exported to {filepath}",
                )
            else:
                QMessageBox.warning(
                    self, "Export Failed",
                    f"Failed to export plot to {filepath}",
                )

    def _on_copy_to_clipboard(self) -> None:
        """Handle 'Copy to Clipboard' menu action."""
        from PySide6.QtWidgets import QMessageBox

        plot_widget = self._get_current_plot_widget()
        from bernardyn.export.exporter import get_default_dispatcher

        dispatcher = get_default_dispatcher()
        success = dispatcher.export(plot_widget, "clipboard")

        if success:
            QMessageBox.information(
                self, "Copied",
                "Plot copied to clipboard.",
            )
        else:
            QMessageBox.warning(
                self, "Copy Failed",
                "Failed to copy plot to clipboard.",
            )

    def _on_save_project(self) -> None:
        """Handle 'Save Project' menu action — export as .hdf5 container."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "bernardyn_project.hdf5",
            "HDF5 Files (*.hdf *.h5)",
        )

        if filepath:
            from bernardyn.export.container_exporter import get_container_exporter

            plot_widget = self._get_current_plot_widget()
            exporter = get_container_exporter()
            success = exporter.export(plot_widget, filepath)

            if success:
                QMessageBox.information(
                    self, "Project Saved",
                    f"Project saved to {filepath}",
                )
            else:
                QMessageBox.warning(
                    self, "Save Failed",
                    f"Failed to save project to {filepath}",
                )

    def _on_graph_generate(self, graph_name: str) -> None:
        """Generate the plot for a specific graph tab."""
        controls = self._get_current_controls()
        plot_widget = self._get_current_plot_widget()

        plot_widget.clear()

        if not self._loaded_data:
            return

        plot_type = controls.get_plot_type()
        x_log = controls.get_x_log()
        y_log = controls.get_y_log()

        if plot_type == "image":
            self._render_image_plot(plot_widget, controls)
        elif plot_type == "waterfall":
            self._render_waterfall_plot(plot_widget, controls)
        elif plot_type == "heatmap":
            self._render_heatmap_plot(plot_widget, controls)
        else:
            self._render_line_plot(plot_widget, controls, x_log, y_log)

    def _render_line_plot(
        self,
        plot_widget: PlotWidget,
        controls: ControlsPanel,
        x_log: bool,
        y_log: bool,
    ) -> None:
        """Render a line plot from loaded 1D SAS data.

        Args:
            plot_widget: The target PlotWidget to render into.
            controls: The ControlsPanel with current settings.
            x_log: Whether X axis is logarithmic.
            y_log: Whether Y axis is logarithmic.
        """
        plot_widget.set_log_mode(x_log=x_log, y_log=y_log)

        # Apply grid and legend settings
        show_grid_x, show_grid_y = controls.get_show_grid()
        plot_widget.set_grid(show_x=show_grid_x, show_y=show_grid_y)
        plot_widget.set_legend(controls.get_show_legend())

        show_slit_smear = controls.get_show_slit_smear()
        dataset_styles = controls.get_dataset_styles()

        dataset_index = 0
        all_x_min = float("inf")
        all_x_max = float("-inf")
        all_y_min = float("inf")
        all_y_max = float("-inf")
        has_slit_smear_data = False

        for basename, data in self._loaded_data.items():
            # Process 1D SAS datasets
            for sas_data in data.get("sas_data_list", []):
                x = sas_data.x
                y = sas_data.y

                # Skip datasets with non-positive values for log scale
                if (x_log and np.any(x <= 0)) or (y_log and np.any(y <= 0)):
                    continue

                # Get style for this dataset
                if dataset_index < len(dataset_styles):
                    style = dataset_styles[dataset_index]
                    color = style.get("color", "blue")
                    symbol = style.get("symbol", "o")
                    linestyle = style.get("linestyle", "-")
                else:
                    from bernardyn.plot.plot_style import get_color, DEFAULT_SYMBOLS
                    color = get_color(dataset_index)
                    symbol = DEFAULT_SYMBOLS[dataset_index % len(DEFAULT_SYMBOLS)]
                    linestyle = "-"

                plot_widget.add_line(
                    x, y,
                    color=color,
                    symbol=symbol,
                    linestyle=linestyle,
                    linewidth=1.5,
                    name=basename,
                )

                # Add error bars if available
                if sas_data.y_err is not None:
                    plot_widget.add_error_bars(x, y, sas_data.y_err, color=color)

                # Track ranges
                all_x_min = min(all_x_min, float(x.min()))
                all_x_max = max(all_x_max, float(x.max()))
                all_y_min = min(all_y_min, float(y.min()))
                all_y_max = max(all_y_max, float(y.max()))

                dataset_index += 1

            # Process slit-smeared data
            slit_smear = data.get("slit_smear")
            if slit_smear is not None:
                has_slit_smear_data = True
                x = slit_smear.x
                y = slit_smear.y

                if (x_log and np.any(x <= 0)) or (y_log and np.any(y <= 0)):
                    continue

                # Only show if toggle is enabled
                if not show_slit_smear:
                    dataset_index += 1
                    continue

                from bernardyn.plot.plot_style import get_color, DEFAULT_SYMBOLS
                color = get_color(dataset_index)
                symbol = "^"  # Upward triangle for SMR

                plot_widget.add_line(
                    x, y, color=color, symbol=symbol, linewidth=1.5,
                    name=f"{basename} (SMR)",
                )

                all_x_min = min(all_x_min, float(x.min()))
                all_x_max = max(all_x_max, float(x.max()))
                all_y_min = min(all_y_min, float(y.min()))
                all_y_max = max(all_y_max, float(y.max()))

                dataset_index += 1

            # Process desmeared data
            desmear = data.get("desmear")
            if desmear is not None:
                x = desmear.x
                y = desmear.y

                if (x_log and np.any(x <= 0)) or (y_log and np.any(y <= 0)):
                    continue

                from bernardyn.plot.plot_style import get_color, DEFAULT_SYMBOLS
                color = get_color(dataset_index)
                symbol = "v"  # Downward triangle for desmear

                plot_widget.add_line(
                    x, y, color=color, symbol=symbol, linewidth=1.5,
                    name=f"{basename} (desmear)",
                )

                all_x_min = min(all_x_min, float(x.min()))
                all_x_max = max(all_x_max, float(x.max()))
                all_y_min = min(all_y_min, float(y.min()))
                all_y_max = max(all_y_max, float(y.max()))

                dataset_index += 1

        # Set axis ranges
        if all_x_min != float("inf"):
            plot_widget.set_x_range(all_x_min, all_x_max)
        if all_y_min != float("inf"):
            plot_widget.set_y_range(all_y_min, all_y_max)

        # Update axis labels from first dataset
        for basename, data in self._loaded_data.items():
            for sas_data in data.get("sas_data_list", []):
                if len(sas_data.x) > 0:
                    plot_widget.set_x_label(sas_data.x_label or "X")
                    plot_widget.set_y_label(sas_data.y_label or "Y")
                    break

        # Update controls panel ranges
        if all_x_min != float("inf"):
            controls.set_x_range(all_x_min, all_x_max)
        if all_y_min != float("inf"):
            controls.set_y_range(all_y_min, all_y_max)

        # Update dataset count in controls
        controls.set_dataset_count(dataset_index)

        # Enable slit-smeared toggle if data has it
        controls.set_slit_smear_available(has_slit_smear_data)

        # Enable controls
        controls.set_enabled(True)

    def _render_image_plot(
        self,
        plot_widget: PlotWidget,
        controls: ControlsPanel,
    ) -> None:
        """Render a 2D image plot from loaded data.

        Args:
            plot_widget: The target PlotWidget to render into.
            controls: The ControlsPanel with current settings (color scale, log).
        """
        plot_widget.set_log_mode(x_log=False, y_log=False)

        color_scale = controls.get_color_scale()
        log_scale = controls.get_log_scale()

        for basename, data in self._loaded_data.items():
            raw_image = data.get("raw_image")
            if raw_image is not None and raw_image.data.size > 0:
                img = raw_image.data

                # Apply log scale if requested
                if log_scale:
                    img = np.where(img > 0, np.log10(np.maximum(img, 1e-30)), 0)

                vmin = float(np.percentile(img[img > 0], 1)) if np.any(img > 0) else float(img.min())
                vmax = float(np.percentile(img[img > 0], 99)) if np.any(img > 0) else float(img.max())

                plot_widget.add_image(img, vmin=vmin, vmax=vmax)
                plot_widget.set_title(f"{basename} - Raw Image ({color_scale})")
                break

        # Enable controls
        controls.set_enabled(True)

    def _render_waterfall_plot(
        self,
        plot_widget: PlotWidget,
        controls: ControlsPanel,
    ) -> None:
        """Render a waterfall (offset) plot from loaded 1D SAS data.

        Datasets are stacked vertically with Z-offset based on order number.

        Args:
            plot_widget: The target PlotWidget to render into.
            controls: The ControlsPanel with current settings (z_offset).
        """
        # Waterfall uses lin-lin by default
        plot_widget.set_log_mode(x_log=False, y_log=False)

        # Apply grid and legend settings
        show_grid_x, show_grid_y = controls.get_show_grid()
        plot_widget.set_grid(show_x=show_grid_x, show_y=show_grid_y)
        plot_widget.set_legend(controls.get_show_legend())

        z_offset = controls.get_z_offset()
        dataset_styles = controls.get_dataset_styles()

        # Collect all datasets for waterfall rendering
        waterfall_datasets = []
        dataset_index = 0

        for basename, data in self._loaded_data.items():
            for sas_data in data.get("sas_data_list", []):
                x = sas_data.x
                y = sas_data.y

                # Skip datasets with non-positive values for log scale
                if np.any(x <= 0) or np.any(y <= 0):
                    continue

                # Get style for this dataset
                if dataset_index < len(dataset_styles):
                    style = dataset_styles[dataset_index]
                    color = style.get("color", "blue")
                    symbol = style.get("symbol", "o")
                else:
                    from bernardyn.plot.plot_style import get_color, DEFAULT_SYMBOLS
                    color = get_color(dataset_index)
                    symbol = DEFAULT_SYMBOLS[dataset_index % len(DEFAULT_SYMBOLS)]

                waterfall_datasets.append({
                    "x": x,
                    "y": y,
                    "z_offset": float(dataset_index) * z_offset,
                    "order_number": dataset_index,
                    "color": color,
                    "symbol": symbol,
                    "title": basename,
                })

                dataset_index += 1

        # Render waterfall lines
        if waterfall_datasets:
            plot_widget.add_waterfall_lines(waterfall_datasets)

            # Set axis labels
            for basename, data in self._loaded_data.items():
                for sas_data in data.get("sas_data_list", []):
                    if len(sas_data.x) > 0:
                        plot_widget.set_x_label(sas_data.x_label or "Q")
                        break

            # Update controls panel dataset count
            controls.set_dataset_count(dataset_index)

        # Enable controls
        controls.set_enabled(True)

    def _render_heatmap_plot(
        self,
        plot_widget: PlotWidget,
        controls: ControlsPanel,
    ) -> None:
        """Render a heatmap plot from loaded 1D SAS data.

        Datasets are arranged with X horizontal, order number vertical,
        and intensity mapped to color.

        Args:
            plot_widget: The target PlotWidget to render into.
            controls: The ControlsPanel with current settings (color scale).
        """
        # Heatmap uses lin-lin by default
        plot_widget.set_log_mode(x_log=False, y_log=False)

        # Apply grid and legend settings
        show_grid_x, show_grid_y = controls.get_show_grid()
        plot_widget.set_grid(show_x=show_grid_x, show_y=show_grid_y)

        color_scale = controls.get_color_scale()
        dataset_styles = controls.get_dataset_styles()

        # Collect all datasets for heatmap rendering
        heatmap_datasets = []
        dataset_index = 0

        for basename, data in self._loaded_data.items():
            for sas_data in data.get("sas_data_list", []):
                x = sas_data.x
                y = sas_data.y

                # Skip datasets with non-positive values for log scale
                if np.any(x <= 0) or np.any(y <= 0):
                    continue

                heatmap_datasets.append({
                    "x": x,
                    "y": y,
                    "order_number": dataset_index,
                })

                dataset_index += 1

        # Render heatmap lines (scatter plot with color mapping)
        if heatmap_datasets:
            plot_widget.add_heatmap_lines(heatmap_datasets)

            # Set axis labels
            for basename, data in self._loaded_data.items():
                for sas_data in data.get("sas_data_list", []):
                    if len(sas_data.x) > 0:
                        plot_widget.set_x_label(sas_data.x_label or "Q")
                        break

            # Update controls panel dataset count
            controls.set_dataset_count(dataset_index)

        # Enable controls
        controls.set_enabled(True)

    def get_plot_widget(self) -> PlotWidget:
        """Get the plot widget for the currently active graph."""
        return self._get_current_plot_widget()

    def get_data_panel(self) -> DataPanel:
        """Get the data panel for external access."""
        return self._data_panel

    def get_controls_panel(self) -> ControlsPanel:
        """Get the controls panel for external access."""
        return self._get_current_controls()
