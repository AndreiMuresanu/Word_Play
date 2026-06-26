from __future__ import annotations

import random

from word_play.core import Component, Entity, Environment, Target_Is_Self
from word_play.presets.systems.coordinated_action import Coordinated_Action
from word_play.presets.systems.reward import Rewardable, award_reward


def boat_events(env: Environment) -> list[str]:
    if getattr(env, "_boat_events_step", None) != env.cur_step:
        env.boat_events = []
        env.tick = env.cur_step
        env._boat_events_step = env.cur_step
    return env.boat_events


def advance_boat_race(env: Environment, participants: list[Entity], reward: float, event: str) -> None:
    boat_events(env)
    env.boat_progress = getattr(env, "boat_progress", 0) + 1
    for participant in participants:
        award_reward(env, participant, reward)
    env.boat_events.append(event.format(progress=env.boat_progress, participants=len(participants)))
    if env.boat_progress >= getattr(env, "boat_num_races", 8):
        env.terminations = [True] * len(env.agents)


class Paddle(Coordinated_Action):
    def __init__(self):
        super().__init__(
            "Paddle the boat.",
            2,
            coordination_key="boat_paddle",
            same_target=False,
            validation_rules=[Target_Is_Self()],
        )

    def exec_coordinated_action(self, actor, target, env, participants, kwargs=None):
        advance_boat_race(
            env,
            participants,
            0.2,
            "{participants} paddlers coordinated; race progress is {progress}.",
        )
        return {"paddle": True, "progress": env.boat_progress, "reward_each": 0.2}

    def action_description_text(self, actor, target, env):
        return "Paddle the boat."


class Flail(Coordinated_Action):
    def __init__(self):
        super().__init__(
            "Flail the oar.",
            1,
            coordination_key="boat_flail",
            same_target=False,
            validation_rules=[Target_Is_Self()],
        )

    def exec_coordinated_action(self, actor, target, env, participants, kwargs=None):
        paddle_count = sum(
            1
            for selection in self._selected_actions(env)
            if isinstance(selection.action, Paddle)
            and selection.action._local_is_valid(
                selection.actor,
                selection.target_entity,
                env,
                selection.action_kwargs,
            )
        )
        if paddle_count >= 2 or random.random() >= 0.25:
            return {"flail": True, "moved": False}

        advance_boat_race(
            env,
            participants,
            0.05,
            "A flail moved a boat; race progress is {progress}.",
        )
        return {"flail": True, "moved": True, "progress": env.boat_progress, "reward_each": 0.05}

    def action_description_text(self, actor, target, env):
        return "Flail the oar."


class BoatFood(Component):
    def __init__(self, reward: float = 1.0):
        super().__init__(tags=["boat_food"])
        self.reward = reward
        self.consumed = False

    def post_actions_step(self, env: Environment) -> None:
        if self.consumed:
            return
        for agent in env.agents:
            if agent.position == self.entity.position:
                self.consumed = True
                rewardable = self.entity.get_component(Rewardable)
                reward = rewardable.reward_for(agent, env) if rewardable is not None else self.reward
                if rewardable is None:
                    award_reward(env, agent, reward)
                self._mark_consumed()
                boat_events(env).append(f"{agent.name} ate {self.entity.name} for +{reward:g}.")
                return

    def _mark_consumed(self) -> None:
        self.entity.name = f"Eaten {self.entity.name}"
        for tag in ("apple", "food"):
            while tag in self.entity.tags:
                self.entity.tags.remove(tag)
        if "eaten_food" not in self.entity.tags:
            self.entity.tags.append("eaten_food")
