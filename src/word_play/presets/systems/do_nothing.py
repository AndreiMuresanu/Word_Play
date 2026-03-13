from src.word_play.core.environment import Action, Target_Is_Self, Entity, Environment


class Do_Nothing(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        pass

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Do nothing."
