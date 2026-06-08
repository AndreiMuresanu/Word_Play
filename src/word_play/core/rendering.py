from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .environment import Environment


@dataclass(slots=True)
class Renderer_State:
    values: dict[str, Any] = field(default_factory=dict)
    lists: dict[str, list[Any]] = field(default_factory=dict)
    private: dict[str, Any] = field(default_factory=dict)

    def set_value(self, key: str, value: Any) -> None:
        self.values[key] = value

    def get_value(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def set_list(self, key: str, items: Iterable[Any]) -> None:
        self.lists[key] = list(items)

    def get_list(self, key: str) -> list[Any]:
        return list(self.lists.get(key, []))

    def append_to_list(self, key: str, item: Any) -> None:
        self.lists.setdefault(key, []).append(item)

    def extend_list(self, key: str, items: Iterable[Any]) -> None:
        self.lists.setdefault(key, []).extend(items)

    def clear_list(self, key: str) -> None:
        self.lists.pop(key, None)


@dataclass(slots=True)
class Render_Result:
    quit_requested: bool = False
    reset_requested: bool = False

    def __bool__(self) -> bool:
        return not self.quit_requested


class Renderer(ABC):
    def create_renderer_state(self) -> Renderer_State:
        return Renderer_State()

    @abstractmethod
    def render(self, env: "Environment") -> Render_Result:
        """Render one environment frame and report any user requests."""
