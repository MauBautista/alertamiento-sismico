"""Máquina de estados del ciclo de vida de un incidente. LÓGICA PURA.

Estados y transiciones alineados con ``incidents.state`` (db/schema.sql):
CHECK (state IN ('open','acked','in_review','closed')). Sin retrocesos;
``closed`` es terminal.
"""

from __future__ import annotations

STATES: frozenset[str] = frozenset({"open", "acked", "in_review", "closed"})

# Sólo avances: open→acked→in_review→closed con atajos hacia adelante.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"acked", "in_review", "closed"}),
    "acked": frozenset({"in_review", "closed"}),
    "in_review": frozenset({"closed"}),
    "closed": frozenset(),
}


class InvalidTransition(ValueError):
    """Transición no permitida por la máquina de ciclo de vida."""


def is_terminal(state: str) -> bool:
    """``closed`` es el único estado terminal."""
    return state == "closed"


def validate_transition(cur: str, nxt: str) -> None:
    """No hace nada si ``cur → nxt`` es válida; si no, lanza ``InvalidTransition``."""
    if cur not in STATES:
        raise InvalidTransition(f"estado actual desconocido: {cur!r}")
    if nxt not in STATES:
        raise InvalidTransition(f"estado destino desconocido: {nxt!r}")
    if nxt not in VALID_TRANSITIONS[cur]:
        raise InvalidTransition(f"transición no permitida: {cur} → {nxt}")
