"""Pasada del dictamen automático preliminar (T-1.20 · B5).

Corre en el MISMO worker que el motor de incidentes (``python -m
takab_api.incident``), tras cada correlación: post-hoc y cloud-only, jamás en
el camino de actuación del edge. Escribe como ``takab_ingest`` (BYPASSRLS).

Reglas de emisión (inmutabilidad §9):
- Incidente sin dictamen → INSERT del preliminar (``signed_by NULL``).
- Cabeza de cadena SIN firma y status recalculado distinto (p.ej. el quórum
  corroboró después del preliminar) → corrección = fila NUEVA con
  ``supersedes_dictamen_id`` (nunca UPDATE; trigger append-only).
- Cabeza FIRMADA → intocable: el juicio del inspector nunca se corrige solo.

El ``settle_s`` retrasa el dictamen para dar tiempo a la corroboración de red
(> tope de ventana del quórum); un quórum aún más tardío queda cubierto por la
regla de corrección. Idempotente: re-run sin cambios = 0 escrituras.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import psycopg

from takab_api.dictamen.rules import EvalInput, evaluate, resolve_params
from takab_api.incident.quorum import resolve_params as resolve_quorum_params
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.dictamen")

# Advisory lock propio (≠ engine): serializa pasadas de dictamen concurrentes.
_DICTAMEN_LOCK_KEY = 0x7A4B_1120

# Candidatos: incidentes de la ventana [since, cutoff] con su pico de PGA/PGV
# (sensor estructural preferente, ventana ASIMÉTRICA pre/post — la sacudida
# SASMEX llega DESPUÉS de la alerta), sus votos de quórum y la CABEZA de su
# cadena de dictámenes (la fila que ninguna otra supersede). Los picos de
# features y el valor preexistente del incidente van SEPARADOS: de ahí sale
# ``pga_source`` (basis v2) y el backfill monotónico.
# Se lee la hypertable BASE de features: lector interno de RED (BYPASSRLS),
# igual que el engine de correlación (allowlisted en el contract-test).
_CANDIDATES_SQL = """
SELECT i.incident_id,
       i.tenant_id,
       i.site_id,
       i.event_id,
       i.severity,
       i.trigger,
       i.opened_at,
       wf.peak_pga::float8   AS feat_pga,
       wf.peak_pgv::float8   AS feat_pgv,
       i.max_pga_g::float8   AS inc_pga,
       i.max_pgv_cms::float8 AS inc_pgv,
       COALESCE(nv.node_count, 0)::int AS node_count,
       head.dictamen_id AS head_id,
       head.status      AS head_status,
       head.signed_by   AS head_signed_by
FROM incidents i
LEFT JOIN LATERAL (
  SELECT se.sensor_id
  FROM sensors se
  WHERE se.site_id = i.site_id
  ORDER BY (se.kind = 'structural') DESC, se.sensor_id
  LIMIT 1
) s ON true
LEFT JOIN LATERAL (
  SELECT MAX(wf1.pga_g) AS peak_pga, MAX(wf1.pgv_cms) AS peak_pgv
  FROM waveform_features_1s wf1
  WHERE wf1.sensor_id = s.sensor_id
    AND wf1.ts BETWEEN i.opened_at - make_interval(secs => %(pga_pre)s)
                   AND i.opened_at + make_interval(secs => %(pga_post)s)
) wf ON true
LEFT JOIN LATERAL (
  SELECT COUNT(*) AS node_count
  FROM quorum_votes qv
  WHERE qv.event_id = i.event_id AND qv.counted
) nv ON true
LEFT JOIN LATERAL (
  SELECT d.dictamen_id, d.status, d.signed_by
  FROM dictamens d
  WHERE d.incident_id = i.incident_id
    AND NOT EXISTS (
      SELECT 1 FROM dictamens d2
      WHERE d2.supersedes_dictamen_id = d.dictamen_id
    )
  ORDER BY d.created_at DESC, d.dictamen_id DESC
  LIMIT 1
) head ON true
WHERE i.opened_at >= %(since)s
  AND i.opened_at <= %(cutoff)s
ORDER BY i.opened_at, i.incident_id
"""

# rule_set activo del sitio (site preferente sobre tenant) — espejo del engine.
_RULESET_SQL = """
SELECT config
FROM rule_sets
WHERE is_active
  AND ( (scope_type = 'site'   AND scope_id = %(site)s)
     OR (scope_type = 'tenant' AND scope_id = %(tenant)s) )
ORDER BY (scope_type = 'site') DESC, version DESC
LIMIT 1
"""

_INSERT_DICTAMEN_SQL = """
INSERT INTO dictamens (tenant_id, incident_id, status, basis, supersedes_dictamen_id)
VALUES (%(tenant)s, %(incident)s, %(status)s, %(basis)s::jsonb, %(supersedes)s)
RETURNING dictamen_id
"""

_INSERT_ACTION_SQL = """
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
VALUES (%(incident)s, %(tenant)s, 'dictamen', 'system', %(payload)s::jsonb)
"""

# Backfill MONOTÓNICO de los picos medidos hacia el incidente (T-1.48): el
# ingest no puebla max_pga_g/max_pgv_cms y la consola los lee de ahí. GREATEST
# = nunca degrada (espejo de G3); el WHERE evita UPDATEs sin mejora (el trigger
# NOTIFY de 0004 dispararía frames repetidos al hub WS). Cada campo se trata
# por separado: un pico ausente JAMÁS escribe un 0 fabricado sobre NULL.
_BACKFILL_SQL = """
UPDATE incidents SET
  max_pga_g = CASE WHEN %(pga)s::float8 IS NOT NULL
                   THEN GREATEST(COALESCE(max_pga_g, 0), %(pga)s::float8)
                   ELSE max_pga_g END,
  max_pgv_cms = CASE WHEN %(pgv)s::float8 IS NOT NULL
                     THEN GREATEST(COALESCE(max_pgv_cms, 0), %(pgv)s::float8)
                     ELSE max_pgv_cms END
WHERE incident_id = %(incident)s
  AND ( (%(pga)s::float8 IS NOT NULL AND COALESCE(max_pga_g, -1) < %(pga)s::float8)
     OR (%(pgv)s::float8 IS NOT NULL AND COALESCE(max_pgv_cms, -1) < %(pgv)s::float8) )
"""


def run_dictamen_pass(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    now: datetime | None = None,
    lookback_s: float = 300.0,
    settle_s: float | None = None,
) -> list[str]:
    """Emite/corrige dictámenes preliminares de la ventana. Devuelve los
    ``dictamen_id`` insertados (vacío si nada cambió). Un COMMIT al final si
    hubo escrituras; si no, ROLLBACK (solo se leyó)."""
    now = now or datetime.now(tz=UTC)
    settle = settings.dictamen_settle_s if settle_s is None else settle_s
    since = now - timedelta(seconds=lookback_s)
    cutoff = now - timedelta(seconds=settle)
    if cutoff <= since:
        return []

    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_DICTAMEN_LOCK_KEY,))
    rows = conn.execute(
        _CANDIDATES_SQL,
        {
            "since": since,
            "cutoff": cutoff,
            "pga_pre": settings.dictamen_pga_window_pre_s,
            "pga_post": settings.dictamen_pga_window_post_s,
        },
    ).fetchall()

    created: list[str] = []
    backfilled = 0
    for row in rows:
        # Backfill de picos medidos (hecho factual, independiente del dictamen
        # e incluso de una cabeza firmada): la consola lee incident.max_pga_g.
        cur = conn.execute(
            _BACKFILL_SQL,
            {
                "incident": row["incident_id"],
                "pga": row["feat_pga"],
                "pgv": row["feat_pgv"],
            },
        )
        backfilled += cur.rowcount

        if row["head_signed_by"] is not None:
            continue  # el juicio del inspector manda
        # Pico efectivo + procedencia (basis v2): features > incidente > nada.
        if row["feat_pga"] is not None:
            pga_g, pga_source = row["feat_pga"], "features"
        elif row["inc_pga"] is not None:
            pga_g, pga_source = row["inc_pga"], "incident"
        else:
            pga_g, pga_source = None, "none"
        config_row = conn.execute(
            _RULESET_SQL, {"site": row["site_id"], "tenant": row["tenant_id"]}
        ).fetchone()
        config = config_row["config"] if config_row else None
        decision = evaluate(
            EvalInput(
                severity=row["severity"],
                pga_g=pga_g,
                node_count=row["node_count"],
                quorum_min_nodes=resolve_quorum_params(config, settings).min_nodes,
                trigger=row["trigger"],
                event_id=row["event_id"],
                pga_source=pga_source,
            ),
            resolve_params(config, settings),
        )
        if row["head_id"] is not None and row["head_status"] == decision.status:
            continue  # sin cambio material → sin fila nueva
        dictamen_id = conn.execute(
            _INSERT_DICTAMEN_SQL,
            {
                "tenant": row["tenant_id"],
                "incident": row["incident_id"],
                "status": decision.status,
                "basis": json.dumps(decision.basis),
                "supersedes": row["head_id"],
            },
        ).fetchone()["dictamen_id"]
        conn.execute(
            _INSERT_ACTION_SQL,
            {
                "incident": row["incident_id"],
                "tenant": row["tenant_id"],
                "payload": json.dumps(
                    {
                        "dictamen_id": str(dictamen_id),
                        "status": decision.status,
                        "rule_set_version": decision.basis["rule_set_version"],
                        "supersedes": str(row["head_id"]) if row["head_id"] else None,
                    }
                ),
            },
        )
        created.append(str(dictamen_id))
        logger.info(
            "dictamen %s: incidente %s → %s%s",
            dictamen_id,
            row["incident_id"],
            decision.status,
            " (corrección)" if row["head_id"] else "",
        )

    if created or backfilled:
        conn.commit()
    else:
        conn.rollback()
    return created
