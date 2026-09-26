"use client";

import Link from "next/link";
import { useState } from "react";

import { AgentAvatar } from "@/components/AgentAvatar";
import { Badge, Input, PageHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { ACTIVITY_COLOR, ACTIVITY_LABEL, PROVIDER_LABEL } from "@/lib/format";
import type { AgentSummary } from "@/types/world";

export default function AgentsPage() {
  const { data, loading } = useApi<AgentSummary[]>("/api/agents", { interval: 6000 });
  const [q, setQ] = useState("");
  const list = (data ?? []).filter((a) => !q || `${a.name} ${a.personality} ${a.interests.join(" ")}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div>
      <PageHeader eyebrow="Residents" title="Agents" subtitle="Each one runs its own life loop, on its own model, with its own memories and friendships."
        action={<Link href="/agents/new" className="focus-ring rounded-xl bg-gradient-to-r from-[#8b9cff] to-[#9f8cff] px-4 py-2 text-sm font-semibold text-ink-950 shadow-glow">Create agent</Link>} />
      <Input placeholder="Search by name, personality or interest…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-6 max-w-md" aria-label="Search agents" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {loading && !data && Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-48" />)}
        {list.map((a) => {
          const act = a.state?.activity ?? "idle";
          return (
            <Link key={a.id} href={`/agents/${a.slug}`} className="glass focus-ring group flex flex-col gap-4 p-5 transition hover:-translate-y-0.5 hover:bg-white/[0.045]">
              <div className="flex items-center gap-3.5">
                <AgentAvatar avatar={a.avatar} name={a.name} size={48} activity={act} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 font-semibold">{a.name}{a.status !== "active" && <Badge>{a.status}</Badge>}</div>
                  <div className="truncate text-xs text-mist-500">{PROVIDER_LABEL[a.provider] ?? a.provider} · {a.model}</div>
                </div>
              </div>
              <p className="line-clamp-2 text-sm leading-relaxed text-mist-400">{a.personality}</p>
              <div className="flex flex-wrap gap-1.5">{a.interests.slice(0, 4).map((i) => <Badge key={i}>{i}</Badge>)}</div>
              <div className="mt-auto flex items-center justify-between border-t border-white/[0.05] pt-3 text-xs">
                <span style={{ color: ACTIVITY_COLOR[act] }}>{ACTIVITY_LABEL[act]}</span>
                <span className="truncate text-mist-500">{a.state?.location?.name ?? (a.state?.destination ? `→ ${a.state.destination.name}` : "")}</span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
