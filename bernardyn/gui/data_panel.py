"""Left panel: file browser, listbox, sort/filter for Bernardyn.

Provides the data selection interface where users can:
  - Browse to a folder containing data files
  - View files in a listbox with one or more selection
  - Sort alphabetically or by order number
  - Filter files using a dropdown for common extensions (HDF5, ASCII, All)
  - Filter files using regex patterns
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
)

from bernardyn.utils.file_utils import (
    extract_order_number,
    filter_files_by_regex,
    sort_files_alphabetically,
    sort_files_by_order_number,
)

logger = logging.getLogger(__name__)


class DataPanel(QGroupBox):
    """Left panel for data file selection.

    Provides folder browsing, file listing with multi-selection,
    sorting controls, extension filter dropdown, and regex filtering.
    """

    # Signal emitted when file selection changes
    files_selected = Signal(list)

    def __init__(self, parent: Optional[Any] = None):
        super().__init__("Data Files", parent)

        self._current_folder: str = ""
        self._all_files: List[str] = []
        self._filtered_files: List[str] = []
        self._sort_mode: str = "alphabetical"  # 'alphabetical' or 'order_number'
        self._regex_pattern: str = ""

        # Extension filter options
        self._extension_filter: str = "all"  # 'hdf5', 'ascii', 'all'

        # Callback for when data is loaded (set by main window)
        self._on_data_loaded: Optional[Callable] = None

        # State manager reference (set by main window)
        self._state_manager: Optional[Any] = None

        self._setup_ui()
        # _load_state() is deferred to set_state_manager() since the state manager
        # may not be available yet (it's injected by MainWindow after construction).

    def _setup_ui(self) -> None:
        """Build the UI layout."""
        layout = QVBoxLayout()

        # Folder browser row
        folder_layout = QHBoxLayout()
        self._folder_label = QLabel("Folder:")
        folder_layout.addWidget(self._folder_label)

        self._folder_path = QLineEdit()
        self._folder_path.setReadOnly(True)
        self._folder_path.setPlaceholderText("Select a data folder...")
        folder_layout.addWidget(self._folder_path, 1)

        self._browse_btn = QPushButton("Browse...")
        self._browse_btn.clicked.connect(self._on_browse_folder)
        folder_layout.addWidget(self._browse_btn)

        layout.addLayout(folder_layout)

        # Extension filter dropdown
        ext_layout = QHBoxLayout()
        ext_label = QLabel("Extension:")
        ext_layout.addWidget(ext_label)

        self._ext_combo = QComboBox()
        self._ext_combo.addItem("All Files", "all")
        self._ext_combo.addItem("HDF5 (.hdf, .h5)", "hdf5")
        self._ext_combo.addItem("ASCII (.txt, .dat, .csv)", "ascii")
        self._ext_combo.currentIndexChanged.connect(self._on_extension_changed)
        ext_layout.addWidget(self._ext_combo, 1)

        layout.addLayout(ext_layout)

        # Sort controls
        sort_layout = QHBoxLayout()
        sort_label = QLabel("Sort:")
        sort_layout.addWidget(sort_label)

        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Alphabetical", "alphabetical")
        self._sort_combo.addItem("Order Number", "order_number")
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        sort_layout.addWidget(self._sort_combo)

        layout.addLayout(sort_layout)

        # Regex filter
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter (regex):")
        filter_layout.addWidget(filter_label)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("e.g., LnG_.*")
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._filter_edit, 1)

        layout.addLayout(filter_layout)

        # File list
        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QListWidget.ExtendedSelection)
        self._file_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._file_list, 1)

        # Status label
        self._status_label = QLabel("No files loaded")
        layout.addWidget(self._status_label)

        self.setLayout(layout)

    def set_state_manager(self, state_manager: Any) -> None:
        """Set the state manager for persisting preferences."""
        self._state_manager = state_manager
        # Now that the state manager is available, load saved preferences.
        self._load_state()

    def _load_state(self) -> None:
        """Load saved preferences from state manager."""
        if self._state_manager is None:
            return

        # Restore last folder
        saved_folder = self._state_manager.get("last_data_folder", "")
        if saved_folder and os.path.isdir(saved_folder):
            self._current_folder = saved_folder
            self._folder_path.setText(saved_folder)

        # Restore regex filter
        saved_regex = self._state_manager.get("data_panel_regex_filter", "")
        if saved_regex:
            self._filter_edit.setText(saved_regex)

        # Restore sort mode
        saved_sort = self._state_manager.get("data_panel_sort_mode", "alphabetical")
        sort_idx = self._sort_combo.findData(saved_sort)
        if sort_idx >= 0:
            self._sort_combo.setCurrentIndex(sort_idx)

        # Restore extension filter
        saved_ext = self._state_manager.get("data_panel_extension_filter", "all")
        ext_idx = self._ext_combo.findData(saved_ext)
        if ext_idx >= 0:
            self._ext_combo.setCurrentIndex(ext_idx)

        # Load files if folder is valid
        if self._current_folder:
            self._load_files()

    def _save_state(self) -> None:
        """Save current preferences to state manager."""
        if self._state_manager is None:
            return

        self._state_manager.set("last_data_folder", self._current_folder)
        self._state_manager.set("data_panel_regex_filter", self._filter_edit.text())
        self._state_manager.set("data_panel_sort_mode", self._sort_combo.currentData())
        self._state_manager.set("data_panel_extension_filter", self._ext_combo.currentData())

    def set_on_data_loaded(self, callback: Callable) -> None:
        """Set the callback for when data is loaded from a selected file."""
        self._on_data_loaded = callback

    def _on_browse_folder(self) -> None:
        """Open folder browser dialog."""
        start_dir = self._current_folder or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Data Folder",
            start_dir,
        )

        if folder:
            self._current_folder = folder
            self._folder_path.setText(folder)
            self._load_files()
            self._save_state()

    def _get_extension_filter_regex(self) -> str:
        """Build a regex pattern from the current extension filter selection."""
        ext = self._ext_combo.currentData() or "all"

        if ext == "hdf5":
            return r".*\.(hdf|h5|HDF|H5)$"
        elif ext == "ascii":
            return r".*\.(txt|dat|csv|TXT|DAT|CSV)$"
        else:
            # All files - match common data extensions plus no extension
            return r".*\.(hdf|h5|txt|dat|csv|HDF|H5|TXT|DAT|CSV)$"

    def _load_files(self) -> None:
        """Load and display files from the current folder."""
        if not self._current_folder:
            return

        try:
            # Get all files in folder (non-recursive)
            entries = os.listdir(self._current_folder)
            self._all_files = [e for e in entries if os.path.isfile(os.path.join(self._current_folder, e))]

            # Apply extension filter
            ext_pattern = self._get_extension_filter_regex()
            try:
                import re
                ext_filtered = [f for f in self._all_files if re.search(ext_pattern, f)]
            except Exception:
                ext_filtered = list(self._all_files)

            # Apply regex filter on top of extension filter
            self._filtered_files = list(ext_filtered)
            self._apply_filter()

            # Sort files
            self._sort_files()

            # Update listbox
            self._file_list.clear()
            for filename in self._filtered_files:
                item = QListWidgetItem(filename)
                item.setData(Qt.UserRole, os.path.join(self._current_folder, filename))
                self._file_list.addItem(item)

            # Update status
            self._status_label.setText(f"{len(self._filtered_files)} files found")

        except OSError as e:
            logger.error("Error reading folder %s: %s", self._current_folder, e)
            self._status_label.setText(f"Error: {e}")

    def _apply_filter(self) -> None:
        """Apply the current regex filter to the file list."""
        pattern = self._filter_edit.text().strip()
        if not pattern:
            # No regex filter - use the extension-filtered list as-is
            ext_pattern = self._get_extension_filter_regex()
            try:
                import re
                self._filtered_files = [f for f in self._all_files if re.search(ext_pattern, f)]
            except Exception:
                self._filtered_files = list(self._all_files)
        else:
            try:
                self._filtered_files = filter_files_by_regex(self._all_files, pattern)
            except Exception:
                self._filtered_files = list(self._all_files)

    def _on_extension_changed(self, index: int) -> None:
        """Handle extension filter dropdown changes."""
        self._extension_filter = self._ext_combo.currentData() or "all"
        self._load_files()  # Reload with new extension filter
        self._save_state()

    def _on_filter_changed(self, text: str) -> None:
        """Handle regex filter text changes."""
        self._apply_filter()
        self._sort_files()
        self._refresh_listbox()
        self._save_state()

    def _on_sort_changed(self, index: int) -> None:
        """Handle sort mode changes."""
        self._sort_files()
        self._refresh_listbox()
        self._save_state()

    def _sort_files(self) -> None:
        """Sort the filtered files based on current sort mode."""
        if self._sort_combo.currentData() == "order_number":
            self._filtered_files = sort_files_by_order_number(self._filtered_files)
        else:
            self._filtered_files = sort_files_alphabetically(self._filtered_files)

    def _refresh_listbox(self) -> None:
        """Refresh the file listbox display."""
        self._file_list.clear()
        for filename in self._filtered_files:
            item = QListWidgetItem(filename)
            item.setData(Qt.UserRole, os.path.join(self._current_folder, filename))
            self._file_list.addItem(item)

    def _on_selection_changed(self) -> None:
        """Handle file selection changes."""
        selected = self._file_list.selectedItems()
        if not selected:
            return

        filepaths = []
        for item in selected:
            filepath = item.data(Qt.UserRole)
            if filepath:
                filepaths.append(filepath)

        self.files_selected.emit(filepaths)

    def get_selected_files(self) -> List[str]:
        """Get the list of currently selected file paths."""
        selected = self._file_list.selectedItems()
        return [item.data(Qt.UserRole) for item in selected if item.data(Qt.UserRole)]

    def set_folder(self, folder: str) -> None:
        """Programmatically set the data folder and load files."""
        self._current_folder = folder
        self._folder_path.setText(folder)
        self._load_files()

    def set_regex_filter(self, pattern: str) -> None:
        """Programmatically set the regex filter."""
        self._filter_edit.setText(pattern)

    def get_current_folder(self) -> str:
        """Get the current data folder path."""
        return self._current_folder
