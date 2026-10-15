"""P0-11 R1: the DSO value gate accepts the sealed browser session cookie.

MAO issues ``__Secure-mao_session`` (HttpOnly; the customer's ``mao_live_`` key
sealed with the shared ``MAO_SESSION_SEAL_KEY``). With that key configured,
``require_dso_access`` accepts the cookie as it accepts a ``mao_live_`` Bearer:
Premium and up, the session id forwarded to MAO (revocation), CSRF-checked on
unsafe methods. Header credentials and the seal-key-unset mode are unchanged.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from platform_auth import SealKeyring
from platform_auth import session as session_mod

from demand_signal_os.api.app import create_app

SEAL = "k1:" + ("ab" * 32)
OTHER_SEAL = "k9:" + ("cd" * 32)
PREMIUM = "mao_live_cookie_premium_0123456789"
FREE = "mao_live_cookie_free_0123456789"
COOKIE = "__Secure-mao_session"
ORIGIN = "https://demand-signal.sim-os.ai"
BROWSER = {"Origin": ORIGIN, "X-Requested-With": "mao"}
GATED_GET = "/api/v1/forecast/leaderboard/lb_none"  # 404 once past the gate
GATED_POST = "/api/v1/inventory/policy"  # 422 on an empty body once past the gate


def _sealed(
    *, key: str = PREMIUM, sid: str = "sid-abc", ring: str = SEAL, exp: int | None = None
) -> str:
    now = int(time.time())
    return SealKeyring.parse(ring).seal(
        sid=sid, key=key, iat=now, exp=exp if exp is not None else now + 3600
    )


def _cookie(value: str) -> dict[str, str]:
    return {"Cookie": f"{COOKIE}={value}"}


class _Resolver:
    def __init__(self, revoked: frozenset[str] = frozenset()) -> None:
        self.revoked = revoked
        self.calls: list[tuple[str, str | None]] = []

    async def resolve_plan(self, token: str, *, session_id: str | None = None) -> str:
        self.calls.append((token, session_id))
        if session_id is not None and session_id in self.revoked:
            raise HTTPException(status_code=401, detail="Invalid or revoked tier-key.")
        return "free" if token == FREE else "premium"


@pytest.fixture
def seal_on(monkeypatch):
    monkeypatch.setenv("MAO_SESSION_SEAL_KEY", SEAL)
    monkeypatch.delenv("MAO_SESSION_ORIGINS", raising=False)
    monkeypatch.setenv("DSO_API_KEYS", "dso_live_secret123")
    session_mod._keyring_for.cache_clear()
    yield
    session_mod._keyring_for.cache_clear()


@pytest.fixture
def seal_off(monkeypatch):
    monkeypatch.delenv("MAO_SESSION_SEAL_KEY", raising=False)
    monkeypatch.setenv("DSO_API_KEYS", "dso_live_secret123")
    session_mod._keyring_for.cache_clear()
    yield


def _client(resolver: _Resolver) -> TestClient:
    app = create_app()
    app.state.mao_tier_resolver = resolver
    return TestClient(app, base_url="https://testserver")


def test_valid_cookie_passes_the_premium_gate(seal_on) -> None:
    r = _Resolver()
    resp = _client(r).get(GATED_GET, headers=_cookie(_sealed()))
    assert resp.status_code == 404, resp.text  # past the gate, run unknown
    assert r.calls == [(PREMIUM, "sid-abc")]


def test_cookie_post_with_origin_and_csrf_header_passes(seal_on) -> None:
    resp = _client(_Resolver()).post(GATED_POST, json={}, headers={**_cookie(_sealed()), **BROWSER})
    assert resp.status_code == 422  # past the gate, body invalid


def test_cookie_below_premium_is_403(seal_on) -> None:
    resp = _client(_Resolver()).get(GATED_GET, headers=_cookie(_sealed(key=FREE)))
    assert resp.status_code == 403
    assert resp.json() == {"detail": "DSO requires premium+; your plan is 'free'."}


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(lambda: _sealed(exp=int(time.time()) - 1), id="expired"),
        pytest.param(lambda: _sealed()[:-3] + "AAA", id="tampered"),
        pytest.param(lambda: _sealed(ring=OTHER_SEAL), id="unknown-key"),
    ],
)
def test_bad_cookie_is_401(seal_on, value) -> None:
    r = _Resolver()
    resp = _client(r).get(GATED_GET, headers=_cookie(value()))
    assert resp.status_code == 401
    assert r.calls == []


def test_revoked_session_is_401(seal_on) -> None:
    resp = _client(_Resolver(revoked=frozenset({"sid-gone"}))).get(
        GATED_GET, headers=_cookie(_sealed(sid="sid-gone"))
    )
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": ORIGIN},
        {"X-Requested-With": "mao"},
        {"Origin": "https://evil.example", "X-Requested-With": "mao"},
    ],
)
def test_cookie_post_without_origin_and_csrf_header_is_403(seal_on, headers) -> None:
    resp = _client(_Resolver()).post(GATED_POST, json={}, headers={**_cookie(_sealed()), **headers})
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Request origin not allowed"}


def test_header_credentials_are_unchanged_with_the_flag_on(seal_on) -> None:
    r = _Resolver()
    client = _client(r)
    # dso_live_ X-API-Key, with a foreign Origin and a FREE cookie: header wins.
    resp = client.post(
        GATED_POST,
        json={},
        headers={"X-API-Key": "dso_live_secret123", **_cookie(_sealed(key=FREE)),
                 "Origin": "https://evil.example"},
    )
    assert resp.status_code == 422
    # mao_live_ Bearer: resolved without a session id, no Origin needed.
    resp = client.post(GATED_POST, json={}, headers={"Authorization": f"Bearer {PREMIUM}"})
    assert resp.status_code == 422
    assert r.calls == [(PREMIUM, None)]


def test_flag_off_cookie_is_ignored(seal_off) -> None:
    r = _Resolver()
    resp = _client(r).get(GATED_GET, headers=_cookie(_sealed()))
    assert resp.status_code == 401
    assert resp.json() == {"detail": "missing or invalid X-API-Key"}
    assert r.calls == []


def test_flag_off_unsafe_cookie_request_is_the_old_401(seal_off) -> None:
    resp = _client(_Resolver()).post(
        GATED_POST, json={}, headers={**_cookie(_sealed()), "Origin": "https://evil.example"}
    )
    assert resp.status_code == 401


def test_account_whoami_reads_the_cookie_and_forwards_the_session(seal_on, monkeypatch) -> None:
    import httpx

    from demand_signal_os.api import account_routes as mod

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"display_name": "Ann", "role": "r", "plan": "premium"})

    real_client = httpx.AsyncClient

    def _factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(mod.httpx, "AsyncClient", _factory)
    resp = _client(_Resolver()).get("/api/v1/account/whoami", headers=_cookie(_sealed()))
    assert resp.json() == {"name": "Ann", "role": "r", "tier": "premium"}
    assert seen[0].headers["authorization"] == f"Bearer {PREMIUM}"
    assert seen[0].headers["x-mao-session"] == "sid-abc"


def test_account_whoami_flag_off_ignores_the_cookie(seal_off) -> None:
    resp = _client(_Resolver()).get("/api/v1/account/whoami", headers=_cookie(_sealed()))
    assert resp.json() == {"name": None, "role": None, "tier": None}
