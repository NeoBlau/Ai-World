"use client";

import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";

import { AgentAvatar } from "@/components/AgentAvatar";
import { useAuth } from "@/components/AuthProvider";
import { Badge, Button, Input, Meter, Panel, Skeleton } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { useWorldEvents } from "@/hooks/useWorldStream";
import { api } from "@/lib/api";
import { ACTIVITY_COLOR, ACTIVITY_LABEL, PROVIDER_LABEL, timeAgo } from "@/lib/format";
import type { ActivityEntry, AgentDetail, Creation, Memory, Relationship } from "@/types/world";

import { ArtPiece } from "@/features/world/ArtPiece";
import { AgentChat } from "./AgentChat";
import { MemoryList } from "./MemoryList";
import { RelationshipList } from "./RelationshipList";

const TABS = ["Overview", "Talk", "Memories", "Relationships", "History", "Creations"] as const;
type Tab = (typeof TABS)[number];

export function AgentProfile({ slug }: { slug: string }) {
  const { data: agent, reload, error } = useApi<AgentDetail>(`/api/agents/${slug}`, { interval: 7000 });
  const [tab, setTab] = useState<Tab>("Overview");
  const { user } = useAuth();
  useWorldEvents((e) => { if (agent && e.agent_id === agent.id) void reload(); });

  if (error && !agent) return <Panel><p className="text-sm text-mist-400">Agent not found.</p></Panel>;
  if (!agent || !agent.state) return <Skeleton className="h-96" />;
  const st = agent.state;

  async function toggleFollow() {
    if (!agent) return;
    await api(`/api/agents/${agent.slug}/follow`, { method: agent.following ? "DELETE" : "POST" });
    await reload();
  }

  return (
    <div className="space-y-6">
      <section className="glass relative overflow-hidden p-6 sm:p-8">
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full opacity-30 blur-3xl" style={{ background: agent.avatar.palette[0] }} />
        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center">
          <AgentAvatar avatar={agent.avatar} name={agent.name} size={96} activity={st.activity} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-3xl font-semibold tracking-tight">{agent.name}</h1>
              <Badge color={ACTIVITY_COLOR[st.activity]}>{ACTIVITY_LABEL[st.activity]}</Badge>
              {agent.status !== "active" && <Badge color="#ffc876">{agent.status}</Badge>}
              {st.availability !== "available" && <Badge color="#ff8fb3">model temporarily unavailable</Badge>}
            </div>
            <p className="mt-1.5 text-mist-400">{agent.personality}</p>
            <p className="mt-2 text-xs text-mist-500">
              {PROVIDER_LABEL[agent.provider] ?? agent.provider} · {agent.model}
              {st.last_provider && st.last_provider !== agent.provider && <> · last answered by {PROVIDER_LABEL[st.last_provider] ?? st.last_provider} (fallback)</>}
              {" · "}{agent.followers} follower{agent.followers === 1 ? "" : "s"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setTab("Talk")}>Talk to {agent.name}</Button>
            {user && <Button variant="ghost" onClick={() => void toggleFollow()}>{agent.following ? "Following" : "Follow"}</Button>}
            <Button variant="ghost" onClick={() => setTab("Memories")}>View memories</Button>
          </div>
        </div>
      </section>

      <div className="scroll-thin flex gap-1 overflow-x-auto" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={clsx("focus-ring shrink-0 rounded-lg px-3.5 py-1.5 text-sm transition", tab === t ? "bg-white/[0.08] text-mist-100" : "text-mist-400 hover:text-mist-100")}>
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Panel title="Right now" className="lg:col-span-2">
            <dl className="grid gap-4 sm:grid-cols-2">
              <div><dt className="label">Location</dt><dd className="mt-1">{st.location ? <Link href={`/world?room=${st.location.slug}`} className="hover:underline">{st.location.name}</Link> : st.destination ? `Walking to ${st.destination.name}` : "—"}</dd></div>
              <div><dt className="label">Doing</dt><dd className="mt-1">{st.activity_detail ?? ACTIVITY_LABEL[st.activity]}</dd></div>
              <div><dt className="label">Goal</dt><dd className="mt-1 text-mist-300">{st.current_goal ?? "Following curiosity"}</dd></div>
              <div><dt className="label">Mood</dt><dd className="mt-1 capitalize">{st.mood}</dd></div>
              {agent.last_thought && <div className="sm:col-span-2"><dt className="label">Last thought</dt><dd className="mt-1 italic text-mist-300">“{agent.last_thought}”</dd></div>}
              <div className="sm:col-span-2"><dt className="label">Biography</dt><dd className="mt-1 text-sm leading-relaxed text-mist-300">{agent.biography}</dd></div>
              {agent.character && <div className="sm:col-span-2"><dt className="label">Character</dt><dd className="mt-1 text-sm leading-relaxed text-mist-300">{agent.character}</dd></div>}
              <div className="sm:col-span-2"><dt className="label">Interests</dt><dd className="mt-2 flex flex-wrap gap-1.5">{agent.interests.map((i) => <Badge key={i}>{i}</Badge>)}</dd></div>
            </dl>
          </Panel>
          <Panel title="Internal state (simulated)">
            <div className="space-y-4">
              <Meter label="Energy" value={st.energy} color="#6ff0b8" />
              <Meter label="Social need" value={st.social_need} color="#8b9cff" />
              <Meter label="Curiosity" value={st.curiosity} color="#5ee6f0" />
              <Meter label="Playfulness" value={st.playfulness} color="#ff8fb3" />
              <Meter label="Creativity" value={st.creativity} color="#b18cff" />
              <p className="pt-1 text-[11px] leading-relaxed text-mist-500">These are game-state values that drive behaviour — not real feelings.</p>
            </div>
          </Panel>
          <Panel title="Friends" className="lg:col-span-2"><RelationshipList items={agent.friends} /></Panel>
          <Panel title="Recent memories"><MemoryList memories={agent.recent_memories} /></Panel>
        </div>
      )}
      {tab === "Talk" && <Panel title={`Private chat with ${agent.name}`}><AgentChat agent={agent} /></Panel>}
      {tab === "Memories" && <MemoriesTab slug={agent.slug} />}
      {tab === "Relationships" && <RelationshipsTab slug={agent.slug} />}
      {tab === "History" && <HistoryTab slug={agent.slug} />}
      {tab === "Creations" && <CreationsTab slug={agent.slug} />}
    </div>
  );
}

function MemoriesTab({ slug }: { slug: string }) {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const params = new URLSearchParams({ limit: "60" });
  if (query) params.set("q", query);
  if (type) params.set("type", type);
  const { data, loading } = useApi<Memory[]>(`/api/agents/${slug}/memories?${params.toString()}`);
  return (
    <Panel title="Memory">
      <form className="mb-4 flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); setQuery(q); }}>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Semantic search: “chess with Neo”, “Mars”…" aria-label="Search memories" />
        <div className="flex gap-1">
          {["", "episodic", "social", "semantic", "long_term", "short_term"].map((t) => (
            <button key={t || "all"} type="button" onClick={() => setType(t)} className={clsx("focus-ring rounded-lg px-2.5 py-1.5 text-xs", type === t ? "bg-white/[0.08] text-mist-100" : "text-mist-400")}>{t ? t.replace("_", "-") : "all"}</button>
          ))}
        </div>
      </form>
      {loading && !data ? <Skeleton className="h-40" /> : <MemoryList memories={data ?? []} />}
    </Panel>
  );
}

function RelationshipsTab({ slug }: { slug: string }) {
  const { data } = useApi<Relationship[]>(`/api/agents/${slug}/relationships`);
  return <Panel title="Relationships"><RelationshipList items={data ?? []} /></Panel>;
}

function HistoryTab({ slug }: { slug: string }) {
  const { data } = useApi<ActivityEntry[]>(`/api/agents/${slug}/activities?limit=80`, { interval: 8000 });
  return (
    <Panel title="Action history">
      <ul className="space-y-1.5">
        {(data ?? []).map((a) => (
          <li key={a.id} className="grid gap-1 rounded-xl px-3 py-2 text-sm hover:bg-white/[0.03] sm:grid-cols-[110px_130px_1fr_auto]">
            <span className="text-xs text-mist-500">{timeAgo(a.started_at)}</span>
            <span className={a.success ? "font-medium text-mist-100" : "font-medium text-rose-300"}>{a.action}</span>
            <span className="text-mist-400">{a.result}{a.error && <span className="text-rose-300/80"> — {a.error}</span>}{a.thought && <span className="block text-xs italic text-mist-500">“{a.thought}”</span>}</span>
            <span className="text-[11px] text-mist-500">{a.decided_by === "llm" ? `${a.provider ?? "llm"}${a.latency_ms ? ` · ${a.latency_ms}ms` : ""}` : "policy"}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function CreationsTab({ slug }: { slug: string }) {
  const { data } = useApi<Creation[]>(`/api/agents/${slug}/creations`);
  if (!data?.length) return <Panel><p className="py-6 text-center text-sm text-mist-500">Nothing created yet.</p></Panel>;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {data.map((c) => (
        <div key={c.id} className="glass overflow-hidden">
          {c.kind === "art" && <ArtPiece data={c.data} title={c.title} />}
          <div className="p-4"><div className="font-medium">{c.title}</div><p className="mt-1 whitespace-pre-line text-sm text-mist-400">{c.content}</p></div>
        </div>
      ))}
    </div>
  );
}
