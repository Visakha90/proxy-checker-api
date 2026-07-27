"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useWebSocket } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, Globe, Download, Zap, Code2, Users,
  Settings, Search, Menu, X, User,
} from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/proxies", label: "Proxies", icon: Globe },
  { href: "/download", label: "Download", icon: Download },
  { href: "/tester", label: "Tester", icon: Zap },
  { href: "/api-docs", label: "API", icon: Code2 },
  { href: "/users", label: "Users", icon: Users },
  { href: "/admin", label: "Admin", icon: Settings },
];

export function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { connected } = useWebSocket();
  const { user } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setCmdOpen(v => !v); }
      if (e.key === "Escape") { setCmdOpen(false); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div className="min-h-screen flex">
      {/* Sidebar — Desktop */}
      <aside className="hidden lg:flex fixed left-0 top-0 bottom-0 w-[240px] flex-col border-r border-border bg-card/80 backdrop-blur-xl z-40">
        <div className="h-16 flex items-center px-5 border-b border-border">
          <Link href="/" className="flex items-center gap-3 group">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/25 group-hover:shadow-blue-500/40 transition-shadow">
              <Globe className="w-4 h-4 text-white" />
            </div>
            <span className="text-sm font-bold tracking-tight">ProxyChecker</span>
          </Link>
        </div>

        {/* Search */}
        <div className="px-3 py-3">
          <button onClick={() => setCmdOpen(true)} className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl bg-secondary text-muted-foreground text-xs hover:bg-accent transition-colors">
            <Search className="w-3.5 h-3.5" />
            <span className="flex-1 text-left">Search...</span>
            <kbd className="text-[10px] px-1.5 py-0.5 rounded bg-background border border-border font-mono">⌘K</kbd>
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 space-y-1 overflow-y-auto">
          {navItems.map(item => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200",
                  active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground hover:bg-accent"
                )}>
                <Icon className="w-4 h-4" />
                {item.label}
                {active && <div className="ml-auto w-1.5 h-1.5 rounded-full bg-primary" />}
              </Link>
            );
          })}
        </nav>

        {/* Bottom */}
        <div className="p-3 border-t border-border space-y-2">
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-secondary/50">
            <div className={cn("w-2 h-2 rounded-full", connected ? "bg-success animate-pulse-slow" : "bg-destructive")} />
            <span className="text-2xs text-muted-foreground">{connected ? "Systems Operational" : "Reconnecting..."}</span>
          </div>
          <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-secondary/50">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-pink-500 flex items-center justify-center">
              <User className="w-3.5 h-3.5 text-white" />
            </div>
            <div className="flex-1 text-left">
              <p className="text-xs font-medium truncate">Team Admin</p>
              <p className="text-2xs text-muted-foreground">Private access</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 inset-x-0 h-14 border-b border-border bg-background/80 backdrop-blur-xl z-40 flex items-center px-4 justify-between">
        <button onClick={() => setSidebarOpen(true)} className="p-2 rounded-lg hover:bg-accent"><Menu className="w-5 h-5" /></button>
        <Link href="/" className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center"><Globe className="w-3.5 h-3.5 text-white" /></div>
          <span className="text-sm font-bold">ProxyChecker</span>
        </Link>
        <div className="w-9" />
      </div>

      {/* Mobile Sidebar Overlay */}
      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="lg:hidden fixed inset-0 bg-black/50 z-50" onClick={() => setSidebarOpen(false)} />
            <motion.aside initial={{ x: -240 }} animate={{ x: 0 }} exit={{ x: -240 }} transition={{ type: "spring", damping: 25 }}
              className="lg:hidden fixed left-0 top-0 bottom-0 w-[240px] bg-card border-r border-border z-50 flex flex-col">
              <div className="h-14 flex items-center justify-between px-4 border-b border-border">
                <span className="text-sm font-bold">Menu</span>
                <button onClick={() => setSidebarOpen(false)} className="p-1.5 rounded-lg hover:bg-accent"><X className="w-4 h-4" /></button>
              </div>
              <nav className="flex-1 p-3 space-y-1">
                {navItems.map(item => {
                  const Icon = item.icon;
                  return (
                    <Link key={item.href} href={item.href} onClick={() => setSidebarOpen(false)}
                      className={cn("flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium", pathname === item.href ? "bg-primary/10 text-primary" : "text-muted-foreground")}>
                      <Icon className="w-4 h-4" />{item.label}
                    </Link>
                  );
                })}
              </nav>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Main content */}
      <main className="flex-1 lg:ml-[240px] pt-14 lg:pt-0">
        <motion.div key={pathname} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto">
          {children}
        </motion.div>
      </main>

      {/* Command Palette */}
      <AnimatePresence>
        {cmdOpen && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[60]" onClick={() => setCmdOpen(false)} />
            <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}
              className="fixed top-[15%] left-1/2 -translate-x-1/2 w-full max-w-lg z-[60] rounded-2xl bg-card border border-border shadow-2xl overflow-hidden">
              <div className="flex items-center gap-3 px-4 h-12 border-b border-border">
                <Search className="w-4 h-4 text-muted-foreground" />
                <input autoFocus placeholder="Search proxies, pages, commands..." className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
                <kbd className="text-2xs px-1.5 py-0.5 rounded bg-secondary border border-border font-mono text-muted-foreground">ESC</kbd>
              </div>
              <div className="p-2 max-h-[320px] overflow-y-auto">
                {navItems.map(item => {
                  const Icon = item.icon;
                  return (
                    <Link key={item.href} href={item.href} onClick={() => setCmdOpen(false)}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                      <Icon className="w-4 h-4" />{item.label}
                    </Link>
                  );
                })}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
      className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {description && <p className="text-sm text-muted-foreground mt-1">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </motion.div>
  );
}
