"use client";

import { useEffect, useRef, useState } from "react";

import { WS_URL } from "@/lib/config";
import type { Clock, WorldEvent } from "@/types/world";

type Listener = (e: WorldEvent) => void;

/** Shared WebSocket connection with automatic reconnect (one per tab). */
class WorldSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private clockListeners = new Set<(c: Clock) => void>();
  private statusListeners = new Set<(s: boolean) => void>();
  private retry = 0;
  private timer: number | null = null;
  connected = false;

  subscribe(l: Listener) {
    this.listeners.add(l);
    this.ensure();
    return () => void this.listeners.delete(l);
  }
  onClock(l: (c: Clock) => void) {
    this.clockListeners.add(l);
    return () => void this.clockListeners.delete(l);
  }
  onStatus(l: (s: boolean) => void) {
    this.statusListeners.add(l);
    l(this.connected);
    this.ensure();
    return () => void this.statusListeners.delete(l);
  }

  private setConnected(v: boolean) {
    this.connected = v;
    this.statusListeners.forEach((l) => l(v));
  }

  private ensure() {
    if (typeof window === "undefined" || this.ws) return;
    const ws = new WebSocket(WS_URL);
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.setConnected(true);
    };
    ws.onmessage = (msg) => {
      let data: unknown;
      try {
        data = JSON.parse(String(msg.data));
      } catch {
        return;
      }
      const ev = data as WorldEvent & { payload: unknown };
      if (ev.type === "world.clock") {
        this.clockListeners.forEach((l) => l(ev.payload as unknown as Clock));
        return;
      }
      if (ev.type === "hello" || ev.type === "pong") return;
      this.listeners.forEach((l) => l(ev));
    };
    ws.onclose = () => {
      this.ws = null;
      this.setConnected(false);
      const delay = Math.min(15000, 800 * 2 ** this.retry++);
      if (this.timer) window.clearTimeout(this.timer);
      this.timer = window.setTimeout(() => this.ensure(), delay);
    };
    ws.onerror = () => ws.close();
  }
}

let socket: WorldSocket | null = null;
function getSocket(): WorldSocket {
  if (!socket) socket = new WorldSocket();
  return socket;
}

export function useWorldEvents(onEvent: Listener): void {
  const ref = useRef(onEvent);
  ref.current = onEvent;
  useEffect(() => getSocket().subscribe((e) => ref.current(e)), []);
}

export function useConnection(): boolean {
  const [ok, setOk] = useState(false);
  useEffect(() => getSocket().onStatus(setOk), []);
  return ok;
}

export function useLiveClock(initial?: Clock): Clock | undefined {
  const [clock, setClock] = useState<Clock | undefined>(initial);
  useEffect(() => setClock((c) => c ?? initial), [initial]);
  useEffect(() => getSocket().onClock(setClock), []);
  return clock;
}
