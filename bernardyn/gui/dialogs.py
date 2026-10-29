"""Focused workbench dialogs that return domain values."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path

import h5py
from PySide6.QtCore import (
    QItemSelectionModel,
    QMimeData,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bernardyn.core.models import Annotation, AnnotationKind
from bernardyn.core.transforms import PlotTransform
from bernardyn.io.file_browser import (
    DEFAULT_SORT_INDEX,
    FILE_TYPE_CHOICES,
    FILTER_PLACEHOLDER,
    FILTER_TOOLTIP,
    SORT_LABELS,
    SORT_TOOLTIP,
    SUBFOLDER_LIMIT,
    child_folders,
    display_name,
    files_in_folder,
    make_file_matcher,
    sort_paths,
)
from bernardyn.io.result_batch import IQ_KIND, kind_label
from bernardyn.io.sources import ScatteringLocation


class StatusLabel(QLabel):
    """A status line whose text never resizes the panel around it.

    A word-wrapping label is at least as wide as its longest unbreakable word,
    so a long file name or HDF5 path used to widen the dock, and the panel
    jumped back when the text changed.  This label takes whatever width the
    layout gives it, reserves a fixed number of lines, may break after ``/``,
    ``\\`` and ``_``, and shows the full text as its tooltip when clipped.
    ``text()`` returns the text as set.
    """

    _BREAK_AFTER = ("/", "\\", "_")

    def __init__(self, text: str = "", parent=None, *, lines: int = 2) -> None:
        super().__init__(parent)
        self._plain = ""
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(1)
        self.setFixedHeight(self.fontMetrics().lineSpacing() * lines + 4)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        self._plain = str(text)
        shown = self._plain
        for mark in self._BREAK_AFTER:
            # A zero-width space is a line-break opportunity for Qt's layout.
            shown = shown.replace(mark, mark + "\u200b")
        super().setText(shown)
        self.setToolTip(self._plain)

    def text(self) -> str:
        return self._plain


#: Marks a drag that started in the File browser, so a drop adds the files
#: with the browser's current choices instead of opening the data dialog.
FILE_BROWSER_MIME_TYPE = "application/x-bernardyn-file-browser"


class _FileListWidget(QListWidget):
    """File list whose drags carry the files themselves (as local URLs)."""

    def mimeData(self, items) -> QMimeData:  # noqa: N802 - Qt API
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(str(item.data(Qt.ItemDataRole.UserRole))) for item in items])
        data.setData(FILE_BROWSER_MIME_TYPE, b"1")
        return data


class _SubfolderListingSignals(QObject):
    # (generation, files of one subfolder)
    listed = Signal(int, object)
    # (generation, message; empty when every subfolder was listed)
    finished = Signal(int, str)


class _SubfolderListingWorker(QRunnable):
    """Lists the files of each first-level subfolder, off the GUI thread.

    Over a network drive each directory read can take a while; the file list
    shows the folder's own files at once and grows as each subfolder arrives.
    """

    def __init__(self, generation: int, folder: Path, file_type: str) -> None:
        super().__init__()
        self.generation = generation
        self.folder = folder
        self.file_type = file_type
        self.cancelled = False
        self.signals = _SubfolderListingSignals()

    def run(self) -> None:
        folders = child_folders(self.folder)
        if len(folders) > SUBFOLDER_LIMIT:
            self.signals.finished.emit(
                self.generation,
                f"{len(folders)} subfolders: more than {SUBFOLDER_LIMIT}, so none are listed. "
                "Open one of them instead.",
            )
            return
        for folder in folders:
            if self.cancelled:
                return
            files = files_in_folder(folder, self.file_type)
            if files:
                self.signals.listed.emit(self.generation, files)
        self.signals.finished.emit(self.generation, "")


class DataSelectorWidget(QWidget):
    """Files on one side, the I(Q) data and saved pyIrena results to add on the other.

    Shared by :class:`DataFileSelectorDialog` and the File browser dock, so a
    file layout taught in one is handled the same way by the other.  Both kinds
    of data in the current file are listed with the same prominence.  I(Q)
    choices are remembered per file layout; a checked result kind (say
    "Unified Fit · Residuals") applies to every selected file that stores it.

    ``orientation`` places the data lists beside (horizontal, dialog) or below
    (vertical, dock) the file list.
    """

    #: Double-click or Enter on a file.
    activated = Signal()

    def __init__(
        self,
        folder: Path,
        discover: Callable[[Path], list[ScatteringLocation]],
        preferences: Mapping[str, object] | None = None,
        paths: list[Path] | None = None,
        parent=None,
        *,
        discover_results: Callable[[Path], Mapping[str, tuple[str, tuple[str, ...]]]] | None = None,
        iq_results_allowed: bool = True,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
    ) -> None:
        super().__init__(parent)
        self.folder = Path(folder)
        self._discover = discover
        # path -> {analysis: (title, available curve kinds)}
        self._discover_results = discover_results
        self._results: dict[Path, Mapping[str, tuple[str, tuple[str, ...]]]] = {}
        self._iq_results_allowed = iq_results_allowed
        self._fixed_paths = [Path(path) for path in paths] if paths is not None else None
        stored = dict(preferences or {})
        self._profiles: dict[str, list[int]] = {}
        # "analysis/kind" keys of the result curves to add.
        self._checked_results: set[str] = set()
        self._read_shared_preferences(stored)
        self._locations: dict[Path, list[ScatteringLocation]] = {}
        self._errors: dict[Path, str] = {}
        self._current_path: Path | None = None
        self._syncing = False
        # Every listed file (the folder's own, then subfolders as they arrive).
        self._all_paths: list[Path] = []
        self._listing_generation = 0
        self._listing_worker: _SubfolderListingWorker | None = None
        self._listing_note = ""
        self._listing_pool = QThreadPool(self)
        self._listing_pool.setMaxThreadCount(1)
        vertical = orientation == Qt.Orientation.Vertical
        self.file_type = QComboBox(self)
        for label, value in FILE_TYPE_CHOICES:
            self.file_type.addItem(label, value)
        self.sort = QComboBox(self)
        self.sort.addItems(SORT_LABELS)
        self.sort.setToolTip(SORT_TOOLTIP)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText(FILTER_PLACEHOLDER)
        self.filter.setToolTip(FILTER_TOOLTIP)
        self.filter.setClearButtonEnabled(True)
        self.count = StatusLabel(parent=self)
        self.file_list = _FileListWidget(self)
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.currentItemChanged.connect(self._file_selected)
        # itemActivated covers both double-click and Enter.
        self.file_list.itemActivated.connect(lambda _item: self.activated.emit())
        self.data_list = QListWidget(self)
        self.data_list.itemChanged.connect(self._data_selection_changed)
        self.data_list.setToolTip("Check one or more 1-D data sets to load from the selected file.")
        self.data_status = StatusLabel("Select a file to inspect its 1-D data.", self)
        self.results_list = QListWidget(self)
        self.results_list.itemChanged.connect(self._result_selection_changed)
        self.results_list.setToolTip(
            "Check saved results to add. A checked kind is added from every selected file "
            "that stores it."
        )
        self.results_status = StatusLabel(parent=self)
        self.q_unit = QComboBox(self)
        self.q_unit.addItems(["1/A", "1/nm", "1/pm", "1/um", "1/mm"])
        self.error_fraction = QDoubleSpinBox(self)
        self.error_fraction.setRange(0.0001, 100.0)
        self.error_fraction.setDecimals(3)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("File type:" if not vertical else "Type:"))
        controls.addWidget(self.file_type, int(vertical))
        controls.addWidget(QLabel("Sort:"))
        controls.addWidget(self.sort, int(vertical))
        if not vertical:
            controls.addStretch()
        self.include_subfolders = QCheckBox("Include subfolders", self)
        self.include_subfolders.setToolTip(
            "Also list files in the folders directly inside this one (one level, e.g. the "
            "USAXS, SAXS, and WAXS folders of a sample). They are shown as subfolder/file, "
            "and the filter matches that text."
        )
        self.group_by_folder = QCheckBox("Group by folder", self)
        self.group_by_folder.setToolTip(
            "Keep each folder's files together and sort within each; otherwise files from "
            "all folders are sorted together."
        )
        subfolder_row = QHBoxLayout()
        subfolder_row.addWidget(self.include_subfolders)
        subfolder_row.addWidget(self.group_by_folder)
        subfolder_row.addStretch()
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        filter_row.addWidget(self.filter, 1)
        select_all = QPushButton("Select all visible", self)
        select_all.clicked.connect(self._select_all_visible)
        filter_row.addWidget(select_all)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addLayout(subfolder_row)
        layout.addLayout(filter_row)
        files_box = QWidget(self)
        left = QVBoxLayout(files_box)
        left.setContentsMargins(0, 0, 0, 0)
        if not vertical:
            left.addWidget(QLabel("Files"))
        left.addWidget(self.file_list, 1)
        left.addWidget(self.count)
        data_box = QWidget(self)
        right = QVBoxLayout(data_box)
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(QLabel("<b>I(Q) data</b> in the current file"))
        right.addWidget(self.data_list, 1)
        right.addWidget(self.data_status)
        if discover_results is not None:
            right.addWidget(QLabel("<b>Saved pyIrena results</b> in the current file"))
            right.addWidget(self.results_list, 1)
            right.addWidget(self.results_status)
        else:
            self.results_list.hide()
            self.results_status.hide()
        self.splitter = QSplitter(orientation, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(files_box)
        self.splitter.addWidget(data_box)
        self.splitter.setStretchFactor(0, 3 if vertical else 1)
        self.splitter.setStretchFactor(1, 2 if vertical else 1)
        layout.addWidget(self.splitter, 1)
        # The import options apply only when a file lacks them (text data); the
        # dock tucks them away, the dialog shows them as before.
        self.options_widget = QWidget(self)
        if vertical:
            options = QFormLayout(self.options_widget)
            options.addRow("Q unit when missing:", self.q_unit)
            options.addRow("Missing uncertainty (%):", self.error_fraction)
        else:
            options = QHBoxLayout(self.options_widget)
            options.addWidget(QLabel("Q unit when missing:"))
            options.addWidget(self.q_unit)
            options.addSpacing(12)
            options.addWidget(QLabel("Missing intensity uncertainty (%):"))
            options.addWidget(self.error_fraction)
            options.addStretch()
        options.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.options_widget)
        self.file_type.setCurrentIndex(
            max(0, self.file_type.findData(stored.get("file_type", "all")))
        )
        self.sort.setCurrentIndex(int(stored.get("sort_index", DEFAULT_SORT_INDEX)))
        self.include_subfolders.setChecked(bool(stored.get("include_subfolders", False)))
        self.group_by_folder.setChecked(bool(stored.get("group_by_folder", False)))
        self.filter.setText(str(stored.get("filter", "")))
        self.q_unit.setCurrentIndex(max(0, self.q_unit.findText(str(stored.get("q_unit", "1/A")))))
        self.error_fraction.setValue(float(stored.get("error_percent", 5.0)))
        self.file_type.currentIndexChanged.connect(self.refresh)
        self.include_subfolders.toggled.connect(self.refresh)
        # A different order needs no new listing.
        self.sort.currentIndexChanged.connect(self._rebuild_file_list)
        self.group_by_folder.toggled.connect(self._rebuild_file_list)
        self.filter.textChanged.connect(self._apply_filter)
        self.refresh()

    def _read_shared_preferences(self, stored: Mapping[str, object]) -> None:
        self._profiles = {
            str(key): [int(index) for index in value]
            for key, value in dict(stored.get("dataset_profiles", {})).items()
            if isinstance(value, list)
        }
        self._checked_results = {
            str(item) for item in stored.get("result_kinds", []) if isinstance(item, str)
        }

    def adopt_shared_preferences(self, preferences: Mapping[str, object]) -> None:
        """Take over layout choices, result kinds, and import options learned elsewhere."""
        stored = dict(preferences or {})
        self._read_shared_preferences(stored)
        if "q_unit" in stored:
            self.q_unit.setCurrentIndex(max(0, self.q_unit.findText(str(stored["q_unit"]))))
        if "error_percent" in stored:
            self.error_fraction.setValue(float(stored["error_percent"]))
        self._populate_data_list()
        self._populate_results_list()

    @property
    def current_path(self) -> Path | None:
        """The file whose contents the I(Q) and results lists show."""
        return self._current_path

    def set_folder(self, folder: Path) -> None:
        """List another folder; learned layout choices are kept."""
        self.folder = Path(folder)
        self._fixed_paths = None
        self.refresh()

    def set_iq_results_allowed(self, allowed: bool) -> None:
        """Data + fit joins only an I(Q) graph; follow the active graph's view."""
        if allowed != self._iq_results_allowed:
            self._iq_results_allowed = allowed
            self._populate_results_list()

    def forget_cached_contents(self) -> None:
        """Re-read files on next use, e.g. ones still being written."""
        self._locations.clear()
        self._errors.clear()
        self._results.clear()

    def refresh(self) -> None:
        """List the folder again: its own files now, first-level subfolders in the background."""
        self._stop_listing()
        listing_folder = self._fixed_paths is None
        self.include_subfolders.setEnabled(listing_folder)
        self.group_by_folder.setEnabled(listing_folder and self.include_subfolders.isChecked())
        file_type = str(self.file_type.currentData())
        self._all_paths = (
            list(self._fixed_paths) if not listing_folder else files_in_folder(self.folder, file_type)
        )
        self._listing_note = ""
        if listing_folder and self.include_subfolders.isChecked():
            worker = _SubfolderListingWorker(self._listing_generation, self.folder, file_type)
            worker.signals.listed.connect(self._subfolder_listed)
            worker.signals.finished.connect(self._subfolder_listing_finished)
            self._listing_worker = worker
            self._listing_note = "listing subfolders…"
            self._listing_pool.start(worker)
        self._rebuild_file_list()

    def _stop_listing(self) -> None:
        # Results of an older listing are recognised by generation and dropped.
        self._listing_generation += 1
        if self._listing_worker is not None:
            self._listing_worker.cancelled = True
            self._listing_worker = None

    def wait_for_listing(self, msecs: int = 30000) -> bool:
        """Block until background listing ends (tests and scripted use)."""
        return self._listing_pool.waitForDone(msecs)

    def _subfolder_listed(self, generation: int, paths: list[Path]) -> None:
        if generation != self._listing_generation:
            return
        self._all_paths.extend(paths)
        self._rebuild_file_list()

    def _subfolder_listing_finished(self, generation: int, message: str) -> None:
        if generation != self._listing_generation:
            return
        self._listing_worker = None
        self._listing_note = message
        self._apply_filter()

    def _rebuild_file_list(self, *_args) -> None:
        """Show the listed files in the chosen order, keeping current file, selection, and scroll."""
        self.group_by_folder.setEnabled(
            self._fixed_paths is None and self.include_subfolders.isChecked()
        )
        grouped = self.include_subfolders.isChecked() and self.group_by_folder.isChecked()
        paths = sort_paths(self._all_paths, self.sort.currentIndex(), group_by_folder=grouped)
        current = self._current_path
        selected = set(self.selected_paths())
        scroll = self.file_list.verticalScrollBar().value()
        current_item = None
        # Rebuilding must not look like the user picking another file.
        self.file_list.blockSignals(True)
        try:
            self.file_list.clear()
            for path in paths:
                item = QListWidgetItem(display_name(path, self.folder))
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(str(path))
                self.file_list.addItem(item)
                if path in selected:
                    item.setSelected(True)
                if path == current:
                    current_item = item
            if current_item is not None:
                self.file_list.setCurrentItem(
                    current_item, QItemSelectionModel.SelectionFlag.NoUpdate
                )
        finally:
            self.file_list.blockSignals(False)
        self._apply_filter()
        self.file_list.verticalScrollBar().setValue(scroll)
        if current_item is None or current_item.isHidden():
            if current is not None or self.file_list.currentItem() is None:
                self._file_selected(None)

    # Kept for small integrations written before the widget existed.
    _refresh = refresh

    def _apply_filter(self) -> None:
        matches = make_file_matcher(self.filter.text())
        visible = 0
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            # The file name alone also counts, so "^S12" works with subfolders listed.
            name = Path(item.data(Qt.ItemDataRole.UserRole)).name
            hidden = not (matches(item.text()) or matches(name))
            item.setHidden(hidden)
            visible += not hidden
        text = f"Showing {visible} of {self.file_list.count()} files"
        self.count.setText(f"{text}; {self._listing_note}" if self._listing_note else text)

    def _select_all_visible(self) -> None:
        self.file_list.clearSelection()
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            item.setSelected(not item.isHidden())

    def selected_paths(self) -> list[Path]:
        return [Path(item.data(Qt.ItemDataRole.UserRole)) for item in self.file_list.selectedItems()]

    @staticmethod
    def _profile_key(locations: list[ScatteringLocation]) -> str:
        # NXcanSAS commonly stores curves as ``entry/<sample>/sasdata``. The
        # sample component changes from file to file, whereas the leaf group,
        # curve order, and variant identify the practical loading layout.
        shape = []
        for location in locations:
            parts = tuple(part for part in (location.internal_path or "").split("/") if part)
            shape.append((parts[-1] if parts else "", location.variant))
        return json.dumps(shape, separators=(",", ":"))

    def _locations_for(self, path: Path) -> list[ScatteringLocation]:
        if path not in self._locations and path not in self._errors:
            try:
                self._locations[path] = self._discover(path)
            except Exception as exc:
                self._errors[path] = str(exc)
        return self._locations.get(path, [])

    def _file_selected(self, current: QListWidgetItem | None, previous=None) -> None:
        self._current_path = None if current is None else Path(current.data(Qt.ItemDataRole.UserRole))
        self._populate_data_list()
        self._populate_results_list()

    def _populate_data_list(self) -> None:
        self._syncing = True
        self.data_list.clear()
        path = self._current_path
        if path is None:
            self.data_status.setText("Select a file to inspect its 1-D data.")
            self._syncing = False
            return
        locations = self._locations_for(path)
        if not locations:
            self.data_status.setText(self._errors.get(path, "No plottable 1-D data was found."))
            self._syncing = False
            return
        profile_key = self._profile_key(locations)
        profile = self._profiles.get(profile_key)
        checked = set(profile if profile is not None else ([0] if len(locations) == 1 else []))
        # A single discovered curve is presented as the sensible default.  That
        # default must also be persisted: itemChanged signals are intentionally
        # ignored while this list is being populated, so otherwise the checkbox
        # looks checked but selected_locations() sees an empty profile.
        if profile is None and len(locations) == 1:
            self._profiles[profile_key] = sorted(checked)
        for index, location in enumerate(locations):
            path_text = location.internal_path or "top-level data"
            unit_note = " — Q unit missing" if location.metadata.get("q_unit_missing") else ""
            item = QListWidgetItem(f"{location.display_name}  [{path_text}]{unit_note}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(f"{location.display_name}\nHDF5 path: {path_text}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if index in checked else Qt.CheckState.Unchecked)
            self.data_list.addItem(item)
        instruction = "Select one or more data sets to load."
        if profile is not None:
            instruction += " Reused from a previous file with this layout."
        elif len(locations) > 1:
            instruction += " No automatic choice is made for a multi-data file."
        self.data_status.setText(instruction)
        self._syncing = False

    def _results_for(self, path: Path) -> Mapping[str, tuple[str, tuple[str, ...]]]:
        """Saved pyIrena results in one file: {analysis: (title, kinds)}."""
        if self._discover_results is None or path.suffix.lower() not in (".h5", ".hdf5", ".hdf", ".nxs"):
            return {}
        if path not in self._results:
            try:
                self._results[path] = dict(self._discover_results(path))
            except Exception:
                self._results[path] = {}
        return self._results[path]

    def _populate_results_list(self) -> None:
        if self._discover_results is None:
            return
        self._syncing = True
        self.results_list.clear()
        path = self._current_path
        results = {} if path is None else self._results_for(path)
        for analysis, (title, kinds) in results.items():
            for kind in kinds:
                key = f"{analysis}/{kind}"
                item = QListWidgetItem(f"{title} · {kind_label(kind)}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                enabled = kind != IQ_KIND or self._iq_results_allowed
                if not enabled:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    item.setToolTip(
                        "Data + fit uses the General I(Q) view; select an I(Q) graph first."
                    )
                checked = enabled and key in self._checked_results
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                self.results_list.addItem(item)
        if path is None:
            self.results_status.setText("Select a file to see its saved results.")
        elif not results:
            self.results_status.setText("No saved pyIrena results in this file.")
        else:
            self.results_status.setText(
                "Data + fit joins the current graph; every other kind gets one graph "
                "for all selected files."
            )
        self._syncing = False

    def _result_selection_changed(self, item: QListWidgetItem) -> None:
        if self._syncing:
            return
        key = str(item.data(Qt.ItemDataRole.UserRole))
        if item.checkState() == Qt.CheckState.Checked:
            self._checked_results.add(key)
        else:
            self._checked_results.discard(key)

    def selected_results(self, paths: list[Path] | None = None) -> dict[str, tuple[str, ...]]:
        """Checked result kinds, by analysis, that some selected file (or *paths*) stores."""
        offered: set[str] = set()
        for path in self.selected_paths() if paths is None else paths:
            for analysis, (_, kinds) in self._results_for(path).items():
                offered.update(f"{analysis}/{kind}" for kind in kinds)
        selection: dict[str, list[str]] = {}
        for key in sorted(self._checked_results & offered):
            analysis, kind = key.split("/", 1)
            if kind == IQ_KIND and not self._iq_results_allowed:
                continue
            selection.setdefault(analysis, []).append(kind)
        return {analysis: tuple(kinds) for analysis, kinds in selection.items()}

    def _data_selection_changed(self, item: QListWidgetItem) -> None:
        if self._syncing or self._current_path is None:
            return
        locations = self._locations_for(self._current_path)
        if not locations:
            return
        selected = [
            int(self.data_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.data_list.count())
            if self.data_list.item(index).checkState() == Qt.CheckState.Checked
        ]
        self._profiles[self._profile_key(locations)] = selected

    def selected_locations(self, paths: list[Path] | None = None) -> list[ScatteringLocation]:
        """Checked I(Q) data of the selected files (or *paths*), by file layout."""
        selected: list[ScatteringLocation] = []
        for path in self.selected_paths() if paths is None else paths:
            locations = self._locations_for(path)
            profile = self._profiles.get(self._profile_key(locations))
            if profile is None:
                # A file never shown in the I(Q) list (e.g. picked with "Select
                # all visible") gets the same default it would show: its only curve.
                profile = [0] if len(locations) == 1 else []
            selected.extend(
                location for index, location in enumerate(locations) if index in profile
            )
        return selected

    def unresolved_paths(self, paths: list[Path] | None = None) -> list[Path]:
        unresolved = []
        for path in self.selected_paths() if paths is None else paths:
            locations = self._locations_for(path)
            if len(locations) > 1 and not self._profiles.get(self._profile_key(locations), []):
                unresolved.append(path)
        return unresolved

    def preferences(self) -> dict[str, object]:
        return {
            "file_type": self.file_type.currentData(),
            "sort_index": self.sort.currentIndex(),
            "include_subfolders": self.include_subfolders.isChecked(),
            "group_by_folder": self.group_by_folder.isChecked(),
            "filter": self.filter.text(),
            "q_unit": self.q_unit.currentText(),
            "error_percent": self.error_fraction.value(),
            "dataset_profiles": self._profiles,
            "result_kinds": sorted(self._checked_results),
        }

    def selection_problem(self, paths: list[Path] | None = None) -> tuple[str, str] | None:
        """Why the selected files (or *paths*) cannot be added, as (title, message), or None."""
        paths = self.selected_paths() if paths is None else list(paths)
        if not paths:
            return "Select data", "Select one or more files to load."
        if self.selected_results(paths):
            # Results alone are a complete request; a multi-curve file with no
            # I(Q) choice then simply contributes its results.
            return None
        unresolved = self.unresolved_paths(paths)
        if unresolved:
            return (
                "Choose 1-D data",
                "Select a representative file and check the data sets to load before continuing.\n\n"
                f"No selection has been made for: {unresolved[0].name}",
            )
        if not self.selected_locations(paths):
            return "Choose data", "Check I(Q) data or saved results to add, then press Add selected."
        return None


class DataFileSelectorDialog(QDialog):
    """Choose files, then the I(Q) data and saved pyIrena results to add.

    A modal wrapper around :class:`DataSelectorWidget`; one button adds
    everything that is checked.
    """

    def __init__(
        self,
        folder: Path,
        discover: Callable[[Path], list[ScatteringLocation]],
        preferences: Mapping[str, object] | None = None,
        paths: list[Path] | None = None,
        parent=None,
        *,
        discover_results: Callable[[Path], Mapping[str, tuple[str, tuple[str, ...]]]] | None = None,
        iq_results_allowed: bool = True,
    ) -> None:
        super().__init__(parent)
        self.folder = Path(folder)
        self.selector = DataSelectorWidget(
            folder,
            discover,
            preferences,
            paths,
            self,
            discover_results=discover_results,
            iq_results_allowed=iq_results_allowed,
        )
        self.selector.activated.connect(self._accept_selection)
        # The dialog's long-standing attribute names stay available.
        for name in (
            "file_type", "sort", "filter", "count", "file_list", "data_list", "data_status",
            "results_list", "results_status", "q_unit", "error_fraction",
        ):
            setattr(self, name, getattr(self.selector, name))
        # Kept as an alias for small integrations written during beta development.
        self.list = self.file_list
        self.setWindowTitle(f"Select data — {self.folder.name}")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, parent=self)
        self.add_button = buttons.addButton("Add selected", QDialogButtonBox.ButtonRole.AcceptRole)
        self.add_button.setDefault(True)
        self.add_button.setToolTip(
            "Add the checked I(Q) data and saved results of every selected file."
        )
        self.add_button.clicked.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f"Folder: {self.folder}\n"
                "Select files on the left, then check what to add on the right: I(Q) data, "
                "saved pyIrena results, or both. Choices are reused for every selected file."
            )
        )
        layout.addWidget(self.selector, 1)
        layout.addWidget(buttons)
        self.resize(1040, 580)

    def _refresh(self) -> None:
        self.selector.refresh()

    def _apply_filter(self) -> None:
        self.selector._apply_filter()

    def _select_all_visible(self) -> None:
        self.selector._select_all_visible()

    def selected_paths(self) -> list[Path]:
        return self.selector.selected_paths()

    def selected_results(self) -> dict[str, tuple[str, ...]]:
        return self.selector.selected_results()

    def selected_locations(self) -> list[ScatteringLocation]:
        return self.selector.selected_locations()

    def unresolved_paths(self) -> list[Path]:
        return self.selector.unresolved_paths()

    def preferences(self) -> dict[str, object]:
        return self.selector.preferences()

    def _accept_selection(self) -> None:
        problem = self.selector.selection_problem()
        if problem is not None:
            QMessageBox.information(self, *problem)
            return
        self.accept()


class LocationDialog(QDialog):
    def __init__(self, locations: list[ScatteringLocation], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select HDF5 datasets")
        self.list = QListWidget(self)
        for location in locations:
            item = QListWidgetItem(location.display_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, location)
            self.list.addItem(item)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose one or more datasets to add to the active graph:"))
        layout.addWidget(self.list)
        layout.addWidget(buttons)
        self.resize(650, 360)

    def selected(self) -> list[ScatteringLocation]:
        return [
            self.list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.list.count())
            if self.list.item(index).checkState() == Qt.CheckState.Checked
        ]


class ChecklistDialog(QDialog):
    """Pick any number of items from a checkable list."""

    def __init__(
        self,
        title: str,
        prompt: str,
        items: list[tuple[str, str]],
        *,
        checked: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.list = QListWidget(self)
        for item_id, label in items:
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, item_id)
            self.list.addItem(item)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(prompt))
        layout.addWidget(self.list)
        layout.addWidget(buttons)
        self.resize(520, 360)

    def selected_ids(self) -> list[str]:
        return [
            str(self.list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.list.count())
            if self.list.item(index).checkState() == Qt.CheckState.Checked
        ]


class GraphSelectionDialog(QDialog):
    def __init__(self, graphs: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import graphs")
        self.list = QListWidget(self)
        for graph_id, title in graphs:
            item = QListWidgetItem(title)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, graph_id)
            self.list.addItem(item)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose one or more graphs to import:"))
        layout.addWidget(self.list)
        layout.addWidget(buttons)
        self.resize(520, 320)

    def selected_ids(self) -> list[str]:
        return [
            str(self.list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.list.count())
            if self.list.item(index).checkState() == Qt.CheckState.Checked
        ]


class HDFMappingDialog(QDialog):
    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(f"Map HDF5 arrays — {path.name}")
        numeric: list[str] = []
        with h5py.File(path, "r") as handle:
            def visitor(name, obj):
                if isinstance(obj, h5py.Dataset) and obj.ndim == 1 and obj.dtype.kind in "iuf":
                    numeric.append("/" + name)
            handle.visititems(visitor)
        self.q = QComboBox(self)
        self.intensity = QComboBox(self)
        self.uncertainty = QComboBox(self)
        self.dq = QComboBox(self)
        for box in (self.q, self.intensity):
            box.addItems(numeric)
        for box in (self.uncertainty, self.dq):
            box.addItem("Not present")
            box.addItems(numeric)
        form = QFormLayout()
        form.addRow("Q:", self.q)
        form.addRow("Intensity:", self.intensity)
        form.addRow("Uncertainty:", self.uncertainty)
        form.addRow("dQ:", self.dq)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose one-dimensional numeric datasets:"))
        layout.addLayout(form)
        layout.addWidget(buttons)
        if len(numeric) < 2:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def location(self) -> ScatteringLocation:
        mapping = {"q": self.q.currentText(), "intensity": self.intensity.currentText()}
        if self.uncertainty.currentIndex() > 0:
            mapping["uncertainty"] = self.uncertainty.currentText()
        if self.dq.currentIndex() > 0:
            mapping["dq"] = self.dq.currentText()
        return ScatteringLocation(
            path=self.path,
            adapter_id="hdf5",
            internal_path="/",
            display_name=f"{self.path.name}: custom mapping",
            variant="custom",
            metadata={"mapping": mapping},
        )


class TransformParameterDialog(QDialog):
    def __init__(self, transform: PlotTransform, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(transform.name)
        self.inputs: dict[str, QDoubleSpinBox] = {}
        form = QFormLayout()
        for parameter in transform.parameters:
            spin = QDoubleSpinBox(self)
            spin.setDecimals(8)
            spin.setRange(parameter.minimum or -1e300, 1e300)
            spin.setValue(parameter.default or max(parameter.minimum or 0.0, 1.0))
            self.inputs[parameter.id] = spin
            form.addRow(parameter.label + ":", spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict[str, float]:
        return {name: spin.value() for name, spin in self.inputs.items()}


class SeriesTransformParameterDialog(QDialog):
    """Declarative per-series transform parameters in one compact table."""

    def __init__(
        self,
        transform: PlotTransform,
        rows: list[tuple[str, str, Mapping[str, float]]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{transform.name} parameters")
        self.inputs: dict[str, dict[str, QDoubleSpinBox]] = {}
        table = QTableWidget(len(rows), len(transform.parameters) + 1, self)
        table.setHorizontalHeaderLabels(
            ["Dataset", *(parameter.label for parameter in transform.parameters)]
        )
        for row_index, (series_id, label, initial) in enumerate(rows):
            table.setItem(row_index, 0, QTableWidgetItem(label))
            self.inputs[series_id] = {}
            for column, parameter in enumerate(transform.parameters, 1):
                spin = QDoubleSpinBox(table)
                spin.setDecimals(8)
                spin.setRange(parameter.minimum or -1e300, 1e300)
                value = initial.get(parameter.id, parameter.default)
                spin.setValue(value if value is not None else max(parameter.minimum or 0.0, 1.0))
                table.setCellWidget(row_index, column, spin)
                self.inputs[series_id][parameter.id] = spin
        table.resizeColumnsToContents()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Values found in PyIrena result metadata are used as initial values.")
        )
        layout.addWidget(table)
        layout.addWidget(buttons)
        self.resize(max(520, table.horizontalHeader().length() + 80), 140 + 42 * len(rows))

    def values(self) -> dict[str, dict[str, float]]:
        return {
            series_id: {name: spin.value() for name, spin in controls.items()}
            for series_id, controls in self.inputs.items()
        }


class AnnotationDialog(QDialog):
    previewRequested = Signal(object)

    def __init__(
        self,
        annotation: Annotation | None = None,
        *,
        default_position: tuple[float, float] | None = None,
        default_end: tuple[float, float] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.annotation = annotation
        self.setWindowTitle("Graph annotation")
        self.setSizeGripEnabled(True)
        self.kind = QComboBox(self)
        for value in AnnotationKind:
            # Store the plain string: that is what Qt keeps either way.
            self.kind.addItem(value.value.replace("_", " ").title(), value.value)
        position = annotation.position if annotation else (default_position or (1.0, 1.0))
        end = annotation.end if annotation and annotation.end else (default_end or (2.0, 2.0))
        self.text = QLineEdit(annotation.text if annotation else "", self)
        self.x = self._spin(position[0])
        self.y = self._spin(position[1])
        self.end_x = self._spin(end[0])
        self.end_y = self._spin(end[1])
        self._color = annotation.color if annotation else (20, 20, 20, 255)
        self.color = QPushButton("Choose…", self)
        self.color.clicked.connect(self._choose_color)
        self._update_color_button()
        self.line_width = self._spin(annotation.line_width if annotation else 1.5)
        self.line_width.setRange(0.1, 50)
        self.slope = self._spin(annotation.slope if annotation and annotation.slope is not None else 4.0)
        self.slope.setRange(-1000, 1000)
        self.slope.setDecimals(4)
        self.slope_label = QLabel("Power exponent P:", self)
        self.font_size = QSpinBox(self)
        self.font_size.setRange(6, 144)
        self.font_size.setValue(annotation.font_size if annotation else 11)
        self.font_size_label = QLabel("Font size:", self)
        self.z_order = QSpinBox(self)
        self.z_order.setRange(-10_000, 10_000)
        self.z_order.setValue(annotation.z_order if annotation else 10)
        if annotation:
            self.kind.setCurrentIndex(self.kind.findData(annotation.kind.value))
        form = QFormLayout()
        form.addRow("Type:", self.kind)
        form.addRow("Text:", self.text)
        form.addRow("X:", self.x)
        form.addRow("Y:", self.y)
        form.addRow("End X (arrow/box):", self.end_x)
        form.addRow("End Y (arrow/box):", self.end_y)
        form.addRow("Color:", self.color)
        form.addRow("Line width:", self.line_width)
        form.addRow(self.slope_label, self.slope)
        form.addRow(self.font_size_label, self.font_size)
        form.addRow("Z order:", self.z_order)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.update_button = buttons.addButton(
            "Update graph", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.update_button.clicked.connect(lambda: self.previewRequested.emit(self.value()))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form_widget = QWidget(self)
        form_widget.setLayout(form)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        scroll.setMaximumHeight(300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Coordinates are in the plotted data units; defaults are placed within the data."))
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)
        self.resize(460, 420)
        self.kind.currentIndexChanged.connect(self._update_kind_controls)
        self._update_kind_controls()

    def _update_kind_controls(self) -> None:
        power_law = self.kind.currentData() == AnnotationKind.POWER_LAW.value
        self.slope_label.setVisible(power_law)
        self.slope.setVisible(power_law)
        self.font_size_label.setText("Slope label font size:" if power_law else "Font size:")
        # Power-law labels are normally read from across a publication-sized
        # plot, so give new guides a more useful starting size. Editing an
        # existing annotation always preserves its chosen size.
        if power_law and self.annotation is None and self.font_size.value() == 11:
            self.font_size.setValue(14)

    def _spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setDecimals(8)
        spin.setRange(-1e300, 1e300)
        spin.setValue(value)
        return spin

    def value(self) -> Annotation:
        # currentData() returns the plain string Qt stored in the item data,
        # never the AnnotationKind member that was put in -- see the warning
        # above AnnotationKind in core/models.py.  Convert explicitly.
        kind = AnnotationKind(self.kind.currentData())
        end = (
            (self.end_x.value(), self.end_y.value())
            if kind in (AnnotationKind.ARROW, AnnotationKind.BOX)
            else None
        )
        options = {
            "kind": kind,
            "position": (self.x.value(), self.y.value()),
            "end": end,
            "text": self.text.text(),
            "color": self._color,
            "line_width": self.line_width.value(),
            "font_size": self.font_size.value(),
            "z_order": self.z_order.value(),
            "slope": self.slope.value() if kind is AnnotationKind.POWER_LAW else None,
        }
        if self.annotation is not None:
            options["id"] = self.annotation.id
        return Annotation(**options)

    def _choose_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(*self._color),
            self,
            "Annotation color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if selected.isValid():
            self._color = (
                selected.red(),
                selected.green(),
                selected.blue(),
                selected.alpha(),
            )
            self._update_color_button()

    def _update_color_button(self) -> None:
        self.color.setStyleSheet(
            f"background: rgba({self._color[0]}, {self._color[1]}, "
            f"{self._color[2]}, {self._color[3]})"
        )
