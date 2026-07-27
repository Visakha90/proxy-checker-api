"use client";

import { useEffect, useState, useCallback } from "react";
import { AppLayout, PageHeader } from "@/components/layout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Badge, StatusDot } from "@/components/ui/badge";
import { TableSkeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { fetchJson, type ProxyItem, type ProxyListResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function ProxiesPage() {
  const [proxies, setProxies] = useState<ProxyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [proxyType, setProxyType] = useState("");
  const [isAlive, setIsAlive] = useState("");
  const [anonymity, setAnonymity] = useState("");
  const [sortBy, setSortBy] = useState("last_checked");
  const [sortOrder, setSortOrder] = useState("desc");

  const fetchProxies = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page), page_size: String(pageSize),
        sort_by: sortBy, sort_order: sortOrder,
      });
      if (search) params.set("search", search);
      if (proxyType) params.set("proxy_type", proxyType);
      if (isAlive) params.set("is_alive", isAlive);
      if (anonymity) params.set("anonymity", anonymity);

      const data = await fetchJson<ProxyListResponse>(`/api/proxies?${params}`);
      setProxies(data.proxies);
      setTotal(data.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, proxyType, isAlive, anonymity, sortBy, sortOrder]);

  useEffect(() => { fetchProxies(); }, [fetchProxies]);

  const totalPages = Math.ceil(total / pageSize);
  const copyProxy = (ip: string, port: number) => navigator.clipboard.writeText(`${ip}:${port}`);

  return (
    <AppLayout>
      <PageHeader
        title="Proxies"
        description={`${total.toLocaleString()} proxies in database`}
        actions={
          <Button variant="secondary" size="sm" onClick={fetchProxies}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 4v6h6M23 20v-6h-6" strokeLinecap="round" strokeLinejoin="round"/><path d="M20.49 9A9 9 0 105.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15" strokeLinecap="round" strokeLinejoin="round"/></svg>
            Refresh
          </Button>
        }
      />

      {/* Filters */}
      <Card className="mb-5 p-4" hover={false}>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <Input
            placeholder="Search IP or country..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>}
          />
          <Select value={proxyType} onChange={(e) => { setProxyType(e.target.value); setPage(1); }}
            options={[{ value: "", label: "All Types" }, { value: "http", label: "HTTP" }, { value: "https", label: "HTTPS" }, { value: "socks4", label: "SOCKS4" }, { value: "socks5", label: "SOCKS5" }]} />
          <Select value={isAlive} onChange={(e) => { setIsAlive(e.target.value); setPage(1); }}
            options={[{ value: "", label: "All Status" }, { value: "true", label: "Alive" }, { value: "false", label: "Dead" }]} />
          <Select value={anonymity} onChange={(e) => { setAnonymity(e.target.value); setPage(1); }}
            options={[{ value: "", label: "All Anonymity" }, { value: "elite", label: "Elite" }, { value: "anonymous", label: "Anonymous" }, { value: "transparent", label: "Transparent" }]} />
          <Select value={sortBy} onChange={(e) => setSortBy(e.target.value)}
            options={[{ value: "last_checked", label: "Last Checked" }, { value: "latency", label: "Latency" }, { value: "first_seen", label: "First Seen" }, { value: "port", label: "Port" }]} />
          <Select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}
            options={[{ value: "desc", label: "Descending" }, { value: "asc", label: "Ascending" }]} />
        </div>
      </Card>

      {/* Table */}
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/[0.06]">
                {["IP:Port", "Type", "Status", "Latency", "Anonymity", "SSL", "Country", "Last Check", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={9}><TableSkeleton rows={8} /></td></tr>
              ) : proxies.length === 0 ? (
                <tr><td colSpan={9}>
                  <EmptyState
                    title="No proxies found"
                    description="Try adjusting your filters or wait for the scraper to collect data."
                    icon={<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>}
                  />
                </td></tr>
              ) : proxies.map((p) => (
                <tr key={p.id} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors group">
                  <td className="px-4 py-3 font-mono text-xs text-foreground">{p.ip}:{p.port}</td>
                  <td className="px-4 py-3">
                    <Badge variant={p.proxy_type === "http" ? "success" : p.proxy_type === "socks5" ? "premium" : "info"}>
                      {p.proxy_type.toUpperCase()}
                    </Badge>
                  </td>
                  <td className="px-4 py-3"><StatusDot alive={p.is_alive} /></td>
                  <td className="px-4 py-3 text-xs text-muted-foreground font-mono">
                    {p.latency ? `${Math.round(p.latency)}ms` : "—"}
                  </td>
                  <td className="px-4 py-3">
                    {p.anonymity_level ? (
                      <Badge variant={p.anonymity_level === "elite" ? "warning" : p.anonymity_level === "anonymous" ? "info" : "default"}>
                        {p.anonymity_level}
                      </Badge>
                    ) : <span className="text-xs text-muted-foreground">—</span>}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {p.ssl_support ? <span className="text-emerald-400">Yes</span> : <span className="text-muted-foreground">No</span>}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{p.country || "—"}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {p.last_checked ? new Date(p.last_checked).toLocaleTimeString() : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => copyProxy(p.ip, p.port)}
                      className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground transition-all"
                      title="Copy"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-white/[0.06]">
            <span className="text-[11px] text-muted-foreground">
              Page {page} of {totalPages}
            </span>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="xs" onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}>
                Prev
              </Button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                const p = page <= 3 ? i + 1 : page + i - 2;
                if (p < 1 || p > totalPages) return null;
                return (
                  <Button key={p} variant={p === page ? "primary" : "ghost"} size="xs" onClick={() => setPage(p)}>
                    {p}
                  </Button>
                );
              })}
              <Button variant="ghost" size="xs" onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page === totalPages}>
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
