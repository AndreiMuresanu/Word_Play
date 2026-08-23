from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from word_play.core import Agent_Policy, Environment

from benchmarks.text_mp.core.rewards import install_reward_buffer, reset_step_rewards
from benchmarks.text_mp.core.timing import BENCHMARK_STEPS


@dataclass
class EpisodeResult:
    steps: int
    returns: list[float]
    events: list[str] = field(default_factory=list)

    @property
    def per_capita_return(self) -> float:
        return sum(self.returns) / len(self.returns) if self.returns else 0.0


def run_episode(
    env: Environment,
    *,
    max_steps: int = BENCHMARK_STEPS,
    event_attributes: Iterable[str] = (),
    print_actions: bool = True,
    print_raw_responses: bool = False,
    print_fn: Callable[[str], None] = print,
) -> EpisodeResult:
    install_reward_buffer(env)
    env.max_episode_steps = max_steps
    events: list[str] = []
    cumulative_returns = [0.0] * len(env.agents)

    while not any(env.terminations) and not any(env.truncations):
        if env.cur_step >= max_steps:
            env.truncations = [True for _ in env.agents]
            break

        reset_step_rewards(env)
        actions = []
        step = env.cur_step
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            policy = agent.get_component(Agent_Policy)
            if policy is None:
                raise ValueError(f"{agent.name} does not have an Agent_Policy component.")
            action, info = policy.select_action(observation)
            info = info or {}
            if print_raw_responses:
                raw_response = info.get("raw_response")
                if raw_response is not None:
                    raw_text = raw_response.strip() or "<empty>"
                    print_fn(f"[step {step}] {agent.name} raw -> {raw_text}")
                if info.get("fallback"):
                    print_fn(f"[step {step}] {agent.name} fallback -> {info.get('fallback_reason')}")
            if print_actions:
                print_fn(f"[step {step}] {agent.name} -> {action}")
            actions.append(action)

        env.step(actions)

        for attr in event_attributes:
            for event in getattr(env, attr, []):
                line = f"[step {step}] {attr.removesuffix('_events')} -> {event}"
                events.append(line)
                print_fn(line)

        for agent_id, reward in enumerate(env.last_step_rewards):
            cumulative_returns[agent_id] += reward

        if any(env.last_step_rewards):
            rewards_line = f"[step {step}] rewards -> {env.last_step_rewards}"
            events.append(rewards_line)
            print_fn(rewards_line)

    summary = ", ".join(
        f"{agent.name}={cumulative_returns[i]:.2f}"
        for i, agent in enumerate(env.agents)
    )
    per_capita = sum(cumulative_returns) / len(cumulative_returns) if cumulative_returns else 0.0
    print_fn(f"[episode end] steps={env.cur_step} returns -> {summary}")
    print_fn(f"[episode end] per-capita return -> {per_capita:.3f}")

    return EpisodeResult(
        steps=env.cur_step,
        returns=cumulative_returns,
        events=events,
    )
