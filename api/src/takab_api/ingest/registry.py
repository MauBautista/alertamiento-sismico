"""Resolución de identidad IoT: thing name → contexto de gateway (G4).

La identidad autoritativa es ``meta_principal`` (thing name del certificado
X.509, inyectado por la IoT Rule — no falsificable). Se resuelve contra
``gateways.iot_thing`` con caché TTL en memoria; el cross-check de los campos
del payload (tenant/site/gateway/station) lo hace cada handler contra el ctx.

Los sensores se consultan por ``sensors.gateway_id`` (un gateway sim atiende
estaciones de varios sitios; ``gateways.site_id`` apunta al primero del bloque).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import closing
from typing import Any

import psycopg
from psycopg.rows import dict_row

_GATEWAY_SQL = """
SELECT g.gateway_id,
       g.serial     AS gateway_serial,
       g.iot_thing,
       g.site_id,
       s.code       AS site_code,
       t.tenant_id,
       t.code       AS tenant_code
  FROM gateways g
  JOIN tenants t USING (tenant_id)
  JOIN sites   s ON s.site_id = g.site_id
 WHERE g.iot_thing = %s
"""

# Estaciones publicables del gateway (serial de sensor = station de Feature1s),
# CON el sitio propio de cada sensor: un gateway sim atiende 5 sitios y los datos
# se atribuyen al sitio del sensor, no al del gateway.
_SENSORS_SQL = """
SELECT se.sensor_id,
       se.serial,
       se.site_id,
       si.code AS site_code
  FROM sensors se
  JOIN sites si ON si.site_id = se.site_id
 WHERE se.gateway_id = %s
   AND se.serial IS NOT NULL
"""


def _default_ctx_factory(**kwargs: Any) -> Any:
    # Import diferido para no acoplar el módulo en import-time (fase B paralela).
    from takab_api.ingest.handlers import GatewayCtx, SensorRef

    kwargs["sensors"] = {serial: SensorRef(**ref) for serial, ref in kwargs["sensors"].items()}
    return GatewayCtx(**kwargs)


class Registry:
    """Caché TTL en memoria de gateways registrados, indexada por thing name.

    ``resolve`` cachea también los misses (None): protege la DB de un
    principal desconocido que publica en ráfaga; un gateway recién
    provisionado aparece a más tardar en ``ttl_s`` segundos (o tras
    ``invalidate``). Los errores operacionales de DB se propagan — el
    consumer los trata como RETRY, nunca como "unknown principal".
    """

    def __init__(
        self,
        conn_factory: Callable[[], psycopg.Connection],
        ttl_s: float = 30.0,
        *,
        ctx_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._conn_factory = conn_factory
        self._ttl_s = ttl_s
        self._ctx_factory = ctx_factory or _default_ctx_factory
        self._cache: dict[str, tuple[float, Any | None]] = {}

    def resolve(self, principal_thing_name: str) -> Any | None:
        """Contexto del gateway cuyo ``iot_thing`` = principal, o None."""
        now = time.monotonic()
        hit = self._cache.get(principal_thing_name)
        if hit is not None and hit[0] > now:
            return hit[1]
        ctx = self._lookup(principal_thing_name)
        self._cache[principal_thing_name] = (now + self._ttl_s, ctx)
        return ctx

    def invalidate(self, principal_thing_name: str | None = None) -> None:
        """Invalida una entrada (o toda la caché si no se indica principal)."""
        if principal_thing_name is None:
            self._cache.clear()
        else:
            self._cache.pop(principal_thing_name, None)

    def _lookup(self, principal: str) -> Any | None:
        with closing(self._conn_factory()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                gw = cur.execute(_GATEWAY_SQL, (principal,)).fetchone()
                if gw is None:
                    return None
                sensors = cur.execute(_SENSORS_SQL, (gw["gateway_id"],)).fetchall()

        return self._ctx_factory(
            gateway_id=gw["gateway_id"],
            gateway_serial=gw["gateway_serial"],
            iot_thing=gw["iot_thing"],
            tenant_id=gw["tenant_id"],
            tenant_code=gw["tenant_code"],
            site_id=gw["site_id"],
            site_code=gw["site_code"],
            sensors={
                row["serial"]: {
                    "sensor_id": row["sensor_id"],
                    "site_id": row["site_id"],
                    "site_code": row["site_code"],
                }
                for row in sensors
            },
        )
