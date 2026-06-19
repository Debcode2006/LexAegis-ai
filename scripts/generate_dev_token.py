"""
Generate a local development Bearer token for LexAegis AI.

Mints an HS256 JWT signed with the project's Supabase JWT secret so you can call
the authenticated endpoints (document upload, retrieval, chat) locally without a
live Supabase project — and without getting 401s.

The secret is read from the backend settings (i.e. SUPABASE_JWT_SECRET in
`backend/.env` or the environment). The token's `tenant_id` defaults to "demo".

Usage:
    python scripts/generate_dev_token.py
    python scripts/generate_dev_token.py --tenant demo --email you@firm.com --hours 8

Then copy the printed token into Swagger (see the printed instructions).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make the backend package importable so we reuse the project's settings.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))

try:
    import jwt  # PyJWT
except ImportError:
    sys.exit(
        "PyJWT is not installed. Activate the backend venv and install deps:\n"
        "    pip install -r backend/requirements-phase1.txt"
    )

from app.core.config import get_settings  # noqa: E402


def build_token(secret: str, *, sub: str, email: str, tenant: str, audience: str, hours: int) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "aud": audience,
        "iat": now,
        "exp": now + hours * 3600,
        # LexAegis reads the tenant from app_metadata.tenant_id.
        "app_metadata": {"tenant_id": tenant},
        "user_metadata": {"full_name": "Dev User"},
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def main() -> None:
    # Avoid UnicodeEncodeError on legacy Windows consoles (cp1252).
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    settings = get_settings()
    sup = settings.supabase

    parser = argparse.ArgumentParser(description="Generate a LexAegis dev Bearer token.")
    parser.add_argument("--tenant", default="demo", help="tenant_id claim (default: demo)")
    parser.add_argument("--sub", default="dev-user", help="user id / subject (default: dev-user)")
    parser.add_argument("--email", default="dev@lexaegis.local", help="email claim")
    parser.add_argument("--hours", type=int, default=8, help="token lifetime in hours (default: 8)")
    args = parser.parse_args()

    secret = sup.jwt_secret.get_secret_value()
    if not secret or secret == "your-supabase-jwt-secret":
        sys.exit(
            "SUPABASE_JWT_SECRET is not set.\n"
            "Set it in backend/.env (any non-empty value works for local dev), e.g.:\n"
            "    SUPABASE_JWT_SECRET=local-dev-secret\n"
            "It must match the value the running backend uses to verify tokens."
        )

    token = build_token(
        secret,
        sub=args.sub,
        email=args.email,
        tenant=args.tenant,
        audience=sup.jwt_audience or "authenticated",
        hours=args.hours,
    )

    base = f"http://{settings.host if settings.host != '0.0.0.0' else 'localhost'}:{settings.port}"
    api = f"{base}{settings.api_v1_prefix}"

    print("=" * 74)
    print(f"  LexAegis dev Bearer token  (tenant_id={args.tenant}, valid {args.hours}h)")
    print("=" * 74)
    print()
    print(token)
    print()
    print("-" * 74)
    print("Use it in Swagger UI:")
    print(f"  1. Start the backend:   cd backend && uvicorn app.main:app --reload")
    print(f"  2. Open the docs:       {base}/docs")
    print("  3. Click the green 'Authorize' button (top-right).")
    print("  4. In the value box paste EITHER the raw token OR 'Bearer <token>':")
    print(f"         Bearer {token[:24]}...")
    print("     (HTTPBearer accepts the raw token; the 'Bearer ' prefix is optional.)")
    print("  5. Click Authorize -> Close. Every request now sends the token.")
    print()
    print("Now try, in this order (no more 401s):")
    print("  - POST /documents/upload   (attach a .pdf/.docx/.txt, document_type=contract)")
    print("  - GET  /documents          (see it listed)")
    print("  - POST /chat               ({\"query\": \"What does the contract say about liability?\"})")
    print("-" * 74)
    print("curl equivalents:")
    print(f'  export TOKEN="{token}"')
    print(f'  curl -X POST {api}/documents/upload \\')
    print('       -H "Authorization: Bearer $TOKEN" \\')
    print('       -F "file=@your-contract.txt" -F "document_type=contract"')
    print(f'  curl {api}/documents -H "Authorization: Bearer $TOKEN"')
    print(f'  curl -X POST {api}/chat -H "Authorization: Bearer $TOKEN" \\')
    print('       -H "Content-Type: application/json" \\')
    print('       -d \'{"query": "Summarize the confidentiality clause."}\'')
    print("=" * 74)


if __name__ == "__main__":
    main()
