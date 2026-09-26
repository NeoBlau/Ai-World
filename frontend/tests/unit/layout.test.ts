import { placeAgents, spotInRoom, worldBounds } from "@/features/world/layout";
import type { AgentSummary, Room } from "@/types/world";

const room = (slug: string, x: number, z: number): Room => ({
  id: slug, slug, name: slug, description: "", kind: "plaza", capacity: 10, allowed_actions: [], is_private: false,
  position: { x, z, w: 12, d: 10 }, theme: { color: "#fff", icon: "" }, ambience: [], occupancy: 0, agents: [],
});
const agent = (id: string, state: Partial<NonNullable<AgentSummary["state"]>>): AgentSummary => ({
  id, slug: id, name: id, avatar: { glyph: "A", palette: [], shape: "orb" }, provider: "sim", model: "m", personality: "", interests: [],
  status: "active", speaking_style: "warm", is_seed: true,
  state: { energy: 50, social_need: 50, curiosity: 50, playfulness: 50, creativity: 50, mood: "calm", activity: "idle", activity_detail: null,
    availability: "available", location: null, destination: null, arrive_at: null, current_goal: null, last_action: null, last_action_at: null,
    last_provider: null, last_model: null, conversation_id: null, game_id: null, event_id: null, ...state },
});

describe("world layout", () => {
  const rooms = [room("central-plaza", 0, 0), room("library", 20, 0)];
  it("keeps agents inside their room", () => {
    const p = spotInRoom(rooms[1], "abc", 0);
    expect(p.x).toBeGreaterThan(14);
    expect(p.x).toBeLessThan(26);
  });
  it("interpolates walking agents between rooms", () => {
    const now = Date.now();
    const walking = agent("w", { activity: "walking", destination: { id: "library", slug: "library", name: "Library" }, arrive_at: new Date(now + 7000).toISOString() });
    const [placed] = placeAgents(rooms, [walking], new Map([["w", "central-plaza"]]), now);
    expect(placed.walking).toBe(true);
    expect(placed.x).toBeGreaterThan(0);
    expect(placed.x).toBeLessThan(20);
  });
  it("computes bounds around rooms", () => {
    const b = worldBounds(rooms);
    expect(b.minX).toBeLessThan(-6);
    expect(b.maxX).toBeGreaterThan(26);
  });
});
