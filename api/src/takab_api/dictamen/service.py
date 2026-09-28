"""Pasada del dictamen automático preliminar (T-1.20 · B5).

Corre en el MISMO worker que el motor de incidentes (``python -m
takab_api.incident``), tras cada correlación: post-hoc y cloud-only, jamás en
el camino de actuación del edge. Escribe como ``takab_ingest`` (BYPASSRLS).

Reglas de emisión [T-9.30/T-9.31 · D-43 · regla ``dictamen-v2``] (inmutabilidad §9:
toda fila es un INSERT con ``supersedes_dictamen_id``; nunca UPDATE):
- Incidente sin dictamen → preliminar v2 sin firmar, con su ``band``.
- La prudencia SUBE sola: banda recalculada más alta que la cabeza (firmada o no,
  de cualquier firmante) → fila nueva sin firmar que la supersede.
- Sólo BAJA con firma: el worker jamás inserta una banda más baja que la cabeza.
- [F3·r3] La firma HUMANA no se deshace sola: con la cabeza firmada por una persona
  (``inspector``/``confirmation``) sólo suben los daños que no vio (creados después
  de su firma; en una confirmación, además, cualquier daño ROJO). La PGA ya la vio.
- VERDE sin firmar + tier ``normal`` ≥ ``dictamen_verde_gracia_s`` + sin daños +
  sin escalada pendiente (``dictamen_request`` sin firma de INSPECTOR posterior) →
  VERDE firmado por el SISTEMA (``SYSTEM_DICTAMEN_SIGNER_UUID``, ``signature_kind
  = 'system'``).
- Re-evaluación: durante ``dictamen_reevaluacion_s`` (72 h) desde la apertura, un
  incidente —abierto o CERRADO— con un VERDE sin firmar o con CUALQUIER reporte de
  daño vuelve a ser candidato; los daños se leen DENTRO del lock.
- Cabeza ÚNICA (``created_at DESC, dictamen_id DESC``) leída DESPUÉS de tomar el
  incidente ``FOR UPDATE``: la firma y la confirmación serializan con el worker.

El ``settle_s`` retrasa el dictamen para dar tiempo a la corroboración de red.
Idempotente: re-run sin cambios = 0 escrituras. Determinista: nada de IA (regla de
oro 1); cada banda lleva sus motivos en el ``basis``.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import psycopg

from takab_api.dictamen.rules import (
    BANDA_STATUS,
    ORDEN_BANDA,
    Decision,
    EvalInputV2,
    banda_de,
    banda_por_danos,
    evaluate_v2,
    resolve_params_v2,
)
from takab_api.dictamen.sistema import (
    FIRMA_DE_INSPECTOR_SQL,
    FIRMA_HUMANA_SQL,
    SYSTEM_DICTAMEN_SIGNER_UUID,
    danos_no_vistos,
)
from takab_api.felt import CLAVE_UMBRAL_CONGELADO, umbral_congelado, umbral_de_fila
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
       COALESCE(se.activos, 0)::int     AS active_sensors,
       COALESCE(se.sin_calibrar, 0)::int AS uncalibrated_sensors,
       COALESCE(nv.node_count, 0)::int AS node_count,
       tr.new_tier AS last_tier,
       tr.ts       AS last_tier_ts
FROM incidents i
-- [T-9.30 · D-43] TODOS los sensores ACTIVOS del sitio: un retirado ni aporta
-- PGA ni impide el VERDE. «Calibrado» = `calibration_source` no vacío.
LEFT JOIN LATERAL (
  SELECT COUNT(*) AS activos,
         COUNT(*) FILTER (WHERE NULLIF(btrim(s.calibration_source), '') IS NULL) AS sin_calibrar
  FROM sensors s
  WHERE s.site_id = i.site_id AND s.status = 'active'
) se ON true
LEFT JOIN LATERAL (
  SELECT MAX(wf1.pga_g) AS peak_pga, MAX(wf1.pgv_cms) AS peak_pgv
  FROM waveform_features_1s wf1
  JOIN sensors s ON s.sensor_id = wf1.sensor_id
  WHERE s.site_id = i.site_id
    AND s.status = 'active'
    AND wf1.ts BETWEEN i.opened_at - make_interval(secs => %(pga_pre)s)
                   AND i.opened_at + make_interval(secs => %(pga_post)s)
) wf ON true
LEFT JOIN LATERAL (
  SELECT COUNT(*) AS node_count
  FROM quorum_votes qv
  WHERE qv.event_id = i.event_id AND qv.counted
) nv ON true
LEFT JOIN LATERAL (
  SELECT r.new_tier, r.ts
  FROM rule_evaluations r
  WHERE r.site_id = i.site_id
  ORDER BY r.ts DESC
  LIMIT 1
) tr ON true
-- Cabeza ÚNICA de la cadena (la misma en router, app y certificado).
LEFT JOIN LATERAL (
  SELECT d.signed_by, d.band, d.status, d.created_at
  FROM dictamens d
  WHERE d.incident_id = i.incident_id
  ORDER BY d.created_at DESC, d.dictamen_id DESC
  LIMIT 1
) head ON true
WHERE i.opened_at <= %(cutoff)s
  AND ( i.opened_at >= %(since)s
     -- Re-evaluación (72 h, abierto o CERRADO): un VERDE sin firmar que espera la
     -- gracia, o CUALQUIER reporte de daño. [F3·r2] No se compara con la cabeza: una
     -- confirmación o una firma posterior al reporte lo tapaba y el daño no se
     -- evaluaba nunca. Se evalúa con TODOS los daños y sólo se inserta si la banda
     -- resultante SUBE sobre la cabeza (idempotente: la misma evidencia no sube dos
     -- veces).
     OR ( i.opened_at >= %(reeval_since)s
          AND ( (head.signed_by IS NULL
                 AND COALESCE(head.band,
                              CASE head.status WHEN 'normal_operation' THEN 'verde' END)
                     = 'verde')
             OR EXISTS (SELECT 1 FROM damage_reports d
                         WHERE d.incident_id = i.incident_id) ) ) )
ORDER BY i.opened_at, i.incident_id
"""

# [T-9.30] Cabeza ÚNICA: `created_at DESC, dictamen_id DESC`. Se lee DESPUÉS de
# tomar el incidente FOR UPDATE, dentro de la misma transacción: lo que vio la
# consulta de candidatos puede haber cambiado (una firma en paralelo).
_LOCK_INCIDENT_SQL = "SELECT 1 FROM incidents WHERE incident_id = %(incident)s FOR UPDATE"

# [F3·r2] Los reportes de daño se leen DENTRO del lock del incidente (tras el
# ``FOR UPDATE``): un reporte que entra entre la selección de candidatos y el lock
# (toma FOR KEY SHARE del incidente por la FK, así que el lock ESPERA a que se
# confirme) tiene que decidir el VERDE del sistema y la subida de banda.
# [F3·r3] Una fila POR REPORTE, con su hora: sobre una cabeza firmada por una
# persona sólo cuentan los que esa persona no vio (``sistema.danos_no_vistos``).
_DAMAGE_SQL = """
SELECT d.report_id, d.created_at,
       COALESCE(array_agg(DISTINCT c.value->>'key')
                  FILTER (WHERE c.value->>'key' IS NOT NULL), ARRAY[]::text[]) AS claves
FROM damage_reports d
LEFT JOIN LATERAL jsonb_array_elements(
  CASE WHEN jsonb_typeof(d.categories) = 'array' THEN d.categories ELSE '[]'::jsonb END
) c ON true
WHERE d.incident_id = %(incident)s
GROUP BY d.report_id, d.created_at
"""

# [F3·r3 · D-43] Escalada PENDIENTE: una solicitud de dictamen técnico que ninguna
# firma de INSPECTOR posterior atendió. Mientras exista, el sistema NO firma el
# VERDE: la brigada pidió que viniera una persona. Mismo predicado que el 409 de
# `incidents_ops` y el correo del orquestador (`FIRMA_DE_INSPECTOR_SQL`).
_PENDING_REQUEST_SQL = f"""
SELECT 1 FROM incident_actions a
WHERE a.incident_id = %(incident)s AND a.kind = 'dictamen_request'
  AND NOT EXISTS (
    SELECT 1 FROM dictamens d
    WHERE d.incident_id = a.incident_id AND {FIRMA_DE_INSPECTOR_SQL}
      AND d.created_at > a.ts
  )
LIMIT 1
"""

# [D-49 · R4] La ÚLTIMA firma HUMANA de la cadena (no necesariamente la cabeza: una
# subida sin firmar puede estar encima). Tras ella sólo sube lo que no vio.
_ULTIMA_FIRMA_HUMANA_SQL = f"""
SELECT d.dictamen_id, d.signature_kind, d.created_at, d.basis
FROM dictamens d
WHERE d.incident_id = %(incident)s AND {FIRMA_HUMANA_SQL}
ORDER BY d.created_at DESC, d.dictamen_id DESC
LIMIT 1
"""

_HEAD_SQL = """
SELECT d.dictamen_id, d.status, d.band, d.signed_by, d.signature_kind,
       d.created_at, d.basis
FROM dictamens d
WHERE d.incident_id = %(incident)s
ORDER BY d.created_at DESC, d.dictamen_id DESC
LIMIT 1
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

# [T-7.37] Umbrales del INMUEBLE vigentes en la apertura del incidente, para
# congelarlos en el `basis`. Es el espejo sync de
# `queries/forensics._THRESHOLDS_IN_FORCE` —aquél es SQLAlchemy async y éste
# psycopg— y por eso `test_umbral_congelado.py` comprueba que los dos eligen la
# MISMA fila: dos consultas del mismo hecho acaban discrepando solas.
#
# No se reusa `_RULESET_SQL`: aquél toma el rule_set ACTIVO de hoy para los
# parámetros del dictamen; éste toma el que REGÍA en la apertura y exige que
# declare umbrales (`config->'edge' ? 'thresholds'`). Son preguntas distintas y
# pueden dar filas distintas.
_UMBRALES_SQL = """
SELECT version,
       (config->'edge'->'thresholds'->>'pga_watch_g')::float   AS pga_watch_g,
       (config->'edge'->'thresholds'->>'pga_trip_g')::float    AS pga_trip_g,
       (config->'edge'->'thresholds'->>'pgv_watch_cms')::float AS pgv_watch_cms,
       (config->'edge'->'thresholds'->>'pgv_trip_cms')::float  AS pgv_trip_cms
  FROM rule_sets
 WHERE created_at <= %(at)s
   AND config->'edge' ? 'thresholds'
   AND ( (scope_type = 'site'   AND scope_id = %(site)s)
      OR (scope_type = 'tenant' AND scope_id = %(tenant)s) )
 ORDER BY (scope_type = 'site') DESC, created_at DESC, version DESC
 LIMIT 1
"""

# `created_at` explícito y MONÓTONO: `now()` es el inicio de la transacción, que
# puede ser ANTERIOR a una firma que se confirmó mientras esperábamos el lock, y la
# fila nueva quedaría DETRÁS de la cabeza que supersede.
_INSERT_DICTAMEN_SQL = """
INSERT INTO dictamens (tenant_id, incident_id, status, basis, supersedes_dictamen_id,
                       band, signed_by, signature_kind, created_at)
VALUES (%(tenant)s, %(incident)s, %(status)s, %(basis)s::jsonb, %(supersedes)s,
        %(band)s, %(signed_by)s, %(signature_kind)s,
        GREATEST(clock_timestamp(),
                 COALESCE(%(head_created_at)s::timestamptz + interval '1 microsecond',
                          '-infinity'::timestamptz)))
RETURNING dictamen_id
"""

_INSERT_ACTION_SQL = """
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
VALUES (%(incident)s, %(tenant)s, 'dictamen', 'system', %(payload)s::jsonb)
"""

# [T-9.33 · D-43] AMARILLO sin firmar ⇒ se pide confirmación a la brigada. La
# acción ancla el push DICTAMEN_CONFIRM del orquestador (`uq_notification_jobs_action`).
# Idempotente por incidente+dictamen: el NOT EXISTS (bajo el lock del incidente) no
# deja pedir dos veces la misma fila.
_INSERT_CONFIRM_REQUEST_SQL = """
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
SELECT %(incident)s, %(tenant)s, 'dictamen_confirm_requested', 'system:dictamen',
       %(payload)s::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM incident_actions
  WHERE incident_id = %(incident)s AND kind = 'dictamen_confirm_requested'
    AND payload->>'dictamen_id' = %(dictamen_id)s
)
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
  AND ( (%(pga)s::float8 IS NOT NULL
         AND COALESCE(max_pga_g, -1) < %(pga)s::float8::numeric)
     OR (%(pgv)s::float8 IS NOT NULL
         AND COALESCE(max_pgv_cms, -1) < %(pgv)s::float8::numeric) )
"""
# [T-9.30] La comparación va en `numeric`, el tipo de la columna: comparada con el
# float8 original, una PGA como 0.01 (real) guardada con 15 dígitos quedaba MENOR
# que sí misma y el UPDATE se repetía en cada pasada.


def run_dictamen_pass(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    now: datetime | None = None,
    lookback_s: float = 300.0,
    settle_s: float | None = None,
) -> list[str]:
    """Emite/corrige dictámenes ``dictamen-v2``. Devuelve los ``dictamen_id``
    insertados (vacío si nada cambió). Un COMMIT al final si hubo escrituras; si
    no, ROLLBACK (solo se leyó)."""
    now = now or datetime.now(tz=UTC)
    settle = settings.dictamen_settle_s if settle_s is None else settle_s
    since = now - timedelta(seconds=lookback_s)
    cutoff = now - timedelta(seconds=settle)
    reeval_since = now - timedelta(seconds=settings.dictamen_reevaluacion_s)
    if cutoff <= since:
        return []

    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_DICTAMEN_LOCK_KEY,))
    rows = conn.execute(
        _CANDIDATES_SQL,
        {
            "since": since,
            "cutoff": cutoff,
            "reeval_since": reeval_since,
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

        dictamen_id = _dictaminar(conn, settings, row, now)
        if dictamen_id is not None:
            created.append(dictamen_id)

    if created or backfilled:
        conn.commit()
    else:
        conn.rollback()
    return created


def _gracia_cumplida(row: dict, settings: Settings, now: datetime) -> tuple[bool, datetime]:
    """El tier del sitio lleva en ``normal`` ≥ ``dictamen_verde_gracia_s``.

    Sin evaluaciones el tier es ``normal`` (mismo criterio que ``lifecycle``). La
    gracia cuenta desde lo ÚLTIMO de la vuelta a normal y la apertura: una vuelta a
    normal ANTERIOR al sismo no puede adelantar la firma."""
    tier = row["last_tier"] or "normal"
    desde = row["opened_at"]
    if row["last_tier_ts"] is not None and row["last_tier_ts"] > desde:
        desde = row["last_tier_ts"]
    ok = tier == "normal" and desde <= now - timedelta(seconds=settings.dictamen_verde_gracia_s)
    return ok, desde


def _subida_tras_firma_humana(decision: Decision, band: str, firma: dict, nuevos: list) -> Decision:
    """La fila que sube sobre una firma humana: banda y motivos SÓLO de los daños
    nuevos (la PGA y lo anterior ya los juzgó quien firmó); la evidencia completa
    sigue constando."""
    basis = dict(decision.basis)
    claves = sorted({k for r in nuevos for k in (r["claves"] or ())})
    basis["band"] = band
    basis["motivos"] = [f"dano:{k}" for k in claves] or ["dano_sin_categoria"]
    basis["subida_tras_firma"] = {
        "signature_kind": firma["signature_kind"],
        "firmada_en": firma["created_at"].isoformat(),
        "reportes_nuevos": [str(r["report_id"]) for r in nuevos],
    }
    basis["notes"] = "daño reportado después de la firma: requiere nueva revisión"
    return Decision(status=BANDA_STATUS[band], basis=basis, band=band)


def _dictaminar(
    conn: psycopg.Connection, settings: Settings, row: dict, now: datetime
) -> str | None:
    """Decide e inserta (a lo sumo) UNA fila para el incidente. Reglas D-43:

    - Sin cadena ⇒ preliminar v2 sin firmar.
    - Banda nueva MÁS ALTA que la cabeza (firmada o no, de quien sea) ⇒ fila sin
      firmar que la supersede: la prudencia sube sola.
    - Jamás inserta una banda más baja: sólo baja con firma.
    - Tras la ÚLTIMA firma de una PERSONA ⇒ sólo suben los daños que no vio (D-49 R4).
    - Cabeza VERDE sin firmar + evaluación VERDE + tier normal ≥ gracia + sin
      daños + sin escalada pendiente ⇒ VERDE firmado por el sistema.
    """
    # Serializa con la firma y la confirmación: la cabeza se valida DENTRO del lock.
    conn.execute(_LOCK_INCIDENT_SQL, {"incident": row["incident_id"]})
    head = conn.execute(_HEAD_SQL, {"incident": row["incident_id"]}).fetchone()
    reportes = conn.execute(_DAMAGE_SQL, {"incident": row["incident_id"]}).fetchall()
    damage_reports = len(reportes)
    claves = sorted({k for r in reportes for k in (r["claves"] or ())})

    # Pico efectivo + procedencia: features de los ACTIVOS > incidente > nada.
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
    decision = evaluate_v2(
        EvalInputV2(
            pga_g=pga_g,
            pga_source=pga_source,
            active_sensors=row["active_sensors"],
            uncalibrated_sensors=row["uncalibrated_sensors"],
            damage_reports=damage_reports,
            damage_keys=tuple(claves),
            severity=row["severity"],
            trigger=row["trigger"],
            event_id=row["event_id"],
        ),
        resolve_params_v2(config, settings),
    )
    # Consta (no decide): la corroboración de red sigue siendo evidencia legible.
    decision.basis["evidence"]["node_count"] = row["node_count"]
    decision.basis["evidence"]["corroborated"] = (
        row["node_count"] >= resolve_quorum_params(config, settings).min_nodes
    )
    band = decision.band or "rojo"

    signed_by: str | None = None
    signature_kind: str | None = None
    firma = (
        conn.execute(_ULTIMA_FIRMA_HUMANA_SQL, {"incident": row["incident_id"]}).fetchone()
        if head is not None
        else None
    )
    if head is not None and firma is not None:
        # [F3·r3 · D-43 · D-49 R4] LA FIRMA HUMANA NO SE DESHACE SOLA. Quien firmó ya
        # vio la PGA y los daños de su lista (``basis.danos_vistos``); la evaluación
        # completa volvía a subir sobre su firma en cada pasada durante 72 h. Tras la
        # ÚLTIMA firma humana —sea la cabeza o tenga una subida sin firmar encima—
        # sólo sube un daño que NO vio: si no, una fuga de agua tras el VERDE del
        # inspector con PGA roja subía a AMARILLO y la pasada siguiente, por la PGA
        # que él ya juzgó, a ROJO (el edificio cerrado 72 h tras la firma).
        nuevos = danos_no_vistos(reportes, firma)
        if not nuevos:
            return None
        band = banda_por_danos([k for r in nuevos for k in (r["claves"] or ())])
        if ORDEN_BANDA[band] <= ORDEN_BANDA[banda_de(head["status"], head["band"])]:
            return None
        decision = _subida_tras_firma_humana(decision, band, firma, nuevos)
    elif head is not None:
        head_band = banda_de(head["status"], head["band"])
        if ORDEN_BANDA[band] > ORDEN_BANDA[head_band]:
            pass  # la prudencia sube sola: fila nueva SIN firmar
        elif (
            head["signed_by"] is None
            and head_band == "verde"
            and band == "verde"
            and damage_reports == 0
        ):
            ok, desde = _gracia_cumplida(row, settings, now)
            if not ok:
                return None
            # [F3·r3 · D-43] La brigada ESCALÓ al inspector: el sistema no firma el
            # VERDE por encima de esa petición (la app le dijo «solicitud enviada»).
            if conn.execute(_PENDING_REQUEST_SQL, {"incident": row["incident_id"]}).fetchone():
                return None
            signed_by, signature_kind = SYSTEM_DICTAMEN_SIGNER_UUID, "system"
            decision.basis["firma_sistema"] = {
                "gracia_s": settings.dictamen_verde_gracia_s,
                "tier_normal_desde": desde.isoformat(),
            }
            decision.basis["notes"] = "dictamen emitido y firmado por el sistema (banda VERDE)"
        else:
            return None  # igual o más bajo: sólo baja con firma

    # [T-7.37] Los umbrales contra los que se clasifica la sacudida se CONGELAN
    # al emitir y una corrección los ARRASTRA VERBATIM del anterior.
    congelado = (
        umbral_congelado([head["basis"]] if head is not None else [])
        or umbral_de_fila(
            conn.execute(
                _UMBRALES_SQL,
                {"at": row["opened_at"], "site": row["site_id"], "tenant": row["tenant_id"]},
            ).fetchone()
        ).as_dict()
    )
    decision.basis[CLAVE_UMBRAL_CONGELADO] = congelado
    head_id = head["dictamen_id"] if head is not None else None
    dictamen_id = conn.execute(
        _INSERT_DICTAMEN_SQL,
        {
            "tenant": row["tenant_id"],
            "incident": row["incident_id"],
            "status": decision.status,
            "basis": json.dumps(decision.basis),
            "supersedes": head_id,
            "band": band,
            "signed_by": signed_by,
            "signature_kind": signature_kind,
            "head_created_at": head["created_at"] if head is not None else None,
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
                    "band": band,
                    "signature_kind": signature_kind,
                    "rule_set_version": decision.basis["rule_set_version"],
                    "supersedes": str(head_id) if head_id else None,
                }
            ),
        },
    )
    if band == "amarillo" and signed_by is None:
        conn.execute(
            _INSERT_CONFIRM_REQUEST_SQL,
            {
                "incident": row["incident_id"],
                "tenant": row["tenant_id"],
                "dictamen_id": str(dictamen_id),
                "payload": json.dumps(
                    {"dictamen_id": str(dictamen_id), "status": decision.status, "band": band}
                ),
            },
        )
    logger.info(
        "dictamen %s: incidente %s → %s (%s)%s%s",
        dictamen_id,
        row["incident_id"],
        decision.status,
        band,
        " (corrección)" if head_id else "",
        " · firmado por el sistema" if signature_kind == "system" else "",
    )
    return str(dictamen_id)
