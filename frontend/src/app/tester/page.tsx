"use client";

import { useState, useMemo, useCallback } from "react";
import { AppLayout, PageHeader } from "@/components/layout";
import { Card, StatCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Badge, StatusDot } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { fetchJson, type TestResult } from "@/lib/api";

type Fmt = "txt" | "csv" | "json";

function gen(proxies: TestResult[], fmt: Fmt): string {
  if (fmt === "txt") return proxies.map((p) => `${p.ip}:${p.port}`).join("\n");
  if (fmt === "csv") return ["ip,port,type,latency,status", ...proxies.map((p) => `${p.ip},${p.port},${p.proxy_type},${p.latency ?? ""},${p.status_code ?? ""}`)].join("\n");
  return JSON.stringify(proxies.map((p) => ({ ip: p.ip, port: p.port, type: p.proxy_type, latency: p.latency, status_code: p.status_code })), null, 2);
}

function dl(content: string, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type: "text/plain" }));
  a.download = name;
  a.click();
}

export default function TesterPage() {
  const [url, setUrl] = useState("https://httpbin.org/ip");
  const [timeout, setTimeout] = useState("10");
  const [method, setMethod] = useState("GET");
  const [type, setType] = useState("");
  const [limit, setLimit] = useState("100");
  const [testing, setTesting] = useState(false);
  const [results, setResults] = useState<TestResult[]>([]);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [fmt, setFmt] = useState<Fmt>("txt");
  const [copied, setCopied] = useState("");

  const live = useMemo(() => results.filter((r) => r.working && r.status_code === 200), [results]);
  const working = useMemo(() => results.filter((r) => r.working), [results]);
  const failed = useMemo(() => results.filter((r) => !r.working), [results]);

  const runTest = async () => {
    setTesting(true); setError(""); setResults([]); setDone(false);
    try {
      const body: any = { target_url: url, timeout: parseInt(timeout), method, limit: parseInt(limit) };
      if (type) body.proxy_type = type;
      const data = await fetchJson<TestResult[]>("/api/test", { method: "POST", body: JSON.stringify(body) });
      setResults(data); setDone(true);
    } catch (e: any) { setError(e.message || "Test failed"); }
    finally { setTesting(false); }
  };

  const retestFailed = async () => {
    if (!failed.length) return;
    setTesting(true); setError("");
    try {
      const body: any = { target_url: url, timeout: parseInt(timeout), method, limit: failed.length };
      if (type) body.proxy_type = type;
      const data = await fetchJson<TestResult[]>("/api/test", { method: "POST", body: JSON.stringify(body) });
      setResults([...working, ...data]); setDone(true);
    } catch (e: any) { setError(e.message || "Retest failed"); }
    finally { setTesting(false); }
  };

  const copy = useCallback(async (items: TestResult[], label: string) => {
    await navigator.clipboard.writeText(items.map((p) => `${p.ip}:${p.port}`).join("\n"));
    setCopied(label); window.setTimeout(() => setCopied(""), 2000);
  }, []);

  const ts = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}_${String(d.getHours()).padStart(2,"0")}-${String(d.getMinutes()).padStart(2,"0")}`; };

  return (
    <AppLayout>
      <PageHeader title="Proxy Tester" description="Test proxies against any target URL" />

      <Card className="mb-6 p-5" hover={false}>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
          <div className="sm:col-span-2">
            <Input label="Target URL" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com" />
          </div>
          <Select label="Method" value={method} onChange={(e) => setMethod(e.target.value)} options={[{ value: "GET", label: "GET" }, { value: "POST", label: "POST" }]} />
          <Input label="Timeout (s)" type="number" value={timeout} onChange={(e) => setTimeout(e.target.value)} />
          <Input label="Limit" type="number" value={limit} onChange={(e) => setLimit(e.target.value)} />
        </div>
        <div className="flex items-center gap-3">
          <Select value={type} onChange={(e) => setType(e.target.value)} options={[{ value: "", label: "All Types" }, { value: "http", label: "HTTP" }, { value: "https", label: "HTTPS" }, { value: "socks4", label: "SOCKS4" }, { value: "socks5", label: "SOCKS5" }]} />
          <Button onClick={runTest} disabled={testing || !url} loading={testing}>
            {testing ? "Testing..." : "Run Test"}
          </Button>
        </div>
      </Card>

      {error && (
        <Card className="mb-4 p-3 border-red-500/20 bg-red-500/5" hover={false}>
          <p className="text-xs text-red-400">{error}</p>
        </Card>
      )}

      {results.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <StatCard label="Tested" value={results.length} />
            <StatCard label="Working" value={working.length} color="text-emerald-400" />
            <StatCard label="Live (200)" value={live.length} color="text-cyan-400" />
            <StatCard label="Failed" value={failed.length} color="text-red-400" />
          </div>

          {/* Actions */}
          <Card className="mb-4 p-4" hover={false}>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" disabled={!done || !live.length} onClick={() => dl(gen(live, fmt), `live_proxies_${ts()}.${fmt}`)}>
                Download Live ({live.length})
              </Button>
              <select value={fmt} onChange={(e) => setFmt(e.target.value as Fmt)} className="h-8 px-2 rounded-md bg-white/[0.03] border border-white/[0.08] text-xs text-foreground">
                <option value="txt" className="bg-[#111]">TXT</option>
                <option value="csv" className="bg-[#111]">CSV</option>
                <option value="json" className="bg-[#111]">JSON</option>
              </select>
              <div className="w-px h-5 bg-white/[0.06] hidden sm:block" />
              <Button size="sm" variant="secondary" disabled={!live.length} onClick={() => copy(live, "live")}>
                {copied === "live" ? "Copied!" : "Copy Live"}
              </Button>
              <Button size="sm" variant="secondary" disabled={!results.length} onClick={() => copy(results, "all")}>
                {copied === "all" ? "Copied!" : "Copy All"}
              </Button>
              <div className="w-px h-5 bg-white/[0.06] hidden sm:block" />
              <Button size="sm" variant="outline" disabled={testing || !failed.length} loading={testing} onClick={retestFailed}>
                Retest Failed ({failed.length})
              </Button>
              <Button size="sm" variant="ghost" disabled={!failed.length} onClick={() => dl(gen(failed, fmt), `failed_proxies_${ts()}.${fmt}`)}>
                Download Failed
              </Button>
            </div>
          </Card>

          {/* Table */}
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
            <div className="overflow-x-auto max-h-[500px]">
              <table className="w-full">
                <thead className="sticky top-0 bg-[#0a0a0a]">
                  <tr className="border-b border-white/[0.06]">
                    {["Proxy", "Type", "Status", "Latency", "HTTP", "Error"].map((h) => (
                      <th key={h} className="text-left px-4 py-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">
                      <td className="px-4 py-2.5 font-mono text-xs">{r.ip}:{r.port}</td>
                      <td className="px-4 py-2.5"><Badge variant="info" size="sm">{r.proxy_type.toUpperCase()}</Badge></td>
                      <td className="px-4 py-2.5"><StatusDot alive={r.working} /></td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground font-mono">{r.latency ? `${Math.round(r.latency)}ms` : "—"}</td>
                      <td className="px-4 py-2.5 text-xs font-mono">
                        <span className={r.status_code === 200 ? "text-emerald-400" : r.status_code ? "text-amber-400" : "text-muted-foreground"}>
                          {r.status_code || "—"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-[11px] text-red-400/70 max-w-[180px] truncate">{r.error || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {testing && !results.length && (
        <Card className="p-16 text-center" hover={false}>
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">Testing {limit} proxies...</p>
        </Card>
      )}
    </AppLayout>
  );
}
