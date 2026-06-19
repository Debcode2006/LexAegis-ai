"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function EvaluationPage() {
  const { token } = useAuth();
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.evaluation(token).then(setReport).catch((e) => setError(e.message));
  }, [token]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Evaluation Dashboard</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {!report || report.available === false ? (
        <Card>
          <CardContent className="pt-5 text-sm text-slate-500">
            No evaluation report yet. Run{" "}
            <code className="rounded bg-slate-100 px-1">python evaluation/evaluate_local.py</code>{" "}
            (or <code className="rounded bg-slate-100 px-1">run_ragas.py</code> /{" "}
            <code className="rounded bg-slate-100 px-1">run_deepeval.py</code>) and refresh.
          </CardContent>
        </Card>
      ) : (
        <>
          <p className="text-sm text-slate-500">
            Dataset: <span className="font-medium">{report.dataset}</span> · Evaluator:{" "}
            <span className="font-medium">{report.evaluator}</span> · Generated:{" "}
            {report.generated_at}
          </p>

          <div className="grid gap-4 sm:grid-cols-3">
            {Object.entries(report.summary ?? {}).map(([metric, value]) => (
              <Card key={metric}>
                <CardContent className="pt-5">
                  <p className="text-sm capitalize text-slate-500">
                    {metric.replace(/_/g, " ")}
                  </p>
                  <p className="text-2xl font-bold">
                    {typeof value === "number" ? value.toFixed(3) : String(value)}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>

          {report.samples?.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Per-sample results</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {report.samples.map((s: any, i: number) => (
                  <div key={i} className="rounded-md border border-slate-200 p-3 text-sm">
                    <p className="font-medium">{s.question}</p>
                    <p className="mt-1 text-slate-600">{s.answer}</p>
                    {s.scores && (
                      <p className="mt-2 text-xs text-slate-400">
                        {Object.entries(s.scores)
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(" · ")}
                      </p>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
