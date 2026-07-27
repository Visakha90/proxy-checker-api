"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { fetchJson } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get("redirect") || "/dashboard";
  const { login: authLogin } = useAuth();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await fetchJson<any>("/api/users/register", {
        method: "POST",
        body: JSON.stringify({ email, username, password }),
      });
      authLogin(data.token, data.user);
      router.push(redirect);
    } catch (err: any) {
      setError(err.message || "Registration failed");
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
          <h1 className="text-lg font-semibold">Create your account</h1>
          <p className="text-sm text-muted-foreground mt-1">Get started with a free API key instantly</p>
        </div>
        <div className="rounded-2xl surface-1 p-6">
          <form onSubmit={handleRegister} className="space-y-4">
            <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required />
            <Input label="Username" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" required />
            <Input label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Min 6 characters" required />
            {error && (
              <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/15">
                <p className="text-[11px] text-red-400">{error}</p>
              </div>
            )}
            <Button type="submit" loading={loading} className="w-full">Create Account</Button>
          </form>
        </div>
        <p className="text-center text-xs text-muted-foreground mt-5">
          Already have an account?{" "}
          <Link href={`/login${redirect !== "/dashboard" ? `?redirect=${encodeURIComponent(redirect)}` : ""}`} className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
