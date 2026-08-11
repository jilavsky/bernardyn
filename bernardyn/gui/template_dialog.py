"""Template management dialog for Bernardyn.

Provides a modal dialog for creating, renaming, deleting, and
importing/export plot templates via the Bernardyn TemplateManager.
"""

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from bernardyn.template.manager import TemplateManager, get_default_manager

logger = logging.getLogger(__name__)


class TemplateDialog(QDialog):
    """Modal dialog for template management (CRUD operations).

    Provides a user interface for:
      - Listing all available templates
      - Creating new templates from current plot state
      - Renaming existing templates
      - Deleting templates
      - Importing templates from external files
      - Exporting templates to external files
    """

    # Signal emitted when a template is selected or created
    template_selected = Signal(str)

    def __init__(self, parent: Optional[Any] = None, template_manager: Optional[TemplateManager] = None):
        super().__init__(parent)

        self._template_manager = template_manager or get_default_manager()
        self.setWindowTitle("Manage Templates")
        self.setMinimumWidth(400)

        self._setup_ui()
        self._refresh_template_list()

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        layout = QVBoxLayout()

        # Template list
        list_layout = QHBoxLayout()
        list_layout.addWidget(QLabel("Templates:"))

        self._template_list = QListWidget()
        self._template_list.currentItemChanged.connect(self._on_template_selected)
        list_layout.addWidget(self._template_list, 1)
        layout.addLayout(list_layout)

        # Name input for new/rename
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Enter template name...")
        name_layout.addWidget(self._name_edit, 1)
        layout.addLayout(name_layout)

        # Action buttons row
        btn_row = QHBoxLayout()

        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        self._rename_btn = QPushButton("Rename")
        self._rename_btn.clicked.connect(self._on_rename)
        btn_row.addWidget(self._rename_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._delete_btn)

        layout.addLayout(btn_row)

        # Import/Export buttons row
        io_row = QHBoxLayout()

        self._import_btn = QPushButton("Import...")
        self._import_btn.clicked.connect(self._on_import)
        io_row.addWidget(self._import_btn)

        self._export_btn = QPushButton("Export...")
        self._export_btn.clicked.connect(self._on_export)
        io_row.addWidget(self._export_btn)

        layout.addLayout(io_row)

        # Dialog buttons (OK/Cancel)
        self._button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self.setLayout(layout)

    def _refresh_template_list(self) -> None:
        """Refresh the template list from the manager."""
        self._template_list.clear()
        templates = self._template_manager.list_templates()
        for name in templates:
            self._template_list.addItem(name)

    def _on_template_selected(self, current, previous) -> None:
        """Handle template selection change."""
        if current is not None:
            self._name_edit.setText(current.text())

    def _on_save(self) -> None:
        """Handle Save button click — create or overwrite a template."""
        name = self._name_edit.text().strip()
        if not name:
            logger.warning("Cannot save template with empty name")
            return

        # The caller should set the current plot state before calling save
        # This is handled by the main window's "Save Current as Template" workflow
        self.template_selected.emit(name)

    def _on_rename(self) -> None:
        """Handle Rename button click."""
        current_item = self._template_list.currentItem()
        if current_item is None:
            return

        old_name = current_item.text()
        new_name = self._name_edit.text().strip()

        if not new_name or new_name == old_name:
            return

        if self._template_manager.rename_template(old_name, new_name):
            self._refresh_template_list()

    def _on_delete(self) -> None:
        """Handle Delete button click."""
        current_item = self._template_list.currentItem()
        if current_item is None:
            return

        name = current_item.text()
        if self._template_manager.delete_template(name):
            self._refresh_template_list()

    def _on_import(self) -> None:
        """Handle Import button click."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Template", "",
            "JSON Files (*.json);;All Files (*)",
        )
        if filepath:
            name, _ = QFileDialog.getSaveFileName(
                self, "Import Template As", "",
                "JSON Files (*.json);;All Files (*)",
            )
            if name:
                # Remove .json extension from the save path to get template name
                import os
                if name.endswith(".json"):
                    name = name[:-5]

                self._template_manager.import_template(filepath, name)
                self._refresh_template_list()

    def _on_export(self) -> None:
        """Handle Export button click."""
        current_item = self._template_list.currentItem()
        if current_item is None:
            return

        name = current_item.text()
        dest_path, _ = QFileDialog.getSaveFileName(
            self, "Export Template", f"{name}.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if dest_path:
            self._template_manager.export_template(name, dest_path)

    def _on_accept(self) -> None:
        """Handle OK button click."""
        current_item = self._template_list.currentItem()
        if current_item is not None:
            self.template_selected.emit(current_item.text())
        self.accept()

    def set_current_template(self, name: str) -> None:
        """Select a specific template in the list.

        Args:
            name: Template name to select.
        """
        for i in range(self._template_list.count()):
            if self._template_list.item(i).text() == name:
                self._template_list.setCurrentRow(i)
                break
