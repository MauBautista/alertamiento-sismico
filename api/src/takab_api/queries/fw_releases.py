"""Registro de releases de firmware (T-2.69) — contra QUÉ se mide la deriva.

Tabla de PLATAFORMA sin ``tenant_id`` (excepción documentada, familia de
``reference_earthquakes``): qué firmware existe lo decide TAKAB. La RLS de la
tabla concede lectura a cualquier rol autenticado y escritura solo a
``takab_superadmin``; la deriva de CADA cliente sigue acotada por la RLS de
``gateways``, que es donde vive "qué gabinete corre qué".

El orden ``released_at DESC, seq DESC`` es la única fuente del "cuántos atrás":
los SHAs de 7 hex de ``deploy/edge/deploy.sh`` no son ordenables por sí mismos.
``seq`` desempata: sin él, dos releases con el mismo ``released_at`` (un backfill)
darían un "cuántos atrás" distinto en cada recarga según el plan de ejecución.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

# ``age_s`` se calcula con el ``now()`` de la transacción, igual que ``age_s`` de
# la flota: la antigüedad no puede depender del reloj de la app ni del navegador.
_LIST = text(
    "SELECT release_id, version, released_at, notes, published_by, "
    "       EXTRACT(EPOCH FROM (now() - released_at))::float8 AS age_s "
    "FROM fw_releases ORDER BY released_at DESC, seq DESC"
)

# Sin ON CONFLICT: republicar el mismo SHA no es idempotencia, es un error de
# operación (¿el de ayer o el de hoy?). El UNIQUE lo convierte en IntegrityError
# y el router en 409, que es lo que el operador necesita leer.
_INSERT = text(
    "INSERT INTO fw_releases (version, released_at, notes, published_by) "
    "VALUES (:version, COALESCE(CAST(:released_at AS timestamptz), now()), "
    "        :notes, :published_by) "
    "RETURNING release_id, version, released_at, notes, published_by, "
    "          EXTRACT(EPOCH FROM (now() - released_at))::float8 AS age_s"
)


async def list_releases(conn: AsyncConnection) -> Sequence[Row]:
    """Releases publicados, MÁS NUEVO PRIMERO. El índice de la lista es la deriva."""
    return (await conn.execute(_LIST)).all()


async def insert_release(
    conn: AsyncConnection,
    *,
    version: str,
    released_at: datetime | None,
    notes: str | None,
    published_by: str | None,
) -> Row:
    """Publica un release. Lanza ``IntegrityError`` si la versión ya existe."""
    return (
        await conn.execute(
            _INSERT,
            {
                "version": version,
                "released_at": released_at,
                "notes": notes,
                "published_by": published_by,
            },
        )
    ).one()
