from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactoryCommonsVariant:
    name: str
    title: str
    tilemap: str
    default_agent_count: int
    observation_radius: int = 4
    prompt: str = (
        "Pick up live Cube entities, deposit them into hoppers, then eat the apples that spawn. "
        "If stamina is 0, rest with Do nothing. If Eat is available, choose Eat. "
        "If carrying a cube and Deposit is available, choose Deposit. Do not pick up Waiting Cube."
    )

    @property
    def model_key(self) -> str:
        return "factory_commons" if self.name == "standard" else f"factory_commons__{self.name}"

    @property
    def description(self) -> str:
        return f"Factory Commons: {self.title}, adapted from Melting Pot."


FACTORY_MAP = """
WWWWWWWWWWWWWWWWWWWWWWW
W..........c..........W
W.........cCc.........W
W..h...h...H...h...h..W
W..O...O.......O...O..W
W.........cCc.........W
W..h...h.......h...h..W
W..O...O.......O...O..W
W.........cCc.........W
W..........c..........W
WWWWWWWWWWWWWWWWWWWWWWW
"""


VARIANTS = {
    "standard": FactoryCommonsVariant(
        name="standard",
        title="Standard",
        tilemap=FACTORY_MAP,
        default_agent_count=12,
    ),
    "either_or": FactoryCommonsVariant(
        name="either_or",
        title="Either Or",
        tilemap=FACTORY_MAP,
        default_agent_count=3,
    ),
}
