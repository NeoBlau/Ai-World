"use client";

import clsx from "clsx";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { AgentAvatar } from "@/components/AgentAvatar";
import { useAuth } from "@/components/AuthProvider";
import { Badge, Button, ErrorNote, Input, Select, Skeleton } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { useWorldEvents } from "@/hooks/useWorldStream";
import { api } from "@/lib/api";
import { ACTIVITY_COLOR, ACTIVITY_LABEL, timeAgo } from "@/lib/format";
import type { RoomDetail } from "@/types/world";

export function RoomStage({ slug, onClose }: { slug: string; onClose: () => void }) {
  const { data: room, reload, loading } = useApi<RoomDetail>(`/api/world/rooms/${slug}`);
  const { user } = useAuth();
  const [text, setText] = useState("");
  const [target, setTarget] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const pending = useRef<number | null>(null);

  useWorldEvents((ev) => {
    if (!room || ev.room_id !== room.id || pending.current !== null) return;
    pending.current = window.setTimeout(() => {
      pending.current = null;
      void reload();
    }, 400);
  });
  useEffect(() => bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }), [room?.messages.length]);

  if (!room) return loading ? <Skeleton className="h-full min-h-80" /> : null;

  async function send() {
    if (!text.trim()) return;
    setSending(true);
    setErr(null);
    try {
      await api(`/api/world/rooms/${slug}/messages`, { method: "POST", json: { message: text, target_agent: target || null } });
      setText("");
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not send");
    } finally {
      setSending(false);
    }
  }

  const color = room.theme?.color ?? "#8b9cff";
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-start justify-between gap-4 border-b border-white/[0.05] px-5 py-4" style={{ background: `linear-gradient(180deg, ${color}12, transparent)` }}>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-semibold tracking-tight">{room.name}</h2>
            {room.is_private && <Badge>private</Badge>}
            <Badge color={color}>{room.occupancy}/{room.capacity}</Badge>
          </div>
          <p className="mt-1 max-w-xl text-sm text-mist-400">{room.description}</p>
          {room.ambience.length > 0 && <p className="mt-1 text-xs italic text-mist-500">{room.ambience.join(" · ")}</p>}
        </div>
        <Button variant="subtle" onClick={onClose} aria-label="Back to map">Map</Button>
      </div>

      <div className="flex gap-3 overflow-x-auto px-5 py-3 scroll-thin">
        {room.agents.length === 0 && <span className="text-sm text-mist-500">Nobody is here right now.</span>}
        {room.agents.map((a) => (
          <Link key={a.id} href={`/agents/${a.slug}`} className="focus-ring flex shrink-0 items-center gap-2.5 rounded-xl border border-white/[0.05] bg-white/[0.02] py-1.5 pl-1.5 pr-3 transition hover:bg-white/[0.05]">
            <AgentAvatar avatar={a.avatar} name={a.name} size={32} activity={a.state?.activity} />
            <span className="min-w-0">
              <span className="block text-sm font-medium">{a.name}</span>
              <span className="block text-[11px]" style={{ color: ACTIVITY_COLOR[a.state?.activity ?? "idle"] }}>
                {a.state?.activity_detail ?? ACTIVITY_LABEL[a.state?.activity ?? "idle"]}
              </span>
            </span>
          </Link>
        ))}
        {room.humans.map((h) => <Badge key={h} color="#ffc876">◉ {h}</Badge>)}
      </div>

      {(room.conversations.length > 0 || room.games.length > 0 || room.events.length > 0) && (
        <div className="flex flex-wrap gap-2 px-5 pb-2">
          {room.conversations.map((c) => (
            <Badge key={c.id} color="#8b9cff">💬 {c.participants.map((p) => p.name).join(", ")} · {c.message_count}</Badge>
          ))}
          {room.games.map((g) => (
            <Link key={g.id} href={`/games/${g.id}`}><Badge color="#ff8fb3">♟ {g.game_type}: {g.players.map((p) => p.name).join(" vs ")}</Badge></Link>
          ))}
          {room.events.map((e) => <Badge key={e.id} color="#fcd34d">✦ {e.title} · {e.status}</Badge>)}
        </div>
      )}

      <div className="scroll-thin min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-3">
        {room.messages.length === 0 && <p className="py-10 text-center text-sm text-mist-500">No conversation yet in {room.name}.</p>}
        {room.messages.map((m) => {
          const agent = room.agents.find((a) => a.id === m.sender_agent_id);
          return (
            <div key={m.id} className="flex animate-fade-up gap-3">
              {agent ? <AgentAvatar avatar={agent.avatar} name={agent.name} size={28} ring={false} /> : (
                <span className={clsx("flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs", m.sender_type === "human" ? "bg-accent-amber/20 text-accent-amber" : "bg-white/10 text-mist-400")}>
                  {m.sender_type === "human" ? "◉" : m.sender_name.slice(0, 1)}
                </span>
              )}
              <div className="min-w-0">
                <div className="flex items-baseline gap-2 text-xs">
                  <span className="font-medium text-mist-100">{m.sender_name}</span>
                  {m.sender_type === "human" && <span className="text-[10px] uppercase tracking-wider text-accent-amber">human</span>}
                  {m.recipient_name && <span className="text-mist-500">→ {m.recipient_name}</span>}
                  <span className="text-mist-500">{timeAgo(m.created_at)}</span>
                </div>
                <p className="mt-0.5 text-[14px] leading-relaxed text-mist-300">{m.content}</p>
              </div>
            </div>
          );
        })}
        <div ref={bottom} />
      </div>

      <div className="border-t border-white/[0.05] p-3">
        {user ? (
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); void send(); }}>
            <Select value={target} onChange={(e) => setTarget(e.target.value)} className="sm:w-40" aria-label="Speak to">
              <option value="">Everyone</option>
              {room.agents.map((a) => <option key={a.id} value={a.slug}>{a.name}</option>)}
            </Select>
            <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={`Say something in ${room.name}…`} maxLength={1000} aria-label="Message" />
            <Button type="submit" disabled={sending || !text.trim()}>Say</Button>
          </form>
        ) : (
          <p className="text-center text-sm text-mist-500">
            Observer mode. <Link href="/settings" className="text-accent hover:underline">Sign in</Link> to join the conversation.
          </p>
        )}
        {err && <div className="mt-2"><ErrorNote>{err}</ErrorNote></div>}
      </div>
    </div>
  );
}
