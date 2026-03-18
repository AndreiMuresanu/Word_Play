from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable


# TODO: do we need to add an abstract __eq__ method? tbd as needs arise
@dataclass(slots=True)
class Position(ABC):
    # We keep Position as an ABC with no assumption because environments may have non-coordinate based positions.
    # For example, consider the enum based location-wise (ie., graph-based) positions: 'market', 'office', 'home', etc.
    # additionally, position comparison functions (ex., '>') may be useful
    @abstractmethod
    def __str__(self):
        pass


# TODO: maybe this can be made simpler and more effecient (we can likely sacrifice some generality)
@dataclass(slots=True)
class Movement_System:
    position_type: Position
    # TODO: ANDREI: currently movement_options is unused. I like the idea of clearly defining what the movement actions
    #       are since this can reduce confusion about which movement actions related to which position type. But this is
    #       likely not the best approach
    movement_options: list
    positions_are_close: Callable[[Position, Position], bool]
