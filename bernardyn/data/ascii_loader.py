"""ASCII file loader for Bernardyn.

Loads 1D data from plain text files (.txt, .csv) with 2 or 3 columns.
Handles optional header lines and comment lines starting with '#'.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class AsciiData:
    """Container for loaded ASCII data."""

    def __init__(self):
        self.x: np.ndarray = np.array([])
        self.y: np.ndarray = np.array([])
        self.y_err: Optional[np.ndarray] = None
        self.x_label: str = ""
        self.y_label: str = ""
        self.source_file: str = ""
        self.attributes: Dict[str, Any] = {}

    def __repr__(self):
        return f"AsciiData(x={len(self.x)}pts, y={len(self.y)}pts)"


class AsciiLoader:
    """Loads 1D data from ASCII text files.

    Supports:
      - 2-column format: X Y
      - 3-column format: X Y DY (with error bars)
      - Optional header lines (skipped if non-numeric)
      - Comment lines starting with '#' or '!'
    """

    SUPPORTED_EXTENSIONS = (".txt", ".csv", ".dat", ".asc")
    DELIMITERS = (",", "\t", None)  # None = whitespace

    def can_load(self, filepath: str) -> bool:
        """Check if this loader can handle the given file."""
        return any(filepath.lower().endswith(ext) for ext in self.SUPPORTED_EXTENSIONS)

    def load(self, filepath: str) -> Optional[AsciiData]:
        """Load data from an ASCII file.

        Returns AsciiData or None if loading fails.
        """
        data = AsciiData()
        data.source_file = filepath

        try:
            # Read file and filter out comments/headers
            lines = []
            with open(filepath, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                        continue
                    lines.append(stripped)

            if not lines:
                logger.warning("No data found in %s", filepath)
                return None

            # Try to parse all lines as numeric data
            parsed_rows = []
            for i, line in enumerate(lines):
                for delim in self.DELIMITERS:
                    try:
                        parts = line.split(delim) if delim else line.split()
                        parts = [p.strip() for p in parts]
                        nums = [float(p) for p in parts if p]
                        if len(nums) >= 2:
                            parsed_rows.append(nums)
                            break
                    except ValueError:
                        continue

            if not parsed_rows:
                logger.warning("Could not parse any numeric data from %s", filepath)
                return None

            array = np.array(parsed_rows)
            data.x = array[:, 0]
            data.y = array[:, 1]

            if array.shape[1] >= 3:
                data.y_err = array[:, 2]

            # Try to extract labels from first non-numeric line
            if lines:
                for line in lines[:5]:
                    parts = line.split(None, 1) if len(line.split()) > 1 else [line]
                    try:
                        float(parts[0])
                        continue
                    except ValueError:
                        if len(parts) >= 2 and len(parts[1].split()) == 2:
                            data.x_label = parts[1].split()[0]
                            data.y_label = parts[1].split()[1]
                        break

            return data

        except Exception as e:
            logger.error("Error loading ASCII file %s: %s", filepath, e)
            return None

    def load_1d(self, filepath: str) -> Optional[AsciiData]:
        """Convenience method to load 1D data from an ASCII file."""
        return self.load(filepath)
