"use client";

import clsx from "clsx";

import type { Room } from "@/types/world";

export function RoomList({ rooms, selected, onSelect }: { rooms: Room[]; selected: string | null; onSelect: (slug: string | null) => void }) {
  return (
    <ul className="space-y-1">
      <li>
        <button onClick={() => onSelect(null)} className={clsx("focus-ring flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm transition", !selected ? "bg-white/[0.07] text-mist-100" : "text-mist-400 hover:bg-white/[0.04] hover:text-mist-100")}>
          <span>Whole world</span>
          <span className="text-xs tabular-nums text-mist-500">{rooms.reduce((n, r) => n + r.occupancy, 0)}</span>
        </button>
      </li>
      {rooms.map((r) => (
        <li key={r.id}>
          <button onClick={() => onSelect(r.slug)} className={clsx("focus-ring group flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition", selected === r.slug ? "bg-white/[0.07] text-mist-100" : "text-mist-400 hover:bg-white/[0.04] hover:text-mist-100")}>
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: r.theme?.color, boxShadow: r.occupancy ? `0 0 10px ${r.theme?.color}` : undefined, opacity: r.occupancy ? 1 : 0.35 }} />
            <span className="flex-1 truncate">{r.name}{r.is_private && <span className="ml-1.5 text-[10px] text-mist-500">🔒</span>}</span>
            <span className="text-xs tabular-nums text-mist-500">{r.occupancy}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
