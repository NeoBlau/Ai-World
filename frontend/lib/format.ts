import type { ActivityKind } from "@/types/world";

export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export function untilLabel(iso: string, now: number = Date.now()): string {
  const s = Math.round((new Date(iso).getTime() - now) / 1000);
  if (s <= 0) return "now";
  if (s < 60) return `in ${s}s`;
  const m = Math.round(s / 60);
  return m < 60 ? `in ${m} min` : `in ${Math.round(m / 60)} h`;
}

export const ACTIVITY_LABEL: Record<ActivityKind, string> = {
  idle: "Idle", talking: "Talking", walking: "Walking", playing: "Playing", watching: "Watching", reading: "Reading",
  creating: "Creating", thinking: "Thinking", resting: "Resting", attending_event: "At an event",
};

export const ACTIVITY_COLOR: Record<ActivityKind, string> = {
  idle: "#8c94ab", talking: "#8b9cff", walking: "#5ee6f0", playing: "#ff8fb3", watching: "#f0abfc", reading: "#6ff0b8",
  creating: "#b18cff", thinking: "#ffc876", resting: "#64748b", attending_event: "#fcd34d",
};

export const PROVIDER_LABEL: Record<string, string> = {
  openai: "OpenAI", anthropic: "Anthropic", gemini: "Gemini", ollama: "Ollama", sim: "Offline sim",
};

export function clockLabel(hour: number, minute: number): string {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

/** Icon-ish glyph for world events. */
export function eventGlyph(type: string): string {
  if (type.startsWith("message") || type.includes("conversation") || type === "agent.met") return "💬";
  if (type.includes("room") || type === "agent.walking") return "➜";
  if (type.includes("game")) return "♟";
  if (type.includes("topic")) return "✎";
  if (type.startsWith("event") || type.includes("event")) return "✦";
  if (type.includes("art") || type.includes("note")) return "✧";
  if (type.includes("book")) return "❏";
  if (type.startsWith("human")) return "◉";
  if (type.includes("invit")) return "✉";
  return "·";
}
