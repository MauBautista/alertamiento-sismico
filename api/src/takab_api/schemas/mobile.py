"""Modelos de la superficie MÓVIL (T-2.03 · spec móvil §5).

Contratos honestos: cada campo refleja una columna o derivación documentada;
nada se inventa. ``phase`` es la derivación del servidor (el teléfono JAMÁS
decide fases — spec §4.1); los ingredientes crudos viajan al lado para que el
cliente no pueda ser engañado por la derivación.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# --- push tokens --------------------------------------------------------------


class PushTokenIn(BaseModel):
    """Registro/rotación de token FCM/APNs (upsert por ``token``)."""

    platform: Literal["ios", "android"]
    token: str = Field(min_length=8, max_length=4096)
    site_id: UUID | None = None


class PushTokenOut(BaseModel):
    push_token_id: UUID
    platform: str
    token: str
    site_id: UUID | None
    created_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None


# --- device keys (§2.1-B: el teléfono firma la INTENCIÓN) ----------------------


class DeviceKeyIn(BaseModel):
    """Llave pública respaldada por hardware (SPKI PEM, P-256). La verificación
    criptográfica de intenciones llega en T-2.09; aquí solo se registra."""

    platform: Literal["ios", "android"]
    public_key: str = Field(min_length=64, max_length=8192)
    attestation: dict[str, Any] = Field(default_factory=dict)

    @field_validator("public_key")
    @classmethod
    def _looks_like_pem(cls, v: str) -> str:
        v = v.strip()
        if "-----BEGIN PUBLIC KEY-----" not in v or "-----END PUBLIC KEY-----" not in v:
            raise ValueError("public_key debe ser SPKI PEM (BEGIN/END PUBLIC KEY)")
        return v


class DeviceKeyOut(BaseModel):
    key_id: UUID
    platform: str
    created_at: datetime
    revoked_at: datetime | None


# --- enrolamiento (site_enrollment_codes → user_zone_assignments) -------------


class EnrollmentIn(BaseModel):
    code: str = Field(min_length=4, max_length=64)


class EnrollmentOut(BaseModel):
    """Resultado del alta: a qué sitio/zona quedó vinculado el portador."""

    site_id: UUID
    site_name: str
    zone_id: UUID | None
    zone_name: str | None
    evac_policy: str | None
    role: str


class EnrollmentCodeIn(BaseModel):
    """Alta de un código de enrolamiento (acción ``enrollment_manage``)."""

    code: str = Field(min_length=4, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    zone_id: UUID | None = None
    expires_at: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1)


class EnrollmentCodeOut(BaseModel):
    code: str
    site_id: UUID
    zone_id: UUID | None
    grants_role: str
    expires_at: datetime | None
    max_uses: int | None
    uses: int
    active: bool


# --- mobile-state (spec §4.1/§5) ----------------------------------------------

Phase = Literal["idle", "alert_active", "shaking_concluded", "reentry_approved"]


class MobileIncidentOut(BaseModel):
    incident_id: UUID
    trigger: str
    severity: str
    state: str
    opened_at: datetime
    #: Estaciones que corroboraron el evento regional (meta.node_count del
    #: evento; None si la fuente no es de red). Mismo dato que el pill de Triage.
    node_count: int | None
    #: [T-2.05] PGA instrumental MEDIDO por el gabinete (incidents.max_pga_g) —
    #: la etiqueta de fuente "DETECCIÓN LOCAL" lo muestra; None si aún no hay
    #: medición. JAMÁS es magnitud (§2.1-A: la magnitud solo post-evento, SSN).
    max_pga_g: float | None


class MobileZoneOut(BaseModel):
    zone_id: UUID
    name: str
    level_code: str | None
    #: evacuate|shelter|None — None = sin política definida (la app lo declara).
    evac_policy: str | None


class SiteAssetOut(BaseModel):
    asset_id: UUID
    kind: str
    title: str
    description: str | None
    zone_id: UUID | None
    content_type: str | None
    #: URL presignada de descarga (TTL corto). None si el asset es textual o el
    #: bucket no está configurado en este entorno (la app lo declara, no inventa).
    url: str | None
    updated_at: datetime


class MobileDrillOut(BaseModel):
    """Simulacros para la app: activo (banner ámbar), próximo (agenda D4c —
    informativa, JAMÁS auto-arranca) y último ejecutado."""

    active: bool
    next_scheduled_at: datetime | None
    last_started_at: datetime | None
    last_note: str | None


class MobileReentryOut(BaseModel):
    blocked: bool
    #: Estado del último dictamen del incidente (o None si no hay).
    dictamen_status: str | None
    dictamen_signed: bool


class MobileStateOut(BaseModel):
    """Estado consolidado por sitio para la app (spec §5).

    Derivación de ``phase`` (documentada; el servidor es la autoridad):
    - sin incidente abierto → ``idle``
    - incidente abierto + último tier del sitio ≠ ``normal`` → ``alert_active``
    - incidente abierto + tier ``normal`` → ``shaking_concluded`` (movimiento
      terminado; el reingreso queda BLOQUEADO durante la evaluación — la app
      muestra check-in o bloqueo según su propio check-in)
    - dictamen FIRMADO habitable (normal_operation|inhabit_monitor) →
      ``reentry_approved`` (hasta que el incidente cierre → idle)
    Los ingredientes crudos (incident/state, latest_tier, reentry) viajan junto
    a la derivación.
    """

    site_id: UUID
    site_name: str
    server_ts: datetime
    phase: Phase
    incident: MobileIncidentOut | None
    latest_tier: str | None
    my_zone: MobileZoneOut | None
    reentry: MobileReentryOut
    assembly_point: SiteAssetOut | None
    #: Strings normativos del tenant (§2.1-C). Vacío = el tenant no tiene textos
    #: configurados TODAVÍA (GATE-LEGAL) — la app no muestra literal alguno.
    compliance_labels: dict[str, str]
    drill: MobileDrillOut


# --- check-ins (life_checkins) --------------------------------------------------


class CheckinIn(BaseModel):
    """Check-in de vida. ``subject_user_id`` SOLO para el check-in DELEGADO del
    headcount (táctico marca "verificado en persona"); requiere ``roster_read``."""

    status: Literal["safe", "need_help"]
    zone_id: UUID | None = None
    #: GPS opcional (LFPDPPP): solo viaja con consentimiento y solo aporta en
    #: need_help. [lon, lat] WGS84.
    location: tuple[float, float] | None = None
    ts_device: datetime | None = None
    subject_user_id: UUID | None = None

    @field_validator("location")
    @classmethod
    def _valid_lonlat(cls, v: tuple[float, float] | None) -> tuple[float, float] | None:
        if v is None:
            return None
        lon, lat = v
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError("location fuera de rango [lon, lat]")
        return v


class CheckinOut(BaseModel):
    checkin_id: UUID
    incident_id: UUID
    user_id: UUID
    site_id: UUID
    status: str
    via: str
    verified_by: UUID | None
    ts_device: datetime | None
    created_at: datetime


# --- roster (headcount 2.6) -----------------------------------------------------


class RosterCheckin(BaseModel):
    status: str
    via: str
    created_at: datetime
    ts_device: datetime | None


class RosterEntry(BaseModel):
    user_id: UUID
    display_name: str | None
    phone: str | None
    zone_id: UUID | None
    zone_name: str | None
    checkin: RosterCheckin | None


class RosterOut(BaseModel):
    incident_id: UUID
    site_id: UUID
    total: int
    safe: int
    need_help: int
    unreported: int
    entries: list[RosterEntry]


# --- damage reports (2.4) --------------------------------------------------------

DAMAGE_CATEGORY_KEYS = frozenset(
    {
        "structural",
        "non_structural",
        "water_leak",
        "gas_leak",
        "electrical",
        "people_trapped",
    }
)
DAMAGE_SEVERITIES = frozenset({"low", "medium", "critical"})


class DamageCategoryIn(BaseModel):
    key: str
    severity: str
    note: str | None = Field(default=None, max_length=500)

    @field_validator("key")
    @classmethod
    def _known_key(cls, v: str) -> str:
        if v not in DAMAGE_CATEGORY_KEYS:
            raise ValueError(f"categoría desconocida: {v!r}")
        return v

    @field_validator("severity")
    @classmethod
    def _known_severity(cls, v: str) -> str:
        if v not in DAMAGE_SEVERITIES:
            raise ValueError(f"severidad desconocida: {v!r}")
        return v


class DamageReportIn(BaseModel):
    categories: list[DamageCategoryIn] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=2000)
    zone_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
    ts_device: datetime | None = None
    #: Firma de intención (llave hardware-backed §2.1-B). Se ALMACENA desde ya;
    #: la verificación criptográfica llega en T-2.09/T-2.10 — sin fingir.
    intent_key_id: UUID | None = None
    intent_signature: str | None = None


class DamageReportOut(BaseModel):
    report_id: UUID
    incident_id: UUID
    site_id: UUID
    zone_id: UUID | None
    user_sub: UUID
    categories: list[dict[str, Any]]
    people_at_risk: bool
    notes: str | None
    evidence_ids: list[UUID]
    ts_device: datetime | None
    created_at: datetime


# --- assets (gestión) -------------------------------------------------------------


class SiteAssetCreateIn(BaseModel):
    kind: Literal["evac_route", "assembly_point", "manual"]
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    zone_id: UUID | None = None
    #: true ⇒ el asset lleva archivo: la respuesta incluye upload_url presignada.
    with_file: bool = False
    content_type: str | None = Field(default=None, max_length=120)


class SiteAssetCreateOut(BaseModel):
    asset: SiteAssetOut
    #: URL PUT presignada para subir el archivo (solo si with_file y hay bucket).
    upload_url: str | None
