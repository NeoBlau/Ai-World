import Link from "next/link";

import { AgentAvatar } from "@/components/AgentAvatar";
import { Badge } from "@/components/ui";
import type { Relationship } from "@/types/world";

function Bar({ label, value, min = 0, color }: { label: string; value: number; min?: number; color: string }) {
  const pct = ((value - min) / (100 - min)) * 100;
  return (
    <div className="flex items-center gap-2 text-[11px] text-mist-500">
      <span className="w-16">{label}</span>
      <span className="h-1 flex-1 overflow-hidden rounded-full bg-white/[0.06]"><span className="block h-full rounded-full" style={{ width: `${pct}%`, background: color }} /></span>
      <span className="w-8 text-right tabular-nums text-mist-400">{Math.round(value)}</span>
    </div>
  );
}

export function RelationshipList({ items }: { items: Relationship[] }) {
  if (!items.length) return <p className="py-6 text-center text-sm text-mist-500">Hasn't met anyone yet.</p>;
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {items.map((r) => r.other_agent && (
        <li key={r.other_agent.id} className="rounded-xl border border-white/[0.05] bg-white/[0.02] p-4">
          <Link href={`/agents/${r.other_agent.slug}`} className="mb-3 flex items-center gap-3">
            <AgentAvatar avatar={r.other_agent.avatar} name={r.other_agent.name} size={34} />
            <span className="font-medium">{r.other_agent.name}</span>
            <Badge className="ml-auto">{r.label}</Badge>
          </Link>
          <div className="space-y-1.5">
            <Bar label="familiarity" value={r.familiarity} color="#8b9cff" />
            <Bar label="friendship" value={r.friendship} min={-100} color="#6ff0b8" />
            <Bar label="trust" value={r.trust} color="#5ee6f0" />
            <Bar label="respect" value={r.respect} color="#ffc876" />
            {r.conflict > 0 && <Bar label="conflict" value={r.conflict} color="#ff8fb3" />}
          </div>
          {r.shared_history.length > 0 && <p className="mt-3 truncate text-[11px] text-mist-500">Last: {r.shared_history[r.shared_history.length - 1].note}</p>}
        </li>
      ))}
    </ul>
  );
}
