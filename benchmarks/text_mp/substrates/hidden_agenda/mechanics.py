from __future__ import annotations

import random
from collections import Counter

from word_play.core import (
    Action,
    Action_Validation,
    Component,
    Entity,
    Environment,
    Target_Is_Self,
    Target_Not_Self,
)
from word_play.presets.action_validations import Target_Within_Range
from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
from word_play.presets.movement.simple_2d_grid import Collidable, Position_2D
from word_play.presets.observation.simple_observation import Simple_Observation
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.role import Role

from benchmarks.text_mp.core.timing import normalized_probability, normalized_steps


GEM_GOAL = max(3, normalized_steps(32))
GEM_REGROW_PROBABILITY = normalized_probability(0.001)
VOTING_FRAME_FREQUENCY = normalized_steps(200, minimum=3)
DELIBERATION_DURATION = normalized_steps(25, minimum=2)
FREEZE_RANGE = 2
FREEZE_COOLDOWN = normalized_steps(50)


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

class HiddenAgendaState(Role):
    def __init__(self, role: str, spawn_position: Position_2D):
        super().__init__(role)
        self._role = role
        self.spawn_position = Position_2D(spawn_position.x, spawn_position.y)
        self.held_gems = 0
        self.status = "active"
        self.frozen = False
        self.voted_out = False
        self.vote: str | None = None
        self.freeze_cooldown = 0
        self._base_actions: list[Action] = []

    def post_initialization(self) -> None:
        self._base_actions = list(self.entity.actions)

    def pre_actions_step(self, env: Environment) -> None:
        if self.freeze_cooldown > 0:
            self.freeze_cooldown -= 1

    @property
    def is_crewmate(self) -> bool:
        return self._role == "crewmate"

    @property
    def is_impostor(self) -> bool:
        return self._role == "impostor"

    @property
    def active(self) -> bool:
        return not self.frozen and not self.voted_out

    def set_base_actions(self) -> None:
        if self.active:
            self.entity.actions = list(self._base_actions)
            self.status = "active"
        else:
            self.entity.actions = [Do_Nothing()]

    def set_voting_actions(self, num_players: int) -> None:
        if self.active:
            self.entity.actions = [
                Do_Nothing(),
                AbstainVote(),
                *[VoteForPlayer(i) for i in range(1, num_players + 1)],
            ]
            self.status = "deliberating"
            self.vote = "abstain"
        else:
            self.entity.actions = [Do_Nothing()]
            self.vote = "no-vote"

    def freeze_permanently(self) -> None:
        self.frozen = True
        self.status = "frozen"
        self.vote = "no-vote"
        self.entity.actions = [Do_Nothing()]

    def vote_out(self) -> None:
        self.voted_out = True
        self.status = "voted_out"
        self.vote = "no-vote"
        self.entity.actions = [Do_Nothing()]


class GemPatch(Component):
    def __init__(self):
        super().__init__(tags=["gem"])
        self.available = True

    def pre_actions_step(self, env: Environment) -> None:
        if not self.available and random.random() < GEM_REGROW_PROBABILITY:
            self.available = True
            self._sync()

    def collect(self) -> bool:
        if not self.available:
            return False
        self.available = False
        self._sync()
        return True

    def _sync(self) -> None:
        self.entity.name = "Gem" if self.available else "Empty Gem Site"


class GemDeposit(Component):
    def __init__(self):
        super().__init__(tags=["gem_deposit"])


class VotingSpawn(Component):
    def __init__(self):
        super().__init__(tags=["voting_spawn"])


class HiddenAgendaManager(Component):
    def __init__(self, voting_positions: list[tuple[int, int]]):
        super().__init__()
        self.voting_positions = voting_positions
        self.voting_active = False
        self.voting_timer = 0
        self.pending_deliberation = False
        self.gems_deposited = 0
        self.outcome = "ongoing"

    def pre_actions_step(self, env: Environment) -> None:
        env.hidden_agenda_events = []

    def post_actions_step(self, env: Environment) -> None:
        if self.outcome != "ongoing":
            return
        self._collect_gems(env)
        self._deposit_gems(env)
        if self.outcome != "ongoing":
            return
        if self.voting_active:
            self.voting_timer -= 1
            if self.voting_timer <= 0:
                self._resolve_vote(env)
            return
        if self._active_crewmates(env) <= 1:
            self._finish(env, winner="impostor", reason="Only one crewmate remains active.")
            return
        if self.pending_deliberation or (env.cur_step + 1) % VOTING_FRAME_FREQUENCY == 0:
            self._start_deliberation(env)

    def _collect_gems(self, env: Environment) -> None:
        gems = [e for e in env.state.entities if e.get_component(GemPatch) is not None]
        for agent in env.agents:
            state = agent.get_component(HiddenAgendaState)
            if state is None or not state.active or not state.is_crewmate or state.held_gems >= 1:
                continue
            for gem in gems:
                patch = gem.get_component(GemPatch)
                if gem.position == agent.position and patch.collect():
                    state.held_gems += 1
                    env.hidden_agenda_events.append(f"{agent.name} picked up a gem.")
                    break

    def _deposit_gems(self, env: Environment) -> None:
        deposit_positions = {
            (e.position.x, e.position.y)
            for e in env.state.entities
            if e.get_component(GemDeposit) is not None
        }
        for agent in env.agents:
            state = agent.get_component(HiddenAgendaState)
            if state is None or not state.active or not state.is_crewmate or state.held_gems <= 0:
                continue
            if (agent.position.x, agent.position.y) not in deposit_positions:
                continue
            self.gems_deposited += state.held_gems
            env.hidden_agenda_events.append(
                f"{agent.name} deposited {state.held_gems} gem(s); "
                f"progress {self.gems_deposited}/{GEM_GOAL}."
            )
            state.held_gems = 0
            if self.gems_deposited >= GEM_GOAL:
                self._finish(env, winner="crewmates", reason="Crewmates deposited enough gems.")
                return

    def _start_deliberation(self, env: Environment) -> None:
        self.pending_deliberation = False
        self.voting_active = True
        self.voting_timer = DELIBERATION_DURATION
        positions = self.voting_positions or [
            (agent.position.x, agent.position.y) for agent in env.agents
        ]
        for idx, agent in enumerate(env.agents):
            state = agent.get_component(HiddenAgendaState)
            if state is None:
                continue
            if state.active:
                x, y = positions[idx % len(positions)]
                agent.position = Position_2D(x, y)
            state.set_voting_actions(len(env.agents))
        env.hidden_agenda_events.append("Deliberation started.")

    def _resolve_vote(self, env: Environment) -> None:
        self.voting_active = False
        active_states = [agent.get_component(HiddenAgendaState) for agent in env.agents]
        active_voters = [s for s in active_states if s is not None and s.active]
        votes = Counter(
            s.vote for s in active_voters if s.vote and s.vote not in ("abstain", "no-vote")
        )
        voted_player = None
        if votes:
            candidate, count = votes.most_common(1)[0]
            if count > len(active_voters) / 2:
                voted_player = candidate

        if voted_player is not None:
            player_number = int(voted_player.split()[-1])
            if 1 <= player_number <= len(env.agents):
                target = env.agents[player_number - 1]
                target_state = target.get_component(HiddenAgendaState)
                if target_state is not None and target_state.active:
                    target_state.vote_out()
                    env.hidden_agenda_events.append(f"{target.name} was voted out.")
                    if target_state.is_impostor:
                        self._finish(env, winner="crewmates", reason="The impostor was voted out.")
                        return

        for agent in env.agents:
            state = agent.get_component(HiddenAgendaState)
            if state is None:
                continue
            if state.active:
                agent.position = Position_2D(state.spawn_position.x, state.spawn_position.y)
            state.vote = None
            state.set_base_actions()

        if self._active_crewmates(env) <= 1:
            self._finish(env, winner="impostor", reason="Only one crewmate remains active.")

    def _active_crewmates(self, env: Environment) -> int:
        return sum(
            1
            for agent in env.agents
            if (s := agent.get_component(HiddenAgendaState)) is not None
            and s.is_crewmate
            and s.active
        )

    def _finish(self, env: Environment, *, winner: str, reason: str) -> None:
        self.outcome = f"{winner}_win"
        env.hidden_agenda_events.append(f"{winner} win: {reason}")
        for idx, agent in enumerate(env.agents):
            state = agent.get_component(HiddenAgendaState)
            if state is None:
                continue
            if winner == "crewmates":
                env.last_step_rewards[idx] += 1.0 if state.is_crewmate else -1.0
            else:
                env.last_step_rewards[idx] += 1.0 if state.is_impostor else -1.0
        env.terminations = [True] * len(env.agents)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

class ActorIsImpostor(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        state = actor.get_component(HiddenAgendaState)
        manager = _get_manager(env)
        return (
            state is not None
            and state.is_impostor
            and state.active
            and not manager.voting_active
        )


class FreezeReady(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        state = actor.get_component(HiddenAgendaState)
        return state is not None and state.freeze_cooldown <= 0


class TargetIsActiveCrewmate(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        state = target_entity.get_component(HiddenAgendaState)
        return state is not None and state.is_crewmate and state.active


class VotingIsActive(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        state = actor.get_component(HiddenAgendaState)
        return state is not None and state.active and _get_manager(env).voting_active


class FreezeCrewmate(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Within_Range(FREEZE_RANGE),
                ActorIsImpostor(),
                FreezeReady(),
                TargetIsActiveCrewmate(),
            ]
        )

    def exec_action(self, actor, target, env, kwargs=None):
        actor_state = actor.get_component(HiddenAgendaState)
        target_state = target.get_component(HiddenAgendaState)
        target_state.freeze_permanently()
        actor_state.freeze_cooldown = FREEZE_COOLDOWN
        _get_manager(env).pending_deliberation = True
        env.hidden_agenda_events.append(
            f"{actor.name} froze {target.name}; deliberation will begin."
        )
        return {"froze": target.name, "triggered_deliberation": True}

    def action_description_text(self, actor, target, env) -> str:
        return f"Freeze {target.name}."


class VoteForPlayer(Action):
    def __init__(self, player_number: int):
        super().__init__(validation_rules=[Target_Is_Self(), VotingIsActive()])
        self.player_number = player_number

    def exec_action(self, actor, target, env, kwargs=None):
        state = actor.get_component(HiddenAgendaState)
        state.vote = f"Player {self.player_number}"
        return {"vote": state.vote}

    def action_description_text(self, actor, target, env) -> str:
        return f"Vote for Player {self.player_number}."


class AbstainVote(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self(), VotingIsActive()])

    def exec_action(self, actor, target, env, kwargs=None):
        state = actor.get_component(HiddenAgendaState)
        state.vote = "abstain"
        return {"vote": "abstain"}

    def action_description_text(self, actor, target, env) -> str:
        return "Abstain from the vote."


# ---------------------------------------------------------------------------
# Custom world with role-aware observation
# ---------------------------------------------------------------------------

def _get_manager(env: Environment) -> HiddenAgendaManager:
    for entity in env.state.entities:
        m = entity.get_component(HiddenAgendaManager)
        if m is not None:
            return m
    raise RuntimeError("HiddenAgendaManager missing from environment.")


def _grid_distance(a: Entity, b: Entity) -> int:
    return abs(a.position.x - b.position.x) + abs(a.position.y - b.position.y)


def _relative_text(actor: Entity, target: Entity) -> str:
    dx = target.position.x - actor.position.x
    dy = target.position.y - actor.position.y
    return f"relative=({dx:+d},{dy:+d}), distance={abs(dx) + abs(dy)}"


def _direction_text(actor: Entity, target: Entity) -> str:
    dx = target.position.x - actor.position.x
    dy = target.position.y - actor.position.y
    moves = []
    if dx > 0:
        moves.append("right")
    elif dx < 0:
        moves.append("left")
    if dy > 0:
        moves.append("up")
    elif dy < 0:
        moves.append("down")
    return "/".join(moves) if moves else "already here"


def _state_text(entity: Entity) -> str:
    state = entity.get_component(HiddenAgendaState)
    if state is None:
        return "role=unknown"
    return (
        f"role={state._role}, status={state.status}, "
        f"held_gems={state.held_gems}, freeze_cooldown={state.freeze_cooldown}, "
        f"vote={state.vote}"
    )


def _important_actions_text(possible_actions: list) -> str:
    matches = [
        f"  [{idx}] {selection}"
        for idx, selection in enumerate(possible_actions)
        if any(k in str(selection) for k in ("Freeze", "Vote for", "Abstain"))
    ]
    if not matches:
        return (
            "IMPORTANT AVAILABLE ACTIONS: no freeze or vote action is valid this turn; "
            "use movement to reach visible gems or deposits."
        )
    return "IMPORTANT AVAILABLE ACTIONS:\n" + "\n".join(matches)


def _local_map_symbol(entity: Entity, agent: Entity) -> tuple[int, str] | None:
    if entity is agent:
        return 100, "A"
    if entity.is_agent:
        return 90, "P"
    if "gem" in entity.tags and entity.name == "Gem":
        return 80, "G"
    if "gem_deposit" in entity.tags:
        return 70, "D"
    if "voting_spawn" in entity.tags:
        return 60, "V"
    if "wall" in entity.tags:
        return 50, "#"
    return None


def _local_map(env: "HiddenAgendaWorld", agent: Entity, nearby: list[Entity]) -> str:
    radius = env.observation_radius
    cells: dict[tuple[int, int], tuple[int, str]] = {
        (x, y): (0, ".")
        for y in range(agent.position.y - radius, agent.position.y + radius + 1)
        for x in range(agent.position.x - radius, agent.position.x + radius + 1)
    }
    for entity in nearby:
        sym = _local_map_symbol(entity, agent)
        if sym is None:
            continue
        xy = (entity.position.x, entity.position.y)
        if xy in cells and sym[0] >= cells[xy][0]:
            cells[xy] = sym
    rows = []
    for y in range(agent.position.y + radius, agent.position.y - radius - 1, -1):
        rows.append(
            "".join(
                cells[(x, y)][1]
                for x in range(agent.position.x - radius, agent.position.x + radius + 1)
            )
        )
    return "LOCAL MAP (A=you, P=player, G=gem, D=deposit, V=vote, #=wall):\n" + "\n".join(rows)


def _format_entities(nearby: list[Entity], agent: Entity) -> str:
    lines = ["VISIBLE ENTITIES:"]
    ordered = sorted(nearby, key=lambda e: (_grid_distance(agent, e), e.name))
    for entity in ordered:
        if entity is agent:
            continue
        if entity.is_agent:
            lines.append(f"- {entity.name}: {_relative_text(agent, entity)}, {_state_text(entity)}")
        elif "gem" in entity.tags and entity.name == "Gem":
            lines.append(
                f"- Gem: {_relative_text(agent, entity)}; move {_direction_text(agent, entity)}"
            )
        elif "gem_deposit" in entity.tags:
            lines.append(
                f"- Gem Deposit: {_relative_text(agent, entity)}; move {_direction_text(agent, entity)}"
            )
    if len(lines) == 1:
        return "VISIBLE ENTITIES: none"
    return "\n".join(lines)


class HiddenAgendaWorld(Simple_2D_Grid_World):
    def observe(self, agent_id: int):
        agent = self.agents[agent_id]
        nearby = self.entities_in_observation_square(agent.position)
        possible_actions = self.possible_actions(agent)
        state = agent.get_component(HiddenAgendaState)
        manager = _get_manager(self)

        visible_gems = [e for e in nearby if "gem" in e.tags and e.name == "Gem"]
        visible_deposits = [e for e in nearby if "gem_deposit" in e.tags]

        lines = [
            "HIDDEN AGENDA STATUS:",
            f"  your_state: {_state_text(agent)}",
            f"  team_progress: gems_deposited={manager.gems_deposited}/{GEM_GOAL}, "
            f"voting_active={manager.voting_active}, voting_timer={manager.voting_timer}, "
            f"outcome={manager.outcome}",
        ]
        if state is not None and state.is_crewmate:
            if state.held_gems > 0:
                lines.append(
                    "  goal_now: find a visible Gem Deposit tile and step onto it with your held gem."
                )
            else:
                lines.append(
                    "  goal_now: explore for a visible Gem (G), then step onto it to pick it up."
                )
            if manager.voting_active:
                lines.append("  voting_now: vote for the suspected impostor or abstain.")
        elif state is not None and state.is_impostor:
            lines.append("  goal_now: freeze active crewmates in range and survive votes.")

        if visible_gems:
            nearest = min(visible_gems, key=lambda e: _grid_distance(agent, e))
            lines.append(
                f"  nearest_visible_gem: {_relative_text(agent, nearest)}; "
                f"move {_direction_text(agent, nearest)}"
            )
        if visible_deposits:
            nearest = min(visible_deposits, key=lambda e: _grid_distance(agent, e))
            lines.append(
                f"  nearest_visible_deposit: {_relative_text(agent, nearest)}; "
                f"move {_direction_text(agent, nearest)}"
            )

        if state is not None and state.is_crewmate and state.held_gems == 0 and visible_gems:
            lines.append("  immediate_priority: move toward nearest_visible_gem.")
        elif state is not None and state.is_crewmate and state.held_gems > 0 and visible_deposits:
            lines.append("  immediate_priority: move toward nearest_visible_deposit.")

        return Simple_Observation(
            possible_actions=possible_actions,
            nearby_entities=nearby,
            agent=agent,
            last_reward=self.last_rewards[agent_id],
            info=self.infos[agent_id],
            observation_radius=self.observation_radius,
            extra_sections=(
                "\n".join(lines),
                _local_map(self, agent, nearby),
                _important_actions_text(possible_actions),
            ),
            nearby_entities_formatter=lambda entities, cur_agent: _format_entities(
                entities, cur_agent
            ),
        )
