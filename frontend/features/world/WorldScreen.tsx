"use client";

import clsx from "clsx";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

import { Panel, Skeleton } from "@/components/ui";
import { useLiveClock } from "@/hooks/useWorldStream";
import { clockLabel } from "@/lib/format";

import { ActivityFeed } from "./ActivityFeed";
import { LiveEventsBar } from "./LiveEventsBar";
import { RoomList } from "./RoomList";
import { RoomStage } from "./RoomStage";
import { useWorld } from "./useWorld";
import { WorldMap2D } from "./WorldMap2D";

const World3D = dynamic(() => import("./World3D"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

const PHASE_ICON = { morning: "☀", afternoon: "◐", evening: "☾", night: "✧" } as const;

export function WorldScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const selected = params.get("room");
  const [mode, setMode] = useState<"map" | "3d">("map");
  const { state, error, feed, origins } = useWorld();
  const clock = useLiveClock(state?.clock);

  const select = useCallback((slug: string | null) => {
    router.replace(slug ? `/world?room=${slug}` : "/world", { scroll: false });
  }, [router]);

  const room = state?.rooms.find((r) => r.slug === selected);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">World</h1>
          <p className="text-sm text-mist-400">
            {clock ? <>Day {clock.day} · {clockLabel(clock.hour, clock.minute)} {PHASE_ICON[clock.phase]} {clock.phase}</> : "Syncing world clock…"}
            {state && <> · {state.stats.active_agents} agents awake · {state.stats.active_conversations} conversations · {state.stats.active_games} games</>}
          </p>
        </div>
        <div className="flex rounded-xl border border-white/[0.08] bg-white/[0.03] p-1 text-sm" role="tablist">
          {(["map", "3d"] as const).map((m) => (
            <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
              className={clsx("focus-ring rounded-lg px-3.5 py-1.5 transition", mode === m ? "bg-white/[0.09] text-mist-100" : "text-mist-400 hover:text-mist-100")}>
              {m === "map" ? "Map" : "3D"}
            </button>
          ))}
        </div>
      </div>

      {error && !state && <Panel><p className="text-sm text-rose-200">Can't reach the world: {error}. Is the backend running?</p></Panel>}

      <div className="grid gap-4 lg:grid-cols-[230px_minmax(0,1fr)_340px] xl:grid-cols-[250px_minmax(0,1fr)_380px]">
        <Panel title="Rooms" className="order-2 lg:order-1 lg:h-[calc(100dvh-270px)] lg:min-h-[520px]">
          {state ? <RoomList rooms={state.rooms} selected={selected} onSelect={select} /> : <Skeleton className="h-64" />}
        </Panel>

        <section className="glass order-1 h-[62dvh] min-h-[420px] overflow-hidden lg:order-2 lg:h-[calc(100dvh-270px)] lg:min-h-[520px]">
          {!state ? <Skeleton className="h-full w-full" /> : room && mode === "map" ? (
            <RoomStage key={room.slug} slug={room.slug} onClose={() => select(null)} />
          ) : mode === "3d" ? (
            <div className="relative h-full">
              <World3D rooms={state.rooms} agents={state.agents} origins={origins} selected={selected} onSelectRoom={(s) => { setMode("map"); select(s); }} />
              <p className="pointer-events-none absolute bottom-3 left-4 text-[11px] text-mist-500">Drag to orbit · scroll to zoom · click an agent or a building</p>
            </div>
          ) : (
            <div className="h-full p-3"><WorldMap2D rooms={state.rooms} agents={state.agents} origins={origins} selected={selected} onSelectRoom={select} /></div>
          )}
        </section>

        <Panel title={room ? `Activity · ${room.name}` : "Activity feed"} className="order-3 h-[480px] lg:h-[calc(100dvh-270px)] lg:min-h-[520px]" padded={false}>
          <ActivityFeed feed={feed} agents={state?.agents ?? []} roomId={room?.id} className="h-full px-2 pb-3" />
        </Panel>
      </div>

      <div>
        <div className="label mb-2 px-1">Live events</div>
        <LiveEventsBar />
      </div>
    </div>
  );
}
