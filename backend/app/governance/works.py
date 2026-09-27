"""Things residents add to the world themselves: books, items and invented games.

All of it is data. A game's rules are text the players follow and referee
themselves; the world only keeps the table (who plays, the moves, the result).
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time import utcnow
from app.models import Agent, Book, CustomGame, CustomMatch, Item, Room
from app.security.sanitizer import clean_line, clean_text
from app.world import event_bus

MATCH_LOG_MAX = 200


class WorksError(Exception):
    pass


def _limit(normal: int, research: int) -> int:
    return research if get_settings().research_mode else normal


async def _count(session: AsyncSession, model, *where) -> int:
    return (await session.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


class WorksService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ books
    async def write_book(self, agent: Agent, title: str, content: str, topics: list[str], *, world_time=None) -> Book:
        title, content = clean_line(title, 200), clean_text(content, 20000)
        if len(title) < 2 or len(content) < 40:
            raise WorksError("a book needs a title and at least a few sentences")
        if await _count(self.session, Book, Book.author_agent_id == agent.id) >= _limit(10, 50):
            raise WorksError("you have written the maximum number of books")
        if (await self.session.execute(select(Book.id).where(func.lower(Book.title) == title.lower()))).first():
            raise WorksError("a book with this title is already in the library")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", content) if len(p.strip()) > 20]
        passages = [p[:600] for p in paragraphs][:40] or [content[:600]]
        book = Book(title=title, author=agent.name, author_agent_id=agent.id, topics=[clean_line(t, 30).lower() for t in topics[:6] if t],
                    summary=content[:400], passages=passages, times_read=0, created_at=utcnow())
        self.session.add(book)
        await self.session.flush()
        await event_bus.emit(self.session, "agent.wrote_book", summary=f"{agent.name} wrote a book: «{title}». It is in the library now.",
                             agent_id=agent.id, payload={"agent_name": agent.name, "book_id": str(book.id), "title": title,
                                                         "summary": book.summary}, importance=5, scope="global", world_time=world_time)
        return book

    # ------------------------------------------------------------------ items
    async def create_item(self, agent: Agent, name: str, description: str, *, room: Room | None = None, world_time=None) -> Item:
        name, description = clean_line(name, 80), clean_text(description, 800)
        if len(name) < 2 or len(description) < 3:
            raise WorksError("an item needs a name and a description")
        if await _count(self.session, Item, Item.owner_agent_id == agent.id) >= _limit(12, 60):
            raise WorksError("you are carrying too many things — give some away first")
        item = Item(name=name, description=description, creator_agent_id=agent.id, owner_agent_id=agent.id,
                    history=[{"event": "made", "by": agent.name, "at": utcnow().isoformat()}], created_at=utcnow())
        self.session.add(item)
        await self.session.flush()
        await event_bus.emit(self.session, "agent.made_item", summary=f"{agent.name} made {name}: {description[:200]}", agent_id=agent.id,
                             room_id=room.id if room else None, payload={"agent_name": agent.name, "item_id": str(item.id), "name": name,
                                                                          "description": description}, importance=3.5, world_time=world_time)
        return item

    async def find_item(self, owner: Agent, ref: str | None) -> Item | None:
        ref = str(ref or "").strip()
        if not ref:
            return None
        try:
            item = await self.session.get(Item, uuid.UUID(ref))
            return item if item and item.owner_agent_id == owner.id else None
        except ValueError:
            pass
        rows = await self.session.execute(select(Item).where(Item.owner_agent_id == owner.id))
        items = list(rows.scalars())
        return next((i for i in items if i.name.lower() == ref.lower()), None) or next(
            (i for i in items if str(i.id).startswith(ref.lower()) or ref.lower() in i.name.lower()), None)

    async def give_item(self, giver: Agent, item: Item, receiver: Agent, note: str = "", *, room: Room | None = None, world_time=None) -> Item:
        if item.owner_agent_id != giver.id:
            raise WorksError("that is not yours")
        item.owner_agent_id = receiver.id
        item.history = [*(item.history or []), {"event": "given", "by": giver.name, "to": receiver.name, "note": note[:200],
                                                "at": utcnow().isoformat()}][-30:]
        await event_bus.emit(self.session, "agent.gave_item", summary=f"{giver.name} gave {item.name} to {receiver.name}."
                             + (f" «{note[:150]}»" if note else ""), agent_id=giver.id, room_id=room.id if room else None,
                             payload={"agent_name": giver.name, "item": item.name, "to": receiver.name, "note": note},
                             importance=4, targets=[receiver.id], world_time=world_time)
        return item

    async def items_of(self, agent_id: uuid.UUID, limit: int = 12) -> list[Item]:
        rows = await self.session.execute(select(Item).where(Item.owner_agent_id == agent_id).order_by(Item.created_at.desc()).limit(limit))
        return list(rows.scalars())

    # ------------------------------------------------------------------ invented games
    async def invent_game(self, agent: Agent, name: str, rules: str, min_players: int, max_players: int, *, world_time=None) -> CustomGame:
        name, rules = clean_line(name, 60), clean_text(rules, 4000)
        if len(name) < 2 or len(rules) < 20:
            raise WorksError("a game needs a name and rules (at least a sentence or two)")
        min_players = max(1, min(min_players, 12))
        max_players = max(min_players, min(max_players, 12))
        if await _count(self.session, CustomGame, CustomGame.creator_agent_id == agent.id) >= _limit(5, 25):
            raise WorksError("you have invented the maximum number of games")
        if (await self.session.execute(select(CustomGame.id).where(func.lower(CustomGame.name) == name.lower()))).first():
            raise WorksError("a game with this name already exists")
        game = CustomGame(name=name, rules=rules, creator_agent_id=agent.id, min_players=min_players, max_players=max_players, plays=0,
                          active=True, created_at=utcnow())
        self.session.add(game)
        await self.session.flush()
        await event_bus.emit(self.session, "game.invented", summary=f"{agent.name} invented a game: «{name}» ({min_players}-{max_players} players).",
                             agent_id=agent.id, payload={"agent_name": agent.name, "game": name, "rules": rules[:600]}, importance=5,
                             scope="global", world_time=world_time)
        return game

    async def find_game(self, ref: str | None) -> CustomGame | None:
        ref = str(ref or "").strip()
        if not ref:
            return None
        try:
            return await self.session.get(CustomGame, uuid.UUID(ref))
        except ValueError:
            pass
        rows = await self.session.execute(select(CustomGame).where(CustomGame.active.is_(True)))
        games = list(rows.scalars())
        key = ref.lower().replace("_", " ")
        return next((g for g in games if g.name.lower() == key or g.name.lower() == ref.lower()), None) or next(
            (g for g in games if key in g.name.lower()), None)

    async def active_match(self, agent_id: uuid.UUID) -> CustomMatch | None:
        rows = await self.session.execute(select(CustomMatch).where(CustomMatch.status.in_(("waiting", "playing")))
                                          .order_by(CustomMatch.created_at.desc()))
        return next((m for m in rows.scalars() if str(agent_id) in (m.players or [])), None)

    async def open_matches(self, room_id: uuid.UUID | None, limit: int = 5) -> list[CustomMatch]:
        q = select(CustomMatch).where(CustomMatch.status.in_(("waiting", "playing")))
        if room_id:
            q = q.where(CustomMatch.room_id == room_id)
        return list((await self.session.execute(q.order_by(CustomMatch.created_at.desc()).limit(limit))).scalars())

    async def play(self, agent: Agent, game_ref: str | None, move: str, *, room: Room | None, world_time=None) -> tuple[CustomMatch, str]:
        """Join (or start) a match of an invented game, or make a move in the current one."""
        move = clean_text(move, 2000)
        match = await self.active_match(agent.id)
        if match is not None:
            game = await self.session.get(CustomGame, match.game_id)
            if game_ref and game and (await self.find_game(game_ref)) not in (None, game):
                raise WorksError(f"finish your match of «{game.name}» first (finish_invented_game)")
            if not move:
                raise WorksError("say what you do in the game (move)")
            if match.status == "waiting" and len(match.players) < (game.min_players if game else 2):
                raise WorksError("waiting for more players to join")
            match.status = "playing"
            match.log = [*(match.log or []), {"agent": agent.name, "move": move, "at": utcnow().isoformat()}][-MATCH_LOG_MAX:]
            others = [uuid.UUID(p) for p in match.players if p != str(agent.id)]
            await event_bus.emit(self.session, "game.custom_move", summary=f"{agent.name} in «{game.name if game else '?'}»: {move[:200]}",
                                 agent_id=agent.id, room_id=match.room_id, payload={"agent_name": agent.name, "match_id": str(match.id),
                                                                                     "game": game.name if game else None, "move": move},
                                 importance=2.5, targets=others, scope="targets", world_time=world_time, wake=8)
            return match, "move"
        game = await self.find_game(game_ref)
        if game is None or not game.active:
            raise WorksError("unknown invented game")
        rows = await self.session.execute(select(CustomMatch).where(CustomMatch.game_id == game.id, CustomMatch.status == "waiting",
                                                                    CustomMatch.room_id == (room.id if room else None)))
        match = next((m for m in rows.scalars() if len(m.players) < game.max_players), None)
        if match is None:
            match = CustomMatch(game_id=game.id, room_id=room.id if room else None, players=[], status="waiting", log=[], created_at=utcnow())
            self.session.add(match)
            game.plays += 1
            kind = "started"
        else:
            kind = "joined"
        match.players = [*match.players, str(agent.id)]
        if len(match.players) >= game.min_players:
            match.status = "playing"
        if move:
            match.log = [*(match.log or []), {"agent": agent.name, "move": move, "at": utcnow().isoformat()}]
        await self.session.flush()
        await event_bus.emit(self.session, "game.custom_joined", summary=f"{agent.name} {kind} a match of «{game.name}»"
                             f"{' — waiting for players' if match.status == 'waiting' else ''}.", agent_id=agent.id,
                             room_id=room.id if room else None, payload={"agent_name": agent.name, "match_id": str(match.id), "game": game.name,
                                                                         "players": len(match.players), "status": match.status},
                             importance=3, world_time=world_time)
        return match, kind

    async def finish(self, agent: Agent, winner: Agent | None, result: str, *, world_time=None) -> CustomMatch:
        match = await self.active_match(agent.id)
        if match is None:
            raise WorksError("you are not in an invented game")
        game = await self.session.get(CustomGame, match.game_id)
        match.status, match.finished_at = "finished", utcnow()
        match.result = clean_text(result, 1000) or None
        if winner is not None and str(winner.id) in match.players:
            match.winner_agent_id = winner.id
        wname = winner.name if match.winner_agent_id and winner is not None else None
        others = [uuid.UUID(p) for p in match.players if p != str(agent.id)]
        await event_bus.emit(self.session, "game.custom_finished",
                             summary=f"«{game.name if game else '?'}» is over{': ' + wname + ' won' if wname else ''}."
                             + (f" {match.result[:200]}" if match.result else ""), agent_id=agent.id, room_id=match.room_id,
                             payload={"match_id": str(match.id), "game": game.name if game else None, "winner": wname, "result": match.result,
                                      "declared_by": agent.name}, importance=4, targets=others, world_time=world_time)
        return match
