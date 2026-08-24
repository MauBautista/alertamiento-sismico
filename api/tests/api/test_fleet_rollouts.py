"""Canary por cohortes (T-2.70): primero uno, se observa, luego el resto.

El escenario que decide la ficha, y que ningún otro test del repo cubre: **el
gabinete que ACUSA la orden y no arranca el código**. Ahí un canary ingenuo
—«¿llegó el comando? entonces sigue»— suelta la versión mala a toda la cohorte,
que es exactamente el incidente que esta tarea existe para no tener.

Aquí `fw_running` se escribe a mano en `gateways` porque en producción lo escribe
la ingesta desde el latido (T-2.69). Lo que se mide no es cómo llega ese dato,
sino qué hace la nube con él.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.commands.publisher import PublishError
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher

pytestmark = pytest.mark.asyncio

KEY_1 = "clave-rollout-1"
KEY_2 = "clave-rollout-2"
GW_1 = "7c800000-0000-0000-0000-0000000000e1"
GW_2 = "7c800000-0000-0000-0000-0000000000e2"
THING_1 = "gw-roll-1"
THING_2 = "gw-roll-2"
# DOS SITIOS PROPIOS, y no `DB_SITE_PRIV`. Ese sitio lo comparten varios ficheros
# y `test_commands_router.py` ya le cuelga un gateway (`gw-cmd-test-a`): como
# `SELECT_GATEWAY` elige UNO por sitio, el rollout acababa firmando contra un
# `iot_thing` ajeno cuya clave no está en el mapa de este fichero — 503 en la
# suite completa y verde en aislado, que es la peor forma de rojo.
SITE_1 = "7a000000-0000-0000-0000-0000000000e1"
SITE_2 = "7a000000-0000-0000-0000-0000000000e2"

RELEASE = "20260823T120000Z-abc1234"
TARGET_FW = "abc1234"


class _FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        if topic.endswith("nunca"):  # pragma: no cover - guarda de forma
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
    monkeypatch.setenv(
        "TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING_1: KEY_1, THING_2: KEY_2})
    )


@pytest.fixture
async def dos_gabinetes(base_data) -> list[str]:
    """Dos sitios del MISMO tenant, cada uno con su gabinete comandable."""
    engine = get_engine()
    async with engine.begin() as conn:
        for site, gw, serial, thing, lon in (
            (SITE_1, GW_1, "SER-ROLL-1", THING_1, -99.09),
            (SITE_2, GW_2, "SER-ROLL-2", THING_2, -99.10),
        ):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                    "(:s, :t, :code, :name, "
                    "ST_SetSRID(ST_MakePoint(:lon, 19.44), 4326)::geography) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "s": site,
                    "t": au.DB_TENANT_PRIV,
                    "code": f"S-ROLL-{serial[-1]}",
                    "name": f"Sitio rollout {serial[-1]}",
                    "lon": lon,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                    "VALUES (:g, :t, :s, :serial, :thing) ON CONFLICT DO NOTHING"
                ),
                {
                    "g": gw,
                    "t": au.DB_TENANT_PRIV,
                    "s": site,
                    "serial": serial,
                    "thing": thing,
                },
            )
    return [SITE_1, SITE_2]


async def _declarar_fw(site_id: str, fw: str | None) -> None:
    """Lo que en producción escribe la ingesta desde el latido (T-2.69)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE gateways SET fw_running = :fw WHERE site_id = CAST(:s AS uuid)"),
            {"fw": fw, "s": site_id},
        )


def _tok() -> str:
    return au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)


async def _abrir(client, sitios: list[str]) -> dict:
    r = await client.post(
        "/fleet/rollouts",
        json={"release_id": RELEASE, "site_ids": sitios, "canary_site_id": sitios[0]},
        headers=au.bearer(_tok()),
    )
    assert r.status_code == 202, r.text
    return r.json()


async def test_abrir_un_rollout_activa_UNO_y_se_para(
    client, dos_gabinetes, publisher: _FakePublisher
) -> None:
    """No hay parámetro para «actívalos todos», y esa ausencia es la ficha
    entera: un despliegue a toda la flota a la vez es un incidente a toda la
    flota a la vez."""
    cuerpo = await _abrir(client, dos_gabinetes)

    assert cuerpo["state"] == "canary"
    assert cuerpo["target_fw"] == TARGET_FW
    fases = {s["phase"]: s for s in cuerpo["sites"]}
    assert fases["canary"]["activated"] is True
    assert fases["resto"]["activated"] is False
    assert len(publisher.published) == 1, "se activó más de un gabinete"
    _topic, envelope = publisher.published[0]
    assert envelope["payload"]["action"] == "update_activate"
    assert envelope["payload"]["release_id"] == RELEASE


async def test_el_canary_que_ACUSA_pero_no_arranca_NO_deja_avanzar(
    client, dos_gabinetes, publisher: _FakePublisher
) -> None:
    """EL ESCENARIO QUE DECIDE LA FICHA.

    El comando llegó y el gabinete lo acusó — pero su proceso sigue ejecutando el
    código de antes. Un canary que se conformara con el ack soltaría la versión
    mala al resto de la cohorte. Aquí el 409 dice qué se esperaba y qué se recibe.
    """
    cuerpo = await _abrir(client, dos_gabinetes)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE commands SET status = 'acked' WHERE command_id IS NOT NULL")
        )
    await _declarar_fw(dos_gabinetes[0], "viejo99")

    r = await client.post(
        f"/fleet/rollouts/{cuerpo['rollout_id']}/advance", headers=au.bearer(_tok())
    )
    assert r.status_code == 409, r.text
    assert TARGET_FW in r.text and "viejo99" in r.text
    assert "Un ack no basta" in r.text
    assert len(publisher.published) == 1, "soltó la cohorte con el canary sin confirmar"


async def test_sin_noticias_del_canary_tampoco_se_avanza(
    client, dos_gabinetes, publisher: _FakePublisher
) -> None:
    """`fw_running` en `null` es «el gabinete no lo ha dicho», que NO es
    «confirmado». Tratar la ausencia de dato como buena señal es la familia de
    defecto que la regla de oro 7 persigue en la UI y que aquí costaría una
    cohorte."""
    cuerpo = await _abrir(client, dos_gabinetes)
    await _declarar_fw(dos_gabinetes[0], None)

    r = await client.post(
        f"/fleet/rollouts/{cuerpo['rollout_id']}/advance", headers=au.bearer(_tok())
    )
    assert r.status_code == 409
    assert len(publisher.published) == 1


async def test_con_el_canary_confirmado_se_suelta_el_resto(
    client, dos_gabinetes, publisher: _FakePublisher
) -> None:
    cuerpo = await _abrir(client, dos_gabinetes)
    await _declarar_fw(dos_gabinetes[0], TARGET_FW)

    r = await client.post(
        f"/fleet/rollouts/{cuerpo['rollout_id']}/advance", headers=au.bearer(_tok())
    )
    assert r.status_code == 202, r.text
    despues = r.json()
    assert despues["state"] == "desplegado"
    assert all(s["activated"] for s in despues["sites"])
    assert len(publisher.published) == 2
    assert {t for t, _ in publisher.published} == {
        f"takab/cmd/{THING_1}",
        f"takab/cmd/{THING_2}",
    }


async def test_avanzar_dos_veces_no_reactiva_a_nadie(
    client, dos_gabinetes, publisher: _FakePublisher
) -> None:
    """Idempotencia: cada activación cuesta un reinicio del cliente, y en un
    gabinete cuyo dueño de pines siga dentro de `takab-edge`, un ciclo de gas y
    retenedores. Repetir la orden por un doble clic no puede costar eso."""
    cuerpo = await _abrir(client, dos_gabinetes)
    await _declarar_fw(dos_gabinetes[0], TARGET_FW)
    assert (
        await client.post(
            f"/fleet/rollouts/{cuerpo['rollout_id']}/advance", headers=au.bearer(_tok())
        )
    ).status_code == 202
    r = await client.post(
        f"/fleet/rollouts/{cuerpo['rollout_id']}/advance", headers=au.bearer(_tok())
    )
    assert r.status_code == 409
    assert len(publisher.published) == 2


async def test_abortar_manda_revertir_SOLO_a_lo_ya_activado(
    client, dos_gabinetes, publisher: _FakePublisher
) -> None:
    """Pedirle volver atrás a un gabinete que nunca estrenó nada le costaría un
    reinicio por una versión que jamás corrió."""
    cuerpo = await _abrir(client, dos_gabinetes)

    r = await client.post(
        f"/fleet/rollouts/{cuerpo['rollout_id']}/abort",
        json={"motivo": "el SOC vio latencias raras"},
        headers=au.bearer(_tok()),
    )
    assert r.status_code == 202, r.text
    assert r.json()["state"] == "abortado"
    reversiones = [
        e for _t, e in publisher.published if e["payload"]["action"] == "update_rollback"
    ]
    assert len(reversiones) == 1, "revirtió a un gabinete que nunca activó nada"
    assert reversiones[0]["payload"]["motivo"] == "el SOC vio latencias raras"


async def test_un_rollout_no_puede_mezclar_dos_clientes(client, dos_gabinetes) -> None:
    """Actualizar varios clientes a la vez es exactamente lo que el canary existe
    para impedir, así que el modelo lo prohíbe en vez de confiar en el runbook."""
    # Sitio comandable de OTRO tenant. Se crea aquí y no se reusa `DB_SITE_PRIV2`
    # a propósito: ese sitio existe justo para NO tener gateway, y darle uno
    # rompería los tests que miden el 409 de «sitio sin gabinete comandable».
    otro_sitio = "7c900000-0000-0000-0000-0000000000f1"
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-ROLL-OTRO', 'Sitio de otro cliente', "
                "ST_SetSRID(ST_MakePoint(-99.20, 19.50), 4326)::geography) "
                "ON CONFLICT DO NOTHING"
            ),
            {"s": otro_sitio, "t": au.DB_TENANT_PRIV2},
        )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-ROLL-X', 'gw-roll-x') ON CONFLICT DO NOTHING"
            ),
            {
                "g": "7c800000-0000-0000-0000-0000000000e9",
                "t": au.DB_TENANT_PRIV2,
                "s": otro_sitio,
            },
        )
    r = await client.post(
        "/fleet/rollouts",
        json={"release_id": RELEASE, "site_ids": [dos_gabinetes[0], otro_sitio]},
        headers=au.bearer(_tok()),
    )
    assert r.status_code == 422, r.text
    assert "UN tenant" in r.text


async def test_una_release_sin_sha_reconocible_no_abre_rollout(client, dos_gabinetes) -> None:
    """Sin saber qué debe declarar `fw_running`, «confirmado» no se puede
    decidir — y un canary que no puede decidir es un canary que aprueba."""
    r = await client.post(
        "/fleet/rollouts",
        json={"release_id": "heredada-20260101T000000Z", "site_ids": dos_gabinetes},
        headers=au.bearer(_tok()),
    )
    assert r.status_code == 422
    assert "fw_running" in r.text


async def test_el_dueno_del_cliente_no_abre_rollouts(client, dos_gabinetes) -> None:
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        "/fleet/rollouts",
        json={"release_id": RELEASE, "site_ids": dos_gabinetes},
        headers=au.bearer(tok),
    )
    assert r.status_code == 403


async def test_la_vista_distingue_ACUSADO_de_EN_EJECUCION(
    client, dos_gabinetes, publisher: _FakePublisher
) -> None:
    """Los dos hechos viajan por separado a propósito: `command_status` dice si
    la orden llegó, `fw_running` si el gabinete arrancó ese código. Fundirlos en
    un solo booleano es cómo se pierde la distinción que hace útil al canary."""
    cuerpo = await _abrir(client, dos_gabinetes)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE commands SET status = 'acked'"))
    await _declarar_fw(dos_gabinetes[0], "viejo99")

    r = await client.get(f"/fleet/rollouts/{cuerpo['rollout_id']}", headers=au.bearer(_tok()))
    assert r.status_code == 200, r.text
    canary = next(s for s in r.json()["sites"] if s["phase"] == "canary")
    assert canary["command_status"] == "acked"
    assert canary["fw_running"] == "viejo99"
    assert canary["confirmed"] is False
