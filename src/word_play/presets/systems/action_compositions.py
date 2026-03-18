from __future__ import annotations

from typing import TYPE_CHECKING

from word_play.core import Action

if TYPE_CHECKING:
    from word_play.core import Entity, Environment


class Action_Chain(Action):
    # TODO: ANDREI: this class is not general enough to support full action flexability, since all actions will have the
    #       same targets. E.g., you won't be able to move and attack or heal yourself and attack.
    #       NOTE: actually, I think are also two types of action composition: parallel actions and sequential actions. And
    #       you can, for example, have a sequence of parallel actions or a parallelization of sequential actions. Parallel
    #       actions execute at the same time and sequential actions execute in sequence. However, in our environment we
    #       distinctly forbid parallel logic, i.e., only a single action may execute at one time. This means that only
    #       sequential actions (action sequences/action chains) exist. For these chains, the question of how to implement
    #       their is_valid method arises. E.g., should is_valid. Continuing discussion in notes...
    # TODO: ANDREI: we could find all possible targets for each non-first action in the chain, but we would require
    #       additional decision steps to choose between them. We could enumerate the full tree of possible action chains to
    #       the agent at the start of the step and have each of these be distinct actions, but the chain could be huge...
    # TODO: doesn't currently check for kwargs being valid and doesn't take as input a list of kwargs.
    def __init__(self, composed_actions: list[Action]):
        assert len(composed_actions) > 0, "Action_Chain requires at least 1 actions be initialized."
        self.composed_actions = composed_actions

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        for action in self.composed_actions:
            if action.is_valid(actor, target_entity, env):
                action(actor, target_entity, env)

    def is_valid(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered"
    ) -> bool:
        return self.composed_actions[0].is_valid(actor, target_entity, env, kwargs=kwargs)
