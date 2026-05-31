from __future__ import annotations

import pprint

from word_play.core import Agent_Policy, Entity, Action_Selection, Non_Agent_Policy
from word_play.presets.systems.communication.core import Communication_Policy


def format_possible_actions(possible_actions: list[Action_Selection]) -> str:
    obs_str = ""
    if possible_actions:
        for idx, action_selection in enumerate(possible_actions):
            obs_str += f"\n[{idx}]: {action_selection}"
    else:
        obs_str += "\nNo possible actions"
    return obs_str


def component_data_attributes(comp):
    return {
        name: value
        for name, value in comp.__dict__.items()
        if not name.startswith("__") and not callable(value) and name != "entity"
    }


def entity_state_to_str_with_complete_info(entity: Entity) -> str:
    return pprint.pformat(
        {
            "name": entity.name,
            "position": entity.position,
            "tags": entity.tags,
            "components": [
                {"component type": ctype.__name__} | component_data_attributes(comp)
                for ctype, comp in entity.components.items()
                if component_data_attributes(comp)
            ],
        },
        sort_dicts=False,
    )


def entity_state_to_str(entity: Entity) -> str:
    lines = [
        f"name: {entity.name}",
        f"position: {entity.position}",
    ]

    if entity.tags:
        lines.append(f"tags: {entity.tags}")

    for ctype, comp in entity.components.items():
        component_name = ctype.__name__
        component_data = component_data_attributes(comp)
        if not component_data:
            continue

        if (
            issubclass(ctype, Agent_Policy)
            or issubclass(ctype, Non_Agent_Policy)
            or issubclass(ctype, Communication_Policy)
        ):
            continue

        if component_name == "Health":
            lines.append(f"health: {comp.health}/{comp.max_health}")
        elif component_name == "Inventory":
            lines.append(f"inventory_size: {comp.inventory_size}")
            lines.append(f"inventory: {[item.name for item in comp.inventory]}")
        elif component_name == "Collidable":
            lines.append(f"collides_with_tags: {comp.collidable_tags}")
        elif component_name == "Key":
            lines.append(f"key_name: {comp.key_name}")
        elif component_name == "Door":
            door_state = "locked" if comp.locked else "unlocked"
            lines.append(f"door: {door_state}")
            lines.append(f"door_key_name: {comp.key_name}")
        else:
            lines.append(f"{component_name}: {pprint.pformat(component_data, sort_dicts=False)}")

    return "\n".join(lines)


def indent(text: str, prefix: str = "\t") -> str:
    lines = text.splitlines(keepends=True)
    return "".join(prefix + line for line in lines)


def format_nearby_entities(nearby_entities: list[Entity], agent: Entity) -> str:
    strs = [
        f"- {entity_state_to_str(entity).replace(chr(10), chr(10) + '  ')}"
        for entity in nearby_entities
        if entity is not agent
    ]
    if not strs:
        return "Nearby Entities: None"
    return "Nearby Entities:\n" + "\n".join(strs)
