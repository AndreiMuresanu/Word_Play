from __future__ import annotations

import json
import pickle

from examples.overcooked.environment import OvercookedKitchenEnv, SinglePlayerOvercookedEnv, select_policy_actions
from experiments.overcooked_kitchen_experiment import run_experiment
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

    assert frame["frame_index"] == 0
    assert payload["title"] == "Manual Replay"
    assert payload["frame_count"] == 1
    assert payload["frames"][0]["notes"] == ["manual"]


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
