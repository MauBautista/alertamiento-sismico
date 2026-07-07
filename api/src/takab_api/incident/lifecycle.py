"""Operaciones de ciclo de vida del incidente con DB (T-1.19 · B2).

``transitions`` (LÓGICA PURA) es la única autoridad de qué transición es válida;
aquí se añade la persistencia: UPDATE de ``incidents.state`` (+ ``closed_at`` al
cerrar), traza en ``incident_actions`` y ``audit_log``. Corre como
``takab_ingest`` (BYPASSRLS). El ack open→acked de la API (T-1.18) es un caso
particular; estas operaciones cubren el resto (in_review, closed) de forma
consistente y le sirven al engine para cerrar incidentes de eventos resueltos.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from psycopg.types.json import Jsonb

from takab_api.incident.transitions import validate_transition

if TYPE_CHECKING:
    import psycopg


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

_AUDIT_SQL = """
INSERT INTO audit_log (tenant_id, actor, verb, object)
VALUES (%(tenant)s, %(actor)s, %(verb)s, %(object)s)
"""


def transition_incident(
    conn: psycopg.Connection, incident_id: str, new_state: str, actor: str
) -> str:
    """Transiciona un incidente a ``new_state`` validando con el state machine.

    Bloquea la fila (``FOR UPDATE``) para serializar transiciones concurrentes,
    valida ``estado_actual → new_state`` (``InvalidTransition`` si no procede),
    aplica el UPDATE (fija ``closed_at`` al cerrar) y deja traza en
    ``incident_actions`` + ``audit_log``. Devuelve ``new_state``.

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
            "payload": Jsonb({"from": current, "to": new_state}),
        },
    )
    conn.execute(
        _AUDIT_SQL,
        {
            "tenant": tenant_id,
            "actor": actor,
            "verb": kind,
            "object": f"incident:{incident_id}",
        },
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
