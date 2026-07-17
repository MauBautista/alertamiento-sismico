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


class MobileSiteHealthOut(BaseModel):
    """[T-2.07 · 1.1] Salud del gabinete del sitio para el banner del edificio.

    ``status`` sale del MISMO derivador que la Flota Edge de consola
    (``derive_fleet_state`` — verdad única, mismos umbrales); con varios
    gabinetes gana el PEOR. ``has_wr1`` es el hardware DECLARADO en el alta del
    gabinete: el WR-1 no expone supervisión de línea (solo el Relevador 2 está
    cableado — fase 1.9), así que "SASMEX ENLAZADO" honesto = WR-1 instalado y
    gabinete reportando; jamás un estado del enlace que nadie mide.
    """

    #: OPERATIVO | DEGRADADO | SIN ENLACE (strings de schemas.fleet).
    status: str
    heartbeat_at: datetime | None
    age_s: float | None
    has_wr1: bool
    #: [T-2.08] Métricas del heartbeat MÁS RECIENTE del sitio (dashboard 2.1):
    #: mismo payload que la consola de flota; None = sin dato (la app pinta
    #: "S/D", jamás un 0 inventado — contrato honesto T-1.40).
    mqtt_rtt_ms: float | None = None
    seedlink_lag_s: float | None = None
    ntp_offset_ms: float | None = None
    cpu_temp_c: float | None = None
    power_status: str | None = None
    battery_pct: float | None = None
    cert_days_remaining: int | None = None


class DirectoryEntryOut(BaseModel):
    """[T-2.07 · 1.7] Contacto de emergencia del sitio (roster público:
    brigadistas/seguridad/administración con teléfono de un toque)."""

    user_id: UUID
    display_name: str
    role: str
    zone_id: UUID | None
    zone_name: str | None
    phone: str | None


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
    #: [T-2.07] Banner del edificio (1.1) — verdad única de Flota Edge.
    site_health: MobileSiteHealthOut


# --- check-ins (life_checkins) --------------------------------------------------


class CheckinIn(BaseModel):
    """Check-in de vida. ``subject_user_id`` SOLO para el check-in DELEGADO del
    headcount (táctico marca "verificado en persona"); requiere ``roster_read``."""

    #: [T-2.06] Id generado por la COLA OFFLINE del dispositivo: el reintento
    #: tras una red que murió a medias replica el MISMO id y el servidor
    #: deduplica (regla de oro 3). Sin id ⇒ el servidor genera uno.
    checkin_id: UUID | None = None
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


class HeadcountCloseIn(BaseModel):
    """[T-2.11] Cierre de headcount = ACCIÓN FIRMADA (precondición del paso 1
    de 2.2). La firma de intención (§2.1-B) es OPCIONAL: si viene, se verifica
    contra ``device_keys`` sobre el canónico ``takab-headcount-v1``."""

    key_id: UUID | None = None
    signature: str | None = Field(default=None, max_length=4096)


class HeadcountActionOut(BaseModel):
    """Acción de headcount registrada en el timeline (cierre o notificación)."""

    action_id: UUID
    incident_id: UUID
    kind: str
    unreported: int
    signed: bool


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


# --- evidencia forense (cámara 2.3) ---------------------------------------------


class EvidenceRegisterIn(BaseModel):
    """[T-2.10] Registro de una foto forense: el móvil declara el SHA-256 del
    archivo FINAL (marca de agua ya horneada) calculado en captura (§4.2); el
    backend firma el PUT y guarda la huella para verificarla después."""

    #: SHA-256 hex (64) del archivo final — la verificación server-side lo
    #: confronta contra el objeto realmente subido (alterar un byte ⇒ falla).
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    content_type: str = Field(default="image/jpeg", max_length=120)
    ts_from: datetime | None = None


class EvidenceRegisterOut(BaseModel):
    evidence_id: UUID
    #: PUT presignado (subida directa sin credenciales AWS); None sin bucket.
    upload_url: str | None


class EvidenceVerifyOut(BaseModel):
    """[T-2.10] Resultado de re-hashear el objeto subido contra lo declarado."""

    evidence_id: UUID
    verified: bool
    expected_sha256: str | None
    actual_sha256: str | None


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
