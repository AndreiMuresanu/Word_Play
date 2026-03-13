from word_play.environment import Action, Target_Is_Self, Entity, Environment


class Do_Nothing(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        pass

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Do nothing."


# # TODO: this is just a temp example
# def pick_berry(self, actor, world_state):
# 	self.properties.berry_count -= 1
# 	actor.properties.berry_count += 1

# def pick_up_item(self, actor, world_state):
# 	actor.inventory.append(self)

# def unlock(self, actor, world_state):
# 	if self.required_key in actor.inventory:
# 		self.locked = False

# def sleep(target_entity, env):
# 	target_entity.rest_amount += 3
