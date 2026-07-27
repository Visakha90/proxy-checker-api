"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppLayout, PageHeader } from "@/components/layout";
import { Card, StatCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { CardSkeleton } from "@/components/ui/skeleton";
import { fetchJson, type ProxySource } from "@/lib/api";

export default function AdminPage() {
  const router = useRouter();
  const [auth, setAuth] = useState(false);
  const [dash, setDash] = useState<any>(null);
  const [sources, setSources] = useState<ProxySource[]>([]);
  const [settings, setSettings] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [newUrl, setNewUrl] = useState("");
  const [newType, setNewType] = useState("http");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!localStorage.getItem("token")) { router.push("/login"); return; }
    setAuth(true); load();
  }, [router]);

  const load = async () => {
    try {
      const [d, s, st, l] = await Promise.all([
        fetchJson<any>("/api/admin/dashboard"),
        fetchJson<ProxySource[]>("/api/sources"),
        fetchJson<any>("/api/admin/settings"),
        fetchJson<any[]>("/api/admin/logs?limit=20"),
      ]);
      setDash(d); setSources(s); setSettings(st); setLogs(l);
    } catch (e: any) {
      if (e.message?.includes("401")) { localStorage.removeItem("token"); router.push("/login"); }
    } finally { setLoading(false); }
  };

  const addSource = async () => {
    if (!newUrl) return;
    try { await fetchJson("/api/sources", { method: "POST", body: JSON.stringify({ url: newUrl, proxy_type: newType }) }); setNewUrl(""); load(); }
    catch (e: any) { alert(e.message); }
  };

  const toggle = async (id: number) => { await fetchJson(`/api/sources/${id}/toggle`, { method: "PATCH" }); load(); };
  const del = async (id: number) => { if (!confirm("Delete?")) return; await fetchJson(`/api/sources/${id}`, { method: "DELETE" }); load(); };
  const action = async (a: string) => { try { const r = await fetchJson<any>(`/api/admin/${a}`, { method: "POST" }); alert(JSON.stringify(r, null, 2)); load(); } catch (e: any) { alert(e.message); } };

  if (!auth || loading) return (
    <AppLayout>
      <PageHeader title="Admin" description="Loading..." />
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
      </div>
    </AppLayout>
  );

  return (
    <AppLayout>
      <PageHeader title="Admin Panel" description="Manage proxy infrastructure"
        actions={<Button variant="destructive" size="sm" onClick={() => { localStorage.removeItem("token"); router.push("/login"); }}>Logout</Button>}
      />

      {dash && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
          <StatCard label="Sources" value={dash.total_sources} />
          <StatCard label="Enabled" value={dash.enabled_sources} color="text-emerald-400" />
          <StatCard label="Proxies" value={dash.total_proxies?.toLocaleString()} color="text-cyan-400" />
          <StatCard label="Checks" value={dash.total_checks?.toLocaleString()} color="text-violet-400" />
          <StatCard label="Scraper" value={dash.scraper_running ? "On" : "Off"} color={dash.scraper_running ? "text-emerald-400" : "text-red-400"} />
          <StatCard label="Checker" value={dash.checker_running ? "On" : "Off"} color={dash.checker_running ? "text-emerald-400" : "text-red-400"} />
        </div>
      )}

      {/* Controls */}
      <Card className="mb-6 p-4" hover={false}>
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-3">Controls</h3>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => action("scraper/start")}>Start Scraper</Button>
          <Button size="sm" variant="destructive" onClick={() => action("scraper/stop")}>Stop Scraper</Button>
          <Button size="sm" onClick={() => action("checker/start")}>Start Checker</Button>
          <Button size="sm" variant="destructive" onClick={() => action("checker/stop")}>Stop Checker</Button>
          <Button size="sm" variant="outline" onClick={() => action("recheck")}>Force Recheck</Button>
          <Button size="sm" variant="outline" onClick={() => action("clean")}>Cleanup</Button>
        </div>
      </Card>

      {/* Add Source */}
      <Card className="mb-6 p-4" hover={false}>
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-3">Add Source</h3>
        <div className="flex gap-2">
          <div className="flex-1"><Input placeholder="https://..." value={newUrl} onChange={(e) => setNewUrl(e.target.value)} /></div>
          <select value={newType} onChange={(e) => setNewType(e.target.value)} className="h-9 px-3 rounded-lg bg-white/[0.03] border border-white/[0.08] text-xs text-foreground">
            <option value="http" className="bg-[#111]">HTTP</option>
            <option value="socks4" className="bg-[#111]">SOCKS4</option>
            <option value="socks5" className="bg-[#111]">SOCKS5</option>
          </select>
          <Button onClick={addSource}>Add</Button>
        </div>
      </Card>

      {/* Sources */}
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden mb-6">
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Sources ({sources.length})</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr className="border-b border-white/[0.06]">
              {["URL", "Type", "Status", "Count", "Last Scraped", ""].map((h) => (
                <th key={h} className="text-left px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                  <td className="px-4 py-2.5 text-xs font-mono max-w-[250px] truncate text-muted-foreground">{s.url}</td>
                  <td className="px-4 py-2.5"><Badge variant="info">{s.proxy_type.toUpperCase()}</Badge></td>
                  <td className="px-4 py-2.5"><Badge variant={s.enabled ? "success" : "error"}>{s.enabled ? "On" : "Off"}</Badge></td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">{s.proxy_count}</td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">{s.last_scraped ? new Date(s.last_scraped).toLocaleString() : "—"}</td>
                  <td className="px-4 py-2.5 flex gap-1">
                    <Button size="xs" variant="ghost" onClick={() => toggle(s.id)}>{s.enabled ? "Disable" : "Enable"}</Button>
                    <Button size="xs" variant="ghost" onClick={() => del(s.id)}>Del</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Settings */}
      {settings && (
        <Card className="mb-6 p-4" hover={false}>
          <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-3">Settings</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {Object.entries(settings).map(([k, v]) => (
              <div key={k} className="rounded-lg bg-white/[0.03] border border-white/[0.06] p-2.5">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{k.replace(/_/g, " ")}</p>
                <p className="text-xs font-mono text-foreground mt-0.5">{String(v)}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Logs */}
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Recent Checks</h3>
        </div>
        <div className="max-h-[250px] overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-[#0a0a0a]"><tr className="border-b border-white/[0.06]">
              {["Time", "Proxy", "Status", "Latency", "Error"].map((h) => (
                <th key={h} className="text-left px-3 py-2 text-muted-foreground font-medium">{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} className="border-b border-white/[0.04]">
                  <td className="px-3 py-1.5 text-muted-foreground">{l.checked_at ? new Date(l.checked_at).toLocaleTimeString() : "—"}</td>
                  <td className="px-3 py-1.5 font-mono text-muted-foreground">{l.proxy_id}</td>
                  <td className="px-3 py-1.5"><span className={l.is_alive ? "text-emerald-400" : "text-red-400"}>{l.is_alive ? "✓" : "✗"}</span></td>
                  <td className="px-3 py-1.5 text-muted-foreground font-mono">{l.latency ? `${Math.round(l.latency)}ms` : "—"}</td>
                  <td className="px-3 py-1.5 text-red-400/60 max-w-[150px] truncate">{l.error || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppLayout>
  );
}
