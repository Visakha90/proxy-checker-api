"use client";

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface User {
  id: number;
  username: string;
  email?: string;
  role: string;
  plan: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (token: string, user?: User) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: true,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("token");
    if (stored) {
      setToken(stored);
      fetchProfile(stored);
    } else {
      setIsLoading(false);
    }
  }, []);

  const fetchProfile = async (t: string) => {
    try {
      const res = await fetch(`${API_URL}/api/users/me`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data.data);
      } else {
        // Token invalid, clear it
        localStorage.removeItem("token");
        setToken(null);
      }
    } catch {
      // Network error, keep token but no user data
    } finally {
      setIsLoading(false);
    }
  };

  const login = useCallback((newToken: string, newUser?: User) => {
    localStorage.setItem("token", newToken);
    setToken(newToken);
    if (newUser) {
      setUser(newUser);
    } else {
      fetchProfile(newToken);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!token, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

/**
 * Pages that require authentication.
 * Public pages are accessible without login.
 */
const PROTECTED_PAGES = [
  "/dashboard",
  "/admin",
  "/api-docs", // Only the keys/analytics tabs, handled within the page
];

const AUTH_REQUIRED_PAGES = [
  "/dashboard",
  "/admin",
];

/**
 * Wrapper for pages that require authentication.
 * Shows a CTA to sign in if not authenticated.
 */
export function RequireAuth({ children, fallback }: { children: ReactNode; fallback?: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    if (fallback) return <>{fallback}</>;

    return (
      <div className="flex flex-col items-center justify-center py-20 px-4 text-center">
        <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-5">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-primary">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0110 0v4" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold mb-2">Authentication Required</h2>
        <p className="text-sm text-muted-foreground max-w-sm mb-6">
          Sign in to access this feature. Create a free account to get your API key and start using the platform.
        </p>
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(`/login?redirect=${encodeURIComponent(pathname)}`)}
            className="px-5 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Sign In
          </button>
          <button
            onClick={() => router.push(`/register?redirect=${encodeURIComponent(pathname)}`)}
            className="px-5 py-2.5 rounded-lg surface-2 text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            Create Account
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

/**
 * Component that shows a sign-in CTA in place of sensitive content.
 */
export function AuthGate({
  children,
  message = "Sign in to create your first API key.",
  actionLabel = "Sign In to Access",
}: {
  children: ReactNode;
  message?: string;
  actionLabel?: string;
}) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  if (isLoading) {
    return (
      <div className="rounded-2xl surface-1 p-8 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="rounded-2xl surface-1 border-dashed p-8 text-center">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-muted-foreground mx-auto mb-3">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0110 0v4" />
        </svg>
        <p className="text-sm text-muted-foreground mb-4">{message}</p>
        <button
          onClick={() => router.push(`/login?redirect=${encodeURIComponent(pathname)}`)}
          className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity"
        >
          {actionLabel}
        </button>
      </div>
    );
  }

  return <>{children}</>;
}
