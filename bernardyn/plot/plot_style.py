"""Plot styling utilities for Bernardyn.

Provides color palettes, symbol definitions, and line style mappings
for consistent visual representation of SAS data.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# Default color palette (10 distinct colors for multi-dataset plots)
DEFAULT_COLORS = [
    "#1f77b4",  # blue
    "#ff7f0e",  # orange
    "#2ca02c",  # green
    "#d62728",  # red
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#e377c2",  # pink
    "#7f7f7f",  # gray
    "#bcbd22",  # olive
    "#17becf",  # cyan
]

# Extended color palette (20 colors)
EXTENDED_COLORS = DEFAULT_COLORS + [
    "#aec7e8",  # light blue
    "#ffbb78",  # light orange
    "#98df8a",  # light green
    "#ff9896",  # light red
    "#c5b0d5",  # light purple
]


# Symbol definitions for pyqtgraph
SYMBOLS = {
    "o": "o",   # circle
    "s": "s",   # square
    "t": "t",   # triangle
    "d": "d",   # diamond
    "+": "+",   # plus
    "x": "x",   # x-mark
    "*": "*",   # star
    "p": "p",   # pentagon
    "h": "h",   # hexagon
}

DEFAULT_SYMBOLS = ["o", "s", "t", "d", "+", "x", "*", "p", "h"]


# Line style definitions for pyqtgraph
LINE_STYLES = {
    "-": 1,       # solid
    "--": 2,      # dashed
    ".": 3,       # dotted
    "-.": 4,      # dash-dot
    "none": 0,    # no line
}

DEFAULT_LINE_STYLES = ["-", "--", ".-.", "-."]

# Default line width for plot lines
DEFAULT_LINEWIDTH = 1.5

# Default symbol size
DEFAULT_SYMBOL_SIZE = 4


def get_color(index: int) -> str:
    """Get a color from the default palette by index.

    Wraps around if index exceeds palette size.
    """
    return EXTENDED_COLORS[index % len(EXTENDED_COLORS)]


def get_symbol(index: int) -> str:
    """Get a symbol from the default list by index.

    Wraps around if index exceeds list size.
    """
    return DEFAULT_SYMBOLS[index % len(DEFAULT_SYMBOLS)]


def get_line_style(index: int) -> str:
    """Get a line style from the default list by index.

    Wraps around if index exceeds list size.
    """
    return DEFAULT_LINE_STYLES[index % len(DEFAULT_LINE_STYLES)]


def auto_style(index: int) -> Dict[str, any]:
    """Generate a complete auto-style dict for the Nth dataset.

    Returns:
        Dict with 'color', 'symbol', and 'linestyle' keys.
    """
    return {
        "color": get_color(index),
        "symbol": get_symbol(index),
        "linestyle": get_line_style(index),
    }


def generate_colors(n: int) -> List[str]:
    """Generate N distinct colors for a multi-dataset plot."""
    return [get_color(i) for i in range(n)]


def generate_symbols(n: int) -> List[str]:
    """Generate N distinct symbols for a multi-dataset plot."""
    return [get_symbol(i) for i in range(n)]


def generate_line_styles(n: int) -> List[str]:
    """Generate N distinct line styles for a multi-dataset plot."""
    return [get_line_style(i) for i in range(n)]


def map_symbol_to_pyqtgraph(symbol_name: str) -> str:
    """Map a symbol name to its pyqtgraph representation.

    Returns the pyqtgraph symbol character, or 'o' as fallback.
    """
    return SYMBOLS.get(symbol_name, "o")


def map_linestyle_to_pyqtgraph(style_name: str) -> int:
    """Map a line style name to its pyqtgraph value.

    Returns the pyqtgraph linestyle integer, or 1 (solid) as fallback.
    """
    return LINE_STYLES.get(style_name, 1)
