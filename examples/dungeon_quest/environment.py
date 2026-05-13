from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from word_play.core import (
    Action,
    Agent_Policy,
    Entity,
    Environment,
    Environment_State,
    Observation,
)
from word_play.core.actions import Target_Is_Self
from word_play.presets.action_policies.follow_action_sequence import Follow_Action_Sequence
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.action_validations import Target_Doesnt_Have_Tag, Target_Has_Component
from word_play.presets.movement.common import Collidable
from word_play.presets.movement.simple_2d_grid import (
    INFINITE_2D_MOVEMENT_SYSTEM,
    Move_Down,
    Move_Left,
    Move_Right,
    Move_Up,
    Position_2D,
)
from word_play.presets.renderers import Renderable
from word_play.presets.systems import Do_Nothing, Health

if TYPE_CHECKING:
    from word_play.core import Action_Selection


def dungeon_terminal_reward(action_selections: list["Action_Selection"], env: "DungeonRaidEnv") -> list[float]:
    """Return a sparse reward that pays out only when the final boss dies."""
    reward = 1.0 if env.final_boss_defeated else 0.0
    return [reward for _ in env.agents]


def manhattan_distance(a: Position_2D, b: Position_2D) -> int:
    """Return the Manhattan distance between two grid positions."""
    return abs(a.x - b.x) + abs(a.y - b.y)


def is_adjacent(actor: Entity, target: Entity, env: Environment) -> bool:
    """Return whether two entities are orthogonally adjacent."""
    actor_pos = actor.position
    target_pos = target.position
    if not isinstance(actor_pos, Position_2D) or not isinstance(target_pos, Position_2D):
        return False
    return manhattan_distance(actor_pos, target_pos) == 1


def direction_name(dx: int, dy: int) -> str:
    """Convert a unit delta into a readable movement label."""
    if dx == 1 and dy == 0:
        return "right"
    if dx == -1 and dy == 0:
        return "left"
    if dx == 0 and dy == 1:
        return "up"
    if dx == 0 and dy == -1:
        return "down"
    return "unknown"


class DungeonPreviewPolicy(Agent_Policy):
    """Choose a simple combat-first action for preview runs."""

    def select_action(self, observation: Observation):
        for selection in observation.possible_actions:
            if isinstance(selection.action, EnemyStrike):
                return selection, {"policy": "attack_first"}

        move_actions = [
            selection
            for selection in observation.possible_actions
            if isinstance(selection.action, (Move_Left, Move_Right, Move_Up, Move_Down))
        ]
        if move_actions:
            actor_position = move_actions[0].actor.position
            if not isinstance(actor_position, Position_2D):
                return move_actions[0], {"policy": "fallback_move"}

            enemy_targets = [selection.target_entity for selection in observation.possible_actions if "enemy" in selection.target_entity.tags]
            if enemy_targets:
                unique_targets = {enemy.name: enemy for enemy in enemy_targets}
                target_position = min(
                    (enemy.position for enemy in unique_targets.values() if isinstance(enemy.position, Position_2D)),
                    key=lambda pos: manhattan_distance(actor_position, pos),
                )
            elif isinstance(observation, DungeonObservation):
                enter_exit_actions = [selection for selection in observation.possible_actions if isinstance(selection.action, EnterExit)]
                if enter_exit_actions:
                    return enter_exit_actions[0], {"policy": "take_exit"}
                target_position = Position_2D(*observation.exit_tile)
            else:
                target_position = Position_2D(actor_position.x + 1, actor_position.y)
            preferred_action_types: list[type[Action]] = []
            dx = target_position.x - actor_position.x
            dy = target_position.y - actor_position.y
            if abs(dx) >= abs(dy):
                if dx > 0:
                    preferred_action_types.append(Move_Right)
                elif dx < 0:
                    preferred_action_types.append(Move_Left)
                if dy > 0:
                    preferred_action_types.append(Move_Up)
                elif dy < 0:
                    preferred_action_types.append(Move_Down)
                if dy <= 0:
                    preferred_action_types.append(Move_Up)
                if dy >= 0:
                    preferred_action_types.append(Move_Down)
                if dx > 0:
                    preferred_action_types.append(Move_Left)
                elif dx < 0:
                    preferred_action_types.append(Move_Right)
            else:
                if dy > 0:
                    preferred_action_types.append(Move_Up)
                elif dy < 0:
                    preferred_action_types.append(Move_Down)
                if dx > 0:
                    preferred_action_types.append(Move_Right)
                elif dx < 0:
                    preferred_action_types.append(Move_Left)
                if dx <= 0:
                    preferred_action_types.append(Move_Right)
                if dx >= 0:
                    preferred_action_types.append(Move_Left)
                if dy > 0:
                    preferred_action_types.append(Move_Down)
                elif dy < 0:
                    preferred_action_types.append(Move_Up)
            preferred_action_types.extend([Move_Right, Move_Up, Move_Down, Move_Left])

            for action_type in preferred_action_types:
                for selection in move_actions:
                    if isinstance(selection.action, action_type):
                        return selection, {"policy": "chase_target"}

        for selection in observation.possible_actions:
            if isinstance(selection.action, ClaimChestReward):
                return selection, {"policy": "take_reward"}
        for selection in observation.possible_actions:
            if isinstance(selection.action, OpenChest):
                return selection, {"policy": "open_chest"}
        for selection in observation.possible_actions:
            if isinstance(selection.action, EnterExit):
                return selection, {"policy": "take_exit"}
        for selection in observation.possible_actions:
            if isinstance(selection.action, Do_Nothing):
                return selection, {"policy": "stall"}
        raise ValueError("DungeonPreviewPolicy could not find a valid action.")


@dataclass(slots=True)
class DungeonObservation(Observation):
    """Describe the current room, nearby danger, and available actions."""

    room_name: str
    room_type: str
    room_size: tuple[int, int]
    coordinate_system: list[str]
    player_position: tuple[int, int]
    player_hp: str
    loadout_summary: str
    enemy_summary: str
    chest_summary: str
    wall_summary: str
    exit_summary: str
    exit_tile: tuple[int, int]
    spatial_facts: list[str]
    mission: str

    def __str__(self) -> str:
        action_lines = [f"[{idx}] {action}" for idx, action in enumerate(self.possible_actions)]
        action_block = "\n".join(action_lines) if action_lines else "(no valid actions)"
        coordinate_block = "\n".join(f"- {fact}" for fact in self.coordinate_system)
        facts_block = "\n".join(f"- {fact}" for fact in self.spatial_facts) if self.spatial_facts else "- none"
        return (
            f"MISSION:\n{self.mission}\n\n"
            f"COORDINATE SYSTEM:\n{coordinate_block}\n\n"
            f"ROOM:\n"
            f"- name: {self.room_name}\n"
            f"- type: {self.room_type}\n"
            f"- size: {self.room_size}\n\n"
            f"PLAYER:\n"
            f"- status: {self.player_hp}\n"
            f"- loadout: {self.loadout_summary}\n"
            f"- position: {self.player_position}\n\n"
            f"ROOM STATE:\n"
            f"- enemies: {self.enemy_summary}\n"
            f"- chest: {self.chest_summary}\n"
            f"- internal_walls: {self.wall_summary}\n"
            f"- exit: {self.exit_summary}\n"
            f"- exit_tile: {self.exit_tile}\n\n"
            f"SPATIAL FACTS:\n{facts_block}\n\n"
            f"ACTIONS:\n{action_block}"
        )


class EnterExit(Action):
    """Move the player to the next room when standing on an open exit tile."""

    def __init__(self):
        super().__init__()

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered") -> bool:
        if actor is not target_entity:
            return False
        if not isinstance(env, DungeonRaidEnv):
            return False
        if env.current_room_exit_locked():
            return False
        if env.current_room_index >= len(env.rooms) - 1:
            return False
        actor_pos = actor.position
        return isinstance(actor_pos, Position_2D) and (actor_pos.x, actor_pos.y) == env.current_room.exit_tile

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert isinstance(env, DungeonRaidEnv)
        env.pending_room_advance = env.current_room_index + 1
        return {"transitioned": True}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Enter the exit."


class EnemyStrike(Action):
    """Attack any orthogonally adjacent unit with health."""

    def __init__(self, damage_amount: float):
        super().__init__(
            validation_rules=[
                Target_Has_Component(Health),
                Target_Doesnt_Have_Tag(["in_inventory"]),
            ]
        )
        self.damage_amount = damage_amount

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered") -> bool:
        if actor is target_entity:
            return False
        base_valid = super().is_valid(actor, target_entity, env, kwargs=kwargs)
        return base_valid and is_adjacent(actor, target_entity, env)

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        damage = self.damage_amount
        if isinstance(env, DungeonRaidEnv) and actor is env.player:
            damage = env.sword_damage + (1 if env.battle_tonic_turns > 0 else 0)
        health = target_entity.get_component(Health)
        health.health -= damage
        return {"damage": damage}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Strike {target_entity.name}"


class UseHealingPotion(Action):
    """Restore health from the raider's potion supply."""

    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered") -> bool:
        if actor is not target_entity or not isinstance(env, DungeonRaidEnv):
            return False
        health = actor.get_component(Health)
        return env.healing_potions > 0 and health.health < health.max_health

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert isinstance(env, DungeonRaidEnv)
        health = actor.get_component(Health)
        healed = min(4, int(health.max_health - health.health))
        health.health += healed
        env.healing_potions -= 1
        env.event_log.append(f"The raider drinks a healing potion and restores {healed} HP.")
        return {"healed": healed}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        assert isinstance(env, DungeonRaidEnv)
        return f"Use healing potion ({env.healing_potions} left)"


class UseBattleTonic(Action):
    """Temporarily empower the raider's sword."""

    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered") -> bool:
        return actor is target_entity and isinstance(env, DungeonRaidEnv) and env.battle_tonics > 0 and env.battle_tonic_turns == 0

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert isinstance(env, DungeonRaidEnv)
        env.battle_tonics -= 1
        env.battle_tonic_turns = env.battle_tonic_duration
        env.event_log.append("The raider drinks a battle tonic. The sword crackles with energy.")
        return {"buff_turns": env.battle_tonic_turns}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        assert isinstance(env, DungeonRaidEnv)
        return f"Use battle tonic ({env.battle_tonics} left)"


class OpenChest(Action):
    """Open a room chest after reaching it."""

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered") -> bool:
        return (
            isinstance(env, DungeonRaidEnv)
            and "chest" in target_entity.tags
            and env.current_room_chest_available()
            and not env.chest_opened.get(env.current_room.room_id, False)
            and is_adjacent(actor, target_entity, env)
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert isinstance(env, DungeonRaidEnv)
        env.chest_opened[env.current_room.room_id] = True
        env.event_log.append(f"{target_entity.name} opens and reveals several rewards.")
        return {"opened": True}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Open {target_entity.name}"


class ClaimChestReward(Action):
    """Claim one chest reward after opening it."""

    def __init__(self, reward_id: str, label: str):
        super().__init__()
        self.reward_id = reward_id
        self.label = label

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered") -> bool:
        return (
            isinstance(env, DungeonRaidEnv)
            and "chest" in target_entity.tags
            and env.current_room_chest_available()
            and env.chest_opened.get(env.current_room.room_id, False)
            and not env.chest_claimed.get(env.current_room.room_id, False)
            and is_adjacent(actor, target_entity, env)
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert isinstance(env, DungeonRaidEnv)
        env.apply_chest_reward(self.reward_id)
        env.chest_claimed[env.current_room.room_id] = True
        env.event_log.append(f"The raider takes {self.label}.")
        return {"reward_id": self.reward_id}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Take {self.label} from {target_entity.name}"


@dataclass(slots=True)
class EnemyTemplate:
    """Define a spawnable enemy archetype."""

    name: str
    sprite: str
    max_health: int
    damage: int
    position: tuple[int, int]
    tags: list[str]


@dataclass(slots=True)
class RoomTemplate:
    """Describe a single dungeon room and its render layout."""

    room_id: str
    name: str
    room_type: str
    width: int
    height: int
    floor_sprite: str
    wall_set: str
    accent_tiles: list[dict[str, object]] = field(default_factory=list)
    wall_positions: set[tuple[int, int]] = field(default_factory=set)
    enemy_templates: list[EnemyTemplate] = field(default_factory=list)
    chest_position: tuple[int, int] | None = None
    chest_rewards: list[tuple[str, str]] = field(default_factory=list)
    player_spawn: tuple[int, int] = (1, 1)
    exit_tile: tuple[int, int] = (5, 1)
    lore: str = ""

    def build_background(self) -> list[dict[str, object]]:
        """Return the background tile payload for renderer consumption."""
        tiles: list[dict[str, object]] = []
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) in self.wall_positions or x in {0, self.width - 1} or y in {0, self.height - 1}:
                    tiles.append({"x": x, "y": y, "kind": "wall", "wall_set": self.wall_set})
                else:
                    tiles.append({"x": x, "y": y, "kind": "floor", "sprite": self.floor_sprite})
        tiles.extend(dict(tile) for tile in self.accent_tiles)
        exit_x, exit_y = self.exit_tile
        tiles.append(
            {
                "x": exit_x,
                "y": exit_y,
                "kind": "floor",
                "sprite": "src/items/materials/misc/small_ladder_down.png",
            }
        )
        return tiles


class DungeonRaidEnv(Environment):
    """Run a small multi-room dungeon with a single sparse boss reward."""

    PLAYER_SPRITE = "src/characters/humanoids/human/farmer_man.png"
    GOBLIN_SPRITE = "src/characters/humanoids/goblinoid/goblin.png"
    SKELETON_SPRITE = "src/characters/monsters/undead/skeleton.png"
    BOSS_SPRITE = "src/characters/monsters/demonic/horned_devil.png"
    TREASURE_SPRITE = "src/items/materials/misc/open_chest.png"
    ALTAR_SPRITE = "src/items/materials/misc/altar.png"

    def __init__(self, renderer=None):
        self.renderer_impl = renderer
        self.episode_length = 120
        self.rooms = self._build_room_templates()
        self.current_room_index = 0
        self.current_room = self.rooms[0]
        self.player = self._build_player()
        self._room_background: list[dict[str, object]] = []
        self.event_log: list[str] = []
        self.hud_header = ""
        self.hud_lines: list[str] = []
        self.tick = 0
        self.score = 0
        self.deliveries = 0
        self.sword_name = "Iron Sword"
        self.sword_damage = 2
        self.healing_potions = 2
        self.battle_tonics = 1
        self.battle_tonic_turns = 0
        self.battle_tonic_duration = 3
        self.chest_opened: dict[str, bool] = {}
        self.chest_claimed: dict[str, bool] = {}
        self.final_boss_defeated = False
        self.pending_room_advance: int | None = None
        super().__init__(
            description="Dungeon Raid: cross each room, defeat its enemies, and slay the final boss.",
            entities=[],
            movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
            reward_func=dungeon_terminal_reward,
            entity_order=entity_definition_order,
        )

    def _build_player(self) -> Entity:
        """Create the single dungeon raider."""
        return Entity(
            name="Raider",
            position=Position_2D(1, 1),
            tags=["agent", "hero", "player"],
            actions=[
                Move_Left(),
                Move_Right(),
                Move_Up(),
                Move_Down(),
                EnemyStrike(damage_amount=2),
                UseHealingPotion(),
                UseBattleTonic(),
                OpenChest(),
                ClaimChestReward("moonblade", "Moonblade (+1 sword damage)"),
                ClaimChestReward("vitality_flask", "Vitality Flask (+2 max HP, +1 potion)"),
                ClaimChestReward("war_drum", "War Drum (+2 tonics, longer buff)"),
                EnterExit(),
                Do_Nothing(),
            ],
            components=[
                DungeonPreviewPolicy(),
                Health(max_health=12, starting_health=12),
                Collidable(collidable_tags=["wall", "enemy"]),
                Renderable(sprite_path=self.PLAYER_SPRITE, z_index=10),
            ],
        )

    def _build_room_templates(self) -> list[RoomTemplate]:
        """Create the fixed room sequence for the first dungeon slice."""
        return [
            RoomTemplate(
                room_id="entry_hall",
                name="Entry Hall",
                room_type="combat",
                width=9,
                height=7,
                floor_sprite="src/world_tiles/indoors/floors/night_stone_floor_c.png",
                wall_set="src/world_tiles/indoors/wall_sets/bright_brick_wall",
                wall_positions={(4, 3)},
                enemy_templates=[
                    EnemyTemplate(
                        name="Goblin Scout",
                        sprite=self.GOBLIN_SPRITE,
                        max_health=3,
                        damage=1,
                        position=(6, 3),
                        tags=["enemy", "goblin"],
                    )
                ],
                player_spawn=(1, 3),
                exit_tile=(7, 3),
                lore="A narrow hall with one snarling scout guarding the way forward.",
            ),
            RoomTemplate(
                room_id="crypt",
                name="Moon Crypt",
                room_type="combat",
                width=11,
                height=7,
                floor_sprite="src/world_tiles/indoors/floors/night_stone_floor_c.png",
                wall_set="src/world_tiles/indoors/wall_sets/dim_blue_wall",
                wall_positions={(3, 2), (3, 4), (7, 2), (7, 4)},
                accent_tiles=[
                    {"x": 5, "y": 3, "kind": "floor", "sprite": self.ALTAR_SPRITE},
                ],
                chest_position=(5, 3),
                chest_rewards=[
                    ("moonblade", "Moonblade (+1 sword damage)"),
                    ("vitality_flask", "Vitality Flask (+2 max HP, +1 potion)"),
                    ("war_drum", "War Drum (+2 tonics, longer buff)"),
                ],
                enemy_templates=[
                    EnemyTemplate(
                        name="Bone Guard",
                        sprite=self.SKELETON_SPRITE,
                        max_health=4,
                        damage=1,
                        position=(8, 2),
                        tags=["enemy", "undead"],
                    ),
                    EnemyTemplate(
                        name="Bone Guard B",
                        sprite=self.SKELETON_SPRITE,
                        max_health=4,
                        damage=1,
                        position=(8, 4),
                        tags=["enemy", "undead"],
                    ),
                ],
                player_spawn=(1, 3),
                exit_tile=(9, 3),
                lore="An altar splits the chamber while skeletal guards close in from both flanks.",
            ),
            RoomTemplate(
                room_id="throne",
                name="Ashen Throne",
                room_type="boss",
                width=11,
                height=9,
                floor_sprite="src/world_tiles/indoors/floors/night_stone_floor_c.png",
                wall_set="src/world_tiles/indoors/wall_sets/dark_infernal_wall",
                wall_positions={(4, 4), (5, 4), (6, 4)},
                accent_tiles=[
                    {"x": 5, "y": 6, "kind": "floor", "sprite": self.TREASURE_SPRITE},
                ],
                enemy_templates=[
                    EnemyTemplate(
                        name="Ash Warden",
                        sprite=self.BOSS_SPRITE,
                        max_health=8,
                        damage=2,
                        position=(8, 4),
                        tags=["enemy", "boss"],
                    )
                ],
                player_spawn=(1, 4),
                exit_tile=(9, 4),
                lore="The final chamber opens into a throne room where the Ash Warden waits.",
            ),
        ]

    def _build_room_entities(self, room: RoomTemplate) -> list[Entity]:
        """Instantiate the active room's collidable walls and enemies."""
        entities: list[Entity] = [self.player]
        all_wall_positions = set(room.wall_positions)
        for x in range(room.width):
            all_wall_positions.add((x, 0))
            all_wall_positions.add((x, room.height - 1))
        for y in range(room.height):
            all_wall_positions.add((0, y))
            all_wall_positions.add((room.width - 1, y))

        for wall_x, wall_y in sorted(all_wall_positions):
            entities.append(
                Entity(
                    name=f"Wall {wall_x},{wall_y}",
                    position=Position_2D(wall_x, wall_y),
                    tags=["wall"],
                    components=[
                        Collidable(collidable_tags=["hero", "enemy"]),
                        Renderable(sprite_path=room.wall_set, visible=False),
                    ],
                )
            )
        for template in room.enemy_templates:
            entities.append(
                Entity(
                    name=template.name,
                    position=Position_2D(*template.position),
                    tags=list(template.tags),
                    actions=[
                        Move_Left(),
                        Move_Right(),
                        Move_Up(),
                        Move_Down(),
                        EnemyStrike(damage_amount=template.damage),
                        Do_Nothing(),
                    ],
                    components=[
                        Follow_Action_Sequence([(Do_Nothing, None)]),
                        Health(max_health=template.max_health, starting_health=template.max_health),
                        Collidable(collidable_tags=["wall", "hero", "enemy"]),
                        Renderable(sprite_path=template.sprite, z_index=9),
                    ],
                )
            )
        if room.chest_position is not None:
            entities.append(
                Entity(
                    name="Moon Chest",
                    position=Position_2D(*room.chest_position),
                    tags=["chest", "loot"],
                    components=[Renderable(sprite_path=self.TREASURE_SPRITE, z_index=8)],
                )
            )
        return entities

    def _set_active_room(self, room_index: int) -> None:
        """Swap the active room and rebuild the room-scoped entity list."""
        self.current_room_index = room_index
        self.current_room = self.rooms[room_index]
        spawn_x, spawn_y = self.current_room.player_spawn
        self.player.position = Position_2D(spawn_x, spawn_y)
        self.state = Environment_State(self._build_room_entities(self.current_room))
        self._room_background = self.current_room.build_background()

    def advance_to_next_room(self) -> None:
        """Progress to the next room in the dungeon sequence."""
        if self.current_room_index >= len(self.rooms) - 1:
            return
        self._set_active_room(self.current_room_index + 1)
        self._init_agent_list()
        self._init_agent_idx_dict()
        self.event_log.append(f"You push deeper into the dungeon and enter {self.current_room.name}.")
        self.event_log = self.event_log[-6:]
        self._refresh_hud()

    def observe(self, agent_id: int) -> Observation:
        """Return a plain-language summary of the current room state."""
        player_health = self.player.get_component(Health)
        player_position = self.player.position
        player_weapon_damage = self.sword_damage + (1 if self.battle_tonic_turns > 0 else 0)
        legal_moves = {
            str(selection)
            for selection in self.possible_actions(self.agents[agent_id])
            if isinstance(selection.action, (Move_Left, Move_Right, Move_Up, Move_Down))
        }
        coordinate_system = [
            "Positions are grid coordinates written as (x, y).",
            "The bottom-left wall tile of the room is the origin: (0, 0).",
            f"For this room, x ranges from 0 to {self.current_room.width - 1} and y ranges from 0 to {self.current_room.height - 1}.",
            "The left wall lies on x=0. The bottom wall lies on y=0.",
            "Move right increases x by 1. Move left decreases x by 1.",
            "Move up increases y by 1. Move down decreases y by 1.",
            "Positive dy means the target is above you. Negative dy means the target is below you.",
            "Use these coordinate rules, not the screen image, to reason about direction.",
        ]
        enemies = self.active_enemies()
        chest_summary = self.current_chest_summary()
        spatial_facts: list[str] = []
        if enemies:
            enemy_bits = []
            nearest_enemy = min(
                (enemy for enemy in enemies if isinstance(enemy.position, Position_2D)),
                key=lambda enemy: manhattan_distance(player_position, enemy.position),
            )
            for enemy in enemies:
                health = enemy.get_component(Health)
                enemy_bits.append(
                    f"{enemy.name} at {enemy.position} ({int(health.health)}/{int(health.max_health)} HP)"
                )
            enemy_summary = "; ".join(enemy_bits)
            dx = nearest_enemy.position.x - player_position.x
            dy = nearest_enemy.position.y - player_position.y
            spatial_facts.append(f"Nearest enemy is {nearest_enemy.name} at {nearest_enemy.position}.")
            if dx != 0:
                step = 1 if dx > 0 else -1
                blocked_horizontal = any(
                    (x, player_position.y) in self.current_room.wall_positions
                    for x in range(player_position.x + step, nearest_enemy.position.x, step)
                )
                if blocked_horizontal:
                    spatial_facts.append(
                        "A wall blocks the direct horizontal route to the nearest enemy, so changing x alone will not reach it."
                    )
            if dy != 0:
                step = 1 if dy > 0 else -1
                blocked_vertical = any(
                    (player_position.x, y) in self.current_room.wall_positions
                    for y in range(player_position.y + step, nearest_enemy.position.y, step)
                )
                if blocked_vertical:
                    spatial_facts.append(
                        "A wall blocks the direct vertical route to the nearest enemy, so changing y alone will not reach it."
                    )
            if is_adjacent(self.player, nearest_enemy, self):
                spatial_facts.append("You are already adjacent to the nearest enemy and can attack now.")
        else:
            enemy_summary = "No enemies remain in this room."
            spatial_facts.append("No enemies remain in this room.")
            if (player_position.x, player_position.y) == self.current_room.exit_tile:
                spatial_facts.append("You are standing on the exit tile right now.")
            else:
                exit_position = Position_2D(*self.current_room.exit_tile)
                dx = exit_position.x - player_position.x
                dy = exit_position.y - player_position.y
                spatial_facts.append(f"The exit tile is at {self.current_room.exit_tile}.")
            if not self.current_room_exit_locked():
                spatial_facts.append("The exit is open.")

        move_names = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            move_label = f"Move {direction_name(dx, dy)}."
            if move_label in legal_moves:
                move_names.append(f"{direction_name(dx, dy)} ({'x+1' if dx == 1 else 'x-1' if dx == -1 else 'y+1' if dy == 1 else 'y-1'})")
        spatial_facts.append(
            f"Legal movement actions from this tile: {', '.join(move_names) if move_names else 'none'}."
        )

        if any(isinstance(selection.action, EnemyStrike) for selection in self.possible_actions(self.agents[agent_id])):
            spatial_facts.append("A strike action is currently available.")
        if any(isinstance(selection.action, EnterExit) for selection in self.possible_actions(self.agents[agent_id])):
            spatial_facts.append("Enter the exit is currently available.")
        if any(isinstance(selection.action, OpenChest) for selection in self.possible_actions(self.agents[agent_id])):
            spatial_facts.append("Open chest is currently available.")

        wall_points = sorted(self.current_room.wall_positions)
        wall_summary = (
            ", ".join(str(point) for point in wall_points)
            if wall_points
            else "No internal wall blocks in this room."
        )

        exit_open = not self.current_room_exit_locked()
        exit_summary = (
            f"Exit at {self.current_room.exit_tile} is open."
            if exit_open
            else f"Exit at {self.current_room.exit_tile} is sealed until every enemy dies."
        )
        mission = (
            "Defeat the final boss, the Ash Warden. "
            "To reach the boss, you must move through the dungeon one room at a time. "
            "To leave a room, you must kill every monster in that room. "
            "The Moon Crypt contains one chest reward that you may open and select. "
            "When all monsters are dead, the exit opens. "
            "If you are standing on the open exit tile, choose Enter the exit."
        )
        return DungeonObservation(
            possible_actions=self.possible_actions(self.agents[agent_id]),
            room_name=self.current_room.name,
            room_type=self.current_room.room_type,
            room_size=(self.current_room.width, self.current_room.height),
            coordinate_system=coordinate_system,
            player_position=(player_position.x, player_position.y),
            player_hp=f"{int(player_health.health)}/{int(player_health.max_health)} HP at {self.player.position}",
            loadout_summary=(
                f"weapon: {self.sword_name} ({player_weapon_damage} damage now), "
                f"healing_potions: {self.healing_potions}, "
                f"battle_tonics: {self.battle_tonics}, "
                f"battle_buff_turns: {self.battle_tonic_turns}"
            ),
            enemy_summary=enemy_summary,
            chest_summary=chest_summary,
            wall_summary=wall_summary,
            exit_summary=exit_summary,
            exit_tile=self.current_room.exit_tile,
            spatial_facts=spatial_facts,
            mission=mission,
        )

    def environment_start_of_step(self, action_selections: list["Action_Selection"]):
        """Reset per-step bookkeeping before actions resolve."""
        self.tick += 1
        self.last_action_labels = [str(selection) for selection in action_selections]

    def environment_end_of_step(self, action_selections: list["Action_Selection"]):
        """Run enemy turns, open exits, and terminate on death or boss kill."""
        events = []

        if self.battle_tonic_turns > 0:
            self.battle_tonic_turns -= 1

        player_health = self.player.get_component(Health)
        if player_health is not None and player_health.health > 0:
            for enemy in list(self.active_enemies()):
                if player_health.health <= 0:
                    break
                enemy_health = enemy.get_component(Health)
                if enemy_health is None or enemy_health.health <= 0:
                    continue
                if is_adjacent(enemy, self.player, self):
                    enemy_damage = next(
                        (
                            action.damage_amount
                            for action in enemy.actions
                            if isinstance(action, EnemyStrike)
                        ),
                        1,
                    )
                    player_health.health -= enemy_damage
                    events.append(f"{enemy.name} hits the raider for {enemy_damage} damage.")

        if not self.active_enemies():
            events.append(f"{self.current_room.name} is clear.")
            if self.current_room.room_type == "boss":
                self.final_boss_defeated = True
                self.score = 1
                self.deliveries = 1
                self.terminations = [True for _ in self.agents]
                events.append("The Ash Warden falls. The raid is complete.")

        if player_health is not None and player_health.health <= 0:
            self.terminations = [True for _ in self.agents]
            events.append("The raider falls in battle.")

        if self.tick >= self.episode_length and not any(self.terminations):
            self.truncations = [True for _ in self.agents]
            events.append("The dungeon closes before the boss is defeated.")

        if self.pending_room_advance is not None and not any(self.terminations) and not any(self.truncations):
            next_room_name = self.rooms[self.pending_room_advance].name
            self.advance_to_next_room()
            events.append(f"You enter {next_room_name}.")
            self.pending_room_advance = None

        if action_selections:
            events.insert(0, f"Raider: {action_selections[0]}")

        self.event_log.extend(events or ["Torches flicker in the silence."])
        self.event_log = self.event_log[-6:]
        self._refresh_hud()

    def _refresh_hud(self) -> None:
        """Refresh the renderer-facing HUD strings."""
        player_health = self.player.get_component(Health)
        room_status = f"Room {self.current_room_index + 1}/{len(self.rooms)}: {self.current_room.name}"
        hp_status = f"HP {int(player_health.health)}/{int(player_health.max_health)}"
        enemy_count = len(self.active_enemies())
        exit_status = "open" if not self.current_room_exit_locked() else "locked"
        inventory_status = (
            f"{self.sword_name} dmg {self.sword_damage + (1 if self.battle_tonic_turns > 0 else 0)} | "
            f"potions {self.healing_potions} | tonics {self.battle_tonics}"
        )
        self.hud_header = f"Dungeon Raid | {room_status}"
        self.hud_lines = [
            self.current_room.lore,
            f"{hp_status} | Enemies remaining: {enemy_count} | Exit: {exit_status}",
            inventory_status,
            "Goal: clear rooms and defeat the final boss. Reward appears only on boss kill.",
            *self.event_log[-3:],
        ]

    def _reset(self, seed=None):
        """Reset the dungeon run to the entrance room."""
        player_health = self.player.get_component(Health)
        player_health.max_health = 12
        player_health.health = player_health.max_health
        self.tick = 0
        self.score = 0
        self.deliveries = 0
        self.sword_name = "Iron Sword"
        self.sword_damage = 2
        self.healing_potions = 2
        self.battle_tonics = 1
        self.battle_tonic_turns = 0
        self.battle_tonic_duration = 3
        self.chest_opened = {}
        self.chest_claimed = {}
        self.draw_grid_overlay = False
        self.event_log = ["You descend into the dungeon.", self.rooms[0].lore]
        self.final_boss_defeated = False
        self.pending_room_advance = None
        self._set_active_room(0)
        self._refresh_hud()

    def render(self) -> None:
        """Draw the current room using the attached renderer."""
        if self.renderer_impl is None:
            raise NotImplementedError("This dungeon environment does not have a renderer attached.")
        self.renderer_impl.render(self)

    def background_tiles(self) -> list[dict]:
        """Return the active room's background tile payload."""
        return list(self._room_background)

    def active_enemies(self) -> list[Entity]:
        """Return the enemies currently alive in the active room."""
        return [entity for entity in self.state.entities if "enemy" in entity.tags]

    def active_chest(self) -> Entity | None:
        """Return the active room chest, if present."""
        for entity in self.state.entities:
            if "chest" in entity.tags:
                return entity
        return None

    def current_room_chest_available(self) -> bool:
        """Return whether the active room has a chest that can still be interacted with."""
        return (
            self.active_chest() is not None
            and not self.active_enemies()
            and not self.chest_claimed.get(self.current_room.room_id, False)
        )

    def current_chest_summary(self) -> str:
        """Describe the active room chest and its current state."""
        chest = self.active_chest()
        if chest is None:
            return "No chest in this room."
        if self.active_enemies():
            return f"{chest.name} at {chest.position} is sealed until the room is clear."
        if not self.chest_opened.get(self.current_room.room_id, False):
            return f"{chest.name} at {chest.position} is closed."
        if self.chest_claimed.get(self.current_room.room_id, False):
            return f"{chest.name} at {chest.position} has already been looted."
        options = ", ".join(label for _, label in self.current_room.chest_rewards)
        return f"{chest.name} at {chest.position} is open. Choices: {options}."

    def apply_chest_reward(self, reward_id: str) -> None:
        """Apply the selected chest reward to the raider."""
        player_health = self.player.get_component(Health)
        if reward_id == "moonblade":
            self.sword_name = "Moonblade"
            self.sword_damage += 1
        elif reward_id == "vitality_flask":
            player_health.max_health += 2
            player_health.health = min(player_health.max_health, player_health.health + 2)
            self.healing_potions += 1
        elif reward_id == "war_drum":
            self.battle_tonics += 2
            self.battle_tonic_duration = 5

    def current_room_exit_locked(self) -> bool:
        """Return whether the current room exit is still sealed."""
        return bool(self.active_enemies())
