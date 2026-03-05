from word_play.environment import (
    Environment,
    Environment_State,
    Entity,
    Component,
    Take_Action,
    Observation,
    Action,
    Action_Validation,
    Action_Chain,
    Target_Is_Self,
    Target_Not_Self,
    Target_Is_Nearby,
    Target_Has_Tag,
    Target_Doesnt_Have_Tag,
    Target_Has_Component,
    Action_Selection,
)

from word_play.presets.movement_system_presets import (
    INFINITE_2D_MOVEMENT_SYSTEM,
    Move_Up,
    Move_Down,
    Move_Left,
    Move_Right,
    Position_2D,
    Collidable,
)
from word_play.presets.reward_func_presets import zero_reward_func
from word_play.presets.action_presets import Do_Nothing
from word_play.presets.observation_presets import format_possible_actions

from dataclasses import dataclass
from typing import Any, Callable
from copy import deepcopy
import pprint

"""This file is to be used with V2.0 of WordPlay, i.e., the version after the component refactor."""


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


# TODO: slowly make this nice so that the printing of things like all component infos are printed nicely
# TODO: make it so that I can see some info about objs in inventory (not all since it would be too much)
@dataclass(slots=True)
class Simple_Observation(Observation):
    agent: Entity
    nearby_entities: list[Entity]

    def __str__(self):
        return f"""Your Info:
{indent("State: " + indent(entity_state_to_str(self.agent)))}

{format_nearby_entities(self.nearby_entities, self.agent)}

Possible Action:{format_possible_actions(self.possible_actions)}
"""


class Test_Env(Environment):
    def __init__(self, description: str, state: Environment_State):
        super().__init__(
            description,
            state,
            movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
            reward_func=zero_reward_func,
        )

    def observe(self, agent_id: int) -> Observation:
        return Simple_Observation(
            possible_actions=self.possible_actions(agent_id),
            nearby_entities=self.entities_near_position(self.agents[agent_id].position),
            agent=self.agents[agent_id],
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]):
        pass

    def environment_end_of_step(self, action_selections: list[Action_Selection]):
        pass

    def _reset(self, seed=None) -> None:
        pass


class Human_Takes_Action(Take_Action):

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        print("--------------------")
        print(observation)

        while True:
            try:
                action_choice_idx = int(input("Input action index: "))
                if 0 <= action_choice_idx < len(observation.possible_actions):
                    break
            except Exception:
                pass

        return (
            Action_Selection(
                action=observation.possible_actions[action_choice_idx].action,
                actor=observation.possible_actions[action_choice_idx].actor,
                target_entity=observation.possible_actions[action_choice_idx].target_entity,
            ),
            None,
        )


class Room_In_Inventory(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        inventory_comp = actor.get_component(Inventory)
        if inventory_comp.inventory_size < 0:
            return True
        return len(inventory_comp.inventory) < inventory_comp.inventory_size


class Pick_Up_Item(Action):
    def __init__(
        self, collectable_tags: list[str], item_is_nearby: Callable[[Entity, Entity, Environment], bool] | None = None
    ):
        super().__init__(
            validation_rules=[
                Target_Has_Tag(collectable_tags),
                Target_Doesnt_Have_Tag(["in_inventory"]),
                Room_In_Inventory(),
                Target_Not_Self(),
                Target_Is_Nearby(item_is_nearby),
            ]
        )

    def __call__(self, actor: Entity, target_entity: Entity, env: Environment) -> None:
        target_entity.tags.append("in_inventory")
        actor.get_component(Inventory).inventory.append(target_entity)

    def action_description_text(self, actor: Entity, target_entity: Entity) -> str:
        return f"Pick up {target_entity.name}."


class Drop_Item(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Has_Tag(["in_inventory"]),
                Target_Not_Self(),
                Target_Is_Nearby(),
            ]
        )

    def __call__(self, actor: Entity, target_entity: Entity, env: Environment) -> None:
        target_entity.tags.remove("in_inventory")
        actor.get_component(Inventory).inventory.remove(target_entity)

    def action_description_text(self, actor: Entity, target_entity: Entity) -> str:
        return f"Drop {target_entity.name}."


# TODO: would be nice to add the functionality to have agents start with things in their inventory
# TODO: perhaps there is a nicer solution than the in_inventory tag I'm not sure what issues the tag approach can cause
#       when it interacts with different components. A diff approach is creating entity heirarchies, but this might be
#       overkill.
class Inventory(Component):

    def __init__(
        self, collectable_tags: list[str], inventory_size: int = -1, starting_inventory: list[Entity] | None = None
    ):
        """inventory_size < 0 represents an infinite inventory size."""

        super().__init__(
            actions=[Pick_Up_Item(collectable_tags), Drop_Item()],
        )
        self.inventory_size: int = inventory_size
        self.inventory: list[Entity] = []
        self.starting_inventory = starting_inventory

    def on_instantiation(self, env: Environment, seed: int | None) -> None:
        for entity in self.starting_inventory:
            entity.position = deepcopy(self.entity.position)
            env.instantiate_entity(entity)
            self.inventory.append(entity)
            entity.tags.append("in_inventory")

    def post_actions_step(self, env: Environment) -> None:
        for obj_entity in self.inventory:
            # TODO: we can likely do something nicer than a deepcopy (e.g., by adding some kinda of functionality to the
            #       Position class)
            obj_entity.position = deepcopy(self.entity.position)


# TODO: complete class. Heal should be able to heal both self and other entities (just don't add the associated validation rules)
# TODO: think about how to chain/compose this action with, E.g., an Eat action. Eat action ought to be able to have any
#       other effect associated
class Heal(Action):
    pass


class Attack(Action):

    def __init__(
        self,
        name: str,
        damage_amount: float,
        untargetable_tags: list[str] | None = None,
        target_is_nearby: Callable[[Entity, Entity, Environment], bool] | None = None,
    ):
        untargetable_tags = untargetable_tags or []
        untargetable_tags.append("in_inventory")

        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Has_Component(Health),
                Target_Is_Nearby(target_is_nearby),
                Target_Doesnt_Have_Tag(untargetable_tags),
            ]
        )

        self.name: str = name
        self.damage_amount: float = damage_amount

    def __call__(self, actor: Entity, target_entity: Entity, env: Environment) -> None:
        target_entity.get_component(Health).health -= self.damage_amount

    def action_description_text(self, actor: Entity, target_entity: Entity) -> str:
        return f"{self.name} {target_entity.name}"


class Health(Component):

    def __init__(self, max_health: float, starting_health: float):
        super().__init__()
        self.max_health = max_health
        self.health = starting_health

    def post_actions_step(self, env: Environment) -> None:
        # NOTE: race conditions (e.g., entity is destory only on the next step after a killing blow) due to action order
        #       are avoided since all entity step funcs are run after the actions are resolved
        if self.health <= 0:
            env.destroy_entity(self.entity)


# *************
# TODO: ANDREI: need to think very deeply about this class. Using pre_actions_step avoid conflict with the Health comp,
#       but maybe some comps need actions to run after their step func. We would also likely need to refactor the
#       Environment.possible_actions method to take as input an entity rather than agent_id. We can have a
#       wrapper/helper which takes agent_id.
#       The biggest thing to think about tho is whether we want Entities to have actions. If so, then there ought to be
#       a standard way for the actions to run. Otherwise, this method is likely not the best. Maybe entities should have
#       actions. Imagine games where we want entities with simple AI. Thus, perhaps non-agent entities should be allowed
#       to add a Take_Action component which they can use to select actions. Or maybe if actions become standard,
#       select_action should just be a standard method of the component class or something else??
#       Maybe the best approach is to create some kinda of component like Non_Agent_Execute_Actions?
# class Apply_Actions_Whenever_Possible(Component):
#     """
#     This component can be attached to non-agent entites to allow them to apply actions anytime it is possible to apply
#     the action. E.g., a spike can apply a damage/attack action to all entities on it.

#     Note that this behaviour (e.g., the spike damange behaviour) can also be directly added to a spike component step
#     function which damages all entities on top of it.
#     """

#     def __init__(self, actions: list[Action]):
#         super().__init__(actions=actions)

#     def pre_actions_step(self, env: Environment) -> None:
#         for action in


# TODO: ANDREI: create fuction which returns a list of entites given a 2D array. This func would be used so that we can
#       just define a tilemap instead of a giant list of wall entities. The function signature should be something like:
#       tilemap_to_entites(tilemap: list[list[str]], tileset: dict[str, dict]) -> list[Entity]. The values of the
#       tileset are all of the args required to init the entity with the exception of the position arg which is added
#       from the tilemap. I think this is better than deepcopying an entity with a random position since we don't know
#       what logic needs to exec in the entity's init
def tilemap_to_entites(tilemap: list[list[str]], tileset: dict[str, dict]) -> list[Entity]:
    pass


def run_exp():
    exp_steps = 1000

    env = Test_Env(
        description="The forbidden forest.",
        state=Environment_State(
            entities=[
                Entity(
                    name="Iskandar",
                    position=Position_2D(0, 0),
                    actions=[
                        Do_Nothing(),
                        Move_Up(),
                        Move_Down(),
                        Move_Left(),
                        Move_Right(),
                        Attack(name="Zap", damage_amount=1),
                    ],
                    components=[
                        Human_Takes_Action(),
                        Inventory(
                            collectable_tags=["item"],
                            inventory_size=2,
                            starting_inventory=[
                                Entity(name="Strawberry", position=Position_2D(100, 100), tags=["item"])
                            ],
                        ),
                        Health(max_health=5, starting_health=3),
                        Collidable(collidable_tags=["wall"]),
                    ],
                ),
                Entity(name="Blue Flower", position=Position_2D(0, 1), tags=["item"]),
                Entity(
                    name="Barrel",
                    position=Position_2D(0, 0),
                    tags=["item"],
                    components=[Health(max_health=1, starting_health=1)],
                ),
                Entity(
                    name="Barrel",
                    position=Position_2D(0, 1),
                    tags=["item"],
                    components=[Health(max_health=1, starting_health=1)],
                ),
                Entity(
                    name="Cow",
                    position=Position_2D(1, 0),
                    components=[Health(max_health=5, starting_health=5)],
                ),
                Entity(
                    name="Wall",
                    position=Position_2D(-1, 0),
                    tags=["wall"],
                    components=[Collidable()],
                ),
            ]
        ),
    )

    for step in range(exp_steps):
        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Take_Action).select_action(observation)
            cur_step_actions.append(action)

        env.step(cur_step_actions)


if __name__ == "__main__":
    run_exp()
