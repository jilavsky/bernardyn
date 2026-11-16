"""Shots for docs/getting-started/window-tour.md.

Dataset: ``testData/Al_Mg_Si__40C_0min_0498.h5`` (USAXS of an Al-Mg-Si alloy
with a saved pyIrena Unified Fit and Size Distribution). The graph shows its
Unified Fit "Data + fit I(Q)" curves.
"""

from __future__ import annotations

from PySide6.QtCore import QRect

from ._common import Context, draw_callouts, shot, widget_rect
from ._package import fixed_data_folder, open_main_window, show_file_browser

FILE = "Al_Mg_Si__40C_0min_0498.h5"


def loaded_window(ctx: Context):
    """Main window with the sample's Unified Fit data and fit in the first graph."""
    window = open_main_window(ctx)
    folder = fixed_data_folder()
    window._import_result_selection([folder / FILE], {"unified_fit": ("iq",)})
    ctx.settle(60)
    show_file_browser(ctx, window, folder, select=FILE)
    return window


def _menu_end(window) -> QRect:
    """Rectangle just right of the last menu title (Help)."""
    bar = window.menuBar()
    last = bar.actionGeometry(bar.actions()[-1])
    return QRect(bar.mapTo(window, last.topRight()), last.size())


@shot("window-tour-01-window")
def main_window(ctx: Context):
    w = loaded_window(ctx)
    image = w.grab()
    page = w.tabs.currentWidget()
    selector = w.files_panel.selector
    marks = [
        (1, _menu_end(w), "l", (18, 0)),
        (2, widget_rect(w.files_panel.tree, w), "tr", (-30, 16)),
        (3, widget_rect(selector.file_list, w), "tr", (-30, 16)),
        (4, widget_rect(selector.data_list, w), "tr", (-30, 16)),
        (5, widget_rect(selector.results_list, w), "tr", (-30, 16)),
        (6, widget_rect(w.files_panel.add_button, w), "r", (-16, 0)),
        (7, widget_rect(w.dataset_list, w), "br", (-30, -40)),
        (8, widget_rect(w.tabs.tabBar(), w), "r", (16, 0)),
        (9, widget_rect(page, w), "c", (0, 120)),
        (10, widget_rect(w.inspector.tabs.tabBar(), w), "r", (16, 0)),
        (11, widget_rect(w.documentation_button, w), "l", (-16, 0)),
        (12, widget_rect(w.version_indicator, w), "l", (-16, 0)),
    ]
    return draw_callouts(image, marks)
