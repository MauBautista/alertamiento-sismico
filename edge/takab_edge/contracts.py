"""Contratos internos del edge (Pydantic v2).

Fuente de verdad tipada de los payloads que fluyen entre módulos
(seedlink→signal→rules→actuators/cloud) y de lo que `cloud` publica hacia
AWS IoT Core. En T-1.11 se promueven a JSON Schema versionados en
`shared/schemas/` (blueprint §0.1: "la nube se construye sobre contratos ya
validados en el edge"); aquí viven como su origen tipado.

Reglas de oro relevantes (CLAUDE.md §2):
- Idempotencia: todo evento que cruza edge→nube lleva `event_id` (nonce).
- El camino SASMEX→actuador es determinista; estos modelos no contienen IA.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Timestamp UTC timezone-aware (evita datetimes naive en el contrato)."""
    return datetime.now(UTC)


def new_event_id() -> str:
    """Nonce de evento para idempotencia edge→nube (CLAUDE.md §2.3)."""
    return uuid4().hex


class Tier(StrEnum):
    """Tiers deterministas del motor de reglas (blueprint §4.5)."""

    NORMAL = "normal"
    WATCH = "watch"
    RESTRICTED = "restricted"
    EVACUATE_OR_HOLD = "evacuate_or_hold"
    MANUAL_ONLY = "manual_only"


class AlertSource(StrEnum):
    """Origen de una detección/evento local (blueprint §4.5)."""

    SASMEX = "sasmex"  # WR-1 dry-contact — canal primario y autoritativo
    # Valor = incidents.trigger (db/schema.sql); NO "threshold" — evitaría DLQ en T-1.17.
    THRESHOLD = "local_threshold"  # umbral instrumental local (PGA/PGV)
    MANUAL = "manual"  # disparo manual autorizado


class ActuatorChannel(StrEnum):
    SIREN = "siren"
    STROBE = "strobe"
    GAS_VALVE = "gas_valve"
    ELEVATOR = "elevator"
    DOOR_RETAINER = "door_retainer"
    #: [T-1.59] Canal LÓGICO de comandos de sistema (self_test): no es un relé —
    #: jamás entra a LOCAL_RELAY_CHANNELS/REFLEX_CHANNELS ni al modelo de demandas.
    SYSTEM = "system"


class FailSafeMode(StrEnum):
    """Estado seguro por canal ante falla del Pi (SPOF-07, blueprint §4.7)."""

    NORMALLY_OPEN = "NO"  # sirena: una falla NO la deja sonando
    NORMALLY_CLOSED = "NC"  # retenedor de puerta: una falla LIBERA la puerta
    FAIL_CLOSE = "fail_close"  # válvula de gas: una falla la CIERRA


class ActuatorAction(StrEnum):
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    #: [T-1.59] Autodiagnóstico del gabinete (canal `system`): pulsa los relés NO
    #: audibles con readback; la sirena JAMÁS se energiza en un self-test.
    SELF_TEST = "self_test"


class UpsStatus(StrEnum):
    LINE = "line"  # RED ELÉCTRICA
    BATTERY = "battery"  # EN BATERÍA
    UNKNOWN = "unknown"


class WaveformPacket(BaseModel):
    """Paquete de muestras de un canal (miniSEED decodificado)."""

    network: str = "AM"
    station: str
    location: str = ""
    channel: str  # EHZ, ENZ, ENN, ENE
    starttime: datetime
    sample_rate: float = 100.0
    samples: list[int]  # counts (el RS4D entrega enteros)

    @property
    def npts(self) -> int:
        return len(self.samples)

    @property
    def endtime(self) -> datetime:
        """Tiempo de la última muestra (para lag y detección de gaps)."""
        if not self.samples or self.sample_rate <= 0:
            return self.starttime
        return self.starttime + timedelta(seconds=(self.npts - 1) / self.sample_rate)

    @property
    def next_starttime(self) -> datetime:
        """Inicio esperado del paquete contiguo siguiente (fin de cobertura)."""
        if self.sample_rate <= 0:
            return self.starttime
        return self.starttime + timedelta(seconds=self.npts / self.sample_rate)


class Feature1s(BaseModel):
    """Features agregadas a 1 s — contrato de salida de `signal` (T-1.6)."""

    station: str
    channel: str
    window_start: datetime
    pga: float  # g
    pgv: float  # cm/s
    rms: float
    sta_lta: float
    clipping: bool = False
    health_score: float = 1.0


class FeatureBatch(BaseModel):
    """Lote de Feature1s de tier `normal` (T-1.56 · batcheo escalonado por tier).

    Solo TELEMETRÍA REPONIBLE: en reposo el gateway acumula ~10 s de features y
    publica 1 mensaje (≈97% menos publishes/SQS); al escalar a `watch`+ se hace
    flush inmediato y se vuelve al 1 Hz individual (`feature_1s`). La detección
    y la actuación JAMÁS pasan por aquí. ``max_length=256`` ≈ 64 KB « 128 KB
    (tope de publish de AWS IoT). Sin ``event_id`` ⇒ sin dedup de spool (como
    los features sueltos); la idempotencia real es la PK ``(ts, sensor_id,
    channel)`` de la nube.
    """

    kind: Literal["feature_batch"] = "feature_batch"
    gateway_id: str
    features: list[Feature1s] = Field(min_length=1, max_length=256)
    batched_at: datetime = Field(default_factory=utcnow)


class SasmexSignal(BaseModel):
    """Estado del contacto seco del WR-1 — canal primario (blueprint §4.5)."""

    active: bool
    source: str = "WR-1"
    is_test: bool = False  # pulso de prueba periódica de CIRES (SPOF-03)
    received_at: datetime = Field(default_factory=utcnow)


class TierDecision(BaseModel):
    """Decisión del motor de reglas (T-1.8). Sin IA — 100% determinista."""

    event_id: str = Field(default_factory=new_event_id)
    tier: Tier
    source: AlertSource
    severity: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=utcnow)


class ActuatorCommand(BaseModel):
    channel: ActuatorChannel
    action: ActuatorAction
    event_id: str
    issued_at: datetime = Field(default_factory=utcnow)


class ActuatorAck(BaseModel):
    """ACK de ejecución con latencia relativa (T+0.42s, blueprint §4.2)."""

    channel: ActuatorChannel
    action: ActuatorAction
    event_id: str
    success: bool
    latency_s: float  # segundos desde el comando
    executed_at: datetime = Field(default_factory=utcnow)
    detail: str = ""

    @property
    def relative_label(self) -> str:
        """Etiqueta legible tipo ``T+0.42s`` para UI/telemetría."""
        return f"T+{self.latency_s:.2f}s"


class BackfillRequest(BaseModel):
    """Solicitud de URL pre-firmada para backfill/evidencia (T-1.25).

    El edge la publica en ``takab/backfill/request/<thing>``; la nube verifica
    que el thing del topic sea el principal X.509 y responde un
    ``backfill_grant`` por ``takab/backfill/grant/<thing>`` con la KEY CANÓNICA
    (autoridad de la nube) y la URL PUT pre-firmada.
    """

    kind: Literal["backfill_request"] = "backfill_request"
    request_id: str = Field(default_factory=new_event_id)
    mode: Literal["backfill", "evidence"]
    #: Ventana temporal de los datos (backfill) o del evento (evidence).
    ts_from: datetime
    ts_to: datetime
    #: Nº de líneas NDJSON (backfill; dimensiona y audita el objeto esperado).
    lines: int = 0
    #: Solo mode='evidence': evento local (== incidents.event_uuid en la nube).
    event_id: str = ""
    #: Solo mode='evidence': sha256 del miniSEED a subir (la key lo incluye).
    sha256: str = ""


class CommandAck(BaseModel):
    """ACK de un comando remoto firmado (T-1.23). Viaja por ``takab/acks``: el
    campo ``kind`` es el discriminador frente a ``ActuatorAck`` (contrato
    ``command_ack.schema.json``); la nube transiciona ``commands.status``."""

    kind: Literal["command_ack"] = "command_ack"
    command_id: str
    nonce: str
    channel: ActuatorChannel
    action: ActuatorAction
    success: bool
    latency_s: float = 0.0
    executed_at: datetime = Field(default_factory=utcnow)
    detail: str = ""
    #: [T-1.59] Resultados estructurados del self_test (por relé + salud del
    #: cache); None en acks de activate/deactivate. ADITIVO (schema 1.4.0).
    results: dict | None = None


class RelayState(BaseModel):
    channel: ActuatorChannel
    energized: bool  # estado eléctrico del relé
    activated: bool = False  # estado lógico de protección (p.ej. gas CERRADO, puerta LIBERADA)
    fail_safe: FailSafeMode


class HealthSnapshot(BaseModel):
    """Snapshot de salud del gabinete (T-1.10; honesto desde T-1.40).

    Los campos de sonda son OPCIONALES: ``None`` = «sin dato» (no hay UPS, no
    hay fuente NTP, cert ilegible) y la nube lo muestra como S/D. Un valor
    presente es una MEDICIÓN — nunca el default optimista de antes (100% de
    batería, 365 días de cert, offset 0.0), que era mentira (regla de oro 7).
    """

    gateway_id: str
    captured_at: datetime = Field(default_factory=utcnow)
    ntp_offset_s: float | None = None
    seedlink_lag_s: float = 0.0
    packet_loss_pct: float = 0.0
    mqtt_rtt_ms: float | None = None
    ups_status: UpsStatus = UpsStatus.UNKNOWN
    battery_pct: float | None = None
    temperature_c: float = 0.0
    cert_days_remaining: int | None = None
    # [T-1.53] % de disco usado (shutil.disk_usage) — None = sin dato (regla de
    # oro 7). ADITIVO (schema 1.2.0): el ingest de la nube lo ignora (sin
    # columna destino), el panel LAN lo muestra.
    disk_used_pct: float | None = None
    relays: list[RelayState] = Field(default_factory=list)
    transition_reason: str = "heartbeat"


class LocalEvent(BaseModel):
    """Evento local confirmado — idempotente por `event_id`; cruza a la nube."""

    event_id: str = Field(default_factory=new_event_id)
    tenant_id: str
    site_id: str
    source: AlertSource
    tier: Tier
    created_at: datetime = Field(default_factory=utcnow)


class EvidenceObject(BaseModel):
    """Evidencia inmutable: ventana miniSEED de un evento subida a S3, con sha256.

    Idempotente por (`event_id`, `sha256`): re-subir el mismo contenido = mismo objeto.
    """

    event_id: str
    s3_key: str
    sha256: str
    size_bytes: int
    uploaded_at: datetime = Field(default_factory=utcnow)
