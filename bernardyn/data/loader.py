"""Abstract base class and dispatcher for data loaders.

Provides a unified interface for loading different file formats
and routes file paths to the appropriate loader based on extension.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Loader(ABC):
    """Abstract base class for all data loaders."""

    @abstractmethod
    def can_load(self, filepath: str) -> bool:
        """Check if this loader can handle the given file."""
        ...

    @abstractmethod
    def load(self, filepath: str) -> Dict[str, Any]:
        """Load data from the given file.

        Returns a dict with at least:
          - 'type': str identifying the data type
          - 'filepath': the source file path
        """
        ...


class LoaderDispatcher:
    """Dispatches file loading to the appropriate loader based on extension.

    Maintains a registry of loaders and selects the first one that
    reports it can handle the given file.
    """

    def __init__(self):
        self._loaders: List[Loader] = []

    def register(self, loader: Loader) -> None:
        """Register a loader for handling specific file types."""
        self._loaders.append(loader)

    def unregister(self, loader: Loader) -> None:
        """Unregister a previously registered loader."""
        self._loaders.remove(loader)

    def get_loader(self, filepath: str) -> Optional[Loader]:
        """Find the first loader that can handle the given file."""
        for loader in self._loaders:
            if loader.can_load(filepath):
                return loader
        return None

    def load(self, filepath: str) -> Optional[Dict[str, Any]]:
        """Load data from a file using the appropriate loader.

        Returns the loaded data dict, or None if no loader can handle it.
        Raises RuntimeError if a loader was found but failed to load.
        """
        loader = self.get_loader(filepath)
        if loader is None:
            logger.error("No loader available for file: %s", filepath)
            return None

        logger.info("Loading %s with %s", filepath, type(loader).__name__)
        try:
            result = loader.load(filepath)
        except Exception as e:
            logger.error("Error loading %s with %s: %s", filepath, type(loader).__name__, e)
            raise RuntimeError(f"Failed to load {filepath} using {type(loader).__name__}: {e}") from e

        if result is None or result == {}:
            logger.error("Loader %s returned empty result for %s", type(loader).__name__, filepath)
            return None

        return result

    def list_supported_extensions(self) -> List[str]:
        """Get all file extensions supported by registered loaders."""
        exts = set()
        for loader in self._loaders:
            if hasattr(loader, "SUPPORTED_EXTENSIONS"):
                exts.update(loader.SUPPORTED_EXTENSIONS)
        return sorted(exts)


# Global loader instance with default loaders registered
_default_dispatcher = LoaderDispatcher()

# Register HDF5 loader
from bernardyn.data.hdf5_loader import Hdf5Loader  # noqa: E402
_default_dispatcher.register(Hdf5Loader())

# Register ASCII loader
from bernardyn.data.ascii_loader import AsciiLoader  # noqa: E402
_default_dispatcher.register(AsciiLoader())


def get_loader(filepath: str) -> Optional[Loader]:
    """Get the appropriate loader for a file path.

    Uses the global default dispatcher.
    """
    return _default_dispatcher.get_loader(filepath)


def get_default_dispatcher() -> LoaderDispatcher:
    """Get the global default loader dispatcher."""
    return _default_dispatcher
