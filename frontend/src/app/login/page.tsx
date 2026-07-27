"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get("redirect") || "/dashboard";
  const { login: authLogin } = useAuth();
  const [loginInput, setLoginInput] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      // Try user login first
      let res = await fetch(`${API_URL}/api/users/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login: loginInput, password }),
      });

      if (res.ok) {
        const data = await res.json();
        authLogin(data.access_token, data.user);
        router.push(redirect);
        return;
      }

      // Fallback: admin login
      res = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginInput, password }),
      });

      if (res.ok) {
        const data = await res.json();
        authLogin(data.access_token);
        router.push(redirect.startsWith("/admin") ? redirect : "/admin");
        return;
      }

      const errData = await res.json().catch(() => ({}));
      setError(errData.detail || "Invalid username/email or password");
    } catch {
      setError("Connection failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[400px] h-[300px] bg-emerald-500/5 rounded-full blur-[100px] pointer-events-none" />

      <div className="relative w-full max-w-sm animate-slide-up">
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2 mb-6">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-400 via-cyan-400 to-indigo-400 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="black" strokeWidth="2.5" strokeLinecap="round">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              </svg>
            </div>
          </Link>
          <h1 className="text-lg font-semibold">Welcome back</h1>
          <p className="text-sm text-muted-foreground mt-1">Sign in with your username, email, or admin account</p>
        </div>

        <div className="rounded-2xl surface-1 p-6">
          <form onSubmit={handleLogin} className="space-y-4">
            <Input
              label="Username or Email"
              value={loginInput}
              onChange={(e) => setLoginInput(e.target.value)}
              placeholder="admin or you@email.com"
              autoComplete="username"
              required
            />
            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
            {error && (
              <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/15">
                <p className="text-[11px] text-red-400">{error}</p>
              </div>
            )}
            <Button type="submit" loading={loading} className="w-full">
              Sign In
            </Button>
          </form>
        </div>

        <div className="flex items-center justify-between mt-5 text-xs text-muted-foreground">
          <Link href="/" className="hover:text-foreground transition-colors">← Home</Link>
          <Link href={`/register${redirect !== "/dashboard" ? `?redirect=${encodeURIComponent(redirect)}` : ""}`} className="text-primary hover:underline">
            Create account
          </Link>
        </div>
      </div>
    </div>
  );
}
