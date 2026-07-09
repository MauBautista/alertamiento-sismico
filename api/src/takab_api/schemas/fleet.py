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

from pydantic import BaseModel

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
    """
    if age_s is None or age_s > sin_enlace_s:
        return SIN_ENLACE
    degraded = (
        power_status == "battery"
        or (battery_pct is not None and battery_pct < battery_min_pct)
        or (cert_days_remaining is not None and cert_days_remaining < cert_min_days)
        or (mqtt_rtt_ms is not None and mqtt_rtt_ms > mqtt_rtt_max_ms)
        or (seedlink_lag_s is not None and seedlink_lag_s > seedlink_lag_max_s)
        or (ntp_offset_ms is not None and abs(ntp_offset_ms) > ntp_offset_max_ms)
    )
    return DEGRADADO if degraded else OPERATIVO


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

    - ``in_sync``: el payload publicado coincide con ``config.edge`` del rule_set
      activo. Es la negación del predicado de publicación del worker.
    - ``has_edge_config``: el rule_set activo trae bloque ``edge``. Si es falso el
      worker no publicará nunca — pintar PENDIENTE para siempre sería mentir.
    - ``is_syncable``: gateway no retirado y con ``iot_thing`` (el worker lo excluye
      en caso contrario).
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


class GatewayOut(BaseModel):
    """Gateway del tenant + estado derivado del último ``device_health``."""

    gateway_id: UUID
    site_id: UUID
    serial: str
    fw_version: str | None = None
    iot_thing: str | None = None
    status: str
    has_wr1: bool
    installed_at: datetime | None = None
    derived_state: str
    last_heartbeat_ts: datetime | None = None
    power_status: str | None = None
    battery_pct: float | None = None
    cert_days_remaining: int | None = None
    mqtt_rtt_ms: float | None = None
    seedlink_lag_s: float | None = None
    ntp_offset_ms: float | None = None
