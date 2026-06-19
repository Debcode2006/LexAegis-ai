"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type ChatResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { ConfidenceBadge } from "@/components/confidence-badge";

type Turn = { query: string; response: ChatResponse };

export default function ChatPage() {
  const { token } = useAuth();
  const [query, setQuery] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const ask = async () => {
    if (!query.trim() || !token) return;
    setError(null);
    setLoading(true);
    const q = query;
    setQuery("");
    try {
      const response = await api.chat(token, q);
      setTurns((prev) => [{ query: q, response }, ...prev]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Legal Chat</h1>

      <Card>
        <CardContent className="space-y-3 pt-5">
          <Textarea
            rows={3}
            placeholder="Ask a question about your documents…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
            }}
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">⌘/Ctrl + Enter to send</span>
            <Button onClick={ask} disabled={loading || !query.trim()}>
              {loading ? "Thinking…" : "Ask"}
            </Button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </CardContent>
      </Card>

      {turns.map((turn, i) => (
        <Card key={i}>
          <CardContent className="space-y-3 pt-5">
            <p className="font-medium text-slate-700">Q: {turn.query}</p>

            {turn.response.blocked ? (
              <p className="rounded-md bg-red-50 p-3 text-sm text-red-800">
                🚫 Blocked: {turn.response.block_reason}
              </p>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <ConfidenceBadge value={turn.response.confidence} />
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs">
                    intent: {turn.response.intent}
                  </span>
                  {turn.response.groundedness && (
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs">
                      groundedness: {Math.round(turn.response.groundedness.groundedness * 100)}%
                    </span>
                  )}
                </div>

                <p className="whitespace-pre-wrap text-sm text-slate-800">
                  {turn.response.answer}
                </p>

                {turn.response.citations.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase text-slate-400">
                      Sources
                    </p>
                    {turn.response.citations.map((c) => (
                      <div
                        key={c.marker}
                        className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs"
                      >
                        <p className="font-medium">
                          [{c.marker}] {c.document_name}
                          {c.clause && ` · clause ${c.clause}`}
                          {c.page_number ? ` · p.${c.page_number}` : ""}
                        </p>
                        <p className="mt-1 text-slate-600">{c.snippet}</p>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
