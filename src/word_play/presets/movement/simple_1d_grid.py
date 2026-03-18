from __future__ import annotations

from dataclasses import dataclass

from word_play.core import Movement_System, Position
from word_play.presets.movement.common import positions_are_close_if_equal
from word_play.presets.movement.simple_2d_grid import (
    Move_Left,
    Move_Right,
)


@dataclass(slots=True)
class Position_1D(Position):
    x: int

    def __str__(self) -> str:
        return f"{self.x}"


INFINITE_1D_MOVEMENT_SYSTEM = Movement_System(
    position_type=Position_1D,
    movement_options=[Move_Left(), Move_Right()],
    positions_are_close=positions_are_close_if_equal,
)
