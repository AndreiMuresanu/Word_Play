from __future__ import annotations

from copy import deepcopy

from word_play.core import Action, Component, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.renderers import Renderable


def _container_comp(entity: Entity) -> "Container | None":
    return entity.get_component(Container)


def _set_container_item_visibility(item: Entity, *, visible: bool) -> None:
    renderable = item.get_component(Renderable)
    if renderable is not None:
        renderable.visible = visible


class Container(Component):
    """Store real entity instances inside a container until it is opened."""

    def __init__(self, contents: list[Entity], *, starts_open: bool = False):
        super().__init__(actions=[Open_Container()])
        self.contents = contents
        self.starts_open = starts_open
        self.is_open = starts_open

    def on_instantiation(self, env: Environment, seed: int | None) -> None:
        self._sync_contents_to_env(env)

    def post_actions_step(self, env: Environment) -> None:
        for item in self.contents:
            if item in env.state.entities and "hidden_in_container" in item.tags:
                item.position = deepcopy(self.entity.position)

    def visible_contents(self) -> list[Entity]:
        return [item for item in self.contents if "hidden_in_container" not in item.tags and "in_inventory" not in item.tags]

    def reveal_contents(self) -> None:
        self.is_open = True
        for item in self.contents:
            if "hidden_in_container" in item.tags:
                item.tags.remove("hidden_in_container")
            _set_container_item_visibility(item, visible=True)

    def remove_item(self, item: Entity) -> bool:
        """Remove an item from this container's contents. Returns True if removed."""
        if item in self.contents:
            self.contents.remove(item)
            if "in_container" in item.tags:
                item.tags.remove("in_container")
            return True
        return False

    def _sync_contents_to_env(self, env: Environment) -> None:
        for item in self.contents:
            item.position = deepcopy(self.entity.position)
            if "in_container" not in item.tags:
                item.tags.append("in_container")
            if self.is_open:
                if "hidden_in_container" in item.tags:
                    item.tags.remove("hidden_in_container")
            elif "hidden_in_container" not in item.tags:
                item.tags.append("hidden_in_container")
            _set_container_item_visibility(item, visible=self.is_open)
            if item not in env.state.entities:
                env.instantiate_entity(item)


class Open_Container(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(Container),
            ]
        )

    def is_valid(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered"
    ) -> bool:
        if not super().is_valid(actor, target_entity, env, kwargs=kwargs):
            return False
        container = _container_comp(target_entity)
        return container is not None and not container.is_open

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        container = _container_comp(target_entity)
        assert container is not None
        container.reveal_contents()
        return {"opened": True, "revealed_items": [item.name for item in container.visible_contents()]}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Open {target_entity.name}."
