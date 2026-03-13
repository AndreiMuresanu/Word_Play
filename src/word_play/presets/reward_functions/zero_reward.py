from src.word_play.core.environment import Action_Selection, Environment


def zero_reward_func(agent_actions: list[Action_Selection], env: Environment) -> list[float]:
    return [0] * len(env.agents)
