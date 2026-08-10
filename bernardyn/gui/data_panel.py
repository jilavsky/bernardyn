"""Left panel: file browser, listbox, sort/filter for Bernardyn.

Provides the data selection interface where users can:
  - Browse to a folder containing data files
  - View files in a listbox with one or more selection
  - Sort alphabetically or by order number
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
    sorting controls, and regex filtering.
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

        # Callback for when data is loaded (set by main window)
        self._on_data_loaded: Optional[Callable] = None

        self._setup_ui()

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

    def set_on_data_loaded(self, callback: Callable) -> None:
        """Set the callback for when data is loaded from a selected file."""
        self._on_data_loaded = callback

    def _on_browse_folder(self) -> None:
        """Open folder browser dialog."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Data Folder",
            self._current_folder or os.path.expanduser("~"),
        )

        if folder:
            self._current_folder = folder
            self._folder_path.setText(folder)
            self._load_files()

    def _load_files(self) -> None:
        """Load and display files from the current folder."""
        if not self._current_folder:
            return

        try:
            # Get all files in folder (non-recursive)
            entries = os.listdir(self._current_folder)
            self._all_files = [e for e in entries if os.path.isfile(os.path.join(self._current_folder, e))]

            # Apply regex filter
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
            self._filtered_files = list(self._all_files)
        else:
            try:
                self._filtered_files = filter_files_by_regex(self._all_files, pattern)
            except Exception:
                self._filtered_files = list(self._all_files)

    def _on_filter_changed(self, text: str) -> None:
        """Handle regex filter text changes."""
        self._apply_filter()
        self._sort_files()
        self._refresh_listbox()

    def _on_sort_changed(self, index: int) -> None:
        """Handle sort mode changes."""
        self._sort_files()
        self._refresh_listbox()

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
