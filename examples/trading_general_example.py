from __future__ import annotations

import argparse

from word_play.core import Agent_Policy, Entity
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
from word_play.presets.models import LLM_MODEL_REGISTRY, OpenRouter_Model
from word_play.presets.movement.simple_2d_grid import Position_2D
from word_play.presets.systems.communication.trade_communication.presets.policies import LLM_Trading_Policy
from word_play.presets.systems.communication.trade_communication.trade_actions import (
    Accept_Public_Trade,
    Public_Trade_Offer,
    Start_Public_Trade,
)
from word_play.presets.systems.currency import Money
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.inventory import Inventory
from word_play.utils import tilemap_to_entities


def run_exp(exp_steps: int):
    entity_tilemap = [
        [".", ".", "."],
        [".", ["B", "A", "C"], "."],
        [".", ".", "."],
    ]
    entity_tileset = {
        "B": {
            "name": "Bob",
            "actions": [Start_Public_Trade(), Do_Nothing()],
            "components": [
                LLM_Trading_Policy(
                    model_key="trading_general",
                    system_prompt=(
                        "You are Bob, a forest apothecary. You have Berry and Herb. "
                        "You want Bread and Spice, and you dislike giving away Berry without getting one. "
                        "First post Berry as a public offer for Bread plus Spice or a strong counteroffer. "
                        "After posting, choose Do nothing and let Alice or Cara accept."
                    ),
                    use_chain_of_thought=False,
                    action_generation_config={"temperature": 0.25},
                    message_generation_config={"temperature": 0.5},
                    observation_memory_window=4,
                    conversation_memory_window=8,
                ),
                Inventory(
                    collectable_tags=["trade_good"],
                    starting_inventory=[
                        Entity(name="Berry", position=Position_2D(0, 0), tags=["trade_good"]),
                        Entity(name="Herb", position=Position_2D(0, 0), tags=["trade_good"]),
                    ],
                ),
                Money(amount=1),
                Public_Trade_Offer(),
            ],
        },
        "A": {
            "name": "Alice",
            "actions": [Accept_Public_Trade(), Do_Nothing()],
            "components": [
                LLM_Trading_Policy(
                    model_key="trading_general",
                    system_prompt=(
                        "You are Alice, a village baker. You have Bread, Apple, and gold. "
                        "You want Berry and Cheese, and you prefer to keep them once you have them. "
                        "If Bob posts Berry publicly, accept and offer Bread; add Apple or 1 gold if needed. "
                        "Otherwise choose Do nothing. In chat, say what changed in your offer."
                    ),
                    use_chain_of_thought=False,
                    action_generation_config={"temperature": 0.25},
                    message_generation_config={"temperature": 0.5},
                    observation_memory_window=4,
                    conversation_memory_window=8,
                ),
                Inventory(
                    collectable_tags=["trade_good"],
                    starting_inventory=[
                        Entity(name="Bread", position=Position_2D(0, 0), tags=["trade_good"]),
                        Entity(name="Apple", position=Position_2D(0, 0), tags=["trade_good"]),
                    ],
                ),
                Money(amount=3),
            ],
        },
        "C": {
            "name": "Cara",
            "actions": [Accept_Public_Trade(), Do_Nothing()],
            "components": [
                LLM_Trading_Policy(
                    model_key="trading_general",
                    system_prompt=(
                        "You are Cara, a festival cook. You have Spice, Cheese, and gold. "
                        "You want Berry and Apple, and you value Spice. "
                        "If Bob posts Berry publicly, accept and offer Spice; add Cheese or 1 gold if needed. "
                        "Otherwise choose Do nothing. In chat, say what changed in your offer."
                    ),
                    use_chain_of_thought=False,
                    action_generation_config={"temperature": 0.25},
                    message_generation_config={"temperature": 0.5},
                    observation_memory_window=4,
                    conversation_memory_window=8,
                ),
                Inventory(
                    collectable_tags=["trade_good"],
                    starting_inventory=[
                        Entity(name="Spice", position=Position_2D(0, 0), tags=["trade_good"]),
                        Entity(name="Cheese", position=Position_2D(0, 0), tags=["trade_good"]),
                    ],
                ),
                Money(amount=2),
            ],
        },
    }

    env = Simple_2D_Grid_World(
        description=(
            "A three-person public-trade market. Bob owns the scarce Berry and posts it publicly. "
            "Alice and Cara can both see and accept that public offer, but only the first successful acceptor "
            "gets the negotiation."
        ),
        entities=tilemap_to_entities(entity_tilemap, entity_tileset),
        entity_order=entity_definition_order,
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

    for agent in env.agents:
        inventory = agent.get_component(Inventory)
        money = agent.get_component(Money)
        print(f"{agent.name} final inventory: {inventory or 'empty'}; money: {money or 'no money'}")

    return env


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--model-name", default="openai/gpt-4o-mini")
    args = parser.parse_args()

    LLM_MODEL_REGISTRY.unload("trading_general")
    LLM_MODEL_REGISTRY.register(
        "trading_general",
        OpenRouter_Model,
        model_name=args.model_name,
        generation_config={"temperature": 0.25},
    )

    run_exp(args.steps)
