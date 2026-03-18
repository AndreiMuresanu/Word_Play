from __future__ import annotations

from dataclasses import dataclass

from word_play.core import Movement_System, Position
from word_play.presets.movement.common import positions_are_close_if_equal


@dataclass(slots=True)
class Single_Point_Position(Position):
    CONSTANT_POSITION = 0

    def __str__(self) -> str:
        return f"{self.CONSTANT_POSITION}"


SINGLE_POINT_MOVEMENT_SYSTEM = Movement_System(
    position_type=Single_Point_Position,
    movement_options=[],
    positions_are_close=positions_are_close_if_equal,
)
