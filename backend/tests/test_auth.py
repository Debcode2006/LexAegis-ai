"""Authentication and tenant-isolation tests."""

from __future__ import annotations


def test_whoami_requires_token(client):
    resp = client.get("/api/v1/auth/whoami")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "authentication_failed"


def test_whoami_rejects_invalid_token(client):
    resp = client.get(
        "/api/v1/auth/whoami",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_whoami_accepts_valid_token(client, make_token):
    token = make_token(sub="user-abc", tenant_id="acme", email="a@acme.io")
    resp = client.get(
        "/api/v1/auth/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "user-abc"
    assert body["tenant_id"] == "acme"
    assert body["email"] == "a@acme.io"


def test_expired_token_rejected(client, make_token):
    token = make_token(expires_in=-10)
    resp = client.get(
        "/api/v1/auth/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


def test_tenant_isolation_mismatch_rejected(client, make_token):
    # Principal belongs to tenant "acme" but requests tenant "globex".
    token = make_token(tenant_id="acme")
    resp = client.get(
        "/api/v1/auth/whoami",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": "globex",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "tenant_error"


def test_tenant_header_match_allowed(client, make_token):
    token = make_token(tenant_id="acme")
    resp = client.get(
        "/api/v1/auth/whoami",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": "acme",
        },
    )
    assert resp.status_code == 200
