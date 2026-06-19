# Supabase Setup

LexAegis uses Supabase Auth for identity. The backend only **verifies** JWTs — it
never holds user passwords.

## 1. Create a project
1. Sign in at https://supabase.com and create a project.
2. Note the project URL: `https://<ref>.supabase.co`.

## 2. Collect credentials
From **Project Settings → API**:
- **Project URL** → `SUPABASE_URL`
- **anon public** key → `SUPABASE_ANON_KEY`
- **service_role** key → `SUPABASE_SERVICE_ROLE_KEY` (server-side only — never
  expose to the frontend)
- **JWT Secret** (Settings → API → JWT Settings) → `SUPABASE_JWT_SECRET`
  (used for HS256 verification)

For RS256 projects, set `SUPABASE_JWKS_URL` to
`https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` instead.

## 3. Backend `.env`

```
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_JWT_ALGORITHMS=HS256,RS256
```

## 4. Multi-tenancy claim

LexAegis reads the tenant from the JWT `app_metadata.tenant_id`. Set it per user
(e.g. via the Admin API or a signup trigger):

```sql
-- Example: set tenant on a user via SQL (service role)
update auth.users
set raw_app_meta_data = raw_app_meta_data || '{"tenant_id":"acme"}'
where email = 'user@acme.io';
```

If absent, the backend falls back to `DEFAULT_TENANT_ID` (`public`).

## 5. Frontend `.env.local`

```
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1
```

The login page calls `${SUPABASE_URL}/auth/v1/token?grant_type=password`.

## 6. Local testing without Supabase

You don't need a live project to develop. Mint an HS256 token signed with your
`SUPABASE_JWT_SECRET` and paste it into the login page's "dev token" field, or
use it directly:

```python
import jwt, time
token = jwt.encode(
    {"sub": "user-1", "email": "dev@local", "role": "authenticated",
     "aud": "authenticated", "exp": int(time.time()) + 3600,
     "app_metadata": {"tenant_id": "acme"}},
    "your-supabase-jwt-secret", algorithm="HS256",
)
print(token)
```

The test suite uses exactly this approach (see `backend/tests/conftest.py`).
