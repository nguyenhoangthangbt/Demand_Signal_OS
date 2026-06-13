"""DemandSignalOS thin trust-gate FastAPI app.

``create_app()`` returns a FastAPI app that exposes ONLY the normalized trust
gate (DECISIONS_LOG §P #65): a health probe + the signed-receipt routes. No
auth (mirrors PlanningOS). LIGHT by design — does not import the heavy DSO
forecasting stack.

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
    "https://demandsignal.sim-os.ai",
    "https://demandsignal-api.sim-os.ai",
    "https://plan2cash.sim-os.ai",
    "https://plan2cash-api.sim-os.ai",
]


def create_app() -> Any:
    """Create and configure the thin trust-gate FastAPI application."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from demand_signal_os.api.receipt_routes import router as receipt_router

    app = FastAPI(
        title="DemandSignalOS — Trust Gate",
        description=(
            "Thin trust-gate surface for DemandSignalOS: signed forecast-trust "
            "receipts + self-auditable validation workbook (DECISIONS_LOG §P #65)."
        ),
        version="0.1.0",
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

    app.include_router(receipt_router, prefix="/api/v1")

    return app
