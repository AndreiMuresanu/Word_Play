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
    # This is not the current ordering of agents since the order of the self.agents list does not change. But shuffling
    # self.agents' order or the current agent order are both equivalent.
    new_agent_order = list(range(len(env.agents)))
    random.shuffle(new_agent_order)

    new_agent_order_iter = iter(new_agent_order)
    return [next(new_agent_order_iter) if entity.is_agent else entity_idx for entity_idx, entity in enumerate(entities)]
