const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response;
}

export async function fetchJson<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetchApi(endpoint, options);
  return response.json();
}

export function getWsUrl(): string {
  return `${WS_URL}/ws`;
}

export interface Stats {
  total_proxies: number;
  alive_proxies: number;
  dead_proxies: number;
  http_count: number;
  https_count: number;
  socks4_count: number;
  socks5_count: number;
  elite_count: number;
  anonymous_count: number;
  transparent_count: number;
  avg_latency: number;
  newest_proxy: string | null;
  last_update: string | null;
}

export interface ProxyItem {
  id: number;
  ip: string;
  port: number;
  proxy_type: string;
  is_alive: boolean;
  latency: number | null;
  status_code: number | null;
  country: string | null;
  country_code: string | null;
  isp: string | null;
  anonymity_level: string | null;
  ssl_support: boolean;
  first_seen: string;
  last_seen: string;
  last_checked: string | null;
}

export interface ProxyListResponse {
  proxies: ProxyItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProxySource {
  id: number;
  url: string;
  name: string | null;
  proxy_type: string;
  enabled: boolean;
  last_scraped: string | null;
  proxy_count: number;
  created_at: string;
}

export interface TestResult {
  ip: string;
  port: number;
  proxy_type: string;
  working: boolean;
  latency: number | null;
  status_code: number | null;
  error: string | null;
}
