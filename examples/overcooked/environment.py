from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from word_play.core import (
    Action,
    Action_Selection,
    Agent_Policy,
    Component,
    Entity,
    Environment,
    Environment_State,
    Observation,
)
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.movement import Move_Down, Move_Left, Move_Right, Move_Up
from word_play.presets.movement.common import Collidable
from word_play.presets.movement.simple_2d_grid import INFINITE_2D_MOVEMENT_SYSTEM, Position_2D
from word_play.presets.renderers import GridLayoutAdapter, Renderable
from word_play.presets.systems.communication.chat_room_action_communication.core import sim_simple_conversation
from word_play.presets.systems.communication.core import Communication_Policy
from word_play.presets.systems import Do_Nothing

if TYPE_CHECKING:
    from word_play.presets.renderers import Renderer


map_config = {
    "width": 13,
    "height": 9,
    "agents": {
        "prep_cook": {"x": 1, "y": 4},
        "expediter": {"x": 8, "y": 6},
    },
    "stations": {
        "tomato_crate": {"x": 1, "y": 7},
        "protein_fridge": {"x": 1, "y": 3},
        "chop_board": {"x": 4, "y": 5},
        "north_pass": {"x": 4, "y": 7},
        "middle_pass": {"x": 4, "y": 3},
        "stove": {"x": 6, "y": 5},
        "plate_stack": {"x": 9, "y": 6},
        "lower_plate_pass": {"x": 6, "y": 3},
        "delivery_zone": {"x": 9, "y": 3},
        "window_fixture": {"x": 9, "y": 7},
        "upper_divider_table": {"x": 5, "y": 6},
        "lower_divider_table": {"x": 5, "y": 2},
    },
    "walls": [],
}


def manhattan_distance(a: Position_2D, b: Position_2D) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


class AutonomousKitchenAgentPolicy(Agent_Policy):
    def __init__(self, seed: int = 7):
        super().__init__()
        self.rng = random.Random(seed)

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        if not isinstance(observation, KitchenObservation):
            raise TypeError("AutonomousKitchenAgentPolicy expects KitchenObservation.")
        action_selection = choose_autonomous_action(observation.env_ref, self.entity, self.rng)
        action_selection.action_kwargs = {}
        return action_selection, {"policy": "autonomous_kitchen"}


class KitchenAgentState(Component):
    def __init__(self, chef_title: str):
        super().__init__()
        self.chef_title = chef_title
        self.held_item: str | None = None


class KitchenCommunicationPolicy(Communication_Policy):
    def __init__(self, role_name: str):
        super().__init__()
        self.role_name = role_name
        self.inbox: list[str] = []

    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        self.inbox = []

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        assert isinstance(env, OvercookedKitchenEnv)
        message = env.deliberation_message_for(self.entity, self.inbox)
        env.show_speech_bubble(self.entity.name, message)
        env.log_event(f"{self.entity.name}: {message}")
        return message

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        self.inbox.append(f"{sender.name}: {message}")

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass


class KitchenStation(Component):
    def __init__(self, station_type: str, dispenses: str | None = None):
        super().__init__()
        self.station_type = station_type
        self.dispenses = dispenses


class CounterStorage(Component):
    def __init__(self):
        super().__init__()
        self.stored_item: str | None = None


class SoupPot(Component):
    def __init__(self, recipe_name: str, required_ingredients: list[str], cook_duration: int = 2):
        super().__init__()
        self.recipe_name = recipe_name
        self.required_ingredients = required_ingredients
        self.cook_duration = cook_duration
        self.ingredients: list[str] = []
        self.cook_time_remaining: int | None = None
        self.ready_recipe: str | None = None

    def can_accept(self, item_name: str) -> bool:
        if self.ready_recipe is not None or self.cook_time_remaining is not None:
            return False

        next_ingredients = self.ingredients + [item_name]
        remaining = self.required_ingredients.copy()
        for ingredient in next_ingredients:
            if ingredient not in remaining:
                return False
            remaining.remove(ingredient)
        return len(self.ingredients) < len(self.required_ingredients)

    def add_ingredient(self, item_name: str) -> None:
        self.ingredients.append(item_name)
        if sorted(self.ingredients) == sorted(self.required_ingredients):
            self.cook_time_remaining = self.cook_duration

    def advance_cooking(self) -> bool:
        if self.cook_time_remaining is None:
            return False

        self.cook_time_remaining -= 1
        if self.cook_time_remaining <= 0:
            self.cook_time_remaining = None
            self.ready_recipe = self.recipe_name
            return True
        return False

    def reset(self) -> None:
        self.ingredients = []
        self.cook_time_remaining = None
        self.ready_recipe = None


class KitchenInteract(Action):
    RAW_TO_CHOPPED = {
        "tomato": "chopped_tomato",
        "protein": "chopped_protein",
    }

    def is_valid(
        self,
        actor: Entity,
        target_entity: Entity,
        env: Environment,
        kwargs: dict | None | str = "unconsidered",
    ) -> bool:
        agent_state = actor.get_component(KitchenAgentState)
        station = target_entity.get_component(KitchenStation)
        if agent_state is None or station is None:
            return False
        if actor is target_entity:
            return False
        if manhattan_distance(actor.position, target_entity.position) != 1:
            return False

        held_item = agent_state.held_item
        station_type = station.station_type
        if station_type == "source":
            return held_item is None and station.dispenses is not None
        if station_type == "board":
            return held_item in self.RAW_TO_CHOPPED
        if station_type == "pot":
            pot = target_entity.get_component(SoupPot)
            if pot is None:
                return False
            if held_item == "plate":
                return pot.ready_recipe is not None
            if held_item is None:
                return False
            return pot.can_accept(held_item)
        if station_type == "dish_source":
            return held_item is None
        if station_type == "waste":
            return held_item is not None
        if station_type == "serve":
            return held_item is not None and env.can_serve(held_item)
        if station_type == "counter":
            storage = target_entity.get_component(CounterStorage)
            if storage is None:
                return False
            return (held_item is None and storage.stored_item is not None) or (
                held_item is not None and storage.stored_item is None
            )
        return False

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert isinstance(env, OvercookedKitchenEnv)

        actor_state = actor.get_component(KitchenAgentState)
        station = target_entity.get_component(KitchenStation)
        assert actor_state is not None
        assert station is not None

        if station.station_type == "source":
            actor_state.held_item = station.dispenses
            env.log_event(f"{actor.name} grabs {station.dispenses.replace('_', ' ')} from {target_entity.name}.")
            return {"held_item": actor_state.held_item}

        if station.station_type == "board":
            chopped_item = self.RAW_TO_CHOPPED[actor_state.held_item]
            actor_state.held_item = chopped_item
            env.log_event(f"{actor.name} chops {chopped_item.replace('_', ' ')} at {target_entity.name}.")
            return {"held_item": actor_state.held_item}

        if station.station_type == "pot":
            pot = target_entity.get_component(SoupPot)
            assert pot is not None
            if actor_state.held_item == "plate" and pot.ready_recipe is not None:
                actor_state.held_item = pot.ready_recipe
                pot.reset()
                env.log_event(f"{actor.name} plates {actor_state.held_item.replace('_', ' ')}.")
                return {"held_item": actor_state.held_item}

            ingredient = actor_state.held_item
            pot.add_ingredient(ingredient)
            actor_state.held_item = None
            env.log_event(f"{actor.name} adds {ingredient.replace('_', ' ')} to {target_entity.name}.")
            if pot.cook_time_remaining is not None:
                env.log_event(f"{target_entity.name} starts bubbling.")
            return {"pot_ingredients": list(pot.ingredients)}

        if station.station_type == "dish_source":
            actor_state.held_item = "plate"
            env.log_event(f"{actor.name} picks up a plate.")
            return {"held_item": actor_state.held_item}

        if station.station_type == "waste":
            discarded_item = actor_state.held_item
            actor_state.held_item = None
            env.log_event(f"{actor.name} throws away {discarded_item.replace('_', ' ')}.")
            return {"discarded_item": discarded_item}

        if station.station_type == "serve":
            delivered_dish = actor_state.held_item
            if not env.can_serve(delivered_dish):
                env.log_event(f"{actor.name} cannot serve {delivered_dish.replace('_', ' ')}. It is not on the ticket.")
                return {"score_gained": 0}
            actor_state.held_item = None
            points = env.delivery_points(delivered_dish)
            env.score += points
            env.deliveries += 1
            env.step_score_delta += points
            env.deliveries_completed_this_step += 1
            env.order_queue.pop(0)
            env.log_event(f"{actor.name} serves {delivered_dish.replace('_', ' ')} for {points} points.")
            if env.order_queue:
                env.log_event(f"Next ticket up: {env.order_queue[0].replace('_', ' ')}.")
            else:
                env.log_event("All orders are out of the kitchen. Service complete.")
            return {"score_gained": points}

        if station.station_type == "counter":
            storage = target_entity.get_component(CounterStorage)
            assert storage is not None
            if actor_state.held_item is None:
                actor_state.held_item = storage.stored_item
                storage.stored_item = None
                env.log_event(f"{actor.name} picks up {actor_state.held_item} from {target_entity.name}.")
            else:
                storage.stored_item = actor_state.held_item
                env.log_event(f"{actor.name} places {actor_state.held_item} on {target_entity.name}.")
                actor_state.held_item = None
            return {"held_item": actor_state.held_item, "stored_item": storage.stored_item}

        return None

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Interact with {target_entity.name}."


@dataclass(slots=True)
class KitchenObservation(Observation):
    chef_name: str
    held_item: str | None
    score: int
    tick: int
    nearby_stations: list[str]
    recent_events: list[str]
    order_summary: str
    pot_status: str
    visible_counters: list[str]
    recipe_summary: str
    suggested_goal: str
    env_ref: "OvercookedKitchenEnv"

    def __str__(self) -> str:
        nearby = ", ".join(self.nearby_stations) if self.nearby_stations else "nothing useful nearby"
        held = self.held_item.replace("_", " ") if self.held_item else "empty hands"
        counters = ", ".join(self.visible_counters) if self.visible_counters else "no staged items"
        recent = " | ".join(self.recent_events) if self.recent_events else "no recent events"
        return (
            f"You are {self.chef_name}.\n"
            f"Current tick: {self.tick}. Score: {self.score}.\n"
            f"Orders to deliver: {self.order_summary}.\n"
            f"Recipe reminder: {self.recipe_summary}.\n"
            f"You are holding: {held}.\n"
            f"Pot status: {self.pot_status}.\n"
            f"Nearby stations you can move around or interact near: {nearby}.\n"
            f"Items currently staged on counters: {counters}.\n"
            f"Suggested immediate goal: {self.suggested_goal}.\n"
            f"Recent events: {recent}"
        )


def cooperative_kitchen_reward(action_selections: list[Action_Selection], env: Environment) -> list[float]:
    assert isinstance(env, OvercookedKitchenEnv)
    reward = float(env.step_score_delta)
    return [reward for _ in env.agents]


class KitchenLayoutAdapter(GridLayoutAdapter):
    def background(self, env: Environment) -> list[dict]:
        return env.background_tiles()


def _blocked_positions(env: Environment, actor: Entity) -> set[tuple[int, int]]:
    blocked: set[tuple[int, int]] = set()
    for entity in env.state.entities:
        if entity is actor or not entity.has_component(Collidable):
            continue
        position = entity.position
        if hasattr(position, "x") and hasattr(position, "y"):
            blocked.add((int(position.x), int(position.y)))
    return blocked


def _world_bounds(env: Environment) -> tuple[int, int, int, int]:
    if hasattr(env, "background_tiles"):
        background_tiles = env.background_tiles()
        xs = [int(item["x"]) for item in background_tiles]
        ys = [int(item["y"]) for item in background_tiles]
        return min(xs), max(xs), min(ys), max(ys)
    return 0, 12, 0, 8


def _station_storage_item(station: Entity) -> str | None:
    storage = station.get_component(CounterStorage)
    if storage is None:
        return None
    return storage.stored_item


def _pot_status_text(pot: SoupPot) -> str:
    if pot.ready_recipe is not None:
        return f"ready {pot.ready_recipe.replace('_', ' ')}"
    if pot.cook_time_remaining is not None:
        ingredients = ", ".join(item.replace("_", " ") for item in pot.ingredients) or "nothing"
        return f"cooking [{ingredients}] with {pot.cook_time_remaining} ticks remaining"
    if pot.ingredients:
        ingredients = ", ".join(item.replace("_", " ") for item in pot.ingredients)
        missing = ", ".join(item.replace("_", " ") for item in _pot_missing_items(pot)) or "nothing"
        return f"staged [{ingredients}], still needs [{missing}]"
    return "empty"


def _counter_snapshot(env: "OvercookedKitchenEnv") -> list[str]:
    snapshots: list[str] = []
    for entity in env.state.entities:
        storage = entity.get_component(CounterStorage)
        if storage is None or storage.stored_item is None:
            continue
        snapshots.append(f"{entity.name}: {storage.stored_item.replace('_', ' ')}")
    return snapshots


def _recipe_summary_text(pot: SoupPot) -> str:
    ingredient_names = [ingredient.replace("_", " ") for ingredient in pot.required_ingredients]
    return (
        f"To make {pot.recipe_name.replace('_', ' ')}, combine "
        f"{' and '.join(ingredient_names)}, let it cook, then plate and serve it."
    )


def _suggested_goal_text(env: "OvercookedKitchenEnv", agent: Entity, held_item: str | None, pot: SoupPot) -> str:
    if held_item == "garden_skillet":
        return "You already have the finished dish. Go to the delivery hatch and serve it."
    if held_item == "plate":
        if pot.ready_recipe is not None:
            return "The pot is ready. Take the plate to the stove and plate the dish."
        return "You are carrying a plate. Stay useful and be ready to plate the next finished dish."
    if held_item in {"chopped_tomato", "chopped_protein"}:
        return f"You have {held_item.replace('_', ' ')}. Bring it to the stove if the pot still needs it."
    if held_item in {"tomato", "protein"}:
        return f"You have raw {held_item}. Take it to the chopping board so it becomes usable."
    if pot.ready_recipe is not None:
        return "A dish is ready in the pot. Someone should get a plate and take it to the stove."

    needed_raw_item = _next_needed_raw_item(env, pot)
    if needed_raw_item == "tomato":
        return "The kitchen still needs tomato prep. Get a tomato, chop it, and stage or deliver it toward the stove."
    if needed_raw_item == "protein":
        return "The kitchen still needs protein prep. Get protein, chop it, and stage or deliver it toward the stove."
    if pot.cook_time_remaining is not None:
        return "The pot is already cooking. Stay in position for plating or service."
    return "Check the pass, the pot, and the current order, then move the next needed ingredient forward."


def _pot_missing_items(pot: SoupPot) -> list[str]:
    missing = list(pot.required_ingredients)
    for ingredient in pot.ingredients:
        if ingredient in missing:
            missing.remove(ingredient)
    return missing


def _recipe_progress_counts(env: "OvercookedKitchenEnv", pot: SoupPot) -> dict[str, int]:
    counts = {ingredient: 0 for ingredient in pot.required_ingredients}
    for ingredient in pot.ingredients:
        if ingredient in counts:
            counts[ingredient] += 1

    equivalents = {
        "tomato": "chopped_tomato",
        "chopped_tomato": "chopped_tomato",
        "protein": "chopped_protein",
        "chopped_protein": "chopped_protein",
    }

    for entity in env.state.entities:
        agent_state = entity.get_component(KitchenAgentState)
        if agent_state is not None and agent_state.held_item in equivalents:
            counts[equivalents[agent_state.held_item]] += 1

        storage = entity.get_component(CounterStorage)
        if storage is not None and storage.stored_item in equivalents:
            counts[equivalents[storage.stored_item]] += 1

    return counts


def _batch_target_count(env: "OvercookedKitchenEnv", pot: SoupPot) -> int:
    outstanding_orders = len(getattr(env, "order_queue", []))
    if outstanding_orders <= 0:
        return 0

    active_batch = 1 if (pot.ingredients or pot.cook_time_remaining is not None or pot.ready_recipe is not None) else 0
    staged_batch = 1 if outstanding_orders > active_batch else 0
    return min(outstanding_orders, active_batch + staged_batch)


def _next_needed_raw_item(env: "OvercookedKitchenEnv", pot: SoupPot) -> str | None:
    progress_counts = _recipe_progress_counts(env, pot)
    batch_target = _batch_target_count(env, pot)
    if batch_target <= 0:
        return None

    raw_by_prepped = {
        "chopped_tomato": "tomato",
        "chopped_protein": "protein",
    }
    deficits: list[tuple[int, str]] = []
    for ingredient in sorted(set(pot.required_ingredients)):
        required_total = pot.required_ingredients.count(ingredient) * batch_target
        current_total = progress_counts.get(ingredient, 0)
        if current_total < required_total:
            deficits.append((required_total - current_total, ingredient))

    if not deficits:
        return None

    _, ingredient = max(deficits, key=lambda item: (item[0], item[1]))
    return raw_by_prepped.get(ingredient)


def _adjacent_walkable_positions(env: Environment, actor: Entity, target: Entity) -> list[tuple[int, int]]:
    min_x, max_x, min_y, max_y = _world_bounds(env)
    blocked = _blocked_positions(env, actor)
    blocked.discard((int(target.position.x), int(target.position.y)))
    positions: list[tuple[int, int]] = []
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        x = int(target.position.x) + dx
        y = int(target.position.y) + dy
        if x < min_x or x > max_x or y < min_y or y > max_y:
            continue
        if (x, y) in blocked:
            continue
        positions.append((x, y))
    return positions


def _sort_targets_by_distance(actor: Entity, targets: list[Entity]) -> list[Entity]:
    return sorted(targets, key=lambda target: (manhattan_distance(actor.position, target.position), target.name))


def _path_step_toward(env: Environment, actor: Entity, destinations: list[tuple[int, int]]) -> str | None:
    if not destinations:
        return None

    start = (int(actor.position.x), int(actor.position.y))
    goal_set = set(destinations)
    if start in goal_set:
        return None

    min_x, max_x, min_y, max_y = _world_bounds(env)
    blocked = _blocked_positions(env, actor)
    frontier = [start]
    parents = {start: None}

    for current in frontier:
        if current in goal_set:
            break
        cx, cy = current
        for action_name, dx, dy in (
            ("Move_Left", -1, 0),
            ("Move_Right", 1, 0),
            ("Move_Down", 0, -1),
            ("Move_Up", 0, 1),
        ):
            nx = cx + dx
            ny = cy + dy
            next_position = (nx, ny)
            if nx < min_x or nx > max_x or ny < min_y or ny > max_y:
                continue
            if next_position in blocked or next_position in parents:
                continue
            parents[next_position] = (current, action_name)
            frontier.append(next_position)

    reachable_goals = [goal for goal in destinations if goal in parents]
    if not reachable_goals:
        return None

    best_goal = min(reachable_goals, key=lambda goal: len(_reconstruct_path(parents, goal)))
    path = _reconstruct_path(parents, best_goal)
    return None if not path else path[0]


def _reconstruct_path(
    parents: dict[tuple[int, int], tuple[tuple[int, int], str] | None],
    goal: tuple[int, int],
) -> list[str]:
    actions: list[str] = []
    current = goal
    while parents[current] is not None:
        previous, action_name = parents[current]
        actions.append(action_name)
        current = previous
    actions.reverse()
    return actions


def _select_move_toward(env: Environment, agent: Entity, destinations: list[tuple[int, int]]) -> Action_Selection | None:
    action_name = _path_step_toward(env, agent, destinations)
    if action_name is None:
        return None
    for selection in env.possible_actions(agent):
        if selection.action.__class__.__name__ == action_name:
            return selection
    return None


def _select_interaction(env: Environment, agent: Entity, target_name: str) -> Action_Selection | None:
    for selection in env.possible_actions(agent):
        if isinstance(selection.action, KitchenInteract) and selection.target_entity.name == target_name:
            return selection
    return None


def _select_do_nothing(env: Environment, agent: Entity) -> Action_Selection:
    for selection in env.possible_actions(agent):
        if isinstance(selection.action, Do_Nothing):
            return selection
    raise ValueError(f"Agent '{agent.name}' has no Do_Nothing action.")


def choose_autonomous_action(env: "OvercookedKitchenEnv", agent: Entity, rng: random.Random) -> Action_Selection:
    agent_state = agent.get_component(KitchenAgentState)
    if agent_state is None:
        raise ValueError(f"Agent '{agent.name}' is missing KitchenAgentState.")

    if len(env.agents) == 1 or agent.name == "Line Cook":
        return choose_single_player_action(env, agent, rng)

    held_item = agent_state.held_item
    is_prep_cook = agent.name == "Prep Cook"
    is_expediter = agent.name == "Expediter"
    stove = env.find_entity("Stove")
    pot = stove.get_component(SoupPot)
    assert pot is not None

    pass_counters = [
        env.find_entity("Upper Divider Table"),
        env.find_entity("Lower Divider Table"),
        env.find_entity("Middle Pass Counter"),
        env.find_entity("North Pass Counter"),
    ]

    if held_item == "garden_skillet":
        serve_action = _select_interaction(env, agent, "Delivery Hatch")
        if serve_action is not None:
            return serve_action
        move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, env.find_entity("Delivery Hatch")))
        return move_action or _select_do_nothing(env, agent)

    if held_item == "plate":
        plate_pot_action = _select_interaction(env, agent, "Stove")
        if plate_pot_action is not None:
            return plate_pot_action
        if pot.ready_recipe is not None:
            move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, stove))
            return move_action or _select_do_nothing(env, agent)
        if is_expediter:
            pass_targets = [env.find_entity("Lower Plate Pass"), *pass_counters]
            for target in pass_targets:
                if _station_storage_item(target) is None:
                    interact = _select_interaction(env, agent, target.name)
                    if interact is not None:
                        return interact
                    move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, target))
                    if move_action is not None:
                        return move_action

    if held_item in {"chopped_tomato", "chopped_protein"}:
        pot_action = _select_interaction(env, agent, "Stove")
        if pot_action is not None and pot.can_accept(held_item):
            return pot_action
        if is_prep_cook:
            for target in pass_counters:
                if _station_storage_item(target) is None:
                    interact = _select_interaction(env, agent, target.name)
                    if interact is not None:
                        return interact
                    move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, target))
                    if move_action is not None:
                        return move_action
        if is_expediter:
            move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, stove))
            if move_action is not None:
                return move_action

    if held_item in {"tomato", "protein"}:
        chop_action = _select_interaction(env, agent, "Chopping Board")
        if chop_action is not None:
            return chop_action
        move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, env.find_entity("Chopping Board")))
        return move_action or _select_do_nothing(env, agent)

    if is_expediter:
        for counter in _sort_targets_by_distance(agent, pass_counters):
            stored_item = _station_storage_item(counter)
            if stored_item in {"chopped_tomato", "chopped_protein"}:
                interact = _select_interaction(env, agent, counter.name)
                if interact is not None:
                    return interact
                move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, counter))
                if move_action is not None:
                    return move_action

        lower_plate_pass = env.find_entity("Lower Plate Pass")
        if _station_storage_item(lower_plate_pass) == "plate":
            interact = _select_interaction(env, agent, lower_plate_pass.name)
            if interact is not None:
                return interact
            move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, lower_plate_pass))
            if move_action is not None:
                return move_action

        if pot.ready_recipe is not None:
            plate_source = env.find_entity("Plate Stack")
            take_plate = _select_interaction(env, agent, plate_source.name)
            if take_plate is not None:
                return take_plate
            move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, plate_source))
            if move_action is not None:
                return move_action

    if is_prep_cook:
        next_raw_item = _next_needed_raw_item(env, pot)

        if next_raw_item is not None:
            source_name = "Tomato Counter" if next_raw_item == "tomato" else "Protein Fridge"
            source = env.find_entity(source_name)
            take_source = _select_interaction(env, agent, source.name)
            if take_source is not None:
                return take_source
            move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, source))
            if move_action is not None:
                return move_action

    if is_expediter:
        missing_items = _pot_missing_items(pot)
        if not missing_items and pot.ready_recipe is None:
            move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, stove))
            if move_action is not None:
                return move_action

    return _select_do_nothing(env, agent)


def choose_single_player_action(env: "OvercookedKitchenEnv", agent: Entity, rng: random.Random) -> Action_Selection:
    agent_state = agent.get_component(KitchenAgentState)
    if agent_state is None:
        raise ValueError(f"Agent '{agent.name}' is missing KitchenAgentState.")

    held_item = agent_state.held_item
    stove = env.find_entity("Stove")
    delivery_hatch = env.find_entity("Delivery Hatch")
    plate_source = env.find_entity("Plate Stack")
    chop_board = env.find_entity("Chopping Board")
    pot = stove.get_component(SoupPot)
    assert pot is not None

    if held_item == "garden_skillet":
        serve_action = _select_interaction(env, agent, delivery_hatch.name)
        if serve_action is not None:
            return serve_action
        move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, delivery_hatch))
        return move_action or _select_do_nothing(env, agent)

    if held_item == "plate":
        plate_pot_action = _select_interaction(env, agent, stove.name)
        if plate_pot_action is not None:
            return plate_pot_action
        move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, stove))
        return move_action or _select_do_nothing(env, agent)

    if held_item in {"chopped_tomato", "chopped_protein"}:
        pot_action = _select_interaction(env, agent, stove.name)
        if pot_action is not None and pot.can_accept(held_item):
            return pot_action
        move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, stove))
        return move_action or _select_do_nothing(env, agent)

    if held_item in {"tomato", "protein"}:
        chop_action = _select_interaction(env, agent, chop_board.name)
        if chop_action is not None:
            return chop_action
        move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, chop_board))
        return move_action or _select_do_nothing(env, agent)

    if pot.ready_recipe is not None:
        take_plate = _select_interaction(env, agent, plate_source.name)
        if take_plate is not None:
            return take_plate
        move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, plate_source))
        return move_action or _select_do_nothing(env, agent)

    next_raw_item = _next_needed_raw_item(env, pot)
    if next_raw_item is not None:
        source_name = "Tomato Counter" if next_raw_item == "tomato" else "Protein Fridge"
        source = env.find_entity(source_name)
        take_source = _select_interaction(env, agent, source.name)
        if take_source is not None:
            return take_source
        move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, source))
        return move_action or _select_do_nothing(env, agent)

    if pot.cook_time_remaining is not None:
        move_action = _select_move_toward(env, agent, _adjacent_walkable_positions(env, agent, stove))
        return move_action or _select_do_nothing(env, agent)

    return _select_do_nothing(env, agent)


class OvercookedKitchenEnv(Environment):
    FLOOR_SPRITE = "src/world_tiles/indoors/floors/day_brick_floor_c.png"
    WALL_SET = "src/world_tiles/indoors/wall_sets/overcooked_kitchen_wall"
    WALL_SPRITE = "src/world_tiles/indoors/wall_sets/overcooked_kitchen_wall/overcooked_kitchen_wall_center.png"
    COUNTER_SPRITE = "src/world_tiles/indoors/appliances/PokemonGen2/table_7.png"
    PASS_COUNTER_SPRITE = "src/world_tiles/indoors/appliances/PokemonGen2/table_6.png"
    SERVICE_COUNTER_SPRITE = "src/world_tiles/indoors/appliances/PokemonGen2/cabnet_00.png"
    FRIDGE_SPRITE = "src/world_tiles/indoors/appliances/PokemonGen2/fridge.png"
    PLATE_PASS_SPRITE = "src/world_tiles/indoors/appliances/PokemonGen2/cabnet_01.png"
    STOVE_SPRITE = "src/world_tiles/indoors/appliances/PokemonGen2/stove_00.png"
    CHOPPING_OVERLAY_SPRITE = "src/items/materials/misc/board_c.png"
    HATCH_OVERLAY_SPRITE = "src/world_tiles/indoors/architecture/window_center.png"
    POT_OVERLAY_SPRITE = "src/items/materials/misc/pot.png"
    WINDOW_SPRITE = "src/world_tiles/indoors/architecture/window_center.png"
    SPEECH_BUBBLE_SPRITE = "src/chat_interface/speech_bubble.png"
    ORDER_QUEUE = ["garden_skillet", "garden_skillet"]
    MAP_CONFIG = map_config
    ITEM_SPRITES = {
        "tomato": "src/items/consumables/vegetables/tomato_2.png",
        "chopped_tomato": "src/items/consumables/vegetables/tomato_2.png",
        "protein": "src/items/consumables/meat/steak_2.png",
        "chopped_protein": "src/items/consumables/meat/steak_2.png",
        "plate": "src/items/equipment/armor/mirror_plate.png",
        "garden_skillet": "src/items/materials/misc/dairy_pot.png",
    }
    READY_POT_SPRITE = "src/items/materials/misc/dairy_pot.png"

    def __init__(self, renderer: Renderer | None = None, episode_length: int = 60):
        self.episode_length = episode_length
        self.renderer_impl = renderer
        entities = self._create_entities()
        super().__init__(
            description="A sprite kitchen with a prep cook on the left, an expediter on the right, and a central pass between them.",
            entities=entities,
            movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
            reward_func=cooperative_kitchen_reward,
            entity_order=entity_definition_order,
        )

    def _wall_coords(self) -> set[tuple[int, int]]:
        width = int(self.MAP_CONFIG["width"])
        height = int(self.MAP_CONFIG["height"])
        wall_coords = {
            *((x, 0) for x in range(width)),
            *((x, height - 1) for x in range(width)),
            *((0, y) for y in range(height)),
            *((width - 1, y) for y in range(height)),
        }
        wall_coords.update({(5, 1), (5, 3), (5, 4), (5, 5), (5, 7)})
        wall_coords.update({(6, 7)})
        return wall_coords

    def _wall_set_for(self, x: int, y: int) -> str:
        return self.WALL_SET

    def _wall_entities(self) -> list[Entity]:
        wall_coords = self._wall_coords()
        return [
            Entity(
                name=f"Wall {x},{y}",
                position=Position_2D(x, y),
                tags=["blocker", "wall"],
                components=[
                    Collidable(collidable_tags=["blocker"]),
                    Renderable(sprite_path=self.WALL_SPRITE, visible=False),
                ],
            )
            for x, y in sorted(wall_coords)
        ]

    def _create_entities(self) -> list[Entity]:
        wall_coords = self._wall_coords()
        map_width = int(self.MAP_CONFIG["width"])
        map_height = int(self.MAP_CONFIG["height"])
        agents = self.MAP_CONFIG["agents"]
        stations = self.MAP_CONFIG["stations"]
        self.background_map = []
        self.station_entities_by_name = {}

        for y in range(map_height):
            for x in range(map_width):
                if (x, y) in wall_coords:
                    self.background_map.append(
                        {
                            "x": x,
                            "y": y,
                            "kind": "wall",
                            "color": (114, 88, 66),
                            "sprite": self.WALL_SPRITE,
                            "wall_set": self._wall_set_for(x, y),
                        }
                    )
                else:
                    self.background_map.append(
                        {
                            "x": x,
                            "y": y,
                            "kind": "floor",
                            "color": (160, 102, 52),
                            "sprite": self.FLOOR_SPRITE,
                        }
                    )

        tomato_crate = Entity(
            name="Tomato Counter",
            position=Position_2D(stations["tomato_crate"]["x"], stations["tomato_crate"]["y"]),
            tags=["blocker", "station", "source"],
            components=[
                KitchenStation(station_type="source", dispenses="tomato"),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.COUNTER_SPRITE,
                    z_index=4,
                    overlay_sprite=self.ITEM_SPRITES["tomato"],
                    overlay_mode="center",
                    overlay_scale=0.42,
                ),
            ],
        )
        north_pass = Entity(
            name="North Pass Counter",
            position=Position_2D(stations["north_pass"]["x"], stations["north_pass"]["y"]),
            tags=["blocker", "station", "counter"],
            components=[
                KitchenStation(station_type="counter"),
                CounterStorage(),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.PASS_COUNTER_SPRITE, z_index=4),
            ],
        )
        chop_board = Entity(
            name="Chopping Board",
            position=Position_2D(stations["chop_board"]["x"], stations["chop_board"]["y"]),
            tags=["blocker", "station", "board"],
            components=[
                KitchenStation(station_type="board"),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.PASS_COUNTER_SPRITE,
                    z_index=4,
                    overlay_sprite=self.CHOPPING_OVERLAY_SPRITE,
                    overlay_mode="center",
                    overlay_scale=0.56,
                ),
            ],
        )
        middle_pass = Entity(
            name="Middle Pass Counter",
            position=Position_2D(stations["middle_pass"]["x"], stations["middle_pass"]["y"]),
            tags=["blocker", "station", "counter"],
            components=[
                KitchenStation(station_type="counter"),
                CounterStorage(),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.PASS_COUNTER_SPRITE, z_index=4),
            ],
        )
        stove = Entity(
            name="Stove",
            position=Position_2D(stations["stove"]["x"], stations["stove"]["y"]),
            tags=["blocker", "station", "pot"],
            components=[
                KitchenStation(station_type="pot"),
                Collidable(collidable_tags=["blocker"]),
                SoupPot(
                    recipe_name="garden_skillet",
                    required_ingredients=["chopped_tomato", "chopped_protein"],
                    cook_duration=2,
                ),
                Renderable(sprite_path=self.STOVE_SPRITE,
                    z_index=4,
                    overlay_sprite=self.POT_OVERLAY_SPRITE,
                    overlay_mode="center",
                    overlay_scale=0.58,
                ),
            ],
        )
        plate_stack = Entity(
            name="Plate Stack",
            position=Position_2D(stations["plate_stack"]["x"], stations["plate_stack"]["y"]),
            tags=["blocker", "station", "dish_source"],
            components=[
                KitchenStation(station_type="dish_source"),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.COUNTER_SPRITE,
                    z_index=4,
                    overlay_sprite=self.ITEM_SPRITES["plate"],
                    overlay_mode="center",
                    overlay_scale=0.42,
                ),
            ],
        )
        lower_plate_pass = Entity(
            name="Lower Plate Pass",
            position=Position_2D(stations["lower_plate_pass"]["x"], stations["lower_plate_pass"]["y"]),
            tags=["blocker", "station", "counter"],
            components=[
                KitchenStation(station_type="counter"),
                CounterStorage(),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.PLATE_PASS_SPRITE,
                    z_index=4,
                    overlay_sprite=self.ITEM_SPRITES["plate"],
                    overlay_mode="center",
                    overlay_scale=0.42,
                ),
            ],
        )
        protein_fridge = Entity(
            name="Protein Fridge",
            position=Position_2D(stations["protein_fridge"]["x"], stations["protein_fridge"]["y"]),
            tags=["blocker", "station", "source"],
            components=[
                KitchenStation(station_type="source", dispenses="protein"),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.FRIDGE_SPRITE,
                    z_index=4,
                    overlay_sprite=self.ITEM_SPRITES["protein"],
                    overlay_mode="center",
                    overlay_scale=0.42,
                ),
            ],
        )
        delivery_zone = Entity(
            name="Delivery Hatch",
            position=Position_2D(stations["delivery_zone"]["x"], stations["delivery_zone"]["y"]),
            tags=["blocker", "station", "serve"],
            components=[
                KitchenStation(station_type="serve"),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.SERVICE_COUNTER_SPRITE,
                    z_index=4,
                    overlay_sprite=self.ITEM_SPRITES["plate"],
                    overlay_mode="center",
                    overlay_scale=0.54,
                ),
            ],
        )
        window_fixture = Entity(
            name="Kitchen Window",
            position=Position_2D(stations["window_fixture"]["x"], stations["window_fixture"]["y"]),
            tags=["fixture"],
            components=[
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.WINDOW_SPRITE,
                    z_index=5,
                ),
            ],
        )
        upper_divider_table = Entity(
            name="Upper Divider Table",
            position=Position_2D(stations["upper_divider_table"]["x"], stations["upper_divider_table"]["y"]),
            tags=["blocker", "station", "counter"],
            components=[
                KitchenStation(station_type="counter"),
                CounterStorage(),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.PASS_COUNTER_SPRITE,
                    z_index=4,
                ),
            ],
        )
        lower_divider_table = Entity(
            name="Lower Divider Table",
            position=Position_2D(stations["lower_divider_table"]["x"], stations["lower_divider_table"]["y"]),
            tags=["blocker", "station", "counter"],
            components=[
                KitchenStation(station_type="counter"),
                CounterStorage(),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path=self.PASS_COUNTER_SPRITE,
                    z_index=4,
                ),
            ],
        )

        prep_cook = Entity(
            name="Prep Cook",
            position=Position_2D(agents["prep_cook"]["x"], agents["prep_cook"]["y"]),
            tags=["agent", "chef"],
            actions=[Move_Left(), Move_Right(), Move_Up(), Move_Down(), KitchenInteract(), Do_Nothing()],
            components=[
                AutonomousKitchenAgentPolicy(seed=11),
                KitchenCommunicationPolicy(role_name="prep"),
                KitchenAgentState(chef_title="Prep Cook"),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/characters/humanoids/human/farmer_man.png", z_index=10),
            ],
        )
        expediter = Entity(
            name="Expediter",
            position=Position_2D(agents["expediter"]["x"], agents["expediter"]["y"]),
            tags=["agent", "chef"],
            actions=[Move_Left(), Move_Right(), Move_Up(), Move_Down(), KitchenInteract(), Do_Nothing()],
            components=[
                AutonomousKitchenAgentPolicy(seed=29),
                KitchenCommunicationPolicy(role_name="expediter"),
                KitchenAgentState(chef_title="Expediter"),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/characters/humanoids/dwarven/gnome_wizard.png", z_index=10),
            ],
        )

        stations = [
            tomato_crate,
            north_pass,
            chop_board,
            stove,
            plate_stack,
            protein_fridge,
            middle_pass,
            lower_plate_pass,
            delivery_zone,
            upper_divider_table,
            lower_divider_table,
        ]
        fixtures = [
            window_fixture,
        ]
        self.station_entities_by_name = {entity.name: entity for entity in stations}

        return [
            *self._wall_entities(),
            *stations,
            *fixtures,
            prep_cook,
            expediter,
        ]

    def _reset(self, seed=None) -> None:
        self.state = Environment_State(self._create_entities())
        self.tick = 0
        self.score = 0
        self.deliveries = 0
        self.step_score_delta = 0
        self.deliveries_completed_this_step = 0
        self.order_queue = list(self.ORDER_QUEUE)
        self.draw_grid_overlay = False
        self.speech_bubble_sprite = self.SPEECH_BUBBLE_SPRITE
        self.speech_bubbles: list[dict[str, object]] = []
        self.event_log = [
            "Goal: cook Garden Skillet, plate it, and deliver it through the pink service hatch.",
            "Recipe: 1 chopped tomato plus 1 chopped protein into the stove.",
            "Prep cook works the left side; expediter works the right side and the center pass.",
        ]
        self._sync_renderables()

    def render(self) -> None:
        if self.renderer_impl is None:
            raise NotImplementedError("This environment does not have a renderer attached.")
        self.renderer_impl.render(self)

    def background_tiles(self) -> list[dict]:
        return list(self.background_map)

    def find_entity(self, entity_name: str) -> Entity:
        for entity in self.state.entities:
            if entity.name == entity_name:
                return entity
        raise ValueError(f"Unknown entity: {entity_name}")

    def log_event(self, message: str) -> None:
        self.event_log.append(message)
        self.event_log = self.event_log[-12:]

    def show_speech_bubble(self, entity_name: str, text: str, ttl: int = 2) -> None:
        self.speech_bubbles = [bubble for bubble in self.speech_bubbles if bubble["entity_name"] != entity_name]
        self.speech_bubbles.append({"entity_name": entity_name, "text": text, "ttl": ttl})

    def _decay_speech_bubbles(self) -> None:
        next_bubbles: list[dict[str, object]] = []
        for bubble in self.speech_bubbles:
            ttl = int(bubble.get("ttl", 0)) - 1
            if ttl > 0:
                next_bubbles.append({**bubble, "ttl": ttl})
        self.speech_bubbles = next_bubbles

    def deliberation_message_for(self, agent: Entity, inbox: list[str]) -> str:
        agent_state = agent.get_component(KitchenAgentState)
        held_item = None if agent_state is None else agent_state.held_item
        stove = self.find_entity("Stove")
        pot = stove.get_component(SoupPot)
        assert pot is not None

        if agent.name == "Prep Cook":
            progress_counts = _recipe_progress_counts(self, pot)
            if held_item == "tomato":
                return "Heading to the board with tomato."
            if held_item == "protein":
                return "Protein is going to the board."
            if held_item in {"chopped_tomato", "chopped_protein"}:
                return f"Passing {held_item.replace('_', ' ')} to the middle."
            if progress_counts.get("chopped_tomato", 0) < pot.required_ingredients.count("chopped_tomato"):
                return "I'll prep tomato next."
            if progress_counts.get("chopped_protein", 0) < pot.required_ingredients.count("chopped_protein"):
                return "I'll prep protein next."
            return "Pass is stocked. Waiting for the next call."

        if held_item == "garden_skillet":
            return "Skillet ready. Serving now."
        if held_item == "plate":
            return "Plate in hand. Going to the stove."
        if held_item in {"chopped_tomato", "chopped_protein"}:
            return f"I've got {held_item.replace('_', ' ')} for the stove."
        if pot.ready_recipe is not None:
            return "Dish is ready. I need a plate."
        if pot.cook_time_remaining is not None:
            return "Stove is working. I'll watch the pass."
        for counter_name in ("Upper Divider Table", "Lower Divider Table", "Middle Pass Counter", "North Pass Counter"):
            stored_item = _station_storage_item(self.find_entity(counter_name))
            if stored_item in {"chopped_tomato", "chopped_protein"}:
                return f"Copy that. Clearing {counter_name.lower()}."
        return "I'll cover stove, plates, and service."

    def can_serve(self, dish_name: str | None) -> bool:
        return dish_name is not None and bool(self.order_queue) and self.order_queue[0] == dish_name

    def order_summary(self) -> str:
        if not self.order_queue:
            return "Orders complete"
        remaining: dict[str, int] = {}
        for order in self.order_queue:
            remaining[order] = remaining.get(order, 0) + 1
        return " | ".join(f"{name.replace('_', ' ').title()} x{count}" for name, count in remaining.items())

    def delivery_points(self, dish_name: str) -> int:
        time_bonus = 6 if self.tick <= 26 else 3 if self.tick <= 34 else 0
        recipe_bonus = 18 if dish_name == "garden_skillet" else 10
        return recipe_bonus + time_bonus

    def _pot_entities(self) -> list[Entity]:
        return [entity for entity in self.state.entities if entity.get_component(SoupPot) is not None]

    def _item_sprite(self, item_name: str | None) -> str | None:
        if item_name is None:
            return None
        return self.ITEM_SPRITES.get(item_name, item_name)

    def _station_overlay_sprite(self, station_type: str, dispenses: str | None) -> str | None:
        if station_type == "board":
            return self.CHOPPING_OVERLAY_SPRITE
        if station_type == "pot":
            return self.POT_OVERLAY_SPRITE
        if station_type == "dish_source":
            return self.ITEM_SPRITES["plate"]
        if station_type == "serve":
            return self.ITEM_SPRITES["plate"]
        return self._item_sprite(dispenses)

    def _sync_renderables(self) -> None:
        for entity in self.state.entities:
            renderable = entity.get_component(Renderable)
            if renderable is None:
                continue

            agent_state = entity.get_component(KitchenAgentState)
            if agent_state is not None:
                renderable.overlay_sprite = self._item_sprite(agent_state.held_item)
                renderable.overlay_mode = "badge"
                renderable.overlay_scale = 0.42
                continue

            station = entity.get_component(KitchenStation)
            if station is None:
                continue

            if station.station_type == "pot":
                pot = entity.get_component(SoupPot)
                assert pot is not None
                renderable.sprite_path = self.STOVE_SPRITE
                renderable.overlay_mode = "center"
                renderable.overlay_scale = 0.58
                renderable.overlay_sprite = self.READY_POT_SPRITE if pot.ready_recipe is not None else self.POT_OVERLAY_SPRITE
                continue

            if station.station_type == "counter":
                storage = entity.get_component(CounterStorage)
                stored_item = None if storage is None else storage.stored_item
                renderable.overlay_sprite = self._item_sprite(stored_item)
                renderable.overlay_mode = "center"
                renderable.overlay_scale = 0.42
                continue

            if station.station_type == "source" and entity.name == "Protein Fridge":
                renderable.sprite_path = self.FRIDGE_SPRITE
            elif station.station_type == "serve":
                renderable.sprite_path = self.SERVICE_COUNTER_SPRITE
            elif station.station_type == "dish_source" and entity.name == "Lower Plate Pass":
                renderable.sprite_path = self.PLATE_PASS_SPRITE
            else:
                renderable.sprite_path = self.COUNTER_SPRITE

            renderable.overlay_sprite = self._station_overlay_sprite(station.station_type, station.dispenses)
            renderable.overlay_mode = "center"
            renderable.overlay_scale = 0.54 if station.station_type == "serve" else 0.56 if station.station_type == "board" else 0.42

    def _update_dynamic_visuals(self) -> None:
        self._sync_renderables()

    def observe(self, agent_id: int) -> Observation:
        agent = self.agents[agent_id]
        agent_state = agent.get_component(KitchenAgentState)
        nearby_stations = [
            entity.name
            for entity in self.state.entities
            if entity is not agent
            and entity.get_component(KitchenStation) is not None
            and manhattan_distance(agent.position, entity.position) == 1
        ]
        return KitchenObservation(
            possible_actions=self.possible_actions(agent),
            chef_name=agent.name,
            held_item=None if agent_state is None else agent_state.held_item,
            score=self.score,
            tick=self.tick,
            nearby_stations=nearby_stations,
            recent_events=self.event_log[-3:],
            order_summary=self.order_summary(),
            pot_status=_pot_status_text(self.find_entity("Stove").get_component(SoupPot)),
            visible_counters=_counter_snapshot(self),
            recipe_summary=_recipe_summary_text(self.find_entity("Stove").get_component(SoupPot)),
            suggested_goal=_suggested_goal_text(
                self,
                agent,
                None if agent_state is None else agent_state.held_item,
                self.find_entity("Stove").get_component(SoupPot),
            ),
            env_ref=self,
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]) -> None:
        self.tick += 1
        self.step_score_delta = 0
        self.deliveries_completed_this_step = 0
        sim_simple_conversation(self.agents, self, conversation_duration=1)

    def environment_end_of_step(self, action_selections: list[Action_Selection]) -> None:
        for entity in self._pot_entities():
            pot = entity.get_component(SoupPot)
            assert pot is not None
            if pot.advance_cooking():
                self.log_event(f"{entity.name} finishes cooking. The skillet is ready to plate.")

        self._update_dynamic_visuals()
        self._decay_speech_bubbles()

        if not self.order_queue:
            self.terminations = [True] * len(self.agents)

        if self.tick >= self.episode_length:
            self.truncations = [True] * len(self.agents)
            self.log_event("The dinner rush winds down and the kitchen closes.")

def select_policy_actions(env: OvercookedKitchenEnv) -> list[Action_Selection]:
    selections: list[Action_Selection] = []
    for agent_id, agent in enumerate(env.agents):
        policy = agent.get_component(Agent_Policy)
        if policy is None:
            raise ValueError(f"Agent '{agent.name}' is missing an Agent_Policy component.")
        selection, _ = policy.select_action(env.observe(agent_id))
        selections.append(selection)
    return selections


class SinglePlayerOvercookedEnv(OvercookedKitchenEnv):
    ORDER_QUEUE = ["garden_skillet", "garden_skillet"]

    def __init__(self, renderer: Renderer | None = None, episode_length: int = 96):
        super().__init__(renderer=renderer, episode_length=episode_length)
        self.description = (
            "A single-player overcooked kitchen where one line cook handles prep, stove work, plating, and service."
        )

    def _wall_coords(self) -> set[tuple[int, int]]:
        wall_coords = super()._wall_coords()
        wall_coords.difference_update({(5, 3), (5, 4), (5, 5)})
        return wall_coords

    def _create_entities(self) -> list[Entity]:
        entities = super()._create_entities()
        filtered: list[Entity] = []
        for entity in entities:
            if entity.name == "Expediter":
                continue
            if entity.name == "Prep Cook":
                entity.name = "Line Cook"
                entity.position = Position_2D(3, 4)
                policy = entity.get_component(AutonomousKitchenAgentPolicy)
                if policy is not None:
                    policy.rng = random.Random(41)
                agent_state = entity.get_component(KitchenAgentState)
                if agent_state is not None:
                    agent_state.chef_title = "Line Cook"
                comms = entity.get_component(KitchenCommunicationPolicy)
                if comms is not None:
                    comms.role_name = "line_cook"
            filtered.append(entity)
        return filtered

    def _reset(self, seed=None) -> None:
        super()._reset(seed=seed)
        self.event_log = [
            "Goal: one chef must prep, cook, plate, and serve two garden skillets before closing.",
            "Tip: stage ingredients early, watch the stove, and keep plates moving.",
            "The divider is opened up so the line cook can cross the whole kitchen.",
        ]
