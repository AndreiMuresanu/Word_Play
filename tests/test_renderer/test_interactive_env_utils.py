from __future__ import annotations

import json
import pickle

from examples.overcooked.environment import OvercookedKitchenEnv, SinglePlayerOvercookedEnv, select_policy_actions
from experiments.overcooked_kitchen_experiment import run_experiment
from word_play.presets.renderers.replay_and_live import ReplayFrameEnvironment
from word_play.utils import ExperimentRecorder, InteractiveEnvironmentSession, capture_environment_frame


def test_capture_environment_frame_includes_overcooked_state() -> None:
    env = OvercookedKitchenEnv(renderer=None)

    frame = capture_environment_frame(env, frame_type="initial", notes=["boot"])

    assert frame["frame_type"] == "initial"
    assert frame["description"] == env.description
    assert frame["tick"] == 0
    assert frame["notes"] == ["boot"]
    assert frame["entities"]
    assert frame["background_tiles"]
    assert "Prep Cook" in frame["available_actions"]
    assert frame["agent_observations"]
    assert frame["agent_observations"][0]["possible_actions"]


def test_experiment_recorder_writes_overcooked_replay(tmp_path) -> None:
    log_path = tmp_path / "overcooked_replay.pkl"

    summary = run_experiment(render=False, log_path=str(log_path))

    payload = pickle.loads(log_path.read_bytes())
    assert payload["title"] == "Overcooked Kitchen Replay"
    assert payload["frame_count"] == len(payload["frames"])
    assert payload["frame_count"] >= 2
    assert payload["frames"][0]["frame_type"] == "initial"
    assert payload["frames"][-1]["selected_actions"]
    assert summary["tick"] > 0
    assert summary["recent_events"]


def test_interactive_session_can_submit_a_step_without_server() -> None:
    session = InteractiveEnvironmentSession(OvercookedKitchenEnv(renderer=None), title="Interactive Overcooked Session")

    snapshot = session.snapshot()
    initial_history_length = len(snapshot["history"])
    assert snapshot["mode"] == "interactive"
    assert snapshot["history"]
    assert snapshot["agents"]

    action_requests = []
    for agent in snapshot["agents"]:
        action_requests.append(
            {
                "agent_name": agent["agent_name"],
                "action_index": 0,
                "kwargs_text": "",
            }
        )

    updated_snapshot = session.submit_step(action_requests)
    assert len(updated_snapshot["history"]) == initial_history_length + 1
    assert updated_snapshot["current_frame"]["frame_type"] == "step"
    assert updated_snapshot["current_frame"]["selected_actions"]


def test_experiment_recorder_round_trips_payload(tmp_path) -> None:
    env = OvercookedKitchenEnv(renderer=None)
    recorder = ExperimentRecorder(tmp_path / "manual_replay.pkl", title="Manual Replay")

    frame = recorder.record(env, frame_type="initial", notes=["manual"])
    payload = pickle.loads((tmp_path / "manual_replay.pkl").read_bytes())
    newest_payload = pickle.loads((tmp_path / "manual_replay_newest.pkl").read_bytes())

    assert frame["frame_index"] == 0
    assert payload["title"] == "Manual Replay"
    assert payload["frame_count"] == 1
    assert payload["frames"][0]["notes"] == ["manual"]
    assert newest_payload == payload


def test_replay_frame_environment_restores_hit_effects_and_health_components() -> None:
    env = OvercookedKitchenEnv(renderer=None)
    agent = env.agents[0]
    health = next(component for component in agent.components.values() if hasattr(component, "health"))
    health.health -= 1
    env.hit_effects = [{"entity_name": agent.name, "sprite": "effects/hit.png", "scale": 0.75}]

    frame = capture_environment_frame(env, frame_type="step")
    replay_env = ReplayFrameEnvironment(frame)
    replay_agent = next(entity for entity in replay_env.state.entities if entity.name == agent.name)
    replay_health = next(component for component in replay_agent.components.values() if hasattr(component, "health"))

    assert replay_env.hit_effects == env.hit_effects
    assert replay_env.hit_entity_names == [agent.name]
    assert replay_health.health == health.health


def test_replay_frame_environment_restores_visibility_and_agent_flags() -> None:
    env = OvercookedKitchenEnv(renderer=None)
    frame = capture_environment_frame(env, frame_type="initial")
    replay_env = ReplayFrameEnvironment(frame)

    assert replay_env.agents
    assert replay_env.agents[0].is_agent is True

    dungeon_like_frame = {
        **frame,
        "sight_radius": 2,
        "visible_tiles": [[0, 0], [1, 1], [2, 2]],
    }
    dungeon_replay_env = ReplayFrameEnvironment(dungeon_like_frame)
    assert dungeon_replay_env.sight_radius == 2
    assert dungeon_replay_env.visible_tiles() == [(0, 0), (1, 1), (2, 2)]


def test_replay_frame_environment_rebuilds_sidebar_fields_when_missing() -> None:
    env = OvercookedKitchenEnv(renderer=None)
    frame = capture_environment_frame(env, frame_type="step")
    frame["hud_sidebar_selected_action"] = []
    frame["hud_sidebar_actions"] = []
    frame["selected_actions"] = [{"label": "Wait", "actor_name": env.agents[0].name}]
    replay_env = ReplayFrameEnvironment(frame)

    assert replay_env.hud_sidebar_selected_action == ["Chosen Action:", "Wait"]
    assert replay_env.hud_sidebar_actions[0] == "Possible Actions:"
    assert len(replay_env.hud_sidebar_actions) > 1


def test_overcooked_policy_path_produces_actions() -> None:
    env = OvercookedKitchenEnv(renderer=None)

    selections = select_policy_actions(env)

    assert len(selections) == len(env.agents)
    assert all(selection.actor in env.agents for selection in selections)


def test_single_player_overcooked_env_has_one_agent() -> None:
    env = SinglePlayerOvercookedEnv(renderer=None)

    assert len(env.agents) == 1
    assert env.agents[0].name == "Line Cook"
    assert env.order_queue
