from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .actions import Action_Selection


# NOTE: We delibrately exclude a default __str__ method to force env creators to think about it
# 	(We may rethink this decision at some point)
@dataclass(slots=True)
class Observation(ABC):
    possible_actions: list[Action_Selection]

    @abstractmethod
    def __str__(self):
        pass
