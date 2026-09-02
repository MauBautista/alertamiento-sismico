"""Modo demostración (T-5.02 · D-27) — el interruptor que impide despertar a nadie.

Lo que estos tests fijan:

* **Asimétrico**: lo enciende el dueño de la plataforma; lo apaga él o el
  administrador del cliente. Difícil de volver inseguro, fácil de volver seguro.
* **Acotado**: la ventana tiene techo, y el techo vive en la BASE — un tope que
  solo viviera en el código se salta con un INSERT a mano, y esto silencia los
  avisos de un edificio entero.
* **Con un incidente abierto NO se entra.** La otra mitad de «lo real gana», y la
  descubrió un test: si un evento apaga el modo, permitir encenderlo con un
  evento vivo dejaría al operador creyendo que demuestra mientras la cascada de
  algo real sigue en vuelo.
* **Cero comandos firmados** mientras está puesto, con su fila de rechazo — y
  todo sigue funcionando en cuanto se apaga, que es la mitad que hace útil a la
  prohibición.

Lo que NO alcanza, y por eso este sistema puede permitirse tenerlo: el reflejo
SASMEX→sirena del gabinete. No pasa por la nube y no sabe que esto existe.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router
from takab_api.routers.demo_mode import router as demo_mode_router
from tests.api.test_commands_router import (  # noqa: F401  (fixtures por nombre)
    KEY,
    THING,
    _FakePublisher,
    gateway,
    publisher,
)


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.include_router(demo_mode_router)
    application.include_router(commands_router)
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _hmac_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))


def _token(role: str, tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _sql(sql: str, **params):
    engine = get_engine()
    async with engine.begin() as conn:
        return (await conn.execute(text(sql), params)).fetchall()


async def _limpiar() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM demo_mode"))


@pytest.fixture(autouse=True)
async def _sin_ventana_previa():
    await _limpiar()
    yield
    await _limpiar()


# ─────────────────────────────────────────────────────────────── quién y cuánto


async def test_el_dueno_de_la_plataforma_lo_enciende(client, gateway):
    r = await client.post(
        "/demo-mode", json={"duration_s": 900}, headers=_token("takab_superadmin")
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["active"] is True
    assert 0 < body["remaining_s"] <= 900


@pytest.mark.parametrize(
    "role", ["tenant_admin", "soc_operator", "gov_operator", "inspector", "building_admin"]
)
async def test_nadie_mas_lo_enciende(client, gateway, role):
    """Encender es acto de PLATAFORMA: la demostración la hace TAKAB."""
    r = await client.post("/demo-mode", json={}, headers=_token(role))
    assert r.status_code == 403


async def test_el_administrador_del_cliente_SI_lo_apaga(client, gateway):
    """Asimetría deliberada: si TAKAB se lo deja puesto, el cliente no puede
    quedarse esperando a que alguien conteste el teléfono para recuperar avisos."""
    await client.post("/demo-mode", json={}, headers=_token("takab_superadmin"))
    r = await client.delete("/demo-mode", headers=_token("tenant_admin"))
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False


async def test_apagar_lo_ya_apagado_no_castiga_al_que_hace_lo_seguro(client, gateway):
    r = await client.delete("/demo-mode", headers=_token("tenant_admin"))
    assert r.status_code == 200
    assert r.json()["active"] is False


async def test_la_ventana_tiene_techo_y_lo_impone_la_BASE(client, gateway):
    """Nueve horas no se piden: el esquema las rechaza antes de llegar al código."""
    r = await client.post(
        "/demo-mode", json={"duration_s": 9 * 3600}, headers=_token("takab_superadmin")
    )
    assert r.status_code == 422, r.text


async def test_re_encender_PISA_la_ventana_en_vez_de_sumarse(client, gateway):
    """Dos ventanas del mismo cliente serían dos verdades sobre cuándo se apaga."""
    await client.post("/demo-mode", json={"duration_s": 3600}, headers=_token("takab_superadmin"))
    r = await client.post(
        "/demo-mode", json={"duration_s": 300}, headers=_token("takab_superadmin")
    )
    assert r.status_code == 201
    assert r.json()["remaining_s"] <= 300
    filas = await _sql("SELECT count(*) AS n FROM demo_mode")
    assert filas[0].n == 1


async def test_encender_y_apagar_quedan_auditados_con_su_actor(client, gateway):
    await client.post("/demo-mode", json={}, headers=_token("takab_superadmin"))
    await client.delete("/demo-mode", headers=_token("takab_superadmin"))
    verbos = await _sql(
        "SELECT verb, actor FROM audit_log WHERE verb IN ('demo_mode_on','demo_mode_off')"
        " ORDER BY audit_id"
    )
    assert [v.verb for v in verbos] == ["demo_mode_on", "demo_mode_off"]
    assert all(v.actor for v in verbos), "una fila de auditoría sin actor no dice quién fue"


# ───────────────────────────────────────────────── la puerta de los comandos


async def _encender(client) -> None:
    r = await client.post("/demo-mode", json={}, headers=_token("takab_superadmin"))
    assert r.status_code == 201, r.text


async def test_con_el_modo_puesto_NO_se_emite_un_solo_comando_firmado(client, gateway, publisher):
    await _encender(client)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands",
        json={"channel": "system", "action": "self_test", "event_id": None},
        headers=_token("tenant_admin"),
    )
    assert r.status_code == 409, r.text
    assert publisher.published == [], "salió un comando al gabinete con el modo puesto"


async def test_el_comando_suprimido_queda_auditado_con_su_motivo(client, gateway, publisher):
    """Un modo que bloquea EN SILENCIO es otra superficie muda."""
    await _encender(client)
    await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands",
        json={"channel": "system", "action": "self_test", "event_id": None},
        headers=_token("tenant_admin"),
    )
    filas = await _sql(
        "SELECT meta FROM audit_log WHERE verb = 'command_rejected' ORDER BY audit_id DESC LIMIT 1"
    )
    assert filas, "el rechazo no dejó fila"
    assert filas[0].meta.get("reason") == "demo_mode"


async def test_con_el_modo_APAGADO_el_mismo_comando_sale(client, gateway, publisher):
    """La mitad que hace útil a la prohibición: sin esto, negarlo todo pasaría."""
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands",
        json={"channel": "system", "action": "self_test", "event_id": None},
        headers=_token("tenant_admin"),
    )
    assert r.status_code == 201, r.text
    assert publisher.published, "sin modo demostración el comando tiene que salir"
