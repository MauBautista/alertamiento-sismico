"""App FastAPI de la API TAKAB: health + auth (/me, ack) y /dev/token en dev."""

from __future__ import annotations

from fastapi import FastAPI

from takab_api.health import router as health_router
from takab_api.routers.incidents_ack import router as incidents_ack_router
from takab_api.routers.me import router as me_router
from takab_api.settings import Settings


def create_app() -> FastAPI:
    """Construye la app. Monta ``/dev/token`` SOLO con JWKS inline (nunca en prod)."""
    app = FastAPI(title="TAKAB API", version="0.1.0")
    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(incidents_ack_router)

    # Guard de entorno: auth_jwks_json vacío = producción (JWKS remoto) → sin /dev/token.
    if Settings().auth_jwks_json:
        from takab_api.routers.dev_token import router as dev_token_router

        app.include_router(dev_token_router)

    return app


app = create_app()
