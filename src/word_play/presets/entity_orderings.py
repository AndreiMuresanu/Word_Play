from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from word_play.core import Entity, Environment


def entity_definition_order(entities: list[Entity], env: Environment) -> list[int]:
    return list(range(len(entities)))


def random_order(entities: list[Entity], env: Environment) -> list[int]:
    new_order = list(range(len(entities)))
    random.shuffle(new_order)
    return new_order


def randomize_agent_order(entities: list[Entity], env: Environment) -> list[int]:
    new_order = list(range(len(entities)))
    agent_indices = [entity_idx for entity_idx, entity in enumerate(entities) if entity.is_agent]
    shuffled_agent_indices = agent_indices.copy()
    random.shuffle(shuffled_agent_indices)

    for target_idx, source_idx in zip(agent_indices, shuffled_agent_indices):
        new_order[target_idx] = source_idx

    return new_order
