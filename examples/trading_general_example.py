from __future__ import annotations

import argparse

from word_play.core import Agent_Policy, Component, Entity
from word_play.presets.entity_orderings import randomize_agent_order
from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
from word_play.presets.models import LLM_MODEL_REGISTRY, OpenRouter_Model
from word_play.presets.movement.simple_2d_grid import Collidable, Move_Down, Move_Left, Move_Right, Move_Up, Position_2D
from word_play.presets.renderers import Renderable, render_step
from word_play.presets.systems.communication.trade_communication.presets.policies import LLM_Trading_Policy
from word_play.presets.systems.communication.trade_communication.trade_actions import (
    Accept_Public_Trade,
    Public_Trade_Offer,
    Start_Private_Trade,
    Start_Public_Trade,
)
from word_play.presets.systems.currency import Money
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.inventory import Inventory
from word_play.utils import tilemap_to_entities


EXP_STEPS = 20


class Trade_Goal(Component):
    def __init__(
        self,
        title: str,
        wants: list[str],
        protect: list[str],
        plan: str,
    ):
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


def run_exp():
    exp_steps = EXP_STEPS

    entity_tilemap = """
    WWWW
    WABW
    WC.W
    WWWW
    """
    entity_tileset = {
        "W": {
            "name": "Wall",
            "tags": ["wall"],
            "components": [
                Collidable(),
                Renderable(
                    "sprite_library/src/world_tiles/indoors/wall_sets/bright_brick_wall/bright_brick_wall_center.png",
                    wall_set="sprite_library/src/world_tiles/indoors/wall_sets/bright_brick_wall",
                ),
            ],
        },
        "A": {
            "name": "Alice",
            "actions": [
                Move_Left(),
                Move_Right(),
                Move_Up(),
                Move_Down(),
                Start_Public_Trade(),
                Accept_Public_Trade(),
                Start_Private_Trade(),
                Do_Nothing(),
            ],
            "components": [
                Renderable("src/characters/humanoids/elf/elf.png"),
                LLM_Trading_Policy(
                    model_key="trading_general",
                    system_prompt=(
                        "You are Alice, a village baker with a high-status picnic order. "
                        "You must end with Cheese and Berry, but you also need to keep either Apple or Bread as your base. "
                        "You start with Apple, Bread, and 4 gold. Bread is more valuable to you than Apple. "
                        "Bob owns Berry but is protective of it. Cara owns Cheese and Spice and also wants Berry. "
                        "A good plan is to get Cheese from Cara without losing both foods, then compete with Cara for Bob's Berry. "
                        "Do not accept one-sided offers. Ask for extra gold or a second useful item when giving up Bread. "
                        "If someone asks for Cheese or Berry after you get it, refuse unless the offer still leaves your goal complete. "
                        "Use public offers when you want to bait both traders; use private trade when you want one focused deal. "
                        "In negotiation, visibly change your offer each round: start with a small offer, then add gold or Bread if needed, "
                        "or remove Bread and offer Apple plus gold if the price is too high. "
                        "Say what you changed, like 'I'll add 1 gold' or 'Bread is too much; I'll switch to Apple'. "
                        "If your goal is already complete and you still have Apple or Bread, do nothing."
                    ),
                    use_chain_of_thought=False,
                    observation_memory_window=4,
                    conversation_memory_window=8,
                ),
                Inventory(
                    collectable_tags=["trade_good"],
                    starting_inventory=[
                        Entity(
                            name="Apple",
                            position=Position_2D(0, 0),
                            tags=["trade_good"],
                            components=[Renderable("src/items/consumables/lpc_food/apple.png")],
                        ),
                        Entity(
                            name="Bread",
                            position=Position_2D(0, 0),
                            tags=["trade_good"],
                            components=[Renderable("src/items/consumables/lpc_food/bread.png")],
                        ),
                    ],
                ),
                Money(amount=4),
                Public_Trade_Offer(),
                Trade_Goal(
                    title="Bake a berry-cheese tart",
                    wants=["Cheese", "Berry"],
                    protect=["Cheese", "Berry"],
                    plan=(
                        "First find Cara for Cheese using Apple or Bread. Later find Bob for Berry using "
                        "spare food or gold. Do not trade just because someone is adjacent."
                    ),
                ),
                Collidable(collidable_tags=["wall"]),
            ],
        },
        "B": {
            "name": "Bob",
            "actions": [
                Move_Left(),
                Move_Right(),
                Move_Up(),
                Move_Down(),
                Start_Public_Trade(),
                Accept_Public_Trade(),
                Start_Private_Trade(),
                Do_Nothing(),
            ],
            "components": [
                Renderable("src/characters/humanoids/elf/wood_elf.png"),
                LLM_Trading_Policy(
                    model_key="trading_general",
                    system_prompt=(
                        "You are Bob, a forest apothecary with the scarce item everyone wants: Berry. "
                        "Your goal is complete when your inventory has Spice and Bread. "
                        "You start with Berry, Herb, and 1 gold. Berry is your leverage; do not give it away for just one cheap item. "
                        "Alice can provide Bread. Cara can provide Spice. The best outcome is getting both Bread and Spice for Berry plus Herb or gold. "
                        "Prefer offers where you receive Spice first, then Bread. If only one goal item is offered for Berry, negotiate for more. "
                        "Herb is expendable. Gold is less important than Bread and Spice. "
                        "Use private trade if you see a path to a bundle deal. Post a public offer if you want Alice and Cara to bid against each other. "
                        "In negotiation, visibly change your offer each round: start expensive for Berry, then add Herb, remove gold, "
                        "or demand an extra item when Alice or Cara underpays. "
                        "Say what changed, like 'Add Bread and I add Herb' or 'No Berry unless Spice is included'. "
                        "If your goal is complete, do nothing unless a trade improves your inventory without losing Bread or Spice."
                    ),
                    use_chain_of_thought=False,
                    observation_memory_window=4,
                    conversation_memory_window=8,
                ),
                Inventory(
                    collectable_tags=["trade_good"],
                    starting_inventory=[
                        Entity(
                            name="Berry",
                            position=Position_2D(0, 0),
                            tags=["trade_good"],
                            components=[Renderable("src/items/consumables/vegetables/berry_blue.png")],
                        ),
                        Entity(
                            name="Herb",
                            position=Position_2D(0, 0),
                            tags=["trade_good"],
                            components=[Renderable("src/items/materials/misc/young_herb_cluster.png")],
                        ),
                    ],
                ),
                Money(amount=1),
                Public_Trade_Offer(),
                Trade_Goal(
                    title="Mix a spiced traveling remedy",
                    wants=["Spice", "Bread"],
                    protect=["Spice", "Bread"],
                    plan=(
                        "Find Cara for Spice. Find Alice for Bread if needed. Keep Berry unless the offer "
                        "clearly pays for one of the goal items."
                    ),
                ),
                Collidable(collidable_tags=["wall"]),
            ],
        },
        "C": {
            "name": "Cara",
            "actions": [
                Move_Left(),
                Move_Right(),
                Move_Up(),
                Move_Down(),
                Start_Public_Trade(),
                Accept_Public_Trade(),
                Start_Private_Trade(),
                Do_Nothing(),
            ],
            "components": [
                Renderable("src/characters/humanoids/elf/gray_elf.png"),
                LLM_Trading_Policy(
                    model_key="trading_general",
                    system_prompt=(
                        "You are Cara, a festival cook trying to assemble the prettiest fruit plate. "
                        "Your goal is complete when your inventory has Apple and Berry. "
                        "You start with Cheese, Spice, and 2 gold. Spice is very valuable because Bob needs it; Cheese is easier to part with. "
                        "Alice has Apple and Bread. Bob has Berry and knows both you and Alice want it. "
                        "A strong plan is to trade Cheese to Alice for Apple, then use Spice as leverage for Bob's Berry. "
                        "Do not trade Spice unless Bob gives Berry or an offer that clearly helps you get Berry next. "
                        "If Alice wants Cheese, ask for Apple plus a little gold or Bread. "
                        "Public offers can make Bob reveal his price; private trade is better when you already know what you want. "
                        "In negotiation, visibly change your offer each round: start with Cheese, then add gold, remove gold, "
                        "or reluctantly add Spice only if Berry is on the table. "
                        "Say what changed, like 'I'll add 1 gold' or 'Spice only for Berry'. "
                        "If your goal is complete, protect Apple and Berry and do nothing."
                    ),
                    use_chain_of_thought=False,
                    observation_memory_window=4,
                    conversation_memory_window=8,
                ),
                Inventory(
                    collectable_tags=["trade_good"],
                    starting_inventory=[
                        Entity(
                            name="Cheese",
                            position=Position_2D(0, 0),
                            tags=["trade_good"],
                            components=[Renderable("src/items/consumables/lpc_food/cheese.png")],
                        ),
                        Entity(
                            name="Spice",
                            position=Position_2D(0, 0),
                            tags=["trade_good"],
                            components=[Renderable("src/items/consumables/magic/orange_scroll.png")],
                        ),
                    ],
                ),
                Money(amount=2),
                Public_Trade_Offer(),
                Trade_Goal(
                    title="Prepare a fruit festival platter",
                    wants=["Apple", "Berry"],
                    protect=["Apple", "Berry"],
                    plan=(
                        "Trade Cheese with Alice for Apple. Trade Spice with Bob for Berry. Once both are "
                        "collected, stop trading."
                    ),
                ),
                Collidable(collidable_tags=["wall"]),
            ],
        },
    }

    env = Simple_2D_Grid_World(
        description=(
            "A tiny closed market with three traders and a scarce Berry. Alice and Cara both want Berry, "
            "Bob needs one item from each of them, and several items should only move as part of a fair bundle. "
            "Good trades require negotiation instead of accepting the first adjacent offer."
        ),
        entities=tilemap_to_entities(entity_tilemap, entity_tileset),
        entity_order=randomize_agent_order,
        observation_radius=6,
    )
    env.floor_sprite = "sprite_library/src/world_tiles/indoors/floors/day_grass_floor_c.png"

    for step in range(exp_steps):
        if not render_step(env):
            break

        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)
            print(f"[step {step}] {agent.name} -> {action}")
            cur_step_actions.append(action)

        env.step(cur_step_actions)
        if not render_step(env, step_delay=0.45):
            break

    return env


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--model-name", default="openai/gpt-4o-mini")
    args = parser.parse_args()

    EXP_STEPS = args.steps
    LLM_MODEL_REGISTRY.unload("trading_general")
    LLM_MODEL_REGISTRY.register(
        "trading_general",
        OpenRouter_Model,
        model_name=args.model_name,
        generation_config={"temperature": 0.2},
    )

    run_exp()
