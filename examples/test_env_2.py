from word_play.core import (
    Action,
    Agent_Policy,
    Component,
    Entity,
    Environment,
    Observation,
    Target_Is_Nearby,
    Target_Is_Self,
    Target_Not_Self,
)
from word_play.presets.action_args import (
    Dict_Arg,
    Dynamic_Choice_Arg,
    Int_Arg,
    List_Arg,
    String_Arg,
    String_Choice_Arg,
    arg_in_range,
)
from word_play.presets.action_policies.follow_action_sequence import Follow_Action_Sequence
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.entity_orderings import entity_definition_order, random_order, randomize_agent_order
from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
from word_play.presets.movement.simple_2d_grid import (
    Collidable,
    Move_Up,
    Move_Down,
    Move_Left,
    Move_Right,
    Position_2D,
)
from word_play.presets.systems.combat import Attack
from word_play.presets.systems.communication import (
    Human_Communication_Policy,
    Start_Private_Conversation,
    Start_Public_Conversation,
    TalkingCow,
)
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.health import Health
from word_play.presets.systems.inventory import Inventory
from word_play.presets.models import Human_Model, Lazy_Model_Handle, LLM_MODEL_REGISTRY
from word_play.utils import tilemap_to_entities

import pprint
import sys


class Test_Action(Action):

    def __init__(self):
        super().__init__(
            validation_rules=[Target_Is_Self()],
            required_kwargs={
                "gold coin count": Int_Arg(),
                "assignment": Dict_Arg(String_Arg(), Int_Arg()),
                "damages": List_Arg(Int_Arg()),
                "item": String_Choice_Arg({"hammer", "apple"}),
            },
        )

    def exec_action(self, actor, target_entity, env, kwargs):
        print("=======")
        pprint.pprint(kwargs, sort_dicts=False)
        print("=======")

    def action_description_text(self, actor, target_entity, env):
        return "Test Action."


def register_run_exp_model(model_mode: str) -> str:
    model_key = "run_exp_llm"
    if model_mode == "human_llm":
        LLM_MODEL_REGISTRY[model_key] = Lazy_Model_Handle(lambda: Human_Model())
    else:
        raise ValueError(f"Unsupported model_mode: {model_mode}")
    return model_key


def run_exp(model_mode: str = "human_action"):
    exp_steps = 1000
    model_key = register_run_exp_model(model_mode) if model_mode == "human_llm" else None

    env = Simple_2D_Grid_World(
        description="The forbidden forest.",
        entities=[
            Entity(
                name="Iskandar",
                position=Position_2D(0, 0),
                actions=[
                    Test_Action(),
                    Do_Nothing(),
                    Move_Up(),
                    Move_Down(),
                    Move_Left(),
                    Move_Right(),
                    Attack(name="Zap", damage_amount=1),
                    Start_Public_Conversation(),
                    Start_Private_Conversation(),
                ],
                components=[
                    LLM_Action_And_Communication_Policy(model_key=model_key) if model_mode == "human_llm" else Human_Takes_Action(),
                    Inventory(
                        collectable_tags=["item"],
                        inventory_size=2,
                        starting_inventory=[Entity(name="Strawberry", position=Position_2D(100, 100), tags=["item"])],
                    ),
                    Health(max_health=5, starting_health=3),
                    Collidable(collidable_tags=["wall"]),
                    Human_Communication_Policy(),
                ],
            ),
            # Entity(
            #     name="Andrei",
            #     position=Position_2D(0, 0),
            #     actions=[
            #         Do_Nothing(),
            #         Move_Up(),
            #         Move_Down(),
            #         Move_Left(),
            #         Move_Right(),
            #         Attack(name="Zap", damage_amount=1),
            #     ],
            #     components=[
            #         Human_Takes_Action(),
            #         Inventory(
            #             collectable_tags=["item"],
            #             inventory_size=2,
            #             starting_inventory=[
            #                 Entity(name="Strawberry", position=Position_2D(100, 100), tags=["item"])
            #             ],
            #         ),
            #         Health(max_health=5, starting_health=3),
            #         Collidable(collidable_tags=["wall"]),
            #     ],
            # ),
            Entity(name="Blue Flower", position=Position_2D(0, 1), tags=["item"]),
            Entity(
                name="Barrel",
                position=Position_2D(0, 0),
                tags=["item"],
                components=[Health(max_health=1, starting_health=1)],
            ),
            Entity(
                name="Barrel",
                position=Position_2D(0, 1),
                tags=["item"],
                components=[Health(max_health=1, starting_health=1)],
            ),
            Entity(
                name="Cow",
                position=Position_2D(1, 0),
                actions=[Move_Up(), Move_Down()],
                components=[
                    Health(max_health=5, starting_health=5),
                    Follow_Action_Sequence([(Move_Up, None), (Move_Down, None)]),
                    TalkingCow(),
                ],
            ),
            Entity(
                name="Fat Cow",
                position=Position_2D(1, 0),
                components=[
                    Health(max_health=10, starting_health=10),
                    TalkingCow(),
                ],
            ),
            Entity(
                name="Tiny Cow",
                position=Position_2D(1, 0),
                components=[
                    Health(max_health=1, starting_health=1),
                    TalkingCow(),
                ],
            ),
            Entity(
                name="Wall",
                position=Position_2D(-1, 0),
                tags=["wall"],
                components=[Collidable()],
            ),
            # TODO: for a real pike entity, you likely want an Attack_All_Nearby_Entities action instead of Attack
            Entity(
                name="Spike",
                position=Position_2D(0, -2),
                actions=[Attack(name="Poke", damage_amount=1)],
                tags=["item"],
                components=[Follow_Action_Sequence([(Attack, None)])],
            ),
        ],
        entity_order=entity_definition_order,
    )

    for step in range(exp_steps):
        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)
            print(f"[step {step}] {agent.name} -> {action}")
            if info:
                if info.get("reasoning"):
                    print(f"[step {step}] reasoning:\n{info['reasoning']}")
                if info.get("raw_response"):
                    print(f"[step {step}] raw response:\n{info['raw_response']}")
            cur_step_actions.append(action)

        env.step(cur_step_actions)


if __name__ == "__main__":
    run_exp(sys.argv[1] if len(sys.argv) > 1 else "human_action")
