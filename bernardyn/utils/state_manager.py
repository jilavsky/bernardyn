"""Persistent state management for Bernardyn.

Saves and loads application preferences (last data folder, regex filter)
to a JSON file so they persist across sessions.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StateManager:
    """Manages persistent application state.

    Stores preferences in a JSON file at ~/.bernardyn/state.json by default.
    Supports saving/loading: last data folder, regex filter pattern, and
    any other arbitrary key-value pairs.
    """

    DEFAULT_STATE_DIR = os.path.join(os.path.expanduser("~"), ".bernardyn")
    DEFAULT_STATE_FILE = "state.json"

    # Default values for known preferences
    DEFAULTS: Dict[str, Any] = {
        "last_data_folder": "",
        "regex_filter": "",
    }

    def __init__(self, state_dir: Optional[str] = None, state_file: Optional[str] = None):
        """Initialize the state manager.

        Args:
            state_dir: Directory to store state file (default: ~/.bernardyn)
            state_file: Filename for state storage (default: state.json)
        """
        self._state_dir = state_dir or self.DEFAULT_STATE_DIR
        self._state_file = os.path.join(self._state_dir, state_file or self.DEFAULT_STATE_FILE)
        # Start empty so load() is triggered on first access. Defaults are
        # merged in during load() (or on first get when no file exists yet).
        self._state: Dict[str, Any] = {}

    def _ensure_dir(self) -> None:
        """Ensure the state directory exists."""
        os.makedirs(self._state_dir, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        """Load state from disk.

        Returns the current state dict (merged with defaults).
        Creates default state file if it doesn't exist.
        """
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file, "r") as f:
                    saved = json.load(f)
                # Merge with defaults (saved values override defaults)
                merged = dict(self.DEFAULTS)
                merged.update(saved)
                self._state = merged
                logger.info("Loaded state from %s", self._state_file)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load state from %s: %s", self._state_file, e)
                self._state = dict(self.DEFAULTS)
        else:
            self._ensure_dir()
            logger.info("No state file found, using defaults")

        return self._state

    def save(self) -> None:
        """Save current state to disk."""
        self._ensure_dir()
        try:
            with open(self._state_file, "w") as f:
                json.dump(self._state, f, indent=2)
            logger.info("Saved state to %s", self._state_file)
        except IOError as e:
            logger.error("Failed to save state to %s: %s", self._state_file, e)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a state value.

        Args:
            key: State key to retrieve
            default: Default value if key not found

        Returns:
            The stored value, or default if not present.
        """
        # Load only if state hasn't been loaded yet
        if not self._state:
            self.load()

        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a state value and save immediately.

        Args:
            key: State key to set
            value: Value to store
        """
        self._state[key] = value
        self.save()

    @property
    def last_data_folder(self) -> str:
        """Get or set the last data folder path."""
        return self.get("last_data_folder", "")

    @last_data_folder.setter
    def last_data_folder(self, path: str) -> None:
        self.set("last_data_folder", path)

    @property
    def regex_filter(self) -> str:
        """Get or set the regex filter pattern."""
        return self.get("regex_filter", "")

    @regex_filter.setter
    def regex_filter(self, pattern: str) -> None:
        self.set("regex_filter", pattern)

    def reset(self) -> None:
        """Reset all state to defaults and save."""
        self._state = dict(self.DEFAULTS)
        self.save()
