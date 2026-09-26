"use client";

import { Badge } from "@/components/ui";
import { timeAgo } from "@/lib/format";
import type { Memory } from "@/types/world";

const TYPE_COLOR: Record<Memory["type"], string> = {
  short_term: "#8c94ab", long_term: "#b18cff", episodic: "#8b9cff", semantic: "#6ff0b8", social: "#ff8fb3",
};

export function MemoryList({ memories, empty = "No memories yet." }: { memories: Memory[]; empty?: string }) {
  if (!memories.length) return <p className="py-6 text-center text-sm text-mist-500">{empty}</p>;
  return (
    <ul className="space-y-2">
      {memories.map((m) => (
        <li key={m.id} className="rounded-xl border border-white/[0.05] bg-white/[0.02] px-4 py-3">
          <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11px] text-mist-500">
            <Badge color={TYPE_COLOR[m.type]}>{m.type.replace("_", "-")}</Badge>
            <span>importance {m.importance.toFixed(0)}</span>
            {m.score !== null && <span>· match {(m.score * 100).toFixed(0)}%</span>}
            <span>· {timeAgo(m.created_at)}</span>
            {m.is_archived && <span>· archived</span>}
          </div>
          <p className="text-sm leading-relaxed text-mist-300">{m.content}</p>
        </li>
      ))}
    </ul>
  );
}
