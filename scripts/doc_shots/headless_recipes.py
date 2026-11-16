"""Shots for docs/guides/headless-recipes.md.

Dataset: ``testData/Al_Mg_Si__40C_0min_0498.h5`` (scratch copy named
``sample.h5``, as in the page's first example). The image is the PNG that the
example itself writes, scaled to half size for the page.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ._common import Context, shot
from ._package import flush_deletes


@shot("headless-recipes-01-porod")
def porod_png(ctx: Context):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from bernardyn import PlotRequest, Presentation, ScatteringInput, create_plot

    work = Path(ctx.dataset("Al_Mg_Si__40C_0min_0498.h5")).parent
    shutil.move(work / "Al_Mg_Si__40C_0min_0498.h5", work / "sample.h5")
    cwd = os.getcwd()
    os.chdir(work)
    try:
        # The page's first example, verbatim apart from the print() calls.
        create_plot(
            PlotRequest(
                recipe_id="porod",
                inputs=(ScatteringInput("sample.h5"),),
                presentation=Presentation(
                    title="Sample Porod", width_px=1600, height_px=1000, dpi=250
                ),
                package_path="sample-porod",
                image_path="sample-porod.png",
            )
        )
    finally:
        os.chdir(cwd)
        flush_deletes(ctx)
    image = QImage(str(work / "sample-porod.png"))
    return image.scaledToWidth(800, Qt.TransformationMode.SmoothTransformation)
