"""File naming utilities for Bernardyn.

Provides functions to extract metadata from file names, sort files
alphabetically or by order number, and filter using regex patterns.
"""

import os
import re
from typing import Any, Dict, List, Optional


def extract_order_number(filename: str) -> Optional[int]:
    """Extract the order number from a filename.

    The order number is defined as the last numeric sequence before
    the file extension. For example:
      "LnG_0103.hdf" -> 103
      "Rh1_0085.h5" -> 85
      "data_42.csv" -> 42

    Returns None if no number is found.
    """
    # Remove extension
    base = os.path.splitext(filename)[0]

    # Find the last numeric sequence
    match = re.search(r'(\d+)$', base)
    if match:
        return int(match.group(1))

    # Try to find any numeric sequence in the name
    match = re.search(r'(\d+)', base)
    if match:
        return int(match.group(1))

    return None


def parse_filename_metadata(filename: str) -> Dict[str, Any]:
    """Parse metadata from a filename.

    Extracts:
      - order_number: Last numeric sequence before extension
      - has_time: True if "MIN" appears in filename (time indicator)
      - has_temperature: True if "DEG" appears in filename (temperature indicator)

    Returns a dict with the extracted metadata.
    """
    result = {
        "order_number": extract_order_number(filename),
        "has_time": bool(re.search(r'MIN', filename, re.IGNORECASE)),
        "has_temperature": bool(re.search(r'DEG', filename, re.IGNORECASE)),
    }

    return result


def sort_files_alphabetically(files: List[str]) -> List[str]:
    """Sort a list of filenames alphabetically.

    Args:
        files: List of filenames to sort

    Returns:
        Sorted list (case-insensitive)
    """
    return sorted(files, key=lambda f: f.lower())


def sort_files_by_order_number(files: List[str]) -> List[str]:
    """Sort a list of filenames by their extracted order number.

    Files without an extractable order number are placed at the end.

    Args:
        files: List of filenames to sort

    Returns:
        Sorted list by order number (ascending)
    """
    def sort_key(filename):
        num = extract_order_number(filename)
        if num is None:
            return (1, 0)  # No number -> sort after numbered files
        return (0, num)

    return sorted(files, key=sort_key)


def filter_files_by_regex(files: List[str], pattern: str) -> List[str]:
    """Filter a list of filenames using a regex pattern.

    Args:
        files: List of filenames to filter
        pattern: Regex pattern to match against filenames

    Returns:
        Filtered list of matching filenames
    """
    try:
        regex = re.compile(pattern)
        return [f for f in files if regex.search(f)]
    except re.error as e:
        # If pattern is invalid, return empty list
        print(f"Invalid regex pattern '{pattern}': {e}")
        return []


def filter_files_by_string(files: List[str], substring: str) -> List[str]:
    """Filter a list of filenames by simple string matching.

    Args:
        files: List of filenames to filter
        substring: String to search for in filenames

    Returns:
        Filtered list of matching filenames
    """
    return [f for f in files if substring.lower() in f.lower()]
