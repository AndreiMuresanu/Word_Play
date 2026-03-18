from __future__ import annotations

from dataclasses import dataclass
import pprint

from word_play.core import Entity, Observation
from word_play.presets.observation.utils import (
    format_possible_actions,
    entity_state_to_str,
    format_nearby_entities,
    indent,
)


# TODO: make this nice so that the printing of things like all component infos are printed nicely. Make it especially
#       nice for common component presets, e.g., inventory, health, etc.
# TODO: make it so that I can see some info about objs in inventory (not all since it would be too much)
@dataclass(slots=True)
class Simple_Observation(Observation):
    agent: Entity
    nearby_entities: list[Entity]
    last_reward: float
    info: dict

    def __str__(self):
        if "action_success" not in self.info:
            previous_action_info = ""
        else:
            if self.info["action_info"]:
                extra_action_info_text = (
                    f"\nSome additional information about your action: {pprint.pformat(self.info['action_info'])}"
                )
            else:
                extra_action_info_text = ""
            previous_action_info = (
                f"Your last action {'was successful.' if self.info['action_success'] else 'unsuccessful.'}"
                f"{extra_action_info_text}\n\n"
            )

        return f"""{previous_action_info}Your reward last turn was {self.last_reward}.

Your Info:
{indent("State: " + indent(entity_state_to_str(self.agent)))}

{format_nearby_entities(self.nearby_entities, self.agent)}

Possible Action:{format_possible_actions(self.possible_actions)}
"""
