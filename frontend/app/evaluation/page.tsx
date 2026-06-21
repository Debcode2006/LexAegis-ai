"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatTimestamp(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function EvaluationPage() {
  const { token } = useAuth();
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.evaluation(token).then(setReport).catch((e) => setError(e.message));
  }, [token]);

  const generatedAt = formatTimestamp(report?.generated_at);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Evaluation</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {!report || report.available === false ? (
        <Card>
          <CardContent className="pt-5 text-sm text-slate-500">
            No evaluation metrics are available to display yet.
          </CardContent>
        </Card>
      ) : (
        <>
          <p className="text-sm text-slate-500">
            {report.dataset && (
              <>
                Dataset: <span className="font-medium">{report.dataset}</span>
              </>
            )}
            {report.dataset && generatedAt && " · "}
            {generatedAt && (
              <>
                Last evaluated: <span className="font-medium">{generatedAt}</span>
              </>
            )}
          </p>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Quality Metrics</h2>
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
          </section>

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

          {(report.evaluator || report.judge_model || report.dataset) && (
            <details className="text-xs text-slate-400">
              <summary className="cursor-pointer select-none text-slate-500">
                Report details
              </summary>
              <dl className="mt-2 space-y-1 pl-1">
                {report.dataset && (
                  <div>
                    <dt className="inline font-medium">Dataset: </dt>
                    <dd className="inline">{report.dataset}</dd>
                  </div>
                )}
                {report.evaluator && (
                  <div>
                    <dt className="inline font-medium">Evaluator: </dt>
                    <dd className="inline">{report.evaluator}</dd>
                  </div>
                )}
                {report.judge_model && (
                  <div>
                    <dt className="inline font-medium">Judge model: </dt>
                    <dd className="inline">{report.judge_model}</dd>
                  </div>
                )}
                {generatedAt && (
                  <div>
                    <dt className="inline font-medium">Generated: </dt>
                    <dd className="inline">{generatedAt}</dd>
                  </div>
                )}
              </dl>
            </details>
          )}
        </>
      )}
    </div>
  );
}
