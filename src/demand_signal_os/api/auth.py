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

import logging
import os
from typing import Annotated

from fastapi import Header, HTTPException, status

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

    if x_api_key is None or x_api_key not in allowed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-API-Key",
        )
    return x_api_key
