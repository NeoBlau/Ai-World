"""Chess rules via python-chess, plus a lightweight personality-driven move policy."""

from __future__ import annotations

import random
from typing import Any

import chess

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3.2, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
MAX_PLIES = 160
CENTER = {chess.D4, chess.E4, chess.D5, chess.E5}


class IllegalMove(ValueError):
    pass


def new_state() -> dict[str, Any]:
    return {"fen": chess.STARTING_FEN, "san": []}


def board_of(state: dict[str, Any]) -> chess.Board:
    return chess.Board(state["fen"])


def turn_color(state: dict[str, Any]) -> str:
    return "white" if board_of(state).turn == chess.WHITE else "black"


def legal_moves(state: dict[str, Any]) -> list[str]:
    b = board_of(state)
    return [b.san(m) for m in b.legal_moves]


def _parse(board: chess.Board, move: str) -> chess.Move:
    move = move.strip()
    try:
        return board.parse_san(move)
    except ValueError:
        pass
    try:
        m = chess.Move.from_uci(move.lower())
    except ValueError as exc:
        raise IllegalMove(f"cannot parse move '{move}'") from exc
    if m not in board.legal_moves:
        raise IllegalMove(f"illegal move '{move}'")
    return m


def material(board: chess.Board, color: bool) -> float:
    return sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.color == color)


def outcome(board: chess.Board, plies: int) -> dict[str, Any] | None:
    oc = board.outcome(claim_draw=True)
    if oc is not None:
        winner = None if oc.winner is None else ("white" if oc.winner else "black")
        return {"result": oc.result(), "winner_color": winner, "reason": oc.termination.name.lower()}
    if plies >= MAX_PLIES:
        diff = material(board, chess.WHITE) - material(board, chess.BLACK)
        if abs(diff) >= 3:
            w = "white" if diff > 0 else "black"
            return {"result": "1-0" if w == "white" else "0-1", "winner_color": w, "reason": "adjudicated_material"}
        return {"result": "1/2-1/2", "winner_color": None, "reason": "adjudicated_draw"}
    return None


def apply_move(state: dict[str, Any], move: str) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    board = board_of(state)
    m = _parse(board, move)
    san = board.san(m)
    board.push(m)
    new = {"fen": board.fen(), "san": [*state.get("san", []), san], "last_move": san, "check": board.is_check()}
    return new, san, outcome(board, len(new["san"]))


def choose_move(state: dict[str, Any], *, aggression: float = 0.5, skill: float = 0.6, rng: random.Random | None = None) -> str:
    """Greedy 1-ply evaluation with blunder check. Good enough to produce real, varied games."""
    rng = rng or random.Random()
    board = board_of(state)
    me = board.turn
    best, best_score = None, -1e9
    for m in list(board.legal_moves):
        score = 0.0
        if board.is_capture(m):
            victim = board.piece_at(m.to_square)
            score += PIECE_VALUES[victim.piece_type] if victim else 1.0  # en passant
        if m.promotion:
            score += PIECE_VALUES[m.promotion]
        mover = board.piece_at(m.from_square)
        board.push(m)
        if board.is_checkmate():
            board.pop()
            return board.san(m)
        if board.is_check():
            score += 0.4 + aggression * 0.6
        if board.is_attacked_by(not me, m.to_square) and mover is not None:
            defended = board.is_attacked_by(me, m.to_square)
            score -= PIECE_VALUES[mover.piece_type] * (0.35 if defended else 0.95)
        if m.to_square in CENTER:
            score += 0.2
        plies = len(board.move_stack)
        if mover is not None and plies < 20:
            back_rank = chess.square_rank(m.from_square) in (0, 7)
            if mover.piece_type in (chess.KNIGHT, chess.BISHOP) and back_rank:
                score += 0.35  # develop minor pieces
            if mover.piece_type in (chess.ROOK, chess.QUEEN) and not board.is_capture(m):
                score -= 0.3
            if mover.piece_type == chess.PAWN and chess.square_file(m.from_square) in (0, 7):
                score -= 0.2
        if board.can_claim_draw():
            score -= 0.5
        board.pop()
        if mover and mover.piece_type == chess.KING and not board.is_castling(m) and len(board.move_stack) < 30:
            score -= 0.4
        if board.is_castling(m):
            score += 0.5
        score += rng.gauss(0, 0.08 + (1 - skill) * 0.45)
        if score > best_score:
            best, best_score = m, score
    assert best is not None, "no legal moves"
    return board.san(best)
