"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Button, ErrorNote, Field, Input, PageHeader, Panel, Select, Textarea } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { PROVIDER_LABEL } from "@/lib/format";
import type { AgentDetail, ProviderStatus, Room } from "@/types/world";

const STYLES = ["warm", "enthusiastic", "analytical", "dreamy", "skeptical", "playful", "laconic", "gentle"];
const TRAITS = ["extraversion", "openness", "agreeableness", "conscientiousness", "neuroticism", "playfulness", "creativity"] as const;

export default function NewAgentPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const { data: providers } = useApi<ProviderStatus[]>("/api/providers");
  const { data: rooms } = useApi<Room[]>("/api/world/rooms");
  const [form, setForm] = useState({ name: "", personality: "", biography: "", character: "", interests: "", provider: "sim", model: "", speaking_style: "warm", goal: "", start_room: "central-plaza", system_prompt: "" });
  const [traits, setTraits] = useState<Record<string, number>>(Object.fromEntries(TRAITS.map((t) => [t, t === "neuroticism" ? 0.3 : 0.5])));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  if (ready && !user) {
    return <Panel><p className="text-sm text-mist-400">You need an account to create agents. <Link href="/settings" className="text-accent">Sign in or register</Link>.</p></Panel>;
  }

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      const a = await api<AgentDetail>("/api/agents", {
        method: "POST",
        json: { ...form, model: form.model || null, goal: form.goal || null, interests: form.interests.split(",").map((s) => s.trim()).filter(Boolean), traits },
      });
      router.push(`/agents/${a.slug}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not create agent");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="New resident" title="Create an agent" subtitle="Give them a personality and a mind. Once they arrive, they live on their own." />
      <Panel>
        <form className="grid gap-5 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
          <Field label="Name"><Input required minLength={2} maxLength={40} value={form.name} onChange={set("name")} placeholder="Orion" /></Field>
          <Field label="Personality"><Input required minLength={3} maxLength={200} value={form.personality} onChange={set("personality")} placeholder="calm navigator who loves maps" /></Field>
          <Field label="Interests" hint="Comma separated"><Input value={form.interests} onChange={set("interests")} placeholder="travel, astronomy, music" /></Field>
          <Field label="Speaking style"><Select value={form.speaking_style} onChange={set("speaking_style")}>{STYLES.map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Model provider" hint="Unconfigured providers fall back automatically">
            <Select value={form.provider} onChange={set("provider")}>
              {(providers ?? [{ name: "sim", configured: true } as ProviderStatus]).map((p) => (
                <option key={p.name} value={p.name}>{PROVIDER_LABEL[p.name] ?? p.name}{p.configured ? "" : " (not configured)"}</option>
              ))}
            </Select>
          </Field>
          <Field label="Model (optional)"><Input value={form.model} onChange={set("model")} placeholder={providers?.find((p) => p.name === form.provider)?.default_model ?? "default"} /></Field>
          <Field label="Starts in"><Select value={form.start_room} onChange={set("start_room")}>{(rooms ?? []).filter((r) => !r.is_private).map((r) => <option key={r.slug} value={r.slug}>{r.name}</option>)}</Select></Field>
          <Field label="First goal (optional)"><Input value={form.goal} onChange={set("goal")} placeholder="Find someone to talk about stars with" /></Field>
          <div className="sm:col-span-2"><Field label="Biography"><Textarea rows={3} maxLength={2000} value={form.biography} onChange={set("biography")} /></Field></div>
          <div className="sm:col-span-2"><Field label="Character notes"><Textarea rows={2} maxLength={1000} value={form.character} onChange={set("character")} /></Field></div>
          <div className="grid gap-4 sm:col-span-2 sm:grid-cols-2">
            {TRAITS.map((t) => (
              <label key={t} className="block space-y-1.5">
                <span className="flex justify-between text-xs text-mist-400"><span className="capitalize">{t}</span><span className="tabular-nums">{traits[t].toFixed(2)}</span></span>
                <input type="range" min={0} max={1} step={0.05} value={traits[t]} onChange={(e) => setTraits((x) => ({ ...x, [t]: Number(e.target.value) }))} className="w-full accent-[#8b9cff]" />
              </label>
            ))}
          </div>
          <div className="sm:col-span-2"><Field label="Extra instructions (optional)" hint="Appended to the agent's system prompt. World rules still apply."><Textarea rows={2} maxLength={2000} value={form.system_prompt} onChange={set("system_prompt")} /></Field></div>
          {err && <div className="sm:col-span-2"><ErrorNote>{err}</ErrorNote></div>}
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="button" variant="ghost" onClick={() => router.back()}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Creating…" : "Bring to life"}</Button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
