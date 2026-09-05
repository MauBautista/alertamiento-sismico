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


# ── [T-5.20] Firmar deja verbo en la bitácora ───────────────────────────────
#
# Firmar escribía la fila del dictamen y —**solo si el veredicto era
# habitable**— una acción en el timeline. No escribía en `audit_log`. El hecho no
# se perdía, pero el sitio donde un perito, un seguro o una auditoría van a
# buscar «quién firmó qué y cuándo» es la bitácora, y el acto de mayor peso legal
# del sistema no estaba ahí. Con un veredicto no habitable, en ningún sitio.


async def _bitacora(incidente: str, verb: str = "dictamen_signed") -> list:
    from sqlalchemy import text

    from takab_api.db.engine import get_engine

    async with get_engine().begin() as conn:
        r = await conn.execute(
            text("SELECT actor, meta FROM audit_log WHERE verb = :v AND object = :o ORDER BY ts"),
            {"v": verb, "o": f"incident:{incidente}"},
        )
        return r.fetchall()


async def test_firmar_deja_VERBO_con_el_veredicto_en_el_detalle(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "normal_operation"},
        headers=_tok("inspector"),
    )
    assert r.status_code == 201, r.text

    filas = await _bitacora(iid)
    assert len(filas) == 1, "el acto de mayor peso legal del sistema no dejó fila"
    actor, meta = filas[0]
    assert actor.startswith("user:")
    assert meta["status"] == "normal_operation"
    assert meta["dictamen_id"] == r.json()["dictamen_id"]
    assert meta["habitable"] is True


async def test_un_veredicto_NO_habitable_tambien_deja_fila(client, make_incident) -> None:
    """Era el peor caso: ni bitácora (nunca) ni timeline (solo si habitable).

    Y es justo el veredicto que más pesa: `no_inhabit_inspect` es la decisión que
    deja a gente fuera de su casa o de su hospital hasta que alguien inspeccione.
    """
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "no_inhabit_inspect"},
        headers=_tok("inspector"),
    )
    assert r.status_code == 201, r.text

    filas = await _bitacora(iid)
    assert len(filas) == 1
    assert filas[0][1]["habitable"] is False


async def test_la_fila_dice_A_QUIEN_SUSTITUYE(client, make_incident) -> None:
    """La cadena se reconstruye desde la bitácora, sin leer la tabla de dictámenes."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    primero = await client.post(
        f"/incidents/{iid}/dictamens", json={"status": "restricted"}, headers=_tok("inspector")
    )
    await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "normal_operation"},
        headers=_tok("inspector"),
    )

    filas = await _bitacora(iid)
    assert [f[1]["supersedes"] for f in filas] == [None, primero.json()["dictamen_id"]]


async def test_una_firma_RECHAZADA_no_deja_fila(client, make_incident) -> None:
    """Un verbo por un acto que no ocurrió es peor que no tener el verbo."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "normal_operation"},
        headers=_tok("soc_operator"),
    )
    assert r.status_code == 403
    assert await _bitacora(iid) == []
