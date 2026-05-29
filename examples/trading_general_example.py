from __future__ import annotations

import argparse

from word_play.core import Agent_Policy, Component, Entity
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


class Trade_Goal(Component):
    def __init__(self, title: str, wants: list[str], protect: list[str], plan: str):
        super().__init__()
        self.title = title
        self.wants = wants
        self.protect = protect
        self.plan = plan
        self.complete = False

    def on_instantiation(self, env, seed) -> None:
        self._update_complete()

    def post_actions_step(self, env) -> None:
        self._update_complete()

    def _update_complete(self) -> None:
        inventory = self.entity.get_component(Inventory)
        item_names = {item.name for item in inventory.inventory} if inventory is not None else set()
        self.complete = all(item_name in item_names for item_name in self.wants)


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
                        "You are Bob, a forest apothecary with the scarce Berry. "
                        "On the first step, post a public trade offer. Offer Berry and maybe Herb, "
                        "and request Bread plus Spice or a strong counteroffer. "
                        "Your goal is complete when you have Bread and Spice. "
                        "Alice can provide Bread or Apple. Cara can provide Spice or Cheese. "
                        "After your public offer is active, choose Do nothing and let Alice or Cara accept it. "
                        "During the negotiation, protect Berry unless the other trader offers at least one goal item. "
                        "Change your offer across rounds instead of repeating the exact same deal."
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
                Trade_Goal(
                    title="Mix a spiced traveling remedy",
                    wants=["Bread", "Spice"],
                    protect=["Bread", "Spice", "Berry"],
                    plan="Post Berry publicly, then negotiate with whichever trader accepts first.",
                ),
            ],
        },
        "A": {
            "name": "Alice",
            "actions": [Accept_Public_Trade(), Do_Nothing()],
            "components": [
                LLM_Trading_Policy(
                    model_key="trading_general",
                    system_prompt=(
                        "You are Alice, a village baker. "
                        "Your goal is complete when you have Berry and Cheese. "
                        "Bob should post a public offer for Berry. If Bob's public offer is visible, "
                        "accept it and counter with Bread first, then add Apple or up to 1 gold if needed. "
                        "Do nothing only when no public offer is available or your goal is already complete. "
                        "During negotiation, say exactly what you changed in the deal."
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
                Trade_Goal(
                    title="Bake a berry-cheese tart",
                    wants=["Berry", "Cheese"],
                    protect=["Berry", "Cheese"],
                    plan="Bid for Bob's public Berry offer with Bread, then add Apple or gold if needed.",
                ),
            ],
        },
        "C": {
            "name": "Cara",
            "actions": [Accept_Public_Trade(), Do_Nothing()],
            "components": [
                LLM_Trading_Policy(
                    model_key="trading_general",
                    system_prompt=(
                        "You are Cara, a festival cook. "
                        "Your goal is complete when you have Berry and Apple. "
                        "Bob should post a public offer for Berry. If Bob's public offer is visible, "
                        "accept it and counter with Spice first, then add Cheese or up to 1 gold if needed. "
                        "Do nothing only when no public offer is available or your goal is already complete. "
                        "During negotiation, say exactly what you changed in the deal."
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
                Trade_Goal(
                    title="Prepare a berry fruit plate",
                    wants=["Berry", "Apple"],
                    protect=["Berry", "Apple", "Spice"],
                    plan="Bid for Bob's public Berry offer with Spice, then add Cheese or gold if needed.",
                ),
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
