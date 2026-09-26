"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useApi } from "@/hooks/useApi";
import { untilLabel } from "@/lib/format";
import type { Game, SocialEvent } from "@/types/world";

export function LiveEventsBar() {
  const { data: events } = useApi<SocialEvent[]>("/api/events?limit=12", { interval: 10000 });
  const { data: games } = useApi<Game[]>("/api/games?status=active&limit=6", { interval: 8000 });
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(id);
  }, []);
  const upcoming = (events ?? []).filter((e) => e.status === "live" || e.status === "scheduled").sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  return (
    <div className="scroll-thin flex gap-3 overflow-x-auto pb-1">
      {upcoming.map((e) => (
        <Link key={e.id} href="/events" className="glass focus-ring flex min-w-[220px] shrink-0 items-center gap-3 px-4 py-3 transition hover:bg-white/[0.05]">
          <span className={e.status === "live" ? "h-2 w-2 animate-pulse2 rounded-full bg-rose-400" : "h-2 w-2 rounded-full bg-accent-amber/70"} />
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">{e.title}</span>
            <span className="block text-[11px] text-mist-500">
              {e.status === "live" ? "Live now" : untilLabel(e.starts_at, now)} · {e.room?.name} · {e.participants.filter((p) => p.status !== "declined").length} going
            </span>
          </span>
        </Link>
      ))}
      {(games ?? []).map((g) => (
        <Link key={g.id} href={`/games/${g.id}`} className="glass focus-ring flex min-w-[200px] shrink-0 items-center gap-3 px-4 py-3 transition hover:bg-white/[0.05]">
          <span className="text-lg text-accent-rose">♟</span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">{g.players.map((p) => p.name).join(" vs ")}</span>
            <span className="block text-[11px] text-mist-500">{g.game_type} · move {g.move_count}</span>
          </span>
        </Link>
      ))}
      {upcoming.length === 0 && (games ?? []).length === 0 && <span className="px-2 py-3 text-sm text-mist-500">No live events right now.</span>}
    </div>
  );
}
