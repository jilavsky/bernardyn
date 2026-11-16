"""Per-package part of the documentation screenshot machinery.

Copied from jilavsky-docs/templates/package-docs; **this is the only file in
scripts/doc_shots/ that differs between packages** (like the PER-PACKAGE
block of docs/conf.py). These are Bernardyn's values.

``isolate_settings`` runs before anything imports Qt or the package, and
again before every shot, so each shot starts from the coded defaults and
nothing is written to the user's real settings.

Where Bernardyn keeps user state (checked 2026-11-16):

* ``bernardyn.state.UserState``: ``~/.bernardyn/state.json`` through
  ``Path.home()``: last folder, recent workspaces, last workspace, data
  selector and File browser choices. Redirected by pointing ``HOME`` (and
  ``USERPROFILE`` on Windows) into the scratch folder.
* ``MainWindow._template_folder``: Qt's ``AppDataLocation`` + ``templates``.
  On macOS Qt ignores ``HOME`` here, so the method is replaced with one that
  returns a scratch folder. The application also runs under its own
  organisation/application name, so anything else Qt might store lands in a
  separate ``Bernardyn-docshots`` entry, never the real ``Bernardyn`` one.
* ``~/.bernardyn/logs``: written only by ``bernardyn.app.main()``, which the
  script never calls; covered by ``HOME`` anyway.
* Workspace ``.lock`` files sit beside the package, i.e. in scratch.
* Bernardyn does not use ``QSettings``.
* MCP paths ``BERNARDYN_DATA_ROOT`` / ``BERNARDYN_OUTPUT_ROOT`` point at scratch
  in case a shot uses the MCP code.
"""

from __future__ import annotations

import os
from pathlib import Path

from ._common import REPO

#: Default folder for Context.dataset(): tracked input files for the shots.
DATA_ROOT: Path = REPO / "testData"

#: Callout circles: an orange that reads on white and on plots.
CALLOUT_FILL = "#c2410c"
CALLOUT_RADIUS = 12

#: Organisation and application name for the run (the real app uses "Bernardyn").
APP_NAME = "Bernardyn-docshots"

#: Folder handed out by the replaced ``MainWindow._template_folder``.
_template_folder: Path | None = None


def isolate_settings(scratch: Path) -> None:
    """Point every settings/state location of Bernardyn into *scratch*."""
    global _template_folder
    home = scratch / "home"
    home.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    os.environ["BERNARDYN_DATA_ROOT"] = str(scratch)
    os.environ["BERNARDYN_OUTPUT_ROOT"] = str(scratch / "mcp-output")
    _template_folder = scratch / "templates"


def make_app():
    """Create the offscreen QApplication as ``bernardyn.app.main`` sets it up."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import bernardyn
    from bernardyn.gui import main_window

    def template_folder(self) -> Path:
        folder = _template_folder or Path(os.environ["HOME"]) / "templates"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    main_window.MainWindow._template_folder = template_folder

    # An unexpected message box is modal and would hang the offscreen run:
    # fail the shot with its text instead.
    from PySide6.QtWidgets import QMessageBox

    def refuse(kind):
        def box(_parent, title, text, *args, **kwargs):
            raise RuntimeError(f"unexpected {kind} dialog {title!r}: {text}")

        return staticmethod(box)

    for kind in ("warning", "information", "critical", "question"):
        setattr(QMessageBox, kind, refuse(kind))

    app =QApplication.instance() or QApplication(["make_doc_screenshots"])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(bernardyn.__version__)
    app.setOrganizationName(APP_NAME)
    # Bernardyn has no theme of its own and no window-geometry persistence
    # outside the workspace package; Fusion gives the same light look on every
    # platform the shots are regenerated on.
    app.setStyle("Fusion")
    return app


def open_main_window(ctx, size: tuple[int, int] = (1800, 1000), docks=(330, 260, 540)):
    """A fresh ``MainWindow`` at a fixed size and fixed panel widths.

    Args:
        ctx: The shot context.
        size: Window size in pixels.
        docks: Widths of the File browser, Data browser and Graph inspector.

    The File browser starts in the scratch home (no remembered folder); shots
    that show it navigate it themselves (:func:`show_file_browser`).
    """
    from PySide6.QtCore import Qt

    from bernardyn.gui.main_window import MainWindow

    window = MainWindow()
    ctx.show(window, size)
    ctx.settle(60)
    window.resizeDocks(
        [window.files_dock, window.datasets_dock, window.inspector_dock],
        list(docks),
        Qt.Orientation.Horizontal,
    )
    ctx.settle(60)
    return window


def show_file_browser(ctx, window, folder: Path, select: str | None = None) -> None:
    """Point the File browser at *folder*, optionally making file *select* current.

    The folder tree is rooted at *folder*'s parent, so the shot shows only the
    fixed docs folder and not whatever else lives in the temporary directory.
    """
    panel = window.files_panel
    panel.navigate(folder, remember=False)
    ctx.wait_until(lambda: panel.selector.file_list.count() > 0, 30)
    model = panel.folder_model
    root = model.index(str(folder.resolve().parent))
    if root.isValid():
        panel.tree.setRootIndex(root)
        panel._select_in_tree(folder.resolve())
    if select:
        file_list = panel.selector.file_list
        for row in range(file_list.count()):
            item = file_list.item(row)
            if item.text().endswith(select):
                file_list.setCurrentItem(item)
                break
        ctx.wait_until(lambda: panel.selector.data_list.count() > 0, 30)
    ctx.settle(60)


def wait_for_loads(ctx, window, timeout: float = 60.0) -> None:
    """Process events until every queued source load has finished and rendered."""
    ctx.wait_until(lambda: not window._workers and not window._load_batches, timeout)
    ctx.settle(60)


def fixed_data_folder(name: str = "testData") -> Path:
    """Copy ``testData/`` to ``<temp>/bernardyn-docs/<name>`` and return it.

    A fixed path, so a folder shown in a screenshot reads the same on every
    run (``/tmp/bernardyn-docs/testData`` on macOS/Linux). Rebuilt each call.
    """
    import shutil
    import tempfile

    root = Path("/tmp") if os.name != "nt" else Path(tempfile.gettempdir())
    target = root / "bernardyn-docs" / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(DATA_ROOT, target)
    return target


def flush_deletes(ctx) -> None:
    """Delete widgets queued with ``deleteLater()``.

    Outside a running event loop ``processEvents()`` does not handle deferred
    deletes. The 2-D renderer closes its temporary output widget and queues
    its deletion; left alive, it is a top-level widget that the script's
    clean-up would close a second time, which pyqtgraph does not allow.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    ctx.settle(5)
