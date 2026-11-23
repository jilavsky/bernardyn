"""Qt/PyQtGraph renderers for Bernardyn graph documents."""

# First: the Qt shim pins PyQtGraph to PySide6 before any renderer imports it.
import bernardyn.gui._qt  # noqa: F401
from bernardyn.renderers.opengl import OpenGLPlotWidget, opengl_available
from bernardyn.renderers.plot2d import Plot2DWidget
from bernardyn.renderers.registry import (
    RendererRegistration,
    RendererRegistry,
    RendererWidget,
    builtin_renderers,
)

__all__ = [
    "OpenGLPlotWidget",
    "Plot2DWidget",
    "RendererRegistration",
    "RendererRegistry",
    "RendererWidget",
    "builtin_renderers",
    "opengl_available",
]
