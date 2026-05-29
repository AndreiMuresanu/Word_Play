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


def run_exp(exp_steps: int):

    env = Simple_2D_Grid_World(
        description=(
            "A small private-trade market. Alice is trying to assemble a festival basket, "
            "while Bob is trying to gather ingredients for a picnic tonic."
        ),
        entities=[
            Entity(
                name="Alice",
                position=Position_2D(0, 0),
                actions=[Start_Private_Trade(), Do_Nothing()],
                components=[
                    LLM_Trading_Policy(
                        model_key="trading_private",
                        system_prompt=(
                            "You are Alice, a baker. You have Apple, Honey, Bread, Coffee Beans, and gold. "
                            "You want Bob's Cheese and Berry; Honey is valuable. "
                            "Start trades by offering Apple or Bread for Berry. "
                            "Only add Honey or extra gold if Bob includes Cheese. "
                            "Once you have Cheese and Berry, choose Do nothing."
                        ),
                        use_chain_of_thought=False,
                        action_generation_config={"temperature": 0.35},
                        message_generation_config={"temperature": 0.55},
                        observation_memory_window=4,
                        conversation_memory_window=8,
                    ),
                    Inventory(
                        collectable_tags=["trade_good"],
                        starting_inventory=[
                            Entity(name="Apple", position=Position_2D(0, 0), tags=["trade_good"]),
                            Entity(name="Honey", position=Position_2D(0, 0), tags=["trade_good"]),
                            Entity(name="Bread", position=Position_2D(0, 0), tags=["trade_good"]),
                            Entity(name="Coffee Beans", position=Position_2D(0, 0), tags=["trade_good"]),
                        ],
                    ),
                    Money(amount=5),
                ],
            ),
            Entity(
                name="Bob",
                position=Position_2D(0, 0),
                actions=[Start_Private_Trade(), Do_Nothing()],
                components=[
                    LLM_Trading_Policy(
                        model_key="trading_private",
                        system_prompt=(
                            "You are Bob, a cook. You have Berry, Cheese, Herb, Spice, and gold. "
                            "You want Alice's Honey and Apple; Cheese is valuable. "
                            "Trade Berry for Apple, but ask for Honey or gold before giving Cheese. "
                            "Use Herb or Spice as small sweeteners. "
                            "Once you have Honey and Apple, choose Do nothing."
                        ),
                        use_chain_of_thought=False,
                        action_generation_config={"temperature": 0.35},
                        message_generation_config={"temperature": 0.55},
                        observation_memory_window=4,
                        conversation_memory_window=8,
                    ),
                    Inventory(
                        collectable_tags=["trade_good"],
                        starting_inventory=[
                            Entity(name="Berry", position=Position_2D(0, 0), tags=["trade_good"]),
                            Entity(name="Cheese", position=Position_2D(0, 0), tags=["trade_good"]),
                            Entity(name="Herb", position=Position_2D(0, 0), tags=["trade_good"]),
                            Entity(name="Spice", position=Position_2D(0, 0), tags=["trade_good"]),
                        ],
                    ),
                    Money(amount=2),
                ],
            ),
        ],
        entity_order=randomize_agent_order,
        observation_radius=0,
    )
    for agent in env.agents:
        allowed_actions = (Start_Private_Trade, Do_Nothing)
        agent.actions = [action for action in agent.actions if isinstance(action, allowed_actions)]

    for step in range(exp_steps):
        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)
            print(f"[step {step}] {agent.name} -> {action}")
            cur_step_actions.append(action)

        env.step(cur_step_actions)

    for agent in env.agents:
        inventory = agent.get_component(Inventory)
        money = agent.get_component(Money)
        print(f"{agent.name} final inventory: {inventory or 'empty'}; money: {money or 'no money'}")

    return env


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--model-name", default="openai/gpt-4o-mini")
    args = parser.parse_args()

    LLM_MODEL_REGISTRY.unload("trading_private")
    LLM_MODEL_REGISTRY.register(
        "trading_private",
        OpenRouter_Model,
        model_name=args.model_name,
        generation_config={"temperature": 0.35},
    )

    run_exp(args.steps)
