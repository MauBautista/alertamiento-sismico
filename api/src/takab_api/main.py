"""App FastAPI de la API TAKAB: health + auth (/me, ack), catálogo/incidentes/
telemetría/exports REST y el canal live WebSocket ``/ws`` (T-1.22)."""

from __future__ import annotations

from fastapi import FastAPI

from takab_api.health import router as health_router
from takab_api.routers.dictamens import router as dictamens_router
from takab_api.routers.events import router as events_router
from takab_api.routers.exports import router as exports_router
from takab_api.routers.fleet import router as fleet_router
from takab_api.routers.incidents import router as incidents_router
from takab_api.routers.incidents_ack import router as incidents_ack_router
from takab_api.routers.me import router as me_router
from takab_api.routers.rule_sets import router as rule_sets_router
from takab_api.routers.sensors import router as sensors_router
from takab_api.routers.sites import router as sites_router
from takab_api.routers.telemetry import router as telemetry_router
from takab_api.routers.tenants import router as tenants_router
from takab_api.routers.ws import router as ws_router
from takab_api.settings import Settings
from takab_api.ws import lifespan


def create_app() -> FastAPI:
    """Construye la app. Monta ``/dev/token`` SOLO con JWKS inline (nunca en prod).

    El ``lifespan`` arranca/detiene el hub del WebSocket (LISTEN/NOTIFY); solo
    corre cuando la app se sirve de verdad (uvicorn), no bajo ASGITransport.
    """
    app = FastAPI(title="TAKAB API", version="0.1.0", lifespan=lifespan)

    # Fundación T-1.18.
    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(incidents_ack_router)

    # Catálogo SOC (B1).
    app.include_router(sites_router)
    app.include_router(sensors_router)
    app.include_router(fleet_router)
    app.include_router(tenants_router)

    # Incidentes / eventos / dictámenes / rule-sets (B2).
    app.include_router(incidents_router)
    app.include_router(events_router)
    app.include_router(dictamens_router)
    app.include_router(rule_sets_router)

    # Telemetría (B3) y exportación de evidencia (B4).
    app.include_router(telemetry_router)
    app.include_router(exports_router)

    # Canal live WebSocket ``/ws`` (B4).
    app.include_router(ws_router)

    # Guard de entorno: auth_jwks_json vacío = producción (JWKS remoto) → sin /dev/token.
    if Settings().auth_jwks_json:
        from takab_api.routers.dev_token import router as dev_token_router

        app.include_router(dev_token_router)

    return app


app = create_app()
