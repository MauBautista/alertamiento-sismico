"""T-2.79 · ``/privacy``: el aviso vigente, el consentimiento y lo que NO gatea.

Tres familias de medida, y las tres tienen su forma de fallar en verde:

1. **RESOLUCIÓN.** Que el aviso del tenant tape al de plataforma no se prueba con
   un tenant: se prueba con DOS, uno con aviso propio y otro sin él, exigiendo
   que reciban textos y digests DISTINTOS. Con un solo tenant, una función que
   devolviera siempre lo mismo pasaría.

2. **OBSOLESCENCIA.** Que el consentimiento de ayer se detecte obsoleto cuando el
   texto cambia. Es el corazón de la ficha y aquí se mide de punta a punta: la
   respuesta del servidor pasa de ``current`` a ``stale`` sin que nadie invalide
   nada a mano, y la fila del consentimiento sigue llevando el digest de AYER.

3. **NO BLOQUEO.** Que un consentimiento ausente u obsoleto **no impide** hacer
   un check-in de vida. Esto no es un detalle de cumplimiento: en una emergencia
   sísmica, un brigadista que no puede pasar lista porque hay un aviso nuevo
   pendiente es un fallo de SEGURIDAD. Reglas de oro 1 y 2.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.privacy import store
from takab_api.privacy.artifacts import get_catalog, notice_digest

ZONE_PRIV = "7e000000-0000-0000-0000-0000000000e1"
OCC_USER = "7e000000-0000-0000-0000-00000000aa01"

_CUERPO_TENANT = (
    "Aviso de privacidad del Hospital de prueba. Tratamos su nombre, su zona y sus "
    "check-ins de vida para coordinar la evacuacion del inmueble.\n\nSus datos no "
    "cruzan a otra organizacion."
)


# El `sub` va FIJO: `make_token` genera uno aleatorio en cada llamada, y con un
# sub distinto por peticion el consentimiento se escribiria a nombre de una
# persona y se leeria a nombre de otra — el test pasaria a verde por el motivo
# equivocado en la mitad de los casos y en rojo en la otra.
ADMIN_SUB = "7e000000-0000-0000-0000-00000000ad01"
ADMIN_SUB_B = "7e000000-0000-0000-0000-00000000ad02"
OPERADOR_SUB = "7e000000-0000-0000-0000-00000000op01".replace("op", "0b")


def _admin(tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    sub = ADMIN_SUB if tenant == au.DB_TENANT_PRIV else ADMIN_SUB_B
    return au.bearer(au.make_token("tenant_admin", tenant=tenant, site_scope="*", user_id=sub))


def _operador(tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(
        au.make_token("soc_operator", tenant=tenant, site_scope="*", user_id=OPERADOR_SUB)
    )


@pytest.fixture(autouse=True)
def _catalogo_limpio():
    """El catálogo del repo se cachea por proceso; los tests lo releen."""
    get_catalog.cache_clear()
    yield
    get_catalog.cache_clear()


@pytest.fixture
async def limpia_privacidad(base_data):
    """Las dos tablas son append-only: DELETE lo veta el trigger, TRUNCATE no."""
    yield
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE privacy_consents, privacy_notices CASCADE"))


def _publicar(version: str, body: str = _CUERPO_TENANT) -> dict:
    return {
        "purpose": "privacy_notice",
        "locale": "es-MX",
        "version": version,
        "title": "Aviso de privacidad del inmueble",
        "body": body,
    }


# ---------------------------------------------------------------------------
# 1 · Resolución: plataforma por defecto, tenant si lo publicó
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sin_aviso_propio_se_sirve_el_de_plataforma_marcado_provisional(
    limpia_privacidad,
) -> None:
    """El artefacto del repo se sirve tal cual, y viaja diciendo que es provisional.

    Que el texto sea provisional no es un comentario en un JSON: llega hasta la
    respuesta de la API con su razón, para que la pantalla pueda decirlo.
    """
    async with au.client_for(create_app()) as client:
        resp = await client.get("/privacy/notice", headers=_admin())
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "repo"
    assert body["provisional"] is True
    assert "PROVISIONAL" in body["provisional_reason"]
    # El digest de la respuesta es el del texto servido, no un valor cualquiera.
    assert body["digest"] == notice_digest(body["locale"], body["title"], body["body"])
    assert len(body["paragraphs"]) > 1


@pytest.mark.anyio
async def test_el_aviso_del_tenant_tapa_al_de_plataforma_y_solo_para_ese_tenant(
    limpia_privacidad,
) -> None:
    """DOS tenants: uno publica el suyo, el otro no. Deben recibir textos distintos.

    Con un solo tenant este test lo pasaría una función que devolviera siempre lo
    mismo. La comparación entre los dos es lo que distingue una resolución real
    de una constante.
    """
    async with au.client_for(create_app()) as client:
        alta = await client.post("/privacy/notices", json=_publicar("1.0.0"), headers=_admin())
        assert alta.status_code == 201

        propio = (await client.get("/privacy/notice", headers=_admin())).json()
        ajeno = (await client.get("/privacy/notice", headers=_admin(au.DB_TENANT_PRIV2))).json()

    assert propio["source"] == "tenant"
    assert propio["version"] == "1.0.0"
    assert propio["digest"] == alta.json()["digest"]
    # El vecino sigue con el de plataforma: publicar no contamina a nadie más.
    assert ajeno["source"] == "repo"
    assert ajeno["digest"] != propio["digest"]


@pytest.mark.anyio
async def test_publicar_es_del_dueno_del_cliente(limpia_privacidad) -> None:
    """Un ``soc_operator`` opera incidentes; no firma el aviso de privacidad."""
    async with au.client_for(create_app()) as client:
        resp = await client.post("/privacy/notices", json=_publicar("1.0.0"), headers=_operador())
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_el_mismo_texto_con_otra_etiqueta_no_es_una_version_nueva(
    limpia_privacidad,
) -> None:
    async with au.client_for(create_app()) as client:
        assert (
            await client.post("/privacy/notices", json=_publicar("1.0.0"), headers=_admin())
        ).status_code == 201
        repetido = await client.post("/privacy/notices", json=_publicar("1.0.1"), headers=_admin())
        etiqueta_repetida = await client.post(
            "/privacy/notices",
            json=_publicar("1.0.0", body=_CUERPO_TENANT + " Parrafo nuevo."),
            headers=_admin(),
        )
    assert repetido.status_code == 409, "mismo texto, otra etiqueta: no es una versión"
    assert etiqueta_repetida.status_code == 409, "misma etiqueta, otro texto: mentiría"


# ---------------------------------------------------------------------------
# 2 · EL CORAZÓN: cambiar el aviso deja obsoleto el consentimiento de ayer
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_aceptar_sella_digest_version_e_instante(limpia_privacidad) -> None:
    async with au.client_for(create_app()) as client:
        aviso = (await client.get("/privacy/notice", headers=_admin())).json()
        creado = await client.post(
            "/privacy/consent",
            json={"decision": "accept", "digest": aviso["digest"], "via": "web"},
            headers=_admin(),
        )
        estado = (await client.get("/privacy/consent", headers=_admin())).json()

    assert creado.status_code == 201
    fila = creado.json()
    assert fila["notice_digest"] == aviso["digest"]
    assert fila["notice_version"] == aviso["version"]
    assert fila["notice_source"] == "repo"
    assert fila["decision"] == "accept"
    assert fila["decided_at"] is not None
    assert estado["state"] == "current"
    assert estado["blocks_emergency_actions"] is False


@pytest.mark.anyio
async def test_cambiar_el_aviso_deja_el_consentimiento_de_ayer_obsoleto(
    limpia_privacidad,
) -> None:
    """EL TEST DE LA FICHA, de punta a punta por HTTP.

    Ayer: se aceptó el aviso de plataforma. Hoy: el cliente publica el suyo. El
    servidor pasa de ``current`` a ``stale`` **sin que nadie invalide nada**, y
    la fila del consentimiento sigue llevando el digest de ayer — que es lo que
    permite decir QUÉ se aceptó, y no solo que se aceptó algo.
    """
    async with au.client_for(create_app()) as client:
        ayer = (await client.get("/privacy/notice", headers=_admin())).json()
        await client.post(
            "/privacy/consent",
            json={"decision": "accept", "digest": ayer["digest"], "via": "web"},
            headers=_admin(),
        )
        antes = (await client.get("/privacy/consent", headers=_admin())).json()
        assert antes["state"] == "current"

        # El aviso cambia.
        await client.post("/privacy/notices", json=_publicar("1.0.0"), headers=_admin())
        despues = (await client.get("/privacy/consent", headers=_admin())).json()

    assert despues["state"] == "stale"
    assert despues["notice"]["digest"] != ayer["digest"], "el vigente es otro texto"
    assert despues["consent"]["notice_digest"] == ayer["digest"], (
        "el consentimiento conserva el digest que selló: cambiar el aviso NO lo reescribió"
    )
    assert despues["consent"]["notice_version"] == ayer["version"]


@pytest.mark.anyio
async def test_no_se_puede_firmar_un_digest_que_ya_no_es_el_vigente(
    limpia_privacidad,
) -> None:
    """Pantalla abierta mientras el aviso cambia ⇒ 409, no una firma del texto nuevo.

    Sin esta guarda, quien leyó el texto A acabaría constando como que aceptó el
    texto B — exactamente la mentira que la tarea existe para impedir.
    """
    async with au.client_for(create_app()) as client:
        viejo = (await client.get("/privacy/notice", headers=_admin())).json()
        await client.post("/privacy/notices", json=_publicar("1.0.0"), headers=_admin())
        resp = await client.post(
            "/privacy/consent",
            json={"decision": "accept", "digest": viejo["digest"], "via": "web"},
            headers=_admin(),
        )
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_retirar_no_borra_el_accept_anterior(limpia_privacidad) -> None:
    """Retirar opera hacia adelante. El registro tiene que poder decir que entre
    el día 1 y el día 2 SÍ había consentimiento."""
    async with au.client_for(create_app()) as client:
        aviso = (await client.get("/privacy/notice", headers=_admin())).json()
        cuerpo = {"digest": aviso["digest"], "via": "web"}
        await client.post(
            "/privacy/consent", json={**cuerpo, "decision": "accept"}, headers=_admin()
        )
        await client.post(
            "/privacy/consent", json={**cuerpo, "decision": "withdraw"}, headers=_admin()
        )
        estado = (await client.get("/privacy/consent", headers=_admin())).json()
        hist = (await client.get("/privacy/consent/history", headers=_admin())).json()

    assert estado["state"] == "withdrawn"
    assert [i["decision"] for i in hist["items"]] == ["withdraw", "accept"]
    assert all(i["notice_digest"] == aviso["digest"] for i in hist["items"])


@pytest.mark.anyio
async def test_retirado_sobre_el_texto_vigente_no_se_pinta_como_current(
    limpia_privacidad,
) -> None:
    """El orden de las ramas importa: si se comparara el digest ANTES de mirar la
    decisión, un ``withdraw`` sobre el texto vigente saldría ``current`` y el
    sistema afirmaría que hay consentimiento donde el sujeto dijo que no."""
    async with au.client_for(create_app()) as client:
        aviso = (await client.get("/privacy/notice", headers=_admin())).json()
        await client.post(
            "/privacy/consent",
            json={"decision": "withdraw", "digest": aviso["digest"], "via": "web"},
            headers=_admin(),
        )
        estado = (await client.get("/privacy/consent", headers=_admin())).json()
    assert estado["state"] == "withdrawn"
    assert estado["consent"]["notice_digest"] == aviso["digest"]


@pytest.mark.anyio
async def test_sin_decidir_nada_el_estado_es_missing(limpia_privacidad) -> None:
    async with au.client_for(create_app()) as client:
        estado = (await client.get("/privacy/consent", headers=_admin())).json()
    assert estado["state"] == "missing"
    assert estado["consent"] is None
    assert estado["notice"] is not None


@pytest.mark.anyio
async def test_la_bitacora_guarda_el_sello_y_no_el_cuerpo(limpia_privacidad) -> None:
    """El `audit_log` no se poda jamás (regla de oro 11): meter ahí una copia del
    aviso entero en cada aceptación lo engorda sin añadir nada. El digest
    identifica el texto, y el texto ya vive íntegro en el artefacto o en la fila.
    """
    async with au.client_for(create_app()) as client:
        aviso = (await client.get("/privacy/notice", headers=_admin())).json()
        await client.post(
            "/privacy/consent",
            json={"decision": "accept", "digest": aviso["digest"], "via": "web"},
            headers=_admin(),
        )
    engine = get_engine()
    async with engine.begin() as conn:
        fila = (
            (
                await conn.execute(
                    text(
                        "SELECT verb, meta FROM audit_log WHERE verb = 'privacy_consent_accept' "
                        "ORDER BY ts DESC LIMIT 1"
                    )
                )
            )
            .mappings()
            .one()
        )
    meta = fila["meta"]
    assert meta["notice_digest"] == aviso["digest"]
    assert meta["state_before"] == "missing"
    assert meta["provisional"] is True
    assert aviso["body"][:60] not in str(meta), "el cuerpo del aviso NO va a la bitácora"


# ---------------------------------------------------------------------------
# 3 · NO BLOQUEO: el consentimiento jamás gatea el camino de emergencia
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_consentimiento_pendiente_no_bloquea_el_checkin(
    base_data, make_incident, limpia_privacidad, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regla de oro 1 y 2, medidas y no afirmadas.

    Se pone el estado PEOR posible —el ocupante no ha consentido nada y además el
    aviso acaba de cambiar— y se exige que el check-in de vida siga dando 201.
    En un sismo, pasar lista no espera a un trámite.
    """
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code, evac_policy) "
                "VALUES (:z, :t, :s, 'P10-A', 'P10', 'shelter') ON CONFLICT DO NOTHING"
            ),
            {"z": ZONE_PRIV, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO site_enrollment_codes (code, tenant_id, site_id, zone_id, active) "
                "VALUES ('CODE-PRIV-79', :t, :s, :z, true) ON CONFLICT DO NOTHING"
            ),
            {"t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "z": ZONE_PRIV},
        )
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    occ = au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC_USER)

    try:
        async with au.client_for(create_app()) as client:
            await client.post(
                "/me/enrollment", json={"code": "CODE-PRIV-79"}, headers=au.bearer(occ)
            )
            # El aviso cambia y el ocupante NO ha consentido nada.
            await client.post("/privacy/notices", json=_publicar("1.0.0"), headers=_admin())
            estado = (await client.get("/privacy/consent", headers=au.bearer(occ))).json()
            assert estado["state"] == "missing", "estado peor posible, a propósito"

            checkin = await client.post(
                f"/incidents/{incident_id}/checkins",
                json={"status": "need_help", "ts_device": datetime.now(UTC).isoformat()},
                headers=au.bearer(occ),
            )
        assert checkin.status_code == 201, (
            "un consentimiento pendiente NO puede impedir pedir ayuda en un sismo"
        )
        assert checkin.json()["status"] == "need_help"
    finally:
        deps._reset_caches()
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM site_enrollment_codes WHERE code = 'CODE-PRIV-79'")
            )
            await conn.execute(
                text("DELETE FROM user_zone_assignments WHERE zone_id = :z"), {"z": ZONE_PRIV}
            )
            await conn.execute(text("DELETE FROM zones WHERE zone_id = :z"), {"z": ZONE_PRIV})


# ---------------------------------------------------------------------------
# 4 · Aislamiento y la costura de WhatsApp
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_historial_de_un_tenant_no_alcanza_al_otro(limpia_privacidad) -> None:
    """Mismo `sub`, dos tenants: el registro no cruza (regla de oro 5)."""
    sub = str(uuid.uuid4())
    a = au.bearer(au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV, user_id=sub))
    b = au.bearer(au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV2, user_id=sub))
    async with au.client_for(create_app()) as client:
        aviso = (await client.get("/privacy/notice", headers=a)).json()
        await client.post(
            "/privacy/consent",
            json={"decision": "accept", "digest": aviso["digest"], "via": "web"},
            headers=a,
        )
        propio = (await client.get("/privacy/consent/history", headers=a)).json()
        ajeno = (await client.get("/privacy/consent/history", headers=b)).json()
    assert len(propio["items"]) == 1
    assert ajeno["items"] == [], "el mismo sub en otro tenant no ve nada"


@pytest.mark.anyio
async def test_optin_de_whatsapp_de_un_tercero_y_la_costura_que_lo_lee(
    limpia_privacidad,
) -> None:
    """El opt-in de un NÚMERO se registra y ``whatsapp_opt_in_at`` lo lee.

    Es el reemplazo exacto de ``notifications.whatsapp.opt_in.at`` del
    ``rule_set`` (T-2.77). Y la prueba no es solo que devuelva una fecha: tras
    retirarlo devuelve ``None``, que es lo que un instante suelto en el
    ``rule_set`` no puede hacer nunca.
    """
    msisdn = "+525512345678"
    async with au.client_for(create_app()) as client:
        aviso = (
            await client.get(
                "/privacy/notice", params={"purpose": "whatsapp_alerts"}, headers=_admin()
            )
        ).json()
        cuerpo = {
            "purpose": "whatsapp_alerts",
            "digest": aviso["digest"],
            "msisdn": msisdn,
            "via": "out_of_band",
        }
        alta = await client.post(
            "/privacy/consents/third-party", json={**cuerpo, "decision": "accept"}, headers=_admin()
        )
        assert alta.status_code == 201

        engine = get_engine()
        async with engine.begin() as conn:
            cuando = await store.whatsapp_opt_in_at(
                conn, tenant_id=au.DB_TENANT_PRIV, msisdn=msisdn
            )
            otro = await store.whatsapp_opt_in_at(
                conn, tenant_id=au.DB_TENANT_PRIV, msisdn="+525599999999"
            )
        assert cuando is not None, "el opt-in registrado se lee del motor"
        assert otro is None, "un número sin opt-in no devuelve fecha"
        assert datetime.now(UTC) - cuando < timedelta(minutes=5)

        await client.post(
            "/privacy/consents/third-party",
            json={**cuerpo, "decision": "withdraw"},
            headers=_admin(),
        )
        async with engine.begin() as conn:
            tras_retirar = await store.whatsapp_opt_in_at(
                conn, tenant_id=au.DB_TENANT_PRIV, msisdn=msisdn
            )
    assert tras_retirar is None, "retirado el consentimiento, no hay opt-in"


@pytest.mark.anyio
async def test_registrar_el_optin_de_un_tercero_es_del_dueno(limpia_privacidad) -> None:
    async with au.client_for(create_app()) as client:
        aviso = (
            await client.get(
                "/privacy/notice", params={"purpose": "whatsapp_alerts"}, headers=_admin()
            )
        ).json()
        resp = await client.post(
            "/privacy/consents/third-party",
            json={
                "purpose": "whatsapp_alerts",
                "decision": "accept",
                "digest": aviso["digest"],
                "msisdn": "+525512345678",
            },
            headers=_operador(),
        )
    assert resp.status_code == 403
