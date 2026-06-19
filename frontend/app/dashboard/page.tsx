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

  const tiles = [
    { href: "/upload", title: "Upload Documents", desc: "Ingest contracts, policies, regulations." },
    { href: "/chat", title: "Legal Chat", desc: "Ask grounded, cited legal questions." },
    { href: "/documents", title: "Document Explorer", desc: "Browse ingested documents." },
    { href: "/evaluation", title: "Evaluation", desc: "RAGAS / DeepEval quality metrics." },
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
        <Card>
          <CardContent className="pt-5">
            <p className="text-sm text-slate-500">Cache hit rate</p>
            <p className="text-3xl font-bold">
              {metrics ? `${Math.round((metrics.cache?.hit_rate ?? 0) * 100)}%` : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <p className="text-sm text-slate-500">Avg latency (traced)</p>
            <p className="text-3xl font-bold">
              {metrics ? `${metrics.traces?.avg_latency_ms ?? 0} ms` : "—"}
            </p>
          </CardContent>
        </Card>
      </div>

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
