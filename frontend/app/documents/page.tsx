"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type DocumentSummary } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";

export default function DocumentsPage() {
  const { token } = useAuth();
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    api
      .listDocuments(token)
      .then((d) => setDocs(d.documents))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Document Explorer</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {loading ? (
        <p className="text-slate-500">Loading…</p>
      ) : docs.length === 0 ? (
        <p className="text-slate-500">No documents ingested yet. Upload one to get started.</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Pages</th>
                <th className="px-4 py-3">Chunks</th>
                <th className="px-4 py-3">PII masked</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.document_id} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-medium">{d.document_name}</td>
                  <td className="px-4 py-3">{d.document_type}</td>
                  <td className="px-4 py-3">{d.pages}</td>
                  <td className="px-4 py-3">{d.chunks_indexed}</td>
                  <td className="px-4 py-3">{d.pii_entities_masked}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
