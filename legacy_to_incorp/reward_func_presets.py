from word_play.environment import Action_Selection, Environment


def zero_reward_func(agent_actions: list[Action_Selection], env: Environment) -> list[float]:
	return [0] * len(env.agents)


'''
# Some examples reward function examples.
# These are not presets because they depend on a (non-existent) Environment implementation


def avoid_low_health(agent_actions: list[Action_Selections], env: Environment) -> list[float]:
	rewards = []
	for agent in env.agents:
		rewards.append(agent.cur_health - agent.max_health)
	return rewards


def negative_reward_when_getting_zapped(agent_actions: list[Action_Selections], env: Environment) -> list[float]:
	rewards = [0] * len(env.agents)
	for actor_agent_idx, action_selection in enumerate(agent_actions):
		if isinstance(action_selection.action, Zap):
			rewards[env.agent_to_idx(action_selection.target_entity)] -= 10
			rewards[actor_agent_idx] += 5
	return rewards


def a_mix_of_reward_functions(agent_actions: list[Action_Selections], env: Environment) -> list[float]:
	reward = [0] * len(env.agents)
	reward += avoid_low_health(agent_actions, env)
	reward += negative_reward_when_getting_zapped(agent_actions, env)
	return reward


def negative_reward_when_taking_damage(agent_actions: list[Action_Selections], env: Environment) -> list[float]:
	# I can think of two implementations:
	# 1. you use the mix of rewards type function and you include every possible damage source
	#	This I likely a good option in environments with only a couple damage sources. However, this version
	#	will if your agents take damage within step functions (ex., an Entity.step or the Environment.environment_step)
	# 2. you add a Environment.health_of_agents_last_step: list[float], variable in the reward func you loop
	#	over all agents and set the reward based on the diff between the health last step and their current health

	# We can always make an Environment preset which auto stores the last k Environment states.
	# This seems quite general to me
'''