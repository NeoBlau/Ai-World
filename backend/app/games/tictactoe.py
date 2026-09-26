"""Tic-tac-toe rules with a minimax policy that makes personality-dependent mistakes."""

from __future__ import annotations

import random
from functools import lru_cache
from typing import Any

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


class IllegalMove(ValueError):
    pass


def new_state() -> dict[str, Any]:
    return {"board": [""] * 9, "turn": "X", "moves": []}


def winner(board: list[str]) -> str | None:
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def legal_moves(state: dict[str, Any]) -> list[str]:
    if winner(state["board"]):
        return []
    return [str(i) for i, v in enumerate(state["board"]) if not v]


def apply_move(state: dict[str, Any], move: str | int) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    try:
        idx = int(str(move).strip())
    except ValueError as exc:
        raise IllegalMove(f"cell must be 0-8, got {move!r}") from exc
    board = list(state["board"])
    if not 0 <= idx <= 8 or board[idx]:
        raise IllegalMove(f"cell {idx} is not free")
    if winner(board):
        raise IllegalMove("game already over")
    mark = state["turn"]
    board[idx] = mark
    new = {"board": board, "turn": "O" if mark == "X" else "X", "moves": [*state.get("moves", []), idx]}
    w = winner(board)
    if w:
        return new, str(idx), {"result": f"{w} wins", "winner_mark": w, "reason": "three_in_a_row"}
    if all(board):
        return new, str(idx), {"result": "draw", "winner_mark": None, "reason": "board_full"}
    return new, str(idx), None


@lru_cache(maxsize=None)
def _minimax(board: tuple[str, ...], player: str, me: str) -> int:
    w = winner(list(board))
    if w:
        return 1 if w == me else -1
    if all(board):
        return 0
    scores = []
    for i, v in enumerate(board):
        if not v:
            nb = list(board)
            nb[i] = player
            scores.append(_minimax(tuple(nb), "O" if player == "X" else "X", me))
    return max(scores) if player == me else min(scores)


def choose_move(state: dict[str, Any], *, skill: float = 0.7, rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    free = legal_moves(state)
    if not free:
        raise IllegalMove("no moves")
    if rng.random() > skill:
        return rng.choice(free)
    me = state["turn"]
    best = max(free, key=lambda i: (_minimax(tuple(_place(state["board"], int(i), me)), "O" if me == "X" else "X", me), rng.random()))
    return best


def _place(board: list[str], i: int, mark: str) -> list[str]:
    nb = list(board)
    nb[i] = mark
    return nb
