"""Regression tests for the code review of November 9, 2026 (issue #1).

Each test names its finding (B01-B17, D1-D4; the review is summarized in
CHANGELOG.md and its open items are in docs/TODO.md)
and checks the invariant rather than the implementation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import replace
from pathlib import Path

import h5py
import numpy as np
import pytest

from bernardyn.core.controller import ApplicationController
from bernardyn.core.models import (
    Annotation,
    AnnotationKind,
    CurveRole,
    Dataset,
    GenericCurve,
    GraphDocument,
    SeriesView,
)
from bernardyn.core.transforms import builtin_transforms, resolve_series
from bernardyn.io.container import UTF8, PackageValidationError, load_package
from bernardyn.io.sources import ScatteringLocation, builtin_sources

Q = np.geomspace(0.005, 0.3, 50)
I = 100.0 * np.exp(-((Q * 30.0) ** 2) / 3.0) + 0.01


def _dataset(label: str = "sample") -> Dataset:
    return Dataset(q=Q, intensity=I, uncertainty=0.05 * I, label=label)


def _controller_with_data(transform: str | None = None, **parameters) -> ApplicationController:
    controller = ApplicationController()
    graph = controller.workspace.graphs[0]
    controller.add_dataset(_dataset(), graph_id=graph.id)
    if transform is not None:
        controller.set_transform(graph.id, transform, parameters or None)
    return controller


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rewrite_json(handle: h5py.File, name: str, change) -> None:
    raw = handle[name][()]
    document = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    change(document)
    del handle[name]
    handle.create_dataset(name, data=json.dumps(document), dtype=UTF8)


def _old_kratky_package(tmp_path) -> tuple[Path, str]:
    """A package whose Dimensionless Kratky snapshot was written by version 1.0."""
    controller = _controller_with_data("dimensionless_kratky", I0=100.0, Rg=30.0)
    graph = controller.workspace.graphs[0]
    controller.snapshots[graph.id] = {
        key: replace(value, transform_version="1.0")
        for key, value in controller.snapshots[graph.id].items()
    }
    return controller.save(tmp_path / "old.bernardyn.h5"), graph.id


# ------------------------------------------------------------ B01 newer schema


def test_b01_future_schema_package_is_never_overwritten_by_save(tmp_path):
    controller = _controller_with_data()
    path = controller.save(tmp_path / "future.bernardyn.h5")
    with h5py.File(path, "r+") as handle:
        handle.attrs["schema_version"] = 99
    before = _digest(path)
    reopened = ApplicationController()
    loaded = reopened.open_package(path)
    assert loaded.future_schema
    assert reopened.package_path is None
    reopened.new_graph()
    with pytest.raises(ValueError, match="destination path"):
        reopened.save()
    assert _digest(path) == before


def test_b01_gui_opens_future_schema_without_lock_and_save_asks_for_a_name(
    qapp, tmp_path, monkeypatch
):
    from bernardyn.gui import main_window
    from bernardyn.state import UserState

    controller = _controller_with_data()
    path = controller.save(tmp_path / "future.bernardyn.h5")
    with h5py.File(path, "r+") as handle:
        handle.attrs["schema_version"] = 99
    before = _digest(path)
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *args: None)
    asked = []
    monkeypatch.setattr(
        main_window.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: asked.append(args) or ("", ""),
    )
    window = main_window.MainWindow()
    window.user_state = UserState(tmp_path / "state.json")
    assert window.open_workspace(path)
    assert window.workspace_path is None
    assert window._workspace_lock is None
    window._new_graph("plot2d")
    assert not window._save()
    assert asked, "Save must ask for a new file name"
    assert _digest(path) == before
    window.controller.workspace.dirty = False
    window.close()


# ------------------------------------------------- B02 / D4 archived versions


def test_b02_version_note_is_derived_and_survives_import(tmp_path):
    path, graph_id = _old_kratky_package(tmp_path)
    reopened = ApplicationController()
    reopened.open_package(path)
    assert any("current version is 2.0" in note for note in reopened.graph_warnings(graph_id))

    importer = ApplicationController()
    graph_map = importer.import_from_package(path)
    imported = graph_map[graph_id]
    assert any("current version is 2.0" in note for note in importer.graph_warnings(imported))
    assert all(
        snapshot.transform_version == "1.0" for snapshot in importer.snapshots[imported].values()
    )


def test_d4_data_edits_refuse_to_recompute_archived_snapshots(tmp_path):
    path, graph_id = _old_kratky_package(tmp_path)
    controller = ApplicationController()
    controller.open_package(path)
    graph = controller.workspace.graph(graph_id)
    archived = dict(controller.snapshots[graph_id])
    extra = replace(_dataset("extra"), metadata={"I0": 100.0, "Rg": 30.0})

    with pytest.raises(ValueError, match="Recompute with current version"):
        controller.add_datasets((extra,), graph_id=graph_id)
    with pytest.raises(ValueError, match="Recompute with current version"):
        controller.replace_series_datasets(graph_id, (graph.series[0].id,), (extra,))
    edited = graph.replace_series(
        replace(view, multiplier=2.0) for view in graph.series
    )
    with pytest.raises(ValueError, match="Recompute with current version"):
        controller.update_graph(edited, recompute=True)
    assert controller.snapshots[graph_id] == archived

    # Changing the view is an explicit choice and replaces the snapshots.
    controller.set_transform(graph_id, "raw")
    assert all(s.transform_version == "1.0" for s in controller.snapshots[graph_id].values())
    assert not controller.stale_series(graph_id)


def test_d4_removing_series_keeps_the_others_archived_arrays(tmp_path):
    controller = _controller_with_data("dimensionless_kratky", I0=100.0, Rg=30.0)
    graph = controller.workspace.graphs[0]
    controller.add_datasets(
        (replace(_dataset("second"), metadata={"I0": 50.0, "Rg": 20.0}),), graph_id=graph.id
    )
    graph = controller.workspace.graph(graph.id)
    controller.snapshots[graph.id] = {
        key: replace(value, transform_version="1.0")
        for key, value in controller.snapshots[graph.id].items()
    }
    kept = graph.series[1].id
    archived = controller.snapshots[graph.id][kept]
    controller.remove_series(graph.id, graph.series[0].id)
    assert controller.snapshots[graph.id] == {kept: archived}

    controller.recompute_graph(graph.id)
    assert not controller.stale_series(graph.id)
    controller.add_datasets(
        (replace(_dataset("third"), metadata={"I0": 10.0, "Rg": 5.0}),), graph_id=graph.id
    )


# --------------------------------------------------------- D1 multiplier on I


def _guinier_slope(controller: ApplicationController, graph_id: str) -> float:
    snapshot = next(iter(controller.snapshots[graph_id].values()))
    low = snapshot.x < (1.0 / 30.0) ** 2
    return float(np.polyfit(snapshot.x[low], snapshot.y[low], 1)[0])


def test_d1_multiplier_scales_intensity_so_guinier_rg_is_unchanged():
    controller = _controller_with_data("guinier")
    graph = controller.workspace.graphs[0]
    slope = _guinier_slope(controller, graph.id)
    controller.update_graph(
        graph.replace_series(replace(view, multiplier=2.0) for view in graph.series),
        recompute=True,
    )
    assert _guinier_slope(controller, graph.id) == pytest.approx(slope, rel=1e-9)
    rg = math.sqrt(-3.0 * slope)
    assert rg == pytest.approx(30.0, rel=1e-3)
    snapshot = next(iter(controller.snapshots[graph.id].values()))
    unscaled = resolve_series(
        _dataset(), SeriesView(dataset_id=_dataset().id, transform_id="guinier"),
        builtin_transforms(discover_plugins=False),
    )
    np.testing.assert_allclose(snapshot.y, unscaled.y + math.log(2.0))
    np.testing.assert_allclose(snapshot.dy, unscaled.dy)


@pytest.mark.parametrize("transform", ["raw", "kratky", "porod", "dimensionless_kratky"])
def test_d1_views_linear_in_intensity_are_unchanged(transform):
    transforms = builtin_transforms(discover_plugins=False)
    dataset = _dataset()
    parameters = {"I0": 100.0, "Rg": 30.0} if transform == "dimensionless_kratky" else {}
    base = SeriesView(dataset_id=dataset.id, transform_id=transform, transform_parameters=parameters)
    plain = resolve_series(dataset, base, transforms)
    scaled = resolve_series(dataset, replace(base, multiplier=3.0, offset=1.5), transforms)
    np.testing.assert_allclose(scaled.y, plain.y * 3.0 + 1.5, rtol=1e-12)
    np.testing.assert_allclose(scaled.dy, plain.dy * 3.0, rtol=1e-12)


def test_d1_old_guinier_snapshot_is_current_only_with_unit_multiplier():
    controller = _controller_with_data("guinier")
    graph = controller.workspace.graphs[0]
    controller.snapshots[graph.id] = {
        key: replace(value, transform_version="1.0")
        for key, value in controller.snapshots[graph.id].items()
    }
    assert not controller.stale_series(graph.id)
    view = graph.series[0]
    controller.workspace.replace_graph(graph.replace_series([replace(view, multiplier=2.0)]))
    assert controller.stale_series(graph.id)


# ------------------------------------------------------------ B03 spin boxes


VALUES = (3.2e-10, -7e-10, 1.5e12)


@pytest.mark.parametrize("value", VALUES)
def test_b03_annotation_positions_keep_small_values(qapp, value):
    from bernardyn.gui.dialogs import AnnotationDialog

    dialog = AnnotationDialog(default_position=(value, value), default_end=(value, value))
    assert dialog.value().position == (value, value)


@pytest.mark.parametrize("value", VALUES)
def test_b03_multiplier_offset_and_view_parameters_keep_small_values(qapp, value):
    from bernardyn.gui.dialogs import SeriesTransformParameterDialog
    from bernardyn.gui.inspector import InspectorWidget

    transforms = builtin_transforms(discover_plugins=False)
    inspector = InspectorWidget(transforms)
    for spin in (inspector.multiplier, inspector.offset):
        spin.setValue(value)
        assert spin.value() == value
        spin.lineEdit().setText(repr(value))
        spin.interpretText()
        assert spin.value() == value
    positive = abs(value)
    dialog = SeriesTransformParameterDialog(
        transforms.get("dimensionless_kratky"), [("row", "sample", {"I0": positive, "Rg": positive})]
    )
    assert dialog.values()["row"] == {"I0": positive, "Rg": positive}


# --------------------------------------------------------------- B04 h5xp


def test_b04_h5xp_export_without_scattering_data_leaves_existing_file(tmp_path):
    pytest.importorskip("pyirena.io")
    from bernardyn.io.igor import export_datasets_to_h5xp

    controller = ApplicationController()
    controller.add_dataset(
        GenericCurve(x=[1.0, 2.0], y=[0.1, -0.1], role=CurveRole.RESIDUAL, x_semantic="q",
                     y_semantic="residual"),
    )
    target = tmp_path / "existing.h5xp"
    target.write_bytes(b"precious experiment")
    with pytest.raises(ValueError, match="scattering"):
        export_datasets_to_h5xp(target, controller.workspace)
    assert target.read_bytes() == b"precious experiment"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["existing.h5xp"]


# ------------------------------------------------------ B05 / B06 / D2 output


def _ink_columns(image) -> tuple[int, int]:
    columns = [
        x
        for x in range(0, image.width(), 2)
        if any(image.pixelColor(x, y).lightness() < 200 for y in range(0, image.height(), 4))
    ]
    return min(columns), max(columns)


def test_b05_headless_image_uses_the_whole_canvas(qapp, tmp_path):
    from PySide6.QtGui import QImage

    from bernardyn.api import render_2d_image

    controller = _controller_with_data("porod")
    graph = replace(controller.workspace.graphs[0], x_axis=replace(
        controller.workspace.graphs[0].x_axis, grid_major=False
    ), y_axis=replace(controller.workspace.graphs[0].y_axis, grid_major=False))
    snapshots = controller.snapshots[graph.id]
    path = render_2d_image(graph, snapshots, tmp_path / "porod.png")
    image = QImage(str(path))
    assert (image.width(), image.height()) == (graph.width_px, graph.height_px)
    _, right = _ink_columns(image)
    assert right >= 0.97 * image.width()


def test_b06_output_does_not_depend_on_window_size(qapp):
    from bernardyn.renderers.plot2d import Plot2DWidget

    controller = _controller_with_data()
    graph = controller.workspace.graphs[0]
    images = []
    for width, height in ((600, 420), (1500, 1050)):
        widget = Plot2DWidget()
        widget.resize(width, height)
        widget.show()
        widget.render(graph, controller.snapshots[graph.id])
        qapp.processEvents()
        images.append(widget.capture_output_image())
        widget.close()
    assert images[0].size() == images[1].size()
    assert images[0] == images[1]


def test_d2_font_points_are_physical_in_output(qapp):
    """A 14 pt title is 14/72 inch tall: about 58 px at 300 dpi, whatever the window."""
    from bernardyn.renderers.plot2d import Plot2DWidget

    controller = _controller_with_data()
    graph = controller.workspace.graphs[0]
    widget = Plot2DWidget()
    widget.resize(700, 500)
    widget.render(graph, controller.snapshots[graph.id])
    with widget._output_widget() as output:
        assert (output.width(), output.height()) == (468, 324)  # 6.5 x 4.5 in, in points
        title_html = output.getPlotItem().titleLabel.item.toHtml()
        assert f"font-size:{graph.typography.title_size}px" in title_html.replace(" ", "")
        tick_font = output.getPlotItem().getAxis("bottom").style["tickFont"]
        assert tick_font.pixelSize() == graph.typography.tick_size
    widget.close()


# ----------------------------------------------------------------- B07 arrows


def test_b07_arrow_head_follows_the_shaft_on_screen(qapp):
    from bernardyn.renderers.plot2d import Plot2DWidget

    controller = _controller_with_data()
    graph = controller.workspace.graphs[0]
    graph = replace(
        graph,
        annotations=(
            Annotation(AnnotationKind.ARROW, position=(0.01, 50.0), end=(0.1, 1.0)),
        ),
    )
    widget = Plot2DWidget()
    widget.resize(900, 400)
    widget.show()
    widget.render(graph, controller.snapshots[graph.id])
    widget.settle_layout()
    (arrow, start, end), = widget._arrow_heads
    view_box = widget.getPlotItem().getViewBox()
    first = view_box.mapViewToScene(pg_point(*start))
    second = view_box.mapViewToScene(pg_point(*end))
    shaft = math.degrees(math.atan2(-(second.y() - first.y()), second.x() - first.x()))
    assert arrow.opts["angle"] == pytest.approx(180 - shaft, abs=1.0)
    widget.close()


def pg_point(x, y):
    import pyqtgraph as pg

    return pg.Point(x, y)


# ------------------------------------------------------------- B08 generic HDF5


def test_b08_plain_group_with_q_and_intensity_loads(tmp_path):
    path = tmp_path / "generic.h5"
    with h5py.File(path, "w") as handle:
        group = handle.create_group("data")
        group["q"] = Q
        group["intensity"] = I
    sources = builtin_sources(discover_plugins=False) if _takes_plugins() else builtin_sources()
    (location,) = sources.discover_path(path)
    assert location.internal_path == "/data"
    record = sources.load_location(location)
    np.testing.assert_allclose(record.intensity, I)


def test_b08_unknown_layout_asks_for_a_mapping_and_custom_mapping_loads(tmp_path):
    path = tmp_path / "unknown.h5"
    with h5py.File(path, "w") as handle:
        group = handle.create_group("entry")
        group["xx"] = Q
        group["yy"] = I
    sources = builtin_sources()
    # The GUI opens "Map HDF5 arrays" when discovery fails.
    with pytest.raises(ValueError, match="no recognizable"):
        sources.discover_path(path)
    location = ScatteringLocation(
        path=path.resolve(),
        adapter_id="hdf5",
        internal_path="/entry",
        display_name="custom",
        variant="custom",
        metadata={"mapping": {"q": "xx", "intensity": "yy"}},
    )
    record = sources.load_location(location)
    np.testing.assert_allclose(record.q, Q)


def _takes_plugins() -> bool:
    import inspect

    return "discover_plugins" in inspect.signature(builtin_sources).parameters


# ------------------------------------------------------------ B09 residual axes


def test_b09_residual_added_to_untouched_graph_gets_linear_y():
    controller = ApplicationController()
    graph = controller.workspace.graphs[0]
    residual = GenericCurve(
        x=Q, y=np.sin(np.arange(len(Q))), role=CurveRole.RESIDUAL,
        x_semantic="q", y_semantic="normalized_residual", x_label="q", y_label="Residual",
    )
    controller.add_datasets((residual,), graph_id=graph.id)
    graph = controller.workspace.graph(graph.id)
    assert graph.x_axis.log and not graph.y_axis.log
    snapshot = next(iter(controller.snapshots[graph.id].values()))
    assert len(snapshot.y) == len(Q)


def test_b09_result_curves_carry_their_axis_hint():
    from bernardyn.core.controller import curve_axis_hint
    from bernardyn.core.models import SeriesStyle
    from bernardyn.io.results import ResultCurveBundle

    curve = GenericCurve(
        x=[1.0, 2.0], y=[1.0, 2.0], metadata={"bernardyn_result": {"role": "volume_distribution"}}
    )
    bundle = ResultCurveBundle(
        descriptor=None, curve=curve, style=SeriesStyle(), graph_title="t", x_log=True, y_log=False
    )
    assert curve_axis_hint(bundle.curve) == (True, False)


# ------------------------------------------------------------ B10 read-only


def test_b10_read_only_graph_refuses_added_and_transferred_data():
    controller = _controller_with_data()
    source = controller.workspace.graphs[0]
    target = controller.new_graph()
    controller.read_only_graphs.add(source.id)
    with pytest.raises(PermissionError):
        controller.add_datasets((_dataset("more"),), graph_id=source.id)
    with pytest.raises(PermissionError):
        controller.transfer_series(source.id, target.id, [source.series[0].id], move=True)
    controller.read_only_graphs = {target.id}
    with pytest.raises(PermissionError):
        controller.transfer_series(source.id, target.id, [source.series[0].id], move=False)


# ------------------------------------------------- B11 / D3 newer enum values


def test_d3_unknown_annotation_kind_is_kept_and_written_back(tmp_path):
    controller = _controller_with_data()
    graph = controller.workspace.graphs[0]
    path = controller.save(tmp_path / "newer.bernardyn.h5")
    newer = {"kind": "ellipse", "position": [0.01, 1.0], "id": graph.id, "rx": 2}
    with h5py.File(path, "r+") as handle:
        _rewrite_json(
            handle, f"graphs/{graph.id}/document",
            lambda document: document["annotations"].append(newer),
        )
    loaded = load_package(path)
    assert not loaded.warnings
    assert any("ellipse" in notice for notice in loaded.notices)
    reopened = ApplicationController()
    reopened.open_package(path)
    restored = reopened.workspace.graph(graph.id)
    assert restored.annotations == ()
    assert restored.preserved_annotations == (newer,)
    saved = reopened.save(tmp_path / "resaved.bernardyn.h5")
    assert newer in load_package(saved).workspace.graph(graph.id).to_dict()["annotations"]


def test_d3_unknown_curve_role_loads_as_plain_curve_and_is_kept(tmp_path):
    controller = ApplicationController()
    curve = GenericCurve(x=[1.0, 2.0], y=[3.0, 4.0], x_semantic="x", y_semantic="y")
    controller.add_dataset(curve)
    path = controller.save(tmp_path / "role.bernardyn.h5")
    with h5py.File(path, "r+") as handle:
        _rewrite_json(
            handle, f"datasets/{curve.id}/metadata",
            lambda document: document.update(role="parameter_table"),
        )
    reopened = ApplicationController()
    loaded = reopened.open_package(path)
    restored = reopened.workspace.datasets[curve.id]
    assert restored.role.value == "parameter_table"
    assert not restored.role.known
    assert restored.role is not CurveRole.RESIDUAL
    assert any("parameter_table" in notice for notice in loaded.notices)
    saved = reopened.save(tmp_path / "role-resaved.bernardyn.h5")
    assert load_package(saved).workspace.datasets[curve.id].role.value == "parameter_table"


def test_b11_invalid_dataset_values_are_validation_errors(tmp_path):
    controller = _controller_with_data()
    dataset_id = next(iter(controller.workspace.datasets))
    path = controller.save(tmp_path / "bad.bernardyn.h5")
    with h5py.File(path, "r+") as handle:
        _rewrite_json(
            handle, f"datasets/{dataset_id}/metadata",
            lambda document: document.update(kind="curve_3d"),
        )
    with pytest.raises(PackageValidationError, match="invalid dataset"):
        load_package(path)


# ------------------------------------------------------------- B12 import


def test_b12_import_reuses_loaded_package_shows_warnings_and_remaps_3d_positions(tmp_path):
    controller = ApplicationController()
    graph = controller.new_graph("opengl_waterfall")
    (view,) = controller.add_datasets((_dataset(),), graph_id=graph.id)
    graph = controller.workspace.graph(graph.id)
    controller.update_graph(
        replace(graph, renderer_config={**graph.renderer_config, "series_positions": {view.id: 2.5}})
    )
    path = controller.save(tmp_path / "waterfall.bernardyn.h5")
    loaded = load_package(path)
    loaded.warnings.append("canonical dataset checksum failed for sample")

    importer = ApplicationController()
    graph_map = importer.import_from_package(loaded, [graph.id])
    imported = importer.workspace.graph(graph_map[graph.id])
    (new_view,) = imported.series
    assert imported.renderer_config["series_positions"] == {new_view.id: 2.5}
    assert any("checksum failed" in note for note in importer.graph_warnings(imported.id))


# ---------------------------------------------------------------- B15 ranges


def test_b15_trimming_the_q_range_is_not_reported_as_invalid_data():
    transforms = builtin_transforms(discover_plugins=False)
    dataset = _dataset()
    view = SeriesView(dataset_id=dataset.id, q_range=(0.02, 0.1))
    result = resolve_series(dataset, view, transforms)
    assert 0 < len(result.x) < len(Q)
    assert not any("valid plot domain" in warning for warning in result.warnings)

    bad = Dataset(q=Q, intensity=np.where(np.arange(len(Q)) == 20, np.nan, I))
    result = resolve_series(bad, replace(view, dataset_id=bad.id), transforms)
    assert any("1 of" in warning for warning in result.warnings)

    curve = GenericCurve(x=Q, y=I, x_semantic="x", y_semantic="y")
    controller = ApplicationController()
    snapshot = controller._resolve_generic_curve(
        curve, SeriesView(dataset_id=curve.id, q_range=(0.02, 0.1)), x_log=True, y_log=True
    )
    assert not snapshot.warnings


# ------------------------------------------------------------- B16 save graph


def test_b16_save_graph_package_onto_open_workspace_is_refused(qapp, tmp_path, monkeypatch):
    from bernardyn.gui import main_window
    from bernardyn.state import UserState

    warnings = []
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *args: warnings.append(args))
    window = main_window.MainWindow()
    window.user_state = UserState(tmp_path / "state.json")
    window.controller.add_dataset(_dataset())
    window._new_graph("plot2d")
    path = tmp_path / "workspace.bernardyn.h5"
    assert window._save_to(path)
    before = _digest(path)
    graph_id = window.controller.workspace.graphs[0].id
    assert not window._save_to(path, graph_ids=[graph_id])
    assert warnings
    assert _digest(path) == before
    assert len(load_package(path).workspace.graphs) == 2
    window.controller.workspace.dirty = False
    window.close()


# ------------------------------------------------------------- B17 open


def test_b17_failed_open_leaves_the_current_workspace_intact(tmp_path, monkeypatch):
    other = _controller_with_data()
    path = other.save(tmp_path / "other.bernardyn.h5")
    controller = _controller_with_data()
    workspace = controller.workspace
    snapshots = controller.snapshots

    def fail(*args, **kwargs):
        raise RuntimeError("recompute failed")

    monkeypatch.setattr(controller, "_recover_snapshots", fail)
    with pytest.raises(RuntimeError):
        controller.open_package(path)
    assert controller.workspace is workspace
    assert controller.snapshots is snapshots
    assert controller.package_path is None


# ------------------------------------------------------------- B13 / B14


def test_b13_folder_listing_skips_folders_and_packages(tmp_path):
    from bernardyn.io.access import SOURCE_ACCESS_LOCK
    from bernardyn.io.file_browser import files_in_folder

    (tmp_path / "a.h5").write_bytes(b"")
    (tmp_path / "b.dat").write_text("1 2\n")
    (tmp_path / "graph.bernardyn.h5").write_bytes(b"")
    (tmp_path / "folder.h5").mkdir()
    assert sorted(path.name for path in files_in_folder(tmp_path)) == ["a.h5", "b.dat"]
    with SOURCE_ACCESS_LOCK, SOURCE_ACCESS_LOCK:  # re-entrant: nested readers never deadlock
        pass


def test_b14_log_file_and_excepthook_record_uncaught_errors(tmp_path, monkeypatch):
    import sys
    import threading

    from PySide6.QtWidgets import QMessageBox

    from bernardyn import app

    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: shown.append(args))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    root = logging.getLogger()
    handlers = list(root.handlers)
    try:
        path = app.configure_logging("INFO", tmp_path)
        app.install_exception_hooks(path)
        try:
            raise RuntimeError("lost error")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        for handler in root.handlers:
            handler.flush()
        assert "lost error" in path.read_text(encoding="utf-8")
        if app.QApplication.instance() is not None:
            assert shown and "lost error" in shown[0][2]
    finally:
        for handler in root.handlers:
            if handler not in handlers:
                root.removeHandler(handler)
                handler.close()


def test_graph_document_round_trip_without_preserved_annotations_is_unchanged():
    graph = GraphDocument()
    document = graph.to_dict()
    assert "preserved_annotations" not in document
    assert GraphDocument.from_dict(document) == graph


def test_d4_undoing_a_removal_restores_archived_snapshots(qapp, tmp_path, monkeypatch):
    from bernardyn.gui import main_window
    from bernardyn.state import UserState

    path, graph_id = _old_kratky_package(tmp_path)
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *args: None)
    window = main_window.MainWindow()
    window.user_state = UserState(tmp_path / "state.json")
    assert window.open_workspace(path)
    controller = window.controller
    graph = controller.workspace.graph(graph_id)
    archived = dict(controller.snapshots[graph_id])
    window.undo_stack.push(
        main_window.GraphEditCommand(window, graph, graph.replace_series(()), True, "Remove")
    )
    assert controller.snapshots[graph_id] == {}
    window.undo_stack.undo()
    assert controller.snapshots[graph_id] == archived
    assert controller.stale_series(graph_id)
    window.undo_stack.redo()
    assert controller.snapshots[graph_id] == {}
    window.controller.workspace.dirty = False
    window.close()


def test_d2_match_output_canvas_uses_the_screen_logical_dpi(qapp):
    from bernardyn.gui.graph_page import GraphPage

    controller = _controller_with_data()
    graph = controller.workspace.graphs[0]
    page = GraphPage(graph)
    page.render(graph, controller.snapshots[graph.id])
    dpi = page.renderer.logicalDpiX()
    width, height = page.output_matching_canvas_size()
    assert width == round(graph.width_in * dpi)
    assert height == round(width * graph.height_px / graph.width_px)
    page.close()
