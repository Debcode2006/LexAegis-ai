// Persistent, multi-session chat history backed by localStorage.
//
// Each conversation holds an ordered list of turns (query + the full
// ChatResponse) plus the retrieval scope that was active. Everything is stored
// client-side only — no backend changes and the chat API contract is unchanged.

import type { ChatResponse } from "./api";

const STORAGE_KEY = "lexaegis_conversations";
const SCHEMA_VERSION = 1;

export type StoredTurn = {
  id: string;
  query: string;
  response: ChatResponse;
  // Snapshot of the retrieval scope used for this turn (for display in history).
  scopeDocumentIds: string[];
  scopeDocumentNames: string[];
  createdAt: number;
};

export type Conversation = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  turns: StoredTurn[];
  // Current/last-used document scope for this conversation ([] = all documents).
  documentIds: string[];
};

type StoreShape = {
  version: number;
  conversations: Conversation[];
};

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function loadStore(): StoreShape {
  if (!isBrowser()) return { version: SCHEMA_VERSION, conversations: [] };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { version: SCHEMA_VERSION, conversations: [] };
    const parsed = JSON.parse(raw) as StoreShape;
    if (!parsed || !Array.isArray(parsed.conversations)) {
      return { version: SCHEMA_VERSION, conversations: [] };
    }
    return parsed;
  } catch {
    // Corrupted storage — start clean rather than crash the page.
    return { version: SCHEMA_VERSION, conversations: [] };
  }
}

function saveStore(store: StoreShape): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Quota exceeded or storage disabled — fail silently (in-memory state stays).
  }
}

export function deriveTitle(query: string): string {
  const trimmed = query.trim().replace(/\s+/g, " ");
  if (!trimmed) return "New chat";
  return trimmed.length > 48 ? `${trimmed.slice(0, 48)}…` : trimmed;
}

/** All conversations, most-recently-updated first. */
export function listConversations(): Conversation[] {
  return loadStore().conversations.sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getConversation(id: string): Conversation | null {
  return loadStore().conversations.find((c) => c.id === id) ?? null;
}

export function createConversation(documentIds: string[] = []): Conversation {
  const now = Date.now();
  const convo: Conversation = {
    id: newId(),
    title: "New chat",
    createdAt: now,
    updatedAt: now,
    turns: [],
    documentIds,
  };
  const store = loadStore();
  store.conversations.unshift(convo);
  saveStore(store);
  return convo;
}

export function appendTurn(
  conversationId: string,
  turn: Omit<StoredTurn, "id" | "createdAt">
): Conversation | null {
  const store = loadStore();
  const convo = store.conversations.find((c) => c.id === conversationId);
  if (!convo) return null;
  const stored: StoredTurn = { ...turn, id: newId(), createdAt: Date.now() };
  convo.turns.push(stored);
  convo.updatedAt = stored.createdAt;
  // First user message names the conversation (ChatGPT-style).
  if (convo.turns.length === 1 && (convo.title === "New chat" || !convo.title)) {
    convo.title = deriveTitle(turn.query);
  }
  saveStore(store);
  return convo;
}

export function renameConversation(id: string, title: string): void {
  const store = loadStore();
  const convo = store.conversations.find((c) => c.id === id);
  if (!convo) return;
  convo.title = title.trim() || convo.title;
  convo.updatedAt = Date.now();
  saveStore(store);
}

export function setConversationScope(id: string, documentIds: string[]): void {
  const store = loadStore();
  const convo = store.conversations.find((c) => c.id === id);
  if (!convo) return;
  convo.documentIds = documentIds;
  saveStore(store);
}

export function deleteConversation(id: string): void {
  const store = loadStore();
  store.conversations = store.conversations.filter((c) => c.id !== id);
  saveStore(store);
}
