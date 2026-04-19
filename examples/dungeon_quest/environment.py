"""Dungeon quest environment - Simple open arena with enemies."""

from word_play.core import Entity, Environment, Observation
from word_play.presets.action_policies.follow_action_sequence import Follow_Action_Sequence
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.environments.simple_env_reset_mixin import Simple_Env_Reset_Mixin
from word_play.presets.movement.common import Collidable
from word_play.presets.movement.simple_2d_grid import (
    INFINITE_2D_MOVEMENT_SYSTEM,
    Move_Down,
    Move_Left,
    Move_Right,
    Move_Up,
    Position_2D,
    positions_are_adjacent_2d,
)
from word_play.presets.observation.simple_observation import Simple_Observation
from word_play.presets.renderers import Renderable
from word_play.presets.reward_functions import zero_reward_func
from word_play.presets.systems import Attack, Do_Nothing, Health


PLAYER_SPRITE = "src/characters/humanoids/human/farmer_man.png"
GOBLIN_SPRITE = "src/characters/humanoids/goblinoid/goblin.png"
SKELETON_SPRITE = "src/characters/monsters/undead/skeleton.png"
BOSS_SPRITE = "src/characters/monsters/demonic/horned_devil.png"

WALL_SET = "src/world_tiles/indoors/wall_sets/bright_brick_wall"
FLOOR_SPRITE = "src/world_tiles/indoors/floors/night_brick_floor_c.png"


class DungeonRaidEnv(Simple_Env_Reset_Mixin, Environment):
    """Dungeon raid - defeat all enemies then the boss in an open arena."""

    def __init__(self, renderer=None, episode_length: int = 120):
        self.renderer_impl = renderer
        self.episode_length = episode_length
        self.sight_radius = 4
        self.hud_sidebar_width = 380
        self.hud_sidebar_header = "Agent View"
        self.hud_sidebar_lines = ["Waiting for first policy step..."]
        self.hud_sidebar_selected_action = ["Chosen Action:", "(pending)"]
        self.hud_sidebar_actions = ["Possible Actions:", "(pending)"]
        self.tick = 0
        self.score = 0
        self.deliveries = 0
        self.final_boss_defeated = False
        self.event_log: list[str] = []

        # Environment layout for background rendering
        self.width = 15
        self.height = 11
        self.wall_positions = {
            # Just the outer border
            *{(x, 0) for x in range(15)},
            *{(x, 10) for x in range(15)},
            *{(0, y) for y in range(11)},
            *{(14, y) for y in range(11)},
        }
        self.wall_set = WALL_SET
        self.floor_sprite = FLOOR_SPRITE

                # Player at entry (moved closer to center so enemies are visible)
        self.player = Entity(
            name="Raider",
            position=Position_2D(4, 5),
            tags=["agent", "hero", "player"],
            actions=[
                Move_Left(),
                Move_Right(),
                Move_Up(),
                Move_Down(),
                Attack(name="Strike", damage_amount=2, target_is_nearby=positions_are_adjacent_2d),
                Do_Nothing(),
            ],
            components=[
                Health(max_health=15, starting_health=15),
                Collidable(collidable_tags=["wall", "enemy"]),
                Renderable(sprite_path=PLAYER_SPRITE, z_index=10, sight_radius=4),
            ],
        )
        self.player.is_agent = True

        # Regular enemies scattered in the room
        # Enemy 1: Near entry
        goblin_scout = Entity(
            name="Goblin Scout",
            position=Position_2D(5, 3),
            tags=["enemy", "minion"],
            actions=[
                Move_Left(),
                Move_Right(),
                Move_Up(),
                Move_Down(),
                Attack(name="Strike", damage_amount=1),
                Do_Nothing(),
            ],
            components=[
                Follow_Action_Sequence([(Do_Nothing, None)]),
                Health(max_health=3, starting_health=3),
                Collidable(collidable_tags=["wall", "hero", "enemy"]),
                Renderable(sprite_path=GOBLIN_SPRITE, z_index=9),
            ],
        )

        # Enemy 2: Middle left
        bone_guard_a = Entity(
            name="Bone Guard",
            position=Position_2D(6, 7),
            tags=["enemy", "minion"],
            actions=[
                Move_Left(),
                Move_Right(),
                Move_Up(),
                Move_Down(),
                Attack(name="Strike", damage_amount=1),
                Do_Nothing(),
            ],
            components=[
                Follow_Action_Sequence([(Do_Nothing, None)]),
                Health(max_health=4, starting_health=4),
                Collidable(collidable_tags=["wall", "hero", "enemy"]),
                Renderable(sprite_path=SKELETON_SPRITE, z_index=9),
            ],
        )

        # Enemy 3: Middle right
        bone_guard_b = Entity(
            name="Bone Guard",
            position=Position_2D(9, 4),
            tags=["enemy", "minion"],
            actions=[
                Move_Left(),
                Move_Right(),
                Move_Up(),
                Move_Down(),
                Attack(name="Strike", damage_amount=1),
                Do_Nothing(),
            ],
            components=[
                Follow_Action_Sequence([(Do_Nothing, None)]),
                Health(max_health=4, starting_health=4),
                Collidable(collidable_tags=["wall", "hero", "enemy"]),
                Renderable(sprite_path=SKELETON_SPRITE, z_index=9),
            ],
        )

        # Enemy 4: Near boss area
        goblin_warrior = Entity(
            name="Goblin Warrior",
            position=Position_2D(10, 6),
            tags=["enemy", "minion"],
            actions=[
                Move_Left(),
                Move_Right(),
                Move_Up(),
                Move_Down(),
                Attack(name="Strike", damage_amount=2),
                Do_Nothing(),
            ],
            components=[
                Follow_Action_Sequence([(Do_Nothing, None)]),
                Health(max_health=5, starting_health=5),
                Collidable(collidable_tags=["wall", "hero", "enemy"]),
                Renderable(sprite_path=GOBLIN_SPRITE, z_index=9),
            ],
        )

        # BOSS at far end
        ash_warden = Entity(
            name="Ash Warden",
            position=Position_2D(12, 5),
            tags=["enemy", "boss"],
            actions=[
                Move_Left(),
                Move_Right(),
                Move_Up(),
                Move_Down(),
                Attack(name="Strike", damage_amount=3),
                Do_Nothing(),
            ],
            components=[
                Follow_Action_Sequence([(Do_Nothing, None)]),
                Health(max_health=12, starting_health=12),
                Collidable(collidable_tags=["wall", "hero", "enemy"]),
                Renderable(sprite_path=BOSS_SPRITE, z_index=9),
            ],
        )

        # Collision-only walls (invisible, not rendered - background handles visuals)
        walls = [
            Entity(
                name=f"Wall {x},{y}",
                position=Position_2D(x, y),
                tags=["wall"],
                components=[
                    Collidable(collidable_tags=["hero", "enemy"]),
                    Renderable(sprite_path="", visible=False),
                ],
            )
            for x, y in sorted(self.wall_positions)
        ]

        super().__init__(
            description="Dungeon Raid: Defeat all minions, then slay the Ash Warden!",
            entities=[
                self.player,
                *walls,
                goblin_scout,
                bone_guard_a,
                bone_guard_b,
                goblin_warrior,
                ash_warden,
            ],
            movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
            reward_func=zero_reward_func,
            entity_order=entity_definition_order,
        )

    def post_init(self):
        """Set up initial state."""
        self.event_log = [
            "You enter the dungeon arena.",
            "Defeat all minions, then face the Ash Warden!",
        ]
        Simple_Env_Reset_Mixin.post_init(self)

    def _minions_alive(self) -> int:
        """Count remaining minion enemies (non-boss)."""
        return len([e for e in self.state.entities
                    if "enemy" in e.tags and "boss" not in e.tags
                    and e.get_component(Health).health > 0])

    def observe(self, agent_id: int) -> Observation:
        agent = self.agents[agent_id]
        # Get entities within sight_radius (Manhattan distance <= sight_radius)
        visible_entities = [
            entity
            for entity in self.state.entities
            if entity is not agent
            and abs(int(entity.position.x) - int(agent.position.x)) + abs(int(entity.position.y) - int(agent.position.y)) <= self.sight_radius
            and "floor" not in entity.tags  # Don't show floor tiles
        ]
        return Simple_Observation(
            possible_actions=self.possible_actions(agent),
            nearby_entities=visible_entities,
            agent=agent,
            last_reward=0.0 if self.last_rewards[agent_id] is None else self.last_rewards[agent_id],
            info=self.infos[agent_id],
        )

    def environment_start_of_step(self, action_selections: list["Action_Selection"]):
        self.tick += 1

    def environment_end_of_step(self, action_selections: list["Action_Selection"]):
        """Run enemy counterattacks and check game state."""
        events = []

        player_health = self.player.get_component(Health)
        if player_health is not None and player_health.health > 0:
            for enemy in list(self.active_enemies()):
                if player_health.health <= 0:
                    break
                enemy_health = enemy.get_component(Health)
                if enemy_health is None or enemy_health.health <= 0:
                    continue
                if positions_are_adjacent_2d(enemy.position, self.player.position):
                    enemy_damage = next(
                        (a.damage_amount for a in enemy.actions if isinstance(a, Attack)),
                        1,
                    )
                    player_health.health -= enemy_damage
                    events.append(f"{enemy.name} hits for {enemy_damage} damage.")

        # Check minion count
        minions_left = self._minions_alive()
        if minions_left == 0 and not self.final_boss_defeated:
            events.append("All minions defeated! The Ash Warden blocks the exit!")

        # Check boss defeated
        boss = next((e for e in self.state.entities if "boss" in e.tags), None)
        if boss is not None:
            boss_health = boss.get_component(Health)
            if boss_health is not None and boss_health.health <= 0:
                self.final_boss_defeated = True
                self.score = 1
                self.deliveries = 1
                self.terminations = [True for _ in self.agents]
                events.append("The Ash Warden falls! Victory!")

        # Check player death
        if player_health is not None and player_health.health <= 0:
            self.terminations = [True for _ in self.agents]
            events.append("You have fallen.")

        # Check timeout
        if self.tick >= self.episode_length and not any(self.terminations):
            self.truncations = [True for _ in self.agents]
            events.append("Time runs out.")

        if action_selections:
            events.insert(0, f"Raider: {action_selections[0]}")

        self.event_log.extend(events or ["..."])
        self.event_log = self.event_log[-6:]

    def active_enemies(self) -> list[Entity]:
        """Return enemies currently alive."""
        return [entity for entity in self.state.entities
                if "enemy" in entity.tags
                and entity.get_component(Health).health > 0]

    def health_summary(self) -> str:
        player_health = self.player.get_component(Health)
        player_hp = "?"
        if player_health is not None:
            player_hp = f"{player_health.health}/{player_health.max_health}"

        minions = self._minions_alive()
        boss_alive = any("boss" in e.tags and e.get_component(Health).health > 0
                         for e in self.state.entities)

        return f"HP {player_hp} | Minions: {minions} | Boss: {'Alive' if boss_alive else 'Dead'}"


__all__ = ["DungeonRaidEnv"]
