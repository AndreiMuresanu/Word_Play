from word_play.environment import Action_Selection, Observation
from dataclasses import dataclass

"""NOTE: this will be useful when we create a dicussion phase style communication system"""


def format_possible_actions(possible_actions: list[Action_Selection]) -> str:
    obs_str = ""
    if possible_actions:
        for idx, action_selection in enumerate(possible_actions):
            obs_str += f"\n[{idx}]: {action_selection}"
    else:
        obs_str += "\nNo possible actions"
    return obs_str


# TODO: DELETE, THIS IS FOR THE SIMULATANIOUS CONVERSATION ENV
def format_conversation(conversation: list[str], all_agent_names: list[str], observing_agent_id: int) -> str:
    obs_str = ""
    for agent_id, (agent_name, message) in enumerate(zip(all_agent_names, conversation)):
        if message:
            if agent_id == observing_agent_id:
                obs_str += f'\n(Me) {agent_name}: "{message}"'
            else:
                obs_str += f'\n{agent_name}: "{message}"'
    obs_str = obs_str.strip()
    if obs_str == "":
        obs_str = "No messages."
    return obs_str


# TODO: DELETE, THIS IS FOR THE SIMULATANIOUS CONVERSATION ENV
def format_conversation_history(
    conversation_history: list[list[str]], all_agent_names: list[str], observing_agent_id: int
) -> str:
    obs_str = "Conversation History:"
    for round_idx, conversation in enumerate(conversation_history, start=1):
        obs_str += f"\nRound {round_idx}:"
        obs_str += format_conversation(conversation, all_agent_names, observing_agent_id)
    return obs_str


def format_discussion_phase(
    discussion_messages: list[list[tuple[int, str]]],
    discussion_phase_turn_count: int,
    all_agent_names: list[str],
    observing_agent_id: int,
) -> str:
    obs_str = ""
    for turn_idx, turn_messages in enumerate(discussion_messages, start=1):
        obs_str += f"\n\n----- Discussion, Turn {turn_idx}/{discussion_phase_turn_count} -----"
        if not turn_messages:
            obs_str += "\nNo messages."
            continue
        for agent_id, message in turn_messages:
            agent_name = all_agent_names[agent_id]
            if agent_id == observing_agent_id:
                obs_str += f'\n(Me) {agent_name}: "{message}"'
            else:
                obs_str += f'\n{agent_name}: "{message}"'
    return obs_str.strip()


def format_actions_taken(
    actions_taken: list[Action_Selection], all_agent_names: list[str], observing_agent_id: int
) -> str:
    obs_str = ""
    for agent_id, action_selection in enumerate(actions_taken):
        agent_name = all_agent_names[agent_id]
        if agent_id == observing_agent_id:
            obs_str += f"\n(Me) {agent_name}: {action_selection}"
        else:
            obs_str += f"\n{agent_name}: {action_selection}"
    return obs_str.strip()


@dataclass(slots=True)
class Possible_Actions_And_Last_Reward(Observation):
    last_reward: float

    def __str__(self) -> str:
        return f"Previous Round Reward: {self.last_reward}\n\nPossible Actions:\n{format_possible_actions(self.possible_actions)}"


@dataclass(slots=True)
class Conversation_Possible_Actions_And_Last_Reward(Observation):
    last_reward: float
    conversation: list[str]
    all_agent_names: list[str]
    observing_agent_id: int

    def __str__(self) -> str:
        return f"Messages From Players:\n{format_conversation(self.conversation, self.all_agent_names, self.observing_agent_id)}\n\nPrevious Round Reward: {self.last_reward}\n\nPossible Actions:\n{format_possible_actions(self.possible_actions)}"


@dataclass(slots=True)
class Discussion_Phase_With_Full_Info(Observation):
    last_reward: float
    # NOTE: we can filter out message from non-nearby agents when initializing the observation
    discussion_messages: list[list[tuple[int, str]]]
    discussion_phase_turn_count: int
    all_agent_names: list[str]
    observing_agent_id: int

    def __str__(self) -> str:
        return f"Discussion Phase:\n{format_discussion_phase(self.discussion_messages, self.discussion_phase_turn_count, self.all_agent_names, self.observing_agent_id)}\n\nPrevious Round Reward: {self.last_reward}\n\nPossible Actions:\n{format_possible_actions(self.possible_actions)}"
