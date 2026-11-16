"""Shots for docs/getting-started/quickstart.md.

Dataset: ``testData/Al_Mg_Si__40C_0min_0498.h5`` (USAXS of an Al-Mg-Si alloy
with a saved pyIrena Unified Fit). The page walks from the File browser to an
exported PNG; each shot is the state after one step.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from ._common import Context, draw_callouts, shot, widget_rect
from ._package import (
    fixed_data_folder,
    flush_deletes,
    open_main_window,
    show_file_browser,
    wait_for_loads,
)

FILE = "Al_Mg_Si__40C_0min_0498.h5"
RESULT = "Unified Fit · Data + fit I(Q)"
TITLE = "Al-Mg-Si alloy, 40 °C"
DATA_SYMBOL_SIZE = 3.0
FIT_LINE_WIDTH = 3.0


def _check_result(ctx: Context, window) -> None:
    results = window.files_panel.selector.results_list
    for row in range(results.count()):
        item = results.item(row)
        if item.text().startswith(RESULT):
            item.setCheckState(Qt.CheckState.Checked)
            results.setCurrentItem(item)
            break
    else:
        raise LookupError(f"{RESULT!r} not offered for {FILE}")
    ctx.settle()


def chosen(ctx: Context):
    """Step 1: File browser on testData, the sample selected, its Unified Fit checked."""
    window = open_main_window(ctx)
    show_file_browser(ctx, window, fixed_data_folder(), select=FILE)
    _check_result(ctx, window)
    return window


def added(ctx: Context):
    """Step 2: after Add to graph."""
    window = chosen(ctx)
    window.files_panel.request_add()
    wait_for_loads(ctx, window)
    return window


def styled(ctx: Context):
    """Step 3: a title and box axes set in the Graph tab."""
    window = added(ctx)
    inspector = window.inspector
    inspector.tabs.setCurrentIndex(0)
    inspector.title.setText(TITLE)
    inspector.title.editingFinished.emit()
    ctx.settle()
    inspector.box_axes.setChecked(True)
    ctx.settle(100)
    return window


def _tab(inspector, text: str) -> int:
    return next(i for i in range(inspector.tabs.count()) if inspector.tabs.tabText(i) == text)


def restyled(ctx: Context):
    """Step 4: smaller data symbols and a thicker fit line, in the Datasets tab."""
    window = styled(ctx)
    inspector = window.inspector
    inspector.tabs.setCurrentIndex(_tab(inspector, "Datasets"))
    ctx.settle()
    for row, control, value in (
        (0, inspector.symbol_size, DATA_SYMBOL_SIZE),
        (1, inspector.line_width, FIT_LINE_WIDTH),
    ):
        inspector.series_list.setCurrentRow(row)
        ctx.settle()
        control.setValue(value)
        control.editingFinished.emit()
        ctx.settle(60)
    return window


@shot("quickstart-01-choose")
def choose(ctx: Context):
    w = chosen(ctx)
    panel = w.files_panel
    selector = panel.selector
    image = w.files_dock.grab()
    item = selector.file_list.currentItem()
    file_rect = selector.file_list.visualItemRect(item)
    file_rect.moveTopLeft(
        selector.file_list.viewport().mapTo(w.files_dock, file_rect.topLeft())
    )
    result_item = selector.results_list.currentItem()
    result_rect = selector.results_list.visualItemRect(result_item)
    result_rect.moveTopLeft(
        selector.results_list.viewport().mapTo(w.files_dock, result_rect.topLeft())
    )
    marks = [
        (1, widget_rect(panel.path_edit, w.files_dock), "r", (-16, 0)),
        (2, file_rect, "r", (-40, 0)),
        (3, result_rect, "r", (-40, 0)),
        (4, widget_rect(panel.add_button, w.files_dock), "r", (-16, 0)),
    ]
    return draw_callouts(image, marks)


@shot("quickstart-02-added")
def after_add(ctx: Context):
    w = added(ctx)
    return w.grab()


@shot("quickstart-03-styled")
def after_style(ctx: Context):
    w = styled(ctx)
    image = w.grab()
    inspector = w.inspector
    marks = [
        (1, widget_rect(inspector.title, w), "r", (-16, 0)),
        (2, widget_rect(inspector.box_axes, w), "l", (-16, 0)),
        (3, widget_rect(inspector.tabs.tabBar(), w), "r", (16, 0)),
    ]
    return draw_callouts(image, marks)


@shot("quickstart-04-datasets")
def after_restyle(ctx: Context):
    w = restyled(ctx)
    image = w.grab()
    inspector = w.inspector
    marks = [
        (1, widget_rect(inspector.tabs.tabBar(), w), "r", (16, 0)),
        (2, widget_rect(inspector.series_list, w), "tr", (-30, 16)),
        (3, widget_rect(inspector.line_width, w), "r", (16, 0)),
        (4, widget_rect(inspector.symbol_size, w), "r", (16, 0)),
    ]
    return draw_callouts(image, marks)


@shot("quickstart-05-preview")
def output_preview(ctx: Context):
    w = restyled(ctx)
    w._preview_output()
    ctx.settle(60)
    dialog = w._output_previews[-1]
    dialog.resize(900, 700)
    ctx.settle(60)
    image = dialog.grab()
    flush_deletes(ctx)
    return image
