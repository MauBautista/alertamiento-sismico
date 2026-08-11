"""T-2.115 · Las filas que `tests/auth` y `tests/api` siembran LAS DOS, en un solo sitio.

Los UUIDs de tenant y sitio viven en ``auth_utils`` y los usan las dos familias, así
que ambas sembraban **exactamente las mismas filas**… con valores distintos y
``ON CONFLICT DO NOTHING``. Ni ``tenants`` ni ``sites`` entran en el ``TRUNCATE`` de
teardown: la fila sobrevive a todo el proceso —y a la corrida anterior—, de modo que
**ganaba quien corriese primero** y el veredicto de un test dependía del ORDEN DE
RECOLECCIÓN (`tests/auth` antes que `tests/api` ponía rojo
`tests/api/test_events.py::test_los_votos_traen_el_codigo_de_la_estacion`).

Dos candados, y hacen falta los dos:

1. **Una sola definición.** Este módulo es el único que escribe esas filas; las dos
   familias lo llaman. Coherencia por construcción, no por disciplina.
2. **Siembra AUTORITATIVA, no "el primero gana".** El ``ON CONFLICT`` es
   ``DO UPDATE``: la fila queda en el valor canónico ejecute quien ejecute, y ni el
   orden ni lo que dejó la corrida anterior pueden decidirlo. Un ``DO NOTHING`` aquí
   reabriría T-2.115 en silencio — lo veta ``tests/test_seed_coherence.py``.

Los códigos son los que las pruebas ya afirman (`B2SA` en `test_events.py`), así que
el valor canónico es el de la familia que lo comprueba.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

import auth_utils as au

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"

#: Nombre único para las filas compartidas: si cada familia pusiera el suyo, el
#: ``DO UPDATE`` las haría oscilar test a test y volveríamos a depender del orden.
TENANT_NAME = "Tenant compartido de tests"
SITE_NAME = "Sitio"

#: ``(tenant_id, code, visibility)``. `code` es UNIQUE global en ``tenants``.
SHARED_TENANTS: tuple[tuple[str, str, str], ...] = (
    (au.DB_TENANT_PRIV, "B2_A", "private"),
    (au.DB_TENANT_PRIV2, "B2_B", "private"),
    (au.DB_TENANT_GOV, "B2_G", "gov_shared"),
)

#: ``(site_id, tenant_id, code)``. `code` es UNIQUE por ``(tenant_id, code)``.
SHARED_SITES: tuple[tuple[str, str, str], ...] = (
    (au.DB_SITE_PRIV, au.DB_TENANT_PRIV, "B2SA"),
    (au.DB_SITE_PRIV2, au.DB_TENANT_PRIV2, "B2SB"),
    (au.DB_SITE_GOV, au.DB_TENANT_GOV, "B2SG"),
)

UPSERT_TENANT = text(
    "INSERT INTO tenants (tenant_id, code, name, visibility) "
    "VALUES (:id, :code, :name, :vis) "
    "ON CONFLICT (tenant_id) DO UPDATE SET "
    "code = EXCLUDED.code, name = EXCLUDED.name, visibility = EXCLUDED.visibility"
)

UPSERT_SITE = text(
    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
    f"VALUES (:sid, :tid, :code, :name, {_GEOM}) "
    "ON CONFLICT (site_id) DO UPDATE SET "
    "tenant_id = EXCLUDED.tenant_id, code = EXCLUDED.code, name = EXCLUDED.name"
)


async def seed_shared_rows(conn: AsyncConnection) -> None:
    """Deja las filas compartidas en su valor canónico. Idempotente y autoritativa.

    Se ejecuta con la conexión del DSN de tests (bypassa RLS), dentro de la
    transacción que abra el llamador.
    """
    for tenant_id, code, visibility in SHARED_TENANTS:
        await conn.execute(
            UPSERT_TENANT,
            {"id": tenant_id, "code": code, "name": TENANT_NAME, "vis": visibility},
        )
    for site_id, tenant_id, code in SHARED_SITES:
        await conn.execute(
            UPSERT_SITE,
            {"sid": site_id, "tid": tenant_id, "code": code, "name": SITE_NAME},
        )
