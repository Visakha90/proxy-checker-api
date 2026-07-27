"use client";

import { useEffect, useState, useRef } from "react";
import { motion } from "framer-motion";
import { AppLayout, PageHeader } from "@/components/layout";
import { RequireAuth } from "@/lib/auth";
import { useWebSocket } from "@/lib/hooks";
import { fetchJson, type Stats } from "@/lib/api";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, PieChart, Pie, Cell } from "recharts";

function AnimatedCounter({ value, suffix = "" }: { value: number; suffix?: string }) {
  const [display, setDisplay] = useState(0);
  const prev = useRef(0);
  useEffect(() => {
    const start = prev.current;
    const diff = value - start;
    const duration = 1200;
    const startTime = Date.now();
    const tick = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(start + diff * eased));
      if (progress < 1) requestAnimationFrame(tick);
      else prev.current = value;
    };
    requestAnimationFrame(tick);
  }, [value]);
  return <>{display.toLocaleString()}{suffix}</>;
}

function BentoCard({ children, className = "", delay = 0 }: { children: React.ReactNode; className?: string; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className={`rounded-2xl surface-1 p-5 ${className}`}
    >
      {children}
    </motion.div>
  );
}

const ChartTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg surface-2 px-3 py-2 shadow-xl text-xs">
      {payload.map((p: any, i: number) => (
        <div key={i} className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-medium">{p.value?.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
};

function DashboardContent() {
  const { stats } = useWebSocket();
  const [history, setHistory] = useState<any[]>([]);
  const [initial, setInitial] = useState<Stats | null>(null);

  useEffect(() => {
    fetchJson<Stats>("/api/stats").then(setInitial).catch(() => {});
    fetchJson<any[]>("/api/history?limit=30").then(setHistory).catch(() => {});
  }, []);

  const s = stats || initial;
  const typeData = s ? [
    { name: "HTTP", value: s.http_count, color: "#34d399" },
    { name: "SOCKS4", value: s.socks4_count, color: "#818cf8" },
    { name: "SOCKS5", value: s.socks5_count, color: "#f472b6" },
  ].filter(d => d.value > 0) : [];

  if (!s) return (
    <div className="flex items-center justify-center h-[50vh]">
      <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <>
      <PageHeader title="Dashboard" description="Real-time proxy infrastructure" />

      <div className="grid grid-cols-12 gap-4 mb-6">
        <BentoCard className="col-span-12 sm:col-span-6 lg:col-span-3" delay={0}>
          <p className="text-2xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Total Proxies</p>
          <p className="text-3xl font-bold tracking-tight"><AnimatedCounter value={s.total_proxies} /></p>
        </BentoCard>
        <BentoCard className="col-span-12 sm:col-span-6 lg:col-span-3 relative overflow-hidden" delay={0.05}>
          <div className="absolute top-0 right-0 w-20 h-20 bg-emerald-500/5 rounded-full blur-2xl" />
          <p className="text-2xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Alive</p>
          <p className="text-3xl font-bold tracking-tight text-emerald-400"><AnimatedCounter value={s.alive_proxies} /></p>
          <p className="text-2xs text-emerald-400/70 mt-1">{((s.alive_proxies / Math.max(s.total_proxies, 1)) * 100).toFixed(1)}% success rate</p>
        </BentoCard>
        <BentoCard className="col-span-6 lg:col-span-3" delay={0.1}>
          <p className="text-2xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Avg Latency</p>
          <p className="text-3xl font-bold tracking-tight text-cyan-400"><AnimatedCounter value={Math.round(s.avg_latency)} suffix="ms" /></p>
        </BentoCard>
        <BentoCard className="col-span-6 lg:col-span-3" delay={0.15}>
          <p className="text-2xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Dead</p>
          <p className="text-3xl font-bold tracking-tight text-red-400"><AnimatedCounter value={s.dead_proxies} /></p>
        </BentoCard>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        {[
          { label: "HTTP", value: s.http_count, color: "text-emerald-400" },
          { label: "SOCKS4", value: s.socks4_count, color: "text-indigo-400" },
          { label: "SOCKS5", value: s.socks5_count, color: "text-pink-400" },
          { label: "Elite", value: s.elite_count, color: "text-amber-400" },
          { label: "Anonymous", value: s.anonymous_count, color: "text-cyan-400" },
          { label: "Transparent", value: s.transparent_count, color: "text-gray-400" },
        ].map((m, i) => (
          <BentoCard key={m.label} className="!p-4" delay={0.2 + i * 0.03}>
            <p className="text-2xs text-muted-foreground uppercase tracking-wider mb-1">{m.label}</p>
            <p className={`text-lg font-bold ${m.color}`}><AnimatedCounter value={m.value} /></p>
          </BentoCard>
        ))}
      </div>

      <div className="grid grid-cols-12 gap-4">
        <BentoCard className="col-span-12 lg:col-span-8 !p-4" delay={0.3}>
          <p className="text-2xs font-medium text-muted-foreground uppercase tracking-wider mb-4">Proxy Growth</p>
          <div className="h-[240px]">
            {history.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="gAlive" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#34d399" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="recorded_at" tick={{ fontSize: 10, fill: "hsl(220,10%,40%)" }} tickFormatter={v => v ? new Date(v).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}) : ""} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: "hsl(220,10%,40%)" }} axisLine={false} tickLine={false} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area type="monotone" dataKey="alive_proxies" stroke="#34d399" strokeWidth={2} fill="url(#gAlive)" name="Alive" />
                  <Area type="monotone" dataKey="dead_proxies" stroke="#f87171" strokeWidth={1} fill="transparent" name="Dead" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <div className="h-full flex items-center justify-center text-xs text-muted-foreground">Collecting data...</div>}
          </div>
        </BentoCard>

        <BentoCard className="col-span-12 lg:col-span-4 !p-4" delay={0.35}>
          <p className="text-2xs font-medium text-muted-foreground uppercase tracking-wider mb-4">Distribution</p>
          <div className="h-[200px]">
            {typeData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={typeData} cx="50%" cy="50%" innerRadius={55} outerRadius={80} dataKey="value" strokeWidth={0}>
                    {typeData.map((d, i) => <Cell key={i} fill={d.color} />)}
                  </Pie>
                  <Tooltip content={<ChartTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            ) : <div className="h-full flex items-center justify-center text-xs text-muted-foreground">No data</div>}
          </div>
          <div className="flex justify-center gap-4 mt-2">
            {typeData.map(d => (
              <div key={d.name} className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full" style={{ background: d.color }} />
                <span className="text-2xs text-muted-foreground">{d.name}</span>
              </div>
            ))}
          </div>
        </BentoCard>
      </div>
    </>
  );
}

export default function DashboardPage() {
  return (
    <AppLayout>
      <RequireAuth>
        <DashboardContent />
      </RequireAuth>
    </AppLayout>
  );
}
