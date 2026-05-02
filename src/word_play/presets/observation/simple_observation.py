from __future__ import annotations

from dataclasses import dataclass
import pprint
from typing import Callable

from word_play.core import Action_Selection, Entity, Observation
from word_play.presets.observation.utils import (
    entity_state_to_str,
    format_nearby_entities,
    indent,
)

def format_action_list(possible_actions: list[Action_Selection]) -> str:
    if not possible_actions:
        return " None"
    return "".join(f"\n  [{i}] {sel}" for i, sel in enumerate(possible_actions))


def format_action_details(possible_actions: list[Action_Selection]) -> str:
    lines = ["ACTION DETAILS:"]
    for idx, sel in enumerate(possible_actions):
        lines.append(f"  [{idx}] {sel}")
        if sel.required_kwargs:
            lines.append("       kwargs required:")
            for name, arg in sel.required_kwargs.items():
                desc = arg.arg_description(sel.actor, sel.target_entity, sel.env)
                lines.append(f'         "{name}": {desc}')
    return "\n".join(lines)


# TODO: make this nice so that the printing of things like all component infos are printed nicely. Make it especially
#       nice for common component presets, e.g., inventory, health, etc.
# TODO: make it so that I can see some info about objs in inventory (not all since it would be too much)
@dataclass(slots=True)
class Simple_Observation(Observation):
    agent: Entity
    nearby_entities: list[Entity]
    last_reward: float
    info: dict
    observation_radius: int = 0
    extra_sections: tuple[str, ...] = ()
    nearby_entities_formatter: Callable[[list[Entity], Entity], str] | None = None

    def __str__(self) -> str:
        if "action_success" not in self.info:
            prev_block = ""
        else:
            status = "succeeded" if self.info["action_success"] else "FAILED"
            extra = ""
            if self.info.get("action_info"):
                extra = f"\n  Details: {pprint.pformat(self.info['action_info'])}"
            prev_block = f"LAST ACTION: {status}{extra}\n\n"

        agent_block = "YOUR STATE:\n" + indent(entity_state_to_str(self.agent))
        visible_square_block = (
            "VISIBLE AREA:\n"
            + f"  square radius: {self.observation_radius}\n"
            + f"  center: {self.agent.position}"
        )
        nearby_formatter = self.nearby_entities_formatter or format_nearby_entities
        nearby_block = nearby_formatter(self.nearby_entities, self.agent)
        actions_block = "AVAILABLE ACTIONS (reply with the index):" + format_action_list(self.possible_actions)

        return "\n\n".join(
            filter(
                None,
                [
                    prev_block + f"REWARD THIS TURN: {self.last_reward}",
                    *self.extra_sections,
                    agent_block,
                    visible_square_block,
                    nearby_block,
                    actions_block,
                ],
            )
        )
