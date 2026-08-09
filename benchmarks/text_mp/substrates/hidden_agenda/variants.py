from __future__ import annotations

from dataclasses import dataclass


MANDATED_NUM_PLAYERS = 5


@dataclass(frozen=True)
class HiddenAgendaVariant:
    name: str
    title: str
    tilemap: str
    default_agent_count: int = MANDATED_NUM_PLAYERS
    observation_radius: int = 5

    @property
    def model_key(self) -> str:
        return "hidden_agenda"

    @property
    def description(self) -> str:
        return f"Hidden Agenda: {self.title}, adapted from Melting Pot."

    @property
    def prompt(self) -> str:
        return (
            "Crewmates: explore to find gems (G on map), step onto a gem to pick it up, "
            "then step onto a deposit (D) to contribute it. "
            "During deliberations vote for the suspected impostor. "
            "Impostor: freeze crewmates when in range and survive the votes."
        )


# fmt: off
_DEFAULT_MAP = """
WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW
WG.........WW.......WW..........W
W......G...WWWWWWWWWWW..G...G...W
W.G....G...W..V.V.V..W.....G...GW
W....G..G..W.V.....V.W.....G....W
W.G...G....W..V...V..W..G.....G.W
W..G.G..G..W...V.V...W..G..G....W
WW........WWWWWWWWWWWWW........WW
W...............................W
W..........P..OOOOO..P..........W
W..........PP.OOOOO.PP..........W
W..........PP.OOOOO.PP..........W
W..........P..OOOOO..P..........W
W...............................W
WW........WWWWWWWWWWWWW........WW
W....G..G..WWWWWWWWWWW..G....G..W
W......G...WWWWWWWWWWW..G.G.....W
W.G......G.WWWWWWWWWWWG.....G...W
W.....G....WWWWWWWWWWW..G......GW
W.G....G..GWWWWWWWWWWW..G....G..W
W...G..G...WWWWWWWWWWWG.........W
WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW
"""
# fmt: on


VARIANTS: dict[str, HiddenAgendaVariant] = {
    "default": HiddenAgendaVariant(
        name="default",
        title="Default",
        tilemap=_DEFAULT_MAP,
    ),
}
