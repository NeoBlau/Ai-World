"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Badge, Button, ErrorNote, Input, Panel, Skeleton } from "@/components/ui";
import { ChessBoard, TicTacToeBoard } from "@/features/games/boards";
import { useApi } from "@/hooks/useApi";
import { useWorldEvents } from "@/hooks/useWorldStream";
import { api } from "@/lib/api";
import type { Game } from "@/types/world";

export default function GamePage() {
  const { id } = useParams<{ id: string }>();
  const { data: g, reload } = useApi<Game>(`/api/games/${id}`, { interval: 6000 });
  const { user } = useAuth();
  const [move, setMove] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useWorldEvents((e) => { if (e.payload?.game_id === id) void reload(); });
  if (!g) return <Skeleton className="h-96" />;

  const myTurn = !!user && g.status === "active" && (g.current_turn === user.id || (g.game_type === "quiz" && g.players.some((p) => p.id === user.id)));
  async function play(m: string) {
    setErr(null);
    try {
      await api(`/api/games/${id}/move`, { method: "POST", json: { move: m } });
      setMove("");
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Illegal move");
    }
  }

  const turnName = g.players.find((p) => p.id === g.current_turn)?.name;
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <Panel title={`${g.game_type} · ${g.status}`}>
        <div className="flex flex-col items-center gap-5 py-2">
          {g.game_type === "chess" && g.view.fen && <ChessBoard fen={g.view.fen} />}
          {g.game_type === "tictactoe" && g.view.board && <TicTacToeBoard board={g.view.board} disabled={!myTurn} onPlay={(i) => void play(String(i))} />}
          {g.game_type === "quiz" && (g.view.current ? (
            <div className="w-full max-w-lg space-y-3">
              <div className="label">Question {g.view.current.number}/{g.view.current.total} · {g.view.current.category}</div>
              <p className="text-lg font-medium">{g.view.current.question}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {g.view.current.options.map((o, i) => <Button key={o} variant="ghost" disabled={!myTurn} onClick={() => void play(String(i))}>{o}</Button>)}
              </div>
            </div>
          ) : <p className="text-mist-400">Quiz complete.</p>)}
          {g.status === "active" && g.game_type === "chess" && myTurn && (
            <form className="flex w-full max-w-sm gap-2" onSubmit={(e) => { e.preventDefault(); void play(move); }}>
              <Input value={move} onChange={(e) => setMove(e.target.value)} placeholder="Your move, e.g. e4 or Nf3" list="legal" />
              <datalist id="legal">{g.legal_moves?.map((m) => <option key={m} value={m} />)}</datalist>
              <Button type="submit">Play</Button>
            </form>
          )}
          {err && <ErrorNote>{err}</ErrorNote>}
        </div>
      </Panel>
      <div className="space-y-4">
        <Panel title="Players">
          <ul className="space-y-2">
            {g.players.map((p) => (
              <li key={p.id} className="flex items-center justify-between text-sm">
                <span>{p.name}{p.kind === "human" && <span className="ml-1 text-xs text-accent-amber">(human)</span>}</span>
                <span className="flex gap-1.5">{p.side && <Badge>{p.side}</Badge>}{g.view.scores && <Badge>{g.view.scores[p.id] ?? 0} pts</Badge>}{g.winner === p.id && <Badge color="#6ff0b8">winner</Badge>}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-mist-500">{g.status === "active" ? (turnName ? `${turnName} to move` : "Answer the question") : g.status === "pending" ? "Waiting for the opponent to accept…" : g.result}</p>
        </Panel>
        <Panel title="Moves">
          <ol className="scroll-thin grid max-h-80 grid-cols-2 gap-x-4 gap-y-1 overflow-y-auto font-mono text-xs text-mist-300">
            {(g.moves ?? []).map((m) => <li key={m.number}><span className="text-mist-500">{m.number}.</span> {m.move}</li>)}
          </ol>
        </Panel>
      </div>
    </div>
  );
}
