from __future__ import annotations

import random

from word_play.core import Component, Environment
from word_play.presets.systems.preferences import Preference
from word_play.presets.systems.reward import award_reward

from benchmarks.text_mp.core.timing import BENCHMARK_STEPS, normalized_probability, normalized_steps


MIN_EPISODE_LENGTH = normalized_steps(300)
INTERVAL_LENGTH = normalized_steps(100)
TERMINATION_PROBABILITY = 0.05
COIN_REGROW_PROBABILITY = normalized_probability(0.0005)


def coins_events(env: Environment) -> list[str]:
    if getattr(env, "_coins_events_step", None) != env.cur_step:
        env.tick = env.cur_step
        env.coins_events = []
        env._coins_events_step = env.cur_step
    return env.coins_events


class CoinPatch(Component):
    def __init__(self, coin_color: str):
        super().__init__(tags=["coin", f"{coin_color}_coin"])
        self.coin_color = coin_color
        self.consumed = False

    def pre_actions_step(self, env: Environment) -> None:
        coins_events(env)
        if self.consumed and random.random() < COIN_REGROW_PROBABILITY:
            self.consumed = False
            self._sync_tags()
            coins_events(env).append(f"A {self.coin_color} coin reappeared.")

    def post_actions_step(self, env: Environment) -> None:
        if not self.consumed:
            self._collect(env)
        self._maybe_end_episode(env)

    def _collect(self, env: Environment) -> None:
        for agent in env.agents:
            if agent.position != self.entity.position:
                continue
            preference = agent.get_component(Preference)
            reward = preference.reward_for(self.entity) if preference is not None else 1.0
            is_mismatch = preference is not None and not preference.is_preferred(self.entity)
            # evaluate tags and apply penalty before _sync_tags removes coin tags
            if preference is not None:
                preference.apply_mismatch_penalty(agent, self.entity, env)
            self.consumed = True
            self._sync_tags()
            award_reward(env, agent, reward)
            if is_mismatch:
                coins_events(env).append(
                    f"{agent.name} took a {self.coin_color} coin (+{reward:g}); opponent loses 2."
                )
            else:
                coins_events(env).append(
                    f"{agent.name} collected a {self.coin_color} coin for +{reward:g}."
                )
            break

    def _sync_tags(self) -> None:
        coin_tags = ["coin", f"{self.coin_color}_coin"]
        for tag in [*coin_tags, "empty_coin_site"]:
            while tag in self.entity.tags:
                self.entity.tags.remove(tag)
        if self.consumed:
            self.entity.name = "Empty Coin Site"
            self.entity.tags.append("empty_coin_site")
        else:
            self.entity.name = f"{self.coin_color.title()} Coin"
            for tag in coin_tags:
                self.entity.tags.append(tag)

    def _maybe_end_episode(self, env: Environment) -> None:
        if getattr(env, "_coins_end_checked_step", None) == env.cur_step:
            return
        env._coins_end_checked_step = env.cur_step
        next_step = env.cur_step + 1
        max_steps = getattr(env, "max_episode_steps", BENCHMARK_STEPS)
        if next_step >= max_steps:
            env.truncations = [True for _ in env.agents]
            return
        if next_step < MIN_EPISODE_LENGTH:
            return
        if next_step % INTERVAL_LENGTH == 0 and random.random() < TERMINATION_PROBABILITY:
            env.truncations = [True for _ in env.agents]
