from __future__ import annotations

from typing import Callable

from word_play.core import Action, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Doesnt_Have_Tag, Target_Has_Component
from word_play.presets.systems.health import Health


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
        visible_step = getattr(env, "cur_step", 0) + 1
        env.render_state.emit("hit", entity=target_entity, step=visible_step, scale=0.75)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"{self.name} {target_entity.name}"
