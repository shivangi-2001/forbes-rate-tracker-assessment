"use client";

import { useState, useMemo, useCallback } from "react";
import { Rate, PaginatedResponse, fetchLatestRates } from "@/lib/api";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import styles from "./RatesTable.module.css";

type SortKey = "provider_name" | "rate_type" | "rate_value" | "effective_date";
type SortDir = "asc" | "desc";

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

function LoadingSkeleton() {
  return (
    <div className={styles.loadingState} aria-busy="true" aria-label="Loading rates">
      {[100, 85, 90, 75, 95, 80].map((w, i) => (
        <div key={i} className={styles.skeletonRow} style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}

export default function RatesTable() {
  const [sortKey, setSortKey] = useState<SortKey>("provider_name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [typeFilter, setTypeFilter] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const fetcher = useCallback(
    () => fetchLatestRates({ type: typeFilter || undefined, page, pageSize }),
    [typeFilter, page, pageSize]
  );

  const { data, loading, error, lastUpdated, refresh } =
    useAutoRefresh<PaginatedResponse<Rate>>({
      fetcher,
      intervalMs: 60_000,
    });

  const sorted = useMemo(() => {
    if (!data) return [];
    return [...data.results].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir]);

  const uniqueTypes = useMemo(
    () => Array.from(new Set((data?.results ?? []).map((r) => r.rate_type))).sort(),
    [data]
  );

  const totalPages = data?.total_pages ?? 1;
  const totalCount = data?.count ?? 0;
  const currentPage = data?.page ?? page;
  const startRow = totalCount === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endRow = Math.min(currentPage * pageSize, totalCount);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function arrow(key: SortKey) {
    if (key !== sortKey) return " ↕";
    return sortDir === "asc" ? " ↑" : " ↓";
  }

  function handleFilterChange(value: string) {
    setTypeFilter(value);
    setPage(1);
  }

  function handlePageSizeChange(value: number) {
    setPageSize(value);
    setPage(1);
  }

  return (
    <section className={styles.section}>
      <div className={styles.toolbar}>
        <h2 className={styles.heading}>Latest rates by provider</h2>
        <div className={styles.controls}>
          <select
            className={styles.select}
            value={typeFilter}
            onChange={(e) => handleFilterChange(e.target.value)}
            aria-label="Filter by rate type"
            disabled={loading}
          >
            <option value="">All types</option>
            {uniqueTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <button className={styles.refreshBtn} onClick={refresh} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh now"}
          </button>
        </div>
      </div>

      {lastUpdated && (
        <p className={styles.timestamp}>
          Last updated: {lastUpdated.toLocaleTimeString()} · auto-refresh every 60s
        </p>
      )}

      {loading && !data && <LoadingSkeleton />}

      {error && (
        <div className={styles.errorState} role="alert">
          <div className={styles.errorTitle}>Failed to load rates</div>
          <div className={styles.errorMessage}>{error}</div>
          <button className={styles.retryBtn} onClick={refresh}>Try again</button>
        </div>
      )}

      {!loading && !error && sorted.length === 0 && (
        <div className={styles.emptyState}>No rates found for this filter.</div>
      )}

      {!error && sorted.length > 0 && (
        <>
          <div className={styles.tableWrapper} style={{ opacity: loading ? 0.6 : 1 }}>
            <table className={styles.table}>
              <thead>
                <tr>
                  {(
                    [
                      ["provider_name", "Provider"],
                      ["rate_type", "Type"],
                      ["rate_value", "Rate (%)"],
                      ["effective_date", "Effective date"],
                    ] as [SortKey, string][]
                  ).map(([key, label]) => (
                    <th
                      key={key}
                      className={styles.th}
                      onClick={() => handleSort(key)}
                      aria-sort={
                        sortKey === key
                          ? sortDir === "asc" ? "ascending" : "descending"
                          : "none"
                      }
                    >
                      {label}
                      <span className={styles.sortArrow}>{arrow(key)}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map((rate) => (
                  <tr key={rate.id} className={styles.row}>
                    <td className={styles.td}>{rate.provider_name}</td>
                    <td className={styles.td}>
                      <span className={styles.badge}>{rate.rate_type}</span>
                    </td>
                    <td className={styles.tdNum}>
                      {parseFloat(rate.rate_value).toFixed(3)}%
                    </td>
                    <td className={styles.td}>{rate.effective_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className={styles.pagination}>
            <div className={styles.pageInfo}>
              {totalCount > 0
                ? `Showing ${startRow}–${endRow} of ${totalCount} rates`
                : "No results"}
            </div>

            <div className={styles.pageControls}>
              <button
                className={styles.pageBtn}
                onClick={() => setPage(1)}
                disabled={currentPage === 1 || loading}
                aria-label="First page"
              >«</button>
              <button
                className={styles.pageBtn}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1 || loading}
                aria-label="Previous page"
              >‹</button>
              <span className={styles.pageIndicator}>
                Page {currentPage} of {totalPages}
              </span>
              <button
                className={styles.pageBtn}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages || loading}
                aria-label="Next page"
              >›</button>
              <button
                className={styles.pageBtn}
                onClick={() => setPage(totalPages)}
                disabled={currentPage === totalPages || loading}
                aria-label="Last page"
              >»</button>
            </div>

            <div className={styles.pageSizeControl}>
              <label className={styles.pageSizeLabel} htmlFor="page-size-select">
                Rows
              </label>
              <select
                id="page-size-select"
                className={styles.select}
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                disabled={loading}
                aria-label="Rows per page"
              >
                {PAGE_SIZE_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>
        </>
      )}
    </section>
  );
}