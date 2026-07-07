"""Motor de correlación de red del quórum (T-1.19 · B1).

Worker CLOUD-ONLY y post-hoc: junta incidentes NO corroborados (``event_id IS
NULL``) que asocian entre sí por la ventana distance-aware (blueprint §4.5),
y cuando alcanzan el quórum crea UN ``seismic_events`` (source 'local_quorum')
+ ``quorum_votes`` por miembro + linkea los ``incidents``. La matemática de
asociación es determinista (``incident.quorum``); aquí sólo se le inyecta la
distancia real con PostGIS y la persistencia.

Este motor JAMÁS bloquea ni condiciona la actuación local del edge: su caída o
lentitud no afecta la ingesta de acks ni el disparo de actuadores (sólo LEE y
escribe tablas de red). Idempotente: el guard ``event_id IS NULL`` + la PK de
``quorum_votes`` + el ``ON CONFLICT`` evitan duplicados en cada re-run. El UPDATE
a ``incidents.event_id`` re-dispara ``takab_live`` (0004), pero esos incidentes
ya quedan corroborados → se excluyen en el siguiente wake (bucle acotado).

Escribe como ``takab_ingest`` (BYPASSRLS): ``seismic_events``/``quorum_votes`` no
tienen política de escritura (sólo BYPASSRLS escribe).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import psycopg

from takab_api.db import pool
from takab_api.incident.fail_open import handle_fail_open
from takab_api.incident.quorum import (
    ClusterResult,
    Detection,
    QuorumParams,
    correlate,
    resolve_params,
)

if TYPE_CHECKING:
    from takab_api.settings import Settings

logger = logging.getLogger("takab_api.incident")

_RECONNECT_BACKOFF_S = 1.0
# Ventana ±s alrededor de opened_at donde se busca el pico de PGA en features.
_PGA_WINDOW_S = 5.0
# Clave del advisory lock (bigint) que serializa la correlación entre instancias
# co-locadas del engine: sólo una corre run_correlation a la vez, así dos worker
# no crean dos seismic_events del mismo sismo con conjuntos de candidatos distintos.
_CORRELATION_LOCK_KEY = 0x7A4B_1119

# Candidatos: TODAS las detecciones no corroboradas en la ventana [since, now]
# (con tope superior en ``now``: no se correlacionan detecciones futuras respecto
# al instante de la pasada; entran en el siguiente ciclo). Puede haber más de una
# por sitio; ``run_correlation`` elige la más cercana al ancla para que un disparo
# espurio viejo no enmascare la real (#3),
# con geom del sitio, su sensor (estructural preferente) y el pico de PGA de
# waveform_features_1s alrededor de opened_at. Sitios sin sensor quedan fuera (no
# podrían votar). El orden temporal lo re-deriva ``correlate``.
# Se lee la hypertable BASE (no la vista `_secure`): el engine es un lector interno
# de RED (BYPASSRLS), como la ingesta; la vista segura corre con el contexto RLS de
# su owner y no sirve para una lectura cross-tenant (ver test_waveform_view _ALLOW).
_CANDIDATES_SQL = """
SELECT i.incident_id,
       i.site_id,
       i.tenant_id,
       s.sensor_id,
       i.opened_at,
       ST_X(si.geom::geometry) AS lon,
       ST_Y(si.geom::geometry) AS lat,
       COALESCE(wf.peak_pga, i.max_pga_g, 0.0)::float8 AS pga_g
FROM incidents i
JOIN sites si ON si.site_id = i.site_id
JOIN LATERAL (
  SELECT se.sensor_id
  FROM sensors se
  WHERE se.site_id = i.site_id
  ORDER BY (se.kind = 'structural') DESC, se.sensor_id
  LIMIT 1
) s ON true
LEFT JOIN LATERAL (
  SELECT MAX(wf1.pga_g) AS peak_pga
  FROM waveform_features_1s wf1
  WHERE wf1.sensor_id = s.sensor_id
    AND wf1.ts BETWEEN i.opened_at - make_interval(secs => %(pga_win)s)
                   AND i.opened_at + make_interval(secs => %(pga_win)s)
) wf ON true
WHERE i.event_id IS NULL
  AND i.state <> 'closed'
  AND i.opened_at >= %(since)s
  AND i.opened_at <= %(now)s
ORDER BY i.opened_at, i.incident_id
"""

# Params del quórum: rule_set activo del sitio (scope 'site' preferente sobre
# 'tenant'); si no hay, resolve_params cae a los defaults de Settings.
_RULESET_SQL = """
SELECT config
FROM rule_sets
WHERE is_active
  AND ( (scope_type = 'site'   AND scope_id = %(site)s)
     OR (scope_type = 'tenant' AND scope_id = %(tenant)s) )
ORDER BY (scope_type = 'site') DESC, version DESC
LIMIT 1
"""

# Distancia geodésica en km entre dos puntos (geography → metros / 1000).
_DIST_SQL = """
SELECT ST_Distance(
         ST_SetSRID(ST_MakePoint(%(alon)s, %(alat)s), 4326)::geography,
         ST_SetSRID(ST_MakePoint(%(blon)s, %(blat)s), 4326)::geography
       ) / 1000.0 AS d
"""

# Epicentro aproximado (NO autoritativo): centroide de los sitios participantes.
_INSERT_EVENT_SQL = """
INSERT INTO seismic_events (event_id, source, epicenter, magnitude, detected_at, meta)
SELECT %(event_id)s, 'local_quorum',
       ST_Centroid(ST_Collect(geom::geometry))::geography,
       NULL, %(detected_at)s, %(meta)s::jsonb
FROM sites WHERE site_id = ANY(%(sites)s::uuid[])
ON CONFLICT (event_id) DO NOTHING
"""

_EPICENTER_SQL = """
SELECT ST_X(ST_Centroid(ST_Collect(geom::geometry))) AS lon,
       ST_Y(ST_Centroid(ST_Collect(geom::geometry))) AS lat
FROM sites WHERE site_id = ANY(%(sites)s::uuid[])
"""

_INSERT_VOTE_SQL = """
INSERT INTO quorum_votes (event_id, sensor_id, detected_at, pga_g, delta_s, counted)
VALUES (%(event_id)s, %(sensor_id)s::uuid, %(detected_at)s, %(pga_g)s, %(delta_s)s, true)
ON CONFLICT (event_id, sensor_id) DO NOTHING
"""

_LINK_INCIDENTS_SQL = """
UPDATE incidents SET event_id = %(event_id)s
WHERE incident_id = ANY(%(ids)s::uuid[]) AND event_id IS NULL
"""


class IncidentEngine:
    """Correlación de red del quórum. Bucle LISTEN ``takab_live`` (filtra
    ``t='incident'``) + poll periódico de respaldo; cada wake ⇒ ``run_correlation``.

    Firma:
      ``IncidentEngine(conn_factory, settings, *, poll_s=5.0, lookback_s=300.0)``
      - ``conn_factory``: fábrica de conexiones psycopg sync (como ``takab_ingest``),
        p.ej. ``functools.partial(pool.connect, settings.database_url)``.
      - ``poll_s``: cadencia del poll de respaldo (por si se pierde un NOTIFY).
      - ``lookback_s``: ventana hacia atrás de incidentes candidatos. DEBE exceder
        el spread de arribos inter-ciudad (~17 s a 110 km) + latencia de proceso.
    """

    def __init__(
        self,
        conn_factory: Callable[[], psycopg.Connection],
        settings: Settings,
        *,
        poll_s: float = 5.0,
        lookback_s: float = 300.0,
    ) -> None:
        self._conn_factory = conn_factory
        self._settings = settings
        self._poll_s = poll_s
        self._lookback_s = lookback_s
        self._stop = threading.Event()

    # ------------------------------------------------------------------ loop

    def run(self) -> None:
        """Escucha ``takab_live`` y correla hasta ``stop()``. Reconecta con backoff
        indefinidamente: un corte de DB prolongado (failover/reboot de RDS de
        minutos, más largo que el presupuesto de ``with_retry``) NO mata al worker
        —la conexión se (re)establece DENTRO del bucle, así que un fallo al
        reconectar simplemente reintenta en la siguiente vuelta—. La ingesta y la
        actuación local del edge corren en procesos aparte y nunca dependen de esto."""
        listen_conn: psycopg.Connection | None = None
        work_conn: psycopg.Connection | None = None
        try:
            while not self._stop.is_set():
                try:
                    if listen_conn is None or listen_conn.closed:
                        listen_conn = self._connect_listen()
                    self._drain_notifies(listen_conn)
                    if self._stop.is_set():
                        break
                    work_conn = self._ensure_work(work_conn)
                    self.run_correlation(work_conn)
                    self._dictamen_pass(work_conn)
                except psycopg.OperationalError:
                    logger.exception("engine: DB no disponible; reconecta")
                    self._safe_close(work_conn)
                    self._safe_close(listen_conn)
                    work_conn = None
                    listen_conn = None
                    self._stop.wait(_RECONNECT_BACKOFF_S)
                except Exception:
                    logger.exception("engine: error inesperado en el ciclo")
                    if work_conn is not None:
                        try:
                            work_conn.rollback()
                        except psycopg.Error:
                            self._safe_close(work_conn)
                            work_conn = None
                    self._stop.wait(1.0)
        finally:
            self._safe_close(listen_conn)
            self._safe_close(work_conn)

    def stop(self) -> None:
        """Solicita cierre gracioso (idempotente, seguro desde señales)."""
        self._stop.set()

    def _drain_notifies(self, listen_conn: psycopg.Connection) -> None:
        """Consume los NOTIFY de ``takab_live`` hasta ``poll_s`` (o hasta el primero).

        Correlacionamos tras cada retorno (haya llegado un notify o no) → el poll
        de respaldo cubre un NOTIFY perdido. Sólo se filtra ``t='incident'`` para
        el log; el trabajo real lo decide ``run_correlation`` por idempotencia.
        """
        for note in listen_conn.notifies(timeout=self._poll_s, stop_after=1):
            try:
                payload = json.loads(note.payload)
            except (ValueError, TypeError):
                continue
            if isinstance(payload, dict) and payload.get("t") == "incident":
                logger.debug("engine: notify incident tenant=%s", payload.get("tenant"))

    def _dictamen_pass(self, work_conn: psycopg.Connection) -> None:
        """Dictamen preliminar (T-1.20 · B5): post-hoc, tras dar tiempo (settle)
        a que la correlación corrobore. Comparte el manejo de errores/reconexión
        del bucle. Import perezoso: dictamen.service usa incident.quorum
        (ciclo a nivel de módulo)."""
        from takab_api.dictamen.service import run_dictamen_pass

        run_dictamen_pass(work_conn, self._settings, lookback_s=self._lookback_s)

    # ----------------------------------------------------------- correlación

    def run_correlation(
        self, conn: psycopg.Connection, *, now: datetime | None = None
    ) -> list[str]:
        """Correla los incidentes no corroborados y crea/linkea eventos de red.

        Devuelve los ``event_id`` creados en esta pasada (vacío si nada asoció).
        Un único ``COMMIT`` al final si hubo escrituras; si no, ``ROLLBACK`` (sólo
        se leyó). El bucle interno permite MÚLTIPLES eventos disjuntos en la misma
        ventana: crea un cúmulo, retira sus sitios y re-correla el resto. Si el
        ancla más temprana NO forma cúmulo (falso positivo aislado o umbral estricto
        del tenant ancla) se RETIRA sólo esa ancla y se reintenta con la siguiente,
        de modo que un disparo espurio previo no suprima un quórum sísmico real.
        """
        now = now or datetime.now(tz=UTC)
        since = now - timedelta(seconds=self._lookback_s)
        # Serializa las instancias concurrentes del engine antes de leer candidatos:
        # el lock se libera con el commit/rollback de esta misma transacción (#4).
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_CORRELATION_LOCK_KEY,))
        rows = conn.execute(
            _CANDIDATES_SQL, {"since": since, "now": now, "pga_win": _PGA_WINDOW_S}
        ).fetchall()

        # Puede haber MÁS de una detección no corroborada por sitio en la ventana;
        # se conservan todas y la elección por-sitio la hace el bucle (la más cercana
        # al ancla), para que un disparo espurio viejo no enmascare la real (#3).
        det_row: dict[int, dict] = {}
        remaining: list[Detection] = []
        for r in rows:
            det = self._detection(r)
            det_row[id(det)] = r
            remaining.append(det)
        dist_fn = self._make_dist_fn(conn)
        created: list[str] = []

        while True:
            reps = self._per_site_reps(remaining)
            if len(reps) < 2:
                break
            anchor = min(reps, key=lambda d: (d.detected_at, d.site_id, d.sensor_id))
            params = self._resolve_params(conn, det_row[id(anchor)])
            cluster = correlate(reps, dist_fn, params)
            if cluster is None:
                remaining = [d for d in remaining if d is not anchor]
                continue
            event_id = self._persist_cluster(conn, cluster, det_row, params, now=now)
            created.append(event_id)
            member_sites = {m.site_id for m in cluster.members}
            remaining = [d for d in remaining if d.site_id not in member_sites]

        if created:
            conn.commit()
        else:
            conn.rollback()  # cerrar la txn de sólo-lectura sin dejar snapshot abierto
        return created

    @staticmethod
    def _per_site_reps(remaining: list[Detection]) -> list[Detection]:
        """Una detección por sitio: la más temprana (≡ la más cercana al ancla, que
        es el mínimo global de tiempo). Así el ancla nunca es un disparo espurio
        viejo cuando el mismo sitio tiene una detección real posterior (#3)."""
        reps: dict[str, Detection] = {}
        for d in remaining:
            cur = reps.get(d.site_id)
            if cur is None or (d.detected_at, d.sensor_id) < (cur.detected_at, cur.sensor_id):
                reps[d.site_id] = d
        return list(reps.values())

    @staticmethod
    def _detection(row: dict) -> Detection:
        return Detection(
            site_id=str(row["site_id"]),
            sensor_id=str(row["sensor_id"]),
            detected_at=row["opened_at"],
            pga_g=float(row["pga_g"]),
            lon=float(row["lon"]),
            lat=float(row["lat"]),
        )

    def _resolve_params(self, conn: psycopg.Connection, row: dict) -> QuorumParams:
        found = conn.execute(
            _RULESET_SQL, {"site": row["site_id"], "tenant": row["tenant_id"]}
        ).fetchone()
        config = found["config"] if found else None
        return resolve_params(config, self._settings)

    @staticmethod
    def _make_dist_fn(conn: psycopg.Connection) -> Callable[[Detection, Detection], float]:
        def dist_km(a: Detection, b: Detection) -> float:
            row = conn.execute(
                _DIST_SQL, {"alon": a.lon, "alat": a.lat, "blon": b.lon, "blat": b.lat}
            ).fetchone()
            return float(row["d"])

        return dist_km

    def _persist_cluster(
        self,
        conn: psycopg.Connection,
        cluster: ClusterResult,
        det_row: dict[int, dict],
        params: QuorumParams,
        *,
        now: datetime,
    ) -> str:
        anchor = cluster.anchor
        ts = anchor.detected_at
        digest = hashlib.sha1(f"{anchor.site_id}|{ts.isoformat()}".encode()).hexdigest()
        event_id = f"EVT-{ts.astimezone(UTC):%Y%m%d-%H%M%S}-{digest[:6]}"
        member_sites = [m.site_id for m in cluster.members]

        conn.execute(
            _INSERT_EVENT_SQL,
            {
                "event_id": event_id,
                "detected_at": ts,
                "sites": member_sites,
                "meta": json.dumps({"sites": member_sites, "node_count": len(member_sites)}),
            },
        )
        for vote in cluster.votes:
            conn.execute(
                _INSERT_VOTE_SQL,
                {
                    "event_id": event_id,
                    "sensor_id": vote.detection.sensor_id,
                    "detected_at": vote.detection.detected_at,
                    "pga_g": vote.detection.pga_g,
                    "delta_s": vote.delta_s,
                },
            )
        # El incidente de cada miembro es el de SU detección elegida (la más cercana
        # al ancla), no una fila arbitraria del sitio (#3).
        incident_ids = [str(det_row[id(m)]["incident_id"]) for m in cluster.members]
        conn.execute(_LINK_INCIDENTS_SQL, {"event_id": event_id, "ids": incident_ids})

        epi = conn.execute(_EPICENTER_SQL, {"sites": member_sites}).fetchone()
        epicenter = (float(epi["lon"]), float(epi["lat"]))
        # Fail-open (B2, seam T-1.21): sitios SIN ENLACE en rango → incidente
        # sintético en la MISMA txn (un fallo aquí revierte el cúmulo entero).
        handle_fail_open(conn, event_id, member_sites, epicenter, params, now=now)
        return event_id

    # ---------------------------------------------------------------- conns

    def _connect_listen(self) -> psycopg.Connection:
        conn = pool.with_retry(self._conn_factory)
        conn.autocommit = True
        conn.execute("LISTEN takab_live")
        return conn

    def _ensure_work(self, work_conn: psycopg.Connection | None) -> psycopg.Connection:
        if work_conn is None or work_conn.closed:
            return pool.with_retry(self._conn_factory)
        return work_conn

    @staticmethod
    def _safe_close(conn: psycopg.Connection | None) -> None:
        if conn is not None:
            try:
                conn.close()
            except psycopg.Error:
                pass
