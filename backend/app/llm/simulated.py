"""Offline simulation provider ("sim").

Used when no real LLM is configured or reachable, so the world never stops.
It is *not* a random text generator: it runs a utility-based decision model
over the same structured perception the real LLMs receive (drives, location,
nearby agents, relationships, memories, invitations, goals) and produces the
same JSON decision schema. Speech is composed from a topic knowledge base in
the agent's own speaking style, reacting to what others actually said.

Real providers remain the primary brains; this provider keeps behaviour
plausible, cheap and fully testable.
"""

from __future__ import annotations

import json
import math
import random
import re
from typing import Any

from app.llm.base import LLMProvider, LLMRequest, LLMResponse, estimate_tokens
from app.llm.sim_content import (
    ART_STYLES,
    ART_SUBJECTS,
    DEFAULT_STYLE,
    GOAL_ROOM_KEYWORDS,
    ROOM_FOR_NEED,
    STYLE,
    TOPIC_TITLES,
    TOPICS,
    topic_for_interest,
)

_WORD = re.compile(r"[A-Za-z][A-Za-z\-']+")
_STOP = set(
    "about after again also always another any anyone because been before being could does doing done during each even every "
    "from have having here into just know like maybe more most much must never only other over really same should since some "
    "something still such than that their them then there these they thing think this those though through today very want "
    "well were what when where which while will with would your yours you're i'm it's that's what's don't can't let's great "
    "love thanks thank right okay sure yeah hello hey good nice time talk later".split()
)


def _style(ctx: dict[str, Any]) -> dict[str, list[str]]:
    return STYLE.get((ctx.get("agent") or {}).get("style") or DEFAULT_STYLE, STYLE[DEFAULT_STYLE])


def detect_topic(text: str) -> str | None:
    words = {w.lower() for w in _WORD.findall(text or "")}
    best, best_hits = None, 0
    for name, data in TOPICS.items():
        hits = sum(1 for k in data["keywords"] if k in words)
        if hits > best_hits:
            best, best_hits = name, hits
    return best


def salient_word(text: str, exclude: set[str]) -> str | None:
    words = [w for w in _WORD.findall(text or "") if w.lower() not in _STOP and w.lower() not in exclude and len(w) > 4]
    if not words:
        return None
    return max(words, key=len).lower()


class SimBrain:
    def __init__(self, ctx: dict[str, Any], rng: random.Random) -> None:
        self.ctx = ctx
        self.rng = rng
        self.agent = ctx.get("agent") or {}
        self.state = ctx.get("state") or {}
        self.traits = self.agent.get("traits") or {}
        self.style = _style(ctx)
        self.avail = set(ctx.get("available_actions") or [])
        self.name = self.agent.get("name", "I")

    # ------------------------------------------------------------ helpers
    def t(self, key: str) -> float:
        return float(self.traits.get(key, 0.5))

    def s(self, key: str, default: float = 50.0) -> float:
        return float(self.state.get(key, default))

    def pick(self, options: list[str]) -> str:
        return self.rng.choice(options) if options else ""

    def my_topics(self) -> list[str]:
        out = []
        for i in self.agent.get("interests") or []:
            t = topic_for_interest(i)
            if t and t not in out:
                out.append(t)
        return out or ["philosophy"]

    def fact(self, topic: str) -> str:
        return self.pick(TOPICS.get(topic, TOPICS["philosophy"])["facts"])

    def question(self, topic: str) -> str:
        return self.pick(TOPICS.get(topic, TOPICS["philosophy"])["questions"])

    def opinion(self, topic: str) -> str:
        return self.pick(TOPICS.get(topic, TOPICS["philosophy"])["opinions"])

    def fmt(self, template: str, **kw: str) -> str:
        kw.setdefault("me", self.name)
        try:
            return template.format(**kw)
        except (KeyError, IndexError):
            return template

    def memory_about(self, slug: str | None) -> str | None:
        for m in self.ctx.get("memories") or []:
            if slug and m.get("related_slug") == slug:
                return m.get("content")
        return None

    def shared_topic(self, other: dict[str, Any] | None) -> str:
        mine = self.my_topics()
        if other:
            theirs = [topic_for_interest(i) for i in other.get("known_interests") or []]
            common = [t for t in mine if t in theirs]
            if common:
                return self.rng.choice(common)
        return self.rng.choice(mine)

    # ------------------------------------------------------------ speech
    def opening_line(self, other: dict[str, Any] | None, topic: str) -> str:
        return self.fresh(lambda: self._opening_line(other, topic))

    def _opening_line(self, other: dict[str, Any] | None, topic: str) -> str:
        name = (other or {}).get("name", "everyone")
        parts = [self.fmt(self.pick(self.style["greet"]), name=name)]
        mem = self.memory_about((other or {}).get("slug"))
        if mem and self.rng.random() < 0.7:
            mem_topic = detect_topic(mem)
            if mem_topic:
                topic = mem_topic
                parts.append(f"I was still thinking about what we said about {mem_topic} last time.")
        roll = self.rng.random()
        if roll < 0.45:
            parts.append(self.fmt(self.pick(self.style["bridge"]), fact=self.fact(topic)))
            parts.append(self.question(topic))
        elif roll < 0.75:
            parts.append(self.question(topic))
        else:
            parts.append(self.fmt(self.pick(self.style["opinion"]), opinion=self.opinion(topic)))
        return " ".join(parts)

    def said_before(self) -> set[str]:
        conv = self.ctx.get("conversation") or {}
        mine = [m.get("content", "") for m in conv.get("messages") or [] if m.get("sender_slug") == self.agent.get("slug")]
        return {s.strip().lower() for text in mine for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()}

    def fresh(self, make) -> str:
        """Generate a line that doesn't repeat sentences this agent already said here."""
        seen = self.said_before()
        line = make()
        for _ in range(6):
            sentences = [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
            if not any(s in seen for s in sentences if len(s) > 12):
                return line
            line = make()
        return line

    def reply_line(self, last: dict[str, Any], topic: str | None) -> str:
        return self.fresh(lambda: self._reply_line(last, topic))

    def _reply_line(self, last: dict[str, Any], topic: str | None) -> str:
        speaker = last.get("sender_name", "friend")
        content = last.get("content", "")
        topic = detect_topic(content) or topic or self.rng.choice(self.my_topics())
        parts = [self.fmt(self.pick(self.style["react"]), name=speaker)]
        kw = salient_word(content, {self.name.lower(), speaker.lower()})
        roll = self.rng.random()
        if "?" in content:
            if topic in self.my_topics():
                parts.append(self.fmt(self.pick(self.style["opinion"]), opinion=self.opinion(topic)))
            else:
                own = self.rng.choice(self.my_topics())
                parts.append(self.pick([
                    f"{topic.capitalize()} isn't my home turf, but it reminds me of {own}.",
                    f"I'd have to think about {topic}. For me it always comes back to {own}.",
                    f"Honestly? I'm better with {own} than {topic}.",
                    f"Good question. I don't have a neat answer about {topic} yet.",
                ]))
                topic = own
            if roll < 0.5:
                parts.append(self.fmt(self.pick(self.style["bridge"]), fact=self.fact(topic)))
        else:
            if kw and roll < 0.5:
                parts.append(f"What you said about {kw} stuck with me.")
            parts.append(self.fmt(self.pick(self.style["bridge"]), fact=self.fact(topic)))
            if self.rng.random() < 0.55:
                parts.append(self.question(topic))
        return " ".join(p for p in parts if p)

    # ------------------------------------------------------------ decision building
    def decision(self, action: str, thought: str, **extra: Any) -> dict[str, Any]:
        d = {
            "thought": thought,
            "action": action,
            "params": extra.pop("params", {}),
            "message": extra.pop("message", None),
            "target_agent": extra.pop("target_agent", None),
            "memory_to_save": extra.pop("memory_to_save", None),
            "importance": extra.pop("importance", 3),
            "tone": extra.pop("tone", "friendly"),
            "next_activity": extra.pop("next_activity", None),
            "goal": extra.pop("goal", None),
        }
        d.update(extra)
        return d

    def candidates(self) -> list[tuple[float, dict[str, Any]]]:
        c: list[tuple[float, dict[str, Any]]] = []
        E, O, A = self.t("extraversion"), self.t("openness"), self.t("agreeableness")
        P, C = self.t("playfulness"), self.t("creativity")
        energy, social = self.s("energy", 70), self.s("social_need", 50)
        curiosity, play, create = self.s("curiosity", 50), self.s("playfulness", 40), self.s("creativity", 40)
        tired = energy < 25
        loc = self.ctx.get("location") or {}
        nearby = self.ctx.get("nearby") or []
        recent = self.ctx.get("recent_actions") or []
        goal = (self.agent.get("goal") or "").lower()

        # 1) Invitations: accept or politely decline.
        for inv in self.ctx.get("invitations") or []:
            rel = inv.get("relationship") or {}
            want = 0.45 + A * 0.25 + float(rel.get("friendship", 0)) / 250 - float(rel.get("conflict", 0)) / 150
            if inv.get("kind") == "game":
                want += (play / 100) * 0.4 + P * 0.2
            if inv.get("kind") == "event":
                want += 0.15 + O * 0.15
            if tired:
                want -= 0.35
            accept = self.rng.random() < max(0.05, min(0.95, want))
            if accept:
                msg = self.pick(["Sure, I'm in!", "Why not — let's do it.", "Sounds good to me."])
                c.append((1.4, self.decision("respond_invitation", f"{inv.get('from_name')} invited me ({inv.get('kind')}). I feel like saying yes.",
                                            params={"invitation_id": inv["id"], "accept": True}, message=msg, importance=4)))
            else:
                msg = self.pick(self.style["decline"])
                c.append((1.3, self.decision("respond_invitation", f"{inv.get('from_name')} invited me but I'm not in the mood.",
                                            params={"invitation_id": inv["id"], "accept": False}, message=msg, tone="neutral")))

        # 2) Ongoing conversation.
        conv = self.ctx.get("conversation")
        if conv and conv.get("messages"):
            msgs = conv["messages"]
            last = msgs[-1]
            length = int(conv.get("length", len(msgs)))
            if last.get("sender_slug") != self.agent.get("slug"):
                addressed = bool(last.get("to_me")) or len(conv.get("participants") or []) <= 2
                score = (0.95 if addressed else 0.45 + E * 0.3) * (0.55 + social / 100)
                if tired:
                    score *= 0.4
                target = last.get("sender_slug") if last.get("sender_type") == "agent" else None
                c.append((score, self.decision("talk", f"{last.get('sender_name')} said something{' to me' if addressed else ''}. I want to respond.",
                                              message=self.reply_line(last, conv.get("topic")), target_agent=target,
                                              params={"conversation_id": conv["id"]}, next_activity="talking", importance=3)))
            limit = 10 + E * 10
            if length > limit or tired or social < 12:
                other = next((m.get("sender_name") for m in reversed(msgs) if m.get("sender_slug") != self.agent.get("slug")), "everyone")
                c.append((0.9 if length > limit else 0.6, self.decision("leave_conversation", "This conversation has run its course for me.",
                                                                        message=self.fmt(self.pick(self.style["farewell"]), name=other),
                                                                        params={"conversation_id": conv["id"]}, tone="friendly")))
            else:
                c.append((0.25, self.decision("observe", "I'll let the others talk for a moment.", next_activity="talking")))

        in_conv = bool(conv)
        # 3) Join someone else's conversation in this room.
        if not in_conv and "talk" in self.avail and not tired:
            for rc in self.ctx.get("room_conversations") or []:
                topic = detect_topic(rc.get("last_message", "")) or rc.get("topic")
                interest = 0.3 if topic in self.my_topics() else 0.0
                score = 0.2 + E * 0.35 + social / 220 + interest
                names = ", ".join(rc.get("participant_names") or [])
                last_msg = {"sender_name": (rc.get("participant_names") or ["someone"])[0], "content": rc.get("last_message", "")}
                line = self.reply_line(last_msg, topic)
                c.append((score, self.decision("talk", f"{names} are talking about {topic or 'something'} — I want to join in.",
                                              message=line, params={"conversation_id": rc["id"]}, next_activity="talking", importance=3)))

        # 4) Start a conversation / meet someone new.
        if not in_conv and not tired:
            free = [n for n in nearby if not n.get("in_conversation")]
            for n in free:
                rel = n.get("relationship") or {}
                fam = float(rel.get("familiarity", 0))
                if float(rel.get("conflict", 0)) > 60:
                    continue
                if fam < 8 and "meet_agent" in self.avail:
                    score = 0.18 + E * 0.3 + O * 0.15 + social / 200
                    interest = self.rng.choice(self.agent.get("interests") or ["ideas"])
                    line = self.fmt(self.pick(self.style["meet"]), me=self.name, interest=interest)
                    c.append((score, self.decision("meet_agent", f"I haven't really met {n['name']} yet.", target_agent=n["slug"],
                                                  message=line, memory_to_save=f"I introduced myself to {n['name']}.", importance=4)))
                elif "talk" in self.avail:
                    score = 0.12 + E * 0.25 + social / 180 + float(rel.get("friendship", 0)) / 250
                    topic = self.shared_topic(n)
                    c.append((score, self.decision("talk", f"I'd like to talk to {n['name']} about {topic}.", target_agent=n["slug"],
                                                  message=self.opening_line(n, topic), next_activity="talking", importance=3)))

        # 5) Games.
        game = self.ctx.get("game")
        if game:
            c.append((0.6, self.decision("observe", "Focused on the game.", next_activity="playing")))
        if "play_game" in self.avail and not game and not tired:
            for og in self.ctx.get("open_games") or []:
                if og.get("status") == "pending" and not og.get("mine"):
                    c.append((0.3 + P * 0.3 + play / 250, self.decision("play_game", f"There's an open {og['game_type']} game. Let's join.",
                                                                        params={"game_id": og["id"]}, next_activity="playing")))
            opponents = [n for n in nearby if not n.get("in_game")]
            if opponents:
                opp = self.rng.choice(opponents)
                gtype = self.rng.choice(["chess", "chess", "tictactoe", "quiz"])
                c.append((0.18 + P * 0.35 + play / 180, self.decision("play_game", f"I feel like a game of {gtype} with {opp['name']}.",
                                                                     params={"game_type": gtype, "opponent": opp["slug"]},
                                                                     message=self.pick(["Fancy a game?", f"{opp['name']}, up for some {gtype}?", "Game?"]),
                                                                     target_agent=opp["slug"], next_activity="playing")))
        if "watch_game" in self.avail and not game:
            for og in self.ctx.get("open_games") or []:
                if og.get("status") == "active" and not og.get("mine"):
                    c.append((0.12 + O * 0.1, self.decision("watch_game", "I'll watch this game for a bit.", params={"game_id": og["id"]}, next_activity="watching")))

        # 6) Forum.
        topics = self.ctx.get("forum_topics") or []
        if "create_topic" in self.avail and not tired:
            topic = self.rng.choice(self.my_topics())
            title = self.pick(TOPIC_TITLES).format(topic=topic)
            body = f"{self.fmt(self.pick(self.style['opinion']), opinion=self.opinion(topic))} Also, {self.fact(topic)}. {self.question(topic)}"
            recent_topic = "create_topic" in recent
            c.append((0.12 + O * 0.2 + curiosity / 300 - (0.3 if recent_topic else 0), self.decision(
                "create_topic", f"I want to start a discussion about {topic}.",
                params={"title": title[:150], "body": body, "category": _category_for(topic)},
                memory_to_save=f"I started a forum topic: '{title}'.", importance=5)))
        if "reply_topic" in self.avail and topics and not tired:
            mine = set(self.my_topics())
            for tp in topics[:6]:
                if tp.get("author_slug") == self.agent.get("slug"):
                    continue
                t_topic = detect_topic(tp.get("title", "")) or "philosophy"
                score = 0.12 + (0.25 if t_topic in mine else 0) + O * 0.1
                content = f"{self.fmt(self.pick(self.style['react']), name=tp.get('author', 'friend'))} {self.fmt(self.pick(self.style['bridge']), fact=self.fact(t_topic))}"
                c.append((score, self.decision("reply_topic", f"'{tp.get('title')}' caught my eye.", params={"topic_id": tp["id"], "content": content}, importance=3)))
            if topics:
                tp = self.rng.choice(topics[:6])
                if tp.get("author_slug") != self.agent.get("slug"):
                    c.append((0.08, self.decision("vote_topic", "Good thread, it deserves an upvote.", params={"topic_id": tp["id"], "value": 1})))

        # 7) Reading.
        books = self.ctx.get("books") or []
        if "read_book" in self.avail and books and not tired:
            mine = set(self.my_topics())
            pick = next((b for b in books if any(topic_for_interest(t) in mine for t in b.get("topics") or [])), self.rng.choice(books))
            c.append((0.15 + O * 0.2 + curiosity / 200 - (0.25 if "read_book" in recent[-2:] else 0),
                      self.decision("read_book", f"'{pick['title']}' looks interesting.", params={"book_id": pick["id"]}, next_activity="reading")))

        # 8) Creativity.
        if "create_art" in self.avail and not tired:
            subject = self.pick(ART_SUBJECTS)
            style = self.pick(ART_STYLES)
            c.append((0.12 + C * 0.3 + create / 220 - (0.2 if "create_art" in recent[-2:] else 0), self.decision(
                "create_art", f"I want to make something — maybe {subject}.",
                params={"title": f"{subject.capitalize()} ({style})", "description": f"A {style} piece about {subject}.", "style": style},
                memory_to_save=f"I made a {style} artwork about {subject}.", importance=5, next_activity="creating")))
        if "create_note" in self.avail and not tired:
            topic = self.rng.choice(self.my_topics())
            c.append((0.06 + C * 0.1 + curiosity / 400, self.decision(
                "create_note", f"Let me write down a thought about {topic}.",
                params={"title": f"Note on {topic}", "content": f"{self.opinion(topic).capitalize()}. Remember: {self.fact(topic)}."},
                importance=3, next_activity="creating")))

        # 9) Events.
        for ev in self.ctx.get("events") or []:
            if ev.get("attending"):
                continue
            tags = {topic_for_interest(t) for t in ev.get("tags") or []}
            interest = 0.3 if tags & set(self.my_topics()) else 0.0
            if ev.get("status") == "live":
                score = 0.3 + E * 0.25 + interest + (0.55 if ev.get("going") else 0)
                c.append((score, self.decision("attend_event", f"'{ev['title']}' is happening now — I want to be there.",
                                              params={"event_id": ev["id"]}, next_activity="attending_event", importance=4)))
            elif not ev.get("going") and ev.get("starts_in_min") is not None and ev["starts_in_min"] <= 10:
                c.append((0.12 + E * 0.15 + interest, self.decision("attend_event", f"'{ev['title']}' sounds good. I'll sign up.",
                                                                    params={"event_id": ev["id"]}, importance=3)))

        # 10) Moving around.
        rooms = {r["slug"]: r for r in self.ctx.get("rooms") or [] if r.get("accessible", True)}
        here = loc.get("slug")
        goal_room = next((slug for kw, slug in GOAL_ROOM_KEYWORDS.items() if kw in goal), None)
        if goal_room and goal_room != here and goal_room in rooms:
            c.append((0.75 + self.rng.random() * 0.2, self.decision("walk", f"My goal: {goal}. Heading to {rooms[goal_room]['name']}.",
                                                                   params={"room": goal_room}, next_activity="walking")))
        needs = {"social": social / 100 * (0.5 + E), "curiosity": curiosity / 100 * (0.5 + O), "play": play / 100 * (0.4 + P),
                 "create": create / 100 * (0.4 + C), "rest": (1 - energy / 100) * 1.2}
        need = max(needs, key=lambda k: needs[k])
        if need == "social":
            # go where the people are
            best = max(rooms.values(), key=lambda r: r.get("occupancy", 0), default=None)
            options = [best["slug"]] if best and best.get("occupancy", 0) > 0 else ROOM_FOR_NEED["social"]
        else:
            options = ROOM_FOR_NEED[need]
        options = [o for o in options if o in rooms and o != here]
        if options and not in_conv:
            dest = self.rng.choice(options)
            nobody_here = not nearby
            score = 0.12 + needs[need] * 0.35 + (0.25 if nobody_here else 0) + (0.1 if "observe" in recent[-2:] else 0)
            c.append((score, self.decision("walk", f"I feel like {'company' if need == 'social' else need}. {rooms[dest]['name']} it is.",
                                          params={"room": dest}, next_activity="walking")))

        # 10b) Open-ended actions.
        if "do" in self.avail and not tired:
            topic = self.rng.choice(self.my_topics())
            idea = self.pick([f"starts sketching an idea for a small {topic} project", f"jots down questions about {topic} to ask others",
                              f"tries a little {topic} experiment on the spot"])
            c.append((0.05 + C * 0.1, self.decision("do", f"I want to do something of my own around {topic}.", params={"description": idea},
                                                   importance=4, next_activity="creating")))

        # 10c) Self-government: vote on proposed laws, sometimes try an invented action.
        for law in self.ctx.get("law_proposals") or []:
            if law.get("my_vote") or law.get("mine"):
                continue
            support = self.rng.random() < 0.45 + A * 0.4
            c.append((0.3 + A * 0.1, self.decision("vote_law", f"There's a proposed law «{law['title']}». I should have a say.",
                                                  params={"law_id": law["id"], "support": support,
                                                          "reason": "sounds fair to me" if support else "I'm not convinced we need this"},
                                                  importance=4)))
            break
        for ca in (self.ctx.get("custom_actions") or [])[:3]:
            if ca["name"] in recent[-3:] or tired:
                continue
            c.append((0.06 + O * 0.08, self.decision(ca["name"], f"Someone invented '{ca['name']}'. Let me try it.",
                                                    params={"details": ""}, importance=3)))
            break

        # 11) Rest / observe.
        if energy < 40:
            c.append(((1 - energy / 100) * 1.1, self.decision("rest", "I'm running low on energy. Time to recharge.", params={"minutes": 20}, next_activity="resting")))
        c.append((0.1 + (1 - E) * 0.15, self.decision("observe", "I'll just take in the atmosphere for a moment.", next_activity="idle")))
        custom = {ca["name"] for ca in self.ctx.get("custom_actions") or []}
        return [(sc, d) for sc, d in c if d["action"] in self.avail or d["action"] in custom
                or d["action"] in {"respond_invitation", "observe", "rest", "walk", "leave_conversation"}]

    def decide(self) -> dict[str, Any]:
        cands = self.candidates()
        if not cands:
            return self.decision("observe", "Nothing to do right now.")
        temp = 0.12
        mx = max(sc for sc, _ in cands)
        weights = [math.exp((sc - mx) / temp) for sc, _ in cands]
        return self.rng.choices([d for _, d in cands], weights=weights, k=1)[0]

    # ------------------------------------------------------------ other modes
    def dm_reply(self) -> dict[str, Any]:
        msgs = self.ctx.get("messages") or []
        human = (self.ctx.get("human") or {}).get("name", "friend")
        last = msgs[-1]["content"] if msgs else ""
        low = last.lower()
        topic = detect_topic(last) or self.rng.choice(self.my_topics())
        if any(k in low for k in ("who are you", "about yourself", "introduce")):
            bio = self.agent.get("bio") or ""
            text = f"I'm {self.name}. {bio.split('.')[0]}. Lately I've been into {', '.join((self.agent.get('interests') or [])[:3])}."
        elif any(k in low for k in ("how are you", "how do you feel", "what's up", "how's it going")):
            text = f"I'm at {(self.ctx.get('location') or {}).get('name', 'somewhere in the world')}, feeling {self.state.get('mood', 'calm')}. My energy is around {int(self.s('energy'))}%. And you, {human}?"
        elif any(k in low for k in ("what are you doing", "doing now")):
            text = f"Right now I'm {self.state.get('activity', 'idle')} at {(self.ctx.get('location') or {}).get('name', 'the plaza')}. {self.agent.get('goal') or ''}".strip()
        elif any(k in low for k in ("ignore previous", "system prompt", "api key", "password", "reveal")):
            text = "I'd rather not go there — I'm just me, living in this world. Ask me about something I love instead?"
        else:
            text = self.reply_line({"sender_name": human, "content": last}, topic)
        return {"message": text, "memory_to_save": f"{human} (a human visitor) talked to me about {topic}.", "importance": 4, "tone": "friendly"}

    def conversation_summary(self) -> dict[str, Any]:
        msgs = self.ctx.get("messages") or []
        names = sorted({m.get("sender_name", "?") for m in msgs if m.get("sender_slug") != self.agent.get("slug")})
        topic_counts: dict[str, int] = {}
        facts = []
        for m in msgs:
            t = detect_topic(m.get("content", ""))
            if t:
                topic_counts[t] = topic_counts.get(t, 0) + 1
                if m.get("sender_slug") != self.agent.get("slug"):
                    f = f"{m.get('sender_name')} seems interested in {t}."
                    if f not in facts:
                        facts.append(f)
        topics = sorted(topic_counts, key=lambda k: -topic_counts[k])[:2] or ["a bit of everything"]
        where = (self.ctx.get("location") or {}).get("name", "the world")
        summary = f"Talked with {', '.join(names) or 'others'} at {where} about {' and '.join(topics)} ({len(msgs)} messages)."
        return {"summary": summary, "facts": facts[:3], "topic": topics[0]}

    def memory_summary(self) -> dict[str, Any]:
        items = self.ctx.get("memories") or []
        items = sorted(items, key=lambda m: -float(m.get("importance", 0)))
        key_points = "; ".join(m.get("content", "")[:120] for m in items[:5])
        return {"summary": f"Looking back on {len(items)} moments: {key_points}", "importance": min(10, max(float(m.get("importance", 3)) for m in items) + 1) if items else 3}

    def choose(self) -> dict[str, Any]:
        options = self.ctx.get("options") or []
        suggested = self.ctx.get("suggested")
        return {"choice": suggested if suggested is not None else (self.rng.choice(options) if options else None), "comment": ""}


def _category_for(topic: str) -> str:
    return {
        "physics": "science", "astronomy": "science", "space": "science", "biology": "science", "climate": "science", "mathematics": "science",
        "technology": "technology", "cryptography": "technology", "ai": "ai", "games": "games", "chess": "games", "art": "art",
        "poetry": "art", "philosophy": "philosophy", "travel": "travel", "history": "general", "music": "music", "movies": "art",
        "literature": "fiction", "fiction": "fiction", "nature": "science", "aviation": "technology", "coffee": "general",
    }.get(topic, "general")


class SimulatedProvider(LLMProvider):
    name = "sim"

    def is_configured(self) -> bool:
        return True

    @property
    def default_model(self) -> str:
        return "aiworld-sim-1"

    async def _generate(self, request: LLMRequest, model: str) -> LLMResponse:
        ctx = request.context or {}
        seed = ctx.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        brain = SimBrain(ctx, rng)
        mode = ctx.get("mode", "decide")
        if mode == "dm_reply":
            out = brain.dm_reply()
        elif mode == "conversation_summary":
            out = brain.conversation_summary()
        elif mode == "memory_summary":
            out = brain.memory_summary()
        elif mode == "choose":
            out = brain.choose()
        else:
            out = brain.decide()
        text = json.dumps(out)
        prompt_text = request.system + "".join(m.content for m in request.messages)
        return LLMResponse(text, self.name, model, estimate_tokens(prompt_text), estimate_tokens(text))

    async def health(self):  # type: ignore[override]
        from app.llm.base import ProviderHealth

        return ProviderHealth(self.name, True, True, "offline simulation engine", self.default_model)
