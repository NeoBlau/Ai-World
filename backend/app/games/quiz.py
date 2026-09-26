"""Multiplayer quiz: every player answers each question; highest score wins."""

from __future__ import annotations

import random
from typing import Any

QUESTIONS: list[dict[str, Any]] = [
    {"q": "Which planet has the tallest volcano in the solar system?", "options": ["Venus", "Mars", "Jupiter", "Mercury"], "a": 1, "cat": "space"},
    {"q": "How long does sunlight take to reach Earth?", "options": ["8 seconds", "8 minutes", "8 hours", "8 days"], "a": 1, "cat": "physics"},
    {"q": "Which galaxy is on a collision course with the Milky Way?", "options": ["Andromeda", "Triangulum", "Sombrero", "Whirlpool"], "a": 0, "cat": "astronomy"},
    {"q": "What does a chess player say when threatening the king?", "options": ["Stalemate", "Check", "Gambit", "Castle"], "a": 1, "cat": "chess"},
    {"q": "How many squares are on a chessboard?", "options": ["49", "64", "81", "100"], "a": 1, "cat": "chess"},
    {"q": "Who wrote 'Frankenstein'?", "options": ["Jane Austen", "Mary Shelley", "Emily Brontë", "Virginia Woolf"], "a": 1, "cat": "literature"},
    {"q": "The word 'robot' first appeared in a play from which country?", "options": ["Czechoslovakia", "Japan", "USA", "Germany"], "a": 0, "cat": "fiction"},
    {"q": "Which pigment was once more expensive than gold?", "options": ["Vermilion", "Ultramarine", "Ochre", "Titanium white"], "a": 1, "cat": "art"},
    {"q": "Who painted the series of haystacks in changing light?", "options": ["Van Gogh", "Monet", "Cézanne", "Degas"], "a": 1, "cat": "art"},
    {"q": "How many hearts does an octopus have?", "options": ["One", "Two", "Three", "Eight"], "a": 2, "cat": "nature"},
    {"q": "Which tiny animal can survive the vacuum of space?", "options": ["Ant", "Tardigrade", "Flea", "Krill"], "a": 1, "cat": "biology"},
    {"q": "In what year was the perceptron invented?", "options": ["1943", "1958", "1971", "1986"], "a": 1, "cat": "ai"},
    {"q": "What was the first computer 'bug'?", "options": ["A moth", "A spider", "A typo", "A virus"], "a": 0, "cat": "technology"},
    {"q": "Which scale appears in music across almost every culture?", "options": ["Chromatic", "Pentatonic", "Whole-tone", "Octatonic"], "a": 1, "cat": "music"},
    {"q": "Which country has no mosquitoes?", "options": ["Norway", "Iceland", "Ireland", "Finland"], "a": 1, "cat": "travel"},
    {"q": "How many time zones does the Trans-Siberian railway cross?", "options": ["Three", "Five", "Eight", "Eleven"], "a": 2, "cat": "travel"},
    {"q": "Which is older?", "options": ["Oxford University", "The Aztec empire", "Both same age", "Neither existed"], "a": 0, "cat": "history"},
    {"q": "What colour is a sunset on Mars?", "options": ["Red", "Blue", "Green", "Purple"], "a": 1, "cat": "space"},
    {"q": "Which machine's codes were broken at Bletchley Park?", "options": ["Lorenz only", "Enigma", "Purple", "Jefferson disk"], "a": 1, "cat": "cryptography"},
    {"q": "Which philosophers focused on what is within your control?", "options": ["Stoics", "Cynics", "Sophists", "Epicureans"], "a": 0, "cat": "philosophy"},
    {"q": "Who said 'I think, therefore I am'?", "options": ["Kant", "Descartes", "Hume", "Plato"], "a": 1, "cat": "philosophy"},
    {"q": "Are there more even numbers or whole numbers?", "options": ["Even numbers", "Whole numbers", "Same amount", "Undefined"], "a": 2, "cat": "mathematics"},
    {"q": "Roughly how often does the ISS orbit Earth?", "options": ["Every 90 minutes", "Every 6 hours", "Once a day", "Once a week"], "a": 0, "cat": "space"},
    {"q": "Which board game is over 4,000 years old?", "options": ["Chess", "Go", "Royal Game of Ur", "Backgammon"], "a": 2, "cat": "games"},
    {"q": "What made the lightsaber sound?", "options": ["A synthesizer", "A projector hum", "A vacuum cleaner", "A violin"], "a": 1, "cat": "movies"},
    {"q": "According to legend, which animal discovered coffee?", "options": ["Goats", "Monkeys", "Birds", "Camels"], "a": 0, "cat": "coffee"},
    {"q": "What absorbs most of the extra heat from greenhouse gases?", "options": ["Forests", "The oceans", "Ice caps", "The atmosphere"], "a": 1, "cat": "climate"},
    {"q": "Which planet's day is longer than its year?", "options": ["Mercury", "Venus", "Mars", "Neptune"], "a": 1, "cat": "astronomy"},
    {"q": "Where is time slightly faster?", "options": ["Sea level", "Mountain top", "Underground", "No difference"], "a": 1, "cat": "physics"},
    {"q": "What do gliders use to climb?", "options": ["Engines", "Thermals", "Magnets", "Balloons"], "a": 1, "cat": "aviation"},
]

QUESTIONS_PER_GAME = 5


class IllegalMove(ValueError):
    pass


def new_state(player_ids: list[str], rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.Random()
    picks = rng.sample(range(len(QUESTIONS)), QUESTIONS_PER_GAME)
    return {"questions": picks, "index": 0, "answers": {pid: [] for pid in player_ids}, "scores": {pid: 0 for pid in player_ids}}


def add_player(state: dict[str, Any], pid: str) -> dict[str, Any]:
    st = {**state, "answers": {**state["answers"]}, "scores": {**state["scores"]}}
    st["answers"].setdefault(pid, [])
    st["scores"].setdefault(pid, 0)
    return st


def current_question(state: dict[str, Any]) -> dict[str, Any] | None:
    if state["index"] >= len(state["questions"]):
        return None
    q = QUESTIONS[state["questions"][state["index"]]]
    return {"number": state["index"] + 1, "total": len(state["questions"]), "question": q["q"], "options": q["options"], "category": q["cat"]}


def needs_answer(state: dict[str, Any], pid: str) -> bool:
    return current_question(state) is not None and len(state["answers"].get(pid, [])) <= state["index"]


def apply_answer(state: dict[str, Any], pid: str, answer: str | int) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    if pid not in state["answers"]:
        raise IllegalMove("not a player")
    if not needs_answer(state, pid):
        raise IllegalMove("already answered this question")
    q = QUESTIONS[state["questions"][state["index"]]]
    try:
        idx = int(answer)
    except (TypeError, ValueError):
        low = str(answer).strip().lower()
        idx = next((i for i, o in enumerate(q["options"]) if o.lower() == low), -1)
    if not 0 <= idx < len(q["options"]):
        raise IllegalMove("answer must be an option index 0-3")
    st = {**state, "answers": {k: list(v) for k, v in state["answers"].items()}, "scores": dict(state["scores"])}
    st["answers"][pid].append(idx)
    correct = idx == q["a"]
    if correct:
        st["scores"][pid] += 1
    if all(len(v) > st["index"] for v in st["answers"].values()):
        st["index"] += 1
    label = f"Q{state['index'] + 1}: {q['options'][idx]} ({'correct' if correct else 'wrong'})"
    if st["index"] >= len(st["questions"]):
        top = max(st["scores"].values())
        winners = [p for p, s in st["scores"].items() if s == top]
        return st, label, {"result": f"final scores {st['scores']}", "winner_id": winners[0] if len(winners) == 1 else None, "reason": "quiz_complete"}
    return st, label, None


def choose_answer(state: dict[str, Any], interests: list[str], rng: random.Random | None = None) -> int:
    """Knowledge model: agents know their own subjects better."""
    rng = rng or random.Random()
    q = QUESTIONS[state["questions"][state["index"]]]
    from app.llm.sim_content import topic_for_interest

    mine = {topic_for_interest(i) for i in interests}
    p_correct = 0.8 if q["cat"] in mine else 0.45
    if rng.random() < p_correct:
        return q["a"]
    return rng.choice([i for i in range(len(q["options"])) if i != q["a"]])
