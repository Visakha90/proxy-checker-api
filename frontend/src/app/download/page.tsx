"use client";

import { useState } from "react";
import { AppLayout, PageHeader } from "@/components/layout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const types = [
  { key: "http", label: "HTTP", desc: "Standard HTTP proxies", color: "from-emerald-500/20 to-emerald-500/5", border: "border-emerald-500/20", text: "text-emerald-400" },
  { key: "https", label: "HTTPS", desc: "SSL-enabled proxies", color: "from-cyan-500/20 to-cyan-500/5", border: "border-cyan-500/20", text: "text-cyan-400" },
  { key: "socks4", label: "SOCKS4", desc: "SOCKS4 protocol", color: "from-violet-500/20 to-violet-500/5", border: "border-violet-500/20", text: "text-violet-400" },
  { key: "socks5", label: "SOCKS5", desc: "SOCKS5 protocol", color: "from-pink-500/20 to-pink-500/5", border: "border-pink-500/20", text: "text-pink-400" },
  { key: "elite", label: "Elite", desc: "Highest anonymity", color: "from-amber-500/20 to-amber-500/5", border: "border-amber-500/20", text: "text-amber-400" },
  { key: "anonymous", label: "Anonymous", desc: "Anonymous level", color: "from-blue-500/20 to-blue-500/5", border: "border-blue-500/20", text: "text-blue-400" },
  { key: "all", label: "All Proxies", desc: "Every live proxy", color: "from-white/10 to-white/5", border: "border-white/10", text: "text-foreground" },
];

const formats = [
  { value: "txt", label: "TXT", desc: "ip:port per line" },
  { value: "csv", label: "CSV", desc: "Comma separated" },
  { value: "json", label: "JSON", desc: "Structured data" },
];

export default function DownloadPage() {
  const [format, setFormat] = useState("txt");
  const [downloading, setDownloading] = useState<string | null>(null);

  const handleDownload = async (type: string) => {
    setDownloading(type);
    try {
      const r = await fetch(`${API_URL}/api/download/${type}?format=${format}`);
      if (!r.ok) throw new Error("Download failed");
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${type}_proxies.${format}`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { console.error(e); }
    finally { setDownloading(null); }
  };

  return (
    <AppLayout>
      <PageHeader title="Download" description="Export live-checked proxies in multiple formats" />

      {/* Format selector */}
      <div className="flex items-center gap-2 mb-6">
        {formats.map((f) => (
          <button
            key={f.value}
            onClick={() => setFormat(f.value)}
            className={cn(
              "px-4 py-2 rounded-lg text-xs font-medium transition-all duration-200 border",
              format === f.value
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                : "bg-white/[0.02] text-muted-foreground border-white/[0.06] hover:bg-white/[0.04] hover:border-white/[0.1]"
            )}
          >
            <span className="font-semibold">{f.label}</span>
            <span className="ml-1.5 text-muted-foreground hidden sm:inline">{f.desc}</span>
          </button>
        ))}
      </div>

      {/* Download grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {types.map((t) => (
          <div
            key={t.key}
            className={cn(
              "rounded-xl border bg-gradient-to-b p-5 transition-all duration-300 hover:scale-[1.02]",
              t.color, t.border
            )}
          >
            <h3 className={cn("text-sm font-semibold mb-0.5", t.text)}>{t.label}</h3>
            <p className="text-[11px] text-muted-foreground mb-4">{t.desc}</p>
            <Button
              size="sm"
              variant="secondary"
              className="w-full"
              loading={downloading === t.key}
              onClick={() => handleDownload(t.key)}
            >
              Download .{format}
            </Button>
          </div>
        ))}
      </div>

      {/* API URLs */}
      <Card className="mt-8 p-5" hover={false}>
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-3">
          Direct API URLs
        </h3>
        <div className="space-y-1.5 font-mono text-xs">
          {types.map((t) => (
            <div key={t.key} className="flex items-center gap-2 py-1">
              <span className="text-emerald-400 font-medium w-8">GET</span>
              <span className="text-muted-foreground">/api/v1/download/{t.key}?format={format}</span>
            </div>
          ))}
        </div>
      </Card>
    </AppLayout>
  );
}
