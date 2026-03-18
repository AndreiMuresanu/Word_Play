from __future__ import annotations

import pprint

from word_play.core import Entity, Action_Selection


def format_possible_actions(possible_actions: list[Action_Selection]) -> str:
    obs_str = ""
    if possible_actions:
        for idx, action_selection in enumerate(possible_actions):
            obs_str += f"\n[{idx}]: {action_selection}"
    else:
        obs_str += "\nNo possible actions"
    return obs_str


def component_data_attributes(cls):
    return {
        name: value
        for name, value in cls.__dict__.items()
        if not name.startswith("__") and not callable(value) and name != "entity"
    }


def entity_state_to_str(entity: Entity) -> str:
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


def indent(text: str, prefix: str = "\t") -> str:
    lines = text.splitlines(keepends=True)
    return "".join(prefix + line for line in lines)


def format_nearby_entities(nearby_entities: list[Entity], agent: Entity) -> str:
    # TODO: maybe make this "indent(State: indent(...))" stuff a function
    nearby_entities_strs = [
        indent(f"State: {indent(entity_state_to_str(entity))}") for entity in nearby_entities if entity is not agent
    ]
    if not nearby_entities_strs:
        return "Nearby Entities: None"

    return "Nearby Entities:\n" + "\n".join(nearby_entities_strs)
