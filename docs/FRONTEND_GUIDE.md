# Frontend Guide

The frontend is a minimal, professional Next.js (App Router) + TypeScript +
Tailwind app in `frontend/`. It is intentionally lean — backend quality is the
priority — but fully functional against the live API.

## Stack
- Next.js 14 (App Router), React 18, TypeScript.
- Tailwind CSS with shadcn-style local UI components (no CLI dependency).

## Pages

| Route | File | Purpose |
|---|---|---|
| `/login` | `app/login/page.tsx` | Supabase password login **or** paste a dev JWT |
| `/dashboard` | `app/dashboard/page.tsx` | Stats (docs, cache hit-rate, latency) + nav tiles |
| `/upload` | `app/upload/page.tsx` | Upload + ingest PDF/DOCX/TXT |
| `/chat` | `app/chat/page.tsx` | Chat UI with citations + confidence + groundedness |
| `/documents` | `app/documents/page.tsx` | Document Explorer table |
| `/evaluation` | `app/evaluation/page.tsx` | RAGAS/DeepEval/offline metrics dashboard |

## Key modules

- `lib/api.ts` — typed API client; attaches `Authorization: Bearer <token>` and
  unwraps the backend error envelope.
- `lib/auth.tsx` — `AuthProvider` + `useAuth()`; stores the JWT in `localStorage`.
  Supabase email/password via the Supabase Auth REST endpoint, or a dev-token
  paste flow for local work.
- `lib/utils.ts` — `cn()` classnames + `API_BASE`.
- `components/ui/*` — Button, Card, Input/Textarea.
- `components/nav.tsx` — top navigation (hidden on `/login`).
- `components/confidence-badge.tsx` — colored confidence pill.

## Features shown
- **Chat UI** with streaming-free request/response turns.
- **Citation display** — each `[S1]` source rendered with document, clause, page,
  and snippet.
- **Confidence score** — colored badge + intent + groundedness chips.
- **Document upload** with type selection and ingestion summary.
- **Source viewing** in the Document Explorer.

## Run

```bash
cd frontend
cp .env.local.example .env.local
#   NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1
#   NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY (optional)
npm install
npm run dev          # http://localhost:3000
```

## Auth flows
1. **Supabase login** — enter email/password; the app calls
   `${SUPABASE_URL}/auth/v1/token?grant_type=password` and stores the access
   token.
2. **Dev token** — paste any valid Supabase HS256 JWT (e.g. one minted for local
   testing) to skip the Supabase round-trip.

The stored token is sent on every API call; `401`s should redirect the user to
`/login` (sign-out button clears the token).

## Notes
- CORS: the backend allows `CORS_ORIGINS=http://localhost:3000` by default.
- This scaffold avoids heavy shadcn/ui CLI setup by shipping equivalent local
  components, keeping `npm install` light.
