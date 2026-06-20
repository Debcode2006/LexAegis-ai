"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type ChatResponse, type DocumentSummary } from "@/lib/api";
import {
  appendTurn,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
  setConversationScope,
  type Conversation,
} from "@/lib/chatHistory";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { cn } from "@/lib/utils";

export default function ChatPage() {
  const { token } = useAuth();

  // Persistent conversations.
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  // Composer + request state.
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Retrieval scope.
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);

  // Sidebar rename state.
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameText, setRenameText] = useState("");

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const pickerRef = useRef<HTMLDivElement | null>(null);

  // -- load persisted conversations on mount --------------------------------
  useEffect(() => {
    const all = listConversations();
    setConversations(all);
    if (all.length > 0) {
      setActiveId(all[0].id);
      setSelectedDocIds(all[0].documentIds ?? []);
    }
  }, []);

  // -- load the tenant's documents for the picker ---------------------------
  useEffect(() => {
    if (!token) return;
    api
      .listDocuments(token)
      .then((d) => setDocs(d.documents))
      .catch(() => setDocs([]));
  }, [token]);

  const activeConversation = useMemo(
    () => conversations.find((c) => c.id === activeId) ?? null,
    [conversations, activeId]
  );

  // Keep the document scope valid as documents change / conversations switch.
  const docNameById = useMemo(() => {
    const m = new Map<string, string>();
    docs.forEach((d) => m.set(d.document_id, d.document_name));
    return m;
  }, [docs]);

  // Auto-scroll to the latest turn.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConversation?.turns.length, loading]);

  // Close the picker on outside click.
  useEffect(() => {
    if (!pickerOpen) return;
    const onClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setPickerOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [pickerOpen]);

  const refresh = () => setConversations(listConversations());

  const selectConversation = (id: string) => {
    setActiveId(id);
    const convo = getConversation(id);
    setSelectedDocIds(convo?.documentIds ?? []);
    setError(null);
  };

  const startNewChat = () => {
    setActiveId(null);
    setSelectedDocIds([]);
    setQuery("");
    setError(null);
  };

  const toggleDoc = (id: string) => {
    setSelectedDocIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      if (activeId) setConversationScope(activeId, next);
      return next;
    });
  };

  const selectAllDocs = () => {
    setSelectedDocIds([]);
    if (activeId) setConversationScope(activeId, []);
  };

  const ask = async () => {
    if (!query.trim() || !token || loading) return;
    setError(null);
    setLoading(true);
    const q = query;
    setQuery("");

    // Ensure there is an active conversation to append to.
    let convoId = activeId;
    if (!convoId) {
      const convo = createConversation(selectedDocIds);
      convoId = convo.id;
      setActiveId(convoId);
      refresh();
    }

    try {
      const response = await api.chat(token, q, { documentIds: selectedDocIds });
      appendTurn(convoId, {
        query: q,
        response,
        scopeDocumentIds: [...selectedDocIds],
        scopeDocumentNames: selectedDocIds.map((id) => docNameById.get(id) ?? id),
      });
      refresh();
    } catch (err) {
      setError((err as Error).message);
      setQuery(q); // restore the unsent question
    } finally {
      setLoading(false);
    }
  };

  const commitRename = (id: string) => {
    renameConversation(id, renameText);
    setRenamingId(null);
    refresh();
  };

  const removeConversation = (id: string) => {
    if (!confirm("Delete this conversation? This cannot be undone.")) return;
    deleteConversation(id);
    if (activeId === id) startNewChat();
    refresh();
  };

  const scopeLabel =
    selectedDocIds.length === 0
      ? "Searching all documents"
      : `Searching ${selectedDocIds.length} selected document${
          selectedDocIds.length === 1 ? "" : "s"
        }`;

  const turns = activeConversation?.turns ?? [];

  return (
    <div className="flex h-[calc(100vh-9rem)] gap-4">
      {/* -- Sidebar: conversation list ------------------------------------ */}
      <aside className="flex w-64 shrink-0 flex-col rounded-xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 p-3">
          <Button className="w-full" onClick={startNewChat}>
            + New chat
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {conversations.length === 0 ? (
            <p className="px-2 py-4 text-xs text-slate-400">
              No conversations yet. Ask a question to start one.
            </p>
          ) : (
            conversations.map((c) => (
              <div
                key={c.id}
                className={cn(
                  "group mb-1 flex items-center gap-1 rounded-md px-2 py-2 text-sm",
                  c.id === activeId ? "bg-brand/10 text-brand" : "hover:bg-slate-100"
                )}
              >
                {renamingId === c.id ? (
                  <Input
                    autoFocus
                    value={renameText}
                    onChange={(e) => setRenameText(e.target.value)}
                    onBlur={() => commitRename(c.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitRename(c.id);
                      if (e.key === "Escape") setRenamingId(null);
                    }}
                    className="h-7 py-1 text-sm"
                  />
                ) : (
                  <>
                    <button
                      className="flex-1 truncate text-left"
                      title={c.title}
                      onClick={() => selectConversation(c.id)}
                    >
                      {c.title}
                    </button>
                    <button
                      className="hidden text-slate-400 hover:text-slate-700 group-hover:block"
                      title="Rename"
                      onClick={() => {
                        setRenamingId(c.id);
                        setRenameText(c.title);
                      }}
                    >
                      ✎
                    </button>
                    <button
                      className="hidden text-slate-400 hover:text-red-600 group-hover:block"
                      title="Delete"
                      onClick={() => removeConversation(c.id)}
                    >
                      🗑
                    </button>
                  </>
                )}
              </div>
            ))
          )}
        </div>
      </aside>

      {/* -- Main: scope + thread + composer ------------------------------- */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">Legal Chat</h1>

          {/* Document scope picker */}
          <div className="relative" ref={pickerRef}>
            <Button
              variant="outline"
              onClick={() => setPickerOpen((v) => !v)}
              className="gap-2"
            >
              📁 {selectedDocIds.length === 0 ? "All documents" : `${selectedDocIds.length} selected`}
              <span className="text-slate-400">▾</span>
            </Button>
            {pickerOpen && (
              <div className="absolute right-0 z-10 mt-1 w-72 rounded-md border border-slate-200 bg-white p-2 shadow-lg">
                <button
                  className={cn(
                    "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100",
                    selectedDocIds.length === 0 && "font-medium text-brand"
                  )}
                  onClick={selectAllDocs}
                >
                  <span className="w-4">{selectedDocIds.length === 0 ? "✓" : ""}</span>
                  All documents
                </button>
                <div className="my-1 border-t border-slate-100" />
                <div className="max-h-60 overflow-y-auto">
                  {docs.length === 0 ? (
                    <p className="px-2 py-2 text-xs text-slate-400">
                      No documents uploaded yet.
                    </p>
                  ) : (
                    docs.map((d) => {
                      const checked = selectedDocIds.includes(d.document_id);
                      return (
                        <button
                          key={d.document_id}
                          className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100"
                          onClick={() => toggleDoc(d.document_id)}
                        >
                          <span className="w-4">{checked ? "✓" : ""}</span>
                          <span className="truncate" title={d.document_name}>
                            {d.document_name}
                          </span>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Scope indicator */}
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="rounded-full bg-slate-100 px-2.5 py-1">{scopeLabel}</span>
          {selectedDocIds.length > 0 &&
            selectedDocIds.map((id) => (
              <span
                key={id}
                className="rounded-full border border-slate-200 px-2 py-1 text-slate-600"
              >
                {docNameById.get(id) ?? id}
              </span>
            ))}
        </div>

        {/* Message thread */}
        <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50/50 p-4">
          {turns.length === 0 ? (
            <div className="flex h-full items-center justify-center text-center text-slate-400">
              <p>Ask a question about your documents to begin.</p>
            </div>
          ) : (
            turns.map((turn) => (
              <div key={turn.id} className="space-y-2">
                <div className="flex justify-end">
                  <p className="max-w-[80%] rounded-2xl bg-brand px-4 py-2 text-sm text-white">
                    {turn.query}
                  </p>
                </div>
                <Card>
                  <CardContent className="space-y-3 pt-5">
                    <ResponseView response={turn.response} />
                    {turn.scopeDocumentIds.length > 0 && (
                      <p className="text-[11px] text-slate-400">
                        Scoped to: {turn.scopeDocumentNames.join(", ")}
                      </p>
                    )}
                  </CardContent>
                </Card>
              </div>
            ))
          )}
          {loading && <ThinkingIndicator />}
          <div ref={bottomRef} />
        </div>

        {/* Composer */}
        <div className="mt-3 space-y-2">
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
            <Button onClick={ask} disabled={loading || !query.trim() || !token}>
              {loading ? "Thinking…" : "Ask"}
            </Button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
      </section>
    </div>
  );
}

// Stages mirror the backend agent pipeline order so the wait feels alive while
// the single blocking /chat request runs (no server streaming yet).
const THINKING_STAGES = [
  "Checking input safety",
  "Understanding your question",
  "Retrieving relevant clauses",
  "Re-ranking sources",
  "Reasoning over the documents",
];

function ThinkingIndicator() {
  const [stage, setStage] = useState(0);
  const [seconds, setSeconds] = useState(0);

  // Elapsed-time counter.
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  // Walk the early stages on a timer, then dwell on the last (reasoning) stage,
  // which is where most of the latency actually is.
  useEffect(() => {
    if (stage >= THINKING_STAGES.length - 1) return;
    const id = setTimeout(() => setStage((s) => s + 1), stage === 0 ? 800 : 1600);
    return () => clearTimeout(id);
  }, [stage]);

  return (
    <div className="flex items-center gap-3 text-sm text-slate-500" aria-live="polite">
      <span className="flex gap-1">
        <span className="h-2 w-2 animate-bounce rounded-full bg-brand [animation-delay:-0.3s]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-brand [animation-delay:-0.15s]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-brand" />
      </span>
      <span>
        {THINKING_STAGES[stage]}
        <span className="animate-pulse">…</span>
        <span className="ml-2 text-xs text-slate-400">{seconds}s</span>
      </span>
    </div>
  );
}

function ResponseView({ response }: { response: ChatResponse }) {
  if (response.blocked) {
    return (
      <p className="rounded-md bg-red-50 p-3 text-sm text-red-800">
        🚫 Blocked: {response.block_reason}
      </p>
    );
  }
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <ConfidenceBadge value={response.confidence} />
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs">
          intent: {response.intent}
        </span>
        {response.groundedness && (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs">
            groundedness: {Math.round(response.groundedness.groundedness * 100)}%
          </span>
        )}
      </div>

      <p className="whitespace-pre-wrap text-sm text-slate-800">{response.answer}</p>

      {response.citations.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase text-slate-400">Sources</p>
          {response.citations.map((c) => (
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
  );
}
