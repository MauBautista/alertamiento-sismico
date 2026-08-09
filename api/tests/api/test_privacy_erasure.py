"""T-2.80 · ``/privacy/erasure`` de punta a punta.

Lo que se mide aquí y no en `tests/test_privacy_erasure.py` (que prueba la capa
de datos): que el derecho se ejerce **por HTTP con el token del titular**, que la
respuesta no lleva PII, y las dos decisiones de producto que solo se ven desde
fuera —el diferimiento por incidente abierto y el 200 idempotente—.

LA TRAMPA DE ESTE ARCHIVO
─────────────────────────
El `sub` va FIJO en cada token (``make_token`` genera uno aleatorio si no se le
da): con un sub distinto por petición, el titular que ejerce ARCO y el que lo
consulta serían personas distintas y la mitad de los tests pasarían por el motivo
equivocado. Es la misma trampa que documenta ``test_privacy.py``.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app

# Titulares fijos (ver la nota de arriba).
OCC = "7f000000-0000-0000-0000-00000000cc01"
OCC_LIMPIO = "7f000000-0000-0000-0000-00000000cc02"
OCC_B = "7f000000-0000-0000-0000-00000000cc03"

NOMBRE = "Ernestina Zapopan Quinones"
TELEFONO = "+525599887799"
PUNTO = "ST_SetSRID(ST_MakePoint(-99.1332,19.4326),4326)::geography"


def _ocupante(user: str = OCC, tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token("occupant", tenant=tenant, site_scope="*", user_id=user))


@pytest.fixture
async def limpia_arco(base_data):
    """`privacy_erasures` es append-only: DELETE lo veta el trigger, TRUNCATE no."""
    yield
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE privacy_erasures CASCADE"))


async def _siembra(
    user: str = OCC,
    tenant: str = au.DB_TENANT_PRIV,
    site: str = au.DB_SITE_PRIV,
    *,
    incident_id: str | None = None,
    nombre: str = NOMBRE,
) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO user_profiles (user_sub, tenant_id, display_name, phone) "
                "VALUES (CAST(:u AS uuid), :t, :n, :p) ON CONFLICT (user_sub) DO NOTHING"
            ),
            {"u": user, "t": tenant, "n": nombre, "p": TELEFONO},
        )
        await conn.execute(
            text(
                "INSERT INTO life_checkins "
                "(tenant_id, incident_id, user_id, site_id, status, geom) "
                f"VALUES (:t, CAST(:i AS uuid), CAST(:u AS uuid), :s, 'safe', {PUNTO})"
            ),
            {"t": tenant, "i": incident_id, "u": user, "s": site},
        )


@pytest.mark.anyio
async def test_el_titular_ejerce_arco_y_la_respuesta_no_lleva_pii(limpia_arco) -> None:
    """201 con los conteos de lo anonimizado, y ni rastro del dato anonimizado."""
    await _siembra()
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/privacy/erasure",
            json={"right": "cancelacion", "via": "mobile", "confirm": True},
            headers=_ocupante(),
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created"] is True
    assert body["user_sub"] == OCC
    assert body["affected"]["life_checkins"] == 1
    assert body["affected"]["user_profiles"] == 1
    assert len(body["audit_digest"]) == 64
    # El cuerpo entero, no solo los campos que se me ocurra mirar.
    assert NOMBRE not in resp.text
    assert TELEFONO not in resp.text


@pytest.mark.anyio
async def test_ejercerlo_dos_veces_devuelve_200_y_la_misma_lapida(limpia_arco) -> None:
    """Idempotencia por HTTP. Un 409 aquí haría creer que el borrado no ocurrió."""
    await _siembra()
    cuerpo = {"right": "cancelacion", "via": "mobile", "confirm": True}
    async with au.client_for(create_app()) as client:
        primera = await client.post("/privacy/erasure", json=cuerpo, headers=_ocupante())
        segunda = await client.post("/privacy/erasure", json=cuerpo, headers=_ocupante())
    assert primera.status_code == 201
    assert segunda.status_code == 200
    assert segunda.json()["created"] is False
    assert segunda.json()["erasure_id"] == primera.json()["erasure_id"]
    assert segunda.json()["audit_digest"] == primera.json()["audit_digest"]


@pytest.mark.anyio
async def test_un_incidente_abierto_difiere_el_borrado(limpia_arco, make_incident) -> None:
    """DECISIÓN de producto, visible solo desde fuera.

    La ubicación de un check-in es dato de rescate EN VIVO. El derecho no se
    niega: se aplaza, y el mensaje lo dice para que la app no lo pinte como un
    error del usuario.
    """
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, state="open")
    await _siembra(incident_id=inc)
    async with au.client_for(create_app()) as client:
        resp = await client.post("/privacy/erasure", json={"confirm": True}, headers=_ocupante())
    assert resp.status_code == 409, resp.text
    assert "difiere" in resp.json()["detail"]

    # Y no dejó la anonimización a medias.
    engine = get_engine()
    async with engine.begin() as conn:
        fila = (
            await conn.execute(
                text("SELECT display_name FROM user_profiles WHERE user_sub = CAST(:u AS uuid)"),
                {"u": OCC},
            )
        ).first()
    assert fila[0] == NOMBRE


@pytest.mark.anyio
async def test_la_peticion_diferida_queda_auditada(limpia_arco, make_incident) -> None:
    """El 409 hace rollback: sin auditoría FUERA DE BANDA no quedaría constancia.

    Importa porque el plazo legal de respuesta corre desde que el titular pide,
    no desde que el sistema puede. Sin esta fila, una solicitud diferida sería
    indistinguible de una que nunca se hizo.
    """
    inc = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, state="open")
    await _siembra(incident_id=inc)
    async with au.client_for(create_app()) as client:
        await client.post("/privacy/erasure", json={"confirm": True}, headers=_ocupante())

    engine = get_engine()
    async with engine.begin() as conn:
        n = await conn.scalar(
            text("SELECT count(*) FROM audit_log WHERE verb = 'privacy_erasure_deferred'")
        )
    assert n == 1


@pytest.mark.anyio
async def test_sin_confirmacion_explicita_no_se_borra_nada(limpia_arco) -> None:
    """La anonimización es IRREVERSIBLE: un POST accidental no puede deshacerse."""
    await _siembra()
    async with au.client_for(create_app()) as client:
        sin = await client.post("/privacy/erasure", json={}, headers=_ocupante())
        falso = await client.post("/privacy/erasure", json={"confirm": False}, headers=_ocupante())
    assert sin.status_code == 422
    assert falso.status_code == 422


@pytest.mark.anyio
async def test_el_cuerpo_no_admite_un_sujeto(limpia_arco) -> None:
    """`extra="forbid"`: intentar ejercer ARCO por otro es un 422, no un borrado ajeno.

    La defensa real está en la base (la función no tiene parámetro de sujeto);
    esto solo hace que el intento falle ruidosamente en la frontera.
    """
    await _siembra()
    await _siembra(user=OCC_LIMPIO, nombre="Otra Persona")
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/privacy/erasure",
            json={"confirm": True, "user_sub": OCC_LIMPIO},
            headers=_ocupante(),
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_la_prueba_de_integridad_se_recalcula_en_vivo(limpia_arco) -> None:
    """CRITERIO 3 por HTTP: el servidor recalcula el sello y declara si cuadra."""
    await _siembra()
    async with au.client_for(create_app()) as client:
        antes = await client.get("/privacy/erasure", headers=_ocupante())
        assert antes.status_code == 404

        creada = await client.post("/privacy/erasure", json={"confirm": True}, headers=_ocupante())
        prueba = await client.get("/privacy/erasure", headers=_ocupante())

    assert prueba.status_code == 200
    body = prueba.json()
    assert body["audit_intact"] is True
    assert body["audit_digest_now"] == creada.json()["audit_digest"]
    assert body["erasure"]["erasure_id"] == creada.json()["erasure_id"]


@pytest.mark.anyio
async def test_la_lapida_de_otro_tenant_no_se_ve(limpia_arco) -> None:
    """Regla de oro 5, en la superficie HTTP."""
    await _siembra(user=OCC, tenant=au.DB_TENANT_PRIV, site=au.DB_SITE_PRIV)
    async with au.client_for(create_app()) as client:
        await client.post("/privacy/erasure", json={"confirm": True}, headers=_ocupante())
        ajeno = await client.get(
            "/privacy/erasure", headers=_ocupante(user=OCC, tenant=au.DB_TENANT_PRIV2)
        )
    assert ajeno.status_code == 404
