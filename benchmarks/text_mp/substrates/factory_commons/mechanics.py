from __future__ import annotations

from word_play.core import Action, Component, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.movement.simple_2d_grid import Collidable, Position_2D
from word_play.presets.systems.inventory import Inventory


def factory_events(env: Environment) -> list[str]:
    if getattr(env, "_factory_events_step", None) != env.cur_step:
        env.tick = env.cur_step
        env.factory_events = []
        env._factory_events_step = env.cur_step
    return env.factory_events


class FactoryCube(Component):
    def __init__(self, cube_type: str = "blue", live: bool = True):
        super().__init__(tags=["cube", cube_type] if live else [])
        self.cube_type = cube_type
        self.live = live


class FactoryHopper(Component):
    def __init__(self, output_count: int = 1):
        super().__init__(tags=["hopper"])
        self.output_count = output_count


class DepositFactoryCube(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(FactoryHopper),
            ]
        )

    def is_valid(self, actor, target, env, kwargs="unconsidered") -> bool:
        return super().is_valid(actor, target, env, kwargs=kwargs) and self._carried_cube(actor) is not None

    def exec_action(self, actor, target, env, kwargs=None):
        factory_events(env)
        inventory = actor.get_component(Inventory)
        cube = self._carried_cube(actor)
        if inventory is None or cube is None:
            return {"success": False}

        inventory.remove(cube)
        if cube in env.state.entities:
            env.destroy_entity(cube)

        hopper = target.get_component(FactoryHopper)
        for offset in range(hopper.output_count):
            env.instantiate_entity(
                Entity(
                    name="Apple",
                    position=self._apple_spawn_position(env, target.position, offset),
                    tags=["apple", "food"],
                )
            )
        env.factory_events.append(f"{actor.name} deposited a cube into {target.name}.")
        return {"deposited": cube.name, "apples": hopper.output_count}

    def _carried_cube(self, actor: Entity) -> Entity | None:
        inventory = actor.get_component(Inventory)
        if inventory is None:
            return None
        return next((item for item in inventory.contents if item.get_component(FactoryCube) is not None), None)

    def _apple_spawn_position(self, env: Environment, hopper_position: Position_2D, offset: int) -> Position_2D:
        candidates = (
            Position_2D(hopper_position.x + 1, hopper_position.y + offset),
            Position_2D(hopper_position.x - 1, hopper_position.y + offset),
            Position_2D(hopper_position.x, hopper_position.y + 1 + offset),
            Position_2D(hopper_position.x, hopper_position.y - 1 - offset),
            Position_2D(hopper_position.x + 1 + offset, hopper_position.y),
            Position_2D(hopper_position.x - 1 - offset, hopper_position.y),
        )
        return next(
            (
                position
                for position in candidates
                if not any(
                    entity.position == position
                    and (entity.has_component(Collidable) or "apple" in entity.tags)
                    for entity in env.state.entities
                )
            ),
            hopper_position,
        )

    def action_description_text(self, actor, target, env):
        return f"Deposit a cube into {target.name}."
