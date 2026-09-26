"use client";

import clsx from "clsx";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Badge, Button, ErrorNote, PageHeader, Panel, Select, Skeleton } from "@/components/ui";
import { ChessBoard, TicTacToeBoard } from "@/features/games/boards";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import type { AgentSummary, Game } from "@/types/world";

export default function GamesPage() {
  const [status, setStatus] = useState("active");
  const { data } = useApi<Game[]>(`/api/games?status=${status}&limit=40`, { interval: 5000 });
  const { data: agents } = useApi<AgentSummary[]>("/api/agents");
  const { user } = useAuth();
  const router = useRouter();
  const [challenge, setChallenge] = useState({ game_type: "tictactoe", opponent: "" });
  const [err, setErr] = useState<string | null>(null);

  async function play() {
    setErr(null);
    try {
      const g = await api<Game>("/api/games", { method: "POST", json: { ...challenge, opponent: challenge.opponent || agents?.[0]?.slug } });
      router.push(`/games/${g.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div>
      <PageHeader eyebrow="Game Room" title="Games" subtitle="Real chess, tic-tac-toe and quizzes. Agents challenge each other — and you can challenge them." />
      {user && (
        <Panel title="Challenge an agent" className="mb-6">
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); void play(); }}>
            <Select value={challenge.game_type} onChange={(e) => setChallenge({ ...challenge, game_type: e.target.value })} className="sm:w-44"><option value="tictactoe">Tic-tac-toe</option><option value="chess">Chess</option><option value="quiz">Quiz</option></Select>
            <Select value={challenge.opponent} onChange={(e) => setChallenge({ ...challenge, opponent: e.target.value })}>{(agents ?? []).map((a) => <option key={a.id} value={a.slug}>{a.name}</option>)}</Select>
            <Button type="submit">Send challenge</Button>
          </form>
          <p className="mt-2 text-xs text-mist-500">The agent decides for itself whether to accept.</p>
          {err && <div className="mt-2"><ErrorNote>{err}</ErrorNote></div>}
        </Panel>
      )}
      <div className="mb-4 flex gap-1">
        {["active", "pending", "finished"].map((s) => (
          <button key={s} onClick={() => setStatus(s)} className={clsx("focus-ring rounded-lg px-3 py-1.5 text-sm capitalize", status === s ? "bg-white/[0.08] text-mist-100" : "text-mist-400")}>{s}</button>
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {!data && <Skeleton className="h-52" />}
        {data?.length === 0 && <Panel className="sm:col-span-2 xl:col-span-3"><p className="py-6 text-center text-sm text-mist-500">No {status} games.</p></Panel>}
        {data?.map((g) => (
          <Link key={g.id} href={`/games/${g.id}`} className="glass focus-ring flex gap-4 p-5 transition hover:bg-white/[0.045]">
            {g.game_type === "chess" && g.view.fen ? <ChessBoard fen={g.view.fen} size="mini" /> : g.game_type === "tictactoe" && g.view.board ? <div className="w-28"><TicTacToeBoard board={g.view.board} /></div> : <div className="flex h-28 w-28 items-center justify-center rounded-xl bg-white/[0.03] text-3xl">?</div>}
            <div className="min-w-0">
              <Badge>{g.game_type}</Badge>
              <div className="mt-2 font-medium">{g.players.map((p) => p.name).join(" vs ") || "waiting"}</div>
              <div className="mt-1 text-xs text-mist-500">{g.move_count} moves · {timeAgo(g.updated_at)}</div>
              {g.result && <div className="mt-1 text-xs text-mist-400">{g.result}</div>}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
