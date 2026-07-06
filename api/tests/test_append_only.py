"""Inmutabilidad de evidencia/compliance ([ANALISIS-00]).

UPDATE/DELETE sobre las tablas append-only DEBE fallar por el trigger
forbid_update_delete. Se ejercita como el superusuario de la conexión (RESET ROLE):
salta RLS y tiene todos los privilegios, así que lo ÚNICO que puede bloquear es el
trigger — prueba la garantía en su forma más fuerte (ni el rol más privilegiado
puede mutar/borrar auditoría, dictámenes, acciones ni evidencia).
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import reset

# tabla -> expresión SET no-op para el UPDATE (fija la columna a sí misma).
APPEND_ONLY = {
    "audit_log": "verb = verb",
    "incident_actions": "kind = kind",
    "dictamens": "status = status",
    "evidence_objects": "s3_key = s3_key",
}


@pytest.mark.parametrize("table", sorted(APPEND_ONLY))
def test_update_blocked(seeded: psycopg.Connection, table: str) -> None:
    reset(seeded)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        seeded.execute(f"UPDATE {table} SET {APPEND_ONLY[table]}")


@pytest.mark.parametrize("table", sorted(APPEND_ONLY))
def test_delete_blocked(seeded: psycopg.Connection, table: str) -> None:
    reset(seeded)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        seeded.execute(f"DELETE FROM {table}")


def test_insert_still_allowed(seeded: psycopg.Connection) -> None:
    # append-only prohíbe mutar/borrar, no insertar (versionado por fila nueva).
    reset(seeded)
    cur = seeded.execute(
        "INSERT INTO audit_log (tenant_id, actor, verb, object) VALUES (NULL,'system','probe','x')"
    )
    assert cur.rowcount == 1
