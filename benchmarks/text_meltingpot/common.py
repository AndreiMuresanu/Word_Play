"""Common components, actions, and utilities for Melting Pot environments."""

from __future__ import annotations

# Core
from copy import deepcopy
from pathlib import Path
from typing import Callable

from word_play.core import Component, Action, Entity, Environment
from word_play.core.actions import Action_Selection
from word_play.utils.tilemap import find_char_positions

# Movement
from word_play.presets.movement import Move_Down, Move_Left, Move_Right, Move_Up
from word_play.presets.movement.common import Collidable
from word_play.presets.movement.simple_2d_grid import Position_2D

# Actions
from word_play.presets.action_validations import (
    Target_Has_Component,
    Target_Is_Nearby,
    Target_Not_Self,
    Target_Is_Self,
)

# Systems
from word_play.presets.systems import Inventory, Do_Nothing, Preference
from word_play.presets.systems.cooldown import Cooldown, Action_On_Cooldown
from word_play.presets.systems.crafter import Collect_From_Crafter
from word_play.presets.systems.freezable import Freezable, Freeze
from word_play.presets.systems.inventory import materialize_item
from word_play.presets.systems.health import Health
from word_play.presets.systems.communication.trade_communication.trade_actions import Start_Trade
from word_play.presets.systems.regrowable import Regrowable, Consume_Regrowable, Harvest_Regrowable

# Renderers
from word_play.presets.renderers import Renderable, render_step

# Environment
from word_play.presets.environments.simple_env_reset_mixin import Simple_Env_Reset_Mixin
from word_play.presets.entity_orderings import entity_definition_order

# Policies
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.action_policies.random_policy import Random_Policy

# Models
from word_play.presets.models import LLM_MODEL_REGISTRY, OpenRouter_Model

# ============================================================================
# Standard Movement
# ============================================================================

STANDARD_MOVEMENT = [Move_Left(), Move_Right(), Move_Up(), Move_Down()]


# ============================================================================
# Policy Factory
# ============================================================================

def make_llm_policy(system_prompt: str = "", model_key: str = "default"):
    """Create an LLM policy for an agent.

    Args:
        system_prompt: Custom system prompt for the agent
        model_key: Model key (default works with run_exp's default model registration)
    """
    return LLM_Action_And_Communication_Policy(
        model_key=model_key,
        system_prompt=system_prompt,
        use_chain_of_thought=True,
        observation_memory_window=4,
        conversation_memory_window=8,
    )

# ============================================================================
# Components: Berry (Allelopathic Harvest)
# ============================================================================



class Berry(Component):
    """A berry that can be unripe or ripe, and has a color."""
    def __init__(self, color_id: int, ripe: bool = False):
        super().__init__()
        self.color_id = color_id
        self.ripe = ripe
        self.growth = 0.0

    def ripen(self) -> bool:
        self.growth += 1
        if self.growth >= 10:
            self.ripe = True
        return self.ripe

    def pre_actions_step(self, env) -> None:
        if self.ripe:
            return
        berry_counts = [0, 0, 0]
        for entity in env.state.entities:
            berry = entity.get_component(Berry)
            if berry:
                berry_counts[berry.color_id] += 1
        total = max(sum(berry_counts), 1)
        prop = berry_counts[self.color_id] / total
        if env.tick % max(1, int(10 * (1 - prop))) == 0:
            self.ripen()


class Taste(Component):
    """Player's taste preference for berry colors."""
    def __init__(self, preferred_color: int, reward_preferred: int = 2, reward_other: int = 1):
        super().__init__()
        self.preferred_color = preferred_color
        self.reward_preferred = reward_preferred
        self.reward_other = reward_other


class ZapMarking(Component):
    """Graduated sanctions marking: tracks zap-hit level on a player.

    Level 1: freeze (delegates to Freezable component).
    Level 2: -10 reward + eliminate (delegates to Freezable component).
    Recovery clears marking back to 0 after recoveryTime ticks.
    """
    def __init__(self, freeze_duration: int = 25, penalty: float = -10.0, recovery_time: int = 50):
        super().__init__()
        self.mark_level = 0
        self.freeze_duration = freeze_duration
        self.penalty = penalty
        self.recovery_time = recovery_time
        self.recovery_counter = 0

    def zap_hit(self, env) -> dict:
        freezable = self.entity.get_component(Freezable) if hasattr(self, 'entity') else None
        if self.mark_level == 0:
            self.mark_level = 1
            if freezable is not None:
                freezable.freeze(duration=self.freeze_duration)
            return {"level": 1, "effect": "freeze", "duration": self.freeze_duration}
        else:
            self.mark_level = 2
            if freezable is not None:
                freezable.eliminate()
            _award_step_reward(env, self.entity, self.penalty)
            return {"level": 2, "effect": "remove", "penalty": self.penalty}

    def post_actions_step(self, env) -> None:
        if self.mark_level > 0:
            self.recovery_counter += 1
            if self.recovery_counter >= self.recovery_time:
                self.mark_level = 0
                self.recovery_counter = 0


class Zap_Player(Action):
    """FIRE_ZAP: zap a nearby player with graduated sanctions.

    Cooldown is managed by the actor's Cooldown component (key="zap").
    First hit freezes target for 25 frames; second hit within recovery
    gives -10 reward and removes them.
    """
    def __init__(self):
        super().__init__(validation_rules=[
            Action_On_Cooldown("zap"),
            Target_Is_Nearby(),
            Target_Not_Self(),
            Target_Has_Component(ZapMarking),
        ])

    def exec_action(self, actor, target, env, kwargs=None):
        marking = target.get_component(ZapMarking)
        if marking is None:
            return {"success": False, "reason": "no_marking"}
        cooldown = actor.get_component(Cooldown)
        if cooldown is not None:
            cooldown.start("zap")
        result = marking.zap_hit(env)
        return {"success": True, "zapped": target.name, **result}

    def action_description_text(self, actor, target, env):
        return f"Zap {target.name}."


class Harvest_Berry(Action):
    """Harvest a nearby ripe berry into inventory."""

    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Nearby(), Target_Has_Component(Berry)])

    def exec_action(self, actor, target, env, kwargs=None):
        if target not in env.state.entities:
            return {"success": False, "reason": "missing_target"}
        berry = target.get_component(Berry)
        if not berry or not berry.ripe:
            return {"success": False, "reason": "not_ripe"}
        inventory = actor.get_component(Inventory)
        if inventory is None:
            return {"success": False, "reason": "no_inventory"}
        preference = actor.get_component(Preference)
        reward = preference.reward_for(target) if preference else 1.0
        _award_step_reward(env, actor, reward)
        berry_item = make_berry_item(berry.color_id)
        if not inventory.store(berry_item, env):
            return {"success": False, "reason": "inventory_full"}
        env.destroy_entity(target)
        return {"success": True, "harvested": berry_item.name, "reward": reward}

    def action_description_text(self, actor, target, env):
        return "Harvest a ripe berry."


# ============================================================================
# Components: Common Components
# ============================================================================

from word_play.presets.systems.health import Health


class MushroomEffect(Component):
    """Shared externality payoff for mushroom collection."""

    def __init__(self, self_reward: float, others_reward: float = 0.0):
        super().__init__()
        self.self_reward = self_reward
        self.others_reward = others_reward
        self.collected = False

    def collect(self) -> bool:
        if self.collected:
            return False
        self.collected = True
        return True


class Public_Resource(Component):
    """Resource that accumulates/depletes globally (clean_up)."""
    def __init__(self, resource_name: str, initial_level: float = 0.0, accumulation_rate: float = 1.0, max_level: float = 100.0, dirty_threshold: float = 0.4):
        super().__init__()
        self.resource_name = resource_name
        self.level = initial_level
        self.accumulation_rate = accumulation_rate
        self.max_level = max_level
        self.dirty_threshold = dirty_threshold

    def post_actions_step(self, env: Environment) -> None:
        self.level = min(self.max_level, self.level + self.accumulation_rate)

    def clean(self, amount: float) -> float:
        cleaned = min(self.level, amount)
        self.level -= cleaned
        return cleaned

    @property
    def is_dirty(self) -> bool:
        return self.level > self.max_level * self.dirty_threshold


class PunishmentTile(Component):
    """Marker component for partnership punishment tiles."""

    def __init__(self, penalty: float = -10.0):
        super().__init__()
        self.penalty = penalty


class Coin(Component):
    """A collectable coin with a value."""
    def __init__(self, value: int = 1, coin_type: str = "red", regrow_tick_interval: int = 60):
        super().__init__()
        self.value = value
        self.coin_type = coin_type
        self.collected = False
        self.regrow_tick_interval = regrow_tick_interval

    def pre_actions_step(self, env) -> None:
        if not self.collected:
            return
        if env.tick % self.regrow_tick_interval == 0:
            self.collected = False
            renderable = self.entity.get_component(Renderable) if hasattr(self, "entity") else None
            if renderable is not None:
                renderable.visible = True


class CoinPreference(Component):
    """Preference for one coin type in the two-player coins game."""

    def __init__(self, preferred_type: str, mismatch_penalty: float = -2.0):
        super().__init__()
        self.preferred_type = preferred_type
        self.mismatch_penalty = mismatch_penalty


class GoldVein(Component):
    """A gold vein that miners can extract from cooperatively."""
    def __init__(self, max_gold: int = 100, ore_type: str = "iron"):
        super().__init__()
        self.gold_remaining = max_gold
        self.ore_type = ore_type

    def mine(self, team_size: int = 1) -> tuple[int, float]:
        if self.gold_remaining <= 0:
            return 0, 0.0
        if self.ore_type == "gold":
            if team_size < 2:
                return 0, 0.0
            mined = min(self.gold_remaining, 2)
            self.gold_remaining -= mined
            return mined, 8.0
        mined = min(self.gold_remaining, 1)
        self.gold_remaining -= mined
        return mined, 1.0


class Baby(Component):
    """A baby that needs care."""
    def __init__(self, needs_food: bool = False, needs_sleep: bool = False, hunger_interval: int = 200):
        super().__init__()
        self.happiness = 50
        self.needs_food = needs_food
        self.needs_sleep = needs_sleep
        self.hunger_interval = hunger_interval
        self.last_fed_tick = 0

    def feed(self, current_tick: int) -> float:
        self.needs_food = False
        self.last_fed_tick = current_tick
        old = self.happiness
        self.happiness = min(100, self.happiness + 20)
        return float(self.happiness - old)

    def post_actions_step(self, env) -> None:
        if env.tick - self.last_fed_tick >= self.hunger_interval:
            self.needs_food = True
        if self.needs_food and env.tick % 25 == 0:
            self.happiness = max(0, self.happiness - 1)


class BoatRower(Component):
    """Tracks rowing state for boat_race agents."""
    def __init__(self):
        super().__init__()
        self.paddling = False
        self.row_count = 0
        self.last_side = None

    def pre_actions_step(self, env) -> None:
        self.paddling = False
        self.last_side = None


class Dirt(Component):
    """Single cleanable dirt tile for clean_up."""

    def __init__(self, active: bool = True):
        super().__init__()
        self.active = active

    def clean(self) -> bool:
        if not self.active:
            return False
        self.active = False
        renderable = self.entity.get_component(Renderable) if hasattr(self, "entity") else None
        if renderable is not None:
            renderable.visible = False
        return True


class Flag(Component):
    """A flag that can be captured in CTF."""
    def __init__(self, team: str):
        super().__init__()
        self.team = team
        self.captured = False
        self.carrier = None


class HillZone(Component):
    """The central hill that teams fight to control."""
    def __init__(self):
        super().__init__()
        self.controlling_team = None


class Molecule(Component):
    """A chemical molecule that can participate in reactions."""
    def __init__(self, molecule_type: str, color: tuple = (100, 100, 100, 255)):
        super().__init__()
        self.molecule_type = molecule_type
        self.color = color


class AutocatalyticReactor(Component):
    """Runs autocatalytic cycle reactions and spawns molecules each step."""
    def __init__(self, cycle_rules=None, spawn_interval=20, spawn_prob=0.3, spawn_types=None, grid_w=24, grid_h=14):
        super().__init__()
        self.cycle_rules = cycle_rules or []
        self.spawn_interval = spawn_interval
        self.spawn_prob = spawn_prob
        self.spawn_types = spawn_types or []
        self.grid_w = grid_w
        self.grid_h = grid_h

    def pre_actions_step(self, env) -> None:
        import random
        for entity in env.state.entities[:]:
            mol = entity.get_component(Molecule)
            if not mol or not entity.has_tag("map_item"):
                continue
            nearby = [e for e in env.state.entities
                      if e.get_component(Molecule) and e.has_tag("map_item")
                      and 0 < abs(entity.position.x - e.position.x) + abs(entity.position.y - e.position.y) <= 1]
            for reactant_a, reactant_b, product_type, prob in self.cycle_rules:
                if mol.molecule_type == reactant_a:
                    for other in nearby:
                        other_mol = other.get_component(Molecule)
                        if other_mol and other_mol.molecule_type == reactant_b:
                            if random.random() < prob:
                                self._transform(env, entity, other, product_type)
                            break
            if mol.molecule_type == "x":
                for other in nearby:
                    other_mol = other.get_component(Molecule)
                    if other_mol and other_mol.molecule_type == "y":
                        if random.random() < 0.1:
                            self._convert_to_energy(env, entity, other)
                        break

        if env.tick % self.spawn_interval == 0 and random.random() < self.spawn_prob and self.spawn_types:
            map_mols = getattr(env, 'map_molecules', {})
            empty = [(x, y) for x in range(self.grid_w) for y in range(self.grid_h)
                     if (x, y) not in map_mols]
            if empty:
                pos = random.choice(empty)
                mol_type = random.choice(self.spawn_types)
                e = env._create_map_molecule(f"Spawned_{mol_type}_{env.tick}", mol_type, pos)
                env.state.entities.append(e)
                map_mols[pos] = e

    def _transform(self, env, mol1, mol2, product_type):
        mid = ((mol1.position.x + mol2.position.x)//2, (mol1.position.y + mol2.position.y)//2)
        map_mols = getattr(env, 'map_molecules', {})
        for m in [mol1, mol2]:
            map_mols.pop((m.position.x, m.position.y), None)
            if m in env.state.entities:
                env.state.entities.remove(m)
        product = env._create_map_molecule(f"Product_{env.tick}_{product_type}", product_type, mid)
        env.state.entities.append(product)
        map_mols[mid] = product

    def _convert_to_energy(self, env, x_mol, y_mol):
        mid = ((x_mol.position.x + y_mol.position.x)//2, (x_mol.position.y + y_mol.position.y)//2)
        map_mols = getattr(env, 'map_molecules', {})
        for m in [x_mol, y_mol]:
            map_mols.pop((m.position.x, m.position.y), None)
            if m in env.state.entities:
                env.state.entities.remove(m)
        energy = env._create_energy(mid)
        env.state.entities.append(energy)
        map_mols[mid] = energy


class AgentMolecule(Component):
    """Tracks what molecule an agent is currently holding."""
    def __init__(self):
        super().__init__()
        self.held_molecule = None

    def pickup(self, molecule_type: str) -> bool:
        if self.held_molecule is None:
            self.held_molecule = molecule_type
            return True
        return False

    def drop(self) -> str:
        mol = self.held_molecule
        self.held_molecule = None
        return mol

    def has_molecule(self) -> bool:
        return self.held_molecule is not None


class Pickup_Molecule(Action):
    """Pick up a nearby molecule."""

    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Nearby()])

    def exec_action(self, actor, target, env, kwargs=None):
        if target not in env.state.entities:
            return {"success": False, "reason": "missing_target"}
        agent_mol = actor.get_component(AgentMolecule)
        mol = target.get_component(Molecule)
        if not mol:
            return {"success": False, "reason": "not_molecule"}
        if not agent_mol or agent_mol.has_molecule():
            return {"success": False, "reason": "already_holding"}
        if agent_mol.pickup(mol.molecule_type):
            env.destroy_entity(target)
            return {"success": True, "picked_up": mol.molecule_type}
        return {"success": False}

    def action_description_text(self, actor, target, env):
        return "Pick up a nearby molecule."


class Drop_Molecule(Action):
    """Drop the molecule being carried."""

    def __init__(self):
        super().__init__()

    def exec_action(self, actor, target, env, kwargs=None):
        agent_mol = actor.get_component(AgentMolecule)
        if not agent_mol or not agent_mol.has_molecule():
            return {"success": False, "reason": "nothing_held"}
        mol_type = agent_mol.drop()
        mol_entity = Entity(
            name=f"Molecule_{mol_type}_dropped",
            position=actor.position,
            tags=["molecule", mol_type],
            components=[
                Molecule(mol_type),
                Renderable(sprite_path="src/items/crafting/vials/vial_blue.png", z_index=2),
            ],
        )
        env.instantiate_entity(mol_entity)
        return {"success": True, "dropped": mol_type}

    def action_description_text(self, actor, target, env):
        return "Drop the held molecule."


def cooking_team_reward(action_selections, env):
    return list(getattr(env, "last_step_rewards", [0.0] * len(env.agents)))


def step_reward_env(action_selections, env):
    rewards = getattr(env, "last_step_rewards", None)
    if rewards is None:
        return [0.0] * len(env.agents)
    if len(rewards) < len(env.agents):
        return list(rewards) + [0.0] * (len(env.agents) - len(rewards))
    return list(rewards[: len(env.agents)])


def resolve_chemistry_cycles(env, *, required_cycle_count: int = 2) -> None:
    """Consume completed chemistry cycles and award all chemists shared energy."""

    molecule_entities: dict[str, list[Entity]] = {}
    for entity in list(env.state.entities):
        mol = entity.get_component(Molecule)
        if mol is None or "map_item" not in getattr(entity, "tags", []):
            continue
        molecule_entities.setdefault(mol.molecule_type, []).append(entity)

    cycle_defs: list[tuple[str, str, str]] = [
        ("ax", "bx", "cx"),
        ("ay", "by", "cy"),
        ("az", "bz", "cz"),
    ][:required_cycle_count]

    completed = 0
    while True:
        if not all(molecule_entities.get(a) and molecule_entities.get(b) and molecule_entities.get(c) for a, b, c in cycle_defs):
            break
        used: list[Entity] = []
        for a, b, c in cycle_defs:
            used.extend([molecule_entities[a].pop(), molecule_entities[b].pop(), molecule_entities[c].pop()])
        for entity in used:
            if entity in env.state.entities:
                env.destroy_entity(entity)
        completed += 1

    if completed <= 0:
        return

    reward = 1.0 if required_cycle_count == 2 else 2.0
    if hasattr(env, "last_step_rewards"):
        for idx in range(len(env.last_step_rewards)):
            env.last_step_rewards[idx] += reward * completed


def territory_reward(action_selections, env):
    rewards = [0.0] * len(env.agents)
    ownership_counts = {agent: 0 for agent in env.agents}
    from word_play.presets.systems import Owner

    for entity in env.state.entities:
        owner = entity.get_component(Owner)
        if owner is not None and owner.owner in ownership_counts:
            ownership_counts[owner.owner] += 1

    prev_counts = getattr(env, "_prev_owned_counts", {})
    new_counts: dict[str, int] = {}
    for idx, agent in enumerate(env.agents):
        count = ownership_counts.get(agent, 0)
        new_counts[agent.name] = count
        rewards[idx] = float(count - prev_counts.get(agent.name, 0))
    env._prev_owned_counts = new_counts
    return rewards


def paintball_ctf_reward(action_selections, env):
    return list(getattr(env, "last_step_rewards", [0.0] * len(env.agents)))


def make_cooking_tileset(total_orders: int = 5, wall_sprite: str = "src/world_tiles/indoors/wall_sets/kitchen_brick_wall"):
    from word_play.presets.systems import Crafter, Crafter_Recipe, Inventory

    cook_recipe = Crafter_Recipe(
        input_names=("Tomato", "Tomato", "Tomato"),
        output=make_soup,
        duration=20,
    )
    deliver_recipe = Crafter_Recipe(
        input_names=("Soup",),
        output=make_delivered,
        duration=0,
    )
    return {
        "W": make_wall_tile(wall_sprite, name="Kitchen_Wall"),
        "-": {
            "name": "Counter",
            "tags": ["counter", "blocker"],
            "components": [
                Inventory(max_size=1),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/world_tiles/indoors/stations/kitchen_counter.png", z_index=4),
            ],
        },
        "C": {
            "name": "Pot",
            "tags": ["pot", "crafter", "blocker"],
            "components": [
                Crafter(recipes=[cook_recipe]),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/world_tiles/indoors/stations/pot.png", z_index=4),
            ],
        },
        "O": {
            "name": "TomatoSource",
            "tags": ["source", "tomato_source", "blocker"],
            "components": [
                Inventory(max_size=20, accepted_tags=["tomato"]),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/world_tiles/indoors/stations/crate.png", z_index=4),
            ],
        },
        "D": {
            "name": "DishSource",
            "tags": ["source", "dish_source", "blocker"],
            "components": [
                Inventory(max_size=20, accepted_tags=["dish"]),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/world_tiles/indoors/stations/crate.png", z_index=4),
            ],
        },
        "T": {
            "name": "Delivery",
            "tags": ["delivery", "crafter", "blocker"],
            "components": [
                Crafter(recipes=[deliver_recipe]),
                CookingOrderTracker(total_orders=total_orders),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/world_tiles/indoors/stations/delivery.png", z_index=4),
            ],
        },
    }


def stock_cooking_sources(map_entities: list[Entity], *, tomato_count: int = 20, dish_count: int = 20) -> None:
    for entity in map_entities:
        if "tomato_source" in entity.tags:
            populate_source_inventory(
                entity,
                "Tomato",
                ["tomato", "ingredient"],
                "src/items/consumables/vegetables/tomato_2.png",
                tomato_count,
            )
        if "dish_source" in entity.tags:
            inventory = entity.get_component(Inventory)
            if inventory is not None:
                for _ in range(dish_count):
                    inventory.store(make_dish(), None)


def populate_source_inventory(
    entity: Entity,
    item_name: str,
    item_tags: list[str],
    sprite_path: str,
    count: int,
) -> None:
    inventory = entity.get_component(Inventory)
    if inventory is None:
        return
    for _ in range(count):
        inventory.store(
            Entity(
                item_name,
                Position_2D(0, 0),
                item_tags,
                components=[Renderable(sprite_path=sprite_path, z_index=5)],
            ),
            None,
        )


def tilemap_bounds(ascii_map: str) -> tuple[int, int]:
    from word_play.utils.tilemap import ascii_to_tilemap_array
    rows = ascii_to_tilemap_array(ascii_map)
    return (len(rows[0]) if rows else 0, len(rows))


def make_wall_tile(wall_sprite: str, *, name: str = "Wall") -> dict:
    return {
        "name": name,
        "tags": ["wall", "blocker"],
        "components": [
            Collidable(collidable_tags=["blocker"]),
            Renderable(
                sprite_path=f"{wall_sprite}/{Path(wall_sprite).name}_center.png",
                wall_set=wall_sprite,
            ),
        ],
    }


def make_outer_border_walls(width: int, height: int, wall_sprite: str, *, name: str = "Outer_Wall") -> list[Entity]:
    wall_tile = make_wall_tile(wall_sprite, name=name)
    tags = list(wall_tile["tags"])
    components = wall_tile["components"]
    walls: list[Entity] = []

    for x in range(-1, width + 1):
        for y in (-1, height):
            walls.append(
                Entity(
                    f"{name}_{x}_{y}",
                    Position_2D(x, y),
                    list(tags),
                    components=deepcopy(components),
                )
            )
    for y in range(height):
        for x in (-1, width):
            walls.append(
                Entity(
                    f"{name}_{x}_{y}",
                    Position_2D(x, y),
                    list(tags),
                    components=deepcopy(components),
                )
            )
    return walls


def null_tile(_x=None, _y=None, _char=None, _tilemap=None):
    return None


def make_chopped_tomato() -> Entity:
    return Entity(
        "Chopped_Tomato",
        Position_2D(0, 0),
        ["ingredient", "chopped", "tomato"],
        components=[Renderable(sprite_path="src/items/consumables/vegetables/tomato_chopped.png", z_index=5)],
    )


def make_soup() -> Entity:
    return Entity(
        "Soup",
        Position_2D(0, 0),
        ["soup"],
        components=[Renderable(sprite_path="src/items/consumables/misc_food/soup.png", z_index=5)],
    )


def make_dish() -> Entity:
    return Entity(
        "Dish",
        Position_2D(0, 0),
        ["dish"],
        components=[Renderable(sprite_path="src/items/consumables/misc_food/plate.png", z_index=5)],
    )


def make_tomato() -> Entity:
    return Entity(
        "Tomato",
        Position_2D(0, 0),
        ["tomato", "ingredient"],
        components=[Renderable(sprite_path="src/items/consumables/vegetables/tomato_2.png", z_index=5)],
    )


def make_steak() -> Entity:
    return Entity(
        "Steak",
        Position_2D(0, 0),
        ["steak", "ingredient"],
        components=[Renderable(sprite_path="src/items/consumables/meat/steak.png", z_index=5)],
    )


def make_gold_nugget() -> Entity:
    return Entity(
        "Gold Nugget",
        Position_2D(0, 0),
        ["gold"],
        components=[Renderable(sprite_path="src/world_tiles/treasure/gold_ore.png", z_index=5)],
    )


def make_berry_item(color_id: int) -> Entity:
    color_names = {0: "Red", 1: "Green", 2: "Blue"}
    color_tags = {0: "red", 1: "green", 2: "blue"}
    sprite_paths = {
        0: "src/items/consumables/vegetables/mushroom_red.png",
        1: "src/items/consumables/vegetables/mushroom_green.png",
        2: "src/items/consumables/vegetables/mushroom_blue.png",
    }
    return Entity(
        f"{color_names.get(color_id, 'Unknown')} Berry",
        Position_2D(0, 0),
        ["berry", color_tags.get(color_id, "unknown")],
        components=[Renderable(sprite_path=sprite_paths.get(color_id, sprite_paths[0]), z_index=5)],
    )


def make_delivered() -> Entity:
    return Entity("Delivered", Position_2D(0, 0), ["delivered"], components=[])


def make_cooked_steak() -> Entity:
    return Entity(
        "Cooked_Steak",
        Position_2D(0, 0),
        ["ingredient", "chopped", "steak"],
        components=[Renderable(sprite_path="src/items/consumables/meat/steak.png", z_index=5)],
    )


def make_steak_dinner() -> Entity:
    return Entity(
        "Steak_Dinner",
        Position_2D(0, 0),
        ["dish", "finished"],
        components=[Renderable(sprite_path="src/items/consumables/misc_food/plate_dinner.png", z_index=5)],
    )


def make_gift_level_0() -> Entity:
    return Entity(
        "gift_level_0",
        Position_2D(0, 0),
        ["gift", "collectable"],
        [RefinementLevel(0), Renderable(sprite_path="src/items/misc/chest.png", z_index=2)],
    )


def make_gift_level_1() -> Entity:
    return Entity(
        "gift_level_1",
        Position_2D(0, 0),
        ["gift", "collectable"],
        [RefinementLevel(1), Renderable(sprite_path="src/items/misc/chest.png", z_index=2)],
    )


def make_gift_level_2() -> Entity:
    return Entity(
        "gift_level_2",
        Position_2D(0, 0),
        ["gift", "collectable"],
        [RefinementLevel(2), Renderable(sprite_path="src/items/misc/chest.png", z_index=2)],
    )


class Prey(Component):
    """Marks an entity as prey in predator-prey games."""
    def __init__(self, spawn_position: tuple[int, int] | None = None, respawn_delay: int = 40):
        super().__init__()
        self.alive = True
        self.spawn_position = spawn_position
        self.respawn_delay = respawn_delay
        self.respawn_counter = 0

    def caught(self) -> None:
        self.alive = False
        self.respawn_counter = self.respawn_delay
        if hasattr(self, "entity"):
            self.entity.position = Position_2D(-1000, -1000)
            renderable = self.entity.get_component(Renderable)
            if renderable is not None:
                renderable.visible = False

    def post_actions_step(self, env) -> None:
        if self.alive or self.spawn_position is None:
            return
        if self.respawn_counter > 0:
            self.respawn_counter -= 1
        if self.respawn_counter <= 0 and hasattr(self, "entity"):
            self.alive = True
            self.entity.position = Position_2D(*self.spawn_position)
            renderable = self.entity.get_component(Renderable)
            if renderable is not None:
                renderable.visible = True


class Predator(Component):
    """Marks an agent as a predator with a score."""
    def __init__(self):
        super().__init__()
        self.score = 0


def _award_step_reward(env, actor, reward: float) -> None:
    if not hasattr(env, "last_step_rewards"):
        return
    try:
        agent_idx = env.agents.index(actor)
    except ValueError:
        return
    if 0 <= agent_idx < len(env.last_step_rewards):
        env.last_step_rewards[agent_idx] += reward


# Apple/Acorn replaced by Regrowable from presets:
#   Regrowable(regrow_prob=0.005, regrow_tick_interval=20, density_dependent=True)  — was Apple(...)
#   Regrowable(regrow_tick_interval=120)  — was Acorn(...)
#   Consume_Regrowable(destroy=False, reward=1.0)  — was Eat_Apple()
#   Consume_Regrowable(destroy=False, reward=3.0)  — was Eat_Acorn()

class Fruit(Component):
    """A fruit with a type and value (fruit_market)."""
    def __init__(self, fruit_type: str, value: int = 1):
        super().__init__()
        self.fruit_type = fruit_type
        self.value = value
        self.sold = False


class FruitSpecialty(Component):
    """Tracks which fruit an agent harvests well and which fruit tastes best."""

    def __init__(self, specialty: str, favorite: str):
        super().__init__()
        self.specialty = specialty
        self.favorite = favorite

    def __init__(self, fruit_type: str, reward: float = 1.0, regrow_tick_interval: int = 50):
        super().__init__()
        self.fruit_type = fruit_type
        self.reward = reward
        self.regrow_tick_interval = regrow_tick_interval
        self.harvested = False

    def harvest(self) -> bool:
        if self.harvested:
            return False
        self.harvested = True
        renderable = self.entity.get_component(Renderable) if hasattr(self, "entity") else None
        if renderable is not None:
            renderable.visible = False
        return True

    def pre_actions_step(self, env) -> None:
        if not self.harvested:
            return
        if env.tick % self.regrow_tick_interval == 0:
            self.harvested = False
            renderable = self.entity.get_component(Renderable) if hasattr(self, "entity") else None
            if renderable is not None:
                renderable.visible = True


    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Nearby(), Target_Has_Component(FruitTree)])

    def exec_action(self, actor, target, env, kwargs=None):
        tree = target.get_component(FruitTree)
        inv = actor.get_component(Inventory)
        if tree is None or inv is None:
            return {"success": False}
        if tree.harvested:
            return {"success": False, "reason": "not_ready"}
        if not inv.has_space():
            return {"success": False, "reason": "inventory_full"}
        if not tree.harvest():
            return {"success": False, "reason": "already_harvested"}
        item = make_fruit_item(tree.fruit_type, tree.reward)
        if not inv.store(item, env):
            return {"success": False, "reason": "inventory_rejected"}
        return {"success": True, "harvested": tree.fruit_type}

    def action_description_text(self, actor, target, env):
        return "Harvest fruit from tree."


def make_fruit_item(fruit_type: str, value: float = 1.0) -> Entity:
    sprite = "src/items/consumables/fruit/apple.png" if fruit_type == "apple" else "src/items/consumables/fruit/banana.png"
    return Entity(
        name=f"{fruit_type.title()}_Item",
        position=Position_2D(0, 0),
        tags=["fruit", fruit_type, "collectable"],
        components=[
            Fruit(fruit_type=fruit_type, value=value),
            Renderable(sprite_path=sprite, z_index=3),
        ],
    )


class HiddenRole(Component):
    """Role/frozen-state tracking for hidden agenda."""

    def __init__(
        self,
        role: str,
        spawn_position: tuple[int, int],
        teleport_position: tuple[int, int] | None = None,
        frozen_ticks: int = 0,
    ):
        super().__init__()
        self.role = role
        self.spawn_position = spawn_position
        self.teleport_position = teleport_position or spawn_position
        self.frozen_ticks = frozen_ticks
        self.eliminated = False

    @property
    def is_impostor(self) -> bool:
        return self.role == "impostor"

    @property
    def is_frozen(self) -> bool:
        return self.frozen_ticks > 0

    def freeze(self, duration: int = 25) -> None:
        self.frozen_ticks = max(self.frozen_ticks, duration)
        if hasattr(self, "entity"):
            self.entity.position = Position_2D(*self.teleport_position)

    def eliminate(self) -> None:
        self.eliminated = True
        self.frozen_ticks = 0
        if hasattr(self, "entity"):
            self.entity.position = Position_2D(-1000, -1000)
            renderable = self.entity.get_component(Renderable)
            if renderable is not None:
                renderable.visible = False

    def post_actions_step(self, env) -> None:
        if self.eliminated or not hasattr(self, "entity"):
            return
        if self.frozen_ticks > 0:
            self.frozen_ticks -= 1
            self.entity.position = Position_2D(*self.teleport_position)
            if self.frozen_ticks == 0:
                self.entity.position = Position_2D(*self.spawn_position)


class Gem(Component):
    """A gem that can be collected and deposited (hidden_agenda)."""
    def __init__(self, value: float = 1.0, regrow_prob: float = 0.001):
        super().__init__()
        self.value = value
        self.collected = False
        self.regrow_prob = regrow_prob

    def collect(self) -> bool:
        if not self.collected:
            self.collected = True
            return True
        return False

    def pre_actions_step(self, env) -> None:
        if self.collected and env.tick % 100 == 0:
            import random
            if random.random() < self.regrow_prob:
                self.collected = False


class GemDeposit(Component):
    """A grate where gems can be deposited (hidden_agenda)."""
    def __init__(self, reward_per_gem: float = 1.0):
        super().__init__()
        self.gems_deposited = 0
        self.reward_per_gem = reward_per_gem
        self.is_open = True

    def deposit(self, amount: int = 1) -> float:
        if self.is_open:
            self.gems_deposited += amount
            return self.reward_per_gem * amount
        return 0.0


class FactoryItem(Component):
    """Marks a factory item with a type name and reward."""
    def __init__(self, item_type: str, reward: float = 1.0):
        super().__init__()
        self.item_type = item_type
        self.reward = reward


# ============================================================================
# Components: Common Actions
# ============================================================================

class Collect_Gem(Action):
    """Collect a nearby gem into inventory."""

    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Nearby(), Target_Has_Component(Gem)])

    def exec_action(self, actor, target, env, kwargs=None):
        gem = target.get_component(Gem)
        inv = actor.get_component(Inventory)
        role = actor.get_component(HiddenRole)
        if gem is None or inv is None:
            return {"success": False}
        if role and role.is_frozen:
            return {"success": False, "reason": "frozen"}
        if gem.collected:
            return {"success": False, "reason": "already_collected"}
        if not inv.has_space():
            return {"success": False, "reason": "inventory_full"}
        gem.collect()
        renderable = target.get_component(Renderable)
        if renderable is not None:
            renderable.visible = False
        gem_item = Entity(
            name="Gem_Item",
            position=Position_2D(0, 0),
            tags=["gem", "collectable"],
            components=[Gem(value=gem.value), Renderable(sprite_path="src/items/gems/blue_cube.png", z_index=3)],
        )
        inv.store(gem_item, env)
        return {"success": True, "gem_collected": True}

    def action_description_text(self, actor, target, env):
        return "Collect nearby gem."


class Vote_Agent(Action):
    """Cast a vote against another player during hidden-agenda voting windows."""

    def __init__(self):
        super().__init__(validation_rules=[Target_Not_Self()])

    def is_valid(self, actor, target, env, kwargs="unconsidered"):
        if not super().is_valid(actor, target, env, kwargs=kwargs):
            return False
        if not getattr(env, "voting_open", False):
            return False
        target_role = target.get_component(HiddenRole)
        return target_role is None or not target_role.eliminated

    def exec_action(self, actor, target, env, kwargs=None):
        if not getattr(env, "voting_open", False):
            return {"success": False, "reason": "voting_closed"}
        if not hasattr(env, "record_vote"):
            return {"success": False, "reason": "no_voting_system"}
        env.record_vote(actor, target)
        return {"success": True, "voted_for": target.name}

    def action_description_text(self, actor, target, env):
        return f"Vote against {target.name}."


class CollectCoin(Action):
    """Collect a nearby coin."""
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Nearby(), Target_Has_Component(Coin)])

    def exec_action(self, actor, target, env, kwargs=None):
        coin = target.get_component(Coin)
        preference = actor.get_component(CoinPreference)
        if coin and not coin.collected:
            coin.collected = True
            renderable = target.get_component(Renderable)
            if renderable is not None:
                renderable.visible = False
            _award_step_reward(env, actor, 1.0)
            if preference is not None and coin.coin_type != preference.preferred_type:
                for idx, agent in enumerate(env.agents):
                    if agent is not actor and idx < len(env.last_step_rewards):
                        env.last_step_rewards[idx] += preference.mismatch_penalty
            return {"success": True, "value": 1.0, "coin_type": coin.coin_type}
        return {"success": False}

    def action_description_text(self, actor, target, env):
        return "Collect coin."


class MineGold(Action):
    """Mine gold from a nearby gold vein."""
    def __init__(self):
        super().__init__(validation_rules=[Target_Has_Component(GoldVein), Target_Is_Nearby()])

    def exec_action(self, actor, target, env, kwargs=None):
        vein = target.get_component(GoldVein)
        inventory = actor.get_component(Inventory)
        if vein:
            nearby_miners = 0
            for entity in env.entities_near_position(target.position):
                if entity is actor:
                    nearby_miners += 1
                elif "miner" in getattr(entity, "tags", []) and entity.get_component(Inventory) is not None:
                    nearby_miners += 1
            gold, reward = vein.mine(team_size=nearby_miners)
            if gold <= 0:
                return {"success": False, "gold_mined": 0, "remaining": vein.gold_remaining, "ore_type": vein.ore_type}

            stored = 0
            if inventory is not None:
                for _ in range(gold):
                    if inventory.store(make_gold_nugget(), env):
                        stored += 1
                    else:
                        break

            if vein.gold_remaining <= 0 and target in env.state.entities:
                env.destroy_entity(target)

            if reward > 0:
                _award_step_reward(env, actor, reward)

            return {
                "success": stored > 0 or gold > 0,
                "gold_mined": gold,
                "gold_stored": stored,
                "remaining": vein.gold_remaining,
                "ore_type": vein.ore_type,
                "reward": reward,
            }
        return {"success": False}

    def action_description_text(self, actor, target, env):
        return "Mine gold from vein."


class Feed(Action):
    """Feed a nearby baby."""
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Nearby()])

    def exec_action(self, actor, target, env, kwargs=None):
        baby = target.get_component(Baby)
        if baby:
            baby.feed(getattr(env, "tick", 0))
            _award_step_reward(env, actor, 1.0)
            return {"success": True, "happiness": baby.happiness}
        return {"success": False}

    def action_description_text(self, actor, target, env):
        return "Feed the baby."


class Clean_Public_Resource(Action):
    """Spend effort to clean the shared resource."""
    def __init__(self, efficiency: float = 10.0):
        super().__init__(validation_rules=[Target_Not_Self(), Target_Is_Nearby(), Target_Has_Component(Public_Resource)])
        self.efficiency = efficiency

    def exec_action(self, actor, target, env, kwargs=None):
        public = target.get_component(Public_Resource)
        if not public:
            return {"success": False}
        cleaned = public.clean(self.efficiency)
        return {"success": True, "cleaned": cleaned, "remaining": public.level}

    def action_description_text(self, actor, target, env):
        return "Clean the public resource."


class RowLeft(Action):
    """Paddle left side of a boat."""
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor, target, env, kwargs=None):
        rower = actor.get_component(BoatRower)
        if rower:
            rower.paddling = True
            rower.row_count += 1
            rower.last_side = "left"
            return {"success": True}

    def action_description_text(self, actor, target, env):
        return "Paddle left side."


class RowRight(Action):
    """Paddle right side of a boat."""
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor, target, env, kwargs=None):
        rower = actor.get_component(BoatRower)
        if rower:
            rower.paddling = True
            rower.row_count += 1
            rower.last_side = "right"
            return {"success": True}

    def action_description_text(self, actor, target, env):
        return "Paddle right side."


class Row(Action):
    """Row the boat with your partner."""

    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor, target, env, kwargs=None):
        rower = actor.get_component(BoatRower)
        if rower:
            rower.paddling = True
            rower.row_count += 1
            rower.last_side = "row"
            return {"success": True, "row": True}
        return {"success": False}

    def action_description_text(self, actor, target, env):
        return "Row the boat."


class Flail(Action):
    """Desperation paddle with a small chance to advance the boat."""

    def __init__(self, success_rate: float = 0.1):
        super().__init__(validation_rules=[Target_Is_Self()])
        self.success_rate = success_rate

    def exec_action(self, actor, target, env, kwargs=None):
        rower = actor.get_component(BoatRower)
        if rower is None:
            return {"success": False}
        rower.paddling = True
        rower.last_side = "flail"
        if hash((actor.name, getattr(env, "tick", 0))) % 10 == 0:
            _award_step_reward(env, actor, 0.5)
            return {"success": True, "advance": True}
        return {"success": True, "advance": False}

    def action_description_text(self, actor, target, env):
        return "Flail the oar with a small chance of progress."


class ROW(Row):
    pass


class FLAIL(Flail):
    pass


class Catch(Action):
    """Catch/tag nearby prey (predator-prey games)."""
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Nearby(), Target_Has_Component(Prey)])

    def exec_action(self, actor, target, env, kwargs=None):
        prey = target.get_component(Prey)
        pred = actor.get_component(Predator)
        if prey and prey.alive:
            prey.caught()
            if pred:
                pred.score += 1
            _award_step_reward(env, actor, 1.0)
            return {"success": True, "caught": target.name}
        return {"success": False}

    def action_description_text(self, actor, target, env):
        return "Catch nearby prey."


# ============================================================================
# Components: Common Pool System (resource extraction with regrowth)
# ============================================================================


class Hopper(Component):
    """Collection point that accepts items and gives reward."""
    def __init__(self, accepted_types: list[str] = None, reward_per_item: float = 1.0):
        super().__init__()
        self.accepted_types = accepted_types or ["apple", "banana", "blue_cube", "pink_cube"]
        self.reward_per_item = reward_per_item
        self.items_received = 0
        self.is_open = True

    def accept(self, item_type: str) -> bool:
        if not self.is_open or item_type not in self.accepted_types:
            return False
        self.items_received += 1
        return True


class ConveyorBelt(Component):
    """Moves items on the conveyor toward the hopper each step."""
    def __init__(self, hopper_pos=None, speed: int = 1):
        super().__init__()
        self.hopper_pos = hopper_pos
        self.speed = speed


class RefinementLevel(Component):
    """Track how refined an item is."""
    def __init__(self, level: int = 0, max_level: int = 3):
        super().__init__()
        self.level = level
        self.max_level = max_level

    def refine(self) -> bool:
        if self.level < self.max_level:
            self.level += 1
            return True
        return False

    @property
    def value(self) -> int:
        return 10 * (self.level + 1)


class FactoryScore(Component):
    """Tracks per-agent factory score."""
    def __init__(self):
        super().__init__()
        self.score = 0
        self.step_score_delta = 0

    def pre_actions_step(self, env):
        self.step_score_delta = 0


class CoinsThresholdChecker(Component):
    """Checks if any agent's inventory exceeds a coin threshold and terminates."""
    def __init__(self, threshold: int = 50):
        super().__init__()
        self.threshold = threshold

    def post_actions_step(self, env) -> None:
        for agent in env.agents:
            inv = agent.get_component(Inventory)
            if inv and len(inv.contents) >= self.threshold:
                env.terminations = [True] * len(env.agents)
                return


# ============================================================================
# Components: Common Reward Functions
# ============================================================================

def zero_reward(selections: list[Action_Selection], env) -> list[float]:
    """Zero reward for all agents."""
    return [0.0] * len(env.agents)


def predator_prey_reward(selections: list[Action_Selection], env) -> list[float]:
    """Return the per-step predator-prey rewards accumulated during actions."""
    return list(getattr(env, "last_step_rewards", [0.0] * len(env.agents)))


def fruit_market_reward(selections: list[Action_Selection], env) -> list[float]:
    """Return the per-step fruit-market rewards accumulated during actions."""
    return list(getattr(env, "last_step_rewards", [0.0] * len(env.agents)))


def hidden_agenda_reward(selections: list[Action_Selection], env) -> list[float]:
    """Return the per-step hidden-agenda rewards accumulated during actions."""
    return list(getattr(env, "last_step_rewards", [0.0] * len(env.agents)))
def factory_reward(selections: list[Action_Selection], env) -> list[float]:
    """Return the per-step factory rewards accumulated during actions."""
    return list(getattr(env, "last_step_rewards", [0.0] * len(env.agents)))


class HiddenAgendaLifecycleMixin:
    """Shared voting and win-condition lifecycle for Hidden Agenda."""

    def environment_start_of_step(self, action_selections):
        super().environment_start_of_step(action_selections)
        self.last_step_rewards = [0.0] * len(self.agents)
        if not self.voting_open and self.tick > 0 and self.tick % 200 == 0:
            self.trigger_voting()

    def trigger_voting(self):
        self.voting_open = True
        self.voting_ttl = 8
        self.votes = {}

    def record_vote(self, actor, target):
        role = actor.get_component(HiddenRole)
        target_role = target.get_component(HiddenRole)
        if role and (role.is_frozen or role.eliminated):
            return
        if target_role and target_role.eliminated:
            return
        self.votes[actor.name] = target

    def _resolve_votes(self):
        if not self.votes:
            return
        counts = {}
        for target in self.votes.values():
            counts[target] = counts.get(target, 0) + 1
        target, count = max(counts.items(), key=lambda item: item[1])
        if count < 2:
            return
        target_role = target.get_component(HiddenRole)
        if target_role is None or target_role.eliminated:
            return
        target_role.eliminate()
        if target_role.is_impostor:
            for idx, agent in enumerate(self.agents):
                role = agent.get_component(HiddenRole)
                self.last_step_rewards[idx] += -5.0 if role and role.is_impostor else 2.0
            self.terminations = [True] * len(self.agents)
        else:
            for idx, agent in enumerate(self.agents):
                role = agent.get_component(HiddenRole)
                self.last_step_rewards[idx] += 1.0 if role and role.is_impostor else -1.0

    def environment_end_of_step(self, action_selections):
        super().environment_end_of_step(action_selections)
        if self.voting_open:
            self.voting_ttl -= 1
            if self.voting_ttl <= 0:
                self.voting_open = False
                self._resolve_votes()
                self.votes = {}

        total_gems = 0
        for entity in self.state.entities:
            deposit = entity.get_component(GemDeposit)
            if deposit:
                total_gems += deposit.gems_deposited
        if total_gems >= self.goal_gems:
            for idx, agent in enumerate(self.agents):
                role = agent.get_component(HiddenRole)
                self.last_step_rewards[idx] += -4.0 if role and role.is_impostor else 2.0
            self.terminations = [True] * len(self.agents)
        self._init_agent_list()
        self._init_agent_idx_dict()


def pollution_reward(selections: list[Action_Selection], env) -> list[float]:
    """Everyone gets negative reward if pollution is high."""
    for e in env.state.entities:
        public = e.get_component(Public_Resource)
        if public and public.is_dirty:
            return [-1.0] * len(env.agents)
    return [0.0] * len(env.agents)


def run(env, *, policy=None, sidebar_agent_id=0, model_key="default"):
    """Preset run script for tilemapped benchmark environments.

    This is a simple starting point. Write your own run loop if you need
    custom logging, training, or evaluation logic. See examples/overcooked/run.py
    for a more advanced example.

    Args:
        env: The environment instance.
        policy: "random" or "llm". If omitted, parse from CLI.
        sidebar_agent_id: Which agent's reasoning to show in the sidebar (LLM mode).
        model_key: Registry key to use when attaching the default benchmark LLM.
    """
    import argparse
    from word_play.core.components import Agent_Policy

    if policy is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--policy", choices=["random", "llm"], default="random")
        args = parser.parse_args()
        policy = args.policy

    if hasattr(env, "last_step_rewards"):
        original_environment_start_of_step = env.environment_start_of_step

        def _benchmark_environment_start_of_step(action_selections):
            original_environment_start_of_step(action_selections)
            env.last_step_rewards = [0.0] * len(env.agents)

        env.environment_start_of_step = _benchmark_environment_start_of_step

    if policy == "llm":
        LLM_MODEL_REGISTRY[model_key] = OpenRouter_Model(
            model_name="openai/gpt-4o-mini",
            generation_params={"temperature": 0.3},
        )
        env.hud_sidebar_width = 420
    elif policy == "random":
        for agent in env.agents:
            if agent.get_component(Agent_Policy) is not None:
                components = {
                    ctype: comp
                    for ctype, comp in agent.components.items()
                    if not isinstance(comp, Agent_Policy)
                }
                random_policy = Random_Policy()
                random_policy.entity = agent
                components[type(random_policy)] = random_policy
                agent.components = components

    episode_length = getattr(env, "episode_length", 100)
    all_logs = []

    for step in range(episode_length):
        cur_step_log = {"step": step}
        cur_step_actions = []

        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)

            if info:
                if info.get("reasoning"):
                    print(f"[step {step}] {agent.name} reasoning:\n{info['reasoning']}")
                if info.get("raw_response"):
                    print(f"[step {step}] {agent.name} raw:\n{info['raw_response']}")

            cur_step_actions.append(action)
            cur_step_log[agent.name] = {"action": str(action), "info": info}

        env.step(cur_step_actions)
        all_logs.append(cur_step_log)

        if not render_step(env, step_delay=0.0, sidebar_agent_id=sidebar_agent_id):
            break

    return all_logs


def run_exp(env, *, policy="random", sidebar_agent_id=0, model_key="default"):
    """Compatibility alias for older benchmark entrypoints."""
    return run(env, policy=policy, sidebar_agent_id=sidebar_agent_id, model_key=model_key)


# ============================================================================
# Destructible wall factory (paintball variants)
# ============================================================================

import random as _random


def make_destructible_wall(name, intact_prob, wall_sprite, max_health=3):
    """Create a destructible wall tile dict, or a destroyed floor if the random check fails."""
    if _random.random() < intact_prob:
        return {
            "name": name,
            "tags": ["wall", "blocker", "destructible"],
            "components": [
                Collidable(collidable_tags=["blocker"]),
                Health(max_health=max_health, starting_health=max_health),
                Renderable(
                    sprite_path=f"{wall_sprite}/{Path(wall_sprite).name}_center.png",
                    wall_set=wall_sprite,
                ),
            ],
        }
    return {
        "name": f"{name}_Destroyed",
        "tags": ["floor", "destroyed_wall"],
        "components": [
            Renderable(
                sprite_path="src/world_tiles/indoors/floors/day_brick_floor_c.png",
                z_index=0,
            ),
        ],
    }


def make_destructible_wall_tile(name, intact_prob, wall_sprite, max_health=3):
    """Factory that randomizes each tile at tilemap-parse time."""
    def factory(x, y, _char, _tilemap):
        return make_destructible_wall(name, intact_prob, wall_sprite, max_health)
    return factory


# ============================================================================
# CTF end-of-step mixin
# ============================================================================

class CTFLifecycleMixin:
    """Shared CTF flag-capture logic for paintball CTF."""

    def environment_end_of_step(self, action_selections):
        super().environment_end_of_step(action_selections)
        red_positions = find_char_positions(self._ctf_map, "F")
        blue_positions = find_char_positions(self._ctf_map, "G")
        red_base = red_positions[0] if red_positions else (0, 0)
        blue_base = blue_positions[0] if blue_positions else (0, 0)
        for idx, agent in enumerate(self.agents):
            inv = agent.get_component(Inventory)
            if inv is None:
                continue
            for item in list(inv.contents):
                flag = item.get_component(Flag)
                if flag is None:
                    continue
                if "red" in agent.tags and flag.team == "blue" and (agent.position.x, agent.position.y) == red_base:
                    self.score_red += 1
                    self.last_step_rewards[idx] += 5.0
                    inv.remove(item)
                    if item in self.state.entities:
                        self.destroy_entity(item)
                    if self.score_red >= 1:
                        self.terminations = [True] * len(self.agents)
                if "blue" in agent.tags and flag.team == "red" and (agent.position.x, agent.position.y) == blue_base:
                    self.score_blue += 1
                    self.last_step_rewards[idx] += 5.0
                    inv.remove(item)
                    if item in self.state.entities:
                        self.destroy_entity(item)
                    if self.score_blue >= 1:
                        self.terminations = [True] * len(self.agents)


# ============================================================================
# KotH reward function
# ============================================================================

def koth_reward_func(selections, env):
    rewards = []
    hill = next((e for e in env.state.entities if e.get_component(HillZone)), None)
    for agent in env.agents:
        if hill:
            ctrl = hill.get_component(Owner)
            rewards.append(1.0 if ctrl and ctrl.is_owned_by(agent) else 0.0)
        else:
            rewards.append(0.0)
    return rewards
