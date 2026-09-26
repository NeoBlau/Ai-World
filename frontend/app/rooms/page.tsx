"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Badge, Button, ErrorNote, Field, Input, PageHeader, Panel, Skeleton, Textarea } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import type { Room } from "@/types/world";

export default function RoomsPage() {
  const { data, reload } = useApi<Room[]>("/api/world/rooms", { interval: 6000 });
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", is_private: true, capacity: 6 });
  const [err, setErr] = useState<string | null>(null);

  async function create() {
    setErr(null);
    try {
      await api("/api/world/rooms", { method: "POST", json: form });
      setOpen(false);
      setForm({ name: "", description: "", is_private: true, capacity: 6 });
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div>
      <PageHeader eyebrow="Places" title="Rooms" subtitle="Every location has its own mood, capacity and set of things you can do there."
        action={user && <Button onClick={() => setOpen((o) => !o)}>{open ? "Close" : "Create room"}</Button>} />
      {open && (
        <Panel className="mb-6">
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void create(); }}>
            <Field label="Name"><Input required minLength={3} maxLength={60} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Capacity"><Input type="number" min={2} max={40} value={form.capacity} onChange={(e) => setForm({ ...form, capacity: Number(e.target.value) })} /></Field>
            <div className="sm:col-span-2"><Field label="Description"><Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field></div>
            <label className="flex items-center gap-2 text-sm text-mist-300"><input type="checkbox" checked={form.is_private} onChange={(e) => setForm({ ...form, is_private: e.target.checked })} className="accent-[#8b9cff]" /> Private (invitation only)</label>
            <div className="flex justify-end"><Button type="submit">Create</Button></div>
            {err && <div className="sm:col-span-2"><ErrorNote>{err}</ErrorNote></div>}
          </form>
        </Panel>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {!data && Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-44" />)}
        {data?.map((r) => (
          <Link key={r.id} href={`/world?room=${r.slug}`} className="glass focus-ring group relative overflow-hidden p-6 transition hover:-translate-y-0.5 hover:bg-white/[0.045]">
            <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full opacity-25 blur-2xl transition group-hover:opacity-40" style={{ background: r.theme?.color }} />
            <div className="relative">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">{r.name}</h3>
                <Badge color={r.theme?.color}>{r.occupancy}/{r.capacity}</Badge>
              </div>
              <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-mist-400">{r.description}</p>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {r.is_private && <Badge>🔒 private</Badge>}
                {r.allowed_actions.slice(0, 5).map((a) => <Badge key={a}>{a.replace("_", " ")}</Badge>)}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
