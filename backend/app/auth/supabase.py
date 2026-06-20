"""
Supabase JWT verification.

`SupabaseAuthenticator` validates the bearer token issued by Supabase Auth and
returns a `Principal`. Two signing schemes are supported and auto-selected:

- HS256: verified with the shared `SUPABASE_JWT_SECRET`.
- RS256: verified against the project JWKS (`SUPABASE_JWKS_URL`). The JWKS is
  fetched lazily and cached in-process.

The authenticator is deliberately dependency-light (PyJWT only) so it can run in
local development without network access when using the HS256 secret.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import jwt
from jwt import InvalidTokenError, PyJWKClient

from app.auth.models import Principal
from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger

logger = get_logger(__name__)

# JWT algorithm families. HS* are symmetric (verified with the shared
# SUPABASE_JWT_SECRET); the rest are asymmetric and verified against the project
# JWKS. Supabase's modern "JWT signing keys" issue ES256 (ECC P-256) tokens by
# default — RSA keys issue RS256 — so the JWKS path must accept the whole
# asymmetric family, not only RS256.
_HS_ALGS = frozenset({"HS256", "HS384", "HS512"})
_ASYMMETRIC_ALGS = frozenset(
    {
        "RS256", "RS384", "RS512",
        "ES256", "ES384", "ES512",
        "PS256", "PS384", "PS512",
        "EdDSA",
    }
)


class SupabaseAuthenticator:
    """Verify Supabase-issued JWTs and build the request `Principal`."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._jwks_client: Optional[PyJWKClient] = None
        self._jwks_client_created_at: float = 0.0

    # -- public API -----------------------------------------------------------

    def authenticate(self, token: str) -> Principal:
        """Verify a bearer token and return the authenticated principal."""

        token = self._strip_bearer(token)
        claims = self._decode(token)
        return self._build_principal(claims)

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _strip_bearer(token: str) -> str:
        if not token:
            raise AuthenticationError("Missing bearer token.")
        if token.lower().startswith("bearer "):
            token = token[7:]
        return token.strip()

    def _decode(self, token: str) -> Dict[str, Any]:
        sup = self._settings.supabase

        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise AuthenticationError("Malformed token header.") from exc

        algorithm = header.get("alg", "")
        configured = set(sup.jwt_algorithms)

        # Select the verification mode from the token's own alg, then scope the
        # PyJWT `algorithms` allowlist to exactly that mode's family. Passing both
        # families to every decode (the previous behaviour) is what produced
        # "The specified alg value is not allowed": Supabase issues ES256, which
        # was absent from the configured [HS256, RS256] list, so PyJWT rejected
        # the token BEFORE checking its signature. Per-mode scoping also closes an
        # algorithm-confusion gap (an HS-family alg must never be accepted on the
        # public-key path, and vice versa).
        if algorithm in _ASYMMETRIC_ALGS:
            if self._jwks() is None:
                raise AuthenticationError(
                    f"Asymmetric ({algorithm}) token received but SUPABASE_JWKS_URL "
                    "is not configured."
                )
            mode = "jwks"
            # The JWKS is the real trust anchor (only keys Supabase publishes can
            # validate). Allow the operator-pinned asymmetric algs PLUS this
            # token's own (already known-asymmetric) alg, so enabling the JWKS URL
            # works even when SUPABASE_JWT_ALGORITHMS still lists only HS256,RS256.
            allowed = sorted((configured & _ASYMMETRIC_ALGS) | {algorithm})
        else:
            mode = "shared_secret"
            # Strict: only the operator-configured HS algs. Never auto-widen here —
            # that blocks the alg="none" attack and HS/asymmetric confusion.
            allowed = sorted(configured & _HS_ALGS) or ["HS256"]

        logger.debug(
            "JWT verify routing: token_alg=%s mode=%s allowed_algorithms=%s",
            algorithm or "<none>",
            mode,
            allowed,
        )

        decode_kwargs: Dict[str, Any] = {
            "algorithms": allowed,
            "audience": sup.jwt_audience or None,
            "options": {"verify_aud": bool(sup.jwt_audience)},
        }
        if sup.jwt_issuer:
            decode_kwargs["issuer"] = sup.jwt_issuer

        try:
            if mode == "jwks":
                signing_key = self._get_signing_key(token)
                return jwt.decode(token, signing_key, **decode_kwargs)

            secret = sup.jwt_secret.get_secret_value()
            if not secret:
                raise AuthenticationError("HS256 token received but no JWT secret configured.")
            return jwt.decode(token, secret, **decode_kwargs)
        except InvalidTokenError as exc:
            logger.warning(
                "JWT verification failed: %s (token_alg=%s mode=%s allowed_algorithms=%s)",
                exc,
                algorithm or "<none>",
                mode,
                allowed,
            )
            raise AuthenticationError("Invalid or expired token.") from exc

    def _get_signing_key(self, token: str) -> Any:
        client = self._jwks()
        if client is None:
            raise AuthenticationError("RS256 token received but no JWKS URL configured.")
        return client.get_signing_key_from_jwt(token).key

    def _jwks(self) -> Optional[PyJWKClient]:
        jwks_url = self._settings.supabase.jwks_url
        if not jwks_url:
            return None
        # Recreate the client hourly so rotated keys are eventually picked up.
        if self._jwks_client is None or (time.time() - self._jwks_client_created_at) > 3600:
            self._jwks_client = PyJWKClient(jwks_url)
            self._jwks_client_created_at = time.time()
        return self._jwks_client

    def _build_principal(self, claims: Dict[str, Any]) -> Principal:
        user_id = claims.get("sub")
        if not user_id:
            raise AuthenticationError("Token missing subject claim.")

        app_metadata = claims.get("app_metadata", {}) or {}
        user_metadata = claims.get("user_metadata", {}) or {}

        tenant_id = (
            app_metadata.get("tenant_id")
            or claims.get("tenant_id")
            or self._settings.default_tenant_id
        )

        return Principal(
            user_id=str(user_id),
            email=claims.get("email"),
            role=claims.get("role", "authenticated"),
            tenant_id=str(tenant_id),
            app_metadata=app_metadata,
            user_metadata=user_metadata,
            scopes=list(claims.get("scopes", []) or []),
        )


_authenticator: Optional[SupabaseAuthenticator] = None


def get_authenticator() -> SupabaseAuthenticator:
    """Return a process-wide authenticator instance."""

    global _authenticator
    if _authenticator is None:
        _authenticator = SupabaseAuthenticator()
    return _authenticator
