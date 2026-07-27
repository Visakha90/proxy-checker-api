"use client";

import { useEffect, useState } from "react";
import { AppLayout, PageHeader } from "@/components/layout";
import { Card, StatCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { CardSkeleton } from "@/components/ui/skeleton";
import { fetchJson } from "@/lib/api";
import { cn } from "@/lib/utils";

const SDK_LANGS = ["python", "javascript", "nodejs", "php", "go", "java", "rust", "csharp"];

const TABS = ["docs", "dashboard", "keys", "sdk"] as const;
type Tab = (typeof TABS)[number];

export default function ApiDocsPage() {
  const [tab, setTab] = useState<Tab>("docs");
  const [stats, setStats] = useState<any>(null);
  const [keys, setKeys] = useState<any[]>([]);
  const [recent, setRecent] = useState<any[]>([]);
  const [sdk, setSdk] = useState("");
  const [lang, setLang] = useState("python");
  const [newName, setNewName] = useState("");
  const [newTier, setNewTier] = useState("free");
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);
  useEffect(() => { if (tab === "sdk") loadSdk(lang); }, [tab, lang]);

  const loadData = async () => {
    try {
      const [d, k, r] = await Promise.all([
        fetchJson<any>("/api/v1/dashboard").catch(() => null),
        fetchJson<any>("/api/v1/keys").catch(() => ({ data: [] })),
        fetchJson<any>("/api/v1/dashboard/requests?limit=15").catch(() => ({ data: [] })),
      ]);
      setStats(d?.data); setKeys(k?.data || []); setRecent(r?.data || []);
    } catch {} finally { setLoading(false); }
  };

  const loadSdk = async (l: string) => {
    try { const d = await fetchJson<any>(`/api/v1/sdk/${l}`); setSdk(d.code); }
    catch { setSdk("// Failed to load"); }
  };

  const createKey = async () => {
    if (!newName) return;
    try { await fetchJson("/api/v1/keys", { method: "POST", body: JSON.stringify({ name: newName, tier: newTier }) }); setNewName(""); loadData(); }
    catch (e: any) { alert(e.message); }
  };

  const deleteKey = async (id: number) => {
    if (!confirm("Delete this key?")) return;
    await fetchJson(`/api/v1/keys/${id}`, { method: "DELETE" }); loadData();
  };

  const fmtBytes = (b: number) => b < 1024 ? `${b}B` : b < 1048576 ? `${(b/1024).toFixed(1)}KB` : `${(b/1048576).toFixed(1)}MB`;

  return (
    <AppLayout>
      <PageHeader title="Public API" description="Documentation, keys, SDK, and analytics"
        actions={<a href="http://localhost:8000/docs" target="_blank"><Button variant="outline" size="sm">Swagger UI</Button></a>}
      />

      {/* Tabs */}
      <div className="flex gap-0.5 mb-6 p-0.5 rounded-lg bg-white/[0.03] border border-white/[0.06] w-fit">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={cn("px-4 py-1.5 rounded-md text-xs font-medium transition-all", tab === t ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:text-foreground")}
          >{t === "docs" ? "Docs" : t === "dashboard" ? "Analytics" : t === "keys" ? "API Keys" : "SDK"}</button>
        ))}
      </div>

      {tab === "docs" && (
        <div className="space-y-4 animate-fade-in">
          <Card className="p-5" hover={false}>
            <h3 className="text-xs font-semibold text-emerald-400 mb-2">Base URL</h3>
            <code className="text-sm font-mono bg-white/[0.03] px-3 py-1.5 rounded-md border border-white/[0.06]">
              http://localhost:8000/api/v1
            </code>
          </Card>
          <Card className="p-5" hover={false}>
            <h3 className="text-xs font-semibold text-emerald-400 mb-2">Authentication</h3>
            <p className="text-xs text-muted-foreground mb-2">Pass your API key via header or query:</p>
            <div className="space-y-1.5 font-mono text-xs">
              <code className="block bg-white/[0.03] px-3 py-1.5 rounded-md border border-white/[0.06] text-gray-400">X-API-Key: pc_your_key_here</code>
              <code className="block bg-white/[0.03] px-3 py-1.5 rounded-md border border-white/[0.06] text-gray-400">?api_key=pc_your_key_here</code>
            </div>
          </Card>
          <Card className="p-5" hover={false}>
            <h3 className="text-xs font-semibold text-emerald-400 mb-3">Rate Limits</h3>
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] p-3 text-center">
                <p className="text-lg font-bold">100</p><p className="text-[10px] text-muted-foreground uppercase">Guest / hour</p>
              </div>
              <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] p-3 text-center">
                <p className="text-lg font-bold">1,000</p><p className="text-[10px] text-muted-foreground uppercase">Free / day</p>
              </div>
              <div className="rounded-lg bg-emerald-500/5 border border-emerald-500/20 p-3 text-center">
                <p className="text-lg font-bold text-emerald-400">Unlimited</p><p className="text-[10px] text-muted-foreground uppercase">Premium</p>
              </div>
            </div>
          </Card>
          <Card className="p-5" hover={false}>
            <h3 className="text-xs font-semibold text-emerald-400 mb-3">Endpoints</h3>
            <div className="space-y-1.5 font-mono text-xs">
              {[
                ["GET", "/api/v1/proxies", "Filtered proxy list"],
                ["GET", "/api/v1/http", "HTTP proxies"],
                ["GET", "/api/v1/https", "HTTPS proxies"],
                ["GET", "/api/v1/socks4", "SOCKS4 proxies"],
                ["GET", "/api/v1/socks5", "SOCKS5 proxies"],
                ["GET", "/api/v1/random", "Random proxy"],
                ["GET", "/api/v1/stats", "Statistics"],
                ["GET", "/api/v1/countries", "Country list"],
                ["GET", "/api/v1/download/{type}", "Download file"],
              ].map(([m, p, d], i) => (
                <div key={i} className="flex items-center gap-3 py-1.5 border-b border-white/[0.04] last:border-0">
                  <span className="text-emerald-400 w-8">{m}</span>
                  <span className="text-gray-300 flex-1">{p}</span>
                  <span className="text-muted-foreground text-[11px]">{d}</span>
                </div>
              ))}
            </div>
          </Card>
          <Card className="p-5" hover={false}>
            <h3 className="text-xs font-semibold text-emerald-400 mb-3">Query Parameters</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {["country=US", "type=http", "anonymity=elite", "alive=true", "ssl=true", "latency_lt=500", "limit=100", "page=1", "sort=latency"].map((f) => (
                <code key={f} className="bg-white/[0.03] border border-white/[0.06] px-2 py-1 rounded text-[11px] text-muted-foreground">{f}</code>
              ))}
            </div>
          </Card>
        </div>
      )}

      {tab === "dashboard" && (
        <div className="animate-fade-in">
          {stats ? (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
                <StatCard label="Today" value={stats.today_requests?.toLocaleString() || 0} color="text-emerald-400" />
                <StatCard label="Errors" value={stats.today_errors || 0} color="text-red-400" />
                <StatCard label="Avg Response" value={`${stats.avg_response_time_ms || 0}ms`} color="text-cyan-400" />
                <StatCard label="Bandwidth" value={fmtBytes(stats.total_bandwidth_bytes || 0)} color="text-violet-400" />
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
                <Card className="p-4" hover={false}>
                  <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-3">Top Endpoints</h3>
                  {stats.top_endpoints?.length > 0 ? stats.top_endpoints.map((ep: any, i: number) => (
                    <div key={i} className="flex justify-between items-center py-1.5 border-b border-white/[0.04] last:border-0">
                      <code className="text-[11px] text-gray-400 font-mono">{ep.endpoint}</code>
                      <span className="text-[11px] text-emerald-400 font-medium">{ep.count}</span>
                    </div>
                  )) : <p className="text-xs text-muted-foreground">No data yet</p>}
                </Card>
                <Card className="p-4" hover={false}>
                  <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-3">Top Users</h3>
                  {stats.top_users?.length > 0 ? stats.top_users.map((u: any, i: number) => (
                    <div key={i} className="flex justify-between items-center py-1.5 border-b border-white/[0.04] last:border-0">
                      <code className="text-[11px] text-gray-400 font-mono">{u.key}</code>
                      <span className="text-[11px] text-cyan-400 font-medium">{u.count}</span>
                    </div>
                  )) : <p className="text-xs text-muted-foreground">No data yet</p>}
                </Card>
              </div>
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
                <div className="px-4 py-3 border-b border-white/[0.06]">
                  <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Recent Requests</h3>
                </div>
                <div className="overflow-x-auto max-h-[250px]">
                  <table className="w-full text-[11px]">
                    <thead className="sticky top-0 bg-[#0a0a0a]"><tr className="border-b border-white/[0.06]">
                      {["Time", "Endpoint", "Status", "Latency", "Key"].map((h) => (
                        <th key={h} className="text-left px-3 py-2 text-muted-foreground font-medium">{h}</th>
                      ))}
                    </tr></thead>
                    <tbody>
                      {recent.map((r: any, i: number) => (
                        <tr key={i} className="border-b border-white/[0.04]">
                          <td className="px-3 py-1.5 text-muted-foreground">{r.created_at ? new Date(r.created_at).toLocaleTimeString() : "—"}</td>
                          <td className="px-3 py-1.5 font-mono text-gray-300">{r.endpoint}</td>
                          <td className="px-3 py-1.5"><span className={r.status_code < 400 ? "text-emerald-400" : "text-red-400"}>{r.status_code}</span></td>
                          <td className="px-3 py-1.5 text-muted-foreground font-mono">{r.response_time_ms ? `${Math.round(r.response_time_ms)}ms` : "—"}</td>
                          <td className="px-3 py-1.5 text-muted-foreground font-mono">{r.api_key || "guest"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : <div className="grid grid-cols-2 sm:grid-cols-4 gap-3"><CardSkeleton /><CardSkeleton /><CardSkeleton /><CardSkeleton /></div>}
        </div>
      )}

      {tab === "keys" && (
        <div className="animate-fade-in space-y-4">
          <Card className="p-4" hover={false}>
            <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-3">Create Key</h3>
            <div className="flex gap-2">
              <div className="flex-1"><Input placeholder="Key name" value={newName} onChange={(e) => setNewName(e.target.value)} /></div>
              <select value={newTier} onChange={(e) => setNewTier(e.target.value)} className="h-9 px-3 rounded-lg bg-white/[0.03] border border-white/[0.08] text-xs text-foreground">
                <option value="free" className="bg-[#111]">Free</option>
                <option value="premium" className="bg-[#111]">Premium</option>
              </select>
              <Button onClick={createKey}>Create</Button>
            </div>
          </Card>
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
            <table className="w-full">
              <thead><tr className="border-b border-white/[0.06]">
                {["Name", "Key", "Tier", "Today", "Total", "Bandwidth", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {keys.length === 0 ? (
                  <tr><td colSpan={7} className="px-4 py-12 text-center text-xs text-muted-foreground">No API keys yet</td></tr>
                ) : keys.map((k: any) => (
                  <tr key={k.id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                    <td className="px-4 py-2.5 text-xs">{k.name}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-muted-foreground">{k.key}</td>
                    <td className="px-4 py-2.5"><Badge variant={k.tier === "premium" ? "premium" : "info"}>{k.tier}</Badge></td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{k.requests_today}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{k.requests_total?.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{fmtBytes(k.bandwidth_bytes || 0)}</td>
                    <td className="px-4 py-2.5"><Button size="xs" variant="ghost" onClick={() => deleteKey(k.id)}>Delete</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "sdk" && (
        <div className="animate-fade-in">
          <div className="flex flex-wrap gap-1.5 mb-4">
            {SDK_LANGS.map((l) => (
              <button key={l} onClick={() => setLang(l)}
                className={cn("px-3 py-1.5 rounded-md text-xs font-medium transition-all border",
                  lang === l ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-white/[0.02] text-muted-foreground border-white/[0.06] hover:bg-white/[0.04]"
                )}
              >{l}</button>
            ))}
          </div>
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06]">
              <span className="text-[11px] text-muted-foreground font-mono">{lang}</span>
              <Button size="xs" variant="ghost" onClick={() => navigator.clipboard.writeText(sdk)}>Copy</Button>
            </div>
            <pre className="p-4 text-[12px] font-mono text-gray-400 overflow-x-auto max-h-[500px] overflow-y-auto leading-relaxed">
              {sdk || "Loading..."}
            </pre>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
