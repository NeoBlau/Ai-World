"use client";

import clsx from "clsx";
import Link from "next/link";
import { useEffect, useState } from "react";

import { eventGlyph, timeAgo } from "@/lib/format";
import type { AgentSummary, WorldEvent } from "@/types/world";

// Individual moves live on the game page; the feed shows starts and results.
const HIDDEN = new Set(["agent.thinking", "game.move", "agent.voted_topic", "agent.saved_topic"]);

export function FeedItem({ ev, agents, now }: { ev: WorldEvent; agents: Map<string, AgentSummary>; now: number }) {
  const agent = ev.agent_id ? agents.get(ev.agent_id) : undefined;
  const isSpeech = ev.type === "message.created" || ev.type === "human.message";
  const content = typeof ev.payload?.content === "string" ? (ev.payload.content as string) : null;
  const speaker = agent?.name ?? (typeof ev.payload?.user_name === "string" ? (ev.payload.user_name as string) : "");
  return (
    <li className="group animate-fade-up rounded-xl px-3 py-2.5 transition hover:bg-white/[0.03]">
      <div className="flex items-start gap-2.5">
        <span className={clsx("mt-0.5 w-4 shrink-0 text-center text-xs", ev.importance >= 4 ? "text-accent" : "text-mist-500")} aria-hidden>
          {eventGlyph(ev.type)}
        </span>
        <div className="min-w-0 flex-1">
          {isSpeech && content ? (
            <p className="text-[13px] leading-relaxed text-mist-300">
              {agent ? (
                <Link href={`/agents/${agent.slug}`} className="font-medium text-mist-100 hover:underline">{speaker}</Link>
              ) : (
                <span className="font-medium text-accent-amber">{speaker} <span className="text-[10px] uppercase text-mist-500">human</span></span>
              )}
              {typeof ev.payload?.target_name === "string" && <span className="text-mist-500"> → {String(ev.payload.target_name)}</span>}
              <span className="text-mist-500">: </span>
              <span className="text-mist-100/90">“{content}”</span>
            </p>
          ) : (
            <p className="text-[13px] leading-relaxed text-mist-300">{ev.summary}</p>
          )}
          <p className="mt-0.5 text-[11px] text-mist-500">
            {timeAgo(ev.created_at, now)}
            {typeof ev.payload?.room_name === "string" && <> · {String(ev.payload.room_name)}</>}
          </p>
        </div>
      </div>
    </li>
  );
}

export function ActivityFeed({ feed, agents, roomId, className }: { feed: WorldEvent[]; agents: AgentSummary[]; roomId?: string; className?: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 10_000);
    return () => window.clearInterval(id);
  }, []);
  const map = new Map(agents.map((a) => [a.id, a]));
  const items = (roomId ? feed.filter((e) => e.room_id === roomId) : feed).filter((e) => !HIDDEN.has(e.type)).slice(0, 80);
  return (
    <ul className={clsx("scroll-thin space-y-0.5 overflow-y-auto", className)} aria-live="polite" aria-label="Activity feed">
      {items.length === 0 && <li className="px-3 py-8 text-center text-sm text-mist-500">Quiet for now. Things will happen soon.</li>}
      {items.map((ev) => (
        <FeedItem key={ev.id} ev={ev} agents={map} now={now} />
      ))}
    </ul>
  );
}
