import random

import pytest

from app.games import chess_game, quiz, tictactoe
from app.games.service import GameError, GameService
from tests.conftest import get_agent


def test_chess_legal_and_illegal_moves():
    st = chess_game.new_state()
    assert "e4" in chess_game.legal_moves(st)
    st, san, oc = chess_game.apply_move(st, "e4")
    assert san == "e4" and oc is None and chess_game.turn_color(st) == "black"
    with pytest.raises(chess_game.IllegalMove):
        chess_game.apply_move(st, "e4")  # white pawn move on black's turn
    st, san, _ = chess_game.apply_move(st, "e7e5")  # UCI accepted
    assert san == "e5"


def test_chess_fools_mate_outcome():
    st = chess_game.new_state()
    oc = None
    for mv in ["f3", "e5", "g4", "Qh4#"]:
        st, _, oc = chess_game.apply_move(st, mv)
    assert oc == {"result": "0-1", "winner_color": "black", "reason": "checkmate"}


def test_chess_policy_always_legal_and_finds_mate():
    st = chess_game.new_state()
    for mv in ["f3", "e5", "g4"]:
        st, _, _ = chess_game.apply_move(st, mv)
    assert chess_game.choose_move(st, rng=random.Random(1)) == "Qh4#"
    rng = random.Random(7)
    st = chess_game.new_state()
    for _ in range(40):
        mv = chess_game.choose_move(st, rng=rng)
        assert mv in chess_game.legal_moves(st)
        st, _, oc = chess_game.apply_move(st, mv)
        if oc:
            break


def test_tictactoe_rules_and_perfect_play():
    st = tictactoe.new_state()
    for mv in [0, 3, 1, 4]:
        st, _, oc = tictactoe.apply_move(st, mv)
        assert oc is None
    with pytest.raises(tictactoe.IllegalMove):
        tictactoe.apply_move(st, 4)
    st, _, oc = tictactoe.apply_move(st, 2)
    assert oc["winner_mark"] == "X"
    # two perfect players always draw
    st, oc = tictactoe.new_state(), None
    while oc is None:
        st, _, oc = tictactoe.apply_move(st, tictactoe.choose_move(st, skill=1.0, rng=random.Random(3)))
    assert oc["result"] == "draw"


def test_quiz_scoring():
    st = quiz.new_state(["a", "b"], random.Random(1))
    q = quiz.QUESTIONS[st["questions"][0]]
    st, label, oc = quiz.apply_answer(st, "a", q["a"])
    assert "correct" in label and st["scores"]["a"] == 1 and st["index"] == 0
    with pytest.raises(quiz.IllegalMove):
        quiz.apply_answer(st, "a", 0)
    st, _, _ = quiz.apply_answer(st, "b", (q["a"] + 1) % 4)
    assert st["index"] == 1 and st["scores"]["b"] == 0


async def test_game_service_full_flow(world):
    s = world
    alex, neo = await get_agent(s, "alex"), await get_agent(s, "neo")
    svc = GameService(s)
    game = await svc.create("tictactoe", None, creator_agent=alex, opponent=neo)
    assert game.status == "pending"
    await svc.join(game, agent=neo)
    assert game.status == "active" and game.current_turn in (str(alex.id), str(neo.id))
    other = str(neo.id) if game.current_turn == str(alex.id) else str(alex.id)
    with pytest.raises(GameError):
        await svc.move(game, other, "0")
    oc = None
    while oc is None:
        pid = game.current_turn
        agent = alex if pid == str(alex.id) else neo
        _, oc = await svc.move(game, pid, svc.policy_move(game, agent, random.Random(2)))
    assert game.status == "finished" and alex.state.current_game_id is None
