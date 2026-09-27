"""[T-2.109] El registro de un token DECLARA si podrá recibir algo.

``POST /me/push-tokens`` sigue aceptando ``site_id`` nulo — el contrato no
cambia: un dispositivo puede pedir permiso y registrarse antes de canjear su
código de enrolamiento. Lo que no puede es pasar por cubierto. El orquestador
elige destinatarios con ``WHERE site_id = <uuid> AND tenant_id = ... AND
revoked_at IS NULL``, y NULL no iguala a un UUID: un token sin inmueble no es
destinatario de NINGÚN sitio.

Eso tiene que quedar dicho donde se pueda leer, no deducirse. El día que
GATE-STORE (T-2.97) encienda APNs/FCM y nadie reciba nada, la primera pregunta
será cuántos teléfonos se registraron sin edificio, y la auditoría es lo único
que sobrevive a esa noche.

El aislamiento multi-tenant de ``assert_site_access`` NO se toca: un token
contra el sitio de otro tenant sigue siendo 404 (se re-verifica aquí para que
esta ficha no lo afloje sin que nadie se entere).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app

OCC_USER = "70000000-0000-0000-0000-00000000cc01"
ZONE_PRIV = "7d000000-0000-0000-0000-0000000000d9"


@pytest.fixture(autouse=True)
def _occupants_pool(monkeypatch: pytest.MonkeyPatch):
    """Habilita el pool de ocupantes encima del entorno base (_auth_env)."""
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


def _occ() -> str:
    return au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC_USER)


async def _seed_zone_and_code(code: str = "CODE-T2109") -> None:
    engine = get_engine()
    params = {"zone": ZONE_PRIV, "tenant": au.DB_TENANT_PRIV, "site": au.DB_SITE_PRIV, "code": code}
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code, evac_policy) "
                "VALUES (:zone, :tenant, :site, 'P9-A', 'P9', 'shelter') "
                "ON CONFLICT (zone_id) DO NOTHING"
            ),
            params,
        )
        await conn.execute(
            text(
                "INSERT INTO site_enrollment_codes (code, tenant_id, site_id, zone_id, active) "
                "VALUES (:code, :tenant, :site, :zone, true)"
            ),
            params,
        )


async def _audit_meta(push_token_id: str) -> dict:
    """La fila de auditoría del registro (superusuario, solo tests). Se busca por
    el ``object`` del audit trail — el token nativo es material del dispositivo y
    no tiene por qué viajar a una consulta de test."""
    engine = get_engine()
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT meta FROM audit_log WHERE verb = 'push_token_register' "
                    "AND object = :obj ORDER BY ts DESC LIMIT 1"
                ),
                {"obj": f"push_token:{push_token_id}"},
            )
        ).first()
    assert row is not None, "el registro del token no dejó auditoría"
    return row.meta


@pytest.mark.anyio
async def test_registro_con_inmueble_queda_auditado_como_alcanzable(base_data) -> None:
    await _seed_zone_and_code()
    async with au.client_for(create_app()) as client:
        headers = au.bearer(_occ())
        assert (
            await client.post("/me/enrollment", json={"code": "CODE-T2109"}, headers=headers)
        ).status_code == 200

        resp = await client.post(
            "/me/push-tokens",
            json={"platform": "android", "token": "fcm-con-sitio-109", "site_id": au.DB_SITE_PRIV},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["site_id"] == au.DB_SITE_PRIV
        token_id = resp.json()["push_token_id"]

    meta = await _audit_meta(token_id)
    assert meta["site_id"] == au.DB_SITE_PRIV
    assert meta["targetable"] is True


@pytest.mark.anyio
async def test_registro_SIN_inmueble_queda_auditado_como_INALCANZABLE(base_data) -> None:
    """Se acepta (el contrato no cambia) pero se declara: este token no recibirá
    ningún push de sitio mientras siga sin inmueble."""
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/me/push-tokens",
            json={"platform": "android", "token": "fcm-sin-sitio-109"},
            headers=au.bearer(_occ()),
        )
        assert resp.status_code == 201
        assert resp.json()["site_id"] is None
        token_id = resp.json()["push_token_id"]

    meta = await _audit_meta(token_id)
    assert meta["site_id"] is None
    # Lo que convierte la mina en algo detectable: la fila lo dice.
    assert meta["targetable"] is False


@pytest.mark.anyio
async def test_el_sitio_ajeno_sigue_siendo_404(base_data) -> None:
    """Regla de oro 5: esta ficha no puede aflojar ``assert_site_access``. Un
    token contra el sitio de OTRO tenant no existe para este portador."""
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/me/push-tokens",
            json={"platform": "android", "token": "fcm-ajeno-109", "site_id": au.DB_SITE_PRIV2},
            headers=au.bearer(_occ()),
        )
        assert resp.status_code == 404


OCC_USER_2 = "70000000-0000-0000-0000-00000000cc02"


@pytest.mark.anyio
async def test_el_MISMO_telefono_con_OTRO_usuario_sigue_recibiendo_avisos(base_data) -> None:
    """[T-8.13] Medido en el Pixel el 2026-09-24: el token FCM es del APARATO, no de
    la persona. El primero que lo registra se queda la fila, y `pt_self` (RLS por
    `user_sub`) le impedía al siguiente usuario del mismo teléfono tocarla: el
    ON CONFLICT DO UPDATE chocaba con la política, el registro fallaba y la app —
    best-effort— se callaba. El teléfono se quedaba sin push para el edificio del
    usuario nuevo y la alarma llegaba al siguiente poll (5–30 s), no al segundo."""
    await _seed_zone_and_code()
    token_del_aparato = {"platform": "android", "token": "fcm-telefono-compartido"}
    token_b = au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC_USER_2)
    async with au.client_for(create_app()) as client:
        for tok in (_occ(), token_b):
            assert (
                await client.post(
                    "/me/enrollment", json={"code": "CODE-T2109"}, headers=au.bearer(tok)
                )
            ).status_code == 200

        primero = await client.post(
            "/me/push-tokens",
            json={**token_del_aparato, "site_id": au.DB_SITE_PRIV},
            headers=au.bearer(_occ()),
        )
        assert primero.status_code == 201

        segundo = await client.post(
            "/me/push-tokens",
            json={**token_del_aparato, "site_id": au.DB_SITE_PRIV},
            headers=au.bearer(token_b),
        )
        assert segundo.status_code == 201, segundo.text
        assert segundo.json()["site_id"] == au.DB_SITE_PRIV

    engine = get_engine()
    async with engine.begin() as conn:
        filas = (
            await conn.execute(
                text(
                    "SELECT user_sub::text, revoked_at FROM push_tokens "
                    "WHERE token = 'fcm-telefono-compartido'"
                )
            )
        ).all()
    # Un aparato, una fila, y es del usuario que lo tiene AHORA en la mano.
    assert [(f.user_sub, f.revoked_at) for f in filas] == [(OCC_USER_2, None)]


# ── [T-9.05] EL TOKEN DE PUSH ES DEL APARATO ─────────────────────────────────────
#
# La prueba de arriba estuvo roja a propósito desde T-8.13 (guardada en un stash).
# La causa: `pt_self` acota la fila por `user_sub`, y un ON CONFLICT DO UPDATE sobre
# una fila que la RLS no te deja ver no es una actualización — es «new row violates
# row-level security policy (USING expression)». El registro ahora pasa por
# `app_claim_push_token` (SECURITY DEFINER, dueño `takab_ingest`, migración 0071),
# que toma la identidad SOLO de la sesión.

OCC_OTRO_TENANT = "70000000-0000-0000-0000-00000000cc03"
ZONE_PRIV2 = "7d000000-0000-0000-0000-0000000000da"


async def _seed_codigo_en_el_otro_tenant(code: str = "CODE-T905-B") -> None:
    engine = get_engine()
    params = {
        "zone": ZONE_PRIV2,
        "tenant": au.DB_TENANT_PRIV2,
        "site": au.DB_SITE_PRIV2,
        "code": code,
    }
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code, evac_policy) "
                "VALUES (:zone, :tenant, :site, 'B-1', 'B1', 'evacuate') "
                "ON CONFLICT (zone_id) DO NOTHING"
            ),
            params,
        )
        await conn.execute(
            text(
                "INSERT INTO site_enrollment_codes (code, tenant_id, site_id, zone_id, active) "
                "VALUES (:code, :tenant, :site, :zone, true)"
            ),
            params,
        )


def _occ_otro_tenant() -> str:
    return au.occupant_token(tenant=au.DB_TENANT_PRIV2, user_id=OCC_OTRO_TENANT)


async def _fila_del_token(token: str):
    engine = get_engine()
    async with engine.begin() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT push_token_id::text, tenant_id::text, user_sub::text, "
                    "site_id::text, role, platform, endpoint_arn, revoked_at "
                    "FROM push_tokens WHERE token = :t"
                ),
                {"t": token},
            )
        ).all()


async def _bitacora(verbo: str) -> list:
    engine = get_engine()
    async with engine.begin() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT tenant_id::text, actor, object, meta FROM audit_log "
                    "WHERE verb = :v ORDER BY audit_id"
                ),
                {"v": verbo},
            )
        ).all()


@pytest.mark.anyio
async def test_un_usuario_de_OTRO_tenant_tambien_reclama_el_aparato(base_data) -> None:
    """El teléfono cambió de manos entre clientes: un aparato, una fila, y del
    tenant de quien lo tiene AHORA. Si la fila se quedara en el tenant viejo, el
    orquestador de ESE cliente seguiría despertando un teléfono que ya no es suyo
    —con avisos de un edificio ajeno— y el del cliente nuevo no sonaría.

    Queda auditado en los DOS tenants, y en el viejo sin rastro del nuevo dueño:
    la bitácora de un cliente no puede enterarse de quién es el usuario de otro.
    """
    await _seed_zone_and_code()
    await _seed_codigo_en_el_otro_tenant()
    token = {"platform": "android", "token": "fcm-cambia-de-cliente"}
    async with au.client_for(create_app()) as client:
        assert (
            await client.post(
                "/me/enrollment", json={"code": "CODE-T2109"}, headers=au.bearer(_occ())
            )
        ).status_code == 200
        assert (
            await client.post(
                "/me/enrollment",
                json={"code": "CODE-T905-B"},
                headers=au.bearer(_occ_otro_tenant()),
            )
        ).status_code == 200

        primero = await client.post(
            "/me/push-tokens",
            json={**token, "site_id": au.DB_SITE_PRIV},
            headers=au.bearer(_occ()),
        )
        assert primero.status_code == 201
        token_id = primero.json()["push_token_id"]

        segundo = await client.post(
            "/me/push-tokens",
            json={**token, "site_id": au.DB_SITE_PRIV2},
            headers=au.bearer(_occ_otro_tenant()),
        )
        assert segundo.status_code == 201, segundo.text
        assert segundo.json()["push_token_id"] == token_id, "un aparato, UNA fila"
        assert segundo.json()["site_id"] == au.DB_SITE_PRIV2

        # El dueño anterior ya no lo ve; el nuevo sí.
        assert (await client.get("/me/push-tokens", headers=au.bearer(_occ()))).json() == []
        del_nuevo = await client.get("/me/push-tokens", headers=au.bearer(_occ_otro_tenant()))
        assert [t["push_token_id"] for t in del_nuevo.json()] == [token_id]

    [fila] = await _fila_del_token("fcm-cambia-de-cliente")
    assert (fila.tenant_id, fila.user_sub, fila.site_id, fila.role, fila.revoked_at) == (
        au.DB_TENANT_PRIV2,
        OCC_OTRO_TENANT,
        au.DB_SITE_PRIV2,
        "occupant",
        None,
    )

    [liberado] = await _bitacora("push_token_released")
    [reclamado] = await _bitacora("push_token_claimed")
    assert liberado.tenant_id == au.DB_TENANT_PRIV
    assert reclamado.tenant_id == au.DB_TENANT_PRIV2
    for fila_audit in (liberado, reclamado):
        assert fila_audit.object == f"push_token:{token_id}"
        assert fila_audit.meta == {"push_token_id": token_id}
    assert reclamado.actor == f"user:{OCC_OTRO_TENANT}"
    assert OCC_OTRO_TENANT not in liberado.actor, (
        "la bitácora del tenant VIEJO nombra al usuario del tenant nuevo"
    )
    # La auditoría de siempre (T-2.109) sigue ahí, a nombre de quien registró.
    meta = await _audit_meta(token_id)
    assert meta["targetable"] is True


@pytest.mark.anyio
async def test_el_mismo_usuario_re_registrando_NO_es_un_traspaso(base_data) -> None:
    """Rotar o re-registrar el propio token sella `last_seen_at` y ya: sin filas
    de traspaso que harían ruido cada vez que la app arranca."""
    await _seed_zone_and_code()
    body = {"platform": "android", "token": "fcm-mio-de-siempre", "site_id": au.DB_SITE_PRIV}
    async with au.client_for(create_app()) as client:
        headers = au.bearer(_occ())
        assert (
            await client.post("/me/enrollment", json={"code": "CODE-T2109"}, headers=headers)
        ).status_code == 200
        for _ in range(2):
            assert (
                await client.post("/me/push-tokens", json=body, headers=headers)
            ).status_code == 201

    assert await _bitacora("push_token_released") == []
    assert await _bitacora("push_token_claimed") == []
    assert len(await _bitacora("push_token_register")) == 2


@pytest.mark.anyio
async def test_un_sitio_ajeno_sigue_siendo_404_y_NO_roba_el_aparato(base_data) -> None:
    """Regla de oro 5, en el camino nuevo: reclamar el token apuntando al sitio
    de OTRO tenant es el mismo 404 de siempre, y la fila no cambia de dueño."""
    await _seed_zone_and_code()
    await _seed_codigo_en_el_otro_tenant()
    token = {"platform": "android", "token": "fcm-no-se-roba"}
    async with au.client_for(create_app()) as client:
        assert (
            await client.post(
                "/me/enrollment", json={"code": "CODE-T2109"}, headers=au.bearer(_occ())
            )
        ).status_code == 200
        assert (
            await client.post(
                "/me/push-tokens",
                json={**token, "site_id": au.DB_SITE_PRIV},
                headers=au.bearer(_occ()),
            )
        ).status_code == 201

        ajeno = await client.post(
            "/me/push-tokens",
            json={**token, "site_id": au.DB_SITE_PRIV},
            headers=au.bearer(_occ_otro_tenant()),
        )
        assert ajeno.status_code == 404

    [fila] = await _fila_del_token("fcm-no-se-roba")
    assert (fila.tenant_id, fila.user_sub, fila.site_id) == (
        au.DB_TENANT_PRIV,
        OCC_USER,
        au.DB_SITE_PRIV,
    )
    assert await _bitacora("push_token_claimed") == []


@pytest.mark.anyio
async def test_el_endpoint_de_SNS_se_conserva_solo_en_la_misma_plataforma(base_data) -> None:
    """El endpoint de SNS está atado al TOKEN del aparato, no a la persona: se
    conserva al cambiar de dueño. Pero un endpoint creado para otra plataforma
    no sirve, y se tira para que el worker lo vuelva a crear."""
    await _seed_zone_and_code()
    token = "fcm-con-endpoint"
    async with au.client_for(create_app()) as client:
        assert (
            await client.post(
                "/me/enrollment", json={"code": "CODE-T2109"}, headers=au.bearer(_occ())
            )
        ).status_code == 200
        assert (
            await client.post(
                "/me/push-tokens",
                json={"platform": "android", "token": token, "site_id": au.DB_SITE_PRIV},
                headers=au.bearer(_occ()),
            )
        ).status_code == 201
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE push_tokens SET endpoint_arn = 'arn:sns:x' WHERE token = :t"),
                {"t": token},
            )

        otro = au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC_USER_2)
        assert (
            await client.post(
                "/me/enrollment", json={"code": "CODE-T2109"}, headers=au.bearer(otro)
            )
        ).status_code == 200
        assert (
            await client.post(
                "/me/push-tokens",
                json={"platform": "android", "token": token, "site_id": au.DB_SITE_PRIV},
                headers=au.bearer(otro),
            )
        ).status_code == 201
        [fila] = await _fila_del_token(token)
        assert fila.endpoint_arn == "arn:sns:x"

        assert (
            await client.post(
                "/me/push-tokens",
                json={"platform": "ios", "token": token, "site_id": au.DB_SITE_PRIV},
                headers=au.bearer(_occ()),
            )
        ).status_code == 201
        [fila] = await _fila_del_token(token)
        assert (fila.platform, fila.endpoint_arn) == ("ios", None)


@pytest.mark.anyio
async def test_una_lapida_de_ARCO_no_se_reclama(base_data) -> None:
    """`privacy_erase_subject` deja el token como `arco:<id>` y revocado. Con el
    registro capaz de reclamar filas ajenas, ese prefijo resucitaría una
    supresión: 422 en el contrato, y la función de la base lo rechaza igual."""
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/me/push-tokens",
            json={"platform": "android", "token": "arco:7a000000-0000-0000-0000-000000000001"},
            headers=au.bearer(_occ()),
        )
    assert resp.status_code == 422
