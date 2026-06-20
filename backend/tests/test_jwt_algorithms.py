"""JWT algorithm-selection tests for SupabaseAuthenticator.

Reproduces and locks down the production bug "The specified alg value is not
allowed": Supabase's asymmetric signing keys issue ES256 tokens, which the
verifier must validate via JWKS even when SUPABASE_JWT_ALGORITHMS only lists
HS256,RS256. Also asserts the HS256 shared-secret path is preserved and that
alg-confusion / alg=none are rejected.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Dict

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import SecretStr

from app.auth.supabase import SupabaseAuthenticator
from app.core.config import SupabaseSettings
from app.core.exceptions import AuthenticationError

_HS_SECRET = "unit-hs-secret"


def _claims(**over: Any) -> Dict[str, Any]:
    now = int(time.time())
    base: Dict[str, Any] = {
        "sub": "user-1",
        "email": "u@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
        "app_metadata": {"tenant_id": "acme"},
        "user_metadata": {},
    }
    base.update(over)
    return base


def _make_authenticator(jwks_url: str = "https://example.test/jwks") -> SupabaseAuthenticator:
    # jwt_algorithms intentionally OMITS ES256 to reproduce the production config
    # that triggered the bug. The fix must still accept an ES256 JWKS token.
    sup = SupabaseSettings(
        jwt_secret=SecretStr(_HS_SECRET),
        jwks_url=jwks_url,
        jwt_audience="authenticated",
        jwt_algorithms=["HS256", "RS256"],
    )
    settings = SimpleNamespace(supabase=sup, default_tenant_id="public")
    return SupabaseAuthenticator(settings=settings)  # type: ignore[arg-type]


# --- HS256 shared-secret path (local/dev behaviour) is preserved --------------

def test_hs256_shared_secret_still_verifies():
    auth = _make_authenticator()
    token = jwt.encode(_claims(), _HS_SECRET, algorithm="HS256")
    principal = auth.authenticate(token)
    assert principal.user_id == "user-1"
    assert principal.tenant_id == "acme"


def test_hs256_wrong_secret_rejected():
    auth = _make_authenticator()
    token = jwt.encode(_claims(), "the-wrong-secret", algorithm="HS256")
    with pytest.raises(AuthenticationError):
        auth.authenticate(token)


# --- ES256 via JWKS: the actual production fix --------------------------------

def test_es256_jwks_token_verifies_even_when_not_in_configured_algs(monkeypatch):
    auth = _make_authenticator()
    private_key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(_claims(), private_key, algorithm="ES256")

    # Stand in for the live JWKS fetch with the matching public key.
    monkeypatch.setattr(auth, "_get_signing_key", lambda _t: private_key.public_key())

    principal = auth.authenticate(token)
    assert principal.user_id == "user-1"
    assert principal.tenant_id == "acme"


def test_es256_signature_mismatch_rejected(monkeypatch):
    auth = _make_authenticator()
    signer = ec.generate_private_key(ec.SECP256R1())
    other = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(_claims(), signer, algorithm="ES256")

    # JWKS returns a DIFFERENT key -> signature must fail.
    monkeypatch.setattr(auth, "_get_signing_key", lambda _t: other.public_key())
    with pytest.raises(AuthenticationError):
        auth.authenticate(token)


def test_asymmetric_token_without_jwks_gives_clear_error():
    auth = _make_authenticator(jwks_url="")  # JWKS not configured
    private_key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(_claims(), private_key, algorithm="ES256")
    with pytest.raises(AuthenticationError) as exc:
        auth.authenticate(token)
    assert "JWKS" in str(exc.value)


# --- Security: alg confusion / alg=none ---------------------------------------

def test_alg_none_rejected():
    auth = _make_authenticator()
    token = jwt.encode(_claims(), key=None, algorithm="none")  # unsigned
    with pytest.raises(AuthenticationError):
        auth.authenticate(token)


def test_hs_token_not_accepted_on_jwks_key(monkeypatch):
    # An attacker submits an HS256 token; it must be verified with the shared
    # secret (shared_secret mode), never against a public key. Signing with a
    # bogus secret must therefore fail rather than slip through the JWKS path.
    auth = _make_authenticator()
    token = jwt.encode(_claims(), "attacker-secret", algorithm="HS256")
    monkeypatch.setattr(auth, "_get_signing_key", lambda _t: b"should-not-be-used")
    with pytest.raises(AuthenticationError):
        auth.authenticate(token)
