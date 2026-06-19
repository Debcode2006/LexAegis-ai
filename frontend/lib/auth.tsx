"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

type AuthState = {
  token: string | null;
  email: string | null;
  setToken: (token: string | null, email?: string | null) => void;
  loginWithPassword: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

const TOKEN_KEY = "lexaegis_token";
const EMAIL_KEY = "lexaegis_email";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [email, setEmailState] = useState<string | null>(null);

  useEffect(() => {
    setTokenState(localStorage.getItem(TOKEN_KEY));
    setEmailState(localStorage.getItem(EMAIL_KEY));
  }, []);

  const setToken = (value: string | null, mail: string | null = null) => {
    setTokenState(value);
    setEmailState(mail);
    if (value) {
      localStorage.setItem(TOKEN_KEY, value);
      if (mail) localStorage.setItem(EMAIL_KEY, mail);
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(EMAIL_KEY);
    }
  };

  const loginWithPassword = async (mail: string, password: string) => {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (!url || !anon) {
      throw new Error(
        "Supabase is not configured. Use the dev-token login below instead."
      );
    }
    const res = await fetch(`${url}/auth/v1/token?grant_type=password`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: anon },
      body: JSON.stringify({ email: mail, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error_description || err.msg || "Login failed");
    }
    const data = await res.json();
    setToken(data.access_token, mail);
  };

  const logout = () => setToken(null);

  return (
    <AuthContext.Provider
      value={{ token, email, setToken, loginWithPassword, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
