from __future__ import annotations

import io
import pickle
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from word_play.core import (
    Action,
    Entity,
    Environment,
    Observation,
    Render_Context,
    Render_Result,
    Render_Scene,
    Renderer,
    Renderer_State,
    Target_Is_Self,
)
from word_play.presets.action_args import Int_Arg
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.human_io import Human_IO, Human_Text_Request
from word_play.presets.movement.simple_2d_grid import INFINITE_2D_MOVEMENT_SYSTEM, Position_2D
from word_play.presets.renderers.pygame_renderer.extractors import Speech_Bubble_Extractor
from word_play.presets.renderers import (
    Renderable,
    ReplayFrameEnvironment,
    capture_environment_frame,
    load_recording_payload,
)
from word_play.presets.systems.communication import Human_Communication_Policy, TalkingCow
from word_play.presets.systems.communication.chat_room_action_communication.core import sim_simple_conversation


class DummyRenderer(Renderer):
    def __init__(self):
        self.render_calls = 0

    def create_renderer_state(self) -> Renderer_State:
        return Renderer_State(
            frame={"renderer.default": "dummy"},
        )

    def render(self, env: Environment) -> Render_Result:
        self.render_calls += 1
        return Render_Result(reset_requested=True)


@dataclass(slots=True)
class DummyObservation(Observation):
    text: str

    def __str__(self) -> str:
        return self.text


class Self_Count_Action(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[Target_Is_Self()],
            required_kwargs={"count": Int_Arg()},
        )

    def exec_action(self, actor, target_entity, env, kwargs):
        return kwargs

    def action_description_text(self, actor, target_entity, env) -> str:
        return "Count yourself."


class DummyEnv(Environment):
    def __init__(self, entities: list[Entity], renderer: Renderer | None = None):
        super().__init__(
            description="dummy",
            entities=entities,
            movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
            reward_func=lambda actions, env: [0.0 for _ in env.agents],
            entity_order=lambda entities, env: list(range(len(entities))),
            renderer=renderer,
        )

    def observe(self, agent_id: int) -> Observation:
        return DummyObservation(
            possible_actions=self.possible_actions(self.agents[agent_id]),
            text="OBSERVATION TEXT",
        )

    def environment_start_of_step(self, action_selections):
        return None

    def environment_end_of_step(self, action_selections):
        return None

    def _reset(self, seed=None) -> None:
        return None


class RecordingHumanIO(Human_IO):
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.notifications: list[str] = []
        self.requests: list[Human_Text_Request] = []

    def notify(self, text: str, *, env: Environment | None = None) -> None:
        del env
        self.notifications.append(text)

    def request_text(self, request: Human_Text_Request, *, env: Environment | None = None) -> str:
        del env
        self.requests.append(request)
        return self.responses.pop(0)


class RenderingRefactorTests(unittest.TestCase):
    def _make_agent(self) -> Entity:
        return Entity(
            name="Agent",
            position=Position_2D(0, 0),
            actions=[Self_Count_Action()],
            components=[Human_Takes_Action(), Renderable("agent.png")],
        )

    def test_renderer_is_optional_and_render_delegates(self):
        env = DummyEnv([self._make_agent()])
        with self.assertRaises(NotImplementedError):
            env.render()

        renderer = DummyRenderer()
        env = DummyEnv([self._make_agent()], renderer=renderer)
        env.render_state.emit("speech", entity=env.state.entities[0], text="Hi", step=0)
        result = env.render()
        self.assertTrue(result.reset_requested)
        self.assertEqual(renderer.render_calls, 1)
        self.assertIs(env.renderer, renderer)
        self.assertEqual(env.render_state.events, [])
        self.assertFalse(hasattr(env, "renderer_impl"))
        self.assertFalse(hasattr(env, "renderer_recorder"))

    def test_render_context_can_store_typed_private_runtime_state(self):
        @dataclass(slots=True)
        class RuntimeBox:
            counter: int = 0

        context = Render_Context()
        first = context.value_for("runtime.box", RuntimeBox)
        second = context.value_for("runtime.box", RuntimeBox)

        first.counter = 7
        self.assertIs(first, second)
        self.assertEqual(second.counter, 7)

    def test_reset_recreates_renderer_state(self):
        renderer = DummyRenderer()
        env = DummyEnv([self._make_agent()], renderer=renderer)
        first_state = env.state.renderer_state
        env.render_state.frame["custom.namespace"] = ["value"]
        env.render_state.emit("speech", entity=env.state.entities[0], text="Hi", step=0)

        env.reset()

        self.assertIsNot(env.state.renderer_state, first_state)
        self.assertEqual(env.render_state.frame, {"renderer.default": "dummy"})
        self.assertEqual(env.render_state.events, [])

    def test_capture_environment_frame_serializes_frame_and_events(self):
        renderer = DummyRenderer()
        env = DummyEnv([self._make_agent()], renderer=renderer)
        env.render_state.frame["world.floor_sprite"] = "grass.png"
        env.render_state.emit("speech", entity=env.state.entities[0], text="Hi", step=0)

        frame = capture_environment_frame(env)

        self.assertEqual(frame["render_state_frame"]["world.floor_sprite"], "grass.png")
        self.assertEqual(
            frame["render_state_events"][0]["payload"]["entity"],
            {"__entity_ref__": 0},
        )
        self.assertEqual(frame["render_state_events"][0]["kind"], "speech")

    def test_human_policy_uses_observation_text_and_existing_kwarg_parser(self):
        env = DummyEnv([self._make_agent()])
        observation = env.observe(0)
        stdout = io.StringIO()

        with patch("builtins.input", side_effect=["0", "7"]), redirect_stdout(stdout):
            action_selection, _ = env.agents[0].get_component(Human_Takes_Action).select_action(observation)

        self.assertIn("OBSERVATION TEXT", stdout.getvalue())
        self.assertEqual(action_selection.action_kwargs, {"count": 7})

    def test_human_communication_policy_is_renderer_independent(self):
        policy = Human_Communication_Policy()
        speaker = Entity(
            name="Speaker",
            position=Position_2D(0, 0),
            components=[policy],
        )
        recipient = Entity(
            name="Recipient",
            position=Position_2D(0, 1),
            components=[TalkingCow()],
        )
        env = DummyEnv([speaker])

        with patch("builtins.input", return_value="hello"):
            message = policy.send_message([recipient], env)

        self.assertEqual(message, "hello")

    def test_human_policy_accepts_custom_human_io(self):
        io_backend = RecordingHumanIO(["0", "7"])
        agent = Entity(
            name="Agent",
            position=Position_2D(0, 0),
            actions=[Self_Count_Action()],
            components=[Human_Takes_Action(io=io_backend), Renderable("agent.png")],
        )
        env = DummyEnv([agent])

        action_selection, _ = env.agents[0].get_component(Human_Takes_Action).select_action(env.observe(0))

        self.assertEqual(action_selection.action_kwargs, {"count": 7})
        self.assertIn("OBSERVATION TEXT", io_backend.requests[0].observation_text)
        self.assertIn("Required arguments:", io_backend.requests[1].observation_text)

    def test_human_communication_policy_accepts_custom_human_io(self):
        io_backend = RecordingHumanIO(["hello"])
        policy = Human_Communication_Policy(io=io_backend)
        speaker = Entity(
            name="Speaker",
            position=Position_2D(0, 0),
            components=[policy],
        )
        recipient = Entity(
            name="Recipient",
            position=Position_2D(0, 1),
            components=[TalkingCow()],
        )
        env = DummyEnv([speaker])

        message = policy.send_message([recipient], env)

        self.assertEqual(message, "hello")
        self.assertIn("To: Recipient", io_backend.requests[0].observation_text)
        self.assertEqual(io_backend.requests[0].prompt_text(), "Speaker> ")

    def test_human_conversation_start_and_end_are_deduped_per_conversation(self):
        io_backend = RecordingHumanIO(["hello", "hi"])
        first_policy = Human_Communication_Policy(io=io_backend)
        second_policy = Human_Communication_Policy(io=io_backend)
        first = Entity(
            name="Speaker One",
            position=Position_2D(0, 0),
            components=[first_policy],
        )
        second = Entity(
            name="Speaker Two",
            position=Position_2D(0, 1),
            components=[second_policy],
        )
        env = DummyEnv([first, second])

        sim_simple_conversation([first, second], env, conversation_duration=1)

        self.assertEqual(io_backend.notifications.count("Conversation started: Speaker One, Speaker Two"), 1)
        self.assertEqual(io_backend.notifications.count("Conversation ended: Speaker One, Speaker Two"), 1)

    def test_conversation_messages_publish_into_renderer_state_events(self):
        first = Entity(
            name="Cow One",
            position=Position_2D(0, 0),
            components=[TalkingCow()],
        )
        second = Entity(
            name="Cow Two",
            position=Position_2D(0, 1),
            components=[TalkingCow()],
        )
        env = DummyEnv([first, second], renderer=DummyRenderer())

        sim_simple_conversation([first, second], env, conversation_duration=1)

        messages = [event.payload for event in env.render_state.events if event.kind == "speech"]
        self.assertEqual(len(messages), 2)
        self.assertIs(messages[0]["entity"], first)
        self.assertEqual(messages[0]["step"], env.cur_step + 1)

    def test_speech_bubbles_are_visible_during_live_mid_step_prompt_renders(self):
        agent = self._make_agent()
        env = DummyEnv([agent], renderer=DummyRenderer())
        env.render_state.emit("speech", entity=agent, text="Hello", step=env.cur_step + 1)
        scene = Render_Scene(metadata={"simulation.step": env.cur_step})

        Speech_Bubble_Extractor().extract(env, env.render_state, scene, Render_Context())

        self.assertEqual(len(scene.layers["ui.speech_bubbles"]), 1)
        self.assertEqual(scene.layers["ui.speech_bubbles"][0]["text"], "Hello")

    def test_replay_frame_environment_restores_renderer_entity_refs(self):
        renderer = DummyRenderer()
        env = DummyEnv([self._make_agent()], renderer=renderer)
        env.render_state.emit("speech", entity=env.state.entities[0], text="Hi", step=0)
        frame = capture_environment_frame(env)

        replay_env = ReplayFrameEnvironment(frame)
        speech_bubbles = [event.payload for event in replay_env.render_state.events if event.kind == "speech"]

        self.assertIs(speech_bubbles[0]["entity"], replay_env.state.entities[0])
        self.assertEqual(speech_bubbles[0]["text"], "Hi")

    def test_load_recording_payload_preserves_current_renderer_state(self):
        payload = {
            "version": 4,
            "frames": [
                {
                    "cur_step": 3,
                    "render_state_frame": {
                        "world.floor_sprite": "tile.png",
                    },
                    "render_state_events": [
                        {"kind": "speech", "payload": {"entity": {"__entity_ref__": 0}, "text": "Hi", "step": 3}}
                    ],
                    "entities": [],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            payload_path = Path(tmp_dir) / "recording.pkl"
            payload_path.write_bytes(pickle.dumps(payload))
            loaded = load_recording_payload(payload_path)

        frame = loaded["frames"][0]
        self.assertEqual(frame["render_state_frame"], payload["frames"][0]["render_state_frame"])
        self.assertEqual(frame["render_state_events"], payload["frames"][0]["render_state_events"])


if __name__ == "__main__":
    unittest.main()
