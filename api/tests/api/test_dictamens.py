"""GET cadena de dictámenes + POST firma (append-only), RLS y authz (B2)."""

from __future__ import annotations

import auth_utils as au

_INSPECTOR = "abcabcab-0000-0000-0000-0000000000d1"


def _tok(role: str, tenant: str = au.DB_TENANT_PRIV, user: str = _INSPECTOR) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", user_id=user))


async def test_chain_supersedes_and_preliminary_flag(client, make_incident, make_dictamen) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    prelim = await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor", signed_by=None)

    before = await client.get(f"/incidents/{iid}/dictamens", headers=_tok("inspector"))
    assert before.status_code == 200, before.text
    items = before.json()["items"]
    assert len(items) == 1
    assert items[0]["signed_by"] is None, "preliminar = signed_by NULL"

    signed = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "no_inhabit_inspect", "notes": "grietas visibles"},
        headers=_tok("inspector"),
    )
    assert signed.status_code == 201, signed.text
    new = signed.json()
    assert new["signed_by"] == _INSPECTOR
    assert new["supersedes_dictamen_id"] == prelim
    assert new["basis"] == {"notes": "grietas visibles"}

    after = await client.get(f"/incidents/{iid}/dictamens", headers=_tok("inspector"))
    chain = after.json()["items"]
    assert len(chain) == 2
    assert chain[0]["dictamen_id"] == new["dictamen_id"], "más reciente primero"
    assert chain[0]["supersedes_dictamen_id"] == prelim


async def test_sign_always_inserts_new_row(client, make_incident) -> None:
    """Firmar dos veces = dos filas encadenadas (nunca UPDATE; trigger append-only)."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)

    first = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "restricted"},
        headers=_tok("inspector"),
    )
    assert first.status_code == 201
    assert first.json()["supersedes_dictamen_id"] is None

    second = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "normal_operation"},
        headers=_tok("inspector"),
    )
    assert second.status_code == 201
    assert second.json()["supersedes_dictamen_id"] == first.json()["dictamen_id"]

    chain = (await client.get(f"/incidents/{iid}/dictamens", headers=_tok("inspector"))).json()
    ids = {d["dictamen_id"] for d in chain["items"]}
    assert ids == {first.json()["dictamen_id"], second.json()["dictamen_id"]}


async def test_cross_tenant_sign_is_404(client, make_incident) -> None:
    b_iid = await make_incident(au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2)
    resp = await client.post(
        f"/incidents/{b_iid}/dictamens",
        json={"status": "restricted"},
        headers=_tok("inspector"),  # tenant A
    )
    assert resp.status_code == 404


async def test_sign_authz_and_read_authz(client, make_incident, make_dictamen) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await make_dictamen(au.DB_TENANT_PRIV, iid, signed_by=None)

    # soc_operator: Triage lectura sí, firma no.
    read = await client.get(f"/incidents/{iid}/dictamens", headers=_tok("soc_operator"))
    assert read.status_code == 200
    forbidden = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "restricted"},
        headers=_tok("soc_operator"),
    )
    assert forbidden.status_code == 403

    # brigadista: sin Triage → ni lectura.
    no_triage = await client.get(f"/incidents/{iid}/dictamens", headers=_tok("brigadista"))
    assert no_triage.status_code == 403


async def test_invalid_status_is_400(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    resp = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "not_a_status"},
        headers=_tok("inspector"),
    )
    assert resp.status_code == 400


async def test_superadmin_cannot_sign_dictamen(client, make_incident) -> None:
    """La firma es un acto profesional del inspector: ``SIGN_ROLES`` se deriva de
    ``matrix.ROLE_ACTION_MATRIX['sign_dictamen']``, que NO se la concede al
    superadmin pese a su "Total" en Triage §2. Antes el router la hardcodeaba y
    aceptaba una firma que la matriz —y por tanto la consola— negaba."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    resp = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "restricted"},
        headers=_tok("takab_superadmin"),
    )
    assert resp.status_code == 403

    # Pero sí lee la cadena (tiene /triage).
    chain = await client.get(f"/incidents/{iid}/dictamens", headers=_tok("takab_superadmin"))
    assert chain.status_code == 200
