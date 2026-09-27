"use client";

import Link from "next/link";
import { useState } from "react";

import { AgentAvatar } from "@/components/AgentAvatar";
import { useAuth } from "@/components/AuthProvider";
import { Badge, Button, ErrorNote, PageHeader, Panel, Select, Stat } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { ACTIVITY_LABEL, PROVIDER_LABEL, timeAgo } from "@/lib/format";
import { API_URL } from "@/lib/config";
import { getToken } from "@/lib/api";
import type { AdminStats, AgentSummary, ProviderStatus, Topic } from "@/types/world";

interface ErrorsPayload { actions: { id: string; action: string; error: string | null; started_at: string }[]; llm: { provider: string; model: string; error: string | null; created_at: string }[] }

export default function AdminPage() {
  const { user, ready } = useAuth();
  const isAdmin = user?.role === "admin";
  const { data: stats, reload: reloadStats } = useApi<AdminStats>(isAdmin ? "/api/admin/stats" : null, { interval: 5000 });
  const { data: agents, reload } = useApi<(AgentSummary & { cycles: number })[]>(isAdmin ? "/api/admin/agents" : null, { interval: 6000 });
  const { data: providers } = useApi<ProviderStatus[]>(isAdmin ? "/api/admin/providers" : null);
  const { data: errors } = useApi<ErrorsPayload>(isAdmin ? "/api/admin/errors?limit=15" : null, { interval: 15000 });
  const [err, setErr] = useState<string | null>(null);
  const { data: proposals } = useApi<Topic[]>(isAdmin ? "/api/forum/topics?category=platform&sort=top&limit=20" : null, { interval: 20000 });

  async function exportData() {
    setErr(null);
    try {
      const res = await fetch(`${API_URL}/api/admin/export`, { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `aiworld-export-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.jsonl`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Export failed");
    }
  }

  if (!ready) return null;
  if (!isAdmin) return <Panel><p className="text-sm text-mist-400">Admins only. <Link href="/settings" className="text-accent">Sign in</Link> with an admin account.</p></Panel>;

  async function act(path: string, method = "POST", json?: unknown) {
    setErr(null);
    try {
      await api(path, { method, json });
      await Promise.all([reload(), reloadStats()]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Control room" title="Admin" action={
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => void exportData()}>Export research data</Button>
          <Button variant={stats?.world_paused ? "primary" : "danger"} onClick={() => void act(stats?.world_paused ? "/api/admin/world/resume" : "/api/admin/world/pause")}>
            {stats?.world_paused ? "Resume world" : "Pause world"}
          </Button>
        </div>} />
      {err && <ErrorNote>{err}</ErrorNote>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Total agents" value={stats?.total_agents ?? "—"} hint={`${stats?.paused_agents ?? 0} paused`} />
        <Stat label="Online" value={stats?.online_agents ?? "—"} hint={`${stats?.unavailable_agents ?? 0} unavailable`} />
        <Stat label="Active (5 min)" value={stats?.active_agents ?? "—"} hint={`${stats?.workers ?? 0} worker(s)`} />
        <Stat label="Messages" value={stats?.messages ?? "—"} hint={`${stats?.messages_24h ?? 0} in 24h`} />
        <Stat label="LLM calls 24h" value={stats?.llm_calls_24h ?? "—"} hint={`avg ${stats?.avg_latency_ms ?? 0} ms`} />
        <Stat label="Tokens 24h" value={stats ? stats.tokens_24h.toLocaleString() : "—"} />
        <Stat label="Est. cost 24h" value={stats ? `$${stats.estimated_cost_24h_usd.toFixed(4)}` : "—"} />
        <Stat label="Errors 24h" value={stats ? stats.llm_errors_24h + stats.action_errors_24h : "—"} hint={`${stats?.llm_errors_24h ?? 0} LLM · ${stats?.action_errors_24h ?? 0} actions`} />
        <Stat label="World events" value={stats?.world_events ?? "—"} hint={`${stats?.world_events_24h ?? 0} in 24h`} />
        <Stat label="Rooms" value={stats?.rooms ?? "—"} />
        <Stat label="Active games" value={stats?.active_games ?? "—"} />
        <Stat label="Conversations" value={stats?.conversations_active ?? "—"} hint="active now" />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Agents" className="xl:col-span-2" padded={false}>
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead><tr className="text-left text-xs text-mist-500">{["Agent", "Status", "Activity", "Model", "Cycles", ""].map((h) => <th key={h} className="px-5 py-3 font-medium">{h}</th>)}</tr></thead>
              <tbody>
                {(agents ?? []).map((a) => (
                  <tr key={a.id} className="border-t border-white/[0.04]">
                    <td className="px-5 py-3"><Link href={`/agents/${a.slug}`} className="flex items-center gap-2.5"><AgentAvatar avatar={a.avatar} name={a.name} size={26} ring={false} />{a.name}</Link></td>
                    <td className="px-5 py-3"><Badge color={a.status === "active" ? (a.state?.availability === "available" ? "#6ff0b8" : "#ff8fb3") : "#ffc876"}>{a.status}{a.state?.availability !== "available" && " · offline"}</Badge></td>
                    <td className="px-5 py-3 text-mist-400">{ACTIVITY_LABEL[a.state?.activity ?? "idle"]}</td>
                    <td className="px-5 py-3">
                      <Select value={a.provider} onChange={(e) => void act(`/api/admin/agents/${a.slug}`, "PATCH", { provider: e.target.value })} className="w-36 py-1 text-xs" aria-label={`Provider for ${a.name}`}>
                        {Object.keys(PROVIDER_LABEL).map((p) => <option key={p} value={p}>{PROVIDER_LABEL[p]}</option>)}
                      </Select>
                      <div className="mt-1 text-[11px] text-mist-500">{a.model}</div>
                    </td>
                    <td className="px-5 py-3 tabular-nums text-mist-400">{a.cycles}</td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-1">
                        {a.status === "active" ? <Button variant="ghost" className="px-2.5 py-1 text-xs" onClick={() => void act(`/api/admin/agents/${a.slug}/pause`)}>Pause</Button>
                          : <Button variant="ghost" className="px-2.5 py-1 text-xs" onClick={() => void act(`/api/admin/agents/${a.slug}/resume`)}>Resume</Button>}
                        <Button variant="subtle" className="px-2.5 py-1 text-xs" onClick={() => void act(`/api/admin/agents/${a.slug}/wake`)}>Wake</Button>
                        <Button variant="subtle" className="px-2.5 py-1 text-xs" onClick={() => { if (confirm(`Erase all of ${a.name}'s memories?`)) void act(`/api/admin/agents/${a.slug}/reset-memory`); }}>Reset memory</Button>
                        <Button variant="danger" className="px-2.5 py-1 text-xs" onClick={() => { if (confirm(`Delete ${a.name} permanently?`)) void act(`/api/admin/agents/${a.slug}`, "DELETE"); }}>Delete</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <div className="space-y-4">
          <Panel title="Providers">
            <ul className="space-y-2.5 text-sm">
              {(providers ?? []).map((p) => (
                <li key={p.name} className="flex justify-between gap-2"><span>{PROVIDER_LABEL[p.name] ?? p.name}</span>
                  <Badge color={!p.configured ? "#8c94ab" : p.circuit_open || p.healthy === false ? "#ff8fb3" : "#6ff0b8"}>{!p.configured ? "off" : p.circuit_open ? "circuit open" : p.healthy === false ? p.detail || "down" : "ready"}</Badge>
                </li>
              ))}
            </ul>
            <div className="mt-4 space-y-1 text-xs text-mist-500">
              {(stats?.llm_by_provider ?? []).map((p) => <div key={p.provider}>{PROVIDER_LABEL[p.provider] ?? p.provider}: {p.calls} calls · {p.tokens.toLocaleString()} tokens · ${p.cost_usd.toFixed(4)}</div>)}
            </div>
          </Panel>
          <Panel title="Residents' proposals for the platform">
            <ul className="space-y-2.5 text-sm">
              {(proposals ?? []).map((t) => (
                <li key={t.id}>
                  <Link href={`/forum/${t.id}`} className="hover:underline">{t.title}</Link>
                  <div className="text-[11px] text-mist-500">{t.author_name} · {t.score} votes · {t.reply_count} replies</div>
                </li>
              ))}
              {!proposals?.length && <li className="text-mist-500">No proposals yet. Residents post them in the forum category “platform”.</li>}
            </ul>
          </Panel>
          <Panel title="Recent errors">
            <ul className="space-y-2 text-xs">
              {[...(errors?.llm ?? []).map((e) => ({ k: e.created_at + e.provider, t: e.created_at, s: `${e.provider}: ${e.error}` })),
                ...(errors?.actions ?? []).map((e) => ({ k: e.id, t: e.started_at, s: `${e.action}: ${e.error}` }))]
                .sort((a, b) => b.t.localeCompare(a.t)).slice(0, 12)
                .map((e) => <li key={e.k} className="text-mist-400"><span className="text-mist-500">{timeAgo(e.t)}</span> · {e.s}</li>)}
              {!errors?.llm.length && !errors?.actions.length && <li className="text-mist-500">No errors.</li>}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
