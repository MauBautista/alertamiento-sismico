"""App FastAPI de la API TAKAB: health + auth (/me, ack), catálogo/incidentes/
telemetría/exports REST y el canal live WebSocket ``/ws`` (T-1.22)."""

from __future__ import annotations

from fastapi import FastAPI

from takab_api.health import router as health_router
from takab_api.notify.providers import build_providers, channel_reality
from takab_api.routers.audit import router as audit_router
from takab_api.routers.catalog import router as catalog_router
from takab_api.routers.commands import router as commands_router
from takab_api.routers.compliance import router as compliance_router
from takab_api.routers.dictamens import router as dictamens_router
from takab_api.routers.drills import router as drills_router
from takab_api.routers.events import router as events_router
from takab_api.routers.exports import router as exports_router
from takab_api.routers.fleet import router as fleet_router
from takab_api.routers.forensics import router as forensics_router
from takab_api.routers.incidents import actions_router as incident_actions_router
from takab_api.routers.incidents import router as incidents_router
from takab_api.routers.incidents import tactical_ack_router
from takab_api.routers.incidents_ack import router as incidents_ack_router
from takab_api.routers.incidents_ops import router as incidents_ops_router
from takab_api.routers.maintenance import router as maintenance_router
from takab_api.routers.me import router as me_router
from takab_api.routers.mobile_incident import router as mobile_incident_router
from takab_api.routers.mobile_me import router as mobile_me_router
from takab_api.routers.mobile_site import router as mobile_site_router
from takab_api.routers.notify import router as notify_router
from takab_api.routers.notify_webhooks import router as notify_webhooks_router
from takab_api.routers.ops_alerts import router as ops_alerts_router
from takab_api.routers.privacy import router as privacy_router
from takab_api.routers.reports import router as reports_router
from takab_api.routers.rule_sets import router as rule_sets_router
from takab_api.routers.sensors import router as sensors_router
from takab_api.routers.sites import router as sites_router
from takab_api.routers.telemetry import router as telemetry_router
from takab_api.routers.tenants import router as tenants_router
from takab_api.routers.users import router as users_router
from takab_api.routers.visibility import router as visibility_router
from takab_api.routers.ws import router as ws_router
from takab_api.settings import Settings
from takab_api.ws import lifespan


def create_app() -> FastAPI:
    """Construye la app. Monta ``/dev/token`` SOLO con JWKS inline (nunca en prod).

    El ``lifespan`` arranca/detiene el hub del WebSocket (LISTEN/NOTIFY); solo
    corre cuando la app se sirve de verdad (uvicorn), no bajo ASGITransport.
    """
    # [D-22] La documentación interactiva NO se publica en la nube.
    #
    # `web_allowed_cidrs` protegía por red todo lo que no exige autenticación.
    # Al abrir la consola —para que AWS pueda confirmar la suscripción de SNS y
    # para que el enlace de los correos sirva— eso deja de ser cierto.
    #
    # ⚠️ CORRECCIÓN (2026-08-22), y hay que leerla antes que el resto: esto se
    # escribió creyendo que `/docs` estaba EXPUESTO. No lo estaba.
    #
    # Se midió `GET /docs -> 200` desde fuera y se leyó como Swagger. Era el
    # `index.html` de la consola: Caddy manda todo lo que no es `/api/*` al SPA, y
    # un SPA contesta 200 a CUALQUIER ruta para que funcione su enrutado de
    # cliente. Se comprobó el código y no el cuerpo. Contra la API directamente,
    # `/docs`, `/openapi.json` y `/redoc` dan 404 con esto puesto.
    #
    # Se conserva igualmente, y no por orgullo: hoy nada los publica, pero eso
    # depende de una regla de Caddy que vive en otro repositorio mental. El día que
    # alguien enrute `/docs` o monte la API en su propio host, el esquema completo
    # —cada ruta, cada parámetro, cada modelo— saldría publicado sin que nadie lo
    # decidiera. Esto lo impide desde el único sitio que sabe si es producción.
    #
    # No es una vulnerabilidad: la oscuridad no protege y los 401 siguen.
    #
    # `redoc_url` va con ellas: sirve el MISMO esquema por otra puerta, y apagar
    # dos de tres es no apagar ninguna.
    #
    # No rompe el SDK: `openapi.json` se exporta con `scripts/export_openapi.py`
    # importando la app, no pidiéndoselo a un servidor vivo.
    publico = Settings().es_produccion
    app = FastAPI(
        title="TAKAB API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if publico else "/docs",
        redoc_url=None if publico else "/redoc",
        openapi_url=None if publico else "/openapi.json",
    )

    # Fundación T-1.18.
    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(incidents_ack_router)

    # Catálogo SOC (B1).
    app.include_router(sites_router)
    app.include_router(sensors_router)
    app.include_router(fleet_router)
    app.include_router(tenants_router)
    # Marco normativo DECLARADO por el cliente (Fase 2.8 · T-2.82).
    app.include_router(compliance_router)
    # Visibilidad configurable entre clientes (T-1.73, superadmin).
    app.include_router(visibility_router)
    # Gestión de usuarios: proxy del Admin API de Cognito (T-2.54).
    app.include_router(users_router)

    # Incidentes / eventos / dictámenes / rule-sets (B2).
    app.include_router(incidents_router)
    # Timeline del incidente: consola ∪ dashboard táctico móvil (T-2.08).
    app.include_router(incident_actions_router)
    app.include_router(tactical_ack_router)
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

    # Ventanas de mantenimiento: silencian alarmas de OPERACIÓN, jamás la
    # actuación (Fase 2.5 · T-2.71).
    app.include_router(maintenance_router)

    # Aviso de privacidad versionado + consentimiento append-only (Fase 2.8 ·
    # T-2.79). JAMÁS gatea el camino crítico: ver el docstring del router.
    app.include_router(privacy_router)

    # Telemetría (B3), exportación de evidencia (B4) y reporte PDF (B5).
    app.include_router(telemetry_router)
    app.include_router(exports_router)
    app.include_router(reports_router)
    # [T-2.40] Hechos medidos del incidente: una fuente para pantalla y dictamen.
    app.include_router(forensics_router)

    # Comandos remotos de actuador firmados (B9, regla de oro 8).
    app.include_router(commands_router)

    # Superficie MÓVIL (Fase 2 · T-2.03): portador, sitio e incidente.
    app.include_router(mobile_me_router)
    app.include_router(mobile_site_router)
    app.include_router(mobile_incident_router)

    # Canal live WebSocket ``/ws`` (B4).
    app.include_router(ws_router)

    # [T-2.75.a] Realidad de los canales de notificación: qué provider entrega de
    # verdad y cuál no. Se congela AQUÍ, con el mismo ``build_providers`` que
    # arranca el worker, porque es configuración del proceso — cambia con un
    # despliegue, no entre dos peticiones. De paso, la API hereda el grito de
    # arranque de T-2.75 sobre los canales simulados en vez de dejarlo solo en el
    # worker.
    app.state.notify_channels = channel_reality(build_providers(Settings()))
    app.include_router(notify_router)

    # [T-2.77.b] Webhooks de estado de entrega. **La ÚNICA superficie pública de
    # esta API**: la llaman Twilio y Meta, que no tienen un token nuestro, así
    # que no lleva `require_roles` — la firma HMAC del proveedor es toda su
    # autenticación. Va montado aquí como cualquier otro router y su seguridad
    # entera vive en `routers/notify_webhooks.py`; léelo antes de tocar la ruta.
    app.include_router(notify_webhooks_router)

    # [T-2.78.a] La cadena de OPERACIÓN (CloudWatch → SNS → on-call), que es OTRA
    # cadena: no comparte código, destinatario ni permiso con `notify`. Trae dos
    # rutas públicas más —el suscriptor HTTPS de SNS y el acuse humano— y una
    # detrás de Cognito. Un suscriptor HTTPS de SNS es una SSRF esperando: las
    # dos URLs que llegan DENTRO del cuerpo (`SubscribeURL`, `SigningCertURL`)
    # las elige quien lo manda. Cómo se cierran está en `ops/alerts.py`; léelo
    # antes de tocar la ruta.
    app.include_router(ops_alerts_router)

    # Guard de entorno: auth_jwks_json vacío = producción (JWKS remoto) → sin /dev/token.
    if Settings().auth_jwks_json:
        from takab_api.routers.dev_token import router as dev_token_router

        app.include_router(dev_token_router)

    return app


app = create_app()
