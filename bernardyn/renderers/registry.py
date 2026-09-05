"""Renderer protocol and extension-point registry.

Renderer modules stay lazy: importing this registry never initializes OpenGL.
Third-party packages can publish registrations through ``bernardyn.renderers``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol

from PySide6.QtWidgets import QWidget

from bernardyn.core.models import GraphDocument, PlotSeries
from bernardyn.core.registry import Registry


class RendererWidget(Protocol):
    def apply_graph(self, graph: GraphDocument, snapshots: Mapping[str, PlotSeries]) -> None: ...

    def capture_snapshot(self, width: int = 1200) -> bytes: ...

    def save_image(self, path: str | Path, width: int | None = None) -> Path: ...


@dataclass(frozen=True)
class RendererRegistration:
    id: str
    name: str
    version: str
    factory: Callable[[QWidget | None], QWidget]

    def create(self, parent: QWidget | None = None) -> QWidget:
        return self.factory(parent)


class RendererRegistry(Registry[RendererRegistration]):
    def __init__(self) -> None:
        super().__init__("bernardyn.renderers")


def builtin_renderers(*, discover_plugins: bool = True) -> RendererRegistry:
    from bernardyn.renderers.opengl import OpenGLPlotWidget
    from bernardyn.renderers.plot2d import Plot2DWidget

    registry = RendererRegistry()
    registry.register(RendererRegistration("plot2d", "2D plot", "1.0", Plot2DWidget))
    registry.register(
        RendererRegistration("opengl_waterfall", "3D waterfall", "1.0", OpenGLPlotWidget)
    )
    registry.register(
        RendererRegistration("opengl_surface", "3D surface", "1.0", OpenGLPlotWidget)
    )
    if discover_plugins:
        registry.discover()
    return registry

