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


# ---- cruce de tenants en la escritura (hallazgo al construir T-1.30) ---------


async def test_superadmin_cannot_write_a_rule_set_for_another_tenants_scope(
    client, base_data
) -> None:
    """El INSERT fija ``tenant_id = claims.tenant_id`` mientras el alcance lo elige el
    cuerpo. Un rol interno (bypassa RLS por ``rule_sets_admin``) podía así:

    1. apagar los rule_sets ACTIVOS del tenant ajeno (``deactivate_scope`` sólo
       filtraba por alcance), y
    2. insertar una fila con SU ``tenant_id`` y el ``scope_id`` del ajeno.

    El worker de sync resuelve el rule_set POR ALCANCE (``commands/sync.py``
    ``scope_id = g.tenant_id``), sin comparar ``tenant_id``: los gabinetes del tenant
    ajeno habrían aplicado una config que su propio admin ya no podía ni ver (RLS la
    filtra por ``tenant_id``). Umbrales = disparo de sirena y gas: no es cosmético.
    """
    resp = await client.put(
        "/rule-sets",
        json={"scope_type": "tenant", "scope_id": au.DB_TENANT_PRIV2, "config": {"x": 1}},
        headers=_tok("takab_superadmin", tenant=au.DB_TENANT_PRIV),
    )
    assert resp.status_code == 403, resp.text

    # Y el alcance de SITIO ajeno tampoco.
    site_resp = await client.put(
        "/rule-sets",
        json={"scope_type": "site", "scope_id": au.DB_SITE_PRIV2, "config": {"x": 1}},
        headers=_tok("takab_superadmin", tenant=au.DB_TENANT_PRIV),
    )
    assert site_resp.status_code == 403, site_resp.text


async def test_superadmin_still_writes_its_own_tenant_scope(client, base_data) -> None:
    """El cierre no rompe el caso legítimo: el alcance propio se sigue escribiendo."""
    resp = await client.put(
        "/rule-sets",
        json={"scope_type": "tenant", "scope_id": au.DB_TENANT_PRIV, "config": {"x": 1}},
        headers=_tok("takab_superadmin", tenant=au.DB_TENANT_PRIV),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["tenant_id"] == au.DB_TENANT_PRIV
    assert resp.json()["scope_id"] == au.DB_TENANT_PRIV


async def test_put_unknown_scope_is_404(client, base_data) -> None:
    resp = await client.put(
        "/rule-sets",
        json={"scope_type": "site", "scope_id": str(uuid4()), "config": {}},
        headers=_tok("tenant_admin"),
    )
    assert resp.status_code == 404, resp.text


# ---- el secret del webhook nunca sale, y nunca se pierde (hallazgos T-1.30) --

_WEBHOOK = {"notifications": {"webhook": {"url": "https://ops.example/hook", "secret": "hmac-key"}}}


async def _put_tenant(client, config: dict, base_version: int | None = None, role="tenant_admin"):
    body: dict = {"scope_type": "tenant", "scope_id": au.DB_TENANT_PRIV, "config": config}
    if base_version is not None:
        body["base_version"] = base_version
    return await client.put("/rule-sets", json=body, headers=_tok(role))


async def _raw_config(scope_id: str) -> dict:
    engine = get_engine()
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT config FROM rule_sets WHERE scope_id = CAST(:s AS uuid) "
                    "AND is_active ORDER BY version DESC LIMIT 1"
                ),
                {"s": scope_id},
            )
        ).first()
    return row.config


async def test_get_rule_sets_redacts_the_webhook_secret(client, base_data) -> None:
    """El secret firma el webhook del cliente (``notify/providers``). Devolverlo en
    GET /rule-sets lo metía en el navegador, la caché de react-query y el DevTools de
    cualquier superadmin — que además ve TODOS los tenants."""
    created = await _put_tenant(client, _WEBHOOK)
    assert created.status_code == 201, created.text
    assert "hmac-key" not in created.text

    listed = await client.get("/rule-sets", headers=_tok("tenant_admin"))
    assert listed.status_code == 200
    assert "hmac-key" not in listed.text

    # …pero en la DB sigue ahí, intacto: el worker lo re-resuelve al despachar.
    assert (await _raw_config(au.DB_TENANT_PRIV))["notifications"]["webhook"][
        "secret"
    ] == "hmac-key"


async def test_put_without_secret_preserves_the_stored_one(client, base_data) -> None:
    """El cliente ya no ve el secret, así que no puede reenviarlo. Si el PUT no lo
    trae, se conserva el vigente: de otro modo guardar un umbral rompería en silencio
    la firma HMAC del webhook del cliente."""
    await _put_tenant(client, _WEBHOOK)

    # El front reenvía la config SIN secret (nunca lo recibió).
    resp = await _put_tenant(
        client, {"notifications": {"webhook": {"url": "https://ops.example/hook"}}}
    )
    assert resp.status_code == 201, resp.text
    assert (await _raw_config(au.DB_TENANT_PRIV))["notifications"]["webhook"][
        "secret"
    ] == "hmac-key"


async def test_disabling_the_webhook_drops_its_secret(client, base_data) -> None:
    """Quitar el canal SÍ borra su secret (es la intención explícita del operador)."""
    await _put_tenant(client, _WEBHOOK)
    await _put_tenant(client, {"notifications": {}})
    assert "webhook" not in (await _raw_config(au.DB_TENANT_PRIV))["notifications"]


async def test_stale_base_version_is_409_not_a_lost_update(client, base_data) -> None:
    """PUT reemplaza el blob ENTERO del alcance. Sin control de concurrencia, un
    segundo escritor con una copia vieja revertía en silencio claves que su pantalla
    ni muestra (p. ej. ``relays.siren``, que arma la sirena)."""
    v1 = await _put_tenant(client, {"relays": {"siren": "NO"}, "edge": {}})
    assert v1.status_code == 201
    version = v1.json()["version"]

    # Otro actor publica encima.
    v2 = await _put_tenant(client, {"relays": {"siren": "YES"}, "edge": {}})
    assert v2.status_code == 201

    # El primero guarda con su base vieja ⇒ 409, no un lost update.
    stale = await _put_tenant(client, {"relays": {"siren": "NO"}, "edge": {}}, base_version=version)
    assert stale.status_code == 409, stale.text
    assert (await _raw_config(au.DB_TENANT_PRIV))["relays"]["siren"] == "YES"


async def test_correct_base_version_is_accepted(client, base_data) -> None:
    v1 = await _put_tenant(client, {"edge": {}})
    ok = await _put_tenant(client, {"edge": {"x": 1}}, base_version=v1.json()["version"])
    assert ok.status_code == 201, ok.text


async def test_base_version_on_a_scope_without_rule_set_is_409(client, base_data) -> None:
    """Decir "venía de la v3" cuando el alcance no tiene ninguna activa es una
    premisa falsa: se rechaza en vez de crear la v1 a ciegas."""
    resp = await _put_tenant(client, {"edge": {}}, base_version=3)
    assert resp.status_code == 409, resp.text
