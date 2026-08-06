"""Estado derivado de la flota edge (T-1.22 · B1/G7).

``derive_fleet_state`` es la VERDAD ÚNICA del estado de un gateway: se calcula
server-side a partir del último ``device_health`` y los umbrales de ``settings``.
La UI (T-1.28) solo pinta el resultado; jamás recalcula. Función pura → testeable
con filas fixture sin DB.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Estados posibles (strings de UI en español, tal cual los pinta el SOC).
OPERATIVO = "OPERATIVO"
DEGRADADO = "DEGRADADO"
SIN_ENLACE = "SIN ENLACE"


def derive_fleet_state(
    *,
    age_s: float | None,
    power_status: str | None,
    battery_pct: float | None,
    cert_days_remaining: int | None,
    mqtt_rtt_ms: float | None,
    seedlink_lag_s: float | None,
    ntp_offset_ms: float | None,
    sin_enlace_s: float,
    battery_min_pct: float,
    cert_min_days: int,
    mqtt_rtt_max_ms: float,
    seedlink_lag_max_s: float,
    ntp_offset_max_ms: float,
) -> str:
    """Deriva ``OPERATIVO`` | ``DEGRADADO`` | ``SIN ENLACE``.

    - ``SIN ENLACE``: sin heartbeat (``age_s is None``) o el último es más viejo
      que ``sin_enlace_s`` (el gateway dejó de reportar).
    - ``DEGRADADO``: con enlace vivo pero alguna métrica fuera de rango.
    - ``OPERATIVO``: con enlace y todas las métricas sanas.

    Una métrica ``None`` («sin dato», contrato honesto de T-1.40) NUNCA degrada:
    no tener UPS no es lo mismo que estar en batería.
    """
    if age_s is None or age_s > sin_enlace_s:
        return SIN_ENLACE
    reasons = fleet_degrade_reasons(
        power_status=power_status,
        battery_pct=battery_pct,
        cert_days_remaining=cert_days_remaining,
        mqtt_rtt_ms=mqtt_rtt_ms,
        seedlink_lag_s=seedlink_lag_s,
        ntp_offset_ms=ntp_offset_ms,
        battery_min_pct=battery_min_pct,
        cert_min_days=cert_min_days,
        mqtt_rtt_max_ms=mqtt_rtt_max_ms,
        seedlink_lag_max_s=seedlink_lag_max_s,
        ntp_offset_max_ms=ntp_offset_max_ms,
    )
    return DEGRADADO if reasons else OPERATIVO


def fleet_degrade_reasons(
    *,
    power_status: str | None,
    battery_pct: float | None,
    cert_days_remaining: int | None,
    mqtt_rtt_ms: float | None,
    seedlink_lag_s: float | None,
    ntp_offset_ms: float | None,
    battery_min_pct: float,
    cert_min_days: int,
    mqtt_rtt_max_ms: float,
    seedlink_lag_max_s: float,
    ntp_offset_max_ms: float,
) -> list[str]:
    """QUÉ métrica degrada, en el idioma de la UI (T-1.40, backlog de T-1.28).

    Es la MISMA verdad que ``derive_fleet_state`` (que la llama): si esta lista
    no está vacía, el estado es DEGRADADO. La UI pinta cada razón como pill en
    vez de dejar al operador adivinar cuál de seis métricas se salió de rango.
    """
    reasons: list[str] = []
    if power_status == "battery":
        reasons.append("EN BATERÍA")
    if battery_pct is not None and battery_pct < battery_min_pct:
        reasons.append(f"BATERÍA {battery_pct:.0f}%")
    if cert_days_remaining is not None and cert_days_remaining < cert_min_days:
        reasons.append(f"CERT {cert_days_remaining}d")
    if mqtt_rtt_ms is not None and mqtt_rtt_ms > mqtt_rtt_max_ms:
        reasons.append(f"MQTT {mqtt_rtt_ms:.0f}ms")
    if seedlink_lag_s is not None and seedlink_lag_s > seedlink_lag_max_s:
        reasons.append(f"SEEDLINK {seedlink_lag_s:.1f}s")
    if ntp_offset_ms is not None and abs(ntp_offset_ms) > ntp_offset_max_ms:
        reasons.append(f"NTP {ntp_offset_ms:+.0f}ms")
    return reasons


def sig_fingerprint(sig: str | None) -> str | None:
    """Huella corta de la firma HMAC publicada.

    La firma cruda NUNCA sale del servidor: junto al payload sería material de
    ataque offline contra la clave. La huella basta para que el operador vea que
    dos gabinetes traen la misma config firmada.
    """
    if not sig:
        return None
    return hashlib.sha256(sig.encode()).hexdigest()[:12]


class GatewayConfigStateOut(BaseModel):
    """Estado del config firmado que el gateway tiene REALMENTE (T-1.30 · C4).

    ``publish`` solo registra la intención (202 ``pending_sync``); quien firma y
    entrega es el worker de T-1.23. Este modelo es lo único que autoriza a la
    consola a decir "SINCRONIZADO" en vez de "PENDIENTE".

    - ``in_sync``: el payload publicado coincide con el documento que el worker
      volvería a publicar (``config.edge`` fusionado con ``equipment`` y
      ``cloud_admin_state``). Es la negación del predicado de publicación.
    - ``has_edge_config``: hay un documento que publicarle. [B3] Es el espejo del
      gate de publicación del worker (``base IS NOT NULL``), no "el rule_set
      activo trae bloque ``edge``": el worker también recompone la base desde el
      último doc publicado, así que un rule_set inactivo NO implica que no haya
      nada que mandar. Falso ⇒ no se publicará nunca —ni rule_set con ``edge`` ni
      doc anterior del que partir— y pintar PENDIENTE para siempre sería mentir.
    - ``is_syncable``: el gateway PUEDE recibir config firmada — tiene ``iot_thing``
      y no está retirado *y ya avisado*. [T-2.65] Un gabinete recién retirado sigue
      siendo sincronizable hasta que reciba su último sobre, el que le declara la
      baja: sacarlo de la lista ANTES de avisarle es justo el defecto que dejaba al
      gabinete latiendo invisible. Recibido el sobre, deja el flujo de config.
    - ``version``/``published_at``: los del último documento firmado; ``None`` si
      nunca se publicó.
    """

    gateway_id: UUID
    version: int | None = None
    published_at: datetime | None = None
    sig_fingerprint: str | None = None
    in_sync: bool
    has_edge_config: bool
    is_syncable: bool


class EquipmentProfile(BaseModel):
    """[T-2.31] Actuadores INSTALADOS físicamente en el sitio del gabinete.

    No toda estación tiene gas/ascensores/puertas. Contrato: 5 bools, default
    todo-true (la flota existente no cambia de conducta), claves desconocidas
    rechazadas — un typo en 'gas_valve' no puede volverse "instalado" silencioso.
    Viaja al edge FUSIONADO en el doc firmado del config sync (una sola firma
    cubre config + equipamiento).
    """

    model_config = ConfigDict(extra="forbid")

    siren: bool = True
    strobe: bool = True
    gas_valve: bool = True
    elevator: bool = True
    door_retainer: bool = True


class GatewayOut(BaseModel):
    """Gateway del tenant + estado derivado del último ``device_health``.

    [T-2.35] ``site_name``/``site_code``/``site_status`` los pone el SERVIDOR. La web
    los resolvía haciendo join contra ``/sites``, que oculta los retirados: un gabinete
    huérfano perdía su nombre y la UI lo rebautizaba ``SITIO <8 hex>``, de modo que dos
    huérfanos distintos se veían idénticos. Con el nombre en la fila no hay fallback que
    inventar — la clase de bug entera desaparece.
    """

    gateway_id: UUID
    site_id: UUID
    site_name: str
    site_code: str
    site_status: str
    serial: str
    fw_version: str | None = None
    iot_thing: str | None = None
    status: str
    has_wr1: bool
    equipment: EquipmentProfile = Field(default_factory=EquipmentProfile)
    installed_at: datetime | None = None
    row_version: str
    derived_state: str
    # QUÉ degrada (vacía salvo en DEGRADADO): pills de la UI, misma verdad que
    # derive_fleet_state (T-1.40).
    degrade_reasons: list[str] = []
    last_heartbeat_ts: datetime | None = None
    power_status: str | None = None
    battery_pct: float | None = None
    cert_days_remaining: int | None = None
    mqtt_rtt_ms: float | None = None
    seedlink_lag_s: float | None = None
    ntp_offset_ms: float | None = None
    # [T-2.60.a] Retirado PERO sigue latiendo. No es un estado más del gabinete:
    # es una CONTRADICCIÓN entre lo que la organización cree (dado de baja) y lo
    # que el aparato hace (reportar). Por eso va aparte de `status` y de
    # `derived_state`, que siguen diciendo cada uno su verdad sin mezclarse.
    #
    # Exige acción humana en una de las dos direcciones —desmontarlo de verdad o
    # restaurarlo—, y hasta entonces hay un edificio cuya supervisión nadie mira.
    is_ghost: bool = False
    # Cuándo y quién, para no obligar a irse a la auditoría a mano. `None` cuando
    # no está retirado, y también cuando lo está pero la bitácora no lo recoge
    # (p. ej. un retiro hecho por SQL): ahí el fantasma se delata igual, solo que
    # sin quién — mejor eso que callarse por falta de un dato accesorio.
    retired_at: datetime | None = None
    retired_by: str | None = None


class HealthBucket(BaseModel):
    """Un tramo de la historia de salud. Todo opcional salvo el instante y la cuenta.

    Un bucket sin dato para una métrica vale ``None``, **nunca 0**: "no reportó RTT"
    y "reportó 0 ms" son hechos distintos y confundirlos pinta una línea plana que
    parece salud perfecta (regla de oro 7).
    """

    ts: datetime
    heartbeats: int
    mqtt_rtt_p95_ms: float | None = None
    seedlink_lag_max_s: float | None = None
    ntp_offset_abs_max_ms: float | None = None
    battery_min_pct: float | None = None


class GatewayHealthOut(BaseModel):
    """Historia de 24 h de un gabinete (T-2.38).

    ``heartbeat_completeness`` mide LATIDOS, no datos sísmicos: es la fracción de
    latidos periódicos recibidos frente a los esperados por la cadencia del edge. Se
    rotula así en la UI a propósito — la completitud de forma de onda exigiría contar
    la serie sísmica por segundo, y hoy no hay agregado que lo haga barato.
    """

    gateway_id: UUID
    buckets: list[HealthBucket] = []
    outages: int = 0
    downtime_s: float = 0.0
    last_outage_end: datetime | None = None
    heartbeat_completeness: float | None = None


class GatewayRowOut(BaseModel):
    """Fila cruda de ``gateways`` (respuesta de las mutaciones de T-1.32).

    Sin ``derived_state``: ese lo deriva ``derive_fleet_state`` del último
    ``device_health``, y un gabinete recién dado de alta todavía no tiene ninguno.
    Inventarle "OPERATIVO" sería exactamente la clase de dato falso que prohíbe la
    regla de oro 7.
    """

    gateway_id: UUID
    tenant_id: UUID
    site_id: UUID
    serial: str
    fw_version: str | None = None
    iot_thing: str | None = None
    status: str
    has_wr1: bool
    equipment: EquipmentProfile = Field(default_factory=EquipmentProfile)
    installed_at: datetime | None = None
    row_version: str


class GatewayCreate(BaseModel):
    """Alta de gabinete. NO hay ``tenant_id``: se hereda del sitio (y RLS lo valida).

    La API **no llama a AWS**. Escribe la fila con ``status='provisioned'`` e
    ``iot_thing`` nulo salvo que el operador ya conozca el thing creado por Terraform
    (``infra/scripts/provision_gateway.sh``). Sin ``iot_thing`` el gabinete no es
    sincronizable, y la consola lo dice: PENDIENTE DE APROVISIONAR. Un endpoint HTTP
    que pudiera emitir certificados X.509 sería una superficie de ataque contra la
    identidad de los gabinetes.
    """

    model_config = ConfigDict(extra="forbid")

    site_id: UUID
    serial: str = Field(min_length=1, max_length=64)
    fw_version: str | None = Field(default=None, max_length=32)
    iot_thing: str | None = Field(default=None, max_length=128)
    has_wr1: bool = True
    equipment: EquipmentProfile = Field(default_factory=EquipmentProfile)
    installed_at: datetime | None = None


class GatewayUpdate(BaseModel):
    """Edición de gabinete. ``status`` no aparece a propósito.

    ``online``/``degraded``/``offline`` los deriva el heartbeat, no el operador; y
    ``retired`` se alcanza por ``DELETE``. Dejar que un formulario escribiera "online"
    haría que la Flota Edge mintiera sobre un gabinete muerto.
    """

    model_config = ConfigDict(extra="forbid")

    site_id: UUID
    serial: str = Field(min_length=1, max_length=64)
    fw_version: str | None = Field(default=None, max_length=32)
    iot_thing: str | None = Field(default=None, max_length=128)
    has_wr1: bool = True
    equipment: EquipmentProfile = Field(default_factory=EquipmentProfile)
    installed_at: datetime | None = None
    base_row_version: str | None = None
