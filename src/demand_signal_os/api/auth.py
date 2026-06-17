"""Tier-key auth for the authed DSO surfaces (forecast leaderboard).

Per the locked customer-surface architecture, engine APIs are auth-gated by
tier keys while the trust-gate stays public. This is a deliberately small
header-key gate (``X-API-Key``) sourced from the ``DSO_API_KEYS`` env var
(comma-separated). It is NOT a full multi-tenant system — just enough to gate
value-delivery without fragmenting the buyer journey.

Behaviour:
- ``DSO_API_KEYS`` unset/empty  -> open (dev mode); a one-time warning is logged.
- ``DSO_API_KEYS`` set          -> a matching ``X-API-Key`` header is required;
  otherwise 401.
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

try:  # cross-engine SSO tier vocabulary (optional at import time)
    from ops_schemas.tier import Tier, meets_min

    _TIER_OK = True
except ImportError:  # pragma: no cover
    _TIER_OK = False

logger = logging.getLogger("demand_signal_os.api.auth")

_DEV_MODE_WARNED = False


def _allowed_keys() -> set[str]:
    raw = os.environ.get("DSO_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


async def require_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
) -> str:
    """FastAPI dependency: enforce a tier key when configured."""
    global _DEV_MODE_WARNED
    allowed = _allowed_keys()

    if not allowed:
        if not _DEV_MODE_WARNED:
            logger.warning(
                "DSO_API_KEYS is unset — leaderboard API running OPEN (dev mode). "
                "Set DSO_API_KEYS to gate the authed surface."
            )
            _DEV_MODE_WARNED = True
        return "dev"

    if x_api_key is None or not any(
        hmac.compare_digest(x_api_key, k) for k in allowed
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-API-Key",
        )
    return x_api_key


async def require_dso_access(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Dual-accept gate for DSO value endpoints (the leaderboard).

    Cross-engine SSO (Phase 2b): accept EITHER a customer's ``mao_live_`` bearer
    resolving to >= PREMIUM (via the shared platform_auth resolver on
    ``app.state.mao_tier_resolver``), OR the existing ``dso_live_`` ``X-API-Key``
    (transition). Fail-soft-then-closed on the bearer path: the resolver raises
    401 on a revoked key, 503 if MAO is unreachable with a cold cache. Keeps
    dev-open when ``DSO_API_KEYS`` is unset AND no bearer is presented.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token.startswith("mao_live_"):
            resolver = getattr(request.app.state, "mao_tier_resolver", None)
            if resolver is not None and _TIER_OK:
                plan = await resolver.resolve_plan(token)
                if not meets_min(plan, Tier.PREMIUM):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"DSO requires premium+; your plan is '{plan}'.",
                    )
                return f"mao:{plan}"
            # resolver/tier unavailable -> fall through to the dso_live_ path
    return await require_api_key(x_api_key)
