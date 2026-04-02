export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export interface Rate {
  id: number;
  provider_name: string;
  rate_type: string;
  rate_value: string;
  effective_date: string;
  ingestion_timestamp: string;
}

export interface PaginatedResponse<T> {
  count: number;
  total_pages: number;
  page: number;
  page_size: number;
  results: T[];
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export interface FetchLatestRatesOptions {
  type?: string;
  page?: number;
  pageSize?: number;
}

export async function fetchLatestRates(
  options: FetchLatestRatesOptions | string = {}
): Promise<PaginatedResponse<Rate>> {
  // Accept plain string for backward compatibility (used by RateHistoryChart)
  const opts: FetchLatestRatesOptions =
    typeof options === "string" ? { type: options || undefined } : options;

  const params = new URLSearchParams();
  if (opts.type) params.set("type", opts.type);
  if (opts.page !== undefined) params.set("page", String(opts.page));
  if (opts.pageSize !== undefined) params.set("page_size", String(opts.pageSize));

  const qs = params.toString();
  return apiFetch<PaginatedResponse<Rate>>(`/rates/latest${qs ? `?${qs}` : ""}`);
}

export async function fetchRateHistory(
  provider: string,
  type: string,
  from?: string,
  to?: string
): Promise<PaginatedResponse<Rate>> {
  const params = new URLSearchParams({ provider, type });
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  return apiFetch<PaginatedResponse<Rate>>(`/rates/history?${params.toString()}`);
}