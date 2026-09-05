"""Small typed registries with optional Python entry-point discovery."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Generic, Iterable, Protocol, TypeVar


class Identified(Protocol):
    id: str


T = TypeVar("T", bound=Identified)
log = logging.getLogger(__name__)


class Registry(Generic[T]):
    def __init__(self, entry_point_group: str) -> None:
        self.entry_point_group = entry_point_group
        self._items: dict[str, T] = {}

    def register(self, item: T, *, replace: bool = False) -> None:
        if item.id in self._items and not replace:
            raise ValueError(f"{item.id!r} is already registered")
        self._items[item.id] = item

    def get(self, item_id: str) -> T:
        try:
            return self._items[item_id]
        except KeyError as exc:
            raise KeyError(f"unknown {self.entry_point_group} id {item_id!r}") from exc

    def values(self) -> tuple[T, ...]:
        return tuple(self._items.values())

    def discover(self, *, strict: bool = False) -> list[str]:
        loaded: list[str] = []
        for point in entry_points().select(group=self.entry_point_group):
            try:
                item = point.load()
                if isinstance(item, type):
                    item = item()
                self.register(item)
                loaded.append(point.name)
            except Exception:
                if strict:
                    raise
                log.exception(
                    "could not load %s extension %s",
                    self.entry_point_group,
                    point.name,
                )
        return loaded

    def __iter__(self) -> Iterable[T]:
        return iter(self._items.values())
