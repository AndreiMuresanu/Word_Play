from src.word_play.core.environment import Action_Selection


def format_possible_actions(possible_actions: list[Action_Selection]) -> str:
    obs_str = ""
    if possible_actions:
        for idx, action_selection in enumerate(possible_actions):
            obs_str += f"\n[{idx}]: {action_selection}"
    else:
        obs_str += "\nNo possible actions"
    return obs_str
