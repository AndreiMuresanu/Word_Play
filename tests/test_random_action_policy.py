from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest.mock import patch

from word_play.core import Action, Action_Selection, Entity, Observation, Target_Is_Self
from word_play.presets.action_args import Int_Arg
from word_play.presets.action_policies.random_action import Random_Action_Policy
from word_play.presets.movement.simple_2d_grid import Position_2D


@dataclass(slots=True)
class DummyObservation(Observation):
    text: str = "dummy"

    def __str__(self) -> str:
        return self.text


class Wait_Action(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor, target_entity, env, kwargs):
        return None

    def action_description_text(self, actor, target_entity, env) -> str:
        return "Wait."


class Count_Action(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()], required_kwargs={"count": Int_Arg()})

    def exec_action(self, actor, target_entity, env, kwargs):
        return kwargs

    def action_description_text(self, actor, target_entity, env) -> str:
        return "Count."


class TestRandomActionPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.actor = Entity(name="Agent", position=Position_2D(0, 0))
        self.env = object()
        self.policy = Random_Action_Policy()

    def test_select_action_samples_only_valid_actions(self) -> None:
        valid_a = Action_Selection(
            action=Wait_Action(),
            action_kwargs=None,
            actor=self.actor,
            target_entity=self.actor,
            env=self.env,
        )
        valid_b = Action_Selection(
            action=Wait_Action(),
            action_kwargs=None,
            actor=self.actor,
            target_entity=self.actor,
            env=self.env,
        )
        missing_kwargs = Action_Selection(
            action=Count_Action(),
            action_kwargs=None,
            actor=self.actor,
            target_entity=self.actor,
            env=self.env,
        )
        observation = DummyObservation(possible_actions=[valid_a, missing_kwargs, valid_b])

        with patch(
            "word_play.presets.action_policies.random_action.random.choice",
            return_value=valid_b,
        ) as mocked_choice:
            action_selection, info = self.policy.select_action(observation)

        mocked_choice.assert_called_once_with([valid_a, valid_b])
        self.assertIs(action_selection, valid_b)
        self.assertEqual(info, {"selection_mode": "uniform_random"})

    def test_select_action_raises_when_no_actions_are_ready(self) -> None:
        observation = DummyObservation(
            possible_actions=[
                Action_Selection(
                    action=Count_Action(),
                    action_kwargs=None,
                    actor=self.actor,
                    target_entity=self.actor,
                    env=self.env,
                )
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "at least one valid action selection"):
            self.policy.select_action(observation)


if __name__ == "__main__":
    unittest.main()
