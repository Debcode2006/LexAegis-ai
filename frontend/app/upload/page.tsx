"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type DocumentSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TYPES = [
  "contract",
  "compliance_manual",
  "regulation",
  "policy",
  "legal_document",
  "unknown",
];

export default function UploadPage() {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [type, setType] = useState("contract");
  const [result, setResult] = useState<DocumentSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !token) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      setResult(await api.uploadDocument(token, file, type));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <h1 className="text-2xl font-bold">Upload Document</h1>
      <Card>
        <CardHeader>
          <CardTitle>Ingest a legal document (PDF / DOCX / TXT)</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm"
            />
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <Button type="submit" disabled={!file || loading}>
              {loading ? "Ingesting…" : "Upload & ingest"}
            </Button>
          </form>

          {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
          {result && (
            <div className="mt-5 rounded-md bg-green-50 p-4 text-sm text-green-900">
              <p className="font-medium">✓ Ingested {result.document_name}</p>
              <p>Chunks indexed: {result.chunks_indexed}</p>
              <p>Pages: {result.pages}</p>
              <p>PII entities masked: {result.pii_entities_masked}</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
