"""Operaciones de ciclo de vida del incidente con DB (T-1.19 · B2).

``transitions`` (LÓGICA PURA) es la única autoridad de qué transición es válida;
aquí se añade la persistencia: UPDATE de ``incidents.state`` (+ ``closed_at`` al
cerrar), traza en ``incident_actions`` y ``audit_log``. Corre como
``takab_ingest`` (BYPASSRLS). El ack open→acked de la API (T-1.18) es un caso
particular; estas operaciones cubren el resto (in_review, closed) de forma
consistente y le sirven al engine para cerrar incidentes de eventos resueltos.

[T-7.13 · D-33] Aquí vive además ``run_lifecycle_pass``, que es el LLAMADOR que
faltaba: hasta esa ficha estas operaciones no las invocaba nadie en producción y
un incidente abierto en julio seguía siendo «la alerta» en septiembre.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from psycopg.types.json import Jsonb

from takab_api.audit import audit
from takab_api.incident.classification import TERMINALES
from takab_api.incident.transitions import validate_transition

if TYPE_CHECKING:
    import psycopg

    from takab_api.settings import Settings

logger = logging.getLogger("takab_api.incident.lifecycle")

#: Actor de todo lo que mueve el worker. Se distingue a simple vista de un
#: `user:<uuid>` en el timeline: quién cerró el incidente es la primera pregunta.
_ACTOR = "system:incident"


class IncidentNotFound(LookupError):
    """El incidente no existe (o no es visible para el rol)."""


# nuevo estado → kind de incident_actions / verb de audit_log. 'acked' usa 'ack'
# para alinear con el acuse de T-1.18 (misma semántica en el timeline y la UI).
_ACTION_KIND: dict[str, str] = {
    "acked": "ack",
    "in_review": "in_review",
    "closed": "close",
}

_SELECT_SQL = "SELECT state, tenant_id FROM incidents WHERE incident_id = %(id)s FOR UPDATE"

_UPDATE_SQL = """
UPDATE incidents
SET state = %(nxt)s,
    closed_at = CASE WHEN %(nxt)s = 'closed' THEN now() ELSE closed_at END
WHERE incident_id = %(id)s
"""

_ACTION_SQL = """
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
VALUES (%(id)s, %(tenant)s, %(kind)s, %(actor)s, %(payload)s)
"""


def transition_incident(
    conn: psycopg.Connection,
    incident_id: str,
    new_state: str,
    actor: str,
    *,
    detalle: dict | None = None,
) -> str:
    """Transiciona un incidente a ``new_state`` validando con el state machine.

    Bloquea la fila (``FOR UPDATE``) para serializar transiciones concurrentes,
    valida ``estado_actual → new_state`` (``InvalidTransition`` si no procede),
    aplica el UPDATE (fija ``closed_at`` al cerrar) y deja traza en
    ``incident_actions`` + ``audit_log``. Devuelve ``new_state``.

    ``detalle`` se funde en el payload de ``incident_actions`` y en el ``meta``
    de la auditoría: es donde viaja la CAUSA del cambio (T-7.13). Quien lee el
    timeline a las 3 de la mañana tiene que poder distinguir «lo cerró el
    inspector» de «lo cerró el TTL porque nadie lo miró», y sin esto las dos
    filas son idénticas.

    Lanza ``IncidentNotFound`` si el incidente no existe/es invisible, e
    ``InvalidTransition`` (ValueError) si la transición no está permitida.
    """
    row = conn.execute(_SELECT_SQL, {"id": incident_id}).fetchone()
    if row is None:
        raise IncidentNotFound(f"incidente inexistente: {incident_id}")
    current = row["state"]
    tenant_id = row["tenant_id"]
    validate_transition(current, new_state)  # raise InvalidTransition

    conn.execute(_UPDATE_SQL, {"nxt": new_state, "id": incident_id})
    kind = _ACTION_KIND.get(new_state, new_state)
    conn.execute(
        _ACTION_SQL,
        {
            "id": incident_id,
            "tenant": tenant_id,
            "kind": kind,
            "actor": actor,
            "payload": Jsonb({"from": current, "to": new_state, **(detalle or {})}),
        },
    )
    audit(
        conn,
        tenant_id=str(tenant_id),
        actor=actor,
        verb=kind,
        obj=f"incident:{incident_id}",
        meta={"from": current, "to": new_state, **(detalle or {})},
    )
    return new_state


def close_resolved(conn: psycopg.Connection, event_id: str, *, actor: str = "system") -> list[str]:
    """Cierra todos los incidentes NO cerrados de un evento resuelto.

    Recorre los incidentes ligados a ``event_id`` con ``state <> 'closed'`` y los
    lleva a ``closed`` vía ``transition_incident`` (misma traza/side-effects).
    Devuelve los ``incident_id`` (str) cerrados en esta pasada; re-run no reabre
    (los ya cerrados quedan fuera del filtro).
    """
    rows = conn.execute(
        "SELECT incident_id FROM incidents "
        "WHERE event_id = %(ev)s AND state <> 'closed' "
        "ORDER BY opened_at, incident_id",
        {"ev": event_id},
    ).fetchall()
    closed: list[str] = []
    for r in rows:
        incident_id = str(r["incident_id"])
        transition_incident(conn, incident_id, "closed", actor)
        closed.append(incident_id)
    return closed


# ═══════════════════════════════════════════════════════════════════════════
# [T-7.13 · D-33] La pasada de fases: quién saca al incidente de la alerta.
# ═══════════════════════════════════════════════════════════════════════════
#
# Hasta esta ficha `transition_incident` y `close_resolved` NO TENÍAN LLAMADOR
# en producción: un incidente abierto en julio seguía siendo «la alerta» en
# septiembre. Esto es el llamador, y corre en el worker `takab_api.incident`
# —nunca en el cliente—: la escena se apaga por lo que el servidor sabe, no por
# el reloj del navegador (regla de oro 7).

#: Clave del advisory lock de la pasada (misma disciplina que el dictamen): dos
#: réplicas del worker no deben transicionar el mismo incidente a la vez.
_FASES_LOCK_KEY = 0x7A13

#: Tope de incidentes por pasada y por fase. No es una optimización: la primera
#: pasada tras desplegar esto encuentra TODO lo que lleva meses abierto, y una
#: transacción de miles de filas bloquea la ingesta. Lo que quede fuera se
#: DECLARA en el resultado y en el log — un corte silencioso se lee como «ya
#: está todo hecho».
_MAX_POR_PASADA = 200

#: El tier del sitio, como lo define el resto del producto. Es LITERALMENTE la
#: consulta de `queries/mobile.py::LATEST_TIER`, y eso importa: si el teléfono
#: del ocupante dice «la sacudida concluyó» porque el último tier es `normal`,
#: la consola no puede seguir en ALERTA por una definición distinta.
#:
#: ⚠️ El ÚLTIMO tier, no «¿hubo alguna vuelta a normal?». La calma ANTERIOR al
#: sismo sigue en la tabla: preguntar si existe una fila `normal` la encuentra y
#: concluye que la sacudida terminó justo cuando está empezando.
_TIER_ACTUAL = """
  COALESCE((SELECT r.new_tier FROM rule_evaluations r
             WHERE r.site_id = i.site_id
             ORDER BY r.ts DESC LIMIT 1), 'normal')
"""

_A_REVISION_SQL = f"""
SELECT i.incident_id
  FROM incidents i
 WHERE i.state IN ('open','acked')
   AND i.opened_at <= %(cutoff)s
   AND {_TIER_ACTUAL} = 'normal'
 ORDER BY i.opened_at
 LIMIT %(lim)s
"""

#: La clasificación VIGENTE, no la primera: corregir INSERTA (T-5.12), y cerrar
#: por una clasificación que ya fue corregida es cerrar por un dato retirado.
_POR_CLASIFICACION_SQL = """
SELECT i.incident_id, v.classification
  FROM incidents i
  JOIN LATERAL (
       SELECT c.classification
         FROM incident_classifications c
        WHERE c.incident_id = i.incident_id
          AND NOT EXISTS (SELECT 1 FROM incident_classifications s
                           WHERE s.supersedes_id = c.classification_id)
        ORDER BY c.classified_at DESC, c.classification_id DESC
        LIMIT 1) v ON TRUE
 WHERE i.state <> 'closed'
   AND v.classification = ANY(%(terminales)s)
 ORDER BY i.opened_at
 LIMIT %(lim)s
"""

_POR_DICTAMEN_SQL = """
SELECT i.incident_id
  FROM incidents i
 WHERE i.state <> 'closed'
   AND EXISTS (SELECT 1 FROM dictamens d
                WHERE d.incident_id = i.incident_id AND d.signed_by IS NOT NULL)
 ORDER BY i.opened_at
 LIMIT %(lim)s
"""

#: El TTL se cuenta desde el INGRESO A REVISIÓN, no desde la apertura. Contarlo
#: desde `opened_at` cerraría por vencimiento un incidente que acaba de entrar en
#: revisión tras una noche de réplicas — justo cuando alguien va a mirarlo.
_POR_TTL_SQL = """
SELECT i.incident_id
  FROM incidents i
 WHERE i.state = 'in_review'
   AND COALESCE((SELECT max(a.ts) FROM incident_actions a
                  WHERE a.incident_id = i.incident_id AND a.kind = 'in_review'),
                i.opened_at) <= %(cutoff)s
 ORDER BY i.opened_at
 LIMIT %(lim)s
"""


@dataclass(frozen=True)
class PasadaDeFases:
    """Lo que hizo una pasada. ``truncada`` es la parte que no se puede callar."""

    en_revision: list[str] = field(default_factory=list)
    cerrados: list[str] = field(default_factory=list)
    truncada: bool = False


def _limitado(rows: list, maximo: int) -> tuple[list, bool]:
    """Recorta a ``maximo`` y dice si sobraba. Se consulta con ``maximo + 1``."""
    return rows[:maximo], len(rows) > maximo


def run_lifecycle_pass(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    now: datetime | None = None,
    max_por_pasada: int = _MAX_POR_PASADA,
) -> PasadaDeFases:
    """Mueve las fases de los incidentes que toca. Idempotente; un COMMIT al final.

    **Cierra primero, promueve después.** Un incidente con clasificación terminal
    se cierra en ESTA pasada aunque también fuera candidato a revisión: pasarlo
    antes por `in_review` escribiría en el timeline una revisión que nadie hizo.

    Orden y causas (`D-33`):

    * ``open``/``acked`` → ``in_review`` cuando el tier del sitio está de vuelta
      en ``normal`` **y** han pasado ``dictamen_settle_s`` **y**
      ``alert_hold_min_s`` desde la apertura. Las dos condiciones se suman: el
      retén no basta por sí solo y el tier tampoco.
    * → ``closed`` por clasificación terminal, por dictamen firmado o por
      ``incident_review_ttl_s`` en revisión. Cada cierre deja su ``reason``.

    ⚠️ **Un gabinete que escala y se queda mudo deja su incidente en ALERTA.** Es
    deliberado y es la dirección segura: el último tier conocido del sitio dice
    que está sacudiéndose, y apagar el banner porque el gabinete dejó de hablar
    sería inventar una vuelta a la normalidad que nadie observó. El operador
    siempre puede clasificar, que cierra al instante; y el gabinete mudo lo
    delata la flota (`is_ghost`, T-2.60), que es donde se ve esa avería.
    """
    ahora = now or datetime.now(tz=UTC)
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_FASES_LOCK_KEY,))

    cerrados = _cerrar(conn, settings, ahora=ahora, maximo=max_por_pasada)
    revisados = _a_revision(conn, settings, ahora=ahora, maximo=max_por_pasada)

    resultado = PasadaDeFases(
        en_revision=revisados[0],
        cerrados=cerrados[0],
        truncada=cerrados[1] or revisados[1],
    )
    if resultado.en_revision or resultado.cerrados:
        conn.commit()
        logger.info(
            "fases: %d a revisión, %d cerrados%s",
            len(resultado.en_revision),
            len(resultado.cerrados),
            " (PASADA TRUNCADA: quedan más para la siguiente)" if resultado.truncada else "",
        )
    else:
        conn.rollback()  # solo se leyó
    return resultado


def _a_revision(
    conn: psycopg.Connection, settings: Settings, *, ahora: datetime, maximo: int
) -> tuple[list[str], bool]:
    """``open``/``acked`` → ``in_review``: la sacudida concluyó y el retén se cumplió."""
    espera_s = max(settings.dictamen_settle_s, settings.alert_hold_min_s)
    rows = conn.execute(
        _A_REVISION_SQL,
        {"cutoff": ahora - timedelta(seconds=espera_s), "lim": maximo + 1},
    ).fetchall()
    elegidos, sobraban = _limitado(rows, maximo)
    movidos = []
    for r in elegidos:
        incident_id = str(r["incident_id"])
        transition_incident(
            conn,
            incident_id,
            "in_review",
            _ACTOR,
            detalle={"reason": "shaking_concluded", "hold_s": settings.alert_hold_min_s},
        )
        movidos.append(incident_id)
    return movidos, sobraban


def _cerrar(
    conn: psycopg.Connection, settings: Settings, *, ahora: datetime, maximo: int
) -> tuple[list[str], bool]:
    """Las tres vías de cierre de `D-33`, con su causa escrita en la traza."""
    causas: dict[str, dict] = {}
    sobraban = False

    filas = conn.execute(
        _POR_CLASIFICACION_SQL, {"terminales": sorted(TERMINALES), "lim": maximo + 1}
    ).fetchall()
    elegidos, falta = _limitado(filas, maximo)
    sobraban = sobraban or falta
    for r in elegidos:
        causas[str(r["incident_id"])] = {
            "reason": "classification",
            "classification": r["classification"],
        }

    filas = conn.execute(_POR_DICTAMEN_SQL, {"lim": maximo + 1}).fetchall()
    elegidos, falta = _limitado(filas, maximo)
    sobraban = sobraban or falta
    for r in elegidos:
        causas.setdefault(str(r["incident_id"]), {"reason": "dictamen_signed"})

    # `0` desactiva esta vía y deja las otras dos: así se revoca `D-33` sin tocar código.
    if settings.incident_review_ttl_s > 0:
        filas = conn.execute(
            _POR_TTL_SQL,
            {
                "cutoff": ahora - timedelta(seconds=settings.incident_review_ttl_s),
                "lim": maximo + 1,
            },
        ).fetchall()
        elegidos, falta = _limitado(filas, maximo)
        sobraban = sobraban or falta
        for r in elegidos:
            causas.setdefault(str(r["incident_id"]), {"reason": "review_ttl"})

    ids = list(causas)[:maximo]
    sobraban = sobraban or len(causas) > maximo
    for incident_id in ids:
        transition_incident(conn, incident_id, "closed", _ACTOR, detalle=causas[incident_id])
    return ids, sobraban
