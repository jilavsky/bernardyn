"""File browser dock: navigation, Add/Replace without dialogs, and series replacement."""

import json
from dataclasses import replace
from pathlib import Path
from shutil import copy2

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import Dataset, SeriesStyle
from bernardyn.gui import main_window
from bernardyn.gui.dialogs import FILE_BROWSER_MIME_TYPE
from bernardyn.gui.file_browser_panel import RECENT_FOLDER_LIMIT, FileBrowserPanel
from bernardyn.gui.main_window import MainWindow
from bernardyn.state import UserState

TEST_DATA = Path(__file__).parents[1] / "testData"


def _dataset(label: str, scale: float = 1.0) -> Dataset:
    return Dataset(q=[0.01, 0.02, 0.03], intensity=[3.0 * scale, 2.0 * scale, 1.0 * scale], label=label)


# ---------------------------------------------------------------- controller


def test_replace_series_datasets_keeps_presentation_and_order():
    controller = ApplicationController()
    first, second, third = _dataset("first"), _dataset("second"), _dataset("third")
    controller.add_datasets([first, second, third])
    graph = controller.workspace.graphs[0]
    middle = replace(
        graph.series[1],
        multiplier=10.0,
        offset=0.5,
        q_range=(0.015, None),
        visible=False,
        style=SeriesStyle(color=(1, 2, 3, 255), symbol="s"),
    )
    controller.update_graph(graph.replace_series([graph.series[0], middle, graph.series[2]]))
    new = _dataset("replacement", 4.0)

    views = controller.replace_series_datasets(graph.id, [middle.id], [new])

    series = controller.workspace.graphs[0].series
    assert [view.id for view in series] == [view.id for view in graph.series]
    replaced = series[1]
    assert views == (replaced,)
    assert replaced.dataset_id == new.id
    assert replaced.legend_label == "replacement"
    for kept in ("multiplier", "offset", "q_range", "visible", "style", "transform_id"):
        assert getattr(replaced, kept) == getattr(middle, kept)
    # The replaced data stay in the catalog until "Remove unused data".
    assert second.id in controller.workspace.datasets
    assert controller.unused_dataset_ids() == [second.id]
    assert replaced.id in controller.snapshots[graph.id]


def test_replace_series_datasets_is_all_or_nothing():
    controller = ApplicationController()
    controller.add_datasets([_dataset("a"), _dataset("b")])
    graph = controller.workspace.graphs[0]
    before = (controller.workspace.graphs[0], dict(controller.workspace.datasets))
    ids = [view.id for view in graph.series]
    with pytest.raises(ValueError, match="one data set per selected series"):
        controller.replace_series_datasets(graph.id, ids, [_dataset("only one")])
    with pytest.raises(ValueError, match="no longer in this graph"):
        controller.replace_series_datasets(graph.id, ["missing"], [_dataset("x")])
    with pytest.raises(ValueError, match="select one or more"):
        controller.validate_series_replacement(graph.id, [], [])
    assert (controller.workspace.graphs[0], dict(controller.workspace.datasets)) == before


# --------------------------------------------------------------------- panel


def _panel(tmp_path, state=None) -> FileBrowserPanel:
    return FileBrowserPanel(lambda path: [], {}, state or {}, discover_results=None)


def test_panel_navigates_with_history_favorites_and_recent(qapp, tmp_path):
    (tmp_path / "run1").mkdir()
    (tmp_path / "run2").mkdir()
    (tmp_path / "run2" / "S1_0001.h5").touch()
    panel = _panel(tmp_path)
    changes = []
    panel.stateChanged.connect(lambda: changes.append(True))

    assert panel.navigate(tmp_path / "run1")
    assert panel.navigate(tmp_path / "run2")
    assert [panel.selector.file_list.item(i).text() for i in range(panel.selector.file_list.count())] == [
        "S1_0001.h5"
    ]
    assert panel.path_edit.text() == str((tmp_path / "run2").resolve())
    panel.go_back()
    assert panel.folder == (tmp_path / "run1").resolve()
    panel.go_up()
    assert panel.folder == tmp_path.resolve()
    assert panel.recent[0] == str(tmp_path.resolve())
    assert panel.recent.count(str((tmp_path / "run1").resolve())) == 1

    panel._toggle_favorite()
    assert panel.favorites == [str(tmp_path.resolve())]
    assert panel.favorite_button.text() == "★"
    assert changes

    assert not panel.navigate(tmp_path / "does-not-exist")
    assert "Folder not found" in panel.message.text()
    assert panel.folder == tmp_path.resolve()


def test_panel_state_round_trips_and_falls_back_from_missing_folder(qapp, tmp_path):
    panel = _panel(tmp_path)
    panel.navigate(tmp_path)
    panel.selector.filter.setText("SAXS")
    panel._toggle_favorite()
    state = json.loads(json.dumps(panel.state()))

    again = _panel(tmp_path, state)
    again.start()
    assert again.folder == tmp_path.resolve()
    assert again.favorites == [str(tmp_path.resolve())]
    assert again.selector.filter.text() == "SAXS"

    stale = _panel(tmp_path, {**state, "folder": str(tmp_path / "unplugged drive")})
    stale.start(fallback=tmp_path)
    assert stale.folder == tmp_path.resolve()
    # A started panel stays where the user went.
    stale.navigate(Path.home())
    stale.start(fallback=tmp_path)
    assert stale.folder == Path.home().resolve()


def test_panel_keeps_recent_folders_bounded(qapp, tmp_path):
    panel = _panel(tmp_path)
    for index in range(RECENT_FOLDER_LIMIT + 3):
        folder = tmp_path / f"f{index}"
        folder.mkdir()
        panel.navigate(folder)
    assert len(panel.recent) == RECENT_FOLDER_LIMIT
    assert panel.recent[0] == str(folder.resolve())


def test_file_list_drag_carries_files_and_browser_marker(qapp, tmp_path):
    (tmp_path / "a.h5").touch()
    panel = _panel(tmp_path)
    panel.navigate(tmp_path)
    files = panel.selector.file_list
    data = files.mimeData([files.item(0)])
    assert [Path(url.toLocalFile()) for url in data.urls()] == [(tmp_path / "a.h5").resolve()]
    assert data.hasFormat(FILE_BROWSER_MIME_TYPE)


# -------------------------------------------------------------------- window


@pytest.fixture(autouse=True)
def no_modal_message_boxes(monkeypatch):
    """A message box would block the offscreen test run; fail instead."""

    def fail(*args, **kwargs):
        raise AssertionError(f"unexpected message box: {args[1:]}")

    for name in ("warning", "information", "question", "critical"):
        monkeypatch.setattr(main_window.QMessageBox, name, staticmethod(fail))


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    # Never read or write the developer's real ~/.bernardyn/state.json.
    monkeypatch.setattr(main_window, "UserState", lambda: UserState(tmp_path / "state.json"))
    window = MainWindow()
    qapp.processEvents()  # let the deferred File browser start run
    yield window
    window.controller.workspace.dirty = False
    window.close()


def _finish_loads(qapp, window) -> None:
    window.thread_pool.waitForDone(20000)
    for _ in range(10):
        qapp.processEvents()


def _select_file(panel, name: str) -> None:
    files = panel.selector.file_list
    files.setCurrentItem(files.findItems(name, Qt.MatchFlag.MatchExactly)[0])


def test_file_browser_is_a_dock_next_to_the_data_browser(window, qapp):
    window.show()
    qapp.processEvents()
    assert window.files_dock.objectName() == "fileBrowserDock"
    assert window.files_dock.widget() is window.files_panel
    assert window.dockWidgetArea(window.files_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.files_dock.geometry().right() < window.datasets_dock.geometry().left()
    assert window.open_file_browser_action.shortcut().toString() == "Ctrl+Shift+B"

    window.files_dock.close()
    window.open_file_browser_action.trigger()
    assert window.files_dock.isVisible()

    # Restoring a workspace layout keeps the docked panels side by side.
    window._restore_layout()
    qapp.processEvents()
    assert window.files_dock.geometry().right() < window.datasets_dock.geometry().left()


def test_file_browser_add_then_replace_is_one_undo_step(window, qapp, tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    copy2(TEST_DATA / "LnG_0103.hdf", folder / "a_first.hdf")
    copy2(TEST_DATA / "Rh1_0085.h5", folder / "b_second.h5")
    panel = window.files_panel
    assert panel.navigate(folder)

    _select_file(panel, "a_first.hdf")
    panel.request_add()
    _finish_loads(qapp, window)
    graph = window._current_graph()
    assert len(graph.series) == 1
    original = graph.series[0]
    # What just arrived is selected, ready for "next file, Replace".
    assert window._selected_series_ids() == (original.id,)
    styled = replace(original, multiplier=10.0, style=replace(original.style, color=(1, 2, 3, 255)))
    window.controller.update_graph(graph.replace_series([styled]))
    window._refresh_dataset_list()

    _select_file(panel, "b_second.h5")
    # Two curves in this file and no remembered choice yet: Replace says so.
    panel.request_replace()
    assert panel.message.text() == "Check the I(Q) data to use from b_second.h5."
    panel.selector.data_list.item(0).setCheckState(Qt.CheckState.Checked)
    panel.request_replace()
    _finish_loads(qapp, window)

    view = window._current_graph().series[0]
    assert len(window._current_graph().series) == 1
    assert view.id == original.id
    assert view.dataset_id != original.dataset_id
    assert view.multiplier == 10.0
    assert view.style.color == (1, 2, 3, 255)
    assert view.legend_label == window.controller.workspace.datasets[view.dataset_id].label
    assert window.undo_stack.undoText() == "Replace datasets"
    assert window._selected_series_ids() == (view.id,)

    window.undo_stack.undo()
    assert window._current_graph().series[0].dataset_id == original.dataset_id

    stored = json.loads((tmp_path / "state.json").read_text())
    assert stored["files_panel"]["folder"] == str(folder.resolve())
    assert stored["last_data_folder"] == str(folder.resolve())
    assert stored["data_selector"]["dataset_profiles"]


def test_replace_explains_what_is_missing(window, qapp, tmp_path):
    copy2(TEST_DATA / "LnG_0103.hdf", tmp_path / "a.hdf")
    panel = window.files_panel
    panel.navigate(tmp_path)
    _select_file(panel, "a.hdf")
    queued = []
    window._queue_locations = lambda *args, **kwargs: queued.append((args, kwargs))

    panel.request_replace()
    assert panel.message.text() == "Select the series to replace in the Data browser."

    window.controller.add_datasets([_dataset("one"), _dataset("two")])
    window._refresh_dataset_list()
    window._select_series([view.id for view in window._current_graph().series])
    panel.request_replace()
    assert "2 series are selected" in panel.message.text()
    assert not queued

    window._select_series([window._current_graph().series[1].id])
    panel.request_replace()
    (_, kwargs), = queued
    assert kwargs["replace_series_ids"] == (window._current_graph().series[1].id,)


def test_drop_on_a_graph_tab_targets_that_graph(window, qapp, tmp_path):
    window._new_graph("plot2d")
    first_graph_id = window.controller.workspace.graphs[0].id
    received = []
    window._add_from_files_panel = lambda paths, **kwargs: received.append(
        (paths, window._current_graph().id)
    )
    window._dropped_data_paths = lambda paths: received.append(("dialog", paths))
    bar = window.tabs.tabBar()
    position = QPointF(bar.tabRect(0).center())

    def drop(browser: bool) -> None:
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(str(tmp_path / "a.h5"))])
        if browser:
            data.setData(FILE_BROWSER_MIME_TYPE, b"1")
        event = QDropEvent(
            position, Qt.DropAction.CopyAction, data, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        assert window.eventFilter(bar, event)

    drop(browser=True)
    assert received == [([tmp_path / "a.h5"], first_graph_id)]
    drop(browser=False)
    assert received[-1] == ("dialog", [tmp_path / "a.h5"])


def test_data_plus_fit_follows_the_active_graph_view(window):
    selector = window.files_panel.selector
    window._sync_inspector()
    assert selector._iq_results_allowed
    window.controller.add_datasets([_dataset("sample")])
    graph_id = window._current_graph().id
    window.controller.set_transform(graph_id, "kratky")
    window._sync_inspector()
    assert not selector._iq_results_allowed


def test_dialog_choices_reach_the_file_browser(window):
    selector = window.files_panel.selector
    selector.adopt_shared_preferences(
        {"dataset_profiles": {"layout": [1]}, "result_kinds": ["unified_fit/residuals"], "q_unit": "1/nm"}
    )
    preferences = selector.preferences()
    assert preferences["dataset_profiles"] == {"layout": [1]}
    assert preferences["result_kinds"] == ["unified_fit/residuals"]
    assert selector.q_unit.currentText() == "1/nm"


# ------------------------------------------------------- first-level subfolders


def _sample_tree(root: Path) -> Path:
    sample = root / "Sample"
    for technique, number in (("usaxs", 1), ("saxs", 2), ("waxs", 3)):
        folder = sample / f"Sample_{technique}"
        folder.mkdir(parents=True)
        (folder / f"CC1_000{number}.h5").touch()
        (folder / f"CC2_001{number}.h5").touch()
    (sample / "Sample_saxs" / "deeper").mkdir()
    (sample / "Sample_saxs" / "deeper" / "CC1_0099.h5").touch()
    (sample / ".hidden").mkdir()
    (sample / ".hidden" / "CC1_0098.h5").touch()
    (sample / "notes_0000.h5").touch()
    return sample


def test_subfolder_helpers_list_one_level_and_group(tmp_path):
    from bernardyn.io.file_browser import child_folders, display_name, sort_paths

    sample = _sample_tree(tmp_path)
    assert [folder.name for folder in child_folders(sample)] == [
        "Sample_saxs", "Sample_usaxs", "Sample_waxs",
    ]
    assert display_name(sample / "Sample_saxs" / "CC1_0002.h5", sample) == "Sample_saxs/CC1_0002.h5"
    assert display_name(sample / "notes_0000.h5", sample) == "notes_0000.h5"
    paths = [
        sample / "Sample_waxs" / "CC1_0003.h5",
        sample / "Sample_usaxs" / "CC1_0001.h5",
        sample / "notes_0000.h5",
        sample / "Sample_usaxs" / "CC2_0011.h5",
    ]
    order_ascending = 6
    assert [p.name for p in sort_paths(paths, order_ascending)] == [
        "notes_0000.h5", "CC1_0001.h5", "CC1_0003.h5", "CC2_0011.h5",
    ]
    grouped = sort_paths(paths, order_ascending, group_by_folder=True)
    assert [display_name(p, sample) for p in grouped] == [
        "notes_0000.h5", "Sample_usaxs/CC1_0001.h5", "Sample_usaxs/CC2_0011.h5",
        "Sample_waxs/CC1_0003.h5",
    ]


def _listed(selector, qapp) -> list[str]:
    selector.wait_for_listing()
    for _ in range(10):
        qapp.processEvents()
    files = selector.file_list
    return [files.item(i).text() for i in range(files.count()) if not files.item(i).isHidden()]


def test_selector_lists_subfolders_in_the_background(qapp, tmp_path):
    sample = _sample_tree(tmp_path)
    panel = _panel(tmp_path)
    selector = panel.selector
    panel.navigate(sample)
    assert _listed(selector, qapp) == ["notes_0000.h5"]
    # The group option only means something with subfolders listed.
    assert not selector.group_by_folder.isEnabled()

    selector.include_subfolders.setChecked(True)
    names = _listed(selector, qapp)
    assert len(names) == 7
    assert "Sample_saxs/CC1_0002.h5" in names
    assert not any("deeper" in name or "CC1_0098" in name for name in names)
    assert selector.group_by_folder.isEnabled()

    selector.filter.setText("CC1")
    assert sorted(_listed(selector, qapp)) == [
        "Sample_saxs/CC1_0002.h5", "Sample_usaxs/CC1_0001.h5", "Sample_waxs/CC1_0003.h5",
    ]
    selector._select_all_visible()
    assert len(selector.selected_paths()) == 3
    # The subfolder text and the bare file name both match.
    selector.filter.setText("^CC1")
    assert len(_listed(selector, qapp)) == 3
    selector.filter.setText("waxs/CC")
    assert len(_listed(selector, qapp)) == 2

    selector.filter.clear()
    selector.group_by_folder.setChecked(True)
    assert _listed(selector, qapp) == [
        "notes_0000.h5",
        "Sample_saxs/CC1_0002.h5", "Sample_saxs/CC2_0012.h5",
        "Sample_usaxs/CC1_0001.h5", "Sample_usaxs/CC2_0011.h5",
        "Sample_waxs/CC1_0003.h5", "Sample_waxs/CC2_0013.h5",
    ]
    state = panel.state()
    assert state["include_subfolders"] and state["group_by_folder"]
    assert panel.settings_changed


def test_rebuilding_keeps_the_current_file_and_selection(qapp, tmp_path):
    sample = _sample_tree(tmp_path)
    panel = _panel(tmp_path)
    selector = panel.selector
    panel.navigate(sample)
    _listed(selector, qapp)
    files = selector.file_list
    files.setCurrentItem(files.item(0))
    assert selector._current_path == sample / "notes_0000.h5"
    selector.include_subfolders.setChecked(True)
    _listed(selector, qapp)
    assert selector._current_path == sample / "notes_0000.h5"
    assert files.currentItem().text() == "notes_0000.h5"
    assert selector.selected_paths() == [sample / "notes_0000.h5"]


def test_too_many_subfolders_are_not_listed(qapp, tmp_path):
    from bernardyn.io.file_browser import SUBFOLDER_LIMIT

    for index in range(SUBFOLDER_LIMIT + 1):
        (tmp_path / f"run{index:03d}").mkdir()
        (tmp_path / f"run{index:03d}" / "a.h5").touch()
    panel = _panel(tmp_path, {"include_subfolders": True})
    panel.navigate(tmp_path)
    assert _listed(panel.selector, qapp) == []
    assert f"more than {SUBFOLDER_LIMIT}" in panel.selector.count.text()


def test_a_newer_listing_wins_over_a_stale_one(qapp, tmp_path):
    first = _sample_tree(tmp_path / "one")
    other = tmp_path / "two"
    (other / "sub").mkdir(parents=True)
    (other / "sub" / "X_0001.h5").touch()
    panel = _panel(tmp_path, {"include_subfolders": True})
    panel.navigate(first)
    panel.navigate(other)  # before the first listing's results are delivered
    assert _listed(panel.selector, qapp) == ["sub/X_0001.h5"]


def test_add_the_same_sample_from_every_technique_at_once(window, qapp, tmp_path):
    sample = tmp_path / "Sample"
    for technique in ("saxs", "waxs"):
        (sample / f"Sample_{technique}").mkdir(parents=True)
        copy2(TEST_DATA / "LnG_0103.hdf", sample / f"Sample_{technique}" / "CC1_0001.hdf")
        copy2(TEST_DATA / "LnG_0103.hdf", sample / f"Sample_{technique}" / "CC2_0002.hdf")
    panel = window.files_panel
    selector = panel.selector
    selector.include_subfolders.setChecked(True)
    panel.navigate(sample)
    selector.filter.setText("CC1")
    assert len(_listed(selector, qapp)) == 2
    selector._select_all_visible()
    panel.request_add()
    _finish_loads(qapp, window)
    assert len(window._current_graph().series) == 2
    assert window.undo_stack.count() == 1
