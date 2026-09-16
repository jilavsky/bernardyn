"""Path boundaries for the local Bernardyn MCP server."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class PathSecurityError(ValueError):
    """Raised when an MCP path falls outside an authorised root."""


def data_root() -> Path | None:
    value = os.environ.get("BERNARDYN_DATA_ROOT")
    return None if not value else Path(value).expanduser().resolve()


def output_root() -> Path:
    value = os.environ.get("BERNARDYN_OUTPUT_ROOT")
    root = Path(value).expanduser() if value else Path(tempfile.gettempdir()) / "bernardyn-mcp"
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_input(path: str | Path) -> Path:
    """Resolve an existing input, restricting it to DATA_ROOT when configured."""
    root = data_root()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute() and root is not None:
        candidate = root / candidate
    candidate = candidate.resolve()
    roots = tuple(item for item in (root, output_root()) if item is not None)
    if root is not None and not any(_inside(candidate, item) for item in roots):
        raise PathSecurityError(f"input path is outside BERNARDYN_DATA_ROOT: {candidate}")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def output_path(name: str, suffix: str) -> Path:
    """Return one output-root child, rejecting traversal and arbitrary paths."""
    relative = Path(name)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name in {"", ".", ".."}:
        raise PathSecurityError("output name must be a simple filename, not a path")
    destination = output_root() / relative.name
    if not destination.name.lower().endswith(suffix.lower()):
        destination = destination.with_name(destination.name + suffix)
    return destination


def _inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False
