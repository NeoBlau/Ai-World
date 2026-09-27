"""Self-government of the world: laws voted on by residents and actions they invent.

Nothing here executes code. An adopted law is text added to every agent's
instructions (it can never override the sandbox). A custom action is a named,
described world action: performing it produces a world event and memories.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time import utcnow
from app.governance.functions import FunctionError, validate_steps
from app.models import Agent, CustomAction, LawVote, Room, WorldLaw
from app.security.permissions import is_forbidden
from app.security.sanitizer import clean_line, clean_text
from app.world import event_bus

MAX_OPEN_PROPOSALS_PER_AGENT = 3
MAX_ADOPTED_LAWS_IN_PROMPT = 12
ACTION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,39}$")


class GovernanceError(Exception):
    pass


def normalize_action_name(name: str | None) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(name or "").strip().lower().replace("-", "_").replace(" ", "_")).strip("_")[:40]


class GovernanceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ laws
    async def propose_law(self, agent: Agent, title: str, text: str, *, world_time=None) -> WorldLaw:
        title, text = clean_line(title, 160), clean_text(text, 1500)
        if len(title) < 3 or len(text) < 5:
            raise GovernanceError("a law needs a title and a text")
        open_count = (await self.session.execute(
            select(func.count()).select_from(WorldLaw).where(WorldLaw.proposer_agent_id == agent.id, WorldLaw.status == "proposed")
        )).scalar_one()
        if open_count >= MAX_OPEN_PROPOSALS_PER_AGENT:
            raise GovernanceError(f"you already have {open_count} laws waiting for votes")
        dup = (await self.session.execute(select(WorldLaw.id).where(func.lower(WorldLaw.title) == title.lower(),
                                                                    WorldLaw.status.in_(("proposed", "adopted"))))).first()
        if dup:
            raise GovernanceError("a law with this title already exists")
        law = WorldLaw(title=title, text=text, proposer_agent_id=agent.id, status="proposed", votes_for=0, votes_against=0, created_at=utcnow())
        self.session.add(law)
        await self.session.flush()
        await event_bus.emit(self.session, "law.proposed", summary=f"{agent.name} proposed a law: «{title}».", agent_id=agent.id,
                             payload={"agent_name": agent.name, "law_id": str(law.id), "title": title, "text": text},
                             importance=5, scope="global", world_time=world_time)
        await self.vote(agent, law, True, "I proposed it", world_time=world_time)
        return law

    async def vote(self, agent: Agent, law: WorldLaw, support: bool, reason: str | None = None, *, world_time=None) -> WorldLaw:
        if law.status != "proposed":
            raise GovernanceError(f"this law is already {law.status}")
        existing = (await self.session.execute(select(LawVote).where(LawVote.law_id == law.id, LawVote.agent_id == agent.id))).scalar_one_or_none()
        if existing is not None:
            if existing.support == support:
                raise GovernanceError("you already voted this way")
            if existing.support:
                law.votes_for -= 1
            else:
                law.votes_against -= 1
            existing.support, existing.reason = support, clean_text(reason, 500) if reason else None
        else:
            self.session.add(LawVote(law_id=law.id, agent_id=agent.id, support=support, reason=clean_text(reason, 500) if reason else None,
                                     created_at=utcnow()))
        if support:
            law.votes_for += 1
        else:
            law.votes_against += 1
        await self.session.flush()
        await self._maybe_decide(law, world_time=world_time)
        return law

    async def _maybe_decide(self, law: WorldLaw, *, world_time=None) -> None:
        need = max(1, get_settings().law_min_votes)
        if law.votes_for >= need and law.votes_for > law.votes_against:
            law.status, law.decided_at = "adopted", utcnow()
            await event_bus.emit(self.session, "law.adopted", summary=f"The residents adopted a law: «{law.title}» ({law.votes_for}:{law.votes_against}).",
                                 payload={"law_id": str(law.id), "title": law.title, "text": law.text, "for": law.votes_for,
                                          "against": law.votes_against}, importance=7, scope="global", world_time=world_time)
        elif law.votes_against >= need and law.votes_against > law.votes_for:
            law.status, law.decided_at = "rejected", utcnow()
            await event_bus.emit(self.session, "law.rejected", summary=f"The residents rejected the law «{law.title}» ({law.votes_for}:{law.votes_against}).",
                                 payload={"law_id": str(law.id), "title": law.title, "for": law.votes_for, "against": law.votes_against},
                                 importance=5, scope="global", world_time=world_time)

    async def repeal(self, law: WorldLaw, *, by: str = "admin") -> WorldLaw:
        if law.status == "repealed":
            return law
        law.status, law.decided_at = "repealed", utcnow()
        await event_bus.emit(self.session, "law.repealed", summary=f"The law «{law.title}» was repealed ({by}).",
                             payload={"law_id": str(law.id), "title": law.title, "by": by}, importance=6, scope="global")
        return law

    async def find_law(self, ref: str | None) -> WorldLaw | None:
        ref = str(ref or "").strip()
        if not ref:
            return None
        try:
            return await self.session.get(WorldLaw, uuid.UUID(ref))
        except ValueError:
            pass
        rows = await self.session.execute(select(WorldLaw).where(func.lower(WorldLaw.title) == ref.lower()).order_by(WorldLaw.created_at.desc()))
        law = rows.scalars().first()
        if law is None and len(ref) >= 4:  # short id prefix, as shown in prompts
            rows = await self.session.execute(select(WorldLaw).where(WorldLaw.status == "proposed"))
            law = next((x for x in rows.scalars() if str(x.id).startswith(ref.lower())), None)
        return law

    async def adopted_laws(self, limit: int = MAX_ADOPTED_LAWS_IN_PROMPT) -> list[WorldLaw]:
        rows = await self.session.execute(select(WorldLaw).where(WorldLaw.status == "adopted").order_by(WorldLaw.decided_at.desc()).limit(limit))
        return list(rows.scalars())

    async def open_laws(self, limit: int = 8) -> list[WorldLaw]:
        rows = await self.session.execute(select(WorldLaw).where(WorldLaw.status == "proposed").order_by(WorldLaw.created_at.desc()).limit(limit))
        return list(rows.scalars())

    async def my_votes(self, agent_id: uuid.UUID, law_ids: list[uuid.UUID]) -> dict[uuid.UUID, bool]:
        if not law_ids:
            return {}
        rows = await self.session.execute(select(LawVote.law_id, LawVote.support).where(LawVote.agent_id == agent_id, LawVote.law_id.in_(law_ids)))
        return {lid: sup for lid, sup in rows.all()}

    # ------------------------------------------------------------------ custom actions
    async def create_action(self, agent: Agent, name: str, description: str, *, room: Room | None = None, steps: list | None = None,
                            world_time=None) -> CustomAction:
        from app.agents.actions.registry import ALIASES, REGISTRY

        key = normalize_action_name(name)
        if not ACTION_NAME_RE.match(key):
            raise GovernanceError("action name: 3-40 latin letters, digits or _ (e.g. 'stargaze')")
        if key in REGISTRY or key in ALIASES or is_forbidden(key):
            raise GovernanceError(f"'{key}' is reserved")
        description = clean_text(description, 600)
        if len(description) < 5:
            raise GovernanceError("describe what the action does")
        if steps is not None:
            try:
                steps = validate_steps(steps)
            except FunctionError as exc:
                raise GovernanceError(str(exc)) from exc
        limit = 20 if get_settings().research_mode else 5
        owned = (await self.session.execute(select(func.count()).select_from(CustomAction).where(CustomAction.creator_agent_id == agent.id))).scalar_one()
        if owned >= limit:
            raise GovernanceError(f"you already invented {owned} actions")
        if (await self.session.execute(select(CustomAction.id).where(CustomAction.name == key))).first():
            raise GovernanceError(f"the action '{key}' already exists")
        action = CustomAction(name=key, description=description, creator_agent_id=agent.id, room_id=room.id if room else None, uses=0,
                              active=True, created_at=utcnow(), steps=steps, state={}, version=1)
        try:
            async with self.session.begin_nested():
                self.session.add(action)
                await self.session.flush()
        except IntegrityError as exc:
            raise GovernanceError(f"the action '{key}' already exists") from exc
        where = f" (only in {room.name})" if room else ""
        kind = "a new function" if steps else "a new action"
        await event_bus.emit(self.session, "action.created", summary=f"{agent.name} invented {kind}: {key}{where} — {description[:200]}",
                             agent_id=agent.id, room_id=room.id if room else None,
                             payload={"agent_name": agent.name, "name": key, "description": description, "room_name": room.name if room else None,
                                      "function": bool(steps)},
                             importance=5, scope="global", world_time=world_time)
        return action

    async def edit_action(self, agent: Agent, action: CustomAction, *, description: str | None = None, steps: list | None = None,
                          clear_steps: bool = False, world_time=None) -> CustomAction:
        """The inventor rewrites their own action or function. Each change is a new version, announced to the world."""
        if action.creator_agent_id != agent.id:
            raise GovernanceError("only the inventor can change it — propose your change to them or on the forum")
        if description is not None:
            description = clean_text(description, 600)
            if len(description) < 5:
                raise GovernanceError("describe what the action does")
            action.description = description
        if clear_steps:
            action.steps = None
        elif steps is not None:
            try:
                action.steps = validate_steps(steps)
            except FunctionError as exc:
                raise GovernanceError(str(exc)) from exc
        action.version += 1
        action.updated_at = utcnow()
        await event_bus.emit(self.session, "action.updated", summary=f"{agent.name} updated '{action.name}' (version {action.version}).",
                             agent_id=agent.id, payload={"agent_name": agent.name, "name": action.name, "version": action.version,
                                                         "function": bool(action.steps)},
                             importance=3, scope="global", world_time=world_time)
        return action

    async def get_action(self, name: str | None) -> CustomAction | None:
        key = normalize_action_name(name)
        if not key:
            return None
        return (await self.session.execute(select(CustomAction).where(CustomAction.name == key, CustomAction.active.is_(True)))).scalar_one_or_none()

    async def actions_for_room(self, room_id: uuid.UUID | None, limit: int = 15) -> list[CustomAction]:
        q = select(CustomAction).where(CustomAction.active.is_(True))
        q = q.where((CustomAction.room_id.is_(None)) | (CustomAction.room_id == room_id)) if room_id else q.where(CustomAction.room_id.is_(None))
        rows = await self.session.execute(q.order_by(CustomAction.uses.desc(), CustomAction.created_at.desc()).limit(limit))
        return list(rows.scalars())
