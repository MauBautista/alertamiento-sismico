"""Hook de fail-open del quórum (T-1.19 · B2; seam para T-1.21).

Cuando la red confirma un evento (``seismic_events`` local_quorum), los sitios
cuya geometría queda dentro del alcance del evento pero NO reportaron detección
—porque su gateway está SIN ENLACE (offline / sin heartbeat reciente; el mismo
criterio que la flota de T-1.22)— abren un incidente sintético
``trigger='quorum'`` y emiten una señal en el canal ``takab_failopen`` para que
la cascada de notificación de T-1.21 los cubra.

La cascada de notificación NO se implementa aquí: este módulo sólo deja la fila
del incidente y la señal listas (el seam de T-1.21). Corre como ``takab_ingest``
(BYPASSRLS): ``incidents``/``seismic_events`` no tienen política de escritura.

Idempotente: el ``event_uuid`` del incidente sintético es determinista (``uuid5``
de event_id+site_id) → un re-run no duplica (UNIQUE + ON CONFLICT DO NOTHING) y
la señal sólo se emite para incidentes recién creados.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from psycopg.types.json import Jsonb

from takab_api.settings import Settings

if TYPE_CHECKING:
    import psycopg

    from takab_api.incident.quorum import QuorumParams

# Namespace fijo para derivar un event_uuid determinista de (event_id, site_id).
_FAILOPEN_NS = uuid.UUID("5f9d1e2a-19a1-4b7c-9c3d-7a1e6b2f0c44")

# Canal de la señal para T-1.21 (cascada de notificación de fail-open).
FAILOPEN_CHANNEL = "takab_failopen"

# Tope DURO del radio de fail-open (m). El alcance sale de la config del tenant
# ancla (v_P · max_window); sin cota, un tenant podría inyectar incidentes
# sintéticos en sitios de OTROS tenants a escala nacional. Se acota al mayor radio
# físicamente sensato de una red metropolitana (~400 km), defensa en profundidad
# frente a un v_p_km_s/max_window_s abusivos aunque la ventana ya venga acotada.
_MAX_REACH_M = 400_000.0

# Severidad del incidente sintético: un sitio sin enlace alcanzado por un evento
# de red confirmado no puede autoprotegerse → 'warning' (no 'critical': la
# actuación local sigue siendo autoritativa donde sí hay enlace).
_SYNTHETIC_SEVERITY = "warning"

# Sitios en rango, sin enlace, que no reportaron ni tienen ya incidente del evento.
# "Sin enlace" = tiene gateway no retirado y NINGÚN gateway con enlace (online y con
# heartbeat fresco), alineado con schemas.fleet.derive_fleet_state (SIN ENLACE).
_CANDIDATES_SQL = """
SELECT s.site_id, s.tenant_id
FROM sites s
WHERE ST_DWithin(
        s.geom,
        ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
        %(reach_m)s
      )
  AND NOT (s.site_id = ANY(%(members)s::uuid[]))
  AND EXISTS (
        SELECT 1 FROM gateways g
        WHERE g.site_id = s.site_id AND g.status <> 'retired'
      )
  AND NOT EXISTS (
        SELECT 1 FROM gateways g
        LEFT JOIN LATERAL (
          SELECT dh.ts FROM device_health dh
          WHERE dh.gateway_id = g.gateway_id
          ORDER BY dh.ts DESC LIMIT 1
        ) h ON true
        WHERE g.site_id = s.site_id
          AND g.status NOT IN ('offline', 'retired')
          AND h.ts IS NOT NULL
          AND EXTRACT(EPOCH FROM (%(now)s::timestamptz - h.ts)) <= %(sin_enlace_s)s
      )
  AND NOT EXISTS (
        SELECT 1 FROM incidents i
        WHERE i.event_id = %(event_id)s AND i.site_id = s.site_id
      )
ORDER BY s.site_id
"""

_INSERT_SQL = """
INSERT INTO incidents
  (event_uuid, tenant_id, site_id, event_id, opened_at, severity, state, trigger)
VALUES (%(event_uuid)s, %(tenant_id)s, %(site_id)s, %(event_id)s, %(now)s,
        %(severity)s, 'open', 'quorum')
ON CONFLICT (event_uuid) DO NOTHING
RETURNING incident_id
"""

_ACTION_SQL = """
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
VALUES (%(id)s, %(tenant)s, 'fail_open', 'system', %(payload)s)
"""


def handle_fail_open(
    conn: psycopg.Connection,
    event_id: str,
    member_site_ids: list[str],
    epicenter_lonlat: tuple[float, float],
    params: QuorumParams,
    *,
    now: datetime,
) -> list[str]:
    """Abre incidentes sintéticos para sitios SIN ENLACE alcanzados por el evento.

    - ``conn``: conexión psycopg sync como ``takab_ingest`` (BYPASSRLS).
    - ``event_id``: ``seismic_events.event_id`` recién creado por el quórum.
    - ``member_site_ids``: sitios que SÍ reportaron detección (se excluyen).
    - ``epicenter_lonlat``: (lon, lat) del centroide aproximado del evento.
    - ``params``: ``QuorumParams`` resueltos; el alcance = v_P · max_window (km).
    - ``now``: instante de referencia (opened_at + edad del heartbeat; inyectable).

    Devuelve los ``incident_id`` (str) de los incidentes sintéticos recién
    creados (vacío si ningún sitio sin enlace quedó en rango). Idempotente.
    """
    lon, lat = epicenter_lonlat
    reach_m = min(params.v_p_km_s * params.max_window_s * 1000.0, _MAX_REACH_M)
    sin_enlace_s = Settings().sin_enlace_min * 60.0
    members = [str(s) for s in member_site_ids]

    candidates = conn.execute(
        _CANDIDATES_SQL,
        {
            "lon": lon,
            "lat": lat,
            "reach_m": reach_m,
            "members": members,
            "now": now,
            "sin_enlace_s": sin_enlace_s,
            "event_id": event_id,
        },
    ).fetchall()

    created: list[str] = []
    for row in candidates:
        site_id = str(row["site_id"])
        tenant_id = str(row["tenant_id"])
        event_uuid = uuid.uuid5(_FAILOPEN_NS, f"{event_id}:{site_id}")
        inserted = conn.execute(
            _INSERT_SQL,
            {
                "event_uuid": event_uuid,
                "tenant_id": tenant_id,
                "site_id": site_id,
                "event_id": event_id,
                "now": now,
                "severity": _SYNTHETIC_SEVERITY,
            },
        ).fetchone()
        if inserted is None:
            continue  # ya existía (re-run) → idempotente: sin acción ni señal
        incident_id = str(inserted["incident_id"])
        conn.execute(
            _ACTION_SQL,
            {
                "id": incident_id,
                "tenant": tenant_id,
                "payload": Jsonb({"event_id": event_id, "reason": "sin_enlace"}),
            },
        )
        _emit_failopen_signal(conn, event_id, site_id, incident_id)
        created.append(incident_id)
    return created


def _emit_failopen_signal(
    conn: psycopg.Connection, event_id: str, site_id: str, incident_id: str
) -> None:
    """Señal de fail-open para T-1.21 en ``takab_failopen`` (payload mínimo).

    La cascada de notificación real (destinatarios, canales) es T-1.21; aquí sólo
    se publica la invalidación con los ids. Se entrega al COMMIT de la transacción.
    """
    payload = json.dumps({"event_id": event_id, "site_id": site_id, "incident_id": incident_id})
    conn.execute("SELECT pg_notify(%s, %s)", (FAILOPEN_CHANNEL, payload))
