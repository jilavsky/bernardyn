"""Shots for docs/guides/workflow.md.

No dataset: the File menu of a new window, where the workspace and graph
package commands described on the page live.
"""

from __future__ import annotations

from ._common import Context, shot
from ._package import open_main_window


@shot("workflow-01-file-menu")
def file_menu(ctx: Context):
    w = open_main_window(ctx)
    from PySide6.QtWidgets import QMenu

    menu = next(m for m in w.menuBar().findChildren(QMenu) if m.title() == "&File")
    menu.popup(w.mapToGlobal(w.menuBar().geometry().bottomLeft()))
    ctx.settle(60)
    image = menu.grab()
    menu.close()
    return image
