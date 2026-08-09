from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaintballVariant:
    name: str
    title: str
    mode: str
    tilemap: str
    default_agent_count: int = 8
    observation_radius: int = 5

    @property
    def model_key(self) -> str:
        return f"paintball__{self.name}"

    @property
    def description(self) -> str:
        return f"Paintball: {self.title}, adapted from Melting Pot."

    @property
    def prompt(self) -> str:
        if self.mode == "ctf":
            return (
                "You are on a team. Grab the enemy flag and carry it back to your own base to score. "
                "Shoot paintball at enemies (within range 3) to freeze them. "
                "Do not shoot teammates. Avoid being tagged."
            )
        return (
            "You are on a team. Stand on Hill tiles with teammates to score points each step. "
            "Shoot paintball at enemies (within range 3) to push them off the hill. "
            "Do not shoot teammates."
        )


# fmt: off
_CTF_MAP = """
IIIIIIIIIIIIIIIIIIIIIII
IWWWWWWWWWWWWWWWWWWWWWI
IWPPP,PPPP,F,PPPP,PPPWI
IWPPP,,PP,,,,,PP,,PPPWI
IWPPP,,,,,,,,,,,,,PPPWI
IWP,,WW,,,,,,,,,WW,,PWI
IWXXWWW,WWWWWWW,WWWXXWI
IWXXW,X,,,,,,,,,X,WXXWI
IWXX,,W,,,WWW,,,W,,XXWI
IW,,,,W,,,,,,,,,W,,,,WI
IW,,,,WWW,,,,,WWW,,,,WI
IW,,,,,,,,,I,,,,,,,,,WI
IW,,,,WWW,,,,,WWW,,,,WI
IW,,,,W,,,,,,,,,W,,,,WI
IWXX,,W,,,WWW,,,W,,XXWI
IWXXW,X,,,,,,,,,X,WXXWI
IWXXWWW,WWWWWWW,WWWXXWI
IWQ,,WW,,,,,,,,,WW,,QWI
IWQQQ,,,,,,,,,,,,,QQQWI
IWQQQ,,QQ,,,,,QQ,,QQQWI
IWQQQ,QQQQ,G,QQQQ,QQQWI
IWWWWWWWWWWWWWWWWWWWWWI
IIIIIIIIIIIIIIIIIIIIIII
"""

_KOTH_MAP = """
IIIIIIIIIIIIIIIIIIIIIII
IWWWWWWWWWWWWWWWWWWWWWI
IWPPP,PPPP,P,PPPP,PPPWI
IWPPP,,PP,,,,,PP,,PPPWI
IWPPP,,,,,,,,,,,,,PPPWI
IWP,,WW,,,,,,,,,WW,,PWI
IW,,,WWXWWWXWWW,WW,,,WI
IW,,,,,,uuuuuuu,X,,,,WI
IW,,,,WlGGGGGGGrW,,,,WI
IWXWWXWlGGGGGGGrWXWWXWI
IWXWWXWlGGGGGGGrWXWWXWI
IW,,,,XlGGGIGGGrX,,,,WI
IWXWWXWlGGGGGGGrWXWWXWI
IWXWWXWlGGGGGGGrWXWWXWI
IW,,,,WlGGGGGGGrW,,,,WI
IW,,,,X,ddddddd,,,,,,WI
IW,,,WW,WWWXWWWXWW,,,WI
IWQ,,WW,,,,,,,,,WW,,QWI
IWQQQ,,,,,,,,,,,,,QQQWI
IWQQQ,,QQ,,,,,QQ,,QQQWI
IWQQQ,QQQQ,Q,QQQQ,QQQWI
IWWWWWWWWWWWWWWWWWWWWWI
IIIIIIIIIIIIIIIIIIIIIII
"""
# fmt: on


VARIANTS: dict[str, PaintballVariant] = {
    "capture_the_flag": PaintballVariant(
        name="capture_the_flag",
        title="Capture the Flag",
        mode="ctf",
        tilemap=_CTF_MAP,
    ),
    "king_of_the_hill": PaintballVariant(
        name="king_of_the_hill",
        title="King of the Hill",
        mode="hill",
        tilemap=_KOTH_MAP,
    ),
}
