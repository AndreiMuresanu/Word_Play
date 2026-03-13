# Todos (roughly priority sorted)

- [ ] add actions which can take args as input
	- perhaps this is as simple as converting the action + action selection into a NamedTuple and adding an args field to the action selection?
- [x] currently to add new entities, you need to know what youre doing. E.g., env.step() or the action function needs to add an entity to env.entities. They need to know what they are doing and could potentially mess things up (e.g., think about adding a new agent--we likely want to disallow this). We should think about how and when we want new entities added
- [x] update description text methods and call method in movement system presets file


- [ ] create a random action comp. This should be a preset. I.e., random choice of actions from a list where we are also given a random prob for each action. Default to uniform prob. Can have two options, one randomly selects from possible_actions and one which selects from a predefined set of actions and only considers the possible ones when making its choice
- [x] what to do if the agent has no actions available? Maybe the env creator should never let this happen? E.g., they should always provide the Do_Nothing() action if such a situation can arise, since the only other reasonable default is to have the agent Do_Nothing if no actions are available. Hence, it is better to just have the env creator explicitly think about this. And make the choice.

- [ ] if two agents select: the pick up item action for the same item, only 1 agent will be able to pick up the item. Thus, actions can fail. How do we deal with this? Our env is very sequential, maybe we break the standard RL paradigm of selecting all actions at the same time and simulate the environment change after each action is executed. E.g., agent_1_observe(), agent_1_select_action(), sim_agent_1_action(), agent_2_observe(), agent_2_select_action(), sim_agent_2_action(), ...
	- relatedly, if 2 agents start different chats at the same time
	- *** create a preset conflict resolution component

- [ ] how should entities have the ability to take actions? Or at least re-use that functionality.
	- I think having entities take actions is important since it would be really a great re-use of already created logic. E.g., imagine a cow which wanders around. If it does not use the movement actions, then we (or more likely the user) would need to reimplement the entire movement and collision system. This seems wrong. Same with entites which attack you (they would need to reimplement the entire attack and health system)
	- if we'd like all entities to take actions, a few questions arises:
		1. how many actions should entities be allowed to take? Right now agents are restricted to taking a single action per step. Should general entity-related logic have the same restrictions?
			- we could have action composition (not sure how to nicely do this yet tho) which could avoid this issue
			- having 1 action happen per step may be an acceptable constraint to apply to envs, even if it does restrict some env abilities. This is because it is a standard RL paradigm that only one action is taken per step. I think in RL
		2. when should these actions be executed? I.e., at the same time as agent actions or not?

# TODO: ANDREI: this class is not general enough to support full action flexability, since all actions will have the
#       same targets. E.g., you won't be able to move and attack or heal yourself and attack.
#       NOTE: actually, I think are also two types of action composition: parallel actions and sequential actions. And
#       you can, for example, have a sequence of parallel actions or a parallelization of sequential actions. Parallel
#       actions execute at the same time and sequential actions execute in sequence. However, in our environment we
#       distinctly forbid parallel logic, i.e., only a single action may execute at one time. This means that only
#       sequential actions (action sequences/action chains) exist. For these chains, the question of how to implement
#       their is_valid method arises. E.g., should is_valid. Continuing discussion in notes...
	- E.g., there are two options for implementing is_valid:
		- is_valid only returns the validity of the first action in the chain and the rema
		- is_valid is computed for the entire chain at the start by simulating the environment (this might actually not be possible since the validity also depends on the actions of the previous entities)
	- **** I think entities should have the ability to take actions. I think the non-agent AI system (e.g., NPC AI) provides a strong use-case for allowing entities to take actions. The only question which remains is (1) should entities also abide to the AEC 

- *** you can't do prisoner's dilemma using AEC. It requires parallel env

- [\] idk if AOE attacks are possible with the current system/without observer pattern. Actually i think it's possible by instantiating eg fire entites which deal damage. This might actually be nicer

- [ ] add example of Action_Arg where the int range of pickable berries is based on the number of berries available in a bush. Maybe a better example, would be a Give_Money action where the max amount of money you can give is determined by the max amount of money you have
- [ ] create an example with the Dynamic_Choice_Arg where the choices are determined by nearby objects or objects in your inventory or something

- [ ] create some test systems I'd like to turn into nice presets:
	- [x] inventory system
		- agent state: need to store a list of entities
		- entitiy in inventory:
			- ~~either gets removed from env~~
			- or it stays in the env but its position is overridden to always be the same as the agent holding (this might be better--e.g., imagine ice which melts, or food which spoils. You want it to continue updating normally. For entities which have complex behaviour and interactions, which might get messed up by this, you likely anyways don't want them to be pick-up-able)
	- [x] damage and health system
		- do damage
		- track health
		- destory entity on death
	- [ ] chat system
	- [x] wall system (e.g., objects you can and can't move through)
	- [ ] some kind of complex reward function/system
		- we likely want the reward func to take the env as input
	- [ ] door and key system
	- [ ] cooking system (combine entities and create new entities)
- [ ] create a new env to check whether it is easy to use the presets out-of-the-box

- [ ] imagine a convery belt which moves entities which stand on it. How to implement this? Perhaps, one way is to create a Move_Entity action which is a wrapper for the Move_Up (or any movement action). The is_valid would check that both the validation rules of Move_Entity pass and that the validation rules of self.movement_action(target_entity, target_entity, env) are valid. Thee __call__ method would look something like:
def __call__(actor, target_entity, env):
	self.movement_action(target_entity, target_entity, env)

- [ ] add actions with return values??? need to think about what this actually means. It means we have actions doing something other than mutating the env. E.g., getting a value from a RNG. Other than the get value from RNG, are there any other things it could do? Call an API (e.g., access internet), it could return information about action success if action is stochastic (but maybe this can be done using mutation too), anything else????
- [ ] seeds? how? I think I should likely add some built-in functionality
- [ ] reward func isnt too nice. We likely want it to take the env as input (e.g., imagine reward = dist from something or reward = money or reward = town population)
- [ ] think about what other moments in the execution order I would like entities to run code. E.g., on_destroy, on_instantiation, on_collision (might not need this, since for us entities don't really "collide" the current collision system is just making sure that entites don't go on top of one another), others?

- [ ] remove "ANDREI:" comments (these are the most important todo comments)

- [ ] make sure we comply with PettingZoo or AEC

- [ ] add nice description to new classes (e.g., Component class)
- [ ] use Black to format the whole codebase
- [ ] remove (or preferably edit Explicit_Belief_Agent and Explicit_Belielf_Agent_With_Simple_Conversation) such that they conform with the new system
- [ ] add some nice docs about the philosophy of the library and how it ought to be used
- [ ] remove or resolve all "TODO" notes
- [ ] add some nice observational formatting presets (e.g., str list of of nearby entities, observation preset which posts available actions + the current agent's info + the info of nearby entities)
- [ ] we could add a nice default reset functionality for envs. E.g., add a resettable comp to the entities (or perhaps to the env is better??) which just creates a deepcopy of the initial state and then reverts to that when reset() is called

- [ ] (maybe--need to think exactly how to set this up) make observation show a couple tiles in around you rather than just your current tile (e.g., so you know you can't move onto a tile because there is a wall)

- [ ] an state machine based non-agent entity policy component would be nice

- [ ] createa a test suite. E.g., E2E tests where we create an env with a bunch of systems and then take a bunch of actions and check that the final state is as expected

# Notes

- ~~I think I need to make Entity a non-ABC and simply have it such that all their logic is created by adding components. I.e., they are just containers of components~~
- ~~I think I might remove properties and just have everything be part of the state. Technically anything (properties or state) could be mutated, so, the distinction doesn't seem to make much sense. Perhaps tags could be a property, but even those may potentially be edited~~
- ~~likely want to make actions named tuples rather than ABC since it is lighter weight and I don't think people should be storing data inside actions (it should be stored inside the entity), thus, we should not give users the ability to do so~~

- need to think about how to implement chatting nicely as a preset. Since it augments the experiment flow (but not the env?). So we should think about how to make it plug and play

- ~~I need to think about how I want to execute the game-logic (user-defined logic). I'm thinking that I kinda just want logic to be executed (i.e., things to change) only during step() and when an action is executed. Is this enough? Does it make anything difficult? E.g., other options are to use the observer pattern to define events and have different objects listen for these events. Or to have an event bus~~
- I need to decide how I want to create prefab/prototype chains. I.e., how do I want to store and reuse components
	- maybe I dont need child gameobjects tho. Since it seems like the primary uses are things like: Relative transforms, Grouped movement, Grouped lifetime, Logical ownership, Serialization structure, Editor usability, Update ordering
		- grouped movement might be tricky while allowing abritrary movement systems
	- I could also go the Godot route where each component is a child gameobject
- ~~I think everything should be an Entity and that agent should simply be an Entity with the special policy component which implements a select_action method (or something like that)~~
- The chat/talkable feature can perhaps be implemented as a component which implements a send_message method (or something like that)
- (maybe) I should make it so the movement system is also just a component

        # ANDREI: maybe I dont need to add all the component info to entity.state, since components should not be hoping to see
        # fields in there, instead they should know exactly which comps they want to interact with. The reason i think
        # it is better to do it this way is because (1) I dont want to duplicate info, (2) I want the comp to be able
        # to define custom methods (e.g., create_message) and it is awkward to do it with the dataclass approach since
        # dataclasses ought to be representing data and some of the comps are also representing logic, (3) I think it is
        # not nice to define things in the component class (e.g., self.state) and then delete it later, since this would
        # be weird any annoying for the creator of the comp. Doing it this way also avoid naming conflicts between comps
		# which is really nice

suggestions/ideas:
- ~~maybe we should only have entities and simply tag certain entities with some kind of "can take actions" tag. I think this can simply the component system and I think it is also similar to how unity and godot do things?~~
- ~~I would like the ability to create Entities and Agents without creating a new class~~
- ~~should we make exposed_actions and actions_on_self a list instead of a tuple? Some envs may want to dynamically edit this. They can still do that when it's a tuple by simply defining a new tuple. Not sure how important this is~~

comments/observations:
- to make an env a lot of imports are required
- the typing is very nice. It makes it difficult to make a mistake
- it is hard to know which presets are available
- not obvious that the observation needs to be a dataclass
- I refer to environment.py very often while coding


thoughts about Component.state: dict[str, Any]
        # TODO: maybe state should be a dataclass since it would allow of better typing and dict flexability doesn't
        #       seem needed?
        # TODO: ANDREI: maybe we should just delete state and if you want to store something you just modify the init
        #       and store is as a class attribute. Let's think, you would only add a value to state if you would like it
        #       to be used in either the component's step func or by a custom action defined by the component. Adding a
        #       value to the state is useless in every other case since the other actions would not know how to use it.
        #       In each of the useful scenarios, interacting with a class attribute is much nicer (e.g., type hints, less
        #       code). Are there any inheritance/composition issues associated with switching from state to class attr?
        #       I don't think sooo? Since we don't usually inherit from Component subclass and if we do they will make
        #       sure to handle everything. Thus, it seems like class attr is the better approach...
		# 		It is nice in the Observation class for printing info about the component, but I think this is a trade-off
		#		I'm ok with...


Old ideas:

# ANDREI: use or delete
# # TODO: this is just an initial implementations. There are likely nicer ways to implement this
# class Component_TEST(ABC):

#     # state augment
#     # TODO: I ought to find a nicer way to store this. I don't like this abstract property approach, since it is niche
#     # and it also does not enforce types
#     @property
#     @abstractmethod
#     def state_augment():
#         """This must be a dict with str indicies"""
#         pass

#     # actions augment
#     # TODO: I ought to find a nicer way to store this. I don't like this abstract property approach, since it is niche
#     # and it also does not enforce types
#     @property
#     @abstractmethod
#     def actions_augment():
#         """This must be of type: list[]"""
#         pass

#     # ?? how to handle actions_on_self augment? Can we have a single component class for both entities and agents
#     # or do we need 2?

#     # TODO: decide when this code ought to run (e.g., before or after the entity's step function). Perhaps, there
#     # ought to be a toggle. Or we could have a before_components_step and an after_components_step in the entity
#     # (I think this apprach is less nice since it makes the entity class less straightforward)
#     @abstractmethod
#     def entity_step():
#         """This code run each time the associated entity's step function is run."""
#         pass

#     # TODO: maybe add this? Is it redundant?
#     # @abstractmethod
#     # def env_step():
#     #     """This code runs during each environment step"""
#     #     pass


# ANDREI: use or delete
# @dataclass
# class Component_DC:

#     state: dict[str, Any] = field(default_factory=dict)
#     tags: list[str] = field(default_factory=list)
#     step_func: Callable[[Entity, Environment], None] | None = None
#     exposed_actions: list[Action] = field(default_factory=list)
#     actions_on_self: list[Action] = field(default_factory=list)
#     additional_methods: dict[str, Callable[[Entity, Environment], None]] = field(default_factory=dict)


# ANDREI: use or delete
# # TODO: is this even required??? Or is inheritance enough? What kinda components would need, i.e., what would they be
# #       augmenting? They don't need to aug the render since that can be added as an arg. Maybe the step and reset methods?
# #       A default reset functionality would be nice
# class Env_Component:
#     pass



# *************
# TODO: ANDREI: need to think very deeply about this class. Using pre_actions_step avoid conflict with the Health comp,
#       but maybe some comps need actions to run after their step func. We would also likely need to refactor the
#       Environment.possible_actions method to take as input an entity rather than agent_id. We can have a
#       wrapper/helper which takes agent_id.
#       The biggest thing to think about tho is whether we want Entities to have actions. If so, then there ought to be
#       a standard way for the actions to run. Otherwise, this method is likely not the best. Maybe entities should have
#       actions. Imagine games where we want entities with simple AI. Thus, perhaps non-agent entities should be allowed
#       to add a Take_Action component which they can use to select actions. Or maybe if actions become standard,
#       select_action should just be a standard method of the component class or something else??
#       Maybe the best approach is to create some kinda of component like Non_Agent_Execute_Actions?
# class Apply_Actions_Whenever_Possible(Component):
#     """
#     This component can be attached to non-agent entites to allow them to apply actions anytime it is possible to apply
#     the action. E.g., a spike can apply a damage/attack action to all entities on it.

#     Note that this behaviour (e.g., the spike damange behaviour) can also be directly added to a spike component step
#     function which damages all entities on top of it.
#     """

#     def __init__(self, actions: list[Action]):
#         super().__init__(actions=actions)

#     def pre_actions_step(self, env: Environment) -> None:
#         for action in