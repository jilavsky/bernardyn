"""One lock for every read of a source file, across threads.

Concurrent HDF5 opens over an SSHFS-Win network drive fail with spurious
"group not found" errors, which is why the window loads data on a one-thread
pool.  Discovery, result surveys and File-browser previews also open files,
some on the GUI thread, so they could still overlap a load running in that
pool.  Every entry point that opens a source file holds this lock for the
whole operation, so at most one source file is open at a time.  It is
re-entrant, so nested readers do not deadlock.

The GUI thread may wait for one file read in progress; that is the price of
never reading two files at once.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from typing import ParamSpec, TypeVar

__all__ = ["SOURCE_ACCESS_LOCK", "serialized"]

SOURCE_ACCESS_LOCK = threading.RLock()

P = ParamSpec("P")
R = TypeVar("R")


def serialized(function: Callable[P, R]) -> Callable[P, R]:
    """Run ``function`` while holding :data:`SOURCE_ACCESS_LOCK`."""

    @functools.wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with SOURCE_ACCESS_LOCK:
            return function(*args, **kwargs)

    return wrapper
