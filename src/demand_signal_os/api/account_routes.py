"""Same-origin identity proxy for the DSO web UI's identity badge.

The browser can't call MAO ``GET /account/profile`` directly (no CORS
allow-origin for the engine subdomains), so DSO exposes a thin same-origin
shim that forwards the caller's OWN ``mao_live_`` key to MAO and projects the
three fields the identity badge needs (name / role / tier).

This mirrors the SimOS ``/account/whoami`` proxy
(``simulation_os/api/entitlement_routes.py``) and reuses the SAME MAO base-URL
resolution + httpx pattern the DSO engine already uses for tier-gating
(``MaoTierResolver`` in ``app.py``): forward ``Authorization: Bearer <key>`` to
``{mao_base}/account/profile``.

Always HTTP 200 with ``{name, role, tier}``; every field is null when the key
isn't a ``mao_live_`` key, MAO returns non-200, or MAO is unreachable
(fail-soft — the badge simply renders nothing rather than erroring).
"""

from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Header, Request

router = APIRouter(tags=["account"])


def _mao_base() -> str:
    """Resolve the MAO base URL the SAME way ``app.py`` builds the resolver."""
    base = os.environ.get("DSO_MAO_API_URL") or os.environ.get(
        "P2C_MAO_API_URL", "http://master-agents-api:8000"
    )
    return base.rstrip("/")


@router.get("/account/whoami")
async def account_whoami(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Resolve the caller's identity card (name / role / tier) for the UI badge."""
    key = (x_api_key or "").strip()
    if not key and authorization and authorization.startswith("Bearer "):
        key = authorization.removeprefix("Bearer ").strip()
    extra_headers: dict[str, str] = {}
    if x_api_key is None and authorization is None:
        # P0-11 R1: the browser session cookie; its session id goes to MAO so
        # a revoked session shows no identity.
        from demand_signal_os.api.auth import session_credential

        cred = session_credential(request)
        if cred is not None:
            from platform_auth.session import SESSION_HEADER

            key, extra_headers = cred.token, {SESSION_HEADER: cred.session_id}
    if not key or not key.startswith("mao_live_"):
        return {"name": None, "role": None, "tier": None}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{_mao_base()}/account/profile",
                headers={"Authorization": f"Bearer {key}", **extra_headers},
            )
    except (httpx.HTTPError, OSError):
        return {"name": None, "role": None, "tier": None}

    if resp.status_code == 200:
        try:
            j = resp.json() or {}
        except ValueError:
            j = {}
        name = j.get("display_name") or j.get("name")
        role = j.get("role")
        tier = j.get("plan")
        return {"name": name or None, "role": role or None, "tier": tier or None}
    return {"name": None, "role": None, "tier": None}
