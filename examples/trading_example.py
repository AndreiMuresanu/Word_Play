from __future__ import annotations

import argparse

from word_play.core import Agent_Policy, Entity
from word_play.presets.entity_orderings import randomize_agent_order
from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
from word_play.presets.models import LLM_MODEL_REGISTRY, OpenRouter_Model
from word_play.presets.movement.simple_2d_grid import Position_2D
from word_play.presets.systems.communication.trade_communication.presets.policies import (
    LLM_Trading_Policy,
)
from word_play.presets.systems.communication.trade_communication.trade_actions import (
    Start_Private_Trade,
)
from word_play.presets.systems.currency import Money
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.inventory import Inventory


EXP_STEPS = 20


def run_exp():
    exp_steps = EXP_STEPS

    env = Simple_2D_Grid_World(
        description="A small private-trade example with two agents standing together.",
        entities=[
            Entity(
                name="Alice",
                position=Position_2D(0, 0),
                actions=[Start_Private_Trade(), Do_Nothing()],
                components=[
                    LLM_Trading_Policy(
                        model_key="trading_private",
                        system_prompt=(
                            "You are Alice. You really want Bob's Berry. "
                            "Act like an eager trader: if you can trade, do it. "
                            "Open with the vibe of 'wanna trade?' and make concrete offers. "
                            "Offer your Apple and at most 1 gold, and accept deals where you get the Berry. "
                            "Once you already have a Berry, stop trading and choose Do nothing."
                        ),
                        use_chain_of_thought=True,
                        observation_memory_window=4,
                        conversation_memory_window=8,
                    ),
                    Inventory(
                        collectable_tags=["trade_good"],
                        starting_inventory=[
                            Entity(name="Apple", position=Position_2D(0, 0), tags=["trade_good"]),
                            Entity(name="Bread", position=Position_2D(0, 0), tags=["trade_good"]),
                        ]
                    ),
                    Money(amount=3),
                ],
            ),
            Entity(
                name="Bob",
                position=Position_2D(0, 0),
                actions=[Do_Nothing()],
                components=[
                    LLM_Trading_Policy(
                        model_key="trading_private",
                        system_prompt=(
                            "You are Bob. You want Alice's Apple more than your Berry. "
                            "Act like an eager trader: if Alice wants to trade, respond with a real offer instead of waiting. "
                            "The vibe is 'wanna trade?' "
                            "Offer your Berry and accept deals where you get the Apple and maybe some gold. "
                            "Once you already have an Apple, stop trading and choose Do nothing when selecting an action."
                        ),
                        use_chain_of_thought=True,
                        observation_memory_window=4,
                        conversation_memory_window=8,
                    ),
                    Inventory(
                        collectable_tags=["trade_good"],
                        starting_inventory=[
                            Entity(name="Berry", position=Position_2D(0, 0), tags=["trade_good"]),
                            Entity(name="Herb", position=Position_2D(0, 0), tags=["trade_good"]),
                        ]
                    ),
                    Money(amount=1),
                ],
            ),
        ],
        entity_order=randomize_agent_order,
        observation_radius=0,
    )

    for step in range(exp_steps):
        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)
            print(f"[step {step}] {agent.name} -> {action}")
            cur_step_actions.append(action)

        env.step(cur_step_actions)

    return env


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--model-name", default="openai/gpt-4o-mini")
    args = parser.parse_args()

    EXP_STEPS = args.steps
    LLM_MODEL_REGISTRY.unload("trading_private")
    LLM_MODEL_REGISTRY.register(
        "trading_private",
        OpenRouter_Model,
        model_name=args.model_name,
        generation_config={"temperature": 0.2},
    )

    run_exp()
