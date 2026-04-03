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
from word_play.model import Model

from dataclasses import dataclass
from typing import Any, Callable, Iterable
from copy import deepcopy
import pprint
from abc import ABC, abstractmethod
import json
import os
import re
import sys

"""This file is to be used with V2.0 of WordPlay, i.e., the version after the component refactor."""



def component_data_attributes(comp):
    return {
        name: value
        for name, value in comp.__dict__.items()
        if not name.startswith("__") and not callable(value) and name != "entity"
    }


def _format_inventory_items(inventory: list[Entity]) -> list[str]:
    return [item.name for item in inventory]


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

        if issubclass(ctype, Agent_Policy) or issubclass(ctype, Non_Agent_Policy) or issubclass(ctype, Communication_Policy):
            continue

        if component_name == "Health":
            lines.append(f"health: {comp.health}/{comp.max_health}")
        elif component_name == "Inventory":
            lines.append(f"inventory_size: {comp.inventory_size}")
            lines.append(f"inventory: {_format_inventory_items(comp.inventory)}")
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
    strs = [f"- {entity_state_to_str(entity).replace(chr(10), chr(10) + '  ')}" for entity in nearby_entities if entity is not agent]
    if not strs:
        return "Nearby Entities: None"
    return "Nearby Entities:\n" + "\n".join(strs)


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
        nearby_block = format_nearby_entities(self.nearby_entities, self.agent)
        actions_block = "AVAILABLE ACTIONS (reply with the index):" + format_action_list(self.possible_actions)

        return "\n\n".join(
            filter(
                None,
                [
                    prev_block + f"REWARD THIS TURN: {self.last_reward}",
                    agent_block,
                    nearby_block,
                    actions_block,
                ],
            )
        )


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


class OpenRouter_Model(Model):
    """
    Chat model backed by OpenRouter. Any model from https://openrouter.ai/models
    works, e.g.:
        "meta-llama/llama-3.1-8b-instruct"
        "openai/gpt-4o"
        "anthropic/claude-3-5-sonnet"
        "google/gemma-3-1b-it:free"
 
    Requires the OPENROUTER_API_KEY environment variable to be set.
    """
 
    _CLIENT = None
 
    def __init__(
        self,
        model_name: str,
        system_prompt: str = "",
        generation_params: dict | None = None,
        site_url: str | None = None,
        app_name: str | None = None,
        verbosity: int = 0,
    ):
        super().__init__(verbosity=verbosity)
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.generation_params = generation_params or {}
 
        headers = {}
        if site_url:
            headers["HTTP-Referer"] = site_url
        if app_name:
            headers["X-Title"] = app_name
        self._headers = headers
 
    def _get_client(self):
        if OpenRouter_Model._CLIENT is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ImportError("OpenRouter_Model requires the 'openai' package.") from exc
 
            api_key = ""
            if not api_key:
                raise EnvironmentError("Missing environment variable: OPENROUTER_API_KEY")
 
            OpenRouter_Model._CLIENT = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers=self._headers or None,
            )
        return OpenRouter_Model._CLIENT
 
    def generate_text(self, input_text: str | list[str], generation_config=None, max_new_tokens=None) -> str:
        if isinstance(input_text, list):
            raise NotImplementedError("Batched input is not supported.")
 
        params = {**self.generation_params, **(generation_config or {})}
        if max_new_tokens is not None:
            params["max_tokens"] = max_new_tokens
 
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": input_text})
 
        response = self._get_client().chat.completions.create(
            model=self.model_name,
            messages=messages,
            **params,
        )
        return response.choices[0].message.content.strip()
 
 
class Lazy_Model_Handle(Model):
    """
    Defers model construction until the first generate_text call.
 
    Usage:
        LLM_MODEL_REGISTRY["main"] = Lazy_Model_Handle(
            lambda: OpenRouter_Model("meta-llama/llama-3.1-8b-instruct", system_prompt="...")
        )
    """
 
    def __init__(self, loader: Callable[[], Model], verbosity: int = 0):
        super().__init__(verbosity=verbosity)
        self.loader = loader
        self._model: Model | None = None
 
    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = self.loader()
        return self._model
 
    def generate_text(self, input_text: str | list[str], generation_config=None, max_new_tokens=None) -> str:
        if max_new_tokens is None:
            return self.model.generate_text(
                input_text,
                generation_config=generation_config,
            )

        try:
            return self.model.generate_text(
                input_text,
                generation_config=generation_config,
                max_new_tokens=max_new_tokens,
            )
        except TypeError as exc:
            if "max_new_tokens" not in str(exc):
                raise
            return self.model.generate_text(
                input_text,
                generation_config=generation_config,
            )
 
    def cond_logP(self, inputs, targets):
        return self.model.cond_logP(inputs, targets)
 
 
# ===========================================================================
# Model registry
# ===========================================================================
 
# Populate before creating any agents, e.g.:
#   LLM_MODEL_REGISTRY["main"] = OpenRouter_Model("meta-llama/llama-3.1-8b-instruct", system_prompt="...")
LLM_MODEL_REGISTRY: dict[str, Model] = {}


def resolve_registered_model(model_key: str) -> Model:
    if model_key not in LLM_MODEL_REGISTRY:
        raise KeyError(
            f"Model '{model_key}' not found in LLM_MODEL_REGISTRY. "
            f"Available keys: {list(LLM_MODEL_REGISTRY)}"
        )
    return LLM_MODEL_REGISTRY[model_key]

# test with human LLM and observe the history and observations


class LLM_Action_And_Communication_Policy(Agent_Policy, Communication_Policy):
    """
    A combined action-selection and communication policy backed by any Model.

    Action output format — JSON:
        {"action_choice_idx": <int>, "action_kwargs": {<key>: <value>, ...}}

    The policy does NOT store the model object itself — it holds only a string
    key into LLM_MODEL_REGISTRY. This means any number of agents can share one
    model without duplicating it in memory.

    Memory:
        - observation_history: rolling buffer of past observation strings,
          included as context in the selection prompt.
        - conversation_history: rolling buffer of dialogue turns.
    """

    MAX_ATTEMPTS = 3

    def __init__(
        self,
        model_key: str,
        system_prompt: str = "",
        action_generation_config: dict | None = None,
        message_generation_config: dict | None = None,
        reasoning_generation_config: dict | None = None,
        use_chain_of_thought: bool = False,
        conversation_memory_window: int = 12,
        observation_memory_window: int = 4,
    ):
        super().__init__()
        self.model_key = model_key
        self.system_prompt = system_prompt
        self.action_generation_config = action_generation_config
        self.message_generation_config = message_generation_config
        self.reasoning_generation_config = reasoning_generation_config
        self.use_chain_of_thought = use_chain_of_thought
        self.conversation_memory_window = conversation_memory_window
        self.observation_memory_window = observation_memory_window

        self.observation_history: list[str] = []
        self.observation_summary: str | None = None
        self.conversation_history: list[dict[str, str]] = []
        self.active_conversation_participants: list[str] = []

    @property
    def model(self) -> Model:
        return resolve_registered_model(self.model_key)

    # -----------------------------------------------------------------------
    # Agent_Policy — action selection
    # -----------------------------------------------------------------------

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        reasoning: str | None = None

        if self.use_chain_of_thought:
            reasoning_prompt = self._reasoning_prompt(observation)
            reasoning = self.model.generate_text(
                self._with_system(reasoning_prompt),
                self.reasoning_generation_config,
            ).strip()

        selection_prompt = self._selection_prompt(observation, reasoning)
        last_exc: Exception | None = None

        for attempt in range(self.MAX_ATTEMPTS):
            raw = self.model.generate_text(
                self._with_system(selection_prompt),
                self.action_generation_config,
            )
            try:
                action_selection = self._parse_selection(raw, observation)
                self._record_observation(observation)
                return action_selection, {
                    "raw_response": raw,
                    "reasoning": reasoning,
                    "attempt": attempt + 1,
                }
            except Exception as exc:
                last_exc = exc
                selection_prompt = self._retry_prompt(selection_prompt, raw, str(exc))

        raise RuntimeError(
            f"LLM failed to produce a valid action after {self.MAX_ATTEMPTS} attempts. "
            f"Last error: {last_exc}"
        )

    def _record_observation(self, observation: Observation) -> None:
        self.observation_history.append(str(observation))
        if len(self.observation_history) > self.observation_memory_window:
            overflow = self.observation_history[:-self.observation_memory_window]
            self._update_observation_summary(overflow)
            self.observation_history = self.observation_history[-self.observation_memory_window:]

    def _update_observation_summary(self, observations: list[str]) -> None:
        summary_lines: list[str] = []
        if self.observation_summary:
            summary_lines.append(self.observation_summary)

        for observation_text in observations:
            summary_lines.append(self._summarize_observation_text(observation_text))

        self.observation_summary = "\n".join(line for line in summary_lines if line).strip() or None

    def _summarize_observation_text(self, observation_text: str) -> str:
        summary_parts = []
        reward_match = re.search(r"REWARD THIS TURN:\s*(.*)", observation_text)
        if reward_match:
            summary_parts.append(f"reward={reward_match.group(1).strip()}")

        state_lines = []
        in_state_block = False
        for line in observation_text.splitlines():
            stripped = line.strip()
            if stripped == "YOUR STATE:":
                in_state_block = True
                continue
            if in_state_block and not stripped:
                break
            if in_state_block and (
                stripped.startswith("name:")
                or stripped.startswith("position:")
                or stripped.startswith("health:")
                or stripped.startswith("inventory:")
            ):
                state_lines.append(stripped)

        action_lines = [
            line.strip()
            for line in observation_text.splitlines()
            if line.strip().startswith("[") and "]" in line
        ]
        if action_lines:
            summary_parts.append(f"actions={', '.join(action_lines[:3])}")
        if state_lines:
            summary_parts.extend(state_lines[:4])

        if not summary_parts:
            summary_parts.append(observation_text.strip().splitlines()[0][:160])

        return " | ".join(summary_parts)


    # -----------------------------------------------------------------------
    # Prompt builders
    # -----------------------------------------------------------------------

    def _observation_memory_block(self) -> str:
        sections = []
        if self.observation_summary:
            sections.append(f"OLDER OBSERVATION SUMMARY:\n{self.observation_summary}")

        if not self.observation_history:
            return "\n\n".join(sections) + ("\n\n" if sections else "")

        entries = "\n\n---\n\n".join(
            f"[t-{len(self.observation_history) - i}]\n{obs}"
            for i, obs in enumerate(self.observation_history)
        )
        sections.append(f"RECENT OBSERVATIONS (oldest to most recent):\n{entries}")
        return "\n\n".join(sections) + "\n\n"

    def _reasoning_prompt(self, observation: Observation) -> str:
        return (
            "You are controlling an agent in a grid-world game.\n"
            "Think step by step about which action the agent should take next.\n"
            "Consider the agent's state, nearby entities, and available actions.\n"
            "Write your reasoning in plain text. Do NOT output JSON yet.\n\n"
            + self._observation_memory_block()
            + f"CURRENT OBSERVATION:\n{observation}\n\n"
            + format_action_details(observation.possible_actions)
        )

    def _selection_prompt(self, observation: Observation, reasoning: str | None) -> str:
        example_kwargs = "{}"
        for sel in observation.possible_actions:
            if sel.required_kwargs:
                example_kwargs = json.dumps({k: f"<{k}>" for k in sel.required_kwargs})
                break

        reasoning_block = f"\nYour prior reasoning:\n{reasoning}\n" if reasoning else ""

        return (
            "You are controlling an agent in a grid-world game.\n"
            "Choose exactly ONE action. Reply with ONLY a JSON object — no markdown, no extra text.\n\n"
            "REQUIRED FORMAT:\n"
            '{"action_choice_idx": <integer>, "action_kwargs": <dict or {}>}\n\n'
            + f'Example: {{"action_choice_idx": 0, "action_kwargs": {example_kwargs}}}\n\n'
            + self._observation_memory_block()
            + f"CURRENT OBSERVATION:\n{observation}\n"
            + reasoning_block + "\n"
            + format_action_details(observation.possible_actions) + "\n\n"
            + "Your JSON:"
        )

    def _retry_prompt(self, prev_prompt: str, bad_response: str, error: str) -> str:
        return (
            f"{prev_prompt}\n\n"
            f"Your previous response was invalid.\n"
            f"  Response: {bad_response}\n"
            f"  Error: {error}\n\n"
            "Try again. Output ONLY the JSON object."
        )

    # -----------------------------------------------------------------------
    # Response parsing
    # -----------------------------------------------------------------------

    def _parse_selection(self, raw: str, observation: Observation) -> Action_Selection:
        parsed = self._extract_json(raw)
        idx = parsed.get("action_choice_idx")

        if not isinstance(idx, int) or not (0 <= idx < len(observation.possible_actions)):
            raise ValueError(f"Invalid action_choice_idx: {idx}")

        action_selection = observation.possible_actions[idx]

        if action_selection.required_kwargs:
            action_selection.action_kwargs = self._parse_action_kwargs(
                action_selection,
                parsed.get("action_kwargs", {}),
            )
        else:
            action_selection.action_kwargs = None

        if not action_selection.is_valid():
            raise ValueError(f"Action [{idx}] is invalid in the current state.")

        return action_selection


    def _extract_json(self, text: str) -> dict:
        text = re.sub(r"```(?:json)?\s*", "", text).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in model response.")
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("JSON response must be an object.")
        return parsed


    def _with_system(self, prompt: str) -> str:
        if self.system_prompt:
            return f"{self.system_prompt}\n\n{prompt}"
        return prompt

    def _parse_action_kwargs(self, action_selection: Action_Selection, raw_kwargs: Any) -> dict:
        if not action_selection.required_kwargs:
            return {}

        if isinstance(raw_kwargs, dict):
            return self._parse_action_kwargs_dict(action_selection, raw_kwargs)

        if isinstance(raw_kwargs, list):
            kwarg_text = "; ".join(self._coerce_kwarg_value(value) for value in raw_kwargs)
            return action_selection.parse_and_validate_kwarg_list(kwarg_text)

        if isinstance(raw_kwargs, str):
            try:
                return action_selection.parse_and_validate_kwarg_dict(raw_kwargs)
            except Exception:
                return action_selection.parse_and_validate_kwarg_list(raw_kwargs)

        raise ValueError("'action_kwargs' must be a JSON object, list, or string.")

    def _parse_action_kwargs_dict(self, action_selection: Action_Selection, raw_kwargs: dict[str, Any]) -> dict:
        parts = []
        for key, value in raw_kwargs.items():
            parts.append(f"{key}: {self._coerce_kwarg_value(value)}")
        return action_selection.parse_and_validate_kwarg_dict(", ".join(parts))

    def _coerce_kwarg_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return json.dumps(value)

    # -----------------------------------------------------------------------
    # Communication_Policy — multi-agent dialogue
    # -----------------------------------------------------------------------

    def start_conversation(
        self, participants: list[Entity], env: Environment, info: str | None = None
    ) -> None:
        self.active_conversation_participants = [entity.name for entity in participants if entity is not self.entity]
        self.conversation_history.clear()
        if info:
            self.conversation_history.append({"role": "system", "content": info})
            # be careful with system prompts
            # dont want the model to over pay attention to the system prompt

    def send_message(
        self, recipients: list[Entity], env: Environment, info: str | None = None
    ) -> str:
        prompt = self._message_prompt(recipients, env, info)
        response = self.model.generate_text(
            self._with_system(prompt),
            self.message_generation_config,
        ).strip()
        self.conversation_history.append({"role": "assistant", "content": response})
        self._trim_history()
        return response

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        self.conversation_history.append({"role": "user", "content": f"{sender.name}: {message}"})
        self._trim_history()

    def end_conversation(
        self, participants: list[Entity], env: Environment, info: str | None = None
    ) -> None:
        if info:
            self.conversation_history.append({"role": "system", "content": info})
        self.active_conversation_participants = []
        self._trim_history()

    def _message_prompt(
        self, recipients: list[Entity], env: Environment, info: str | None
    ) -> str:
        recipients_str = ", ".join(entity.name for entity in recipients)
        history_str = (
            "\n".join(entry["content"] for entry in self.conversation_history[-self.conversation_memory_window:])
            or "(no prior messages)"
        )
        info_str = f"\nExtra context: {info}\n" if info else ""
        return (
            "You are playing a character in a grid-world game.\n"
            "Write ONE short in-character message. No speaker labels, no quotes.\n\n"
            f"Your character: {self.entity.name}\n"
            f"Recipients: {recipients_str}\n"
            f"Environment: {env.description}\n"
            f"{info_str}"
            f"Conversation so far:\n{history_str}\n\n"
            "Your message:"
        )

    def _trim_history(self) -> None:
        if len(self.conversation_history) > self.conversation_memory_window:
            self.conversation_history = self.conversation_history[-self.conversation_memory_window:]


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


def register_run_exp_model(model_mode: str) -> str:
    model_key = "run_exp_llm"

    if model_mode == "human_llm":
        LLM_MODEL_REGISTRY[model_key] = Lazy_Model_Handle(
            lambda: __import__(
                "word_play.presets.model_presets",
                fromlist=["Human"],
            ).Human(),
        )
        return model_key

    if model_mode == "openrouter":
        LLM_MODEL_REGISTRY[model_key] = Lazy_Model_Handle(
            lambda: OpenRouter_Model(
                model_name="openai/gpt-4.1-mini",
                system_prompt="You are a game-playing assistant that follows formatting instructions exactly.",
                generation_params={"temperature": 0.0},
                app_name="Word Play",
            )
        )
        return model_key

    LLM_MODEL_REGISTRY[model_key] = Lazy_Model_Handle(
        lambda: HuggingFace_Chat_Model(
            model_name="HuggingFaceTB/SmolLM2-360M-Instruct",
            system_prompt="You are a game-playing assistant that follows formatting instructions exactly.",
            generation_params={"max_new_tokens": 180, "do_sample": False},
        )
    )
    return model_key


def run_exp(model_mode: str = "hf_local"):
    exp_steps = 1000
    model_key = register_run_exp_model(model_mode)
    print(f"run_exp model mode: {model_mode}")

    env = Simple_Grid_World(
        description="The forbidden forest.",
        state=Environment_State(
            entities=[
                Entity(
                    name="Iskandar",
                    position=Position_2D(0, 0),
                    actions=[
                        Do_Nothing(),
                        Test_Action(),
                        Move_Up(),
                        Move_Down(),
                        Move_Left(),
                        Move_Right(),
                        Attack(name="Zap", damage_amount=1),
                        Start_Public_Conversation(),
                        Start_Private_Conversation(),
                    ],
                    components=[
                        LLM_Action_And_Communication_Policy(
                            model_key=model_key,
                            use_chain_of_thought=False,
                        ),
                        # Human_Takes_Action(),
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
            print(f"[step {step}] {agent.name} -> {action}")
            if info:
                if info.get("reasoning"):
                    print(f"[step {step}] reasoning:\n{info['reasoning']}")
                if info.get("raw_response"):
                    print(f"[step {step}] raw response:\n{info['raw_response']}")
            cur_step_actions.append(action)

        env.step(cur_step_actions)


if __name__ == "__main__":
    run_exp(sys.argv[1] if len(sys.argv) > 1 else "hf_local")
