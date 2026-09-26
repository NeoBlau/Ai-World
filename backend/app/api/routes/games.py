from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db, rate_limited
from app.api.routes.common import get_agent_or_404, parse_uuid
from app.games.service import GameError, GameService
from app.models import Game, GameMove, Room, User
from app.scheduler.queue import agent_schedule
from app.schemas.inputs import GameIn, MoveIn
from app.schemas.serializers import game_out
from app.world import event_bus

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("")
async def list_games(status: str | None = Query(None, pattern="^(pending|active|finished|abandoned)$"), limit: int = Query(30, ge=1, le=100),
                     session: AsyncSession = Depends(db)) -> list[dict]:
    q = select(Game)
    if status:
        q = q.where(Game.status == status)
    rows = await session.execute(q.order_by(Game.updated_at.desc()).limit(limit))
    return [game_out(g) for g in rows.scalars()]


@router.get("/{game_id}")
async def get_game(game_id: str, session: AsyncSession = Depends(db)) -> dict:
    g = await session.get(Game, parse_uuid(game_id, "game"))
    if g is None:
        raise HTTPException(404, "game not found")
    moves = list((await session.execute(select(GameMove).where(GameMove.game_id == g.id).order_by(GameMove.move_number))).scalars())
    out = game_out(g, moves)
    out["legal_moves"] = GameService(session).legal_moves(g) if g.status == "active" else []
    return out


@router.post("", dependencies=[Depends(rate_limited)])
async def create_game(body: GameIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    """Challenge an agent. The agent decides autonomously whether to accept."""
    opponent = await get_agent_or_404(session, body.opponent)
    room = await session.get(Room, opponent.state.location_room_id) if opponent.state.location_room_id else None
    try:
        game = await GameService(session).create(body.game_type, room, creator_user=user, opponent=opponent)
    except GameError as exc:
        raise HTTPException(400, str(exc)) from exc
    await event_bus.commit(session)
    return game_out(game)


@router.post("/{game_id}/move", dependencies=[Depends(rate_limited)])
async def human_move(game_id: str, body: MoveIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    g = await session.get(Game, parse_uuid(game_id, "game"), with_for_update=True)
    if g is None:
        raise HTTPException(404, "game not found")
    try:
        label, _ = await GameService(session).move(g, str(user.id), body.move)
    except GameError as exc:
        raise HTTPException(400, str(exc)) from exc
    await event_bus.commit(session)
    if g.status == "active" and g.current_turn:
        await agent_schedule.schedule_in(g.current_turn, 2)
    return {"move": label, "game": game_out(g)}
