"use client";

import { useState, useCallback, useEffect } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { Rate, fetchLatestRates, fetchRateHistory } from "@/lib/api";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import styles from "./RateHistoryChart.module.css";

function getThirtyDaysAgo() {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().split("T")[0];
}

function LoadingSkeleton() {
  return (
    <div className={styles.loadingState} aria-busy="true" aria-label="Loading chart">
      <div className={styles.skeletonChart}>
        {[40, 65, 50, 80, 60, 90, 55, 75, 45, 85, 70, 95].map((h, i) => (
          <div
            key={i}
            className={styles.skeletonBar}
            style={{ height: `${h}%` }}
          />
        ))}
      </div>
      <div className={styles.skeletonLabel} />
    </div>
  );
}

export default function RateHistoryChart() {
  const [provider, setProvider] = useState("");
  const [rateType, setRateType] = useState("");
  const [providers, setProviders] = useState<string[]>([]);
  const [rateTypes, setRateTypes] = useState<string[]>([]);

  // Populate dropdowns from real API data
  useEffect(() => {
    fetchLatestRates({ pageSize: 200 }).then((res) => {
      const ps = Array.from(new Set(res.results.map((r) => r.provider_name))).sort();
      const ts = Array.from(new Set(res.results.map((r) => r.rate_type))).sort();
      setProviders(ps);
      setRateTypes(ts);
      if (ps.length > 0) setProvider(ps[0]);
      if (ts.length > 0) setRateType(ts[0]);
    }).catch((err) => {
      console.error("Failed to load providers/types:", err);
    });
  }, []);

  const fetcher = useCallback(() => {
    if (!provider || !rateType) return Promise.resolve([]);
    return fetchRateHistory(provider, rateType, getThirtyDaysAgo()).then((r) =>
      r.results.map((rate: Rate) => ({
        date: rate.effective_date,
        rate: parseFloat(rate.rate_value),
      }))
    );
  }, [provider, rateType]);

  const { data, loading, error, lastUpdated, refresh } = useAutoRefresh<
    { date: string; rate: number }[]
  >({ fetcher, intervalMs: 60_000 });

  const hasData = data && data.length > 0;
  const isInitialLoad = loading && !data;

  return (
    <section className={styles.section}>
      <div className={styles.toolbar}>
        <h2 className={styles.heading}>30-day rate history</h2>
        <div className={styles.controls}>
          <select
            className={styles.select}
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            aria-label="Select provider"
            disabled={loading || providers.length === 0}
          >
            {providers.length === 0
              ? <option>Loading…</option>
              : providers.map((p) => <option key={p} value={p}>{p}</option>)
            }
          </select>
          <select
            className={styles.select}
            value={rateType}
            onChange={(e) => setRateType(e.target.value)}
            aria-label="Select rate type"
            disabled={loading || rateTypes.length === 0}
          >
            {rateTypes.length === 0
              ? <option>Loading…</option>
              : rateTypes.map((t) => <option key={t} value={t}>{t}</option>)
            }
          </select>
          <button
            className={styles.refreshBtn}
            onClick={refresh}
            disabled={loading || !provider}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {lastUpdated && (
        <p className={styles.timestamp}>
          Last updated: {lastUpdated.toLocaleTimeString()} · auto-refresh every 60s
        </p>
      )}

      {/* Initial skeleton — shown only on first load before any data */}
      {isInitialLoad && <LoadingSkeleton />}

      {/* Error state — full block, always visible, not overlaid */}
      {error && (
        <div className={styles.errorState} role="alert">
          <div className={styles.errorTitle}>Failed to load chart data</div>
          <div className={styles.errorMessage}>{error}</div>
          <button className={styles.retryBtn} onClick={refresh}>Try again</button>
        </div>
      )}

      {/* Empty state */}
      {!isInitialLoad && !error && !loading && (!data || data.length === 0) && (
        <div className={styles.emptyState}>
          No data found for <strong>{provider}</strong> · <strong>{rateType}</strong> in the last 30 days.
        </div>
      )}

      {/* Chart — dims during background refresh, stays visible */}
      {!error && hasData && (
        <div
          className={styles.chartArea}
          style={{ opacity: loading ? 0.6 : 1, transition: "opacity 0.2s" }}
        >
          <ResponsiveContainer width="100%" height={320}>
            <LineChart
              data={data}
              margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => v.slice(5)}
                minTickGap={20}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `${Number(v).toFixed(2)}%`}
                width={62}
              />
              <Tooltip
                formatter={(v: number) => [`${Number(v).toFixed(3)}%`, "Rate"]}
                labelFormatter={(l) => `Date: ${l}`}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="rate"
                name={`${provider} · ${rateType}`}
                stroke="#6366f1"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}