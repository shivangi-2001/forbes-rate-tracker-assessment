"use client";

import { useState, useEffect, useCallback, useRef } from "react";

interface UseAutoRefreshOptions<T> {
  fetcher: () => Promise<T>;
  intervalMs?: number;
}

interface UseAutoRefreshResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  refresh: () => void;
}

export function useAutoRefresh<T>({
  fetcher,
  intervalMs = 60_000,
}: UseAutoRefreshOptions<T>): UseAutoRefreshResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetch_ = useCallback(async () => {
    try {
      setError(null);
      const result = await fetcher();
      setData(result);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    fetch_();
    timerRef.current = setInterval(fetch_, intervalMs);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetch_, intervalMs]);

  return { data, loading, error, lastUpdated, refresh: fetch_ };
}
