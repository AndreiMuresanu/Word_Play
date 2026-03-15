from word_play.environment import (
    Position,
    Environment,
    Environment_State,
    Entity,
    Component,
    Agent_Policy,
    Non_Agent_Policy,
    Observation,
    Action_Arg,
    String_Arg,
    Int_Arg,
    arg_in_range,
    String_Choice_Arg,
    Dynamic_Choice_Arg,
    List_Arg,
    Dict_Arg,
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
    entity_definition_order,
    random_order,
    randomize_agent_order,
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
from typing import Any, Callable, Iterable
from copy import deepcopy
import pprint
from abc import ABC, abstractmethod

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
                    f"\nSome additional information about your action: {pprint.pformat(self.info["action_info"])}"
                )
            else:
                extra_action_info_text = ""
            previous_action_info = f"Your last action {"was successful." if self.info["action_success"] else "unsuccessful."}{extra_action_info_text}\n\n"

        return f"""{previous_action_info}Your reward last turn was {self.last_reward}.

Your Info:
{indent("State: " + indent(entity_state_to_str(self.agent)))}

{format_nearby_entities(self.nearby_entities, self.agent)}

Possible Action:{format_possible_actions(self.possible_actions)}
"""


class Simple_Grid_World(Environment):
    def __init__(
        self,
        description: str,
        state: Environment_State,
        entity_order: Callable[[list[Entity], Environment], list[int]] = entity_definition_order,
    ):
        super().__init__(
            description,
            state,
            movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
            reward_func=zero_reward_func,
            entity_order=entity_order,
        )

    def observe(self, agent_id: int) -> Observation:
        return Simple_Observation(
            possible_actions=self.possible_actions(self.agents[agent_id]),
            nearby_entities=self.entities_near_position(self.agents[agent_id].position),
            agent=self.agents[agent_id],
            last_reward=self.last_rewards[agent_id],
            info=self.infos[agent_id],
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]):
        pass

    def environment_end_of_step(self, action_selections: list[Action_Selection]):
        pass

    def _reset(self, seed=None) -> None:
        pass


class Human_Takes_Action(Agent_Policy):

    MAX_ATTEMPTS = 10

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict | None]:
        print("--------------------")
        print(observation)

        for retry_count in range(self.MAX_ATTEMPTS):
            action_selection = self._choose_action(observation)

            if action_selection.required_kwargs:
                kwargs = self._get_action_kwargs(action_selection)
                action_selection.action_kwargs = kwargs

            if action_selection.is_valid():
                break

            print("Invalid action choice.")

            if retry_count >= self.MAX_ATTEMPTS - 1:
                raise RuntimeError("Too many invalid attempts selecting an action.")

        return action_selection, None

    def _choose_action(self, observation: Observation) -> Action_Selection:
        for _ in range(self.MAX_ATTEMPTS):
            try:
                idx = int(input("Input action index: "))
                if 0 <= idx < len(observation.possible_actions):
                    return observation.possible_actions[idx]

            except ValueError:
                pass
            print("Invalid action index.")
        raise RuntimeError("Too many invalid attempts selecting an action.")

    def _format_kwargs_prompt(self, action_selection: Action_Selection) -> str:

        lines = ["Required arguments:"]

        for name, arg in action_selection.required_kwargs.items():
            desc = arg.arg_description(
                action_selection.actor,
                action_selection.target_entity,
                action_selection.env,
            )

            lines.append(f"  - {name}: {desc}")

        lines.append("")
        lines.append("Enter values separated by ';'")
        lines.append("Example: 'value1; value2, ...'")

        return "\n".join(lines) + "\n> "

    def _get_action_kwargs(self, action_selection: Action_Selection) -> dict:
        for _ in range(self.MAX_ATTEMPTS):
            try:
                input_prompt = self._format_kwargs_prompt(action_selection)
                text = input(input_prompt)
                return action_selection.parse_and_validate_kwarg_list(text)

            except Exception:
                print("Invalid argument format. Try again.")
        raise RuntimeError("Too many invalid attempts entering arguments.")


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

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        target_entity.tags.append("in_inventory")
        actor.get_component(Inventory).inventory.append(target_entity)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Pick up {target_entity.name}."


class In_Actor_Inventory(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return target_entity in actor.get_component(Inventory).inventory


class Drop_Item(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                In_Actor_Inventory(),
                Target_Not_Self(),
                Target_Is_Nearby(),
            ]
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        target_entity.tags.remove("in_inventory")
        actor.get_component(Inventory).inventory.remove(target_entity)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
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

    def on_destroy(self, env):
        # Drop items on death
        for item in self.inventory:
            item.tags.remove("in_inventory")

        self.inventory = []


class Key(Component):
    def __init__(self, key_name: str):
        super().__init__()
        self.key_name = key_name


class Door(Component):
    def __init__(self, key_name: str, locked: bool = True, collision_tag: str = "wall"):
        super().__init__()
        self.key_name = key_name
        self.locked = locked
        self.collision_tag = collision_tag

    def on_instantiation(self, env: Environment, seed: int | None) -> None:
        if self.locked and self.collision_tag not in self.entity.tags:
            self.entity.tags.append(self.collision_tag)
        elif not self.locked and self.collision_tag in self.entity.tags:
            self.entity.tags.remove(self.collision_tag)


class Target_Is_Locked_Door(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        door_comp = target_entity.get_component(Door)
        return door_comp is not None and door_comp.locked


class Target_Is_Unlocked_Door(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        door_comp = target_entity.get_component(Door)
        return door_comp is not None and not door_comp.locked


class Actor_Has_Key_For_Door(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        inventory_comp = actor.get_component(Inventory)
        door_comp = target_entity.get_component(Door)

        if inventory_comp is None or door_comp is None:
            return False

        return any(
            item.has_component(Key) and item.get_component(Key).key_name == door_comp.key_name
            for item in inventory_comp.inventory
        )


class Unlock_Door(Action):
    def __init__(self, target_is_nearby: Callable[[Entity, Entity, Environment], bool] | None = None):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Has_Component(Door),
                Target_Is_Locked_Door(),
                Actor_Has_Key_For_Door(),
                Target_Is_Nearby(target_is_nearby),
            ]
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        door_comp = target_entity.get_component(Door)
        door_comp.locked = False
        if door_comp.collision_tag in target_entity.tags:
            target_entity.tags.remove(door_comp.collision_tag)

        return {"unlocked_door": target_entity.name, "key_name": door_comp.key_name}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Unlock {target_entity.name}."


class Lock_Door(Action):
    def __init__(self, target_is_nearby: Callable[[Entity, Entity, Environment], bool] | None = None):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Has_Component(Door),
                Target_Is_Unlocked_Door(),
                Actor_Has_Key_For_Door(),
                Target_Is_Nearby(target_is_nearby),
            ]
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        door_comp = target_entity.get_component(Door)
        door_comp.locked = True
        if door_comp.collision_tag not in target_entity.tags:
            target_entity.tags.append(door_comp.collision_tag)

        return {"locked_door": target_entity.name, "key_name": door_comp.key_name}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Lock {target_entity.name}."


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

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        target_entity.get_component(Health).health -= self.damage_amount

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"{self.name} {target_entity.name}"


class Health(Component):

    def __init__(self, max_health: float, starting_health: float):
        super().__init__()
        self.max_health = max_health
        self.health = starting_health

    def post_actions_step(self, env: Environment) -> None:
        # NOTE: race conditions (e.g., entity is destory only on the next step after a killing blow) due to action order
        #       are avoided since all entity step funcs are run after the actions are resolved
        # NOTE: If both agents A and B have 1 health and they both zap each other on the same turn for 1 damage. Under
        #       the current implementation, they will both die, instead of only the agent who gets zapped first dying.
        #       This is because the agents are only destroyed in post_actions_step, i.e., after all actions have executed
        if self.health <= 0:
            env.destroy_entity(self.entity)


class Test_Action(Action):

    def __init__(self):
        super().__init__(
            validation_rules=[Target_Is_Self()],
            required_kwargs={
                "gold coin count": Int_Arg(),
                "assignment": Dict_Arg(String_Arg(), Int_Arg()),
                "damages": List_Arg(Int_Arg()),
                "item": String_Choice_Arg({"hammer", "apple"}),
            },
        )

    def exec_action(self, actor, target_entity, env, kwargs):
        print("=======")
        pprint.pprint(kwargs, sort_dicts=False)
        print("=======")

    def action_description_text(self, actor, target_entity, env):
        return "Test Action."


def matching_actions(
    action_type: type[Action], target_entity: Entity | None, action_selections: Iterable[Action_Selection]
) -> list[Action_Selection]:
    """
    Return all Action_Selection objects whose action matches action_type and whose target matches target_entity. If
    target_entity is None, any target is accepted.
    """
    return [
        action_selection
        for action_selection in action_selections
        if isinstance(action_selection.action, action_type)
        and (target_entity is None or action_selection.target_entity is target_entity)
    ]


# TODO: ANDREI: use this to make a zap-on-sight comp--this should be a preset (or maybe just show it as an example?). I.e., it's just Follow_Action_Sequence([Attack("Zap", damage=1)])
# TODO: this class can be made much more general. E.g., the target should likely be a func or a list of valid target tags or something
class Follow_Action_Sequence(Non_Agent_Policy):
    """
    Entity will continuously iterate through a sequence of actions. E.g., imagine an entity patrolling an area or doing
    a repetitive routine.
    """

    def __init__(self, action_sequence: list[tuple[type[Action], Entity | None]], skip_invalid_actions: bool = True):
        """
        action_sequence is a list of (Action type, target_entity). If target_entity is None, we consider this to mean
        that all target entities are valid.
        """
        super().__init__()
        assert len(action_sequence) > 0, "action_sequence cannot be empty."
        self.action_sequence = action_sequence
        self.cur_action_index = 0
        self.skip_invalid_actions = skip_invalid_actions

    def post_initialization(self) -> None:
        for action_type, _ in self.action_sequence:
            assert self.entity.has_action_type(action_type), (
                "The Follow_Action_Sequence class expects all action in action_sequence to be present in the parent"
                f" entity. '{action_type}' is missing"
            )

        if not any(isinstance(action, Do_Nothing) for action in self.entity.actions):
            self.entity.actions.append(Do_Nothing())

    def _increment_cur_action_index(self) -> None:
        self.cur_action_index += 1
        if self.cur_action_index >= len(self.action_sequence):
            self.cur_action_index = 0

    def _iterate_over_actions(self, start_index):
        n = len(self.action_sequence)
        for i in range(n):
            yield self.action_sequence[(start_index + i) % n]

    def select_action(self, possible_actions: list[Action_Selection], env: Environment) -> Action_Selection:
        action_selection = Action_Selection(
            action=Do_Nothing(), action_kwargs=None, actor=self.entity, target_entity=self.entity, env=env
        )

        for cur_action in self._iterate_over_actions(self.cur_action_index):
            all_matching_actions = matching_actions(cur_action[0], cur_action[1], possible_actions)
            if all_matching_actions:
                action_selection = all_matching_actions[0]
                break

            if not self.skip_invalid_actions:
                break
            self._increment_cur_action_index()

        self._increment_cur_action_index()

        return action_selection


# TODO: ANDREI: create fuction which returns a list of entites given a 2D array. This func would be used so that we can
#       just define a tilemap instead of a giant list of wall entities. The function signature should be something like:
#       tilemap_to_entites(tilemap: list[list[str]], tileset: dict[str, dict]) -> list[Entity]. The values of the
#       tileset are all of the args required to init the entity with the exception of the position arg which is added
#       from the tilemap. I think this is better than deepcopying an entity with a random position since we don't know
#       what logic needs to exec in the entity's init
def tilemap_to_entites(tilemap: list[list[str]], tileset: dict[str, dict]) -> list[Entity]:
    pass


# TODO: not sure if the info args are required for end_conversation and send_message
class Communication_Policy(Component, ABC):
    @abstractmethod
    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    @abstractmethod
    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        pass

    @abstractmethod
    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        pass

    @abstractmethod
    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass


class Human_Communication_Policy(Communication_Policy):

    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        print(f"====== Starting conversation with: {[entity.name for entity in participants]} ======")
        if info:
            print(info)

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        if info:
            print(info)
        return input("Your message: ")

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        print(f"Received message from {sender.name}: {message}")

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            print(info)
        print(f"====== Ending conversation with: {[entity.name for entity in participants]} ======")


class TalkingCow(Communication_Policy):
    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        return "Moo."

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        pass

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass


# TODO: this is just a template, this class needs to be implemented. This class should use some general LLM API so that
#       it can switch to use different LLMs very easily. It should not store the LLM in memory, since if we have many
#       agents, we don't want many copies of the same LLM. It should also manage its memory, e.g., it is responsible for
#       storing information about past observations and past chats with other agents.
#       This class should accept a Human_LLM class as input for its LLM (e.g., see model_presets.py). The Human_LLM
#       model sees the exact same thing as the LLM, the only difference is that the human is generating text instead of
#       the LLM. This is a very useful class for testing and debugging.
class LLM_Action_And_Communication_Policy(Agent_Policy, Communication_Policy):

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        pass

    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        pass

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        pass

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass


def nearby_conversation_partners(actor: Entity, env: Environment) -> list[Entity]:
    return [
        entity
        for entity in env.state.entities
        if (
            env.movement_system.positions_are_close(actor.position, entity.position)
            and entity is not actor
            and entity.has_component(Communication_Policy)
        )
    ]


class A_Conversation_Partner_Is_Nearby(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return len(nearby_conversation_partners(actor, env)) != 0


# TODO: could add a turn order arg which takes as input an ordering func or a str keyword. Just need to be careful to
#       make sure that the same entity doesn't send a message twice in a row.
def sim_simple_conversation(participants: list[Entity], env: Environment, conversation_duration: int = 3) -> None:
    for speaker in participants:
        speaker.get_component(Communication_Policy).start_conversation(participants, env)

    for turn in range(conversation_duration):
        for speaker in participants:
            recipients = [entity for entity in participants if entity is not speaker]
            message = speaker.get_component(Communication_Policy).send_message(recipients, env)
            for recipient in recipients:
                recipient.get_component(Communication_Policy).receive_message(message, speaker, env)

    for speaker in participants:
        speaker.get_component(Communication_Policy).end_conversation(participants, env)


class Start_Public_Conversation(Action):

    def __init__(
        self,
        conversation_format: Callable[[list[Entity]], None] = sim_simple_conversation,
    ):
        self.conversation_format = conversation_format
        super().__init__(validation_rules=[Target_Is_Self(), A_Conversation_Partner_Is_Nearby()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        participants = nearby_conversation_partners(actor, env)
        participants.append(actor)
        self.conversation_format(participants, env)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Start a conversation with everyone nearby: {[entity.name for entity in nearby_conversation_partners(actor, env)]}."


def partner_idx_list_is_valid(
    partner_indices: list[int], actor: Entity, target_entity: Entity, env: Environment
) -> bool:
    potential_partner_count = len(nearby_conversation_partners(actor, env))
    return all(0 <= idx < potential_partner_count for idx in partner_indices)


class Nearby_Partner_Indicies(List_Arg):

    def __init__(self):
        super().__init__(Int_Arg(), validators=[partner_idx_list_is_valid])

    def arg_description(self, actor, target_entity, env):
        potential_partners = nearby_conversation_partners(actor, env)
        partners_text = ", ".join(f"{idx} ({entity.name})" for idx, entity in enumerate(potential_partners))
        return f"list of indices representing the conversation participants: {partners_text}"


class Start_Private_Conversation(Action):

    def __init__(
        self,
        conversation_format: Callable[[list[Entity]], None] = sim_simple_conversation,
    ):
        self.conversation_format = conversation_format
        super().__init__(
            validation_rules=[Target_Is_Self(), A_Conversation_Partner_Is_Nearby()],
            required_kwargs={"conversation partners": Nearby_Partner_Indicies()},
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert "conversation partners" in kwargs, "Action missing kwarg: 'conversation partners'"
        potential_participants = nearby_conversation_partners(actor, env)
        participants = [potential_participants[idx] for idx in kwargs["conversation partners"]]
        participants.append(actor)
        self.conversation_format(participants, env)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Start a private conversation with only some of the nearby people."


def run_exp():
    exp_steps = 1000

    env = Simple_Grid_World(
        description="The forbidden forest.",
        state=Environment_State(
            entities=[
                Entity(
                    name="Iskandar",
                    position=Position_2D(0, 0),
                    actions=[
                        Test_Action(),
                        Do_Nothing(),
                        Move_Up(),
                        Move_Down(),
                        Move_Left(),
                        Move_Right(),
                        Unlock_Door(),
                        Lock_Door(),
                        Attack(name="Zap", damage_amount=1),
                        Start_Public_Conversation(),
                        Start_Private_Conversation(),
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
                        Human_Communication_Policy(),
                    ],
                ),
                Entity(
                    name="Copper Key",
                    position=Position_2D(0, 0),
                    tags=["item"],
                    components=[Key(key_name="copper")],
                ),
                Entity(
                    name="Copper Door",
                    position=Position_2D(0, 0),
                    components=[Door(key_name="copper"), Collidable()],
                ),
                # Entity(
                #     name="Andrei",
                #     position=Position_2D(0, 0),
                #     actions=[
                #         Do_Nothing(),
                #         Move_Up(),
                #         Move_Down(),
                #         Move_Left(),
                #         Move_Right(),
                #         Attack(name="Zap", damage_amount=1),
                #     ],
                #     components=[
                #         Human_Takes_Action(),
                #         Inventory(
                #             collectable_tags=["item"],
                #             inventory_size=2,
                #             starting_inventory=[
                #                 Entity(name="Strawberry", position=Position_2D(100, 100), tags=["item"])
                #             ],
                #         ),
                #         Health(max_health=5, starting_health=3),
                #         Collidable(collidable_tags=["wall"]),
                #     ],
                # ),
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
                    actions=[Move_Up(), Move_Down()],
                    components=[
                        Health(max_health=5, starting_health=5),
                        Follow_Action_Sequence([(Move_Up, None), (Move_Down, None)]),
                        TalkingCow(),
                    ],
                ),
                Entity(
                    name="Fat Cow",
                    position=Position_2D(1, 0),
                    components=[
                        Health(max_health=10, starting_health=10),
                        TalkingCow(),
                    ],
                ),
                Entity(
                    name="Tiny Cow",
                    position=Position_2D(1, 0),
                    components=[
                        Health(max_health=1, starting_health=1),
                        TalkingCow(),
                    ],
                ),
                Entity(
                    name="Wall",
                    position=Position_2D(-1, 0),
                    tags=["wall"],
                    components=[Collidable()],
                ),
                # TODO: for a real pike entity, you likely want an Attack_All_Nearby_Entities action instead of Attack
                Entity(
                    name="Spike",
                    position=Position_2D(0, -2),
                    actions=[Attack(name="Poke", damage_amount=1)],
                    tags=["item"],
                    components=[Follow_Action_Sequence([(Attack, None)])],
                ),
            ]
        ),
        entity_order=entity_definition_order,
    )

    for step in range(exp_steps):
        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)
            cur_step_actions.append(action)

        env.step(cur_step_actions)


if __name__ == "__main__":
    run_exp()
