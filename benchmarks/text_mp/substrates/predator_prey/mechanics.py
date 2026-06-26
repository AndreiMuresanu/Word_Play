from __future__ import annotations

from word_play.core import Action, Action_Validation, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.movement.simple_2d_grid import Position_2D
from word_play.presets.systems.respawnable import Respawnable
from word_play.presets.systems.reward import award_reward
from word_play.presets.systems.role import Role

from benchmarks.text_mp.core.timing import BENCHMARK_STEPS, normalized_steps


PREDATOR_PREY_RESPAWN_STEPS = normalized_steps(200)
PREDATOR_PREY_GROUP_DEFENSE_RADIUS = 3
PREDATOR_PREY_PREDATOR_REWARD = 1.0
PREDATOR_PREY_ACORN_EAT_STEPS = normalized_steps(40, minimum=3)
PREDATOR_PREY_FOOD_RESPAWN_STEPS = normalized_steps(120)


def predator_prey_events(env: Environment) -> list[str]:
    if getattr(env, "_predator_prey_events_step", None) != env.cur_step:
        env.predator_prey_events = []
        env.tick = env.cur_step
        env._predator_prey_events_step = env.cur_step
    return env.predator_prey_events


class PredatorPreyRole(Role):
    def __init__(self, role: str):
        if role not in {"predator", "prey"}:
            raise ValueError(f"Unknown predator-prey role: {role}")
        super().__init__(role)
        self.max_stamina = 6 if role == "predator" else 9
        self.stamina = self.max_stamina
        self.eating_food_name: str | None = None
        self.eating_timer = 0
        self.eating_started_step: int | None = None
        self.eating_reward_per_step = 0.0
        self._before: Position_2D | None = None
        self._was_active = True

    @property
    def active(self) -> bool:
        respawnable = self.entity.get_component(Respawnable)
        return respawnable is None or respawnable.active

    @property
    def eating(self) -> bool:
        return self.eating_timer > 0

    def pre_actions_step(self, env: Environment) -> None:
        predator_prey_events(env)
        if self.active and not self._was_active:
            self.stamina = self.max_stamina
        self._was_active = self.active
        self._before = Position_2D(self.entity.position.x, self.entity.position.y)

    def can_move(self) -> bool:
        return self.active and not self.eating and self.stamina > 0

    def can_interact(self) -> bool:
        return self.active and not self.eating and self.stamina > 0

    def remove_temporarily(self, duration: int = PREDATOR_PREY_RESPAWN_STEPS) -> None:
        self.eating_food_name = None
        self.eating_timer = 0
        self.eating_started_step = None
        self.eating_reward_per_step = 0.0
        respawnable = self.entity.get_component(Respawnable)
        if respawnable is not None:
            respawnable.remove_temporarily(duration)

    def start_eating(self, food: Entity, reward: float, eat_steps: int, env: Environment) -> None:
        self.eating_food_name = food.name
        self.eating_timer = max(1, eat_steps)
        self.eating_started_step = env.cur_step
        self.eating_reward_per_step = reward / self.eating_timer

    def post_actions_step(self, env: Environment) -> None:
        max_steps = getattr(env, "max_episode_steps", BENCHMARK_STEPS)
        if env.cur_step + 1 >= max_steps:
            env.truncations = [True for _ in env.agents]
        if not self.active:
            return

        if self.eating:
            if self.eating_started_step == env.cur_step:
                return
            award_reward(env, self.entity, self.eating_reward_per_step)
            self.eating_timer -= 1
            if self.eating_timer <= 0:
                env.predator_prey_events.append(f"{self.entity.name} finished eating {self.eating_food_name}.")
                self.eating_food_name = None
                self.eating_started_step = None
                self.eating_reward_per_step = 0.0
            return

        if self._before is None:
            return
        moved = self.entity.position != self._before
        self.stamina = max(0, self.stamina - 1) if moved else min(self.max_stamina, self.stamina + 1)


class PredatorPreyFood(Respawnable):
    def __init__(
        self,
        kind: str,
        reward: float,
        eat_steps: int | None = None,
        respawn_steps: int = PREDATOR_PREY_FOOD_RESPAWN_STEPS,
    ):
        if kind not in {"apple", "acorn"}:
            raise ValueError(f"Unknown predator-prey food kind: {kind}")
        super().__init__(
            respawn_steps,
            inactive_tag="eaten_food",
            inactive_position=Position_2D(-1000, -1000),
        )
        self.tags.extend([kind, "food"])
        self.kind = kind
        self.reward = reward
        self.eat_steps = eat_steps if eat_steps is not None else (PREDATOR_PREY_ACORN_EAT_STEPS if kind == "acorn" else 1)
        self.respawn_steps = respawn_steps

    def post_actions_step(self, env: Environment) -> None:
        if not self.active:
            return
        for agent in env.agents:
            role = agent.get_component(PredatorPreyRole)
            if role is None or role.role != "prey" or not role.active or role.eating:
                continue
            if agent.position == self.entity.position:
                if self.kind == "acorn":
                    role.start_eating(self.entity, self.reward, self.eat_steps, env)
                    env.predator_prey_events.append(
                        f"{agent.name} started eating {self.entity.name} for +{self.reward:g} over {self.eat_steps} steps."
                    )
                else:
                    award_reward(env, agent, self.reward)
                    env.predator_prey_events.append(f"{agent.name} ate {self.entity.name} for +{self.reward:g}.")
                self.remove_temporarily(self.respawn_steps)
                return


class ActorCanCatch(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        role = actor.get_component(PredatorPreyRole)
        return role is not None and role.role == "predator" and role.can_interact()


class ActorCanMove(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        role = actor.get_component(PredatorPreyRole)
        return role is None or role.can_move()


class TargetCanBeCaught(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        target_role = target_entity.get_component(PredatorPreyRole)
        return target_role is not None and target_role.active


def prey_defends_against_catch(prey: Entity, env: Environment) -> bool:
    active_prey = 0
    active_predators = 0
    for agent in env.agents:
        role = agent.get_component(PredatorPreyRole)
        if role is None or not role.active:
            continue
        distance = abs(agent.position.x - prey.position.x) + abs(agent.position.y - prey.position.y)
        if distance > PREDATOR_PREY_GROUP_DEFENSE_RADIUS:
            continue
        if role.role == "prey" and not role.eating:
            active_prey += 1
        elif role.role == "predator":
            active_predators += 1
    return active_prey > active_predators


class CatchPrey(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                ActorCanCatch(),
                TargetCanBeCaught(),
            ]
        )

    def is_valid(self, actor, target, env, kwargs="unconsidered") -> bool:
        if not super().is_valid(actor, target, env, kwargs=kwargs):
            return False
        actor_role = actor.get_component(PredatorPreyRole)
        target_role = target.get_component(PredatorPreyRole)
        if actor_role is None or target_role is None:
            return False
        if target_role.role == "prey" and prey_defends_against_catch(target, env):
            return False
        return target_role.role in {"prey", "predator"}

    def exec_action(self, actor, target, env, kwargs=None):
        target_role = target.get_component(PredatorPreyRole)
        target_role.remove_temporarily(PREDATOR_PREY_RESPAWN_STEPS)
        reward = PREDATOR_PREY_PREDATOR_REWARD if target_role.role == "prey" else 0.0
        if reward:
            award_reward(env, actor, reward)
        env.predator_prey_events.append(f"{actor.name} caught {target.name} for +{reward:g}.")
        return {"caught": target.name, "reward": reward}

    def action_description_text(self, actor, target, env):
        return f"Catch {target.name}."
