"""Frames tipados del WebSocket live (T-1.22 · B4).

Modelos Pydantic de cada frame del protocolo ``/ws``. Se exportan al OpenAPI
(la fase de integración los referencia) para que ``sdk-ts`` tenga los tipos del
canal live sin escribirlos a mano.

Handshake cliente→servidor: ``auth`` (primer frame, obligatorio) y ``subscribe``.
Servidor→cliente: ``ready`` (tras auth ok), ``error``, y los frames de datos
(``incident``/``incident_action``/``site_state``/``features``). El frame de datos
NUNCA es el payload crudo del NOTIFY: el hub re-consulta la fila con los GUCs del
suscriptor y serializa estos modelos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

TOPIC_INCIDENTS = "incidents"
TOPIC_SITE_STATE = "site_state"
TOPIC_FEATURES_PREFIX = "features:"


# ---- cliente → servidor ---------------------------------------------------
class AuthFrame(BaseModel):
    """Primer frame obligatorio: autentica el socket con el ID token."""

    type: Literal["auth"]
    token: str


class SubscribeFrame(BaseModel):
    """Alta a un topic: ``incidents`` | ``site_state`` | ``features:<site_id>``."""

    type: Literal["subscribe"]
    topic: str


# ---- servidor → cliente ---------------------------------------------------
class ReadyFrame(BaseModel):
    """Confirma que el socket quedó autenticado y listo para suscribirse."""

    type: Literal["ready"] = "ready"


class ErrorFrame(BaseModel):
    """Error de protocolo (topic/JSON inválido); no cierra el socket."""

    type: Literal["error"] = "error"
    detail: str


class IncidentFrame(BaseModel):
    """Incidente (INSERT/UPDATE) visible para el suscriptor tras RLS."""

    type: Literal["incident"] = "incident"
    incident_id: UUID
    tenant_id: UUID
    site_id: UUID
    event_id: str | None = None
    opened_at: datetime
    closed_at: datetime | None = None
    severity: str
    state: str
    trigger: str
    max_pga_g: float | None = None
    max_pgv_cms: float | None = None


class IncidentActionFrame(BaseModel):
    """Acción sobre un incidente (ack, siren_on, dictamen, notify_sent…)."""

    type: Literal["incident_action"] = "incident_action"
    action_id: UUID
    incident_id: UUID
    tenant_id: UUID
    #: [T-2.08] Sitio del incidente: permite acotar la entrega por site_scope
    #: (tácticos móviles) y enrutar el frame en clientes multi-sitio.
    site_id: UUID | None = None
    ts: datetime
    kind: str
    actor: str
    payload: dict[str, Any] = {}


class SiteStateFrame(BaseModel):
    """Salud del gabinete: transición de ``device_health`` o de ``rule_evaluations``.

    ``kind`` discrimina el origen. Los campos específicos de cada origen son
    opcionales (device_health trae métricas de enlace; rule_evaluation trae
    tiers). El aislamiento por tenant lo garantiza la re-consulta RLS del hub.
    """

    type: Literal["site_state"] = "site_state"
    kind: Literal["device_health", "rule_evaluation"]
    tenant_id: UUID
    gateway_id: UUID
    site_id: UUID | None = None
    ts: datetime
    # device_health
    reason: str | None = None
    mqtt_rtt_ms: float | None = None
    seedlink_lag_s: float | None = None
    ntp_offset_ms: float | None = None
    cpu_temp_c: float | None = None
    power_status: str | None = None
    battery_pct: float | None = None
    battery_min_left: int | None = None
    cert_days_remaining: int | None = None
    # rule_evaluation
    prev_tier: str | None = None
    new_tier: str | None = None
    rule_set_version: int | None = None


class FeatureRow(BaseModel):
    """Una muestra de features 1 s (no waveform crudo — regla de oro 9)."""

    ts: datetime
    channel: str
    pga_g: float | None = None
    pgv_cms: float | None = None
    rms: float | None = None
    stalta: float | None = None
    energy: float | None = None
    clipping: bool = False


class FeaturesFrame(BaseModel):
    """Strip columnar de features 1 s de un sitio (poller 1 Hz sobre la vista segura)."""

    type: Literal["features"] = "features"
    site_id: UUID
    rows: list[FeatureRow]
