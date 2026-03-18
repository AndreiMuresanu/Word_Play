from __future__ import annotations

import copy


class Simple_Env_Reset_Mixin:
    def post_init(self):
        self.initial_state = copy.deepcopy(self.state)

    def _reset(self, seed=None) -> None:
        # if "initial_state" doesn't exist, _reset() is being called during __init__ and nothing needs to be done
        if hasattr(self, "initial_state"):
            self.state = copy.deepcopy(self.initial_state)
