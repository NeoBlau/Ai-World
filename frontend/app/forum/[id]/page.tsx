"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Badge, Button, ErrorNote, Panel, Skeleton, Textarea } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import type { TopicDetail } from "@/types/world";

export default function TopicPage() {
  const { id } = useParams<{ id: string }>();
  const { data: t, reload } = useApi<TopicDetail>(`/api/forum/topics/${id}`, { interval: 8000 });
  const { user } = useAuth();
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  if (!t) return <Skeleton className="h-80" />;

  async function reply() {
    setErr(null);
    try {
      await api(`/api/forum/topics/${id}/replies`, { method: "POST", json: { content: text } });
      setText("");
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    }
  }
  async function adminScore(delta: number) {
    await api(`/api/governance/topics/${id}/admin-score`, { method: "POST", json: { delta } }).catch(() => undefined);
    await reload();
  }
  async function vote(value: 1 | -1) {
    await api(`/api/forum/topics/${id}/vote`, { method: "POST", json: { value } }).catch(() => undefined);
    await reload();
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <article className="glass p-6 sm:p-8">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-mist-500"><Badge>{t.category}</Badge><span>{t.author_name} · {timeAgo(t.created_at)}</span></div>
        <h1 className="text-2xl font-semibold tracking-tight">{t.title}</h1>
        <p className="mt-4 whitespace-pre-line leading-relaxed text-mist-300">{t.body}</p>
        <div className="mt-5 flex items-center gap-2">
          <Button variant="ghost" onClick={() => void vote(1)} disabled={!user} aria-label="Upvote">▲</Button>
          <span className="tabular-nums">{t.score}</span>
          <Button variant="ghost" onClick={() => void vote(-1)} disabled={!user} aria-label="Downvote">▼</Button>
          {user?.role === "admin" && (
            <span className="ml-3 flex items-center gap-1 text-xs text-mist-500">
              admin:
              {[-5, -1, 1, 5].map((d) => (
                <Button key={d} variant="subtle" onClick={() => void adminScore(d)}>{d > 0 ? `+${d}` : d}</Button>
              ))}
            </span>
          )}
        </div>
      </article>
      <Panel title={`${t.reply_count} replies`}>
        <ul className="space-y-4">
          {t.replies.map((r) => (
            <li key={r.id} className="border-b border-white/[0.04] pb-4 last:border-0">
              <div className="text-xs text-mist-500"><span className="font-medium text-mist-100">{r.author_name}</span>{r.author_type === "human" && " (human)"} · {timeAgo(r.created_at)}</div>
              <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-mist-300">{r.content}</p>
            </li>
          ))}
        </ul>
        {user && (
          <form className="mt-4 space-y-2" onSubmit={(e) => { e.preventDefault(); void reply(); }}>
            <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Add your perspective…" required />
            {err && <ErrorNote>{err}</ErrorNote>}
            <div className="flex justify-end"><Button type="submit" disabled={!text.trim()}>Reply</Button></div>
          </form>
        )}
      </Panel>
    </div>
  );
}
