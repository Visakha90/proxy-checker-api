"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { AppLayout, PageHeader } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { fetchJson } from "@/lib/api";
import { toast } from "sonner";
import { Download, Shield, Zap, Clock, Activity, Database, CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface CacheStats {
  cache: {
    cache_health: string;
    total_proxies: number;
    http_count: number;
    socks4_count: number;
    socks5_count: number;
    avg_latency: number;
    avg_score: number;
    success_rate: number;
    last_refresh: string | null;
    refresh_duration_ms: number;
  };
  downloads: { today_total: number; today_http: number; today_socks4: number; today_socks5: number };
  quality_note: string;
}

const protocols = [
  { key: "http", label: "HTTP", color: "from-emerald-500 to-emerald-600", textColor: "text-emerald-500", bgColor: "bg-emerald-500/10" },
  { key: "socks4", label: "SOCKS4", color: "from-violet-500 to-violet-600", textColor: "text-violet-500", bgColor: "bg-violet-500/10" },
  { key: "socks5", label: "SOCKS5", color: "from-pink-500 to-pink-600", textColor: "text-pink-500", bgColor: "bg-pink-500/10" },
  { key: "all", label: "All Protocols", color: "from-blue-500 to-blue-600", textColor: "text-blue-500", bgColor: "bg-blue-500/10" },
];

const formats = ["txt", "csv", "json"] as const;

export default function DownloadPage() {
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [format, setFormat] = useState<typeof formats[number]>("txt");
  const [downloading, setDownloading] = useState<string | null>(null);

  useEffect(() => {
    fetchJson<CacheStats>("/api/v1/download/stats").then(setStats).catch(() => {});
    const interval = setInterval(() => {
      fetchJson<CacheStats>("/api/v1/download/stats").then(setStats).catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleDownload = async (type: string) => {
    setDownloading(type);
    try {
      const res = await fetch(`${API_URL}/api/v1/download/${type}?format=${format}&limit=5000`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Download failed");
      }
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${type}_proxies.${format}`;
      a.click();
      URL.revokeObjectURL(a.href);
      const count = res.headers.get("X-Proxy-Count") || "?";
      toast.success(`Downloaded ${count} ${type.toUpperCase()} proxies`);
    } catch (e: any) {
      toast.error(e.message || "Download failed");
    } finally {
      setDownloading(null);
    }
  };

  const cache = stats?.cache;
  const cacheHealthy = cache?.cache_health === "healthy";

  return (
    <AppLayout>
      <PageHeader title="Download Proxies" description="Only top-ranked, live-verified proxies are served" />

      {/* Quality Banner */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
        className="mb-6 p-4 rounded-2xl bg-gradient-to-r from-blue-500/10 via-blue-500/5 to-transparent border border-blue-500/20">
        <div className="flex items-start gap-3">
          <Shield className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium">Quality-First Downloads</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Proxies are ranked by success rate, latency, uptime, and anonymity. Only the top {cache?.total_proxies?.toLocaleString() || "10,000"} highest-quality proxies are available. Cache refreshes every 5 minutes.
            </p>
          </div>
        </div>
      </motion.div>

      {/* Cache Health & Metrics */}
      {cache && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
          {[
            { icon: Database, label: "Cached", value: cache.total_proxies.toLocaleString(), color: "text-blue-500" },
            { icon: cacheHealthy ? CheckCircle2 : AlertCircle, label: "Cache", value: cacheHealthy ? "Healthy" : "Degraded", color: cacheHealthy ? "text-success" : "text-warning" },
            { icon: Zap, label: "Avg Latency", value: `${cache.avg_latency}ms`, color: "text-cyan-500" },
            { icon: Activity, label: "Success Rate", value: `${cache.success_rate}%`, color: "text-emerald-500" },
            { icon: Clock, label: "Last Refresh", value: cache.last_refresh ? new Date(cache.last_refresh).toLocaleTimeString() : "—", color: "text-muted-foreground" },
            { icon: Download, label: "Downloads Today", value: stats.downloads.today_total.toLocaleString(), color: "text-violet-500" },
          ].map((m, i) => {
            const Icon = m.icon;
            return (
              <motion.div key={m.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.03 }}
                className="rounded-2xl border border-border bg-card p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Icon className={cn("w-3.5 h-3.5", m.color)} />
                  <span className="text-2xs text-muted-foreground uppercase tracking-wider">{m.label}</span>
                </div>
                <p className={cn("text-lg font-bold", m.color)}>{m.value}</p>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Format Selector */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}
        className="flex items-center gap-2 mb-6">
        <span className="text-xs text-muted-foreground font-medium">Format:</span>
        <div className="flex gap-1 p-1 rounded-xl bg-secondary">
          {formats.map(f => (
            <button key={f} onClick={() => setFormat(f)}
              className={cn("px-4 py-1.5 rounded-lg text-xs font-medium transition-all",
                format === f ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              )}>
              {f.toUpperCase()}
            </button>
          ))}
        </div>
        <span className="text-2xs text-muted-foreground ml-2">
          {format === "txt" ? "ip:port per line" : format === "csv" ? "Comma separated with headers" : "Structured JSON array"}
        </span>
      </motion.div>

      {/* Download Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {protocols.map((proto, i) => {
          const count = cache ? (proto.key === "all" ? cache.total_proxies : cache[`${proto.key}_count` as keyof typeof cache] as number) : 0;
          return (
            <motion.div key={proto.key} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 + i * 0.05 }}
              className="group relative rounded-2xl border border-border bg-card p-6 overflow-hidden hover:border-border/80 hover:shadow-lg transition-all duration-300">
              {/* Background gradient */}
              <div className={cn("absolute top-0 right-0 w-32 h-32 rounded-full blur-3xl opacity-10 group-hover:opacity-20 transition-opacity bg-gradient-to-br", proto.color)} />

              <div className="relative">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-base font-semibold">{proto.label}</h3>
                    <p className="text-2xs text-muted-foreground mt-0.5">
                      {count > 0 ? `${count.toLocaleString()} live proxies` : "Loading..."}
                    </p>
                  </div>
                  <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", proto.bgColor)}>
                    <Download className={cn("w-5 h-5", proto.textColor)} />
                  </div>
                </div>

                <Button
                  onClick={() => handleDownload(proto.key)}
                  loading={downloading === proto.key}
                  disabled={!cacheHealthy || count === 0}
                  className="w-full"
                >
                  Download .{format}
                </Button>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* API Reference */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
        className="mt-8 rounded-2xl border border-border bg-card p-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">API Endpoints</h3>
        <div className="space-y-2 font-mono text-xs">
          {protocols.map(p => (
            <div key={p.key} className="flex items-center gap-3 py-1.5 border-b border-border last:border-0">
              <span className="text-primary font-medium w-8">GET</span>
              <span className="text-muted-foreground">/api/v1/download/{p.key}?format={format}&limit=500</span>
              <span className="ml-auto text-2xs text-muted-foreground">Redis-only</span>
            </div>
          ))}
        </div>
      </motion.div>
    </AppLayout>
  );
}
