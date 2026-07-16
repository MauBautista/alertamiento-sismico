"""App FastAPI de la API TAKAB: health + auth (/me, ack), catálogo/incidentes/
telemetría/exports REST y el canal live WebSocket ``/ws`` (T-1.22)."""

from __future__ import annotations

from fastapi import FastAPI

from takab_api.health import router as health_router
from takab_api.routers.audit import router as audit_router
from takab_api.routers.catalog import router as catalog_router
from takab_api.routers.commands import router as commands_router
from takab_api.routers.dictamens import router as dictamens_router
from takab_api.routers.drills import router as drills_router
from takab_api.routers.events import router as events_router
from takab_api.routers.exports import router as exports_router
from takab_api.routers.fleet import router as fleet_router
from takab_api.routers.incidents import router as incidents_router
from takab_api.routers.incidents_ack import router as incidents_ack_router
from takab_api.routers.incidents_ops import router as incidents_ops_router
from takab_api.routers.me import router as me_router
from takab_api.routers.mobile_incident import router as mobile_incident_router
from takab_api.routers.mobile_me import router as mobile_me_router
from takab_api.routers.mobile_site import router as mobile_site_router
from takab_api.routers.reports import router as reports_router
from takab_api.routers.rule_sets import router as rule_sets_router
from takab_api.routers.sensors import router as sensors_router
from takab_api.routers.sites import router as sites_router
from takab_api.routers.telemetry import router as telemetry_router
from takab_api.routers.tenants import router as tenants_router
from takab_api.routers.visibility import router as visibility_router
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
    # Visibilidad configurable entre clientes (T-1.73, superadmin).
    app.include_router(visibility_router)

    # Incidentes / eventos / dictámenes / rule-sets (B2).
    app.include_router(incidents_router)
    app.include_router(events_router)
    app.include_router(dictamens_router)
    app.include_router(rule_sets_router)

    # Operaciones del operador + catálogo de referencia (Fase 1.7 · T-1.48).
    app.include_router(incidents_ops_router)
    app.include_router(catalog_router)

    # Audit trail, solo lectura (Fase 1.8 · T-1.57).
    app.include_router(audit_router)

    # Simulacro institucional (Fase 1.8 · T-1.60).
    app.include_router(drills_router)

    # Telemetría (B3), exportación de evidencia (B4) y reporte PDF (B5).
    app.include_router(telemetry_router)
    app.include_router(exports_router)
    app.include_router(reports_router)

    # Comandos remotos de actuador firmados (B9, regla de oro 8).
    app.include_router(commands_router)

    # Superficie MÓVIL (Fase 2 · T-2.03): portador, sitio e incidente.
    app.include_router(mobile_me_router)
    app.include_router(mobile_site_router)
    app.include_router(mobile_incident_router)

    # Canal live WebSocket ``/ws`` (B4).
    app.include_router(ws_router)

    # Guard de entorno: auth_jwks_json vacío = producción (JWKS remoto) → sin /dev/token.
    if Settings().auth_jwks_json:
        from takab_api.routers.dev_token import router as dev_token_router

        app.include_router(dev_token_router)

    return app


app = create_app()
