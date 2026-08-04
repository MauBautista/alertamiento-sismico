"""Historia de salud de la flota, 24 h (T-2.38).

La Flota Edge decía si un gabinete está bien AHORA, y nada más: un gabinete que se
cae cinco veces al día se veía idéntico a uno que nunca falló. La reincidencia es
justo lo que distingue un corte puntual de un problema de instalación.

Una sola consulta para TODA la flota — el patrón contrario al que se retiró en T-2.37,
donde la consola abría una petición por gabinete. ``device_health`` lleva ``tenant_id``
propio (no hace falta join para la RLS).

**Las caídas se derivan del silencio, no de un campo.** No existe una tabla de
"outages": lo que hay son latidos, y un hueco entre dos consecutivos mayor que
``sin_enlace_s`` ES una caída. Se calcula con ``lag()`` sobre la serie, con el MISMO
umbral que ``derive_fleet_state`` — dos definiciones distintas de "sin enlace" en dos
pantallas sería exactamente la contradicción que la regla de oro 7 evita.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

# Percentil 95 y no promedio: el RTT tiene cola larga y el promedio la esconde.
# `count(*) FILTER (reason='heartbeat')` cuenta SOLO latidos periódicos — los
# snapshots por transición llegan en ráfaga y falsearían la completitud al alza.
_BUCKETS = text(
    """
    SELECT dh.gateway_id,
           time_bucket(make_interval(mins => :bucket_min), dh.ts) AS bucket,
           count(*) FILTER (WHERE dh.reason = 'heartbeat')        AS heartbeats,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY dh.mqtt_rtt_ms)::float8
                                                                  AS mqtt_rtt_p95_ms,
           max(dh.seedlink_lag_s)::float8                         AS seedlink_lag_max_s,
           max(abs(dh.ntp_offset_ms))::float8                     AS ntp_offset_abs_max_ms,
           min(dh.battery_pct)::float8                            AS battery_min_pct
    FROM device_health dh
    WHERE dh.ts > now() - make_interval(hours => :hours)
    GROUP BY dh.gateway_id, bucket
    ORDER BY dh.gateway_id, bucket
    """
)

# Un hueco > sin_enlace_s entre dos latidos es una caída. El primer registro de la
# ventana no cuenta (su `lag` es NULL): no se sabe qué había antes y afirmarlo sería
# inventar. Tampoco se cuenta el silencio ACTUAL — ese ya lo dice `derived_state`.
_OUTAGES = text(
    """
    WITH gaps AS (
        SELECT dh.gateway_id,
               dh.ts,
               EXTRACT(EPOCH FROM (
                   dh.ts - lag(dh.ts) OVER (PARTITION BY dh.gateway_id ORDER BY dh.ts)
               ))::float8 AS gap_s
        FROM device_health dh
        WHERE dh.ts > now() - make_interval(hours => :hours)
    )
    SELECT gateway_id,
           count(*)                       AS outages,
           coalesce(sum(gap_s), 0)::float8 AS downtime_s,
           max(ts)                        AS last_outage_end
    FROM gaps
    WHERE gap_s IS NOT NULL AND gap_s > :sin_enlace_s
    GROUP BY gateway_id
    """
)


async def health_buckets(conn: AsyncConnection, *, hours: int, bucket_min: int) -> Sequence[Row]:
    """Serie agregada por gabinete y bucket (RLS por tenant sobre ``device_health``)."""
    return (await conn.execute(_BUCKETS, {"hours": hours, "bucket_min": bucket_min})).all()


async def health_outages(
    conn: AsyncConnection, *, hours: int, sin_enlace_s: float
) -> Sequence[Row]:
    """Caídas derivadas del silencio entre latidos, con el umbral de la flota."""
    return (await conn.execute(_OUTAGES, {"hours": hours, "sin_enlace_s": sin_enlace_s})).all()
