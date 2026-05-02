from __future__ import annotations

import itertools


def expand_symmetric_payoff_matrix(
    payoff_matrix_row: list,
    num_players: int,
) -> list:
    """
    Build a full N-player payoff matrix from a single player's payoff row.

    For symmetric games, users only need to provide what one player earns as a
    function of the joint action profile.  This function generates the full
    matrix by applying the symmetry assumption: each player earns what player 1
    would earn if they had played that player's action.

    Parameters
    ----------
    payoff_matrix_row:
        A nested list of depth (num_players - 1) where each leaf is a single
        float — what player 1 earns given the joint action profile.
        Shape: [num_actions] * (num_players - 1), with floats at the leaves.

        Example (2-player, 2 actions — Prisoner's Dilemma):
            [[3, 0],   # player 1 plays C: gets 3 vs C, gets 0 vs D
             [5, 1]]   # player 1 plays D: gets 5 vs C, gets 1 vs D

        Example (3-player, 2 actions):
            [[[4, 2], [2, 0]],   # player 1 plays A
             [[2, 0], [0, 1]]]   # player 1 plays B

    num_players:
        Number of players. Must be >= 2.

    Returns
    -------
    A nested list of depth num_players where each leaf is a tuple of
    num_players floats — one reward per player.

    Raises
    ------
    ValueError
        If the input matrix is not square or has the wrong depth.

    Example
    -------
    >>> expand_symmetric_payoff_matrix([[3, 0], [5, 1]], num_players=2)
    [[(3.0, 3.0), (0.0, 5.0)],
     [(5.0, 0.0), (1.0, 1.0)]]
    """
    if num_players < 2:
        raise ValueError("num_players must be at least 2.")

    num_actions = _infer_num_actions(payoff_matrix_row, num_players)
    _validate_shape(payoff_matrix_row, num_actions, num_players - 1)

    def _lookup(row: list, indices: tuple[int, ...]) -> float:
        """Follow a sequence of indices into the nested row list."""
        result = row
        for idx in indices:
            result = result[idx]
        return float(result)

    # Build the full matrix by iterating over all joint action profiles.
    # For each profile (a0, a1, ..., a_{n-1}), player i earns what player 0
    # would earn if player 0 had played a_i and everyone else kept their action.
    def _build(depth: int, prefix: tuple[int, ...]) -> list | tuple:
        if depth == num_players:
            # prefix is a complete joint action profile (a0, a1, ..., a_{n-1})
            payoffs = []
            for player_idx in range(num_players):
                # Player player_idx earns what player 0 would earn if player 0
                # played a_{player_idx} and the rest played in definition order,
                # excluding player_idx's position.
                player_perspective = (prefix[player_idx],) + tuple(
                    prefix[j] for j in range(num_players) if j != player_idx
                )
                payoffs.append(_lookup(payoff_matrix_row, player_perspective))
            return tuple(payoffs)

        return [_build(depth + 1, prefix + (action_idx,)) for action_idx in range(num_actions)]

    return _build(0, ())


def _infer_num_actions(payoff_matrix_row: list, num_players: int) -> int:
    """Walk to the first leaf to infer num_actions from the shape."""
    node = payoff_matrix_row
    for _ in range(num_players - 1):
        if not isinstance(node, (list, tuple)) or len(node) == 0:
            raise ValueError(
                "payoff_matrix_row is shallower than expected for the given num_players."
            )
        node = node[0]
    # node is now a leaf — the number of top-level entries is num_actions
    return len(payoff_matrix_row)


def _validate_shape(node: list, num_actions: int, remaining_depth: int) -> None:
    """Recursively check that every level has exactly num_actions entries."""
    if not isinstance(node, (list, tuple)):
        raise ValueError(
            f"Expected a list at this level but got {type(node).__name__}."
        )
    if len(node) != num_actions:
        raise ValueError(
            f"Expected {num_actions} entries at this level but got {len(node)}."
        )
    if remaining_depth > 0:
        for child in node:
            _validate_shape(child, num_actions, remaining_depth - 1)
    else:
        # At the leaf level, entries must be numeric
        for leaf in node:
            if not isinstance(leaf, (int, float)):
                raise ValueError(
                    f"Leaf values must be numeric (int or float), got {type(leaf).__name__}."
                )
