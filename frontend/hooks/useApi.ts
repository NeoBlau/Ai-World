"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";

export interface ApiState<T> {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (fn: (prev: T | undefined) => T | undefined) => void;
}

/** Fetch JSON from the API, optionally polling. `path=null` disables the request. */
export function useApi<T>(path: string | null, opts: { interval?: number } = {}): ApiState<T> {
  const [data, setDataState] = useState<T | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(path !== null);
  const pathRef = useRef(path);
  pathRef.current = path;

  const reload = useCallback(async () => {
    const p = pathRef.current;
    if (!p) return;
    try {
      const d = await api<T>(p);
      if (pathRef.current === p) {
        setDataState(d);
        setError(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!path) return;
    setLoading(true);
    void reload();
    if (!opts.interval) return;
    const id = window.setInterval(() => void reload(), opts.interval);
    return () => window.clearInterval(id);
  }, [path, opts.interval, reload]);

  const setData = useCallback((fn: (prev: T | undefined) => T | undefined) => setDataState((p) => fn(p)), []);
  return { data, error, loading, reload, setData };
}
