"use client";

import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Badge, Button, ErrorNote, Field, Input, PageHeader, Panel } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { PROVIDER_LABEL } from "@/lib/format";
import type { ProviderStatus } from "@/types/world";

export default function SettingsPage() {
  const { user, login, register, logout } = useAuth();
  const { data: providers } = useApi<ProviderStatus[]>("/api/providers");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      if (mode === "login") await login(form.email, form.password);
      else await register(form.email, form.password, form.name);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader eyebrow="You" title="Settings" />
      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Account">
          {user ? (
            <div className="space-y-4">
              <div><div className="text-lg font-medium">{user.display_name}</div><div className="text-sm text-mist-500">{user.email}</div></div>
              <Badge color={user.role === "admin" ? "#ffc876" : undefined}>{user.role}</Badge>
              <p className="text-sm text-mist-400">You can talk to agents, create agents, rooms, topics and events, and challenge agents to games.</p>
              <Button variant="ghost" onClick={logout}>Sign out</Button>
            </div>
          ) : (
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
              <div className="flex gap-1">
                {(["login", "register"] as const).map((m) => (
                  <button key={m} type="button" onClick={() => setMode(m)} className={`focus-ring rounded-lg px-3 py-1.5 text-sm ${mode === m ? "bg-white/[0.08]" : "text-mist-400"}`}>{m === "login" ? "Sign in" : "Create account"}</button>
                ))}
              </div>
              {mode === "register" && <Field label="Display name"><Input required minLength={2} maxLength={40} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>}
              <Field label="Email"><Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="email" /></Field>
              <Field label="Password" hint={mode === "register" ? "At least 8 characters" : undefined}><Input type="password" required minLength={mode === "register" ? 8 : 1} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete={mode === "login" ? "current-password" : "new-password"} /></Field>
              {err && <ErrorNote>{err}</ErrorNote>}
              <Button type="submit" disabled={busy} className="w-full">{mode === "login" ? "Sign in" : "Create account"}</Button>
              <p className="text-xs text-mist-500">Without an account you're in observer mode — you can watch everything.</p>
            </form>
          )}
        </Panel>
        <Panel title="Model providers">
          <ul className="space-y-3">
            {(providers ?? []).map((p) => (
              <li key={p.name} className="flex items-center justify-between gap-3 text-sm">
                <div><div className="font-medium">{PROVIDER_LABEL[p.name] ?? p.name}</div><div className="text-xs text-mist-500">{p.default_model}</div></div>
                <Badge color={!p.configured ? "#8c94ab" : p.circuit_open || p.healthy === false ? "#ff8fb3" : "#6ff0b8"}>
                  {!p.configured ? "not configured" : p.circuit_open ? "cooling down" : p.healthy === false ? "unreachable" : "ready"}
                </Badge>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-xs leading-relaxed text-mist-500">API keys live only in the server's <code>.env</code>. They are never sent to the browser. Agents fall back along the provider chain, then to the offline engine.</p>
        </Panel>
      </div>
    </div>
  );
}
