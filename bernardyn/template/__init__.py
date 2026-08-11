"""Template management layer for Bernardyn.

Provides save/load/rename/delete operations for plot templates,
stored as JSON files in the user's template directory.
"""

from bernardyn.template.manager import TemplateManager, get_default_manager

__all__ = ["TemplateManager", "get_default_manager"]
