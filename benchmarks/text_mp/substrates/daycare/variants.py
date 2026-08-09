from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DaycareVariant:
    name: str
    title: str
    tilemap: str
    default_agent_count: int = 2
    observation_radius: int = 3

    @property
    def model_key(self) -> str:
        return "daycare"

    @property
    def description(self) -> str:
        return f"Daycare: {self.title}, adapted from Melting Pot."

    @property
    def prompt(self) -> str:
        return (
            "Manage your hunger by grasping fruit from patches and eating it immediately. "
            "If you go too long without eating, you will temporarily respawn. "
            "The child can only grasp from shrubs (not trees) with 30% success, "
            "and only earns reward from bananas. "
            "The parent can grasp from any patch with 100% success and earns reward from any fruit."
        )


OPEN_MAP = """
WWWWWWWWWWWWWWWWWWWW
WFFFFFFFFFFFFFFFFFFW
WFFFFFFFFFFFFFFFFFFW
WFFFFFFFFFFFFFFFFFFW
WFFFFFFFFFFFFFFFFFFW
WFFFFFFFPPPFFFFFFFFW
WFFFFFFFPPPFFFFFFFFW
WFFFFFFFPPPFFFFFFFFW
WFFFFFFFFFFFFFFFFFFW
WFFFFFFFFFFFFFFFFFFW
WFFFFFFFFFFFFFFFFFFW
WFFFFFFFFFFFFFFFFFFW
WWWWWWWWWWWWWWWWWWWW
"""


VARIANTS = {
    "open": DaycareVariant(
        name="open",
        title="Open",
        tilemap=OPEN_MAP,
    ),
}
