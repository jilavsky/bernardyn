"""Qt-free file-list rules shared by Bernardyn's data browser.

The behavior intentionally matches PyIrena's Data Selector: folders are
listed non-recursively, filters are case-insensitive regular expressions, and
the filename can encode temperature, time, pressure, or acquisition order.
Optionally the first level of subfolders is listed too (USAXS/SAXS/WAXS
subfolders of one sample folder); never deeper.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

HDF5_SUFFIXES = frozenset({".h5", ".hdf5", ".hdf", ".nxs"})
TEXT_SUFFIXES = frozenset({".dat", ".txt", ".csv"})

FILE_TYPE_CHOICES = (
    ("HDF5 / NeXus files", "hdf5"),
    ("Text files", "text"),
    ("All supported files", "all"),
)

SORT_LABELS = (
    "Filename A→Z",
    "Filename Z→A",
    "Temperature ↑",
    "Temperature ↓",
    "Time ↑",
    "Time ↓",
    "Order number ↑",
    "Order number ↓",
    "Pressure ↑",
    "Pressure ↓",
)
DEFAULT_SORT_INDEX = 6
SORT_TOOLTIP = (
    "Sort filenames by embedded metadata. Recognized patterns are _25C, "
    "_10min, _100PSI, and trailing _03 acquisition order. "
    "Files without a matching pattern sort last."
)
#: Above this many subfolders, "Include subfolders" lists none of them: a
#: parent of hundreds of run folders is the wrong place, and listing it over a
#: network drive is slow.
SUBFOLDER_LIMIT = 50
FILTER_PLACEHOLDER = "Filter… (regex OK, e.g. 60C|0[12]min)"
FILTER_TOOLTIP = (
    "Filter filenames using a case-insensitive regular expression. "
    "Plain text also works; an incomplete expression falls back to substring matching."
)


def suffixes_for(file_type: str) -> frozenset[str]:
    if file_type == "hdf5":
        return HDF5_SUFFIXES
    if file_type == "text":
        return TEXT_SUFFIXES
    if file_type == "all":
        return HDF5_SUFFIXES | TEXT_SUFFIXES
    return frozenset()


def files_in_folder(folder: str | Path, file_type: str = "all") -> list[Path]:
    """List supported files directly in *folder*, excluding graph packages."""
    directory = Path(folder).expanduser()
    if not directory.is_dir():
        return []
    suffixes = suffixes_for(file_type)
    try:
        return [
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix.lower() in suffixes
            and not path.name.lower().endswith(".bernardyn.h5")
        ]
    except OSError:
        return []


def child_folders(folder: str | Path) -> list[Path]:
    """Visible folders directly in *folder*, A→Z; empty if it cannot be read."""
    directory = Path(folder).expanduser()
    try:
        return sorted(
            (path for path in directory.iterdir() if path.is_dir() and not path.name.startswith(".")),
            key=lambda path: path.name.lower(),
        )
    except OSError:
        return []


def display_name(path: Path, root: str | Path) -> str:
    """File name, prefixed by its subfolder (with ``/``) when not directly in *root*."""
    parent = Path(path).parent
    if parent == Path(root):
        return path.name
    return f"{parent.name}/{path.name}"


def make_file_matcher(filter_text: str | None) -> Callable[[str], bool]:
    """Return PyIrena-compatible regex/sub-string filename predicate."""
    text = (filter_text or "").strip()
    if not text:
        return lambda name: True
    try:
        pattern = re.compile(text, re.IGNORECASE)
    except re.error:
        lowered = text.lower()
        return lambda name: lowered in name.lower()
    return lambda name: bool(pattern.search(name))


def _temperature(name: str) -> float:
    match = re.search(r"_(-?\d+(?:\.\d+)?)C(?=_|\.|$)", name, re.IGNORECASE)
    return float(match.group(1)) if match else float("inf")


def _time(name: str) -> float:
    match = re.search(r"_(\d+(?:\.\d+)?)min(?=_|\.|$)", name, re.IGNORECASE)
    return float(match.group(1)) if match else float("inf")


def _order(name: str) -> float:
    stem = Path(name).stem
    for part in reversed(stem.split("_")):
        if part.isdigit():
            return float(part)
    return float("inf")


def _pressure(name: str) -> float:
    match = re.search(r"_(\d+(?:\.\d+)?)PSI(?=_|\.|$)", name, re.IGNORECASE)
    return float(match.group(1)) if match else float("inf")


_SORT_KEYS: tuple[Callable[[str], str | float], ...] = (
    lambda name: name.lower(), lambda name: name.lower(),
    _temperature, _temperature, _time, _time, _order, _order, _pressure, _pressure,
)


def sort_paths(
    paths: Iterable[Path], index: int = DEFAULT_SORT_INDEX, *, group_by_folder: bool = False
) -> list[Path]:
    """Sort paths using the same order semantics as PyIrena's Data Selector.

    ``group_by_folder`` keeps each folder's files together (folders A→Z) and
    sorts within each; otherwise files from several folders are interleaved.
    """
    if group_by_folder:
        groups: dict[Path, list[Path]] = {}
        for path in paths:
            groups.setdefault(path.parent, []).append(path)
        return [
            path
            for folder in sorted(groups, key=lambda folder: str(folder).lower())
            for path in sort_paths(groups[folder], index)
        ]
    selected_index = min(max(index, 0), len(_SORT_KEYS) - 1)
    key = _SORT_KEYS[selected_index]
    descending = bool(selected_index % 2)
    values = list(paths)
    if selected_index < 2:
        return sorted(values, key=lambda path: str(key(path.name)), reverse=descending)

    def ordering(path: Path) -> tuple[int, float]:
        value = float(key(path.name))
        if value == float("inf"):
            return (1, 0.0)
        return (0, -value if descending else value)

    return sorted(values, key=ordering)
