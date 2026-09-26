"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { useWorldEvents } from "@/hooks/useWorldStream";
import type { WorldEvent, WorldState } from "@/types/world";

const STATE_EVENTS = /^(agent\.|game\.|event\.|human\.entered|room\.)/;

/** Live world state: initial fetch + debounced refresh whenever the world changes. */
export function useWorld() {
  const [state, setState] = useState<WorldState>();
  const [error, setError] = useState<string | null>(null);
  const [feed, setFeed] = useState<WorldEvent[]>([]);
  const origins = useRef(new Map<string, string>());
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await api<WorldState>("/api/world/state");
      for (const a of s.agents) if (a.state?.location) origins.current.set(a.id, a.state.location.slug);
      setState(s);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "World unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
    api<WorldEvent[]>("/api/world/feed?limit=60").then(setFeed).catch(() => undefined);
    const id = window.setInterval(() => void load(), 8000);
    return () => window.clearInterval(id);
  }, [load]);

  useWorldEvents((ev) => {
    if (ev.type === "agent.thinking") return;
    setFeed((f) => (f.some((x) => x.id === ev.id) ? f : [ev, ...f].slice(0, 150)));
    if (STATE_EVENTS.test(ev.type) && timer.current === null) {
      timer.current = window.setTimeout(() => {
        timer.current = null;
        void load();
      }, 700);
    }
  });

  return { state, error, feed, origins: origins.current, reload: load };
}
