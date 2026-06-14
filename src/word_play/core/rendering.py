from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING, TypeVar, cast

if TYPE_CHECKING:
    from .environment import Environment


T = TypeVar("T")


@dataclass(slots=True)
class Render_Event:
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Renderer_State:
    frame: dict[str, Any] = field(default_factory=dict)
    events: list[Render_Event] = field(default_factory=list)

    def emit(self, kind: str, /, **payload: Any) -> None:
        self.events.append(Render_Event(kind=kind, payload=dict(payload)))

    def clear_events(self) -> None:
        self.events.clear()


@dataclass(slots=True)
class Render_Scene:
    metadata: dict[str, Any] = field(default_factory=dict)
    layers: dict[str, list[Any]] = field(default_factory=dict)


@dataclass(slots=True)
class Render_Context:
    private: dict[object, Any] = field(default_factory=dict)

    def value_for(self, owner: object, factory: Callable[[], T]) -> T:
        value = self.private.get(owner)
        if value is None:
            value = factory()
            self.private[owner] = value
        return cast(T, value)


@dataclass(slots=True)
class Render_Result:
    quit_requested: bool = False
    reset_requested: bool = False

    def __bool__(self) -> bool:
        return not self.quit_requested


class Renderer(ABC):
    def create_renderer_state(self) -> Renderer_State:
        return Renderer_State()

    def create_render_context(self) -> Render_Context:
        return Render_Context()

    @abstractmethod
    def render(self, env: "Environment") -> Render_Result:
        """Render one environment frame and report any user requests."""


class Render_Extractor(ABC):
    @abstractmethod
    def extract(
        self,
        env: "Environment",
        render_state: Renderer_State,
        scene: Render_Scene,
        context: Render_Context,
    ) -> None:
        """Contribute renderer-neutral scene data from the environment state."""
