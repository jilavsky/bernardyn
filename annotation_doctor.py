"""Diagnose why graph annotations may not appear.

Run inside the Bernardyn environment, from the repository root:

    conda activate bernardyn
    python annotation_doctor.py

It prints the loaded module paths and library versions, then drives the exact
inspector -> controller -> renderer path used by the Add button and reports
what actually reached the plot scene.  A PNG is written next to this file.
"""

from __future__ import annotations

import os
import sys
import traceback
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", ""))

import numpy as np
import pyqtgraph as pg
import PySide6


def main() -> int:
    print("== environment ==")
    print("python      :", sys.version.split()[0], sys.executable)
    print("PySide6     :", PySide6.__version__)
    print("pyqtgraph   :", pg.__version__, pg.__file__)
    try:
        import pyirena

        print("pyirena     :", getattr(pyirena, "__version__", "?"), pyirena.__file__)
    except Exception as exc:  # pragma: no cover - diagnostic only
        print("pyirena     : not importable:", exc)

    import bernardyn
    import bernardyn.renderers.plot2d as plot2d

    print("bernardyn   :", getattr(bernardyn, "__version__", "?"), bernardyn.__file__)
    print("plot2d      :", plot2d.__file__)
    import inspect
    source = "".join(
        inspect.getsource(getattr(plot2d.Plot2DWidget, name))
        for name in ("_add_annotations", "_add_annotation")
        if hasattr(plot2d.Plot2DWidget, name)
    )
    has_overlay = "add_overlay" in source
    print("plot2d has the overlay fix:", has_overlay)
    if not has_overlay:
        print("  !! The running plot2d.py is OLDER than commit 7119fc8.")
        print("  !! You are importing a stale copy, not this repository.")

    from PySide6.QtWidgets import QApplication

    from bernardyn.core.models import Annotation, AnnotationKind, Dataset
    from bernardyn.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1400, 900)
    window.show()

    q = np.logspace(-3, 0, 300)
    intensity = 1e4 * q**-3 + 1.0
    window.controller.add_dataset(Dataset(q=q, intensity=intensity))
    window._rebuild_tabs()
    app.processEvents()

    inspector = window.inspector
    graph = inspector._graph
    print()
    print("== graph state ==")
    print("renderer_id :", graph.renderer_id)
    print("x axis      : log=%s auto=%s min=%s max=%s"
          % (graph.x_axis.log, graph.x_axis.auto_range, graph.x_axis.minimum, graph.x_axis.maximum))
    print("y axis      : log=%s auto=%s min=%s max=%s"
          % (graph.y_axis.log, graph.y_axis.auto_range, graph.y_axis.minimum, graph.y_axis.maximum))
    print("inspector snapshots:", list(inspector._snapshots))

    position, end = inspector._annotation_defaults()
    print("default annotation position:", position, "end:", end)

    for kind in AnnotationKind:
        annotation = Annotation(
            kind,
            position,
            end=end if kind is AnnotationKind.ARROW else None,
            text="DIAGNOSTIC",
            font_size=18,
            color=(255, 0, 0, 255),
            line_width=3.0,
        )
        updated = replace(inspector._graph, annotations=(*inspector._graph.annotations, annotation))
        inspector._graph = updated
        try:
            inspector.graphChanged.emit(updated, False, "Add annotation")
        except Exception:
            traceback.print_exc()
        app.processEvents()

    page = window.tabs.currentWidget()
    renderer = page.renderer
    print()
    print("== what reached the renderer ==")
    print("renderer class    :", type(renderer).__name__)
    print("annotations in doc:", len(getattr(renderer, "_graph").annotations))
    if not hasattr(renderer, "getPlotItem"):
        print("!! This renderer draws no annotations at all (3D/OpenGL renderer).")
        return 1
    plot_item = renderer.getPlotItem()
    print("scene items       :", [type(item).__name__ for item in plot_item.items])
    print("view range (plot units):", plot_item.vb.viewRange())
    for item in plot_item.items:
        if isinstance(item, pg.TextItem):
            print("text item pos=%s z=%s visible=%s parent=%s"
                  % (item.pos(), item.zValue(), item.isVisible(), item.parentItem()))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "annotation_doctor.png")
    renderer.grab().save(out)
    print()
    print("wrote", out)
    print("If the four red annotations are in that PNG, rendering works and the")
    print("problem is in how the annotation reaches the document, not the plot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
