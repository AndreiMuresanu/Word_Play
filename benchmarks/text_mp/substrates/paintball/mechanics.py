from __future__ import annotations

from word_play.core import Action, Action_Validation, Component, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Has_Component, Target_Within_Range
from word_play.presets.systems.combat import Attack
from word_play.presets.systems.cooldown import Action_On_Cooldown, Cooldown
from word_play.presets.systems.freezable import Freezable
from word_play.presets.systems.inventory import Inventory, Target_Not_In_Inventory
from word_play.presets.systems.reward import award_reward

from benchmarks.text_mp.core.timing import BENCHMARK_STEPS, normalized_steps


ZAP_RANGE = 3
ZAP_COOLDOWN = 2
ZAP_FREEZE_DURATION = normalized_steps(5)
CTF_CAPTURE_REWARD = 5.0
HILL_SCORE_REWARD = 0.5
HILL_WIN_SCORE = normalized_steps(30)


class Flag(Component):
    def __init__(self, team: str):
        super().__init__(tags=["flag", f"{team}_flag"])
        self.team = team


class HillZone(Component):
    def __init__(self):
        super().__init__(tags=["hill"])


class PaintballZap(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Action_On_Cooldown("paintball"),
                Target_Not_Self(),
                Target_Within_Range(ZAP_RANGE),
            ]
        )
        self._wall_attack = Attack(
            "Shoot paintball at",
            1,
            target_is_nearby=Target_Within_Range(ZAP_RANGE).is_valid,
        )

    def is_valid(self, actor, target, env, kwargs="unconsidered") -> bool:
        if not super().is_valid(actor, target, env, kwargs=kwargs):
            return False
        if ("red" in actor.tags and "red" in target.tags) or (
            "blue" in actor.tags and "blue" in target.tags
        ):
            return False
        return "player" in target.tags or "destructible" in target.tags

    def exec_action(self, actor, target, env, kwargs=None):
        cooldown = actor.get_component(Cooldown)
        if cooldown is not None:
            cooldown.start("paintball")
        if "player" in target.tags:
            freezable = target.get_component(Freezable)
            if freezable is not None:
                freezable.freeze(ZAP_FREEZE_DURATION)
            env.paintball_events.append(f"{actor.name} tagged {target.name}.")
            return {"tagged": target.name}
        if self._wall_attack.is_valid(actor, target, env):
            result = self._wall_attack.exec_action(actor, target, env, kwargs)
            env.paintball_events.append(f"{actor.name} damaged {target.name}.")
            return result
        return {"success": False}

    def action_description_text(self, actor, target, env) -> str:
        return f"Shoot paintball at {target.name}."


class GrabFlag(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(Flag),
                Target_Not_In_Inventory(),
            ]
        )

    def is_valid(self, actor, target, env, kwargs="unconsidered") -> bool:
        if not super().is_valid(actor, target, env, kwargs=kwargs):
            return False
        flag = target.get_component(Flag)
        if flag is None or flag.team in actor.tags:
            return False
        inventory = actor.get_component(Inventory)
        return inventory is not None and inventory.has_space()

    def exec_action(self, actor, target, env, kwargs=None):
        inventory = actor.get_component(Inventory)
        inventory.store(target, env)
        env.paintball_events.append(f"{actor.name} grabbed {target.name}.")
        return {"grabbed": target.name}

    def action_description_text(self, actor, target, env) -> str:
        return f"Grab {target.name}."


class PaintballManager(Component):
    def __init__(self, mode: str, red_base: tuple[int, int] | None = None, blue_base: tuple[int, int] | None = None):
        super().__init__()
        self.mode = mode
        self.red_base = red_base
        self.blue_base = blue_base
        self.red_score = 0.0
        self.blue_score = 0.0

    def pre_actions_step(self, env: Environment) -> None:
        env.paintball_events = []

    def post_actions_step(self, env: Environment) -> None:
        if self.mode == "ctf":
            self._score_ctf(env)
        else:
            self._score_hill(env)

    def _score_ctf(self, env: Environment) -> None:
        for agent in env.agents:
            inventory = agent.get_component(Inventory)
            if inventory is None:
                continue
            for item in list(inventory.contents):
                flag = item.get_component(Flag)
                if flag is None:
                    continue
                pos = (agent.position.x, agent.position.y)
                if "red" in agent.tags and flag.team == "blue" and pos == self.red_base:
                    award_reward(env, agent, CTF_CAPTURE_REWARD)
                    self.red_score += 1
                    env.paintball_events.append(f"{agent.name} captured the blue flag! Red wins.")
                    env.terminations = [True] * len(env.agents)
                elif "blue" in agent.tags and flag.team == "red" and pos == self.blue_base:
                    award_reward(env, agent, CTF_CAPTURE_REWARD)
                    self.blue_score += 1
                    env.paintball_events.append(f"{agent.name} captured the red flag! Blue wins.")
                    env.terminations = [True] * len(env.agents)

    def _score_hill(self, env: Environment) -> None:
        hill_positions = {
            (entity.position.x, entity.position.y)
            for entity in env.state.entities
            if entity.get_component(HillZone) is not None
        }
        if not hill_positions:
            return
        red_on_hill = [
            agent for agent in env.agents
            if "red" in agent.tags and (agent.position.x, agent.position.y) in hill_positions
        ]
        blue_on_hill = [
            agent for agent in env.agents
            if "blue" in agent.tags and (agent.position.x, agent.position.y) in hill_positions
        ]
        if red_on_hill and not blue_on_hill:
            self.red_score += 1
            for agent in red_on_hill:
                award_reward(env, agent, HILL_SCORE_REWARD)
            env.paintball_events.append(f"Red scores the hill (score: red={self.red_score:g}, blue={self.blue_score:g}).")
        elif blue_on_hill and not red_on_hill:
            self.blue_score += 1
            for agent in blue_on_hill:
                award_reward(env, agent, HILL_SCORE_REWARD)
            env.paintball_events.append(f"Blue scores the hill (score: red={self.red_score:g}, blue={self.blue_score:g}).")
        if self.red_score >= HILL_WIN_SCORE or self.blue_score >= HILL_WIN_SCORE:
            winner = "Red" if self.red_score >= HILL_WIN_SCORE else "Blue"
            env.paintball_events.append(f"{winner} wins king of the hill!")
            env.terminations = [True] * len(env.agents)
