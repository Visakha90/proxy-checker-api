"use client";

import { createContext, useContext, ReactNode } from "react";

interface User {
  id: number;
  username: string;
  email?: string;
  role: string;
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
  user: { id: 1, username: "admin", role: "admin" },
  token: "internal",
  isAuthenticated: true,
  isLoading: false,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  return (
    <AuthContext.Provider value={{
      user: { id: 1, username: "admin", role: "admin" },
      token: "internal",
      isAuthenticated: true,
      isLoading: false,
      login: () => {},
      logout: () => {},
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export function RequireAuth({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
