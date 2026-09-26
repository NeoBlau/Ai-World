import type { AgentSummary, Room } from "@/types/world";

/** Deterministic spot for an agent inside a room (shared by the 2D map and the 3D world). */
export function spotInRoom(room: Room, agentId: string, index: number): { x: number; z: number } {
  const { x, z, w, d } = room.position;
  let h = 0;
  for (let i = 0; i < agentId.length; i++) h = (h * 31 + agentId.charCodeAt(i)) >>> 0;
  const cols = Math.max(2, Math.floor(w / 3));
  const col = (index + (h % 3)) % cols;
  const row = Math.floor(index / cols);
  const jitter = ((h % 100) / 100 - 0.5) * 0.8;
  return { x: x - w / 2 + 1.6 + col * ((w - 3.2) / Math.max(1, cols - 1)) + jitter, z: z - d / 2 + 5.2 + (row * 2.6) % Math.max(2.6, d - 6) + jitter * 0.5 };
}

export interface Placed {
  agent: AgentSummary;
  x: number;
  z: number;
  walking: boolean;
}

/** Compute world positions for every agent; walking agents are interpolated between rooms. */
export function placeAgents(rooms: Room[], agents: AgentSummary[], origins: Map<string, string>, now: number = Date.now()): Placed[] {
  const bySlug = new Map(rooms.map((r) => [r.slug, r]));
  const counters = new Map<string, number>();
  const out: Placed[] = [];
  for (const a of agents) {
    const st = a.state;
    if (!st) continue;
    if (st.location) {
      const room = bySlug.get(st.location.slug);
      if (!room) continue;
      const i = counters.get(room.slug) ?? 0;
      counters.set(room.slug, i + 1);
      out.push({ agent: a, ...spotInRoom(room, a.id, i), walking: false });
    } else if (st.destination) {
      const dest = bySlug.get(st.destination.slug);
      const originSlug = origins.get(a.id);
      const origin = originSlug ? bySlug.get(originSlug) : bySlug.get("central-plaza");
      if (!dest || !origin) continue;
      const total = 14_000;
      const remaining = st.arrive_at ? Math.max(0, new Date(st.arrive_at).getTime() - now) : 0;
      const t = Math.min(1, Math.max(0, 1 - remaining / total));
      out.push({
        agent: a,
        x: origin.position.x + (dest.position.x - origin.position.x) * t,
        z: origin.position.z + (dest.position.z - origin.position.z) * t,
        walking: true,
      });
    }
  }
  return out;
}

export function worldBounds(rooms: Room[]) {
  if (!rooms.length) return { minX: -40, maxX: 36, minZ: -36, maxZ: 36 };
  return {
    minX: Math.min(...rooms.map((r) => r.position.x - r.position.w / 2)) - 1,
    maxX: Math.max(...rooms.map((r) => r.position.x + r.position.w / 2)) + 1,
    minZ: Math.min(...rooms.map((r) => r.position.z - r.position.d / 2)) - 1,
    maxZ: Math.max(...rooms.map((r) => r.position.z + r.position.d / 2)) + 2,
  };
}
