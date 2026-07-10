"""GET/PUT /me/profile (T-1.48): nombre de operador editable.

GET /me NO se toca (claims puros, sin DB) — estos endpoints son aparte. La RLS
self-write se prueba a fondo en test_migration_0011; aquí va el contrato HTTP.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine

pytestmark = pytest.mark.usefixtures("base_data")


def _hdr(role: str = "soc_operator", *, sub: str | None = None, **over):
    return au.bearer(
        au.make_token(role, tenant=au.DB_TENANT_PRIV, user_id=sub or str(uuid.uuid4()), **over)
    )


async def test_get_without_profile_is_null_not_404(client) -> None:
    r = await client.get("/me/profile", headers=_hdr())
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] is None
    assert body["updated_at"] is None


async def test_put_creates_then_get_reflects(client) -> None:
    sub = str(uuid.uuid4())
    r = await client.put(
        "/me/profile", headers=_hdr(sub=sub), json={"display_name": "M. Rodríguez"}
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "M. Rodríguez"

    r2 = await client.get("/me/profile", headers=_hdr(sub=sub))
    assert r2.json()["display_name"] == "M. Rodríguez"


async def test_put_updates_and_normalizes_whitespace(client) -> None:
    sub = str(uuid.uuid4())
    await client.put("/me/profile", headers=_hdr(sub=sub), json={"display_name": "Uno"})
    r = await client.put(
        "/me/profile", headers=_hdr(sub=sub), json={"display_name": "  Mauricio   B.  "}
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Mauricio B."


@pytest.mark.parametrize("bad", ["", "   ", "x" * 81])
async def test_put_rejects_empty_or_too_long(client, bad: str) -> None:
    r = await client.put("/me/profile", headers=_hdr(), json={"display_name": bad})
    assert r.status_code == 422


async def test_put_is_audited(client) -> None:
    sub = str(uuid.uuid4())
    await client.put("/me/profile", headers=_hdr(sub=sub), json={"display_name": "Auditado"})
    engine = get_engine()
    async with engine.connect() as conn:
        n = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM audit_log "
                    "WHERE verb = 'profile_update' AND actor = :actor"
                ),
                {"actor": f"user:{sub}"},
            )
        ).scalar_one()
    assert n == 1


async def test_other_user_profile_stays_own(client) -> None:
    """Cada quien ve/edita SU perfil: otro sub del mismo tenant arranca en null."""
    sub_a = str(uuid.uuid4())
    await client.put("/me/profile", headers=_hdr(sub=sub_a), json={"display_name": "A"})
    r = await client.get("/me/profile", headers=_hdr(sub=str(uuid.uuid4())))
    assert r.json()["display_name"] is None


async def test_mobile_surface_is_rejected(client) -> None:
    hdr = au.bearer(au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, surface="mobile"))
    r = await client.get("/me/profile", headers=hdr)
    assert r.status_code == 403
    r2 = await client.put("/me/profile", headers=hdr, json={"display_name": "X"})
    assert r2.status_code == 403


async def test_gov_operator_edits_own_name(client) -> None:
    """Excepción documentada: gov edita SU nombre (dato personal)."""
    hdr = au.bearer(
        au.make_token("gov_operator", tenant=au.DB_TENANT_AGENCY, user_id=str(uuid.uuid4()))
    )
    # La agencia gov no es tenant cliente: siembra el tenant para el FK.
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO tenants (tenant_id, code, name, visibility) "
                "VALUES (:id, 'B2_AG', 'Agencia', 'private') ON CONFLICT DO NOTHING"
            ),
            {"id": au.DB_TENANT_AGENCY},
        )
    r = await client.put("/me/profile", headers=hdr, json={"display_name": "Operador PC"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "Operador PC"
