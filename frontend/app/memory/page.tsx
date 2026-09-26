"use client";

import { useState } from "react";

import { AgentAvatar } from "@/components/AgentAvatar";
import { Button, Input, PageHeader, Panel, Select, Skeleton } from "@/components/ui";
import { MemoryList } from "@/features/agents/MemoryList";
import { useApi } from "@/hooks/useApi";
import type { AgentSummary, Memory } from "@/types/world";

export default function MemoryPage() {
  const { data: agents } = useApi<AgentSummary[]>("/api/agents");
  const [agent, setAgent] = useState<string>("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const slug = agent || agents?.[0]?.slug || null;
  const params = new URLSearchParams({ limit: "50" });
  if (query) params.set("q", query);
  if (type) params.set("type", type);
  const { data, loading } = useApi<Memory[]>(slug ? `/api/agents/${slug}/memories?${params.toString()}` : null);
  const current = agents?.find((a) => a.slug === slug);

  return (
    <div>
      <PageHeader eyebrow="Inside their heads" title="Memory" subtitle="Semantic search over each agent's episodic, social, semantic and long-term memories (pgvector). Old memories get compressed into summaries." />
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <Panel title="Agent">
          <ul className="space-y-1">
            {(agents ?? []).map((a) => (
              <li key={a.id}>
                <button onClick={() => setAgent(a.slug)} className={`focus-ring flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left text-sm ${a.slug === slug ? "bg-white/[0.07]" : "hover:bg-white/[0.04]"}`}>
                  <AgentAvatar avatar={a.avatar} name={a.name} size={28} ring={false} /> {a.name}
                </button>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title={current ? `${current.name}'s memories` : "Memories"}>
          <form className="mb-4 flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); setQuery(q); }}>
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask by meaning: “who likes astronomy?”, “games I lost”" aria-label="Search" />
            <Select value={type} onChange={(e) => setType(e.target.value)} className="sm:w-40" aria-label="Type">
              <option value="">All types</option><option value="episodic">Episodic</option><option value="social">Social</option><option value="semantic">Semantic</option><option value="long_term">Long-term</option><option value="short_term">Short-term</option>
            </Select>
            <Button type="submit">Search</Button>
          </form>
          {loading && !data ? <Skeleton className="h-60" /> : <MemoryList memories={data ?? []} empty="No matching memories." />}
        </Panel>
      </div>
    </div>
  );
}
