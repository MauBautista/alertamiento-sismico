"""GET/PUT rule_sets (versionado + active flip), publish 202, RLS y authz (B2)."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine

_ADMIN = "abcabcab-0000-0000-0000-0000000000f1"


def _tok(role: str, tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", user_id=_ADMIN))


async def _put(client, tenant: str = au.DB_TENANT_PRIV, config: dict | None = None):
    return await client.put(
        "/rule-sets",
        json={
            "scope_type": "site",
            "scope_id": au.DB_SITE_PRIV,
            "config": config or {"thresholds": {"pga_g": 0.05}},
        },
        headers=_tok("tenant_admin", tenant=tenant),
    )


async def test_put_creates_new_versions_and_flips_active(client, base_data) -> None:
    v1 = await _put(client)
    assert v1.status_code == 201, v1.text
    assert v1.json()["version"] == 1
    assert v1.json()["is_active"] is True

    v2 = await _put(client, config={"thresholds": {"pga_g": 0.08}})
    assert v2.status_code == 201
    assert v2.json()["version"] == 2
    assert v2.json()["is_active"] is True

    listing = await client.get("/rule-sets", headers=_tok("tenant_admin"))
    assert listing.status_code == 200
    by_version = {it["version"]: it for it in listing.json()["items"]}
    assert by_version[1]["is_active"] is False, "la versión anterior se apagó"
    assert by_version[2]["is_active"] is True


async def test_publish_returns_202_pending_sync(client, base_data) -> None:
    created = await _put(client)
    rid = created.json()["rule_set_id"]

    resp = await client.post(f"/rule-sets/{rid}/publish", headers=_tok("tenant_admin"))
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending_sync"
    assert body["rule_set_id"] == rid
    assert body["version"] == 1

    engine = get_engine()
    async with engine.connect() as conn:
        n = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM audit_log WHERE verb = 'rule_set_publish' AND object = :o"
                ),
                {"o": f"rule_set:{rid}"},
            )
        ).scalar_one()
    assert n == 1, "publish deja la intención en audit_log"


async def test_publish_missing_is_404(client, base_data) -> None:
    resp = await client.post(f"/rule-sets/{uuid4()}/publish", headers=_tok("tenant_admin"))
    assert resp.status_code == 404


async def test_authz_edit_thresholds_only(client, base_data) -> None:
    created = await _put(client)
    rid = created.json()["rule_set_id"]

    # soc_operator no administra umbrales.
    put_forbidden = await client.put(
        "/rule-sets",
        json={"scope_type": "site", "scope_id": au.DB_SITE_PRIV, "config": {}},
        headers=_tok("soc_operator"),
    )
    assert put_forbidden.status_code == 403
    pub_forbidden = await client.post(f"/rule-sets/{rid}/publish", headers=_tok("soc_operator"))
    assert pub_forbidden.status_code == 403

    # pero sí puede leer el catálogo (superficie web).
    read = await client.get("/rule-sets", headers=_tok("soc_operator"))
    assert read.status_code == 200


async def test_rule_sets_cross_tenant_isolated(client, base_data) -> None:
    created = await _put(client)  # tenant A
    rid = created.json()["rule_set_id"]

    other = await client.get("/rule-sets", headers=_tok("tenant_admin", tenant=au.DB_TENANT_PRIV2))
    assert other.status_code == 200
    assert all(it["rule_set_id"] != rid for it in other.json()["items"])


async def test_invalid_scope_type_is_400(client, base_data) -> None:
    resp = await client.put(
        "/rule-sets",
        json={"scope_type": "planet", "scope_id": au.DB_SITE_PRIV, "config": {}},
        headers=_tok("tenant_admin"),
    )
    assert resp.status_code == 400
