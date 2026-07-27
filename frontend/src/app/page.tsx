"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchJson, type Stats } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function Navbar() {
  return (
    <header className="fixed top-0 inset-x-0 z-50 border-b border-white/[0.06] bg-background/60 backdrop-blur-xl">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-400 flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="black" strokeWidth="2.5" strokeLinecap="round">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
            </svg>
          </div>
          <span className="text-sm font-semibold">ProxyChecker</span>
        </Link>
        <nav className="hidden md:flex items-center gap-6 text-[13px] text-muted-foreground">
          <a href="#features" className="hover:text-foreground transition-colors">Features</a>
          <a href="#stats" className="hover:text-foreground transition-colors">Stats</a>
          <a href="#api" className="hover:text-foreground transition-colors">API</a>
          <a href="#faq" className="hover:text-foreground transition-colors">FAQ</a>
        </nav>
        <div className="flex items-center gap-2">
          <Link href="/login">
            <Button variant="ghost" size="sm">Sign In</Button>
          </Link>
          <Link href="/dashboard">
            <Button size="sm">Dashboard</Button>
          </Link>
        </div>
      </div>
    </header>
  );
}

function HeroSection() {
  return (
    <section className="relative pt-32 pb-20 overflow-hidden">
      {/* Glow effects */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-emerald-500/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute top-20 right-1/4 w-[300px] h-[300px] bg-cyan-500/5 rounded-full blur-[100px] pointer-events-none" />

      <div className="relative max-w-4xl mx-auto text-center px-4">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          Live proxy infrastructure
        </div>

        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-[1.1] mb-6">
          Enterprise-grade{" "}
          <span className="text-gradient">proxy infrastructure</span>
          {" "}at your fingertips
        </h1>

        <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed">
          Automatically scrape, validate, and deliver thousands of proxies in real-time.
          Built for developers who need reliable proxy data without the hassle.
        </p>

        <div className="flex items-center justify-center gap-3 mb-16">
          <Link href="/dashboard">
            <Button size="lg">
              Open Dashboard
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </Button>
          </Link>
          <Link href="/api-docs">
            <Button variant="secondary" size="lg">View API Docs</Button>
          </Link>
        </div>

        {/* Code preview */}
        <div className="max-w-xl mx-auto rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden shadow-2xl shadow-black/40">
          <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-white/[0.06] bg-white/[0.02]">
            <div className="w-2.5 h-2.5 rounded-full bg-white/10" />
            <div className="w-2.5 h-2.5 rounded-full bg-white/10" />
            <div className="w-2.5 h-2.5 rounded-full bg-white/10" />
            <span className="ml-3 text-[11px] text-muted-foreground font-mono">Terminal</span>
          </div>
          <pre className="p-4 text-[13px] font-mono text-left overflow-x-auto">
            <code>
              <span className="text-muted-foreground">$</span>{" "}
              <span className="text-emerald-400">curl</span>{" "}
              <span className="text-gray-300">https://api.proxychecker.io/v1/proxies</span>{"\n"}
              <span className="text-muted-foreground">  </span>
              <span className="text-cyan-400">-H</span>{" "}
              <span className="text-amber-300">{'"X-API-Key: pc_abc123..."'}</span>{"\n\n"}
              <span className="text-muted-foreground">{"{"}</span>{"\n"}
              <span className="text-muted-foreground">{"  "}</span>
              <span className="text-cyan-300">{'"success"'}</span>
              <span className="text-muted-foreground">: </span>
              <span className="text-emerald-400">true</span>
              <span className="text-muted-foreground">,</span>{"\n"}
              <span className="text-muted-foreground">{"  "}</span>
              <span className="text-cyan-300">{'"count"'}</span>
              <span className="text-muted-foreground">: </span>
              <span className="text-amber-300">100</span>
              <span className="text-muted-foreground">,</span>{"\n"}
              <span className="text-muted-foreground">{"  "}</span>
              <span className="text-cyan-300">{'"total"'}</span>
              <span className="text-muted-foreground">: </span>
              <span className="text-amber-300">5231</span>{"\n"}
              <span className="text-muted-foreground">{"}"}</span>
            </code>
          </pre>
        </div>
      </div>
    </section>
  );
}

function FeaturesSection() {
  const features = [
    { title: "Auto Scraping", desc: "Continuously scrapes from 50+ public proxy sources every 10 seconds", icon: "⚡" },
    { title: "Real-time Checking", desc: "Validates every proxy with 500+ concurrent connections for speed", icon: "🔍" },
    { title: "Smart Filtering", desc: "Filter by country, anonymity, latency, protocol, and SSL support", icon: "🎯" },
    { title: "REST API", desc: "Production-ready API with rate limiting, caching, and SDK support", icon: "🔌" },
    { title: "WebSocket Live", desc: "Real-time statistics pushed via WebSocket every 10 seconds", icon: "📡" },
    { title: "Multi-format Export", desc: "Download as TXT, CSV, or JSON. Integrate with any system", icon: "📦" },
  ];

  return (
    <section id="features" className="py-24 relative">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="text-center mb-14">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-3">
            Everything you need for proxy management
          </h2>
          <p className="text-muted-foreground max-w-lg mx-auto">
            A complete platform for discovering, validating, and delivering high-quality proxies at scale.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {features.map((f, i) => (
            <div
              key={i}
              className="group rounded-xl border border-white/[0.06] bg-white/[0.02] p-6 transition-all duration-300 hover:bg-white/[0.04] hover:border-white/[0.1]"
            >
              <div className="text-2xl mb-3">{f.icon}</div>
              <h3 className="text-sm font-semibold mb-1.5">{f.title}</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function LiveStatsSection() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    fetchJson<Stats>("/api/stats").then(setStats).catch(() => {});
  }, []);

  const items = stats ? [
    { label: "Total Proxies", value: stats.total_proxies.toLocaleString() },
    { label: "Live Proxies", value: stats.alive_proxies.toLocaleString() },
    { label: "Avg Latency", value: `${Math.round(stats.avg_latency)}ms` },
    { label: "HTTP", value: stats.http_count.toLocaleString() },
    { label: "SOCKS4", value: stats.socks4_count.toLocaleString() },
    { label: "SOCKS5", value: stats.socks5_count.toLocaleString() },
  ] : null;

  return (
    <section id="stats" className="py-24 relative">
      <div className="absolute inset-0 bg-gradient-to-b from-emerald-500/[0.02] to-transparent pointer-events-none" />
      <div className="relative max-w-6xl mx-auto px-4 sm:px-6">
        <div className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-3">
            Live Statistics
          </h2>
          <p className="text-muted-foreground">Updated in real-time as proxies are checked</p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {items ? items.map((item, i) => (
            <div
              key={i}
              className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-center animate-fade-in"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              <p className="text-xl sm:text-2xl font-bold text-gradient">{item.value}</p>
              <p className="text-[11px] text-muted-foreground mt-1 uppercase tracking-wide">{item.label}</p>
            </div>
          )) : Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-center">
              <div className="h-7 w-16 mx-auto rounded bg-white/[0.04] animate-pulse mb-1" />
              <div className="h-3 w-12 mx-auto rounded bg-white/[0.04] animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function APISection() {
  return (
    <section id="api" className="py-24">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-4">
              Developer-first API
            </h2>
            <p className="text-muted-foreground mb-6 leading-relaxed">
              Simple, powerful REST API with support for 8 programming languages.
              Get started in under a minute with your API key.
            </p>
            <div className="space-y-3 mb-8">
              {[
                "Filter by country, type, anonymity, latency",
                "JSON, CSV, and TXT download formats",
                "Redis-cached responses with ETag support",
                "Rate limiting with clear headers",
                "Prometheus metrics endpoint",
              ].map((item, i) => (
                <div key={i} className="flex items-center gap-2.5 text-sm text-gray-300">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="text-emerald-400 flex-shrink-0">
                    <path d="M5 12l5 5L20 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {item}
                </div>
              ))}
            </div>
            <Link href="/api-docs">
              <Button>Explore API Docs</Button>
            </Link>
          </div>

          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden">
            <div className="px-4 py-2.5 border-b border-white/[0.06] flex items-center gap-2">
              <span className="text-[11px] font-mono text-emerald-400">GET</span>
              <span className="text-[11px] font-mono text-muted-foreground">/api/v1/proxies</span>
            </div>
            <pre className="p-4 text-[12px] font-mono text-gray-400 overflow-x-auto leading-relaxed">
{`{
  "success": true,
  "count": 100,
  "page": 1,
  "total": 5231,
  "data": [
    {
      "ip": "47.243.92.199",
      "port": 3128,
      "type": "http",
      "country": "United States",
      "country_code": "US",
      "anonymity": "elite",
      "latency": 120.5,
      "ssl": true,
      "alive": true,
      "last_checked": "2026-07-27T..."
    }
  ]
}`}
            </pre>
          </div>
        </div>
      </div>
    </section>
  );
}

function FAQSection() {
  const faqs = [
    { q: "How often are proxies checked?", a: "Every proxy is validated every 30 seconds using 500+ concurrent connections. Dead proxies are automatically removed." },
    { q: "What proxy types are supported?", a: "HTTP, HTTPS, SOCKS4, and SOCKS5 proxies are all supported with automatic type detection and filtering." },
    { q: "Is there a free tier?", a: "Yes. Guest users get 100 requests per hour. Free API keys allow 1,000 requests per day. Premium keys have no limits." },
    { q: "How do I get an API key?", a: "Sign in to the admin panel and navigate to the API section. You can generate keys instantly with configurable rate limits." },
    { q: "Can I add custom proxy sources?", a: "Absolutely. The admin panel allows you to add unlimited proxy source URLs that will be scraped automatically." },
  ];

  const [open, setOpen] = useState<number | null>(null);

  return (
    <section id="faq" className="py-24">
      <div className="max-w-2xl mx-auto px-4 sm:px-6">
        <div className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-3">
            Frequently asked questions
          </h2>
        </div>

        <div className="space-y-2">
          {faqs.map((faq, i) => (
            <div
              key={i}
              className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden transition-all"
            >
              <button
                onClick={() => setOpen(open === i ? null : i)}
                className="w-full flex items-center justify-between px-5 py-4 text-left"
              >
                <span className="text-sm font-medium">{faq.q}</span>
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className={cn(
                    "text-muted-foreground transition-transform duration-200",
                    open === i && "rotate-180"
                  )}
                >
                  <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              {open === i && (
                <div className="px-5 pb-4 animate-fade-in">
                  <p className="text-sm text-muted-foreground leading-relaxed">{faq.a}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-white/[0.06] py-12">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-emerald-400 to-cyan-400 flex items-center justify-center">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="black" strokeWidth="3" strokeLinecap="round">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              </svg>
            </div>
            <span className="text-xs text-muted-foreground">ProxyChecker</span>
          </div>
          <div className="flex items-center gap-6 text-xs text-muted-foreground">
            <Link href="/dashboard" className="hover:text-foreground transition-colors">Dashboard</Link>
            <Link href="/api-docs" className="hover:text-foreground transition-colors">API</Link>
            <Link href="/download" className="hover:text-foreground transition-colors">Download</Link>
            <a href="http://localhost:8000/docs" target="_blank" className="hover:text-foreground transition-colors">Swagger</a>
          </div>
          <p className="text-[11px] text-muted-foreground/60">
            Built with FastAPI + Next.js
          </p>
        </div>
      </div>
    </footer>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <Navbar />
      <HeroSection />
      <FeaturesSection />
      <LiveStatsSection />
      <APISection />
      <FAQSection />
      <Footer />
    </div>
  );
}
