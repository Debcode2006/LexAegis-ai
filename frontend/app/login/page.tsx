"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
  const router = useRouter();
  const { loginWithPassword, setToken } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [devToken, setDevToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await loginWithPassword(email, password);
      router.push("/dashboard");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const useDevToken = () => {
    if (!devToken.trim()) return;
    setToken(devToken.trim(), "dev-token");
    router.push("/dashboard");
  };

  const fillDemo = () => {
    setEmail("demo@lexaegis.ai");
    setPassword("Demo@12345");
    setError(null);
  };

  return (
    <div className="mx-auto mt-10 max-w-md">
      <h1 className="mb-1 text-center text-3xl font-bold text-brand">⚖️ LexAegis AI</h1>
      <p className="mb-6 text-center text-sm text-slate-500">
        Agentic Legal Intelligence Platform
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={submit} className="space-y-3">
            <Input
              type="email"
              placeholder="you@firm.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in…" : "Sign in with Supabase"}
            </Button>
          </form>

          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={fillDemo}
            disabled={loading}
          >
            Try demo
          </Button>
          <p className="text-center text-xs text-slate-400">
            Fills demo credentials — just press “Sign in”.
          </p>

          <div className="relative py-2 text-center text-xs text-slate-400">
            — or paste a dev JWT —
          </div>
          <Input
            placeholder="Paste a Supabase access token"
            value={devToken}
            onChange={(e) => setDevToken(e.target.value)}
          />
          <Button variant="outline" className="w-full" onClick={useDevToken}>
            Continue with token
          </Button>

          {error && <p className="text-sm text-red-600">{error}</p>}
        </CardContent>
      </Card>
    </div>
  );
}
