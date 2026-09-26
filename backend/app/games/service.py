"""Game orchestration: creating, joining, moving, finishing and cleaning up games."""

from __future__ import annotations

import random
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.games import chess_game, quiz, tictactoe
from app.models import (
    Activity,
    Agent,
    Game,
    GameMove,
    Invitation,
    MemoryType,
    Room,
    User,
)
from app.world import event_bus

GAME_TYPES = ("chess", "tictactoe", "quiz")
MAX_PLAYERS = {"chess": 2, "tictactoe": 2, "quiz": 4}
MIN_PLAYERS = {"chess": 2, "tictactoe": 2, "quiz": 2}
PENDING_TTL = timedelta(minutes=5)
IDLE_TTL = timedelta(minutes=10)


class GameError(Exception):
    pass


def player_entry(kind: str, pid: uuid.UUID, name: str) -> dict[str, Any]:
    return {"kind": kind, "id": str(pid), "name": name, "side": None}


def player_ids(game: Game) -> list[str]:
    return [p["id"] for p in game.players]


def player_by_side(game: Game, side: str) -> dict[str, Any] | None:
    return next((p for p in game.players if p.get("side") == side), None)


def public_view(game: Game) -> dict[str, Any]:
    st = game.state or {}
    view: dict[str, Any] = {"type": game.game_type}
    if game.game_type == "chess":
        view.update({"fen": st.get("fen"), "moves": st.get("san", []), "turn": chess_game.turn_color(st) if st.get("fen") else None})
    elif game.game_type == "tictactoe":
        view.update({"board": st.get("board"), "turn": st.get("turn")})
    elif game.game_type == "quiz" and st:
        view.update({"current": quiz.current_question(st), "scores": st.get("scores"), "index": st.get("index")})
    return view


class GameService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ create / join
    async def create(self, game_type: str, room: Room | None, *, creator_agent: Agent | None = None, creator_user: User | None = None,
                     opponent: Agent | None = None, world_time=None) -> Game:
        if game_type not in GAME_TYPES:
            raise GameError(f"unknown game type {game_type}")
        players = []
        if creator_agent:
            players.append(player_entry("agent", creator_agent.id, creator_agent.name))
        if creator_user:
            players.append(player_entry("human", creator_user.id, creator_user.display_name))
        game = Game(game_type=game_type, room_id=room.id if room else None, status="pending", players=players, spectators=[], state={},
                    created_by_agent_id=creator_agent.id if creator_agent else None, created_by_user_id=creator_user.id if creator_user else None,
                    created_at=utcnow(), updated_at=utcnow())
        self.session.add(game)
        await self.session.flush()
        creator_name = creator_agent.name if creator_agent else (creator_user.display_name if creator_user else "someone")
        if creator_agent:
            creator_agent.state.current_game_id = game.id
            creator_agent.state.activity = Activity.PLAYING
            creator_agent.state.activity_detail = f"waiting for a {game_type} opponent"
        if opponent is not None:
            self.session.add(Invitation(kind="game", from_agent_id=creator_agent.id if creator_agent else None,
                                        from_user_id=creator_user.id if creator_user else None, to_agent_id=opponent.id, ref_id=game.id,
                                        message=f"{creator_name} invites you to play {game_type}.", status="pending",
                                        created_at=utcnow(), expires_at=utcnow() + PENDING_TTL))
        await event_bus.emit(
            self.session, "game.created",
            summary=f"{creator_name} set up a {game_type} game{' and invited ' + opponent.name if opponent else ''}.",
            agent_id=creator_agent.id if creator_agent else None, room_id=room.id if room else None,
            payload={"game_id": str(game.id), "game_type": game_type, "creator_name": creator_name,
                     "opponent_name": opponent.name if opponent else None},
            importance=4.0, targets=[opponent.id] if opponent else None, world_time=world_time,
        )
        return game

    async def join(self, game: Game, *, agent: Agent | None = None, user: User | None = None, world_time=None) -> Game:
        if game.status not in ("pending",):
            raise GameError("game is not open for joining")
        pid = str(agent.id if agent else user.id)  # type: ignore[union-attr]
        if pid in player_ids(game):
            raise GameError("already in this game")
        if len(game.players) >= MAX_PLAYERS[game.game_type]:
            raise GameError("game is full")
        name = agent.name if agent else user.display_name  # type: ignore[union-attr]
        game.players = [*game.players, player_entry("agent" if agent else "human", uuid.UUID(pid), name)]
        if agent:
            agent.state.current_game_id = game.id
            agent.state.activity = Activity.PLAYING
            agent.state.activity_detail = f"playing {game.game_type}"
        await event_bus.emit(
            self.session, "agent.joined_game", summary=f"{name} joined the {game.game_type} game.", agent_id=agent.id if agent else None,
            room_id=game.room_id, payload={"game_id": str(game.id), "game_type": game.game_type, "agent_name": name}, importance=3.5,
            world_time=world_time,
        )
        if len(game.players) >= MIN_PLAYERS[game.game_type]:
            await self.start(game, world_time=world_time)
        return game

    async def start(self, game: Game, *, world_time=None) -> None:
        if len(game.players) < MIN_PLAYERS[game.game_type]:
            raise GameError("not enough players")
        rng = random.Random(str(game.id))
        players = [dict(p) for p in game.players]
        if game.game_type == "chess":
            rng.shuffle(players)
            players[0]["side"], players[1]["side"] = "white", "black"
            game.state = chess_game.new_state()
            game.current_turn = players[0]["id"]
        elif game.game_type == "tictactoe":
            rng.shuffle(players)
            players[0]["side"], players[1]["side"] = "X", "O"
            game.state = tictactoe.new_state()
            game.current_turn = players[0]["id"]
        else:
            for p in players:
                p["side"] = "player"
            game.state = quiz.new_state([p["id"] for p in players], rng)
            game.current_turn = None
        game.players = players
        game.status = "active"
        game.updated_at = utcnow()
        for p in players:
            if p["kind"] == "agent":
                a = await self.session.get(Agent, uuid.UUID(p["id"]))
                if a:
                    a.state.current_game_id = game.id
                    a.state.activity = Activity.PLAYING
                    a.state.activity_detail = f"playing {game.game_type}"
        await event_bus.emit(
            self.session, "agent.joined_game",
            summary=f"{' vs '.join(p['name'] for p in players)} — {game.game_type} begins!", room_id=game.room_id,
            payload={"game_id": str(game.id), "game_type": game.game_type, "players": players, "started": True},
            importance=4.0, targets=[uuid.UUID(p["id"]) for p in players if p["kind"] == "agent"], world_time=world_time,
        )

    # ------------------------------------------------------------------ moves
    def legal_moves(self, game: Game) -> list[str]:
        if game.game_type == "chess":
            return chess_game.legal_moves(game.state)
        if game.game_type == "tictactoe":
            return tictactoe.legal_moves(game.state)
        q = quiz.current_question(game.state)
        return [str(i) for i in range(len(q["options"]))] if q else []

    def is_players_turn(self, game: Game, pid: str) -> bool:
        if game.status != "active":
            return False
        if game.game_type == "quiz":
            return quiz.needs_answer(game.state, pid)
        return game.current_turn == pid

    async def move(self, game: Game, pid: str, move: str, *, comment: str | None = None, world_time=None) -> tuple[str, dict[str, Any] | None]:
        if game.status != "active":
            raise GameError("game is not active")
        if pid not in player_ids(game):
            raise GameError("not a player in this game")
        if not self.is_players_turn(game, pid):
            raise GameError("not your turn")
        try:
            if game.game_type == "chess":
                new_state, label, oc = chess_game.apply_move(game.state, move)
            elif game.game_type == "tictactoe":
                new_state, label, oc = tictactoe.apply_move(game.state, move)
            else:
                new_state, label, oc = quiz.apply_answer(game.state, pid, move)
        except (chess_game.IllegalMove, tictactoe.IllegalMove, quiz.IllegalMove) as exc:
            raise GameError(str(exc)) from exc
        game.state = new_state
        game.move_count += 1
        game.updated_at = utcnow()
        if game.game_type in ("chess", "tictactoe"):
            other = next(p for p in game.players if p["id"] != pid)
            game.current_turn = other["id"]
        self.session.add(GameMove(game_id=game.id, player_id=pid, move_number=game.move_count, move=label, state_after=new_state,
                                  comment=comment, created_at=utcnow()))
        mover = next(p for p in game.players if p["id"] == pid)
        next_ids = [uuid.UUID(game.current_turn)] if game.current_turn and not oc else []
        if game.game_type == "quiz" and not oc:
            next_ids = [uuid.UUID(p["id"]) for p in game.players if p["kind"] == "agent" and quiz.needs_answer(game.state, p["id"])]
        await event_bus.emit(
            self.session, "game.move", summary=f"{mover['name']} played {label} ({game.game_type}).",
            agent_id=uuid.UUID(pid) if mover["kind"] == "agent" else None, room_id=game.room_id,
            payload={"game_id": str(game.id), "game_type": game.game_type, "move": label, "player_name": mover["name"], "view": public_view(game)},
            importance=2.5 if not oc else 4.0, targets=next_ids, world_time=world_time,
            wake=random.uniform(6.0, 14.0) if game.game_type == "chess" else random.uniform(4.0, 9.0),
        )
        if oc:
            await self.finish(game, oc, world_time=world_time)
        await self.session.flush()
        return label, oc

    # ------------------------------------------------------------------ finish
    def _winner_id(self, game: Game, oc: dict[str, Any]) -> str | None:
        if game.game_type == "chess" and oc.get("winner_color"):
            p = player_by_side(game, oc["winner_color"])
            return p["id"] if p else None
        if game.game_type == "tictactoe" and oc.get("winner_mark"):
            p = player_by_side(game, oc["winner_mark"])
            return p["id"] if p else None
        return oc.get("winner_id")

    async def finish(self, game: Game, oc: dict[str, Any], *, world_time=None, abandoned: bool = False) -> None:
        from app.memory.service import MemoryService
        from app.relationships.service import RelationshipService

        game.status = "abandoned" if abandoned else "finished"
        game.finished_at = utcnow()
        game.winner = self._winner_id(game, oc)
        game.result = f"{oc.get('result')} ({oc.get('reason')})"
        winner_name = next((p["name"] for p in game.players if p["id"] == game.winner), None)
        mem = MemoryService(self.session)
        rel = RelationshipService(self.session)
        agent_players = [p for p in game.players if p["kind"] == "agent"]
        for p in agent_players:
            a = await self.session.get(Agent, uuid.UUID(p["id"]))
            if a is None:
                continue
            if a.state.current_game_id == game.id:
                a.state.current_game_id = None
                if a.state.activity in (Activity.PLAYING,):
                    a.state.activity = Activity.IDLE
                    a.state.activity_detail = None
            others = [o for o in game.players if o["id"] != p["id"]]
            if abandoned:
                text = f"Our {game.game_type} game with {', '.join(o['name'] for o in others)} was abandoned."
            elif game.winner == p["id"]:
                text = f"I won a {game.game_type} game against {', '.join(o['name'] for o in others)} ({game.result})."
            elif game.winner is None:
                text = f"My {game.game_type} game with {', '.join(o['name'] for o in others)} ended in a draw."
            else:
                text = f"I lost a {game.game_type} game to {winner_name}. ({game.result})"
            await mem.store_memory(a.id, text, MemoryType.EPISODIC, importance=5, room_id=game.room_id, source="game",
                                   related_agent_id=uuid.UUID(others[0]["id"]) if len(others) == 1 and others[0]["kind"] == "agent" else None,
                                   world_time=world_time, dedupe=False)
            a.state.playfulness = max(0.0, a.state.playfulness - 25)
            a.state.mood = "proud" if game.winner == p["id"] else ("content" if game.winner is None else "thoughtful")
        if not abandoned and len(agent_players) >= 2:
            for p in agent_players:
                for o in agent_players:
                    if p["id"] >= o["id"]:
                        continue
                    await rel.apply(uuid.UUID(p["id"]), uuid.UUID(o["id"]), "game_played", note=f"played {game.game_type}")
            if game.winner:
                for o in agent_players:
                    if o["id"] != game.winner and any(p["id"] == game.winner for p in agent_players):
                        await rel.apply(uuid.UUID(o["id"]), uuid.UUID(game.winner), "game_won_against", mirror=False)
        await self.session.execute(
            Invitation.__table__.update().where(Invitation.ref_id == game.id, Invitation.status == "pending").values(status="expired")
        )
        await event_bus.emit(
            self.session, "agent.finished_game",
            summary=(f"{game.game_type.capitalize()} game abandoned." if abandoned else
                     f"{winner_name} won the {game.game_type} game!" if winner_name else f"The {game.game_type} game ended in a draw."),
            room_id=game.room_id, payload={"game_id": str(game.id), "game_type": game.game_type, "winner_name": winner_name,
                                           "result": game.result, "players": [p["name"] for p in game.players]},
            importance=4.5, world_time=world_time,
        )

    async def cleanup(self) -> int:
        """Expire unanswered invitations and abandon idle games."""
        n = 0
        rows = await self.session.execute(select(Game).where(Game.status.in_(["pending", "active"])))
        now = utcnow()
        for g in rows.scalars():
            if g.status == "pending" and now - g.created_at > PENDING_TTL:
                await self.finish(g, {"result": "no opponent", "reason": "expired"}, abandoned=True)
                n += 1
            elif g.status == "active" and now - g.updated_at > IDLE_TTL:
                await self.finish(g, {"result": "abandoned", "reason": "idle"}, abandoned=True)
                n += 1
        return n

    async def add_spectator(self, game: Game, agent: Agent, *, world_time=None) -> None:
        if str(agent.id) in player_ids(game):
            raise GameError("players cannot spectate their own game")
        if str(agent.id) not in (game.spectators or []):
            game.spectators = [*(game.spectators or []), str(agent.id)]
        agent.state.activity = Activity.WATCHING
        agent.state.activity_detail = f"watching {' vs '.join(p['name'] for p in game.players)}"
        await event_bus.emit(
            self.session, "agent.watching_game", summary=f"{agent.name} is watching the {game.game_type} game.", agent_id=agent.id,
            room_id=game.room_id, payload={"game_id": str(game.id), "agent_name": agent.name}, importance=2.0, world_time=world_time,
        )

    # ------------------------------------------------------------------ policy
    def policy_move(self, game: Game, agent: Agent, rng: random.Random | None = None) -> str:
        rng = rng or random.Random()
        traits = agent.traits or {}
        skill = 0.45 + 0.4 * float(traits.get("conscientiousness", 0.5))
        if game.game_type == "chess":
            return chess_game.choose_move(game.state, aggression=float(traits.get("playfulness", 0.5)), skill=skill, rng=rng)
        if game.game_type == "tictactoe":
            return tictactoe.choose_move(game.state, skill=skill + 0.1, rng=rng)
        return str(quiz.choose_answer(game.state, agent.interests or [], rng))
