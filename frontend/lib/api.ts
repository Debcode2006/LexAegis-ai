import { API_BASE } from "./utils";

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handle(res: Response) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const message =
      body?.error?.message || body?.detail || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return res.json();
}

export type Citation = {
  marker: string;
  document_id: string;
  document_name: string;
  section?: string | null;
  clause?: string | null;
  page_number?: number | null;
  snippet: string;
};

export type ChatResponse = {
  query: string;
  answer: string;
  intent: string;
  confidence: number;
  confidence_breakdown?: Record<string, number> | null;
  citations: Citation[];
  groundedness?: {
    groundedness: number;
    citation_coverage: number;
    has_citations: boolean;
    unsupported_claims: string[];
  } | null;
  blocked: boolean;
  block_reason?: string | null;
};

export type DocumentSummary = {
  document_id: string;
  document_name: string;
  document_type: string;
  pages: number;
  chunks_indexed: number;
  pii_entities_masked: number;
};

export const api = {
  ping: () => fetch(`${API_BASE}/ping`).then(handle),

  whoami: (token: string) =>
    fetch(`${API_BASE}/auth/whoami`, { headers: authHeaders(token) }).then(handle),

  chat: (
    token: string,
    query: string,
    opts?: { documentIds?: string[]; includeTrace?: boolean }
  ): Promise<ChatResponse> =>
    fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders(token) },
      body: JSON.stringify({
        query,
        // Only send document_ids when a non-empty scope is selected; omitting it
        // preserves the "search all documents" default (backward compatible).
        ...(opts?.documentIds && opts.documentIds.length > 0
          ? { document_ids: opts.documentIds }
          : {}),
        ...(opts?.includeTrace ? { include_trace: true } : {}),
      }),
    }).then(handle),

  uploadDocument: (
    token: string,
    file: File,
    documentType: string
  ): Promise<DocumentSummary> => {
    const form = new FormData();
    form.append("file", file);
    form.append("document_type", documentType);
    return fetch(`${API_BASE}/documents/upload`, {
      method: "POST",
      headers: authHeaders(token),
      body: form,
    }).then(handle);
  },

  listDocuments: (
    token: string
  ): Promise<{ tenant_id: string; count: number; documents: DocumentSummary[] }> =>
    fetch(`${API_BASE}/documents`, { headers: authHeaders(token) }).then(handle),

  metrics: (token: string) =>
    fetch(`${API_BASE}/observability/metrics`, {
      headers: authHeaders(token),
    }).then(handle),

  evaluation: (token: string) =>
    fetch(`${API_BASE}/evaluation/results`, {
      headers: authHeaders(token),
    }).then(handle),
};
