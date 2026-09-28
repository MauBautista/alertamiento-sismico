"""[T-9.42 · D-48] `GET /incidents/{id}/post-event-report`: lo que lee la consola.

Lectura pura de la fila que deja el worker `informes`. Sin fila es 404
`sin_informe` —el asistente de cierre lo pinta como «aún no»—; el incidente de otro
cliente también es 404 (la RLS de la tabla no lo deja ver), nunca 403. Los roles
son los que leen el detalle del incidente, sin acción nueva en la matriz.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine

T0 = datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC)


async def _sql(sql: str, **p):
    async with get_engine().begin() as conn:
        r = await conn.execute(text(sql), p)
        return r.fetchall() if r.returns_rows else []


async def _incidente(tenant: str = au.DB_TENANT_PRIV, site: str = au.DB_SITE_PRIV) -> str:
    inc = str(uuid.uuid4())
    await _sql(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at,"
        " severity, trigger) VALUES (:i, gen_random_uuid(), :t, :s, :o, 'critical', 'sasmex')",
        i=inc,
        t=tenant,
        s=site,
        o=T0,
    )
    return inc


async def _informe(inc: str, *, tenant: str = au.DB_TENANT_PRIV, **campos) -> None:
    fila = {"trigger": "plazo", "state": "fallido", "attempts": 1, "error": "sin_bucket", **campos}
    await _sql(
        "INSERT INTO post_event_reports (tenant_id, incident_id, trigger, state, variant,"
        " attempts, error) VALUES (:t, :i, :trigger, :state, 'executive', :attempts, :error)",
        t=tenant,
        i=inc,
        **fila,
    )


def _token(role: str = "tenant_admin", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _pide(client, inc: str, **over):
    return await client.get(f"/incidents/{inc}/post-event-report", headers=_token(**over))


async def test_sin_fila_es_404_sin_informe(client, base_data):
    inc = await _incidente()
    r = await _pide(client, inc)
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "sin_informe"


async def test_devuelve_la_fila_tal_cual_con_su_error(client, base_data):
    """`error` va tal cual: sólo lo ve personal del cliente con acceso al incidente."""
    inc = await _incidente()
    await _informe(inc)
    r = await _pide(client, inc)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["state"] == "fallido"
    assert cuerpo["trigger"] == "plazo"
    assert cuerpo["variant"] == "executive"
    assert cuerpo["attempts"] == 1
    assert cuerpo["error"] == "sin_bucket"
    assert cuerpo["evidence_id"] is None
    assert cuerpo["preliminar"] is None
    assert set(cuerpo) >= {"created_at", "updated_at"}


async def test_el_informe_de_otro_cliente_es_404_y_NO_403(client, base_data):
    inc = await _incidente(tenant=au.DB_TENANT_PRIV2, site=au.DB_SITE_PRIV2)
    await _informe(inc, tenant=au.DB_TENANT_PRIV2)
    r = await _pide(client, inc)
    assert r.status_code == 404, r.text


async def test_quien_no_lee_el_incidente_no_lee_el_informe(client, base_data):
    """El ocupante no tiene consola: la misma puerta que el detalle del incidente."""
    inc = await _incidente()
    await _informe(inc)
    r = await _pide(client, inc, role="occupant")
    assert r.status_code == 403, r.text
