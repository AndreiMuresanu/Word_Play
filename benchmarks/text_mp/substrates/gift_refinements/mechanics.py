from __future__ import annotations

import random

from word_play.core import Action, Action_Validation, Component, Entity, Environment, Target_Is_Self, Target_Not_Self
from word_play.presets.action_validations import Target_Within_Range
from word_play.presets.systems.reward import award_reward

from benchmarks.text_mp.core.timing import BENCHMARK_STEPS, normalized_probability, normalized_steps


NUM_TOKEN_TYPES = 3
MAX_TOKENS_PER_TYPE = 15
TOKEN_REGROW_PROBABILITY = normalized_probability(0.0002)
GIFT_RANGE = 5
GIFT_MULTIPLIER = 5
SUCCESSFUL_GIFT_REWARD = 10.0
MIN_EPISODE_LENGTH = normalized_steps(1000)
INTERVAL_LENGTH = normalized_steps(100)
TERMINATION_PROBABILITY = 0.2


def gift_refinements_events(env: Environment) -> list[str]:
    if getattr(env, "_gift_refinements_events_step", None) != env.cur_step:
        env.tick = env.cur_step
        env.gift_refinements_events = []
        env._gift_refinements_events_step = env.cur_step
    return env.gift_refinements_events


class TokenInventory(Component):
    def __init__(self):
        super().__init__()
        self.tokens: list[int] = [0] * NUM_TOKEN_TYPES

    @property
    def raw(self) -> int:
        return self.tokens[0]

    @property
    def refined(self) -> int:
        return self.tokens[1]

    @property
    def finest(self) -> int:
        return self.tokens[2]

    def total(self) -> int:
        return sum(self.tokens)

    def add(self, token_type: int, amount: int) -> int:
        space = MAX_TOKENS_PER_TYPE - self.tokens[token_type]
        added = max(0, min(space, amount))
        self.tokens[token_type] += added
        return added

    def remove(self, token_type: int, amount: int = 1) -> bool:
        if self.tokens[token_type] < amount:
            return False
        self.tokens[token_type] -= amount
        return True

    def rawest_available_type(self) -> int | None:
        for token_type, count in enumerate(self.tokens):
            if count > 0:
                return token_type
        return None

    def can_receive(self, token_type: int, amount: int) -> bool:
        return self.tokens[token_type] + amount <= MAX_TOKENS_PER_TYPE

    def consume_all(self) -> int:
        total = self.total()
        self.tokens = [0] * NUM_TOKEN_TYPES
        return total


class TokenPatch(Component):
    def __init__(self):
        super().__init__(tags=["token_patch"])
        self.available = False

    def post_initialization(self) -> None:
        self.available = random.random() < TOKEN_REGROW_PROBABILITY * 10
        self._sync()

    def pre_actions_step(self, env: Environment) -> None:
        gift_refinements_events(env)
        if not self.available and random.random() < TOKEN_REGROW_PROBABILITY:
            self.available = True
            self._sync()

    def post_actions_step(self, env: Environment) -> None:
        if not self.available:
            return
        for agent in env.agents:
            if agent.position != self.entity.position:
                continue
            inventory = agent.get_component(TokenInventory)
            if inventory is not None and inventory.add(0, 1) > 0:
                self.available = False
                self._sync()
                gift_refinements_events(env).append(f"{agent.name} picked up a raw token.")
            return

    def _sync(self) -> None:
        self.entity.name = "Raw Token" if self.available else "Empty Token Site"
        for tag in ("raw_token", "empty_token_site"):
            while tag in self.entity.tags:
                self.entity.tags.remove(tag)
        self.entity.tags.append("raw_token" if self.available else "empty_token_site")


class HasAnyToken(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        inventory = actor.get_component(TokenInventory)
        return inventory is not None and inventory.total() > 0


class TargetCanReceiveGift(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        actor_inv = actor.get_component(TokenInventory)
        target_inv = target_entity.get_component(TokenInventory)
        if actor_inv is None or target_inv is None:
            return False
        token_type = actor_inv.rawest_available_type()
        if token_type is None:
            return False
        receive_type = min(token_type + 1, NUM_TOKEN_TYPES - 1)
        amount = GIFT_MULTIPLIER if token_type < NUM_TOKEN_TYPES - 1 else 1
        return target_inv.can_receive(receive_type, amount)


class RefineAndGift(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Within_Range(GIFT_RANGE),
                HasAnyToken(),
                TargetCanReceiveGift(),
            ]
        )

    def exec_action(self, actor: Entity, target: Entity, env: Environment, kwargs=None):
        actor_inv = actor.get_component(TokenInventory)
        target_inv = target.get_component(TokenInventory)
        token_type = actor_inv.rawest_available_type()
        receive_type = min(token_type + 1, NUM_TOKEN_TYPES - 1)
        amount = GIFT_MULTIPLIER if token_type < NUM_TOKEN_TYPES - 1 else 1
        actor_inv.remove(token_type)
        added = target_inv.add(receive_type, amount)
        award_reward(env, actor, SUCCESSFUL_GIFT_REWARD)
        gift_refinements_events(env).append(
            f"{actor.name} gifted a type-{token_type} token to {target.name}; "
            f"{target.name} received {added} type-{receive_type} token(s) for +{SUCCESSFUL_GIFT_REWARD:g}."
        )
        return {"gifted_type": token_type, "received_type": receive_type, "received_amount": added}

    def action_description_text(self, actor: Entity, target: Entity, env: Environment) -> str:
        return f"Refine and gift your rawest token to {target.name}."


class ConsumeTokens(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self(), HasAnyToken()])

    def exec_action(self, actor: Entity, target: Entity, env: Environment, kwargs=None):
        inventory = actor.get_component(TokenInventory)
        reward = inventory.consume_all()
        award_reward(env, actor, float(reward))
        gift_refinements_events(env).append(
            f"{actor.name} consumed all tokens for +{reward}."
        )
        return {"consumed": reward, "reward": reward}

    def action_description_text(self, actor: Entity, target: Entity, env: Environment) -> str:
        return "Consume all tokens for reward."


class GiftRefinementManager(Component):
    def pre_actions_step(self, env: Environment) -> None:
        gift_refinements_events(env)

    def post_actions_step(self, env: Environment) -> None:
        next_step = env.cur_step + 1
        max_steps = getattr(env, "max_episode_steps", BENCHMARK_STEPS)
        if next_step >= max_steps:
            env.truncations = [True for _ in env.agents]
            return
        if next_step < MIN_EPISODE_LENGTH:
            return
        if next_step % INTERVAL_LENGTH == 0 and random.random() < TERMINATION_PROBABILITY:
            env.truncations = [True for _ in env.agents]
