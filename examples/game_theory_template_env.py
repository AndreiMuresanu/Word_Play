"""
game_theory_template_env.py
============================
Generic environment for repeated, simultaneous-move stage games (matrix-style).

Extension guide
---------------
To add a new game, define a `Stage_Game_Spec` and pass it to
`Game_Theory_Template_Env`.  No env code needs to change.

  - `payoff_matrix`  maps a tuple of strategy indices (one per player, in
    agent-definition order) to a list of per-player float rewards.
  - `private_signal_fn`  (optional) is called once per round to assign each
    agent a private integer.  Useful for info-asymmetry experiments.
  - `public_state_update_fn` (optional) is called after payoffs are resolved
    and can mutate `env.public_state` however you like.
  - `communication_enabled` gates whether the runner attempts a pre-action
    communication phase (requires agents to have a Communication_Policy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from word_play.core import (
    Action,
    Action_Selection,
    Entity,
    Environment,
    Movement_System,
    Observation,
    Position,
    Target_Is_Self,
)
from word_play.presets.entity_orderings import entity_definition_order


# ---------------------------------------------------------------------------
# Shared position  (all agents occupy the same non-spatial "room")
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Game_Room_Position(Position):
    label: str = "game_room"

    def __str__(self) -> str:
        return self.label


GAME_ROOM_MOVEMENT_SYSTEM = Movement_System(
    position_type=Game_Room_Position,
    movement_options=[],
    positions_are_close=lambda _a, _b: True,
)


# ---------------------------------------------------------------------------
# Generic strategy action
# ---------------------------------------------------------------------------

class Play_Strategy(Action):
    """
    Represents a player choosing one named strategy for this round.

    Each strategy gets its own `Play_Strategy` instance so the action list
    mirrors the payoff matrix columns exactly.
    """

    def __init__(self, strategy_index: int, strategy_name: str):
        self.strategy_index = strategy_index
        self.strategy_name = strategy_name
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None
    ) -> dict | None:
        return {"strategy_index": self.strategy_index, "strategy_name": self.strategy_name}

    def action_description_text(
        self, actor: Entity, target_entity: Entity, env: Environment
    ) -> str:
        return f"Play strategy: {self.strategy_name}."



@dataclass
class Stage_Game_Spec:
    """
    Complete description of a stage game.

    Parameters
    ----------
    game_name:
        Human-readable name shown in observations and logs.
    strategy_names:
        Ordered list of strategy labels.  All agents share the same strategy
        set (symmetric games).  For asymmetric games, extend this class.
    num_players:
        Number of agents that play simultaneously.
    payoff_matrix:
        Maps a joint-action profile (tuple of strategy indices, one per
        player in definition order) to a list of per-player float rewards.
        Example for 2-player PD with strategies [C, D]:
            {(0,0): [3.0, 3.0], (0,1): [0.0, 5.0],
             (1,0): [5.0, 0.0], (1,1): [1.0, 1.0]}
    objective_text:
        Multi-line string shown to agents each round.  Should describe the
        game and how payoffs work without revealing the full matrix unless
        you want to.
    private_signal_fn:
        Optional.  Called once at the start of each round as
        `private_signal_fn(round_index, agent_names, rng)` → dict[str, int].
        Return a mapping from agent name to private integer signal.
    public_state_update_fn:
        Optional.  Called after payoffs resolve as
        `public_state_update_fn(joint_profile, rewards, public_state)` → None.
        Mutate `public_state` in-place to track running game state.
    communication_enabled:
        If True, the runner will attempt a pre-action communication phase.
    """

    game_name: str
    strategy_names: list[str]
    num_players: int
    payoff_matrix: dict[tuple[int, ...], list[float]]
    objective_text: str
    private_signal_fn: Callable[[int, list[str], object], dict[str, int]] | None = None
    public_state_update_fn: Callable[[tuple[int, ...], list[float], dict], None] | None = None
    communication_enabled: bool = False

    def validate(self) -> None:
        """Raise ValueError if the spec is internally inconsistent."""
        if len(self.strategy_names) < 2:
            raise ValueError("A game needs at least 2 strategies.")
        if self.num_players < 2:
            raise ValueError("A game needs at least 2 players.")
        n = len(self.strategy_names)
        import itertools
        for profile in itertools.product(range(n), repeat=self.num_players):
            if profile not in self.payoff_matrix:
                raise ValueError(f"Payoff matrix missing entry for profile {profile}.")
            payoffs = self.payoff_matrix[profile]
            if len(payoffs) != self.num_players:
                raise ValueError(
                    f"Profile {profile}: expected {self.num_players} payoffs, got {len(payoffs)}."
                )


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Game_Theory_Observation(Observation):
    agent_name: str
    opponent_names: list[str]
    round_index: int
    max_rounds: int
    spec: Stage_Game_Spec
    last_reward: float
    last_joint_profile: dict[str, str] | None  # agent_name -> strategy_name
    last_payoffs: dict[str, float] | None       # agent_name -> reward
    cumulative_reward: float
    public_state: dict
    private_signal: int | None
    info: dict

    def __str__(self) -> str:
        rounds_remaining = max(0, self.max_rounds - self.round_index)

        # ── last round result ────────────────────────────────────────────────
        if self.last_joint_profile is None:
            last_round_block = ""
        else:
            profile_str = ", ".join(
                f"{name}: {strat}"
                for name, strat in self.last_joint_profile.items()
            )
            payoffs_str = ", ".join(
                f"{name}: {reward:+.2f}"
                for name, reward in (self.last_payoffs or {}).items()
            )
            last_round_block = (
                "LAST ROUND RESULT:"
                f"\n  joint_profile: {profile_str}"
                f"\n  payoffs: {payoffs_str}"
                f"\n  your_reward: {self.last_reward:+.2f}"
                "\n\n"
            )

        # ── current state ────────────────────────────────────────────────────
        state_lines = [
            "CURRENT STATE:",
            f"  your_name: {self.agent_name}",
            f"  opponents: [{', '.join(self.opponent_names)}]",
            f"  round: {self.round_index}/{self.max_rounds}",
            f"  rounds_remaining: {rounds_remaining}",
            f"  cumulative_reward: {self.cumulative_reward:+.2f}",
        ]
        if self.public_state:
            state_lines.append(f"  public_state: {self.public_state}")
        if self.private_signal is not None:
            state_lines.append(f"  your_private_signal: {self.private_signal}")

        # ── actions ──────────────────────────────────────────────────────────
        actions_block = "AVAILABLE ACTIONS:\n" + "".join(
            f"  [{idx}] {action_selection}\n"
            for idx, action_selection in enumerate(self.possible_actions)
        ).rstrip()

        return "\n\n".join(filter(None, [
            last_round_block + f"REWARD THIS TURN: {self.last_reward}",
            self.spec.objective_text,
            "\n".join(state_lines),
            actions_block,
        ]))


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def _game_theory_reward_func(
    agent_actions: list[Action_Selection], env: "Game_Theory_Template_Env"
) -> list[float]:
    """Reward func shim — actual rewards are stored by environment_end_of_step."""
    return env._pending_rewards


class Game_Theory_Template_Env(Environment):
    """
    Repeated simultaneous-move stage game driven entirely by a `Stage_Game_Spec`.

    Round lifecycle
    ---------------
    1. `observe()` — agents receive observations (with last-round result).
    2. Agents simultaneously select actions (collected by the runner).
    3. `env.step(action_selections)` →
         `environment_start_of_step` → (no-op here)
         action execution loop (each agent's Play_Strategy fires)
         `environment_end_of_step` → resolve payoffs, update history, check truncation
    4. `env.last_rewards` holds this round's payoffs.
    """

    def __init__(
        self,
        spec: Stage_Game_Spec,
        agents: list[Entity],
        *,
        max_rounds: int = 20,
    ):
        spec.validate()
        if len(agents) != spec.num_players:
            raise ValueError(
                f"Spec requires {spec.num_players} players but {len(agents)} agents were provided."
            )

        self.spec = spec
        self.max_rounds = max_rounds
        self.round_index = 0
        self.cumulative_rewards: list[float] = [0.0] * len(agents)
        self.last_joint_profile: dict[str, str] | None = None
        self.last_payoffs: dict[str, float] | None = None
        self.public_state: dict = {}
        self.private_signals: dict[str, int] = {}
        self._pending_rewards: list[float] = [0.0] * len(agents)
        self._round_history: list[dict] = []

        import random
        self._rng = random.Random()

        super().__init__(
            description=spec.game_name,
            entities=agents,
            movement_system=GAME_ROOM_MOVEMENT_SYSTEM,
            reward_func=_game_theory_reward_func,
            entity_order=entity_definition_order,
        )

    # -----------------------------------------------------------------------
    # Observation
    # -----------------------------------------------------------------------

    def observe(self, agent_id: int) -> Observation:
        agent = self.agents[agent_id]
        return Game_Theory_Observation(
            possible_actions=self.possible_actions(agent),
            agent_name=agent.name,
            opponent_names=[a.name for a in self.agents if a is not agent],
            round_index=self.round_index,
            max_rounds=self.max_rounds,
            spec=self.spec,
            last_reward=self.last_rewards[agent_id] if self.last_rewards[agent_id] is not None else 0.0,
            last_joint_profile=self.last_joint_profile,
            last_payoffs=self.last_payoffs,
            cumulative_reward=self.cumulative_rewards[agent_id],
            public_state=dict(self.public_state),
            private_signal=self.private_signals.get(agent.name),
            info=self.infos[agent_id],
        )

    # -----------------------------------------------------------------------
    # Step hooks
    # -----------------------------------------------------------------------

    def environment_start_of_step(self, action_selections: list[Action_Selection]) -> None:
        pass

    def environment_end_of_step(self, action_selections: list[Action_Selection]) -> None:
        # Collect the chosen strategy indices from action exec results
        strategy_indices: list[int] = []
        strategy_names_chosen: list[str] = []

        for action_selection in action_selections:
            if not isinstance(action_selection.action, Play_Strategy):
                raise TypeError(
                    "Game_Theory_Template_Env only supports Play_Strategy actions. "
                    f"Got: {type(action_selection.action).__name__}"
                )
            strategy_indices.append(action_selection.action.strategy_index)
            strategy_names_chosen.append(action_selection.action.strategy_name)

        profile_tuple = tuple(strategy_indices)
        payoffs = self.spec.payoff_matrix[profile_tuple]

        # Update rewards
        self._pending_rewards = list(payoffs)
        for i, reward in enumerate(payoffs):
            self.cumulative_rewards[i] += reward

        # Build joint profile dicts for observation and logging
        self.last_joint_profile = {
            agent.name: strategy_names_chosen[i]
            for i, agent in enumerate(self.agents)
        }
        self.last_payoffs = {
            agent.name: payoffs[i]
            for i, agent in enumerate(self.agents)
        }

        # Store per-agent action_info
        step_info = {
            "joint_profile": self.last_joint_profile.copy(),
            "payoffs": self.last_payoffs.copy(),
            "profile_tuple": profile_tuple,
            "round_index": self.round_index,
        }
        for info in self.infos:
            info["action_info"] = step_info

        if self.spec.public_state_update_fn is not None:
            self.spec.public_state_update_fn(profile_tuple, list(payoffs), self.public_state)

        self._round_history.append({
            "round_index": self.round_index,
            "joint_profile": self.last_joint_profile.copy(),
            "payoffs": self.last_payoffs.copy(),
        })

        self.round_index += 1

        if self.round_index >= self.max_rounds:
            self.truncations = [True] * len(self.agents)
            return

        if self.spec.private_signal_fn is not None:
            agent_names = [a.name for a in self.agents]
            self.private_signals = self.spec.private_signal_fn(
                self.round_index, agent_names, self._rng
            )

    # -----------------------------------------------------------------------
    # Reset
    # -----------------------------------------------------------------------

    def _reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self._rng.seed(seed)
        self.round_index = 0
        self.cumulative_rewards = [0.0] * len(self.state.entities)
        self.last_joint_profile = None
        self.last_payoffs = None
        self.public_state = {}
        self.private_signals = {}
        self._pending_rewards = [0.0] * len(self.state.entities)
        self._round_history = []

        # Sample initial private signals
        if self.spec.private_signal_fn is not None:
            agent_names = [e.name for e in self.state.entities if e.is_agent]
            self.private_signals = self.spec.private_signal_fn(0, agent_names, self._rng)


# ---------------------------------------------------------------------------
# Agent builder helper
# ---------------------------------------------------------------------------

def build_game_theory_agents(
    spec: Stage_Game_Spec,
    *policies,
) -> list[Entity]:
    """
    Build one agent per policy, all using the same strategy action set from
    the spec.  Agent names are A, B, C, … (or Agent N for > 26).

    Usage:
        agents = build_game_theory_agents(
            prisoners_dilemma_spec,
            LLM_Action_And_Communication_Policy(model_key="main"),
            LLM_Action_And_Communication_Policy(model_key="main"),
        )
    """
    if len(policies) != spec.num_players:
        raise ValueError(
            f"Spec requires {spec.num_players} players but {len(policies)} policies were provided."
        )

    agents = []
    for idx, policy in enumerate(policies):
        name = f"Agent {chr(ord('A') + idx)}" if idx < 26 else f"Agent {idx + 1}"
        agents.append(
            Entity(
                name=name,
                position=Game_Room_Position(),
                actions=[
                    Play_Strategy(i, strategy_name)
                    for i, strategy_name in enumerate(spec.strategy_names)
                ],
                components=[policy],
            )
        )
    return agents