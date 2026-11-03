import { useCallback, useEffect, useRef, useState } from "react";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export const DEMO = import.meta.env.VITE_DEMO === "1";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (import.meta.env.VITE_DEMO === "1") {
    const { demoFetch } = await import("./demo/mock");   // dead code (removed) in the normal build
    return demoFetch(path, init) as Promise<T>;
  }
  const res = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const j = await res.json(); if (j?.detail) msg = typeof j.detail === "string" ? j.detail : msg; } catch { /* ignore */ }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  const load = useCallback(async (p: string | null = path) => {
    if (!p) return;
    const id = ++seq.current;
    setLoading(true); setError(null);
    try {
      const d = await api<T>(p);
      if (id === seq.current) setData(d);
    } catch (e) {
      if (id === seq.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [path]);
  useEffect(() => { setData(null); load(path); }, [path, load]);
  return { data, error, loading, reload: () => load(path), setData };
}
