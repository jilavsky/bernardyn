"""File browser dock: navigate folders and add data without a modal dialog.

The panel only chooses files and data; the main window owns importing and
undo, exactly as it does for :class:`~bernardyn.gui.dialogs.DataFileSelectorDialog`.
Its location, favorites, and list settings are user state, never workspace
data.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from PySide6.QtCore import QDir, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSplitter,
    QStyle,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from bernardyn.gui.dialogs import DataSelectorWidget
from bernardyn.io.sources import ScatteringLocation

#: Folders kept in the Places menu's "Recent" section.
RECENT_FOLDER_LIMIT = 10


def _folder_strings(value: object) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _shared_choices(preferences: Mapping[str, object] | None) -> dict[str, object]:
    """The selector choices shared with the data dialog; its list settings stay its own."""
    keys = ("dataset_profiles", "result_kinds", "q_unit", "error_percent")
    return {key: value for key, value in dict(preferences or {}).items() if key in keys}


class FileBrowserPanel(QWidget):
    """Folder navigation above a :class:`DataSelectorWidget` that stays open.

    Signals carry the files to use; the window reads the I(Q) and result
    choices for them from :attr:`selector`.
    """

    #: Files to add to the active graph.
    addRequested = Signal(object)
    #: Files whose I(Q) data replace the series selected in the Data browser.
    replaceRequested = Signal(object)
    #: Something worth persisting changed (folder, favorites).
    stateChanged = Signal()
    #: File to preview in the active graph, or None to remove the preview.
    previewRequested = Signal(object)

    #: Pause before previewing, so moving quickly through the list loads
    #: only the file you stop on.
    PREVIEW_DELAY_MS = 300

    def __init__(
        self,
        discover: Callable[[Path], list[ScatteringLocation]],
        shared_preferences: Mapping[str, object] | None = None,
        state: Mapping[str, object] | None = None,
        parent=None,
        *,
        discover_results: Callable[[Path], Mapping[str, tuple[str, tuple[str, ...]]]] | None = None,
    ) -> None:
        super().__init__(parent)
        stored = dict(state or {})
        self.folder: Path | None = None
        self._initial_folder = str(stored.get("folder", "") or "")
        self._back: list[Path] = []
        self.favorites: list[str] = _folder_strings(stored.get("favorites"))
        self.recent: list[str] = _folder_strings(stored.get("recent"))[:RECENT_FOLDER_LIMIT]
        self._syncing_tree = False
        style = self.style()

        self.back_button = QToolButton(self)
        self.back_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.back_button.setToolTip("Back to the previous folder")
        self.back_button.clicked.connect(self.go_back)
        self.up_button = QToolButton(self)
        self.up_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogToParent))
        self.up_button.setToolTip("Up to the parent folder")
        self.up_button.clicked.connect(self.go_up)
        self.path_edit = QLineEdit(self)
        self.path_edit.setPlaceholderText("Type or paste a folder path, then press Enter")
        self.path_edit.setToolTip("Type or paste a folder path, then press Enter")
        self.path_edit.returnPressed.connect(self._path_entered)
        self.favorite_button = QToolButton(self)
        self.favorite_button.setCheckable(True)
        self.favorite_button.setToolTip("Add this folder to Favorites (Places menu)")
        self.favorite_button.clicked.connect(self._toggle_favorite)
        self.places_button = QToolButton(self)
        self.places_button.setText("Places")
        self.places_button.setToolTip("Favorites, recent folders, home, or choose a folder")
        self.places_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.places_menu = QMenu(self.places_button)
        self.places_menu.aboutToShow.connect(self._populate_places_menu)
        self.places_button.setMenu(self.places_menu)
        self.refresh_button = QToolButton(self)
        self.refresh_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_button.setToolTip("Re-read this folder (F5), e.g. while data are being collected")
        self.refresh_button.clicked.connect(self.refresh)
        navigation = QHBoxLayout()
        navigation.setSpacing(2)
        for widget in (self.back_button, self.up_button):
            navigation.addWidget(widget)
        navigation.addWidget(self.path_edit, 1)
        for widget in (self.favorite_button, self.places_button, self.refresh_button):
            navigation.addWidget(widget)

        # Folders only: files are listed by the selector, and an HDF5 file is
        # opened only when it becomes current.  This keeps network drives
        # (SSHFS-Win) responsive while browsing.
        self.folder_model = QFileSystemModel(self)
        self.folder_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot | QDir.Filter.Drives)
        self.folder_model.setRootPath("")
        self.tree = QTreeView(self)
        self.tree.setModel(self.folder_model)
        for column in range(1, self.folder_model.columnCount()):
            self.tree.hideColumn(column)
        self.tree.setHeaderHidden(True)
        self.tree.setToolTip("Click a folder to list its data files below")
        self.tree.selectionModel().currentChanged.connect(self._tree_folder_changed)
        # The model reads folders in the background; scroll again once the
        # path to the current folder has actually been loaded.
        self.folder_model.directoryLoaded.connect(self._folder_loaded)

        self.selector = DataSelectorWidget(
            Path.home(),
            discover,
            {**_shared_choices(shared_preferences), **stored},
            # Nothing is listed until start(): the first folder may be on a
            # network drive and must not delay building the window.
            [],
            self,
            discover_results=discover_results,
            orientation=Qt.Orientation.Vertical,
        )
        # Let the tree have a real share of a short dock; the lists scroll.
        for widget in (self.selector.file_list, self.selector.data_list, self.selector.results_list):
            widget.setMinimumHeight(48)
        self.selector.file_list.setDragEnabled(True)
        self.selector.file_list.setToolTip(
            "Double-click or Enter adds to the active graph. Drag onto a graph tab "
            "or the Data browser to add there."
        )
        self.selector.activated.connect(self.request_add)
        self.options_toggle = QToolButton(self)
        self.options_toggle.setText("Import options")
        self.options_toggle.setCheckable(True)
        self.options_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.options_toggle.setToolTip("Q unit and uncertainty used when a file does not store them")
        self.options_toggle.toggled.connect(self._show_options)
        self.options_toggle.setChecked(bool(stored.get("options_open", False)))
        self._show_options(self.options_toggle.isChecked())
        self.preview_box = QCheckBox("Preview in graph", self)
        self.preview_box.setToolTip(
            "Show the current file as a grey dashed curve in the active graph while you move "
            "through the list. Add to graph or Replace keeps it; nothing else changes the graph."
        )
        self.preview_box.setChecked(bool(stored.get("preview", False)))
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(self.PREVIEW_DELAY_MS)
        self._preview_timer.timeout.connect(self._emit_preview)
        self.preview_box.toggled.connect(self._preview_toggled)
        self.selector.file_list.currentItemChanged.connect(self.schedule_preview)
        self.selector.data_list.itemChanged.connect(self.schedule_preview)

        self.add_button = QPushButton("Add to graph", self)
        self.add_button.setToolTip("Add the checked data of the selected files to the active graph (Enter)")
        self.add_button.clicked.connect(self.request_add)
        self.replace_button = QPushButton("Replace selected series", self)
        self.replace_button.setToolTip(
            "Use the checked I(Q) data of the selected files instead of the series selected in "
            "the Data browser, keeping their style and position (Ctrl+R)"
        )
        self.replace_button.clicked.connect(self.request_replace)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        self.message.setObjectName("fileBrowserMessage")

        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.selector)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        sizes = stored.get("splitter")
        if isinstance(sizes, list) and len(sizes) == 2 and all(isinstance(s, int) for s in sizes):
            self.splitter.setSizes(sizes)
        # Without stored sizes the split is set in start(), once the dock has
        # its real height; sizes set before that are rescaled by Qt.
        self._default_split = not (isinstance(sizes, list) and len(sizes) == 2)
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button, 1)
        buttons.addWidget(self.replace_button, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(navigation)
        layout.addWidget(self.splitter, 1)
        options_row = QHBoxLayout()
        options_row.addWidget(self.options_toggle)
        options_row.addStretch()
        options_row.addWidget(self.preview_box)
        layout.addLayout(options_row)
        layout.addLayout(buttons)
        layout.addWidget(self.message)

        context = Qt.ShortcutContext.WidgetWithChildrenShortcut
        for key, slot in (("Ctrl+R", self.request_replace), (QKeySequence.StandardKey.Refresh, self.refresh)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(context)
            shortcut.activated.connect(slot)
        # List settings are saved on window close only when edited here, so
        # merely opening a window never rewrites the user's stored choices.
        self.settings_changed = False
        for signal in (
            self.selector.file_type.currentIndexChanged,
            self.selector.sort.currentIndexChanged,
            self.selector.include_subfolders.toggled,
            self.selector.group_by_folder.toggled,
            self.selector.filter.textEdited,
            self.splitter.splitterMoved,
            self.options_toggle.toggled,
            self.preview_box.toggled,
        ):
            signal.connect(self._mark_settings_changed)
        self._update_navigation()

    def _mark_settings_changed(self, *_args) -> None:
        self.settings_changed = True

    # ------------------------------------------------------------------ state
    def start(self, fallback: str | Path | None = None) -> None:
        """List the remembered folder, else *fallback*, else the home folder.

        Does nothing once a folder is shown, so a late start never moves away
        from a folder the user already opened.
        """
        if self._default_split and (total := sum(self.splitter.sizes())) > 0:
            self.splitter.setSizes([int(total * 0.3), total - int(total * 0.3)])
            self._default_split = False
        if self.folder is not None:
            return
        for candidate in (self._initial_folder, fallback, Path.home()):
            if candidate and self.navigate(candidate, remember=False):
                return

    def state(self) -> dict[str, object]:
        """Panel settings to keep in user state (not the shared selector choices)."""
        preferences = self.selector.preferences()
        return {
            "folder": "" if self.folder is None else str(self.folder),
            "favorites": list(self.favorites),
            "recent": list(self.recent),
            "file_type": preferences["file_type"],
            "sort_index": preferences["sort_index"],
            "include_subfolders": preferences["include_subfolders"],
            "group_by_folder": preferences["group_by_folder"],
            "filter": preferences["filter"],
            "splitter": [int(size) for size in self.splitter.sizes()],
            "options_open": self.options_toggle.isChecked(),
            "preview": self.preview_box.isChecked(),
        }

    def show_message(self, text: str) -> None:
        self.message.setText(text)

    # ------------------------------------------------------------- navigation
    def navigate(self, folder: str | Path, *, remember: bool = True, history: bool = True) -> bool:
        """Show *folder*; False (and a message) when it is not an accessible folder.

        ``remember`` adds it to Recent folders; ``history`` lets Back return
        to the folder being left.
        """
        target = Path(folder).expanduser()
        try:
            accessible = target.is_dir()
        except OSError:
            accessible = False
        if not accessible:
            self.show_message(f"Folder not found: {target}")
            return False
        target = target.resolve()
        if history and self.folder is not None and target != self.folder:
            self._back.append(self.folder)
        self.folder = target
        self.path_edit.setText(str(target))
        self.selector.set_folder(target)
        self._select_in_tree(target)
        self.show_message("")
        if remember:
            text = str(target)
            self.recent = [text, *(item for item in self.recent if item != text)][:RECENT_FOLDER_LIMIT]
            self.stateChanged.emit()
        self._update_navigation()
        return True

    def go_back(self) -> None:
        while self._back:
            if self.navigate(self._back.pop(), history=False):
                break
        self._update_navigation()

    def go_up(self) -> None:
        if self.folder is not None and self.folder.parent != self.folder:
            self.navigate(self.folder.parent)

    def refresh(self) -> None:
        self.selector.forget_cached_contents()
        self.selector.refresh()

    def _path_entered(self) -> None:
        if not self.navigate(self.path_edit.text().strip()) and self.folder is not None:
            # Keep the typed text so a small typo can be fixed in place.
            self.path_edit.selectAll()

    def _select_in_tree(self, folder: Path) -> None:
        index = self.folder_model.index(str(folder))
        if not index.isValid():
            return
        self._syncing_tree = True
        try:
            parent = index.parent()
            while parent.isValid():
                self.tree.expand(parent)
                parent = parent.parent()
            self.tree.setCurrentIndex(index)
            self.tree.scrollTo(index)
        finally:
            self._syncing_tree = False

    def _folder_loaded(self, loaded: str) -> None:
        if self.folder is None:
            return
        try:
            on_the_way = self.folder == Path(loaded) or Path(loaded) in self.folder.parents
        except (OSError, ValueError):
            return
        if on_the_way:
            # Rows arrive just after this signal; scroll once they are laid out.
            QTimer.singleShot(0, lambda: self.folder is not None and self._select_in_tree(self.folder))

    def _tree_folder_changed(self, current, _previous=None) -> None:
        if self._syncing_tree or not current.isValid():
            return
        path = self.folder_model.filePath(current)
        if path:
            self.navigate(path)

    def _update_navigation(self) -> None:
        self.back_button.setEnabled(bool(self._back))
        self.up_button.setEnabled(self.folder is not None and self.folder.parent != self.folder)
        is_favorite = self.folder is not None and str(self.folder) in self.favorites
        self.favorite_button.setChecked(is_favorite)
        self.favorite_button.setText("★" if is_favorite else "☆")
        self.favorite_button.setEnabled(self.folder is not None)

    def _toggle_favorite(self) -> None:
        if self.folder is None:
            return
        text = str(self.folder)
        if text in self.favorites:
            self.favorites.remove(text)
        else:
            self.favorites.append(text)
        self._update_navigation()
        self.stateChanged.emit()

    def _populate_places_menu(self) -> None:
        menu = self.places_menu
        menu.clear()
        for title, folders in (("Favorites", self.favorites), ("Recent", self.recent)):
            menu.addSection(title)
            if not folders:
                menu.addAction("(none)").setEnabled(False)
            for folder in folders:
                action = menu.addAction(folder)
                action.triggered.connect(lambda _=False, f=folder: self.navigate(f))
        menu.addSeparator()
        menu.addAction("Home folder", lambda: self.navigate(Path.home()))
        menu.addAction("Choose folder…", self._choose_folder)

    def _choose_folder(self) -> None:
        start = "" if self.folder is None else str(self.folder)
        selected = QFileDialog.getExistingDirectory(self, "Show folder in File browser", start)
        if selected:
            self.navigate(selected)

    # ---------------------------------------------------------------- actions
    def _show_options(self, shown: bool) -> None:
        self.selector.options_widget.setVisible(shown)
        self.options_toggle.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)

    def schedule_preview(self, *_args) -> None:
        """Preview the current file after a short pause (if Preview is on)."""
        if self.preview_box.isChecked():
            self._preview_timer.start()

    def _preview_toggled(self, shown: bool) -> None:
        if shown:
            self._emit_preview()
        else:
            self._preview_timer.stop()
            self.previewRequested.emit(None)

    def _emit_preview(self) -> None:
        self.previewRequested.emit(
            self.selector.current_path if self.preview_box.isChecked() else None
        )

    def request_add(self) -> None:
        self.addRequested.emit(self.selector.selected_paths())

    def request_replace(self) -> None:
        self.replaceRequested.emit(self.selector.selected_paths())
