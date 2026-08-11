"""Template storage for Bernardyn.

Handles serialization and deserialization of plot templates to/from JSON files.
Templates are stored in the user's template directory (~/.bernardyn/templates/).

Template Schema:
{
    "name": str,                    # Template name
    "version": str,                 # Schema version (e.g., "1.0")
    "plot_type": str,               # 'line', 'image', 'waterfall', 'heatmap'
    "x_log": bool,                  # X axis logarithmic scale
    "y_log": bool,                  # Y axis logarithmic scale
    "show_grid_x": bool,            # Show X grid lines
    "show_grid_y": bool,            # Show Y grid lines
    "show_legend": bool,            # Show legend
    "color_scale": str,             # Color scale name (for image/heatmap)
    "z_offset": float,              # Z offset multiplier (for waterfall)
    "x_range": tuple,               # X axis range [min, max]
    "y_range": tuple,               # Y axis range [min, max]
    "dataset_styles": list,         # Per-dataset styles [{color, symbol, linestyle}]
    "slit_smear_enabled": bool      # Slit-smeared data toggle state
}
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TemplateStorage:
    """Handles JSON serialization/deserialization of plot templates.

    Provides methods to save and load template data from JSON files,
    with support for the Bernardyn template schema version 1.0.
    """

    SCHEMA_VERSION = "1.0"

    def __init__(self, template_dir: str):
        """Initialize the storage with a template directory.

        Args:
            template_dir: Path to the directory where templates are stored.
                The directory will be created if it doesn't exist.
        """
        self._template_dir = template_dir
        os.makedirs(template_dir, exist_ok=True)

    def _get_template_path(self, name: str) -> str:
        """Get the file path for a template by name.

        Args:
            name: Template name (will be sanitized to remove path separators).

        Returns:
            Full file path for the template JSON file.
        """
        # Sanitize name to prevent path traversal
        safe_name = name.replace("/", "_").replace("\\", "_")
        return os.path.join(self._template_dir, f"{safe_name}.json")

    def save_template(self, name: str, template_data: Dict[str, Any]) -> bool:
        """Save a template to a JSON file.

        Args:
            name: Template name (used as filename).
            template_data: Dictionary containing the template data.

        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            # Add schema version and name to the data
            template_data["name"] = name
            template_data["version"] = self.SCHEMA_VERSION

            filepath = self._get_template_path(name)
            with open(filepath, "w") as f:
                json.dump(template_data, f, indent=2)

            logger.info("Saved template '%s' to %s", name, filepath)
            return True

        except Exception as e:
            logger.error("Failed to save template '%s': %s", name, e)
            return False

    def load_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a template from a JSON file.

        Args:
            name: Template name (used as filename).

        Returns:
            Dictionary containing the template data, or None if not found.
        """
        try:
            filepath = self._get_template_path(name)
            if not os.path.exists(filepath):
                logger.warning("Template '%s' not found at %s", name, filepath)
                return None

            with open(filepath, "r") as f:
                template_data = json.load(f)

            # Validate schema version
            if "version" not in template_data:
                logger.warning("Template '%s' has no version field", name)

            logger.info("Loaded template '%s' from %s", name, filepath)
            return template_data

        except Exception as e:
            logger.error("Failed to load template '%s': %s", name, e)
            return None

    def delete_template(self, name: str) -> bool:
        """Delete a template file.

        Args:
            name: Template name (used as filename).

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            filepath = self._get_template_path(name)
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info("Deleted template '%s' from %s", name, filepath)
                return True
            else:
                logger.warning("Template '%s' not found at %s", name, filepath)
                return False

        except Exception as e:
            logger.error("Failed to delete template '%s': %s", name, e)
            return False

    def list_templates(self) -> List[str]:
        """List all available template names.

        Returns:
            List of template name strings (without .json extension).
        """
        try:
            if not os.path.exists(self._template_dir):
                return []

            templates = []
            for filename in os.listdir(self._template_dir):
                if filename.endswith(".json"):
                    # Remove .json extension to get template name
                    name = filename[:-5]
                    templates.append(name)

            return sorted(templates)

        except Exception as e:
            logger.error("Failed to list templates: %s", e)
            return []

    def template_exists(self, name: str) -> bool:
        """Check if a template file exists.

        Args:
            name: Template name to check.

        Returns:
            True if the template file exists, False otherwise.
        """
        return os.path.exists(self._get_template_path(name))
