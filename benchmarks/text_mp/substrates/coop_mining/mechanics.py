from __future__ import annotations

import random

from word_play.core import Action, Component, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.systems.cooldown import Action_On_Cooldown, Cooldown
from word_play.presets.systems.coordinated_action import Coordinated_Action
from word_play.presets.systems.reward import award_reward

from benchmarks.text_mp.core.timing import BENCHMARK_STEPS, normalized_probability, normalized_steps


MINE_COOLDOWN = normalized_steps(3)
IRON_REWARD = 1.0
GOLD_REWARD = 8.0
GOLD_MINERS_REQUIRED = 2
IRON_REGROW_PROB = normalized_probability(0.0002)
GOLD_REGROW_PROB = normalized_probability(0.00008)
MIN_EPISODE_LENGTH = normalized_steps(1000)
INTERVAL_LENGTH = normalized_steps(100)
TERMINATION_PROBABILITY = 0.2


def coop_mining_events(env: Environment) -> list[str]:
    if getattr(env, "_coop_mining_events_step", None) != env.cur_step:
        env.tick = env.cur_step
        env.coop_mining_events = []
        env._coop_mining_events_step = env.cur_step
    return env.coop_mining_events


class OreNode(Component):
    def __init__(self, ore_type: str | None = None):
        super().__init__(tags=["ore_node"])
        self.ore_type = ore_type
        self.depleted = False

    def post_initialization(self) -> None:
        if self.ore_type is None:
            self.ore_type = "gold" if random.random() < 0.2 else "iron"
        self._sync_tags()

    def pre_actions_step(self, env: Environment) -> None:
        coop_mining_events(env)
        if not self.depleted:
            return
        if random.random() < GOLD_REGROW_PROB:
            self.depleted = False
            self.ore_type = "gold"
            self._sync_tags()
            coop_mining_events(env).append(f"{self.entity.name} regenerated as gold.")
        elif random.random() < IRON_REGROW_PROB:
            self.depleted = False
            self.ore_type = "iron"
            self._sync_tags()
            coop_mining_events(env).append(f"{self.entity.name} regenerated as iron.")

    def post_actions_step(self, env: Environment) -> None:
        self._maybe_end_episode(env)

    def mine(self) -> None:
        self.depleted = True
        self._sync_tags()

    def _sync_tags(self) -> None:
        for tag in ("iron_ore", "gold_ore", "depleted_ore"):
            while tag in self.entity.tags:
                self.entity.tags.remove(tag)
        if self.depleted:
            self.entity.name = "Depleted Ore Site"
            self.entity.tags.append("depleted_ore")
        elif self.ore_type == "gold":
            self.entity.name = "Gold Ore Vein"
            self.entity.tags.append("gold_ore")
        else:
            self.entity.name = "Iron Ore Vein"
            self.entity.tags.append("iron_ore")

    def _maybe_end_episode(self, env: Environment) -> None:
        if getattr(env, "_coop_mining_end_checked_step", None) == env.cur_step:
            return
        env._coop_mining_end_checked_step = env.cur_step
        next_step = env.cur_step + 1
        max_steps = getattr(env, "max_episode_steps", BENCHMARK_STEPS)
        if next_step >= max_steps:
            env.truncations = [True for _ in env.agents]
            return
        if next_step < MIN_EPISODE_LENGTH:
            return
        if next_step % INTERVAL_LENGTH == 0 and random.random() < TERMINATION_PROBABILITY:
            env.truncations = [True for _ in env.agents]


class Mine_Iron_Ore(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(OreNode),
                Action_On_Cooldown("mine"),
            ]
        )

    def is_valid(self, actor, target, env, kwargs="unconsidered") -> bool:
        if not super().is_valid(actor, target, env, kwargs=kwargs):
            return False
        ore = target.get_component(OreNode)
        return ore is not None and ore.ore_type == "iron" and not ore.depleted

    def exec_action(self, actor, target, env, kwargs=None):
        cooldown = actor.get_component(Cooldown)
        if cooldown is not None:
            cooldown.start("mine")
        ore = target.get_component(OreNode)
        ore.mine()
        award_reward(env, actor, IRON_REWARD)
        env.iron_mined = getattr(env, "iron_mined", 0) + 1
        coop_mining_events(env).append(
            f"{actor.name} mined iron from {target.name} for +{IRON_REWARD:g}."
        )
        return {"ore_type": "iron", "reward": IRON_REWARD}

    def action_description_text(self, actor, target, env) -> str:
        return f"Mine iron ore from {target.name}."


class Mine_Gold_Ore(Coordinated_Action):
    def __init__(self):
        super().__init__(
            "Mine gold ore together.",
            GOLD_MINERS_REQUIRED,
            coordination_key="mine_gold_ore",
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(OreNode),
                Action_On_Cooldown("mine"),
            ],
        )

    def is_valid(self, actor, target, env, kwargs="unconsidered") -> bool:
        if self._cached_result(actor, target, env) is not None:
            return True
        if not super().is_valid(actor, target, env, kwargs=kwargs):
            return False
        ore = target.get_component(OreNode)
        return ore is not None and ore.ore_type == "gold" and not ore.depleted

    def exec_coordinated_action(self, actor, target, env, participants, kwargs=None):
        ore = target.get_component(OreNode)
        ore.mine()
        for participant in participants:
            cooldown = participant.get_component(Cooldown)
            if cooldown is not None:
                cooldown.start("mine")
            award_reward(env, participant, GOLD_REWARD)
        env.gold_mined = getattr(env, "gold_mined", 0) + 1
        names = [p.name for p in participants]
        coop_mining_events(env).append(
            f"{' and '.join(names)} mined gold from {target.name} for +{GOLD_REWARD:g} each."
        )
        return {"ore_type": "gold", "miners": names, "reward_each": GOLD_REWARD}

    def action_description_text(self, actor, target, env) -> str:
        return f"Mine gold ore from {target.name} together."
