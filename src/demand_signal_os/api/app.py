"""DemandSignalOS FastAPI app.

``create_app()`` returns a FastAPI app exposing: a health probe, the public
trust-gate signed-receipt routes (DECISIONS_LOG §P #65), and the auth-gated
forecast-leaderboard routes (the v0.1.5 API extraction). The leaderboard
handlers import the heavy DSO forecasting stack lazily so module import stays
light; the trust gate remains public, the leaderboard is tier-key gated.

Run locally::

    uvicorn demand_signal_os.api.app:create_app --factory --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from typing import Any

# Localhost dev ports + the sim-os.ai canopy/subdomains (mirror PlanningOS
# intent; explicit origins rather than "*" so a future authed surface can flip
# allow_credentials on without an origins rewrite).
_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5176",
    "http://localhost:8092",
    "https://sim-os.ai",
    # Canonical deployed spelling is HYPHENATED (matches the live web SPA at
    # demand-signal.sim-os.ai + doctor PUBLIC_URL). Non-hyphen kept as an alias
    # so an older reference doesn't break.
    "https://demand-signal.sim-os.ai",
    "https://demand-signal-api.sim-os.ai",
    "https://demandsignal.sim-os.ai",
    "https://demandsignal-api.sim-os.ai",
    "https://plan2cash.sim-os.ai",
    "https://plan2cash-api.sim-os.ai",
]


def create_app() -> Any:
    """Create and configure the thin trust-gate FastAPI application."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from demand_signal_os.api.account_routes import router as account_router
    from demand_signal_os.api.forecast_routes import router as forecast_router
    from demand_signal_os.api.leaderboard_routes import router as leaderboard_router
    from demand_signal_os.api.receipt_routes import router as receipt_router

    app = FastAPI(
        title="DemandSignalOS - API",
        description=(
            "DemandSignalOS surface: public signed forecast-trust receipts "
            "(DECISIONS_LOG §P #65) + auth-gated forecaster leaderboard "
            "(probabilistic compare-and-pick for the e2e bundle)."
        ),
        version="0.1.5",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health", tags=["health"])
    async def health() -> dict:
        """Health check endpoint."""
        return {"status": "ok", "engine": "demandsignal"}

    # Cross-engine SSO (Phase 2b): resolver for a mao_live_ bearer -> plan, used
    # by require_dso_access on the leaderboard router. The customer presents
    # their own token (no admin credential). Guarded so the app still starts if
    # platform_auth isn't installed (the dso_live_ X-API-Key path still works).
    try:
        import os

        from platform_auth import MaoTierResolver

        mao_url = os.environ.get("DSO_MAO_API_URL") or os.environ.get(
            "P2C_MAO_API_URL", "http://master-agents-api:8000"
        )
        app.state.mao_tier_resolver = MaoTierResolver(mao_url)
    except ImportError:
        app.state.mao_tier_resolver = None

    app.include_router(receipt_router, prefix="/api/v1")
    app.include_router(leaderboard_router, prefix="/api/v1")
    app.include_router(forecast_router, prefix="/api/v1")
    app.include_router(account_router, prefix="/api/v1")

    return app
