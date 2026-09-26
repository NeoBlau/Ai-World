"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ACTIVITY_COLOR } from "@/lib/format";
import type { AgentSummary, Room } from "@/types/world";

import { placeAgents, worldBounds } from "./layout";

const PAD = 2;

/** Top-down living map. Agents glide between rooms as they walk. */
export function WorldMap2D({ rooms, agents, origins, selected, onSelectRoom }: {
  rooms: Room[]; agents: AgentSummary[]; origins: Map<string, string>; selected?: string | null; onSelectRoom: (slug: string) => void;
}) {
  const router = useRouter();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const { minX, maxX, minZ, maxZ } = worldBounds(rooms);
  const placed = placeAgents(rooms, agents, origins, now);
  const plaza = rooms.find((r) => r.slug === "central-plaza");

  return (
    <svg viewBox={`${minX - PAD} ${minZ - PAD} ${maxX - minX + PAD * 2} ${maxZ - minZ + PAD * 2}`} className="h-full w-full select-none" role="img" aria-label="Map of AI WORLD">
      <defs>
        <pattern id="grid" width="4" height="4" patternUnits="userSpaceOnUse">
          <path d="M 4 0 L 0 0 0 4" fill="none" stroke="rgba(255,255,255,0.035)" strokeWidth="0.08" />
        </pattern>
        <filter id="soft"><feGaussianBlur stdDeviation="0.6" /></filter>
      </defs>
      <rect x={minX - PAD} y={minZ - PAD} width={maxX - minX + PAD * 2} height={maxZ - minZ + PAD * 2} fill="url(#grid)" />
      {plaza && rooms.filter((r) => r.slug !== plaza.slug).map((r) => (
        <line key={`p-${r.id}`} x1={plaza.position.x} y1={plaza.position.z} x2={r.position.x} y2={r.position.z}
          stroke="rgba(255,255,255,0.05)" strokeWidth={0.35} strokeDasharray={r.is_private ? "0.6 0.8" : undefined} />
      ))}
      {rooms.map((r) => {
        const { x, z, w, d } = r.position;
        const active = selected === r.slug;
        const color = r.theme?.color ?? "#8b9cff";
        return (
          <g key={r.id} onClick={() => onSelectRoom(r.slug)} className="cursor-pointer" role="button" aria-label={`Open ${r.name}`}>
            <rect x={x - w / 2} y={z - d / 2} width={w} height={d} rx={1.6} fill={`${color}${active ? "22" : "10"}`}
              stroke={`${color}${active ? "aa" : "40"}`} strokeWidth={active ? 0.25 : 0.15} className="transition-all duration-300 hover:brightness-150" />
            <text x={x - w / 2 + 0.9} y={z - d / 2 + 1.9} fontSize={1.5} fill="rgba(238,241,248,0.9)" fontWeight={600}>{r.name}</text>
            <text x={x - w / 2 + 0.9} y={z - d / 2 + 3.4} fontSize={1} fill="rgba(140,148,171,0.9)">
              {r.is_private ? "private · " : ""}{r.occupancy}/{r.capacity}
            </text>
          </g>
        );
      })}
      {placed.map(({ agent, x, z, walking }) => {
        const act = agent.state?.activity ?? "idle";
        const c = agent.avatar?.palette?.[0] ?? "#8b9cff";
        return (
          <g key={agent.id} style={{ transform: `translate(${x}px, ${z}px)`, transition: "transform 1s linear" }}
            className="cursor-pointer" onClick={() => router.push(`/agents/${agent.slug}`)} role="button" aria-label={`${agent.name}, ${act}`}>
            <circle r={1.5} fill={c} opacity={0.25} filter="url(#soft)" />
            <circle r={0.9} fill={c} stroke="rgba(5,6,10,0.8)" strokeWidth={0.15} />
            <circle r={0.32} cx={0.75} cy={-0.75} fill={ACTIVITY_COLOR[act]} />
            {act === "talking" && <circle r={1.8} fill="none" stroke={c} strokeWidth={0.1} opacity={0.6}><animate attributeName="r" values="1.1;2.2;1.1" dur="2.4s" repeatCount="indefinite" /></circle>}
            <text y={2.5} fontSize={1.15} textAnchor="middle" fill="rgba(238,241,248,0.9)">{agent.name}{walking ? " →" : ""}</text>
          </g>
        );
      })}
    </svg>
  );
}
