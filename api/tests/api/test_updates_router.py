"""Actualización remota firmada (T-2.70): activar una release, o volver.

Mismo patrón que `test_commands_router.py` — publisher falso por override y
claves HMAC inline por gateway (T-1.38) —, porque esto ES la misma superficie
sensible: lo que cambia es que el comando no mueve un relé sino el código desde
el que arranca el gabinete.

Lo que se ancla aquí, y por qué cada cosa:

* que el payload que viaja lleve la firma que el gabinete va a verificar, con el
  `release_id` DENTRO del canónico (si viajara fuera, la firma no lo cubriría y
  cualquiera podría cambiar qué versión se estrena);
* que el estado sea **202 y no 201**: lo aceptado es la orden, no el resultado;
* que un `tenant_admin` NO pueda, aunque sea dueño de su gabinete;
* y que revertir NO acepte a qué versión volver — eso lo sabe el gabinete.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.commands.publisher import PublishError
from takab_api.commands.signing import canonical_payload, sign_command
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher

pytestmark = pytest.mark.asyncio

KEY = "clave-updates-test"
GW = "7c700000-0000-0000-0000-0000000000d1"
THING = "gw-upd-test-a"
RELEASE = "20260823T120000Z-abc1234"


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        if self.fail:
            raise PublishError("iot caído (simulado)")
        self.published.append((topic, json.loads(payload)))


@pytest.fixture
def publisher() -> _FakePublisher:
    return _FakePublisher()


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _hmac_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))


@pytest.fixture
async def gateway(base_data) -> str:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-UPD-A', :thing) ON CONFLICT DO NOTHING"
            ),
            {"g": GW, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "thing": THING},
        )
    return GW


async def test_activar_firma_publica_y_acepta_sin_prometer_exito(
    client, gateway, publisher: _FakePublisher
) -> None:
    tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/update",
        json={"release_id": RELEASE},
        headers=au.bearer(tok),
    )
    assert r.status_code == 202, r.text
    cuerpo = r.json()
    assert cuerpo["action"] == "update_activate"
    assert cuerpo["release_id"] == RELEASE
    # La respuesta NO lleva un `success` de la actualización, y esa ausencia es
    # el punto: aquí nadie sabe todavía si la release nueva levanta.
    assert "success" not in cuerpo

    topic, envelope = publisher.published[0]
    assert topic == f"takab/cmd/{THING}"
    assert envelope["payload"]["channel"] == "system"
    assert envelope["payload"]["action"] == "update_activate"
    # EL `release_id` VIAJA DENTRO DEL CANÓNICO. Si viajara fuera, la firma no lo
    # cubriría y quien pudiera reescribir el mensaje elegiría qué versión estrena
    # un edificio.
    assert envelope["payload"]["release_id"] == RELEASE
    esperada = sign_command(
        KEY.encode(), canonical_payload(envelope["payload"]), envelope["nonce"], envelope["ts"]
    )
    assert envelope["sig"] == esperada


async def test_revertir_no_deja_elegir_a_que_version_se_vuelve(
    client, gateway, publisher: _FakePublisher
) -> None:
    """La versión anterior la sabe el gabinete, y sólo él. La nube podría
    equivocarse de id —o nombrar una release ya podada— y una reversión a
    ninguna parte es peor que ninguna reversión."""
    tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/update/rollback",
        json={"motivo": "el SOC vio latencias raras", "release_id": RELEASE},
        headers=au.bearer(tok),
    )
    assert r.status_code == 422, "el body prohíbe claves extra (extra='forbid')"

    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/update/rollback",
        json={"motivo": "el SOC vio latencias raras"},
        headers=au.bearer(tok),
    )
    assert r.status_code == 202, r.text
    _topic, envelope = publisher.published[0]
    assert envelope["payload"]["action"] == "update_rollback"
    assert envelope["payload"]["motivo"] == "el SOC vio latencias raras"
    assert "release_id" not in envelope["payload"]


async def test_una_reversion_sin_motivo_no_sale(client, gateway) -> None:
    """Mismo criterio que el motivo de una ventana de mantenimiento: una
    decisión sin razón registrada es una decisión que nadie puede revisar."""
    tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/update/rollback", json={}, headers=au.bearer(tok)
    )
    assert r.status_code == 422


async def test_el_dueno_del_cliente_NO_puede_empujar_una_version(client, gateway) -> None:
    """`tenant_admin` puede callar las alarmas de SU gabinete
    (`maintenance_window`) y aun así no puede estrenarle código: no tiene el
    artefacto ni con qué juzgarlo, y una release mala deja su edificio sin
    sirena, sin cierre de gas y sin retenedores."""
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/update",
        json={"release_id": RELEASE},
        headers=au.bearer(tok),
    )
    assert r.status_code == 403, r.text


async def test_un_release_id_que_no_es_un_id_se_rechaza_en_la_nube(
    client, gateway, publisher: _FakePublisher
) -> None:
    """Se valida en los DOS lados a propósito: aquí para dar un 422 que el
    operador entiende, y en el gabinete porque el edge no puede fiarse de que
    quien firma haya validado."""
    tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/update",
        json={"release_id": "../../etc; rm -rf /"},
        headers=au.bearer(tok),
    )
    assert r.status_code == 422
    assert publisher.published == [], "se publicó una orden con un id que no es un id"


async def test_un_sitio_sin_gabinete_comandable_es_409(client, base_data) -> None:
    """Heredado de `issue_signed_command`: sin `iot_thing` no hay a quién
    mandarle nada, y decirlo es mejor que publicar a un topic inexistente."""
    tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV2}/update",
        json={"release_id": RELEASE},
        headers=au.bearer(tok),
    )
    assert r.status_code == 409, r.text


async def test_la_ventana_declarada_viaja_firmada(
    client, gateway, publisher: _FakePublisher
) -> None:
    """En un gabinete cuyo dueño de pines siga dentro de `takab-edge`, activar
    cicla GAS_VALVE y DOOR_RETAINER — y sin esta bandera el gabinete se NIEGA.
    Que viaje dentro del canónico es lo que impide que alguien la añada por el
    camino: declarar que un edificio está avisado no puede ser un detalle de
    transporte."""
    tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/update",
        json={"release_id": RELEASE, "ventana_de_mantenimiento": True},
        headers=au.bearer(tok),
    )
    assert r.status_code == 202, r.text
    _topic, envelope = publisher.published[0]
    assert envelope["payload"]["ventana_de_mantenimiento"] is True
    esperada = sign_command(
        KEY.encode(), canonical_payload(envelope["payload"]), envelope["nonce"], envelope["ts"]
    )
    assert envelope["sig"] == esperada


async def test_la_orden_queda_registrada_como_comando_pendiente(client, gateway) -> None:
    """Regla de oro 8: nonce UNIQUE + fila `pending` + TTL. Sin la fila, un
    replay no tendría contra qué chocar y nadie podría responder después a «quién
    ordenó estrenar esa versión»."""
    tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/update",
        json={"release_id": RELEASE},
        headers=au.bearer(tok),
    )
    assert r.status_code == 202
    engine = get_engine()
    async with engine.begin() as conn:
        fila = (
            (
                await conn.execute(
                    text(
                        "SELECT channel, action, status, nonce, expires_at FROM commands "
                        "WHERE command_id = :c"
                    ),
                    {"c": r.json()["command_id"]},
                )
            )
            .mappings()
            .one()
        )
    assert fila["channel"] == "system"
    assert fila["action"] == "update_activate"
    assert fila["status"] == "pending"
    assert fila["nonce"]
    assert fila["expires_at"] is not None
