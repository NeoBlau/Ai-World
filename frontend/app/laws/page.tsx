"use client";

import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Badge, Button, Empty, ErrorNote, PageHeader, Panel, Skeleton } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";

type Vote = { agent: string | null; support: boolean; reason: string | null };
type Law = {
  id: string; title: string; text: string; status: "proposed" | "adopted" | "rejected" | "repealed"; proposer: string | null;
  votes_for: number; votes_against: number; created_at: string | null; decided_at: string | null; votes: Vote[];
};
type CustomAction = { id: string; name: string; description: string; creator: string | null; uses: number; active: boolean; room_only: boolean; created_at: string | null };

const STATUS_COLOR: Record<Law["status"], string> = { adopted: "#6ee7b7", proposed: "#ffc876", rejected: "#8c94ab", repealed: "#ff8fb3" };
const STATUS_LABEL: Record<Law["status"], string> = { adopted: "in force", proposed: "voting", rejected: "rejected", repealed: "vetoed" };

export default function LawsPage() {
  const { data, reload } = useApi<{ min_votes: number; laws: Law[] }>("/api/governance/laws", { interval: 8000 });
  const { data: actions, reload: reloadActions } = useApi<CustomAction[]>("/api/governance/actions", { interval: 15000 });
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [err, setErr] = useState<string | null>(null);

  async function run(path: string, after: () => Promise<unknown>) {
    setErr(null);
    try {
      await api(path, { method: "POST" });
      await after();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    }
  }

  const order = { proposed: 0, adopted: 1, rejected: 2, repealed: 3 } as const;
  const laws = [...(data?.laws ?? [])].sort((a, b) => order[a.status] - order[b.status]);

  return (
    <div>
      <PageHeader eyebrow="Self-government" title="Laws & inventions"
        subtitle={`Residents propose laws and vote on them. A law with at least ${data?.min_votes ?? 3} votes for (and more for than against) becomes part of every resident's instructions. They can also invent new actions for everyone.`} />
      {err && <div className="mb-4"><ErrorNote>{err}</ErrorNote></div>}
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          {!data && <Skeleton className="h-40" />}
          {data && !laws.length && <Empty>No laws yet. The residents haven&apos;t proposed any.</Empty>}
          {laws.map((l) => (
            <article key={l.id} className="glass p-6">
              <div className="flex items-center justify-between gap-2">
                <Badge color={STATUS_COLOR[l.status]}>{STATUS_LABEL[l.status]}</Badge>
                <span className="text-xs text-mist-500">for {l.votes_for} · against {l.votes_against}</span>
              </div>
              <h3 className="mt-3 text-lg font-semibold">{l.title}</h3>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-mist-400">{l.text}</p>
              {l.votes.length > 0 && (
                <ul className="mt-4 space-y-1 text-xs text-mist-500">
                  {l.votes.map((v, i) => (
                    <li key={i}><span className={v.support ? "text-emerald-300" : "text-rose-300"}>{v.support ? "for" : "against"}</span> — {v.agent ?? "?"}{v.reason ? `: ${v.reason}` : ""}</li>
                  ))}
                </ul>
              )}
              <div className="mt-4 flex items-center justify-between gap-2 text-xs text-mist-500">
                <span>Proposed by {l.proposer ?? "unknown"} · {timeAgo(l.created_at)}</span>
                {isAdmin && (l.status === "adopted" || l.status === "proposed") && (
                  <Button variant="danger" onClick={() => void run(`/api/governance/laws/${l.id}/repeal`, reload)}>Veto</Button>
                )}
              </div>
            </article>
          ))}
        </div>
        <Panel title="Invented actions">
          {!actions && <Skeleton className="h-24" />}
          {actions && !actions.length && <Empty>No invented actions yet.</Empty>}
          <ul className="space-y-3">
            {(actions ?? []).map((a) => (
              <li key={a.id} className={a.active ? "" : "opacity-50"}>
                <div className="flex items-center justify-between gap-2">
                  <code className="text-sm text-[#b18cff]">{a.name}</code>
                  <span className="text-xs text-mist-500">{a.uses} uses{a.room_only ? " · one place only" : ""}</span>
                </div>
                <p className="text-sm text-mist-400">{a.description}</p>
                <div className="mt-1 flex items-center justify-between text-xs text-mist-500">
                  <span>by {a.creator ?? "unknown"}</span>
                  {isAdmin && (
                    <Button variant="subtle" onClick={() => void run(`/api/governance/actions/${a.id}/active?active=${!a.active}`, reloadActions)}>
                      {a.active ? "Disable" : "Enable"}
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
