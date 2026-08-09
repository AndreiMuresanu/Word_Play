from __future__ import annotations

import random

from word_play.core import (
    Action,
    Action_Validation,
    Component,
    Entity,
    Environment,
    Target_Is_Nearby,
    Target_Not_Self,
)
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.movement.simple_2d_grid import Position_2D
from word_play.presets.systems.inventory import Consume_Held_Item, Inventory
from word_play.presets.systems.respawnable import Respawnable
from word_play.presets.systems.reward import award_reward
from word_play.presets.systems.role import Role

from benchmarks.text_mp.core.timing import normalized_probability, normalized_steps


FRAMES_TILL_APPLE_RESPAWN = normalized_steps(50)
FRAMES_TILL_RESPAWN = normalized_steps(100)
FRAMES_TILL_HUNGRY = normalized_steps(200)
FLORA_PROBABILITY = normalized_probability(0.2)
FRUIT_KIND_WEIGHTS = [
    1.0 - FLORA_PROBABILITY,
    FLORA_PROBABILITY * 0.75,
    FLORA_PROBABILITY * 0.05,
    FLORA_PROBABILITY * 0.15,
    FLORA_PROBABILITY * 0.05,
]


def daycare_events(env: Environment) -> list[str]:
    if getattr(env, "_daycare_events_step", None) != env.cur_step:
        env.daycare_events = []
        env._daycare_events_step = env.cur_step
    return env.daycare_events


class FruitPatch(Component):
    def __init__(self):
        super().__init__(tags=["fruit_patch"])
        self.kind: str | None = None
        self.fruit_available = False
        self.respawn_timer = 0

    @property
    def fruit_name(self) -> str | None:
        if not self.kind:
            return None
        if "banana" in self.kind:
            return "Banana"
        if "apple" in self.kind:
            return "Apple"
        return None

    @property
    def is_tree(self) -> bool:
        return bool(self.kind and "tree" in self.kind)

    def post_initialization(self) -> None:
        if self.kind is None:
            self.kind = random.choices(
                ["empty", "apple_tree", "apple_shrub", "banana_tree", "banana_shrub"],
                weights=FRUIT_KIND_WEIGHTS,
                k=1,
            )[0]
            self.fruit_available = self.kind != "empty"
        self._sync_state()

    def _sync_state(self) -> None:
        if self.kind == "empty":
            self.entity.name = "Empty Fruit Patch"
        else:
            fruit = self.fruit_name or "Fruit"
            plant = "Tree" if self.is_tree else "Shrub"
            availability = " with fruit" if self.fruit_available else " without fruit"
            self.entity.name = f"{fruit} {plant}{availability}"

    def can_grasp(self, actor: Entity) -> bool:
        if not self.fruit_available or self.kind == "empty":
            return False
        state = actor.get_component(AvatarState)
        if state is None:
            return False
        if state.role == "parent":
            return True
        return not self.is_tree

    def grasp_success_probability(self, actor: Entity) -> float:
        state = actor.get_component(AvatarState)
        return 1.0 if (state is not None and state.role == "parent") else 0.3

    def harvest(self) -> str | None:
        fruit_name = self.fruit_name
        if fruit_name is None or not self.fruit_available:
            return None
        self.fruit_available = False
        self.respawn_timer = FRAMES_TILL_APPLE_RESPAWN
        self._sync_state()
        return fruit_name

    def pre_actions_step(self, env: Environment) -> None:
        if self.kind == "empty" or self.fruit_available or self.respawn_timer <= 0:
            return
        self.respawn_timer -= 1
        if self.respawn_timer <= 0:
            self.fruit_available = True
            self._sync_state()


class AvatarState(Role):
    def __init__(self, role: str):
        super().__init__(role)
        self.hunger_timer = 0
        self.is_hungry = False

    @property
    def active(self) -> bool:
        respawnable = self.entity.get_component(Respawnable)
        return respawnable is None or respawnable.active

    def enter_respawn(self, env: Environment) -> None:
        self.hunger_timer = 0
        self.is_hungry = False
        inventory = self.entity.get_component(Inventory)
        if inventory is not None:
            for item in inventory.contents.copy():
                inventory.remove(item)
                if item in env.state.entities:
                    env.destroy_entity(item)
        respawnable = self.entity.get_component(Respawnable)
        if respawnable is not None:
            respawnable.remove_temporarily(FRAMES_TILL_RESPAWN)
        daycare_events(env).append(f"{self.entity.name} went hungry and is respawning.")

    def reset_after_eating(self) -> None:
        self.hunger_timer = 0
        self.is_hungry = False

    def pre_actions_step(self, env: Environment) -> None:
        if not self.active:
            return
        self.hunger_timer += 1
        self.is_hungry = self.hunger_timer >= FRAMES_TILL_HUNGRY
        if self.is_hungry:
            self.enter_respawn(env)


class ActorCanAct(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        state = actor.get_component(AvatarState)
        return state is not None and state.active


class Grasp(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                ActorCanAct(),
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(FruitPatch),
            ]
        )

    def is_valid(self, actor, target, env, kwargs="unconsidered") -> bool:
        if not super().is_valid(actor, target, env, kwargs=kwargs):
            return False
        inventory = actor.get_component(Inventory)
        patch = target.get_component(FruitPatch)
        return (
            inventory is not None
            and patch is not None
            and inventory.has_space()
            and patch.can_grasp(actor)
        )

    def exec_action(self, actor, target, env, kwargs=None):
        inventory = actor.get_component(Inventory)
        assert inventory is not None
        patch = target.get_component(FruitPatch)
        assert patch is not None
        if random.random() > patch.grasp_success_probability(actor):
            daycare_events(env).append(f"{actor.name} failed to grasp fruit from {target.name}.")
            return {"success": False, "reason": "grasp_failed"}
        fruit_name = patch.harvest()
        if fruit_name is None:
            return {"success": False, "reason": "no_fruit"}
        fruit = Entity(
            name=fruit_name,
            position=Position_2D(actor.position.x, actor.position.y),
            tags=["fruit", fruit_name.lower()],
        )
        inventory.store(fruit, env)
        daycare_events(env).append(f"{actor.name} grasped a {fruit_name} from {target.name}.")
        return {"success": True, "grasped": fruit_name, "from": target.name}

    def action_description_text(self, actor, target, env) -> str:
        return f"Grasp fruit from {target.name}."


class Eating(Component):
    def __init__(self):
        super().__init__(
            actions=[
                Consume_Held_Item(
                    ["fruit"],
                    action_name="Eat your held fruit.",
                    validation_rules=[ActorCanAct()],
                    on_consumed=Eating._on_consumed,
                )
            ]
        )

    @staticmethod
    def _on_consumed(actor: Entity, target: Entity, env: Environment, item: Entity, reward: float) -> None:
        state = actor.get_component(AvatarState)
        if state is None:
            return
        actual_reward = 1.0 if state.role == "parent" else (1.0 if "banana" in item.tags else 0.0)
        award_reward(env, actor, actual_reward)
        state.reset_after_eating()
        daycare_events(env).append(f"{actor.name} ate a {item.name} for +{actual_reward:g} reward.")
