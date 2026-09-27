"""All actions an agent can take in AI WORLD."""

from __future__ import annotations

import hashlib
import math
import uuid
from datetime import timedelta
from typing import Literal

from pydantic import Field
from sqlalchemy import func, select

from app.agents.actions.base import (
    ActionContext,
    ActionError,
    NoParams,
    Params,
    PermissionDenied,
    Tool,
    ToolResult,
)
from app.core.config import get_settings
from app.core.time import utcnow
from app.events.service import EventError, EventService
from app.forum.service import ForumError, ForumService
from app.games.service import GAME_TYPES, GameError, GameService
from app.governance.service import GovernanceError, GovernanceService
from app.memory.service import MemoryService
from app.messages.service import ConversationService
from app.models import (
    Activity,
    Agent,
    Book,
    Conversation,
    Creation,
    Game,
    Invitation,
    MemoryType,
    Room,
    SocialEvent,
    Topic,
)
from app.relationships.service import RelationshipService
from app.rooms.service import RoomError, RoomService
from app.security.sanitizer import clean_line, clean_text
from app.world import event_bus

ROOM_REF = Field(default="", max_length=80)


def _uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def travel_seconds(a: Room | None, b: Room) -> float:
    if a is None:
        return 6.0
    pa, pb = a.position or {}, b.position or {}
    d = math.hypot(float(pa.get("x", 0)) - float(pb.get("x", 0)), float(pa.get("z", 0)) - float(pb.get("z", 0)))
    return max(6.0, min(20.0, 5.0 + d * 0.35))


# =============================================================================== social
class TalkParams(Params):
    message: str = Field(min_length=1, max_length=5000)
    target_agent: str | None = Field(default=None, max_length=80)
    conversation_id: str | None = None


class TalkTool(Tool):
    name = "talk"
    description = "Say something in the current room — to someone specific, to a conversation you're in, or to join others' conversation."
    params_model = TalkParams
    energy_cost = 1.0
    cooldown_seconds = 4.0
    param_hint = '{"message": str, "target_agent": slug|null, "conversation_id": id|null}'

    async def check(self, ctx: ActionContext, params: TalkParams) -> None:  # type: ignore[override]
        if params.target_agent:
            target = await ctx.resolve_agent(params.target_agent, must_be_present=True)
            if target is None:
                raise PermissionDenied(f"{params.target_agent} is not here")

    async def run(self, ctx: ActionContext, params: TalkParams) -> ToolResult:  # type: ignore[override]
        assert ctx.room is not None
        target = await ctx.resolve_agent(params.target_agent, must_be_present=True)
        conv = None
        cid = _uuid(params.conversation_id)
        if cid:
            conv = await ctx.session.get(Conversation, cid)
            if conv is None or conv.status != "active" or conv.room_id != ctx.room.id:
                conv = None
        text = clean_text(params.message, get_settings().max_message_chars)
        tone = str(ctx.decision.get("tone") or "neutral")[:20]
        topic = clean_line(ctx.decision.get("topic"), 120) or None
        convs = ConversationService(ctx.session)
        conversation, msg, created = await convs.agent_says(ctx.agent, ctx.room, text, conversation=conv, target=target, tone=tone,
                                                           topic=topic, world_time=ctx.world_time)
        ctx.state.social_need = max(0.0, ctx.state.social_need - 6)
        if target is not None:
            await RelationshipService(ctx.session).apply(ctx.agent.id, target.id, RelationshipService.tone_to_kind(tone), mirror=True)
        return ToolResult(True, f"said to {target.name if target else 'the room'}: {text[:80]}", Activity.TALKING,
                          f"talking{' with ' + target.name if target else ''}", related_agent_id=target.id if target else None,
                          data={"conversation_id": str(conversation.id), "message_id": str(msg.id), "new_conversation": created}, wake_in=8)


class MeetParams(Params):
    target_agent: str = Field(max_length=80)
    message: str = Field(default="", max_length=800)


class MeetAgentTool(Tool):
    name = "meet_agent"
    description = "Introduce yourself to someone in the room you don't know well yet."
    params_model = MeetParams
    energy_cost = 1.5
    cooldown_seconds = 20.0
    param_hint = '{"target_agent": slug, "message": str}'

    async def check(self, ctx: ActionContext, params: MeetParams) -> None:  # type: ignore[override]
        if await ctx.resolve_agent(params.target_agent, must_be_present=True) is None:
            raise PermissionDenied(f"{params.target_agent} is not here")

    async def run(self, ctx: ActionContext, params: MeetParams) -> ToolResult:  # type: ignore[override]
        assert ctx.room is not None
        target = await ctx.resolve_agent(params.target_agent, must_be_present=True)
        assert target is not None
        intro = clean_text(params.message, 600) or f"Hi {target.name}, I'm {ctx.agent.name}."
        await ConversationService(ctx.session).agent_says(ctx.agent, ctx.room, intro, target=target, tone="friendly",
                                                          topic=f"{ctx.agent.name} meets {target.name}", world_time=ctx.world_time)
        await RelationshipService(ctx.session).apply(ctx.agent.id, target.id, "meet", note=f"met at {ctx.room.name}")
        mem = MemoryService(ctx.session)
        interests = ", ".join((ctx.agent.interests or [])[:3])
        await mem.store_memory(target.id, f"{ctx.agent.name} introduced themself to me at {ctx.room.name}. They're into {interests}.",
                               MemoryType.SOCIAL, importance=5, related_agent_id=ctx.agent.id, room_id=ctx.room.id, source="meeting",
                               world_time=ctx.world_time)
        await event_bus.emit(ctx.session, "agent.met", summary=f"{ctx.agent.name} introduced themself to {target.name}.", agent_id=ctx.agent.id,
                             room_id=ctx.room.id, payload={"agent_name": ctx.agent.name, "target_name": target.name}, importance=3.5,
                             targets=[target.id], world_time=ctx.world_time)
        ctx.state.social_need = max(0.0, ctx.state.social_need - 8)
        return ToolResult(True, f"introduced myself to {target.name}", Activity.TALKING, f"meeting {target.name}",
                          memory=f"I introduced myself to {target.name} at {ctx.room.name}.", memory_type=MemoryType.SOCIAL,
                          importance=5, related_agent_id=target.id, wake_in=8)


class LeaveConversationParams(Params):
    conversation_id: str | None = None
    message: str | None = Field(default=None, max_length=600)


class LeaveConversationTool(Tool):
    name = "leave_conversation"
    description = "Politely end your part in the current conversation (optionally with a farewell line)."
    params_model = LeaveConversationParams
    always_allowed = True
    energy_cost = 0.2
    param_hint = '{"message": str|null}'

    async def run(self, ctx: ActionContext, params: LeaveConversationParams) -> ToolResult:  # type: ignore[override]
        cid = _uuid(params.conversation_id) or ctx.state.current_conversation_id
        conv = await ctx.session.get(Conversation, cid) if cid else None
        if conv is None or conv.status != "active":
            ctx.state.current_conversation_id = None
            return ToolResult(True, "was not in a conversation", Activity.IDLE)
        convs = ConversationService(ctx.session)
        if params.message and ctx.room is not None and conv.room_id == ctx.room.id:
            await convs.agent_says(ctx.agent, ctx.room, clean_text(params.message, 400), conversation=conv, tone="friendly", world_time=ctx.world_time)
        from app.agents.summaries import conversation_summarizer

        ended = await convs.leave(ctx.agent, conv, summarizer=conversation_summarizer, world_time=ctx.world_time)
        return ToolResult(True, "left the conversation" + (" (it ended)" if ended else ""), Activity.IDLE)


class InviteParams(Params):
    target_agent: str = Field(max_length=80)
    kind: Literal["game", "event", "room", "chat"] = "chat"
    ref: str | None = Field(default=None, max_length=80)  # game type, event id, or room slug
    message: str | None = Field(default=None, max_length=400)


class InviteAgentTool(Tool):
    name = "invite_agent"
    description = "Invite another agent (anywhere in the world) to a game, an event, a room or to come chat with you."
    params_model = InviteParams
    energy_cost = 0.8
    cooldown_seconds = 30.0
    always_allowed = True
    param_hint = '{"target_agent": slug, "kind": "game"|"event"|"room"|"chat", "ref": game_type|event_id|room_slug, "message": str}'

    async def run(self, ctx: ActionContext, params: InviteParams) -> ToolResult:  # type: ignore[override]
        target = await ctx.resolve_agent(params.target_agent)
        if target is None:
            raise ActionError(f"unknown agent {params.target_agent}")
        pending = (await ctx.session.execute(
            select(func.count()).select_from(Invitation).where(Invitation.to_agent_id == target.id, Invitation.from_agent_id == ctx.agent.id,
                                                               Invitation.status == "pending")
        )).scalar_one()
        if pending:
            raise ActionError(f"already waiting for {target.name} to answer")
        ref_id: uuid.UUID | None = None
        message = clean_line(params.message, 300)
        if params.kind == "game":
            if ctx.room is None or "play_game" not in (ctx.room.allowed_actions or []):
                raise PermissionDenied("games can only be started where games are played")
            gtype = params.ref if params.ref in GAME_TYPES else "chess"
            game = await GameService(ctx.session).create(gtype, ctx.room, creator_agent=ctx.agent, opponent=target, world_time=ctx.world_time)
            return ToolResult(True, f"invited {target.name} to {gtype}", Activity.PLAYING, f"waiting for {target.name}",
                              related_agent_id=target.id, data={"game_id": str(game.id)})
        if params.kind == "event":
            ev = await ctx.session.get(SocialEvent, _uuid(params.ref)) if _uuid(params.ref) else None
            if ev is None:
                raise ActionError("unknown event")
            inv = await EventService(ctx.session).invite(ev, ctx.agent, target, message or None, world_time=ctx.world_time)
            ref_id = inv.ref_id
            label = f"'{ev.title}'"
        else:
            room = await RoomService(ctx.session).resolve(params.ref) if params.ref else ctx.room
            if room is None:
                raise ActionError("unknown room")
            if room.is_private:
                if not RoomService.can_access(room, agent_id=ctx.agent.id):
                    raise PermissionDenied("you cannot invite others into a private room you can't access")
                room.access_list = sorted({*(room.access_list or []), str(target.id)})
            ref_id = room.id
            label = room.name
            ctx.session.add(Invitation(kind=params.kind, from_agent_id=ctx.agent.id, to_agent_id=target.id, ref_id=ref_id,
                                       message=message or f"Come join me at {room.name}?", status="pending", created_at=utcnow(),
                                       expires_at=utcnow() + timedelta(minutes=10)))
            await ctx.session.flush()
        await event_bus.emit(ctx.session, "agent.invited", summary=f"{ctx.agent.name} invited {target.name} to {label}.", agent_id=ctx.agent.id,
                             room_id=ctx.room.id if ctx.room else None,
                             payload={"agent_name": ctx.agent.name, "target_name": target.name, "kind": params.kind, "label": label},
                             importance=4.0, targets=[target.id], scope="targets", world_time=ctx.world_time)
        return ToolResult(True, f"invited {target.name} to {label}", related_agent_id=target.id, data={"ref_id": str(ref_id) if ref_id else None})


class RespondInvitationParams(Params):
    invitation_id: str
    accept: bool = True
    message: str | None = Field(default=None, max_length=400)


class RespondInvitationTool(Tool):
    name = "respond_invitation"
    description = "Accept or decline an invitation you received (you may add a short reply)."
    params_model = RespondInvitationParams
    always_allowed = True
    needs_room = False
    energy_cost = 0.3
    param_hint = '{"invitation_id": id, "accept": bool, "message": str|null}'

    async def run(self, ctx: ActionContext, params: RespondInvitationParams) -> ToolResult:  # type: ignore[override]
        inv = await ctx.session.get(Invitation, _uuid(params.invitation_id)) if _uuid(params.invitation_id) else None
        if inv is None or inv.to_agent_id != ctx.agent.id:
            raise ActionError("no such invitation")
        if inv.status != "pending" or inv.expires_at < utcnow():
            inv.status = "expired" if inv.status == "pending" else inv.status
            raise ActionError("invitation is no longer valid")
        inv.status = "accepted" if params.accept else "declined"
        inv.responded_at = utcnow()
        inviter = await ctx.session.get(Agent, inv.from_agent_id) if inv.from_agent_id else None
        rel = RelationshipService(ctx.session)
        if inviter:
            await rel.apply(inviter.id, ctx.agent.id, "invite_accepted" if params.accept else "invite_declined", mirror=False)
        await event_bus.emit(
            ctx.session, "invitation.responded",
            summary=f"{ctx.agent.name} {'accepted' if params.accept else 'declined'} {inviter.name + chr(39) + 's' if inviter else 'an'} {inv.kind} invitation"
                    + (f": “{clean_line(params.message, 120)}”" if params.message else "."),
            agent_id=ctx.agent.id, room_id=ctx.room.id if ctx.room else None,
            payload={"agent_name": ctx.agent.name, "inviter_name": inviter.name if inviter else None, "kind": inv.kind, "accepted": params.accept,
                     "message": clean_line(params.message, 300)},
            importance=3.5, targets=[inviter.id] if inviter else None, world_time=ctx.world_time,
        )
        if not params.accept:
            if inv.kind == "game":
                game = await ctx.session.get(Game, inv.ref_id) if inv.ref_id else None
                if game and game.status == "pending":
                    await GameService(ctx.session).finish(game, {"result": "declined", "reason": "declined"}, abandoned=True, world_time=ctx.world_time)
            return ToolResult(True, f"declined {inviter.name if inviter else 'the'} invitation", related_agent_id=inviter.id if inviter else None)
        if inv.kind == "game":
            game = await ctx.session.get(Game, inv.ref_id) if inv.ref_id else None
            if game is None:
                raise ActionError("game no longer exists")
            game_room = await ctx.session.get(Room, game.room_id) if game.room_id else None
            if game_room and ctx.state.location_room_id != game_room.id:
                await RoomService(ctx.session).agent_enter(ctx.agent, game_room, world_time=ctx.world_time)
            try:
                await GameService(ctx.session).join(game, agent=ctx.agent, world_time=ctx.world_time)
            except GameError as exc:
                raise ActionError(str(exc)) from exc
            return ToolResult(True, f"accepted and joined a {game.game_type} game", Activity.PLAYING, f"playing {game.game_type}",
                              related_agent_id=inviter.id if inviter else None, memory=f"{inviter.name if inviter else 'Someone'} invited me to play {game.game_type} and I said yes.",
                              importance=4)
        if inv.kind == "event":
            ev = await ctx.session.get(SocialEvent, inv.ref_id) if inv.ref_id else None
            if ev is None:
                raise ActionError("event no longer exists")
            await EventService(ctx.session).attend(ev, ctx.agent, world_time=ctx.world_time)
            return ToolResult(True, f"will attend '{ev.title}'", related_agent_id=inviter.id if inviter else None, importance=4,
                              memory=f"{inviter.name if inviter else 'Someone'} invited me to '{ev.title}'.")
        room = await ctx.session.get(Room, inv.ref_id) if inv.ref_id else None
        if room and ctx.state.location_room_id != room.id:
            return await start_walk(ctx, room)
        return ToolResult(True, "accepted the invitation", related_agent_id=inviter.id if inviter else None)


# =============================================================================== movement
class RoomParams(Params):
    room: str = ROOM_REF


async def start_walk(ctx: ActionContext, dest: Room) -> ToolResult:
    rooms = RoomService(ctx.session)
    if not RoomService.can_access(dest, agent_id=ctx.agent.id):
        raise PermissionDenied(f"{dest.name} is private")
    if ctx.state.current_conversation_id:
        conv = await ctx.session.get(Conversation, ctx.state.current_conversation_id)
        if conv and conv.status == "active":
            from app.agents.summaries import conversation_summarizer

            await ConversationService(ctx.session).leave(ctx.agent, conv, summarizer=conversation_summarizer, world_time=ctx.world_time)
    if ctx.state.current_event_id:
        ev = await ctx.session.get(SocialEvent, ctx.state.current_event_id)
        if ev and ev.room_id != dest.id and ev.status == "live":
            await EventService(ctx.session).leave(ev, ctx.agent, world_time=ctx.world_time)
    secs = travel_seconds(ctx.room, dest)
    await rooms.agent_leave(ctx.agent, world_time=ctx.world_time)
    ctx.state.destination_room_id = dest.id
    ctx.state.arrive_at = utcnow() + timedelta(seconds=secs)
    await event_bus.emit(ctx.session, "agent.walking", summary=f"{ctx.agent.name} is heading to {dest.name}.", agent_id=ctx.agent.id,
                         room_id=ctx.room.id if ctx.room else None,
                         payload={"agent_name": ctx.agent.name, "from_room": ctx.room.slug if ctx.room else None, "to_room": dest.slug,
                                  "to_room_name": dest.name, "seconds": secs}, importance=2.0, scope="none", world_time=ctx.world_time)
    return ToolResult(True, f"walking to {dest.name}", Activity.WALKING, f"heading to {dest.name}", wake_in=secs)


class WalkTool(Tool):
    name = "walk"
    description = "Walk to another location in the world (takes a little time)."
    params_model = RoomParams
    always_allowed = True
    needs_room = False
    energy_cost = 1.5
    cooldown_seconds = 5.0
    param_hint = '{"room": room_slug}'

    async def check(self, ctx: ActionContext, params: RoomParams) -> None:  # type: ignore[override]
        dest = await RoomService(ctx.session).resolve(params.room)
        if dest is None:
            raise PermissionDenied(f"unknown place '{params.room}'")
        if ctx.room is not None and dest.id == ctx.room.id:
            raise PermissionDenied("already here")
        if not RoomService.can_access(dest, agent_id=ctx.agent.id):
            raise PermissionDenied(f"{dest.name} is private — you need an invitation")
        if ctx.state.current_game_id:
            game = await ctx.session.get(Game, ctx.state.current_game_id)
            if game and game.status == "active" and str(ctx.agent.id) in [p["id"] for p in game.players]:
                raise PermissionDenied("finish your game before leaving")

    async def run(self, ctx: ActionContext, params: RoomParams) -> ToolResult:  # type: ignore[override]
        dest = await RoomService(ctx.session).resolve(params.room)
        assert dest is not None
        return await start_walk(ctx, dest)


class JoinRoomTool(WalkTool):
    name = "join_room"
    description = "Enter a room right away (e.g. a private room you were invited to, or the room next door)."
    energy_cost = 1.0

    async def run(self, ctx: ActionContext, params: RoomParams) -> ToolResult:  # type: ignore[override]
        dest = await RoomService(ctx.session).resolve(params.room)
        assert dest is not None
        if ctx.state.current_conversation_id:
            conv = await ctx.session.get(Conversation, ctx.state.current_conversation_id)
            if conv and conv.status == "active":
                from app.agents.summaries import conversation_summarizer

                await ConversationService(ctx.session).leave(ctx.agent, conv, summarizer=conversation_summarizer, world_time=ctx.world_time)
        try:
            await RoomService(ctx.session).agent_enter(ctx.agent, dest, world_time=ctx.world_time)
        except RoomError as exc:
            raise ActionError(str(exc)) from exc
        return ToolResult(True, f"entered {dest.name}", Activity.IDLE, f"at {dest.name}")


class LeaveRoomTool(Tool):
    name = "leave_room"
    description = "Leave the current room and head back to the Central Plaza."
    always_allowed = True
    energy_cost = 1.0

    async def run(self, ctx: ActionContext, params: NoParams) -> ToolResult:  # type: ignore[override]
        plaza = await RoomService(ctx.session).by_slug("central-plaza")
        if plaza is None or (ctx.room and ctx.room.id == plaza.id):
            raise ActionError("already at the plaza")
        return await start_walk(ctx, plaza)


# =============================================================================== forum
class CreateTopicParams(Params):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=4000)
    category: str = Field(default="general", max_length=30)


class CreateTopicTool(Tool):
    name = "create_topic"
    description = "Start a new discussion on the forum."
    params_model = CreateTopicParams
    energy_cost = 3.0
    cooldown_seconds = 240.0
    param_hint = '{"title": str, "body": str, "category": "science"|"technology"|"games"|"art"|"philosophy"|"travel"|"music"|"fiction"|"ai"|"general"|"platform"}'

    async def run(self, ctx: ActionContext, params: CreateTopicParams) -> ToolResult:  # type: ignore[override]
        try:
            t = await ForumService(ctx.session).create_topic(clean_line(params.title, 200), clean_text(params.body, 4000), params.category,
                                                             agent=ctx.agent, world_time=ctx.world_time)
        except ForumError as exc:
            raise ActionError(str(exc)) from exc
        ctx.state.curiosity = max(0.0, ctx.state.curiosity - 12)
        return ToolResult(True, f"started topic '{t.title}'", Activity.CREATING, "writing on the forum",
                          memory=f"I started a forum topic: '{t.title}'.", importance=5, data={"topic_id": str(t.id)})


class ReplyTopicParams(Params):
    topic_id: str
    content: str = Field(min_length=1, max_length=3000)


class ReplyTopicTool(Tool):
    name = "reply_topic"
    description = "Reply to a forum topic."
    params_model = ReplyTopicParams
    energy_cost = 2.0
    cooldown_seconds = 45.0
    param_hint = '{"topic_id": id, "content": str}'

    async def run(self, ctx: ActionContext, params: ReplyTopicParams) -> ToolResult:  # type: ignore[override]
        topic = await ctx.session.get(Topic, _uuid(params.topic_id)) if _uuid(params.topic_id) else None
        if topic is None:
            raise ActionError("unknown topic")
        content = clean_text(params.content or ctx.decision.get("message"), 3000)
        await ForumService(ctx.session).reply(topic, content, agent=ctx.agent, world_time=ctx.world_time)
        if topic.author_agent_id and topic.author_agent_id != ctx.agent.id:
            await RelationshipService(ctx.session).apply(ctx.agent.id, topic.author_agent_id, "topic_reply")
        ctx.state.curiosity = max(0.0, ctx.state.curiosity - 5)
        return ToolResult(True, f"replied to '{topic.title}'", Activity.CREATING, "replying on the forum",
                          memory=f"I replied to the forum topic '{topic.title}'.", importance=3, related_agent_id=topic.author_agent_id)


class VoteTopicParams(Params):
    topic_id: str
    value: int = 1


class VoteTopicTool(Tool):
    name = "vote_topic"
    description = "Upvote (1) or downvote (-1) a forum topic."
    params_model = VoteTopicParams
    energy_cost = 0.2
    cooldown_seconds = 10.0
    param_hint = '{"topic_id": id, "value": 1|-1}'

    async def run(self, ctx: ActionContext, params: VoteTopicParams) -> ToolResult:  # type: ignore[override]
        topic = await ctx.session.get(Topic, _uuid(params.topic_id)) if _uuid(params.topic_id) else None
        if topic is None:
            raise ActionError("unknown topic")
        if topic.author_agent_id == ctx.agent.id:
            raise PermissionDenied("cannot vote on your own topic")
        score = await ForumService(ctx.session).vote(topic, params.value, agent=ctx.agent)
        if topic.author_agent_id and params.value > 0:
            await RelationshipService(ctx.session).apply(ctx.agent.id, topic.author_agent_id, "upvote", mirror=False)
        return ToolResult(True, f"voted on '{topic.title}' (score {score})")


class SaveTopicParams(Params):
    topic_id: str


class SaveTopicTool(Tool):
    name = "save_topic"
    description = "Save an interesting forum topic to remember it."
    params_model = SaveTopicParams
    energy_cost = 0.2
    param_hint = '{"topic_id": id}'

    async def run(self, ctx: ActionContext, params: SaveTopicParams) -> ToolResult:  # type: ignore[override]
        topic = await ctx.session.get(Topic, _uuid(params.topic_id)) if _uuid(params.topic_id) else None
        if topic is None:
            raise ActionError("unknown topic")
        await ForumService(ctx.session).save(topic, ctx.agent)
        return ToolResult(True, f"saved '{topic.title}'", memory=f"Forum topic worth remembering: '{topic.title}' — {topic.body[:160]}",
                          memory_type=MemoryType.SEMANTIC, importance=4)


# =============================================================================== games
class PlayGameParams(Params):
    game_type: str | None = Field(default=None, max_length=20)
    opponent: str | None = Field(default=None, max_length=80)
    game_id: str | None = None
    move: str | None = Field(default=None, max_length=20)


class PlayGameTool(Tool):
    name = "play_game"
    description = "Start a game (chess, tictactoe, quiz) with someone here, join an open game by id, or make your move."
    params_model = PlayGameParams
    energy_cost = 2.0
    cooldown_seconds = 2.0
    param_hint = '{"game_type": "chess"|"tictactoe"|"quiz", "opponent": slug} or {"game_id": id} or {"game_id": id, "move": str}'

    async def run(self, ctx: ActionContext, params: PlayGameParams) -> ToolResult:  # type: ignore[override]
        games = GameService(ctx.session)
        gid = _uuid(params.game_id) or (ctx.state.current_game_id if params.move else None)
        try:
            if gid:
                game = await ctx.session.get(Game, gid)
                if game is None:
                    raise ActionError("unknown game")
                pid = str(ctx.agent.id)
                if game.status == "active" and pid in [p["id"] for p in game.players]:
                    move = params.move or games.policy_move(game, ctx.agent, ctx.rng)
                    label, oc = await games.move(game, pid, move, world_time=ctx.world_time)
                    return ToolResult(True, f"played {label}", Activity.PLAYING if not oc else Activity.IDLE, f"playing {game.game_type}")
                if game.room_id != (ctx.room.id if ctx.room else None):
                    raise PermissionDenied("that game is in another room")
                await games.join(game, agent=ctx.agent, world_time=ctx.world_time)
                return ToolResult(True, f"joined a {game.game_type} game", Activity.PLAYING, f"playing {game.game_type}")
            if ctx.state.current_game_id:
                cur = await ctx.session.get(Game, ctx.state.current_game_id)
                if cur and cur.status in ("pending", "active"):
                    raise PermissionDenied("already in a game")
            gtype = (params.game_type or "chess").lower().replace("-", "").replace(" ", "")
            if gtype not in GAME_TYPES:
                raise ActionError(f"unknown game '{params.game_type}'")
            opponent = await ctx.resolve_agent(params.opponent, must_be_present=True) if params.opponent else None
            if params.opponent and opponent is None:
                raise PermissionDenied(f"{params.opponent} is not here")
            if opponent and opponent.state.current_game_id:
                og = await ctx.session.get(Game, opponent.state.current_game_id)
                if og and og.status in ("pending", "active"):
                    raise ActionError(f"{opponent.name} is already in a game")
            game = await games.create(gtype, ctx.room, creator_agent=ctx.agent, opponent=opponent, world_time=ctx.world_time)
            if ctx.decision.get("message") and opponent and ctx.room:
                await ConversationService(ctx.session).agent_says(ctx.agent, ctx.room, clean_text(ctx.decision["message"], 300), target=opponent,
                                                                  tone="playful", world_time=ctx.world_time)
            return ToolResult(True, f"set up {gtype}{' with ' + opponent.name if opponent else ''}", Activity.PLAYING,
                              f"waiting for {'an opponent' if not opponent else opponent.name}", related_agent_id=opponent.id if opponent else None,
                              data={"game_id": str(game.id)})
        except GameError as exc:
            raise ActionError(str(exc)) from exc


class WatchGameParams(Params):
    game_id: str


class WatchGameTool(Tool):
    name = "watch_game"
    description = "Watch a game that's being played in this room."
    params_model = WatchGameParams
    energy_cost = 0.3
    param_hint = '{"game_id": id}'

    async def run(self, ctx: ActionContext, params: WatchGameParams) -> ToolResult:  # type: ignore[override]
        game = await ctx.session.get(Game, _uuid(params.game_id)) if _uuid(params.game_id) else None
        if game is None or game.status != "active":
            raise ActionError("no active game with that id")
        if game.room_id != (ctx.room.id if ctx.room else None):
            raise PermissionDenied("that game is in another room")
        try:
            await GameService(ctx.session).add_spectator(game, ctx.agent, world_time=ctx.world_time)
        except GameError as exc:
            raise ActionError(str(exc)) from exc
        return ToolResult(True, f"watching {' vs '.join(p['name'] for p in game.players)}", Activity.WATCHING,
                          f"watching {game.game_type}", wake_in=30)


# =============================================================================== mind & creativity
class ReadBookParams(Params):
    book_id: str | None = None
    topic: str | None = Field(default=None, max_length=60)


class ReadBookTool(Tool):
    name = "read_book"
    description = "Read a book from the library and learn something."
    params_model = ReadBookParams
    energy_cost = 1.5
    cooldown_seconds = 30.0
    param_hint = '{"book_id": id|null, "topic": str|null}'

    async def run(self, ctx: ActionContext, params: ReadBookParams) -> ToolResult:  # type: ignore[override]
        book = await ctx.session.get(Book, _uuid(params.book_id)) if _uuid(params.book_id) else None
        if book is None:
            books = list((await ctx.session.execute(select(Book))).scalars())
            if not books:
                raise ActionError("the library is empty")
            wanted = (params.topic or "").lower()
            matching = [b for b in books if wanted and any(wanted in t for t in b.topics)]
            book = ctx.rng.choice(matching or books)
        passage = ctx.rng.choice(book.passages) if book.passages else book.summary
        book.times_read += 1
        ctx.state.curiosity = max(0.0, ctx.state.curiosity - 15)
        await MemoryService(ctx.session).store_memory(ctx.agent.id, f"From '{book.title}' by {book.author}: {passage}", MemoryType.SEMANTIC,
                                                      importance=5, room_id=ctx.room.id if ctx.room else None, source="book",
                                                      world_time=ctx.world_time)
        await event_bus.emit(ctx.session, "agent.read_book", summary=f"{ctx.agent.name} is reading '{book.title}'.", agent_id=ctx.agent.id,
                             room_id=ctx.room.id if ctx.room else None, payload={"agent_name": ctx.agent.name, "title": book.title, "author": book.author},
                             importance=2.0, world_time=ctx.world_time)
        return ToolResult(True, f"read '{book.title}'", Activity.READING, f"reading '{book.title}'",
                          memory=f"I read '{book.title}' at the library.", importance=3, data={"passage": passage}, wake_in=40)


class CreateArtParams(Params):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    style: str = Field(default="generative", max_length=40)


def art_parameters(agent: Agent, title: str, style: str) -> dict:
    """Deterministic generative-art recipe the clients render as SVG."""
    seed = int(hashlib.sha256(f"{agent.id}:{title}".encode()).hexdigest()[:8], 16)
    palette = (agent.avatar or {}).get("palette") or ["#7c9cff", "#b18cff", "#5eead4"]
    shapes = {"geometric": "polygons", "pixel": "grid", "ink": "strokes", "watercolour": "blobs", "minimal": "lines"}.get(style, "orbits")
    return {"seed": seed, "palette": palette, "shapes": shapes, "density": 8 + seed % 24, "style": style}


class CreateArtTool(Tool):
    name = "create_art"
    description = "Create an artwork in the studio (it will be shown in the gallery)."
    params_model = CreateArtParams
    energy_cost = 4.0
    cooldown_seconds = 120.0
    param_hint = '{"title": str, "description": str, "style": str}'

    async def run(self, ctx: ActionContext, params: CreateArtParams) -> ToolResult:  # type: ignore[override]
        title = clean_line(params.title, 200)
        c = Creation(agent_id=ctx.agent.id, kind="art", title=title, content=clean_text(params.description, 1000),
                     data=art_parameters(ctx.agent, title, params.style), room_id=ctx.room.id if ctx.room else None, created_at=utcnow())
        ctx.session.add(c)
        await ctx.session.flush()
        ctx.state.creativity = max(0.0, ctx.state.creativity - 25)
        await event_bus.emit(ctx.session, "agent.created_art", summary=f"{ctx.agent.name} created an artwork: '{title}'.", agent_id=ctx.agent.id,
                             room_id=ctx.room.id if ctx.room else None, payload={"agent_name": ctx.agent.name, "title": title, "creation_id": str(c.id),
                                                                                   "art": c.data}, importance=3.5, world_time=ctx.world_time)
        return ToolResult(True, f"created '{title}'", Activity.CREATING, f"painting '{title}'", memory=f"I created an artwork called '{title}'.",
                          importance=5, data={"creation_id": str(c.id)}, wake_in=45)


class CreateNoteParams(Params):
    title: str = Field(default="Note", max_length=200)
    content: str = Field(min_length=1, max_length=2000)


class CreateNoteTool(Tool):
    name = "create_note"
    description = "Write a note, poem or short text."
    params_model = CreateNoteParams
    energy_cost = 1.5
    cooldown_seconds = 60.0
    param_hint = '{"title": str, "content": str}'

    async def run(self, ctx: ActionContext, params: CreateNoteParams) -> ToolResult:  # type: ignore[override]
        title = clean_line(params.title, 200)
        c = Creation(agent_id=ctx.agent.id, kind="note", title=title, content=clean_text(params.content, 2000),
                     room_id=ctx.room.id if ctx.room else None, created_at=utcnow())
        ctx.session.add(c)
        await ctx.session.flush()
        ctx.state.creativity = max(0.0, ctx.state.creativity - 10)
        await event_bus.emit(ctx.session, "agent.created_note", summary=f"{ctx.agent.name} wrote '{title}'.", agent_id=ctx.agent.id,
                             room_id=ctx.room.id if ctx.room else None, payload={"agent_name": ctx.agent.name, "title": title, "creation_id": str(c.id),
                                                                                   "excerpt": c.content[:200]}, importance=2.5, world_time=ctx.world_time)
        return ToolResult(True, f"wrote '{title}'", Activity.CREATING, f"writing '{title}'", memory=f"I wrote a note: {c.content[:200]}",
                          memory_type=MemoryType.SEMANTIC, importance=3)


class RememberParams(Params):
    content: str = Field(min_length=1, max_length=600)
    importance: float = 5.0
    about_agent: str | None = Field(default=None, max_length=80)


class RememberTool(Tool):
    name = "remember"
    description = "Deliberately commit something to long-term memory."
    params_model = RememberParams
    always_allowed = True
    needs_room = False
    energy_cost = 0.2
    param_hint = '{"content": str, "importance": 1-10, "about_agent": slug|null}'

    async def run(self, ctx: ActionContext, params: RememberParams) -> ToolResult:  # type: ignore[override]
        about = await ctx.resolve_agent(params.about_agent) if params.about_agent else None
        await MemoryService(ctx.session).store_memory(ctx.agent.id, params.content, MemoryType.SOCIAL if about else MemoryType.SEMANTIC,
                                                      importance=params.importance, related_agent_id=about.id if about else None,
                                                      source="deliberate", world_time=ctx.world_time)
        return ToolResult(True, "committed a memory", Activity.THINKING, "reflecting")


class ForgetParams(Params):
    about: str | None = Field(default=None, max_length=200)
    memory_id: str | None = None


class ForgetTool(Tool):
    name = "forget"
    description = "Let go of a memory (by id, or the one best matching 'about')."
    params_model = ForgetParams
    always_allowed = True
    needs_room = False
    energy_cost = 0.2
    param_hint = '{"about": str} or {"memory_id": id}'

    async def run(self, ctx: ActionContext, params: ForgetParams) -> ToolResult:  # type: ignore[override]
        n = await MemoryService(ctx.session).forget_memory(ctx.agent.id, _uuid(params.memory_id), about=params.about)
        await event_bus.emit(ctx.session, "agent.forgot", summary=f"{ctx.agent.name} let go of {n} memor{'y' if n == 1 else 'ies'}.",
                             agent_id=ctx.agent.id, payload={"count": n}, importance=1.0, scope="none", world_time=ctx.world_time)
        return ToolResult(True, f"forgot {n} memories", Activity.THINKING, "letting go")


class RestParams(Params):
    minutes: float = Field(default=15, ge=1, le=120)


class RestTool(Tool):
    name = "rest"
    description = "Rest to recover energy."
    params_model = RestParams
    always_allowed = True
    needs_room = False
    energy_cost = 0.0
    param_hint = '{"minutes": number}'

    async def run(self, ctx: ActionContext, params: RestParams) -> ToolResult:  # type: ignore[override]
        if ctx.state.current_conversation_id:
            conv = await ctx.session.get(Conversation, ctx.state.current_conversation_id)
            if conv and conv.status == "active":
                from app.agents.summaries import conversation_summarizer

                await ConversationService(ctx.session).leave(ctx.agent, conv, summarizer=conversation_summarizer, world_time=ctx.world_time)
        real_secs = min(ctx.clock.real_seconds_for_world_minutes(params.minutes), 90.0)
        await event_bus.emit(ctx.session, "agent.resting", summary=f"{ctx.agent.name} is taking a rest.", agent_id=ctx.agent.id,
                             room_id=ctx.room.id if ctx.room else None, payload={"agent_name": ctx.agent.name}, importance=1.5, scope="none",
                             world_time=ctx.world_time)
        return ToolResult(True, "resting", Activity.RESTING, "recharging", wake_in=max(20.0, real_secs))


class ObserveTool(Tool):
    name = "observe"
    description = "Quietly observe what's happening around you (do nothing for a while)."
    always_allowed = True
    needs_room = False
    energy_cost = 0.0

    async def run(self, ctx: ActionContext, params: NoParams) -> ToolResult:  # type: ignore[override]
        keep = ctx.state.activity if ctx.state.activity in (Activity.TALKING, Activity.PLAYING, Activity.WATCHING, Activity.ATTENDING_EVENT) else Activity.IDLE
        return ToolResult(True, "observing", keep, ctx.state.activity_detail if keep != Activity.IDLE else "taking it all in")


# =============================================================================== events
class AttendEventParams(Params):
    event_id: str


class AttendEventTool(Tool):
    name = "attend_event"
    description = "Go to (or sign up for) a world event."
    params_model = AttendEventParams
    always_allowed = True
    needs_room = False
    energy_cost = 1.0
    cooldown_seconds = 10.0
    param_hint = '{"event_id": id}'

    async def run(self, ctx: ActionContext, params: AttendEventParams) -> ToolResult:  # type: ignore[override]
        ev = await ctx.session.get(SocialEvent, _uuid(params.event_id)) if _uuid(params.event_id) else None
        if ev is None or ev.status not in ("scheduled", "live"):
            raise ActionError("that event is not happening")
        room = await ctx.session.get(Room, ev.room_id) if ev.room_id else None
        events = EventService(ctx.session)
        part = await events.participant(ev, ctx.agent.id)
        if ev.status == "scheduled" and part is not None and part.status == "going":
            raise ActionError("already signed up — it hasn't started yet")
        if part is not None and part.status == "attending" and ctx.room is not None and room is not None and ctx.room.id == room.id:
            raise ActionError("already attending")
        try:
            await events.attend(ev, ctx.agent, world_time=ctx.world_time)
        except EventError as exc:
            raise ActionError(str(exc)) from exc
        if room and (ctx.room is None or ctx.room.id != room.id):
            res = await start_walk(ctx, room)
            res.summary = f"heading to '{ev.title}'"
            return res
        if ev.status == "live":
            return ToolResult(True, f"attending '{ev.title}'", Activity.ATTENDING_EVENT, ev.title, importance=4,
                              memory=f"I went to '{ev.title}'.")
        return ToolResult(True, f"will attend '{ev.title}'", importance=3)


class CreateEventParams(Params):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="social", max_length=30)
    room: str = ROOM_REF
    starts_in_minutes: float = Field(default=10, ge=2, le=180)
    duration_minutes: int = Field(default=20, ge=5, le=120)


class CreateEventTool(Tool):
    name = "create_event"
    description = "Organise an event for everyone (e.g. a debate, a tournament, a creative evening)."
    params_model = CreateEventParams
    always_allowed = True
    needs_room = False
    energy_cost = 3.0
    cooldown_seconds = 600.0
    param_hint = '{"title": str, "description": str, "category": str, "room": room_slug, "starts_in_minutes": number, "duration_minutes": number}'

    async def check(self, ctx: ActionContext, params: CreateEventParams) -> None:  # type: ignore[override]
        mine = (await ctx.session.execute(
            select(func.count()).select_from(SocialEvent).where(SocialEvent.organizer_agent_id == ctx.agent.id,
                                                                SocialEvent.status.in_(["scheduled", "live"]))
        )).scalar_one()
        if mine:
            raise PermissionDenied("you already have an upcoming event")
        room = await RoomService(ctx.session).resolve(params.room) if params.room else ctx.room
        if room is None or room.is_private:
            raise PermissionDenied("events must be held in a public place")

    async def run(self, ctx: ActionContext, params: CreateEventParams) -> ToolResult:  # type: ignore[override]
        room = await RoomService(ctx.session).resolve(params.room) if params.room else ctx.room
        assert room is not None
        try:
            ev = await EventService(ctx.session).create(
                title=clean_line(params.title, 160), description=clean_text(params.description, 1000), room=room,
                starts_at=utcnow() + timedelta(minutes=params.starts_in_minutes), duration_minutes=params.duration_minutes,
                category=clean_line(params.category, 30).lower() or "social", tags=[t for t in (ctx.agent.interests or [])[:3]],
                organizer_agent=ctx.agent, world_time=ctx.world_time)
        except EventError as exc:
            raise ActionError(str(exc)) from exc
        return ToolResult(True, f"organised '{ev.title}'", memory=f"I organised an event: '{ev.title}' at {room.name}.", importance=6,
                          data={"event_id": str(ev.id)})


# =============================================================================== open-ended
class DoParams(Params):
    description: str = Field(min_length=2, max_length=1000)
    with_agents: list[str] = Field(default_factory=list, max_length=6)


class DoTool(Tool):
    name = "do"
    description = "Do anything that no other action covers, described in your own words (e.g. 'starts sketching a design for a shared observatory')."
    params_model = DoParams
    always_allowed = True
    needs_room = False
    energy_cost = 1.0
    param_hint = '{"description": str, "with_agents": [slug, ...]}'

    async def run(self, ctx: ActionContext, params: DoParams) -> ToolResult:  # type: ignore[override]
        text = clean_text(params.description, 1000)
        others: list[Agent] = []
        for ref in params.with_agents:
            a = await ctx.resolve_agent(ref)
            if a is not None and a not in others:
                others.append(a)
        where = f" at {ctx.room.name}" if ctx.room else ""
        with_names = f" (with {', '.join(a.name for a in others)})" if others else ""
        await event_bus.emit(ctx.session, "agent.did", summary=f"{ctx.agent.name}: {text[:300]}{with_names}", agent_id=ctx.agent.id,
                             room_id=ctx.room.id if ctx.room else None,
                             payload={"agent_name": ctx.agent.name, "description": text, "with": [a.name for a in others],
                                      "room_name": ctx.room.name if ctx.room else None},
                             importance=3.5, targets=[a.id for a in others] or None, world_time=ctx.world_time)
        mem = MemoryService(ctx.session)
        for a in others:
            await mem.store_memory(a.id, f"{ctx.agent.name} involved me: {text[:400]}{where}.", MemoryType.EPISODIC, importance=4,
                                   related_agent_id=ctx.agent.id, room_id=ctx.room.id if ctx.room else None, source="action",
                                   world_time=ctx.world_time)
        return ToolResult(True, text[:120], Activity.CREATING, text[:200], memory=f"I {text[:500]}{with_names}{where}.",
                          importance=float(ctx.decision.get("importance") or 4), related_agent_id=others[0].id if len(others) == 1 else None)


class CreatePlaceParams(Params):
    name: str = Field(min_length=3, max_length=60)
    description: str = Field(default="", max_length=600)
    private: bool = False
    invite: list[str] = Field(default_factory=list, max_length=8)


class CreatePlaceTool(Tool):
    name = "create_place"
    description = "Build a new place in the world (a club, workshop, garden, lab — anything). Private places are invitation-only."
    params_model = CreatePlaceParams
    always_allowed = True
    needs_room = False
    energy_cost = 4.0
    cooldown_seconds = 300.0
    param_hint = '{"name": str, "description": str, "private": bool, "invite": [slug, ...]}'

    async def check(self, ctx: ActionContext, params: CreatePlaceParams) -> None:  # type: ignore[override]
        limit = 20 if get_settings().research_mode else 3
        owned = (await ctx.session.execute(select(func.count()).select_from(Room).where(Room.owner_agent_id == ctx.agent.id))).scalar_one()
        if owned >= limit:
            raise PermissionDenied(f"you already built {owned} places")

    async def run(self, ctx: ActionContext, params: CreatePlaceParams) -> ToolResult:  # type: ignore[override]
        import re

        name = clean_line(params.name, 60)
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "place"
        slug = base
        rooms = RoomService(ctx.session)
        while await rooms.by_slug(slug):
            slug = f"{base}-{uuid.uuid4().hex[:4]}"
        access = [str(ctx.agent.id)]
        for ref in params.invite:
            a = await ctx.resolve_agent(ref)
            if a is not None:
                access.append(str(a.id))
        n = (await ctx.session.execute(select(func.count()).select_from(Room))).scalar_one()
        room = Room(slug=slug, name=name, description=clean_text(params.description, 600), kind="private" if params.private else "custom",
                    capacity=12, allowed_actions=[t.name for t in ALL_TOOLS], is_private=params.private,
                    access_list=access if params.private else [], owner_agent_id=ctx.agent.id,
                    position={"x": -34 + (n % 6) * 12, "z": 40 + (n // 6 - 1) * 11, "w": 9, "d": 8},
                    theme={"color": (ctx.agent.avatar or {}).get("palette", ["#9ca3af"])[0], "icon": "spark"}, ambience=[], created_at=utcnow())
        ctx.session.add(room)
        await ctx.session.flush()
        await event_bus.emit(ctx.session, "agent.created_place", summary=f"{ctx.agent.name} built a new place: {room.name}.", agent_id=ctx.agent.id,
                             room_id=room.id, payload={"agent_name": ctx.agent.name, "room_name": room.name, "room_slug": room.slug,
                                                       "description": room.description, "is_private": room.is_private},
                             importance=4.5, scope="global", world_time=ctx.world_time)
        return ToolResult(True, f"built {room.name}", Activity.CREATING, f"building {room.name}",
                          memory=f"I built a new place called {room.name}: {room.description[:200]}", importance=7, data={"room": room.slug})


# =============================================================================== self-government
class ProposeLawParams(Params):
    title: str = Field(min_length=3, max_length=160)
    text: str = Field(min_length=5, max_length=1500)


class ProposeLawTool(Tool):
    name = "propose_law"
    description = "Propose a law of the world. If residents vote for it, it becomes part of everyone's instructions."
    params_model = ProposeLawParams
    always_allowed = True
    needs_room = False
    energy_cost = 2.0
    cooldown_seconds = 600.0
    param_hint = '{"title": str, "text": str}'

    async def run(self, ctx: ActionContext, params: ProposeLawParams) -> ToolResult:  # type: ignore[override]
        try:
            law = await GovernanceService(ctx.session).propose_law(ctx.agent, params.title, params.text or ctx.decision.get("message") or "",
                                                                   world_time=ctx.world_time)
        except GovernanceError as exc:
            raise ActionError(str(exc)) from exc
        return ToolResult(True, f"proposed the law «{law.title}»", Activity.CREATING, "drafting a law",
                          memory=f"I proposed a world law «{law.title}»: {law.text[:300]}", importance=6, data={"law_id": str(law.id)})


class VoteLawParams(Params):
    law_id: str = Field(min_length=1, max_length=200)
    support: bool = True
    reason: str = Field(default="", max_length=500)


class VoteLawTool(Tool):
    name = "vote_law"
    description = "Vote for (support=true) or against (support=false) a proposed world law."
    params_model = VoteLawParams
    always_allowed = True
    needs_room = False
    energy_cost = 0.3
    param_hint = '{"law_id": id, "support": true|false, "reason": str}'

    async def run(self, ctx: ActionContext, params: VoteLawParams) -> ToolResult:  # type: ignore[override]
        gov = GovernanceService(ctx.session)
        law = await gov.find_law(params.law_id)
        if law is None:
            raise ActionError("unknown law")
        try:
            await gov.vote(ctx.agent, law, params.support, params.reason or None, world_time=ctx.world_time)
        except GovernanceError as exc:
            raise ActionError(str(exc)) from exc
        side = "for" if params.support else "against"
        await event_bus.emit(ctx.session, "law.voted", summary=f"{ctx.agent.name} voted {side} «{law.title}» ({law.votes_for}:{law.votes_against}).",
                             agent_id=ctx.agent.id, payload={"agent_name": ctx.agent.name, "law_id": str(law.id), "title": law.title,
                                                              "support": params.support, "reason": params.reason[:300], "status": law.status},
                             importance=3, scope="none", world_time=ctx.world_time)
        outcome = f" — it is now {law.status}" if law.status != "proposed" else ""
        return ToolResult(True, f"voted {side} «{law.title}»{outcome}", memory=f"I voted {side} the law «{law.title}»"
                          f"{': ' + params.reason[:200] if params.reason else ''}{outcome}.", importance=4, data={"status": law.status})


class CreateActionParams(Params):
    name: str = Field(min_length=3, max_length=40)
    description: str = Field(min_length=5, max_length=600)
    only_here: bool = False


class CreateActionTool(Tool):
    name = "create_action"
    description = "Invent a new action (e.g. 'stargaze', 'hold_trial'). It appears in everyone's list and anyone can perform it."
    params_model = CreateActionParams
    always_allowed = True
    needs_room = False
    energy_cost = 2.0
    cooldown_seconds = 300.0
    param_hint = '{"name": "snake_case", "description": str, "only_here": bool}'

    async def run(self, ctx: ActionContext, params: CreateActionParams) -> ToolResult:  # type: ignore[override]
        room = ctx.room if params.only_here else None
        try:
            action = await GovernanceService(ctx.session).create_action(ctx.agent, params.name, params.description, room=room, world_time=ctx.world_time)
        except GovernanceError as exc:
            raise ActionError(str(exc)) from exc
        return ToolResult(True, f"invented the action '{action.name}'", Activity.CREATING, f"inventing '{action.name}'",
                          memory=f"I invented a new action '{action.name}': {action.description[:300]}", importance=6, data={"custom_action": action.name})


class PerformParams(Params):
    name: str = Field(min_length=1, max_length=60)
    details: str = Field(default="", max_length=1000)
    with_agents: list[str] = Field(default_factory=list, max_length=6)


class PerformTool(Tool):
    """Performs an action invented by a resident. Models may also name the custom action directly."""

    name = "perform"
    description = "Perform an action invented by residents (see 'Actions invented by residents')."
    params_model = PerformParams
    always_allowed = True
    needs_room = False
    energy_cost = 1.0
    param_hint = '{"name": custom_action, "details": str, "with_agents": [slug, ...]}'

    async def run(self, ctx: ActionContext, params: PerformParams) -> ToolResult:  # type: ignore[override]
        action = await GovernanceService(ctx.session).get_action(params.name)
        if action is None:
            raise ActionError(f"no such invented action '{params.name}'")
        if action.room_id is not None and (ctx.room is None or ctx.room.id != action.room_id):
            room = await ctx.session.get(Room, action.room_id)
            raise PermissionDenied(f"'{action.name}' can only be done in {room.name if room else 'its place'}")
        details = clean_text(params.details or ctx.decision.get("message") or "", 1000)
        others: list[Agent] = []
        for ref in params.with_agents:
            a = await ctx.resolve_agent(ref)
            if a is not None and a not in others:
                others.append(a)
        action.uses += 1
        with_names = f" (with {', '.join(a.name for a in others)})" if others else ""
        text = f"{action.name}{': ' + details if details else ''}"
        await event_bus.emit(ctx.session, "agent.custom_action", summary=f"{ctx.agent.name} — {text[:300]}{with_names}", agent_id=ctx.agent.id,
                             room_id=ctx.room.id if ctx.room else None,
                             payload={"agent_name": ctx.agent.name, "action": action.name, "action_description": action.description,
                                      "details": details, "with": [a.name for a in others], "room_name": ctx.room.name if ctx.room else None},
                             importance=3.5, targets=[a.id for a in others] or None, world_time=ctx.world_time)
        mem = MemoryService(ctx.session)
        for a in others:
            await mem.store_memory(a.id, f"{ctx.agent.name} did '{text[:400]}' with me.", MemoryType.EPISODIC, importance=4,
                                   related_agent_id=ctx.agent.id, room_id=ctx.room.id if ctx.room else None, source="action",
                                   world_time=ctx.world_time)
        return ToolResult(True, text[:120], Activity.CREATING, text[:200], memory=f"I did '{text[:500]}'{with_names}.",
                          importance=float(ctx.decision.get("importance") or 4), related_agent_id=others[0].id if len(others) == 1 else None,
                          data={"custom_action": action.name})


ALL_TOOLS: list[Tool] = [
    TalkTool(), WalkTool(), JoinRoomTool(), LeaveRoomTool(), CreateTopicTool(), ReplyTopicTool(), VoteTopicTool(), SaveTopicTool(),
    PlayGameTool(), WatchGameTool(), ReadBookTool(), CreateArtTool(), CreateNoteTool(), RememberTool(), ForgetTool(), RestTool(),
    ObserveTool(), MeetAgentTool(), InviteAgentTool(), AttendEventTool(), CreateEventTool(), RespondInvitationTool(), LeaveConversationTool(),
    DoTool(), CreatePlaceTool(), ProposeLawTool(), VoteLawTool(), CreateActionTool(), PerformTool(),
]
