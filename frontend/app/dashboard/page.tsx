"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function DashboardPage() {
  const { token } = useAuth();
  const [metrics, setMetrics] = useState<any>(null);
  const [docCount, setDocCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.metrics(token).then(setMetrics).catch((e) => setError(e.message));
    api.listDocuments(token).then((d) => setDocCount(d.count)).catch(() => {});
  }, [token]);

  // Derive observability stats from GET /observability/metrics. Request-level
  // latency/count come from the "chat.turn" span (one per request); trace count
  // is the total span volume (chat.turn + per-agent spans). All values come from
  // the always-on in-process recorder — no Phoenix, no extra service.
  const traces = metrics?.traces;
  const cache = metrics?.cache;
  const turn = traces?.by_name?.["chat.turn"];
  const avgLatency = turn?.avg_ms ?? traces?.avg_latency_ms ?? 0;
  const maxLatency = turn?.max_ms ?? 0;
  const requestCount = turn?.count ?? 0;
  const traceCount = traces?.count ?? 0;
  const hitRate = cache?.hit_rate ?? 0;

  const observability = [
    { label: "Average latency", value: metrics ? `${Math.round(avgLatency)} ms` : "—" },
    { label: "Max latency", value: metrics ? `${Math.round(maxLatency)} ms` : "—" },
    { label: "Request count", value: metrics ? requestCount : "—" },
    { label: "Cache hit rate", value: metrics ? `${Math.round(hitRate * 100)}%` : "—" },
    { label: "Trace count", value: metrics ? traceCount : "—" },
  ];

  const tiles = [
    { href: "/upload", title: "Upload Documents", desc: "Ingest contracts, policies, regulations." },
    { href: "/chat", title: "Legal Chat", desc: "Ask grounded, cited legal questions." },
    { href: "/documents", title: "Document Explorer", desc: "Browse ingested documents." },
    { href: "/evaluation", title: "Evaluation", desc: "Retrieval & answer quality metrics." },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="pt-5">
            <p className="text-sm text-slate-500">Documents ingested</p>
            <p className="text-3xl font-bold">{docCount ?? "—"}</p>
          </CardContent>
        </Card>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Observability</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {observability.map((stat) => (
            <Card key={stat.label}>
              <CardContent className="pt-5">
                <p className="text-sm text-slate-500">{stat.label}</p>
                <p className="text-3xl font-bold">{stat.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2">
        {tiles.map((t) => (
          <Link key={t.href} href={t.href}>
            <Card className="transition hover:shadow-md">
              <CardHeader>
                <CardTitle>{t.title}</CardTitle>
              </CardHeader>
              <CardContent className="pt-0 text-sm text-slate-500">{t.desc}</CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
