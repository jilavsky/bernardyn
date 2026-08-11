"""Template manager for Bernardyn.

Provides high-level CRUD operations for plot templates,
including save, load, rename, delete, and import/export.
"""

import copy
import logging
import os
from typing import Any, Dict, List, Optional

from bernardyn.template.storage import TemplateStorage

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manages plot templates with save/load/rename/delete operations.

    Provides a high-level interface for template management,
    including import/export functionality and default templates.

    Default template directory: ~/.bernardyn/templates/
    """

    DEFAULT_TEMPLATE_DIR = os.path.join(os.path.expanduser("~"), ".bernardyn", "templates")

    def __init__(self, template_dir: Optional[str] = None):
        """Initialize the template manager.

        Args:
            template_dir: Path to the template directory.
                Defaults to ~/.bernardyn/templates/ if None.
        """
        self._template_dir = template_dir or self.DEFAULT_TEMPLATE_DIR
        self._storage = TemplateStorage(self._template_dir)

    @property
    def template_dir(self) -> str:
        """Get the template directory path."""
        return self._template_dir

    def save_template(self, name: str, template_data: Dict[str, Any]) -> bool:
        """Save a plot template.

        Args:
            name: Template name (used as filename).
            template_data: Dictionary containing the template data.

        Returns:
            True if saved successfully, False otherwise.
        """
        return self._storage.save_template(name, template_data)

    def load_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a plot template.

        Args:
            name: Template name to load.

        Returns:
            Dictionary containing the template data, or None if not found.
        """
        return self._storage.load_template(name)

    def delete_template(self, name: str) -> bool:
        """Delete a plot template.

        Args:
            name: Template name to delete.

        Returns:
            True if deleted successfully, False otherwise.
        """
        return self._storage.delete_template(name)

    def rename_template(self, old_name: str, new_name: str) -> bool:
        """Rename a plot template.

        Args:
            old_name: Current template name.
            new_name: New template name.

        Returns:
            True if renamed successfully, False otherwise.
        """
        # Load the old template
        data = self._storage.load_template(old_name)
        if data is None:
            logger.error("Cannot rename '%s': template not found", old_name)
            return False

        # Save with new name (deep copy to avoid mutation)
        if not self._storage.save_template(new_name, copy.deepcopy(data)):
            logger.error("Failed to save template as '%s'", new_name)
            return False

        # Delete the old template
        self._storage.delete_template(old_name)

        logger.info("Renamed template '%s' to '%s'", old_name, new_name)
        return True

    def list_templates(self) -> List[str]:
        """List all available template names.

        Returns:
            Sorted list of template name strings.
        """
        return self._storage.list_templates()

    def template_exists(self, name: str) -> bool:
        """Check if a template exists.

        Args:
            name: Template name to check.

        Returns:
            True if the template exists, False otherwise.
        """
        return self._storage.template_exists(name)

    def import_template(self, source_path: str, name: Optional[str] = None) -> bool:
        """Import a template from an external JSON file.

        Args:
            source_path: Path to the source JSON template file.
            name: Optional new name for the imported template.
                If None, uses the filename without extension.

        Returns:
            True if imported successfully, False otherwise.
        """
        try:
            import json

            with open(source_path, "r") as f:
                data = json.load(f)

            if name is None:
                # Use filename without extension as template name
                name = os.path.splitext(os.path.basename(source_path))[0]

            return self.save_template(name, data)

        except Exception as e:
            logger.error("Failed to import template from %s: %s", source_path, e)
            return False

    def export_template(self, name: str, dest_path: str) -> bool:
        """Export a template to an external JSON file.

        Args:
            name: Template name to export.
            dest_path: Destination file path for the exported template.

        Returns:
            True if exported successfully, False otherwise.
        """
        try:
            data = self._storage.load_template(name)
            if data is None:
                logger.error("Cannot export '%s': template not found", name)
                return False

            import json
            os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
            with open(dest_path, "w") as f:
                json.dump(data, f, indent=2)

            logger.info("Exported template '%s' to %s", name, dest_path)
            return True

        except Exception as e:
            logger.error("Failed to export template '%s': %s", name, e)
            return False

    def get_default_template(self) -> Dict[str, Any]:
        """Get the default template configuration.

        Returns:
            Dictionary with default plot settings (log-log line plot).
        """
        return {
            "plot_type": "line",
            "x_log": True,
            "y_log": True,
            "show_grid_x": False,
            "show_grid_y": False,
            "show_legend": True,
            "color_scale": "grayscale",
            "z_offset": 1.0,
            "x_range": [0.0, 1.0],
            "y_range": [0.0, 1.0],
            "dataset_styles": [],
            "slit_smear_enabled": False,
        }


# Global template manager instance
_default_manager: Optional[TemplateManager] = None


def get_default_manager() -> TemplateManager:
    """Get the global default template manager.

    Returns:
        The global TemplateManager instance, creating it if necessary.
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = TemplateManager()
    return _default_manager
