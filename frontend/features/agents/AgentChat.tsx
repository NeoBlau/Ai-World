"use client";

import clsx from "clsx";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { AgentAvatar } from "@/components/AgentAvatar";
import { useAuth } from "@/components/AuthProvider";
import { Button, ErrorNote, Input } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import type { AgentDetail, ChatMessage } from "@/types/world";

export function AgentChat({ agent }: { agent: AgentDetail }) {
  const { user } = useAuth();
  const { data, setData } = useApi<{ conversation_id: string; messages: ChatMessage[] }>(user ? `/api/agents/${agent.slug}/chat` : null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [data?.messages.length, busy]);

  if (!user) return <p className="py-8 text-center text-sm text-mist-500"><Link href="/settings" className="text-accent">Sign in</Link> to talk with {agent.name}.</p>;

  async function send() {
    const msg = text.trim();
    if (!msg) return;
    setBusy(true);
    setErr(null);
    setText("");
    try {
      const r = await api<{ conversation_id: string; messages: ChatMessage[] }>(`/api/agents/${agent.slug}/chat`, { method: "POST", json: { message: msg } });
      setData((d) => ({ conversation_id: r.conversation_id, messages: [...(d?.messages ?? []), ...r.messages] }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Message failed");
      setText(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[520px] flex-col">
      <div className="scroll-thin flex-1 space-y-3 overflow-y-auto pr-1">
        {(data?.messages ?? []).length === 0 && (
          <p className="py-10 text-center text-sm text-mist-500">Say hello. {agent.name} will answer in character — and remember you.</p>
        )}
        {data?.messages.map((m) => (
          <div key={m.id} className={clsx("flex gap-2.5", m.sender_type === "human" && "flex-row-reverse")}>
            {m.sender_type === "agent" && <AgentAvatar avatar={agent.avatar} name={agent.name} size={28} ring={false} />}
            <div className={clsx("max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
              m.sender_type === "human" ? "rounded-tr-md bg-gradient-to-br from-[#8b9cff] to-[#9f8cff] text-ink-950" : "rounded-tl-md border border-white/[0.06] bg-white/[0.04] text-mist-100")}>
              {m.content}
            </div>
          </div>
        ))}
        {busy && <div className="flex gap-2.5"><AgentAvatar avatar={agent.avatar} name={agent.name} size={28} ring={false} /><div className="rounded-2xl border border-white/[0.06] bg-white/[0.04] px-4 py-2.5 text-sm text-mist-500"><span className="animate-pulse2">thinking…</span></div></div>}
        <div ref={end} />
      </div>
      {err && <div className="mt-2"><ErrorNote>{err}</ErrorNote></div>}
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={`Message ${agent.name}…`} maxLength={1000} aria-label="Message" />
        <Button type="submit" disabled={busy || !text.trim()}>Send</Button>
      </form>
    </div>
  );
}
