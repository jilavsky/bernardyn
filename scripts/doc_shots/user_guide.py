"""Shots for docs/guides/user-guide.md.

Datasets (``testData/``):

* ``Al_Mg_Si__40C_0min_0498.h5``: USAXS I(Q) (desmeared and slit-smeared) with
  saved pyIrena Unified Fit and Size Distribution results.
* ``Rh1_0085.h5``: a second USAXS sample, I(Q) only (File browser preview).
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from ._common import Context, draw_callouts, shot, widget_rect
from ._package import (
    fixed_data_folder,
    graph_strip,
    open_main_window,
    show_file_browser,
    wait_for_loads,
)

SAMPLE = "Al_Mg_Si__40C_0min_0498.h5"
OTHER = "Rh1_0085.h5"


def _item_rect(list_widget, item, root):
    rect = list_widget.visualItemRect(item)
    rect.moveTopLeft(list_widget.viewport().mapTo(root, rect.topLeft()))
    return rect


def _check_first(list_widget, prefix: str = ""):
    """Check the first item whose text starts with *prefix*; return it."""
    for row in range(list_widget.count()):
        item = list_widget.item(row)
        if item.text().startswith(prefix) and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            item.setCheckState(Qt.CheckState.Checked)
            return item
    raise LookupError(f"no checkable item starting with {prefix!r}")


@shot("user-guide-01-data-selector")
def data_selector(ctx: Context):
    """Open folder… on testData: the data selector with the sample selected."""
    from bernardyn.gui.dialogs import DataFileSelectorDialog
    from bernardyn.gui.main_window import _results_in_file

    w = open_main_window(ctx)
    folder = fixed_data_folder()
    dialog = DataFileSelectorDialog(
        folder,
        w.controller.sources.discover_path,
        {},
        None,
        w,
        discover_results=_results_in_file,
        iq_results_allowed=True,
    )
    ctx.show(dialog, (1100, 620))
    selector = dialog.selector
    ctx.wait_until(lambda: selector.file_list.count() > 0, 30)
    for row in range(selector.file_list.count()):
        if selector.file_list.item(row).text().endswith(SAMPLE):
            selector.file_list.setCurrentRow(row)
            break
    ctx.wait_until(lambda: selector.data_list.count() > 0, 30)
    iq = _check_first(selector.data_list)
    result = _check_first(selector.results_list, "Unified Fit · Data + fit")
    ctx.settle(60)
    image = dialog.grab()
    add = next(
        b for b in dialog.findChildren(type(w.files_panel.add_button)) if b.text().startswith("Add")
    )
    marks = [
        (1, widget_rect(selector.file_list, dialog), "tr", (-30, 16)),
        (2, _item_rect(selector.data_list, iq, dialog), "r", (-40, 0)),
        (3, _item_rect(selector.results_list, result, dialog), "r", (-40, 0)),
        (4, widget_rect(add, dialog), "l", (-16, 0)),
    ]
    return draw_callouts(image, marks)


@shot("user-guide-02-preview")
def file_browser_preview(ctx: Context):
    """A graph with the sample's I(Q); the File browser previews a second file."""
    w = open_main_window(ctx)
    folder = fixed_data_folder()
    w._open_data_paths([folder / SAMPLE], use_preferred=True)
    wait_for_loads(ctx, w)
    panel = w.files_panel
    show_file_browser(ctx, w, folder, select=OTHER)
    _check_first(panel.selector.data_list)
    panel.preview_box.setChecked(True)
    ctx.wait_until(lambda: w._preview_page is not None and w._preview_worker is None, 30)
    ctx.settle(100)
    image = w.grab()
    marks = [
        (1, widget_rect(panel.preview_box, w), "l", (-16, 0)),
        (2, widget_rect(w.tabs.currentWidget(), w), "c", (60, 40)),
    ]
    return draw_callouts(image, marks)


@shot("user-guide-03-distribution")
def distribution_graph(ctx: Context):
    """Size Distribution · Volume distribution: a new graph of that curve."""
    w = open_main_window(ctx)
    folder = fixed_data_folder()
    w._import_result_selection(
        [folder / SAMPLE], {"size_distribution": ("volume_distribution",)}
    )
    ctx.settle(100)
    return graph_strip(w)


def _porod_graph(ctx: Context):
    w = open_main_window(ctx)
    folder = fixed_data_folder()
    w._open_data_paths([folder / SAMPLE], use_preferred=True)
    wait_for_loads(ctx, w)
    return w


def _power_law_dialog(w):
    from bernardyn.gui.dialogs import AnnotationDialog

    inspector = w.inspector
    position, _ = inspector._annotation_defaults()
    dialog = AnnotationDialog(default_position=position, parent=inspector)
    dialog.kind.setCurrentIndex(dialog.kind.findData("power_law"))
    return dialog


@shot("user-guide-04-power-law-dialog")
def power_law_dialog(ctx: Context):
    """Annotations → Power-law slope…: the dialog with its defaults (P = 4)."""
    w = _porod_graph(ctx)
    dialog = _power_law_dialog(w)
    dialog.show()  # natural size: a taller dialog only grows its top label
    ctx.settle(60)
    return dialog.grab()


@shot("user-guide-05-power-law-graph")
def power_law_graph(ctx: Context):
    """The graph after OK in that dialog: a one-decade Porod guide."""
    w = _porod_graph(ctx)
    dialog = _power_law_dialog(w)
    w.inspector._upsert_annotation(dialog.value(), "Add power-law slope")
    ctx.settle(100)
    return graph_strip(w)
