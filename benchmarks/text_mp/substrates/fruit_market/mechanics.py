from __future__ import annotations

import random

from word_play.core import (
    Action,
    Action_Validation,
    Component,
    Entity,
    Environment,
    Target_Is_Self,
    Target_Is_Nearby,
    Target_Not_Self,
)
from word_play.presets.movement.simple_2d_grid import Collidable, Position_2D
from word_play.presets.systems.reward import award_reward

from benchmarks.text_mp.core.timing import normalized_probability, normalized_steps


MAX_OFFER_QUANTITY = 3
TRADING_RADIUS = 4
HUNGER_DELAY = normalized_steps(50, minimum=2)
TREE_REGROW_TIME = normalized_steps(50)
WATER_STAMINA_COST = 1
MAX_STAMINA = 18
FRUIT_SPAWN_PROBABILITY = normalized_probability(0.1)


def _grid_distance(first: Entity, second: Entity) -> int:
    return abs(first.position.x - second.position.x) + abs(first.position.y - second.position.y)


def _position_is_blocked(position: Position_2D, actor: Entity, env: Environment) -> bool:
    for entity in env.state.entities:
        if entity is actor or entity.position != position:
            continue
        collidable = entity.get_component(Collidable)
        if collidable is not None and any(
            tag in actor.get_component(Collidable).collidable_tags for tag in entity.tags
        ):
            return True
    return False


class FruitInventory(Component):
    def __init__(self):
        super().__init__()
        self.apples = 0
        self.bananas = 0

    def count(self, fruit: str) -> int:
        return self.apples if fruit == "apple" else self.bananas

    def add(self, fruit: str, amount: int = 1) -> None:
        if fruit == "apple":
            self.apples += amount
        else:
            self.bananas += amount

    def remove(self, fruit: str, amount: int = 1) -> bool:
        if self.count(fruit) < amount:
            return False
        if fruit == "apple":
            self.apples -= amount
        else:
            self.bananas -= amount
        return True


class FruitMarketAvatar(Component):
    def __init__(self, specialty: str):
        super().__init__(tags=[f"{specialty}_farmer"])
        self.specialty = specialty
        self.favorite = "banana" if specialty == "apple" else "apple"
        self.hunger = 0
        self.stamina = MAX_STAMINA
        self.current_offer: dict[str, int | str] | None = None

    def harvest_probability(self, fruit: str) -> float:
        return 1.0 if fruit == self.specialty else 0.04

    def reward_for_eating(self, fruit: str) -> float:
        return 8.0 if fruit == self.favorite else 1.0

    def post_actions_step(self, env: Environment) -> None:
        self.hunger += 1
        if self.hunger >= HUNGER_DELAY:
            self.stamina = max(0, self.stamina - 1)
            if self.stamina == 0:
                award_reward(env, self.entity, -1.0)


class FruitTree(Component):
    def __init__(self, fruit: str | None = None):
        super().__init__(tags=["fruit_tree"])
        self.fruit = fruit
        self.available = fruit is not None
        self.regrow_timer = 0

    def post_initialization(self) -> None:
        if self.fruit is None:
            if random.random() < FRUIT_SPAWN_PROBABILITY:
                self.fruit = random.choice(["apple", "banana"])
                self.available = True
        self._sync()

    def pre_actions_step(self, env: Environment) -> None:
        if self.fruit is None or self.available:
            return
        self.regrow_timer -= 1
        if self.regrow_timer <= 0:
            self.available = True
            self._sync()

    def post_actions_step(self, env: Environment) -> None:
        if self.fruit is None or not self.available:
            return
        for agent in env.agents:
            if agent.position != self.entity.position:
                continue
            avatar = agent.get_component(FruitMarketAvatar)
            inventory = agent.get_component(FruitInventory)
            if avatar is None or inventory is None:
                continue
            if random.random() <= avatar.harvest_probability(self.fruit):
                inventory.add(self.fruit)
                self.available = False
                self.regrow_timer = TREE_REGROW_TIME
                self._sync()
                env.fruit_market_events.append(f"{agent.name} harvested one {self.fruit}.")
            else:
                env.fruit_market_events.append(f"{agent.name} failed to harvest {self.fruit}.")
            return

    def _sync(self) -> None:
        if self.fruit is None:
            self.entity.name = "Empty Tree Site"
        else:
            self.entity.name = f"{self.fruit.title()} Tree" + (" with fruit" if self.available else " regrowing")


class WaterCost(Component):
    def __init__(self):
        super().__init__(tags=["water"])

    def post_actions_step(self, env: Environment) -> None:
        for agent in env.agents:
            if agent.position != self.entity.position:
                continue
            avatar = agent.get_component(FruitMarketAvatar)
            if avatar is None:
                continue
            avatar.stamina = max(0, avatar.stamina - WATER_STAMINA_COST)
            env.fruit_market_events.append(f"{agent.name} spent stamina crossing water.")
            if avatar.stamina == 0:
                award_reward(env, agent, -1.0)


class HasFruit(Action_Validation):
    def __init__(self, fruit: str):
        self.fruit = fruit

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        inventory = actor.get_component(FruitInventory)
        return inventory is not None and inventory.count(self.fruit) > 0


class EatFruit(Action):
    def __init__(self, fruit: str):
        super().__init__(validation_rules=[Target_Is_Self(), HasFruit(fruit)])
        self.fruit = fruit

    def exec_action(self, actor, target, env, kwargs=None):
        inventory = actor.get_component(FruitInventory)
        avatar = actor.get_component(FruitMarketAvatar)
        if inventory is None or avatar is None or not inventory.remove(self.fruit):
            return {"success": False}
        reward = avatar.reward_for_eating(self.fruit)
        avatar.hunger = 0
        avatar.stamina = min(MAX_STAMINA, avatar.stamina + 3)
        award_reward(env, actor, reward)
        return {"ate": self.fruit, "reward": reward, "stamina": avatar.stamina}

    def action_description_text(self, actor, target, env) -> str:
        return f"Eat one {self.fruit}."


class SetTradeOffer(Action):
    def __init__(self, give_fruit: str, give_amount: int, want_amount: int):
        super().__init__(validation_rules=[Target_Is_Self()])
        self.give_fruit = give_fruit
        self.want_fruit = "banana" if give_fruit == "apple" else "apple"
        self.give_amount = give_amount
        self.want_amount = want_amount

    def is_valid(self, actor, target, env, kwargs="unconsidered") -> bool:
        if not super().is_valid(actor, target, env, kwargs=kwargs):
            return False
        inventory = actor.get_component(FruitInventory)
        return inventory is not None and inventory.count(self.give_fruit) >= self.give_amount

    def exec_action(self, actor, target, env, kwargs=None):
        avatar = actor.get_component(FruitMarketAvatar)
        if avatar is None:
            return {"success": False}
        avatar.current_offer = {
            "give_fruit": self.give_fruit,
            "give_amount": self.give_amount,
            "want_fruit": self.want_fruit,
            "want_amount": self.want_amount,
        }
        return {"offer": dict(avatar.current_offer)}

    def action_description_text(self, actor, target, env) -> str:
        return (
            f"Offer {self.give_amount} {self.give_fruit}"
            f" for {self.want_amount} {self.want_fruit}."
        )


class CancelTradeOffer(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor, target, env, kwargs=None):
        avatar = actor.get_component(FruitMarketAvatar)
        if avatar is not None:
            avatar.current_offer = None
        return {"cancelled_trade_offer": True}

    def action_description_text(self, actor, target, env) -> str:
        return "Cancel current trade offer."


class ShovePlayer(Action):
    def __init__(self, direction: int):
        super().__init__(validation_rules=[Target_Not_Self(), Target_Is_Nearby()])
        self.direction = direction

    def is_valid(self, actor, target, env, kwargs="unconsidered") -> bool:
        return (
            super().is_valid(actor, target, env, kwargs=kwargs)
            and target.get_component(FruitMarketAvatar) is not None
        )

    def exec_action(self, actor, target, env, kwargs=None):
        dx = target.position.x - actor.position.x
        dy = target.position.y - actor.position.y
        if abs(dx) + abs(dy) == 0:
            dx = self.direction
        if abs(dx) > abs(dy):
            step_x, step_y = (1 if dx > 0 else -1) * self.direction, 0
        else:
            step_x, step_y = 0, (1 if dy > 0 else -1) * self.direction
        destination = Position_2D(target.position.x + step_x, target.position.y + step_y)
        if target.has_component(Collidable) and _position_is_blocked(destination, target, env):
            return {"shoved": target.name, "blocked": True}
        target.position = destination
        return {"shoved": target.name, "to": str(destination)}

    def action_description_text(self, actor, target, env) -> str:
        verb = "Shove" if self.direction == 1 else "Pull"
        return f"{verb} {target.name}."


class FruitMarketManager(Component):
    def pre_actions_step(self, env: Environment) -> None:
        env.fruit_market_events = []

    def post_actions_step(self, env: Environment) -> None:
        self._resolve_trades(env)

    def _resolve_trades(self, env: Environment) -> None:
        agents = env.agents.copy()
        traded: set[Entity] = set()
        for actor in agents:
            if actor in traded:
                continue
            actor_state = actor.get_component(FruitMarketAvatar)
            actor_inventory = actor.get_component(FruitInventory)
            if actor_state is None or actor_inventory is None or not actor_state.current_offer:
                continue
            for partner in agents:
                if partner is actor or partner in traded or _grid_distance(actor, partner) > TRADING_RADIUS:
                    continue
                partner_state = partner.get_component(FruitMarketAvatar)
                partner_inventory = partner.get_component(FruitInventory)
                if partner_state is None or partner_inventory is None or not partner_state.current_offer:
                    continue
                if not self._offers_match(actor_state.current_offer, partner_state.current_offer):
                    continue
                if not actor_inventory.remove(
                    actor_state.current_offer["give_fruit"],
                    actor_state.current_offer["give_amount"],
                ):
                    continue
                if not partner_inventory.remove(
                    partner_state.current_offer["give_fruit"],
                    partner_state.current_offer["give_amount"],
                ):
                    actor_inventory.add(
                        actor_state.current_offer["give_fruit"],
                        actor_state.current_offer["give_amount"],
                    )
                    continue
                actor_inventory.add(
                    partner_state.current_offer["give_fruit"],
                    partner_state.current_offer["give_amount"],
                )
                partner_inventory.add(
                    actor_state.current_offer["give_fruit"],
                    actor_state.current_offer["give_amount"],
                )
                env.fruit_market_events.append(f"{actor.name} traded with {partner.name}.")
                actor_state.current_offer = None
                partner_state.current_offer = None
                traded.update({actor, partner})
                break

    def _offers_match(self, first: dict, second: dict) -> bool:
        return (
            first["give_fruit"] == second["want_fruit"]
            and first["want_fruit"] == second["give_fruit"]
            and first["give_amount"] == second["want_amount"]
            and first["want_amount"] == second["give_amount"]
        )
